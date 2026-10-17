import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / 'backup_compare.py'
spec = importlib.util.spec_from_file_location('bc', SCRIPT)
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)

class ReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.a = self.base / 'a'; self.a.mkdir()
        self.b = self.base / 'b'; self.b.mkdir()
    def test_real_directory_permission(self):
        if os.geteuid() == 0: self.skipTest('Root bypasses permissions')
        p = self.a / 'locked'; p.mkdir(); p.chmod(0)
        try:
            r = bc.compare(self.a, self.b)
            self.assertEqual(r['exit_code'], 2)
            self.assertTrue(any(i['path'] == 'locked' for i in r['issues']))
        finally: p.chmod(0o700)
    def test_real_file_permission(self):
        if os.geteuid() == 0: self.skipTest('Root bypasses permissions')
        p = self.a / 'locked'; p.write_bytes(b'private'); p.chmod(0)
        try:
            r = bc.compare(self.a, self.b)
            self.assertEqual(r['exit_code'], 2)
            self.assertNotIn('locked', r['missing'])
        finally: p.chmod(0o600)
    def test_unusual_posix_names_json(self):
        for name in ['line\nbreak', 'back\\slash', 'é', 'e\u0301', '\udcff']:
            (self.a / name).write_bytes(b'same'); (self.b / name).write_bytes(b'same')
        p = subprocess.run([sys.executable, str(SCRIPT), str(self.a), str(self.b), '--json'], capture_output=True)
        r = json.loads(p.stdout)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(r['same']), 5)
    def test_file_swap_symlink_before_open(self):
        p = self.a / 'victim'; p.write_bytes(b'original')
        outside = self.base / 'outside'; outside.write_bytes(b'secret')
        original = bc.open_checked
        def opening(path, directory=False):
            if Path(path) == p:
                p.unlink(); p.symlink_to(outside)
            return original(path, directory)
        with mock.patch.object(bc, 'open_checked', side_effect=opening):
            r = bc.compare(self.a, self.b)
        self.assertEqual(r['exit_code'], 2)
        self.assertEqual(r['same'], [])
    def test_hardlinked_regular_files(self):
        p = self.a / 'file'; p.write_bytes(b'abc'); os.link(p, self.b / 'file')
        self.assertEqual(bc.compare(self.a, self.b)['exit_code'], 0)
    def test_symlink_dotdot_root_rejected(self):
        outside = self.base / 'outside'; outside.mkdir()
        target = outside / 'target'; target.mkdir()
        (self.a / 'link').symlink_to(target, target_is_directory=True)
        (self.a / 'safe').mkdir()
        (outside / 'safe').mkdir()
        (outside / 'safe' / 'important').write_bytes(b'actual root data')
        # OS resolves outside/safe, but abspath silently picks a/safe instead.
        r = bc.compare(self.a / 'link' / '..' / 'safe', self.b)
        self.assertEqual(r['exit_code'], 2, r)
        self.assertTrue(any(i['side'] == 'roots' for i in r['issues']), r)
    def test_deep_tree_never_crashes(self):
        # A reduced stack gives a fast deterministic stress test of recursive traversal.
        paths = []
        p = self.a
        for _ in range(160):
            p = p / 'd'; p.mkdir(); paths.append(p)
        old = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(140)
            r = bc.compare(self.a, self.b)
            self.assertIn(r['exit_code'], (1, 2))
        finally:
            sys.setrecursionlimit(old)
            for p in reversed(paths): p.rmdir()

if __name__ == '__main__': unittest.main(verbosity=2)
