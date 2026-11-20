# 0005. Test classes that make media in setUpClass skip without FFmpeg

2026-11-20. Amends ADR 0003.

## Context

The release run for #29 (merge 5ff13d6) stopped at "Test the release commit before pushing it". `test_integration.NtscRate.setUpClass` ran `ffmpeg`, which the release job does not install, and raised `FileNotFoundError`. So 0.14.3 was not released.

The class was new in #29. The release step was new in #26 (ADR 0003), after 0.14.2. Per ADR 0003 the step runs ci.yml's unit command and relies on the tests' own skips for what needs FFmpeg. Every other class that makes media in `setUpClass` (`Analyze`, `Conform`, `Determinism`) carries `@unittest.skipUnless(HAVE, ...)`. `NtscRate` did not. Its one per-test skip (`PROJECT`) is read only after `setUpClass` has already failed.

## Decision

`NtscRate` carries the same class-level guard, `@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")`. ci.yml installs FFmpeg and ffmpeg-skill on every OS, so CI still runs the class. The release step is unchanged.

`tests/test_release.py` checks that every class in `tests/test_integration.py` with a `setUpClass` has a class-level `skipUnless` on `HAVE`. A new media class without the guard then fails the unit tests on the pull request, not the release.

## Consequences

The release job, which has no FFmpeg, skips the class, as it skips the other media classes. The contract is unchanged.
