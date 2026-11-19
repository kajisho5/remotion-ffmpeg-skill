"""Temporary directories of the tests, always removed again (docs/adr/0002-test-temporary-directories.md).

`tmp_dir(owner, prefix)` makes a directory with `tempfile.mkdtemp` and removes it whatever happens to the test:

- `owner` a TestCase class (in `setUpClass`): `addClassCleanup`, which also runs when `setUpClass` itself fails
  (where `tearDownClass` is never called);
- `owner` a TestCase instance (in `setUp` or a test): `addCleanup`, after that test whether it passed, failed or raised;
- whatever is still there at interpreter exit (`atexit`) or on SIGTERM (a CI cancel) is removed then. SIGKILL cannot be.

RFS_TEST_TMPDIR=DIR makes them under DIR instead of the OS temp directory. RFS_KEEP_TEST_TMP=1 keeps them and prints
their paths on stderr, for debugging.
"""
from __future__ import annotations

import atexit
import os
import shutil
import signal
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Set

KEEP = os.environ.get("RFS_KEEP_TEST_TMP") == "1"
_LIVE: Set[str] = set()
_SIGTERM_SET = False


def _remove(path: str) -> None:
    if KEEP:
        return
    shutil.rmtree(path, ignore_errors=True)
    if not os.path.exists(path):
        _LIVE.discard(path)


@atexit.register
def remove_all() -> None:
    """Remove every directory tmp_dir made that is still there (with RFS_KEEP_TEST_TMP=1: list them)."""
    if KEEP:
        for path in sorted(_LIVE):
            print(f"kept test temp dir: {path}", file=sys.stderr)
        return
    for path in sorted(_LIVE):
        _remove(path)


def _on_sigterm(signum: int, _frame: Any) -> None:
    # remove first, then end the way SIGTERM would have: a SystemExit raised here could be caught by the code under test
    remove_all()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)


def _catch_sigterm() -> None:
    global _SIGTERM_SET
    if _SIGTERM_SET or threading.current_thread() is not threading.main_thread():
        return
    _SIGTERM_SET = True
    try:
        if signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, None):
            signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError, AttributeError):  # no SIGTERM handler on this platform / thread
        pass


def tmp_dir(owner: Any, prefix: str = "rfs-") -> Path:
    """A new temporary directory, removed when `owner` (a TestCase class or instance) is cleaned up, or at exit."""
    path = tempfile.mkdtemp(prefix=prefix, dir=os.environ.get("RFS_TEST_TMPDIR") or None)
    _LIVE.add(path)
    _catch_sigterm()
    if isinstance(owner, type):
        owner.addClassCleanup(_remove, path)
    elif owner is not None:
        owner.addCleanup(_remove, path)
    return Path(path)
