# Contributing

Thanks for helping. A few rules keep this skill trustworthy for agents:

1. **Measure, don't guess.** Every number a composition uses comes from the timeline (ffmpeg-skill measurements) or from the user's options. No hard-coded durations, sizes or invented text.
2. **No raw ffmpeg here.** Measuring, compositing, checking and delivering go through ffmpeg-skill's scripts (`ffskill()` in `scripts/_common.py`). If ffmpeg-skill lacks something, add it there.
3. **Python and TypeScript agree to the frame.** A composition's length rule lives in `src/timeline.ts` *and* `expected_frames()` in `scripts/_common.py`; frames are `Math.round(seconds * fps)` on both sides.
4. **A new composition** needs: the component, its `<Composition>` with `calculateMetadata`, its id in `BUILTIN_COMPOSITIONS`, its length rule in `expected_frames()`, a row in `references/timeline.md`, and a render in `tests/test_integration.py`.
5. **A new option** goes into `Options` / `DEFAULT_OPTIONS` (TypeScript) and `_OPTION_TYPES` (Python); a test checks they match.
6. **A new script** needs `build_parser()`, an entry in `TOOL_META` (`scripts/_contract.py`) and the shared flags (`--json`, `--dry-run`, `--overwrite`, `--timeout`).

## Running the tests

```bash
export FFMPEG_SKILL_DIR=/path/to/ffmpeg-skill
python3 -m unittest discover -s tests                 # fast: no renders
python3 scripts/init.py /tmp/rfs-proj --install
RFS_PROJECT=/tmp/rfs-proj python3 -m unittest discover -s tests   # also real renders (slow)
cd templates/remotion-project && npm install && npx tsc --noEmit
```

Test media is generated (lavfi test patterns and tones). Please keep sample text fictional: no real people, venues or projects.

## Releasing

Releases are cut on a push to main:

- **Automatically** when the current version is already tagged: label the PR `feature`/`enhancement`/`minor` (→ minor) or `fix`/`bug`/`patch` (→ patch), or, for a commit pushed straight to main, start its subject with `feat:` or `fix:`. The release job bumps `package.json` and `.claude-plugin/plugin.json`, writes the CHANGELOG section from those titles, tags, publishes the GitHub Release and npm. Changes with none of these (docs, ci, chore, unprefixed commits) release nothing. A `major` label or `BREAKING` in a subject is refused: bump that by hand.
- **By hand**: bump `version` in both files and add a `## X.Y.Z` section to `CHANGELOG.md` in the same change; that version is released as written.
