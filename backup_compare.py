#!/usr/bin/env python3
"""Read-only, streaming directory comparison. Python 3.9+; standard library only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

CHUNK_SIZE = 1024 * 1024


def fingerprint(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def is_link(s):
    # Windows junctions and other reparse points are deliberately unsupported.
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)


def guard(path):
    """Reject symlinks/reparse points in every existing path component."""
    if '..' in Path(path).parts:
        raise ValueError("Parent traversal ('..') is not supported; use an explicit absolute path")
    path = Path(os.path.abspath(path))
    for item in reversed((path,) + tuple(path.parents)):
        if is_link(item.lstat()):
            raise OSError('Symlink/reparse point is not followed: ' + str(item))
    return path


def open_checked(path, directory=False):
    """Use descriptor-relative O_NOFOLLOW traversal where POSIX supports it."""
    path = Path(os.path.abspath(path))
    if os.name == 'posix' and hasattr(os, 'O_NOFOLLOW'):
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
        try:
            parts = path.parts[1:]
            for i, part in enumerate(parts):
                flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, 'O_NONBLOCK', 0)
                if i < len(parts) - 1 or directory:
                    flags |= os.O_DIRECTORY
                child = os.open(part, flags, dir_fd=fd)
                os.close(fd)
                fd = child
            return fd
        except BaseException:
            os.close(fd)
            raise
    guard(path)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0)
    return os.open(path, flags)


def hash_file(path, expected):
    fd = open_checked(path)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or fingerprint(before) != fingerprint(expected):
            raise OSError('File changed before reading')
        digest = hashlib.sha256()
        while True:
            chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
        if fingerprint(os.fstat(stream.fileno())) != fingerprint(before):
            raise OSError('File changed while reading')
    guard(path)
    if fingerprint(path.lstat()) != fingerprint(expected):
        raise OSError('File changed after reading')
    return digest.hexdigest()


def scan(root, side):
    entries, snapshots, empty, issues = {}, {}, set(), []

    def issue(rel, exc):
        issues.append({'side': side, 'path': rel, 'reason': str(exc)})

    def visit(path, rel):
        try:
            guard(path)
            before = path.lstat()
            if is_link(before):
                raise OSError('Symlink/reparse point is not followed')
            snapshots[rel] = fingerprint(before)
            if stat.S_ISREG(before.st_mode):
                entries[rel] = ('file', hash_file(path, before))
            elif stat.S_ISDIR(before.st_mode):
                entries[rel] = ('directory', None)
                # POSIX scandir(fd) avoids following a swapped directory symlink.
                if os.name == 'posix' and os.scandir in os.supports_fd:
                    fd = open_checked(path, directory=True)
                    try:
                        if fingerprint(os.fstat(fd)) != fingerprint(before):
                            raise OSError('Directory changed before listing')
                        with os.scandir(fd) as iterator:
                            names = sorted(entry.name for entry in iterator)
                    finally:
                        os.close(fd)
                else:
                    guard(path)
                    with os.scandir(path) as iterator:
                        names = sorted(entry.name for entry in iterator)
                if not names:
                    empty.add(rel)
                for name in names:
                    visit(path / name, name if rel == '.' else rel + '/' + name)
                guard(path)
                if fingerprint(path.lstat()) != fingerprint(before):
                    raise OSError('Directory changed while scanning')
            else:
                raise OSError('Unsupported entry type (not a regular file/directory)')
        except (OSError, ValueError) as exc:
            entries.pop(rel, None)
            empty.discard(rel)
            issue(rel, exc)

    visit(root, '.')
    return {'root': root, 'entries': entries, 'snapshots': snapshots,
            'empty': empty, 'issues': issues, 'side': side}


def validate(tree):
    """Detect observable changes even after an earlier file was hashed."""
    for rel, expected in tree['snapshots'].items():
        path = tree['root'] if rel == '.' else tree['root'].joinpath(*rel.split('/'))
        try:
            guard(path)
            if fingerprint(path.lstat()) != expected:
                raise OSError('Entry changed since it was scanned')
        except (OSError, ValueError) as exc:
            tree['issues'].append({'side': tree['side'], 'path': rel, 'reason': str(exc)})


def compare(source, backup):
    result = {'source': str(source), 'backup': str(backup), 'complete': False,
              'same': [], 'missing': [], 'extra': [], 'different': [],
              'empty_directories': {'same': [], 'missing': [], 'extra': []}, 'issues': []}
    try:
        left, right = guard(source), guard(backup)
        if not left.is_dir() or not right.is_dir():
            raise ValueError('Both roots must be existing directories')
        if os.path.samefile(left, right):
            raise ValueError('Roots must be different directories')
        # realpath/normcase honors the host filesystem; relative names are never folded.
        a, b = (os.path.normcase(os.path.realpath(p)) for p in (left, right))
        common = os.path.commonpath([a, b]) if os.path.splitdrive(a)[0] == os.path.splitdrive(b)[0] else None
        if common in (a, b):
            raise ValueError('Nested roots are not supported')
        trees = [scan(left, 'source'), scan(right, 'backup')]
        for tree in trees:
            validate(tree)
        result['issues'] = [issue for tree in trees for issue in tree['issues']]
        blocked = [issue['path'] for issue in result['issues']]
        def trusted(rel):
            return not any(p == '.' or rel == p or rel.startswith(p + '/') for p in blocked)
        le, re = (tree['entries'] for tree in trees)
        for rel in sorted(set(le) | set(re)):
            if rel == '.' or not trusted(rel):
                continue
            if rel not in re:
                result['missing'].append(rel)
            elif rel not in le:
                result['extra'].append(rel)
            elif le[rel] != re[rel]:
                result['different'].append(rel)
            elif le[rel][0] == 'file':
                result['same'].append(rel)
        el, er = (tree['empty'] for tree in trees)
        result['empty_directories'] = {
            'same': sorted(p for p in el & er if trusted(p)),
            'missing': sorted(p for p in el - er if trusted(p)),
            'extra': sorted(p for p in er - el if trusted(p))}
        result['complete'] = not result['issues']
        if not result['complete']:
            # Conservative: never present any file as verified equal in a partial run.
            result['same'] = []
            result['empty_directories']['same'] = []
    except (OSError, ValueError, RecursionError) as exc:
        result['issues'].append({'side': 'roots', 'path': '.', 'reason': str(exc)})
    differences = any(result[k] for k in ('missing', 'extra', 'different')) or any(
        result['empty_directories'][k] for k in ('missing', 'extra'))
    result['exit_code'] = 2 if not result['complete'] else (1 if differences else 0)
    return result


def render_text(result):
    lines = ['Complete: ' + str(result['complete']).lower(), 'Exit code: ' + str(result['exit_code'])]
    for key in ('missing', 'extra', 'different', 'same'):
        lines.append(key + ': ' + str(len(result[key])))
        lines.extend('  ' + json.dumps(p, ensure_ascii=False) for p in result[key])
    for key, paths in result['empty_directories'].items():
        lines.append('empty_directories.' + key + ': ' + str(len(paths)))
        lines.extend('  ' + json.dumps(p, ensure_ascii=False) for p in paths)
    for issue in result['issues']:
        lines.append('INCOMPLETE: ' + json.dumps(issue, ensure_ascii=False))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only SHA-256 directory comparison (Python 3.9+).')
    parser.add_argument('source', help='Reference directory')
    parser.add_argument('backup', help='Directory to compare against reference')
    parser.add_argument('--json', action='store_true', help='Print structured JSON to stdout')
    args = parser.parse_args(argv)
    result = compare(args.source, args.backup)
    output = json.dumps(result, ensure_ascii=True, indent=2) if args.json else render_text(result)
    try:
        print(output)
    except UnicodeEncodeError:
        print(output.encode(sys.stdout.encoding or 'ascii', errors='backslashreplace').decode(sys.stdout.encoding or 'ascii'))
    return result['exit_code']


if __name__ == '__main__':
    sys.exit(main())
