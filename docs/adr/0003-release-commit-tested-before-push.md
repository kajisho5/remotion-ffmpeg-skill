# 0003. The release job tests its commit before pushing it

2026-11-19. The ecosystem rule is Velisa ADR-023 (decision D37).

## Context

The automatic release commit (`release: vX.Y.Z [skip ci]`) is pushed with the default token, so no workflow runs on it on main. On 2026-11-19 two skills' mains broke this way (sound-design-skill, hyperframes-skill).

## Decision

The automatic bump commits locally. The step "Test the release commit before pushing it" runs `python3 -m unittest discover -s tests` (ci.yml's unit command, which skips what needs FFmpeg or a render) and `python3 contract/generate.py --check` on that commit. Only then does "Push the release commit" push. A failure pushes nothing. `tests/test_release.py` keeps the step between the commit and every push.

The release rule does not change. Unlabelled changes and docs / ci / chore-only changes already release nothing here (`.github/scripts/resolve_version.py`), which covers Velisa ADR-023.

## Consequences

A release that fails the tests is not made; a later push to main retries. A version bumped by hand is not committed by the job and is tagged as before.
