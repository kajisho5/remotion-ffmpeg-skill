# Changelog

## 0.1.0 — 2026-10-24

First release.

- `analyze.py`: measure a source with ffmpeg-skill (probe, scenes, silence, audio peaks, optional beat grid) and carry SRT / WebVTT / JSON captions into a `timeline.json` (schema `remotion-ffmpeg-skill/timeline@1`), with warnings for VFR, HDR and rotated sources.
- Remotion project template with three timeline-driven compositions: `Captioned`, `Jumpcut` (silence-removed cuts with punch-in, captions re-timed), `PeakPulse` (motion on measured audio peaks and scene cuts).
- `init.py`, `still.py`, `render.py` (verifies frame count, fps, size and audio against the timeline, then writes a contact sheet with ffmpeg-skill `look.py`), `deliver.py` (ffmpeg-skill delivery templates + `check.py`), `pipeline.py`, `doctor.py`.
- `npx remotion-ffmpeg-skill` installer for Claude Code, Cursor and Codex.
