# ADR 0002: Test temporary directories are always removed

- Status: accepted
- Date: 2026-11-19

## Context

The tests made their temporary directories with a bare `tempfile.mkdtemp`. The brand tests (`tests/test_unit.py`, class
`Brand`) never removed theirs, so every run of the fast suite left four `rfs-brand-*` directories in the OS temp directory.
The real-media classes in `tests/test_integration.py` removed theirs in `tearDownClass`. unittest does not call
`tearDownClass` when `setUpClass` fails, for example when a fixture render fails, so those runs also left their fixture
media behind. A shared machine had collected 60 `rfs-brand-*` directories. The scripts are not the cause: `analyze.py`
already removes its `.rfs-conform-*` work directory in a `finally`.

## Decision

- Test files make temporary directories only through `tests/tmp_dirs.py`'s `tmp_dir(owner, prefix)`. Each prefix
  starts with `rfs-`.
- With a TestCase class as `owner`, the directory is removed by `addClassCleanup`, which also runs when `setUpClass`
  fails. With a TestCase instance, it is removed by `addCleanup`, after the test whether it passed, failed or raised.
- Whatever is still there at interpreter exit is removed by `atexit`. On SIGTERM it is removed too, and the process then
  ends by SIGTERM. SIGKILL cannot be handled.
- A `tempfile.TemporaryDirectory` used as a context manager is fine; it takes a `rfs-` prefix.
- `RFS_TEST_TMPDIR=DIR` makes the directories under DIR. `RFS_KEEP_TEST_TMP=1` keeps them and prints their paths on
  stderr, for debugging only.

## Verified

`tests/test_tmp_dirs.py` checks:

- the directories are removed after a failing test, a raising test and a failing `setUpClass` (the cleanups alone, with
  `atexit` skipped);
- they are removed at exit when there is no owner;
- they are removed on SIGTERM, even while the code swallows every exception;
- `RFS_KEEP_TEST_TMP=1` keeps them and prints the paths;
- `tests.test_unit` and `tests.test_contract`, run whole with `TMPDIR` set to an empty directory, leave it empty. The one
  exception is Node's own shared `node-compile-cache`;
- no test file calls a bare `mkdtemp` or `TemporaryDirectory()`.

All but the last fail against a helper that does not remove its directories. One run of the fast suite left 4
directories before this change and 0 after.
