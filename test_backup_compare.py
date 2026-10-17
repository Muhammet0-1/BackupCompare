import contextlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import backup_compare as bc


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.a, self.b = self.base / 'source', self.base / 'backup'
        self.a.mkdir()
        self.b.mkdir()

    def write(self, root, name, data=b'abc'):
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def compare(self):
        return bc.compare(self.a, self.b)

    def test_empty_roots(self):
        r = self.compare()
        self.assertEqual(r['exit_code'], 0)
        self.assertEqual(r['empty_directories']['same'], ['.'])

    def test_categories_unicode_spaces_zero_files(self):
        for root in (self.a, self.b):
            self.write(root, 'Türkçe dosya/İstanbul.txt', b'')
            self.write(root, 'changed', b'a' if root == self.a else b'b')
            (root / 'empty').mkdir()
        self.write(self.a, 'missing')
        self.write(self.b, 'extra')
        r = self.compare()
        self.assertEqual(r['exit_code'], 1)
        self.assertEqual(r['same'], ['Türkçe dosya/İstanbul.txt'])
        self.assertEqual(r['different'], ['changed'])
        self.assertEqual(r['missing'], ['missing'])
        self.assertEqual(r['extra'], ['extra'])
        self.assertEqual(r['empty_directories']['same'], ['empty'])

    def test_same_size_and_mtime_different_content(self):
        for root, data in ((self.a, b'ab'), (self.b, b'cd')):
            p = self.write(root, 'file', data)
            os.utime(p, ns=(1234567890000000000, 1234567890000000000))
        self.assertEqual(self.compare()['different'], ['file'])

    def test_large_chunked_read(self):
        data = b'z' * (bc.CHUNK_SIZE * 3 + 17)
        for root in (self.a, self.b):
            self.write(root, 'large', data)
        original = os.fdopen
        sizes = []
        class Wrapper:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(self, size=-1):
                sizes.append(size)
                return self.stream.read(size)
        with mock.patch.object(bc.os, 'fdopen', side_effect=lambda *a, **kw: Wrapper(original(*a, **kw))):
            self.assertEqual(self.compare()['exit_code'], 0)
        self.assertGreater(len(sizes), 6)
        self.assertEqual(set(sizes), {bc.CHUNK_SIZE})

    def test_empty_directory_missing_extra(self):
        (self.a / 'left').mkdir()
        (self.b / 'right').mkdir()
        r = self.compare()
        self.assertEqual(r['empty_directories'], {'same': [], 'missing': ['left'], 'extra': ['right']})
        self.assertEqual(r['exit_code'], 1)

    def test_file_directory_type_conflict(self):
        self.write(self.a, 'entry')
        (self.b / 'entry').mkdir()
        self.assertEqual(self.compare()['different'], ['entry'])

    def test_invalid_same_nested_roots(self):
        file = self.write(self.a, 'file')
        nested = self.a / 'nested'
        nested.mkdir()
        for left, right in [(self.a, self.a), (self.a, self.a / '..' / 'source'),
                            (self.a, nested), (nested, self.a), (self.a, file),
                            (self.a, self.base / 'absent')]:
            with self.subTest(left=left, right=right):
                self.assertEqual(bc.compare(left, right)['exit_code'], 2)

    def test_symlinks_not_hashed(self):
        self.write(self.a, 'normal')
        target = self.write(self.base, 'outside', b'secret')
        try:
            (self.a / 'link').symlink_to(target)
            (self.b / 'dirlink').symlink_to(self.a, target_is_directory=True)
            (self.a / 'broken').symlink_to(self.base / 'absent')
        except OSError as exc:
            self.skipTest(str(exc))
        original = bc.hash_file
        with mock.patch.object(bc, 'hash_file', wraps=original) as hashed:
            r = self.compare()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['same'], [])
        self.assertEqual([call.args[0].name for call in hashed.call_args_list], ['normal'])
        self.assertTrue({'link', 'dirlink', 'broken'}.issubset({i['path'] for i in r['issues']}))
        self.assertEqual(bc.compare(self.b / 'dirlink', self.b)['exit_code'], 2)

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO unavailable')
    def test_unsupported_fifo(self):
        os.mkfifo(self.a / 'pipe')
        self.assertEqual(self.compare()['exit_code'], 2)

    def test_permission_error_simulated(self):
        for root in (self.a, self.b): self.write(root, 'file')
        with mock.patch.object(bc, 'open_checked', side_effect=PermissionError('simulated permission denied')):
            r = self.compare()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['same'], [])
        self.assertIn('simulated', r['issues'][0]['reason'])

    def test_file_permission_error_simulated(self):
        for root in (self.a, self.b): self.write(root, 'file')
        with mock.patch.object(bc, 'hash_file', side_effect=PermissionError('simulated file denied')):
            r = self.compare()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['missing'], [])
        self.assertEqual(r['extra'], [])

    def test_concurrent_change_during_read_simulated(self):
        for root in (self.a, self.b): self.write(root, 'file')
        original = os.fdopen
        changed = [False]
        target = self.a / 'file'
        class Wrapper:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): self.stream.close()
            def fileno(self): return self.stream.fileno()
            def read(self, size=-1):
                value = self.stream.read(size)
                if not changed[0]:
                    target.write_bytes(b'longer replacement')
                    changed[0] = True
                return value
        with mock.patch.object(bc.os, 'fdopen', side_effect=lambda *a, **kw: Wrapper(original(*a, **kw))):
            r = self.compare()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['same'], [])

    def test_change_after_scan_detected(self):
        for root in (self.a, self.b): self.write(root, 'file')
        original = bc.scan
        def scanning(root, side):
            tree = original(root, side)
            if side == 'backup': self.write(self.a, 'file', b'late mutation')
            return tree
        with mock.patch.object(bc, 'scan', side_effect=scanning): r = self.compare()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['same'], [])

    def test_directory_changed_simulated(self):
        self.write(self.a, 'file')
        original = bc.hash_file
        def hashing(path, expected):
            digest = original(path, expected)
            self.write(self.a, 'added', b'late')
            return digest
        with mock.patch.object(bc, 'hash_file', side_effect=hashing): r = self.compare()
        self.assertEqual(r['exit_code'], 2)

    def test_read_only_content_and_metadata(self):
        for root in (self.a, self.b): self.write(root, 'file')
        def snapshot():
            return [(str(p), p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_mode)
                    for root in (self.a, self.b) for p in root.rglob('*') if p.is_file()]
        before = snapshot()
        self.assertEqual(self.compare()['exit_code'], 0)
        self.assertEqual(snapshot(), before)

    def test_case_preserved_on_case_sensitive_host(self):
        self.write(self.a, 'A')
        self.write(self.a, 'a')
        if len(list(self.a.iterdir())) != 2: self.skipTest('Host is case insensitive')
        self.write(self.b, 'A')
        r = self.compare()
        self.assertEqual(r['same'], ['A'])
        self.assertEqual(r['missing'], ['a'])

    def test_cli_json_text_and_exit_codes(self):
        script = str(Path(bc.__file__))
        for expected in (0, 1, 2):
            if expected == 1: self.write(self.a, 'missing')
            right = self.b if expected < 2 else self.base / 'absent'
            for flag in ([], ['--json']):
                p = subprocess.run([sys.executable, script, str(self.a), str(right)] + flag,
                                   text=True, capture_output=True)
                self.assertEqual(p.returncode, expected, p.stderr)
                if flag: self.assertEqual(json.loads(p.stdout)['exit_code'], expected)
                else: self.assertIn('Exit code: ' + str(expected), p.stdout)

    def test_deep_tree_returns_incomplete(self):
        current = self.a
        for _ in range(160):
            current = current / 'd'
            current.mkdir()
        previous = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(140)
            r = self.compare()
        finally:
            sys.setrecursionlimit(previous)
        self.assertEqual(r['exit_code'], 2)
        self.assertFalse(r['complete'])
        self.assertEqual(r['same'], [])
        json.dumps(r)

    def test_parent_traversal_rejected_before_normalization(self):
        (self.a / 'safe').mkdir()
        outside = self.base / 'outside'
        (outside / 'child').mkdir(parents=True)
        (outside / 'safe').mkdir()
        try:
            (self.a / 'link').symlink_to(outside / 'child', target_is_directory=True)
        except OSError as exc:
            self.skipTest(str(exc))
        r = bc.compare(str(self.a / 'link') + '/../safe', self.b)
        self.assertEqual(r['exit_code'], 2)
        self.assertIn('Parent traversal', r['issues'][0]['reason'])

    def test_error_precedence_over_difference(self):
        self.write(self.a, 'missing')
        self.write(self.a, 'bad')
        original = bc.hash_file
        def hashing(path, expected):
            if path.name == 'bad': raise PermissionError('simulated')
            return original(path, expected)
        with mock.patch.object(bc, 'hash_file', side_effect=hashing): r = self.compare()
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['missing'], ['missing'])


if __name__ == '__main__':
    print('Python:', sys.version)
    print('Platform:', platform.platform())
    unittest.main(verbosity=2)
