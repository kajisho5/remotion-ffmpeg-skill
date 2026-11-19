"""The tests' temporary directories are always removed (tests/tmp_dirs.py, docs/adr/0002)."""
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"


class TmpDirs(unittest.TestCase):
    def setUp(self):
        # the root the child processes write under; made and removed here, not through tmp_dir (which is under test)
        self.root = tempfile.mkdtemp(prefix="rfs-tmpcheck-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def env(self, **extra):
        env = dict(os.environ, RFS_TEST_TMPDIR=self.root, PYTHONPATH=str(TESTS) + os.pathsep + os.environ.get("PYTHONPATH", ""))
        env.pop("RFS_KEEP_TEST_TMP", None)
        env.update(extra)
        return env

    def child(self, code, **extra):
        return subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=self.env(**extra),
                              capture_output=True, text=True, timeout=120)

    def test_owners_remove_them_after_failures_and_a_failing_setupclass(self):
        code = (
            "import os, unittest\nfrom tmp_dirs import tmp_dir\n"
            "class A(unittest.TestCase):\n"
            "    def test_fails(self):\n"
            "        (tmp_dir(self, 'rfs-a-') / 'f').write_bytes(b'x')\n"
            "        self.fail('on purpose')\n"
            "    def test_raises(self):\n"
            "        tmp_dir(self, 'rfs-b-')\n"
            "        raise RuntimeError('on purpose')\n"
            "class B(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        cls.tmp = tmp_dir(cls, 'rfs-c-')\n"
            "        raise RuntimeError('fixture build failed')\n"
            "    def test_never(self):\n"
            "        pass\n"
            "s = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(c) for c in (A, B)])\n"
            "r = unittest.TextTestRunner(stream=open(os.devnull, 'w')).run(s)\n"
            "print(len(r.failures), len(r.errors), sorted(os.listdir(os.environ['RFS_TEST_TMPDIR'])))\n"
            "os._exit(0)\n"  # skip atexit: the cleanups alone must have removed them
        )
        r = self.child(code)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "1 2 []")

    def test_no_owner_is_removed_at_exit(self):
        r = self.child("from tmp_dirs import tmp_dir\n(tmp_dir(None) / 'f').write_text('x')\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(os.listdir(self.root), [])

    @unittest.skipIf(os.name == "nt", "SIGTERM cannot be handled on Windows")
    def test_sigterm_removes_them_and_still_ends_by_sigterm(self):
        code = (
            "import time\nfrom tmp_dirs import tmp_dir\nprint(tmp_dir(None), flush=True)\n"
            "while True:\n    try:\n        time.sleep(1)\n    except BaseException:\n        pass\n"
        )
        p = subprocess.Popen([sys.executable, "-c", code], cwd=str(ROOT), env=self.env(), stdout=subprocess.PIPE, text=True)
        try:
            self.assertTrue(os.path.isdir(p.stdout.readline().strip()))
            p.send_signal(signal.SIGTERM)
            self.assertEqual(p.wait(timeout=30), -signal.SIGTERM)
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            p.stdout.close()
        self.assertEqual(os.listdir(self.root), [])

    def test_keep_keeps_them_and_prints_where(self):
        r = self.child("from tmp_dirs import tmp_dir\n(tmp_dir(None, 'rfs-kept-') / 'f').write_text('x')\n", RFS_KEEP_TEST_TMP="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        left = os.listdir(self.root)
        self.assertEqual(len(left), 1)
        self.assertTrue(left[0].startswith("rfs-kept-"))
        self.assertIn(os.path.join(self.root, left[0]), r.stderr)

    def test_the_unit_and_contract_modules_leave_nothing_behind(self):
        r = subprocess.run([sys.executable, "-m", "unittest", "tests.test_unit", "tests.test_contract"], cwd=str(ROOT),
                           env=self.env(TMPDIR=self.root), capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stderr[-3000:])
        self.assertRegex(r.stderr, r"Ran \d{2,} tests")
        # node-compile-cache is Node's own compile cache: one fixed directory, reused by every run, not a leftover
        self.assertEqual([n for n in os.listdir(self.root) if n != "node-compile-cache"], [])

    def test_test_files_make_temporary_directories_only_through_tmp_dir(self):
        bare = re.compile(r"tempfile\.mkdtemp\(|tempfile\.TemporaryDirectory\(\)")
        for f in sorted(TESTS.glob("test_*.py")):
            if f.name == "test_tmp_dirs.py":
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(bare.search(line), f"{f.name}:{n}: use tmp_dirs.tmp_dir(owner, prefix)")


if __name__ == "__main__":
    unittest.main()
