# Changelog

## 0.12.0 — 2026-10-30

_Automated release: version and notes from what was merged since the previous tag._

### Added

- conform a VFR or HDR source instead of only warning (--conform) (#10)


## 0.11.0 — 2026-10-30

_Automated release: version and notes from what was merged since the previous tag._

### Added

- captions from a transcription-skill transcript (--words) (#9)


## 0.10.2 — 2026-10-30

_Automated release: version and notes from what was merged since the previous tag._

### Fixed

- contract in the OS registry shape (#8)


## 0.10.1 — 2026-10-26

_Automated release: version and notes from what was merged since the previous tag._

### Fixed

- plugin installs on claude.ai -- installer moves from bin/ to cli/; listing name and links


## 0.10.0 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Added

- Pip -- a camera in a corner, synced from the audio


## 0.9.0 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Added

- --brand reads ffmpeg-skill's brand.json


## 0.8.1 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Fixed

- deliver.py crashed without --chapters (0.8.0)


## 0.8.0 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Added

- chapters -- cards in Titled, markers and description block on delivery


## 0.7.0 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Added

- --sparse for Titled (lower thirds and scene titles)


## 0.6.0 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Added

- --sparse draws only the captioned stretches of long footage


## 0.5.0 — 2026-10-24

_Automated release: version and notes from what was merged since the previous tag._

### Added

- the contract states each tool's --json result and dry-run shapes


## 0.4.0 — 2026-10-24

- **Karaoke captions:** `analyze.py --words` reads word timings from a local speech engine (whisper JSON with word timestamps); the `Karaoke` composition lights each word at its measured time. Without an SRT, cues are grouped from the words mechanically (pause / length rules), never reworded.
- **About twice as fast:** render.py uses all CPU cores by default (`--concurrency 100%`); 30 s of 1080p30 on 2 cores went from 170 s to 80 s.
- **Tested on Linux, macOS and Windows** in CI, including real renders of every composition, portrait output and the overlay layer.
- macOS: Homebrew's plain `ffmpeg` has no `drawtext`, so ffmpeg-skill's contact sheets fail on it; render.py now reports `look_error` with the fix (`brew install ffmpeg-full`) instead of dropping it silently.
- Clearer Remotion errors (the `Error:` line, not the JavaScript stack).
- Generated `references/scripts.md` (checked against the contract by a test), `references/gotchas.md`, `docs/design-decisions.md`, `AGENTS.md`, `.claude-plugin/plugin.json`, code of conduct.
- Evals: three more tasks (graphics layer for an editor, join + titles, karaoke from words); 9 / 9 passed.

## 0.3.0 — 2026-10-24

- **Machine-readable contract and MCP server:** `scripts/_contract.py` (`npx remotion-ffmpeg-skill contract --json`) describes every tool — role, what it writes, how it verifies, input schema generated from its argparse parser; `mcp/server.py` serves the same tools over stdio JSON-RPC with typed errors.
- **New compositions:** `Titled` (the user's lower thirds + a title at each measured scene), `Highlights` (ffmpeg-skill's ranked highlight ranges back to back with counter and title), `BeatMontage` (audio unbroken, picture cuts on the measured beat grid). `PeakPulse` can pulse on beats (`driver`).
- `analyze.py --beats` stores `{times, tempo_bpm, confidence, usable}`; `--highlights N [--target S]`.
- **Several inputs:** `analyze.py` / `pipeline.py` join clips with ffmpeg-skill `join.py` first; `timeline.clips` keeps where each one sits.
- **Strict options:** unknown option keys and wrong types are refused before rendering (they used to do nothing silently).
- Props files are named by content, so parallel renders in one project never overwrite each other's props.
- **Agent evals:** six natural-language tasks with fixtures and a grader (`evals/`); first run 6/6.
- Roadmap, security policy, contributing guide, dependabot, CodeQL.

## 0.2.0 — 2026-10-24

- **Vertical and square output:** `render.py` / `still.py` / `pipeline.py --aspect 9:16|1:1|4:5|16:9`, `--width`, `--fit blur|contain|cover` (blur by default when the shape changes). Captions size from the frame's short side and sit clear of Reels/TikTok UI on portrait frames. `pipeline.py --platform` renders in the aspect of ffmpeg-skill's delivery template, so a Reels delivery is never centre-cropped from a 16:9 render.
- **CJK captions without tofu:** Japanese / Chinese / Korean captions automatically get the font ffmpeg-skill's doctor finds on the machine, staged into the project and loaded before the first frame; `--font-file` picks any font. Japanese lines break between phrases (`word-break: auto-phrase`) with balanced lines.
- **Audio-only sources** now keep their audio (they rendered silent before).
- **`--overlay`:** the graphics alone as a transparent ProRes 4444 layer, composited over the untouched source with ffmpeg-skill `overlay.py`; `--keep-graphics` keeps the layer for an editing app.
- Sources are hard-linked (or copied once) into the project instead of symlinked: Remotion's file server refuses public/ symlinks that point outside the project.
- Demo GIF, release workflow (tag + GitHub Release + npm publish when `NPM_TOKEN` is set).

## 0.1.0 — 2026-10-24

First release.

- `analyze.py`: measure a source with ffmpeg-skill (probe, scenes, silence, audio peaks, optional beat grid) and carry SRT / WebVTT / JSON captions into a `timeline.json` (schema `remotion-ffmpeg-skill/timeline@1`), with warnings for VFR, HDR and rotated sources.
- Remotion project template with three timeline-driven compositions: `Captioned`, `Jumpcut` (silence-removed cuts with punch-in, captions re-timed), `PeakPulse` (motion on measured audio peaks and scene cuts).
- `init.py`, `still.py`, `render.py` (verifies frame count, fps, size and audio against the timeline, then writes a contact sheet with ffmpeg-skill `look.py`), `deliver.py` (ffmpeg-skill delivery templates + `check.py`), `pipeline.py`, `doctor.py`.
- `npx remotion-ffmpeg-skill` installer for Claude Code, Cursor and Codex.
