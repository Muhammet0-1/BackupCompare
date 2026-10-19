# Backup Compare

[Turkish](README.md) · [Test evidence](TESTING.md)

[Article](https://lordms.net/en/writing/backup-folder-check/) · [Usage guide](https://lordms.net/en/notes/backup-compare-usage/)

A read-only directory comparator using the Python standard library. It does not copy, delete, repair or back up files. Python 3.9+ is the target; no additional Python package is needed. Windows/macOS/Python 3.9 success has not been verified.

Clone the repository or extract the download, then open a terminal in its root. SOURCE is the reference; BACKUP is the copy being checked. Roots must be existing, separate, non-nested directories. Do not use .. root components.

    python3 backup_compare.py "SOURCE" "BACKUP"
    python3 backup_compare.py "SOURCE" "BACKUP" --json

missing/extra can contain files and directories; different means content or item type differs; same contains regular files with equal SHA256 hashes. All regular files are read in 1 MiB chunks; hashes are compared at shared paths.
empty_directories.missing means an empty source path is not also an EMPTY backup directory; a nonempty backup directory at the same path qualifies. A dot denotes the root.
0 completed/no differences; 1 completed/differences; 2 error/incomplete. Read complete, issues and the exit code together. Incomplete comparisons clear all same lists.

Detected links/reparse points, special files and unreadable entries produce an incomplete result. POSIX uses O_NOFOLLOW protection; Windows/fallback opening can retain a check/open race. This is not a security boundary for a maliciously changing tree.
No atomic snapshot is created; unobserved or later changes can escape detection. Reads may update atime. ACLs/ownership/xattrs/alternate streams/resource forks/sparse layout/hardlink topology are excluded. A match does not guarantee restoration.

Keep reports outside both roots. Start with synthetic files. Test actual restoration separately. Shared reports can contain private names and paths.

Tests:
    python3 -B test_backup_compare.py
    python3 -B review/test_review.py

See TESTING.md for evidence and platform limits. Turkish: README.md.

The optional platform workflow is manual-only (workflow_dispatch), with no push or pull-request trigger. It was not run for this publication because account quota/cost conditions remain unverified. A workflow file is not platform test evidence.

## License

This project is available under the [MIT License](LICENSE).
