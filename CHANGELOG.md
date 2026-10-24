# Changelog

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
