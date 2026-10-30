# Roadmap — remotion-ffmpeg-skill

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **映像 (Visual)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR. This repository's own feature roadmap stays in [ROADMAP.md](ROADMAP.md); this file covers only its place in the ecosystem.

## Where it stands

v0.10.1. analyze, init, still, render, deliver, pipeline, doctor; compositions BeatMontage, Captioned, Highlights, Jumpcut, Karaoke, PeakPulse, Pip, Titled. 89 tests, CI on 3 OSes. Delegates heavily to ffmpeg-skill.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| 計測連動モーショングラフィックス(Remotion) | done |  |

## Wiring

Not reachable from the agent. Delegates to ffmpeg-skill probe, scenes, silence, sync, check, join, look, metadata, overlay, render.

## Steps

- [x] **1. Contract in the OS schema shape** — `skill` object or skill_id, provides[], dependencies[] (depends_on is a map today)
  - Done when: OS schema validation passes
- [x] **2. Captions from a transcription-skill transcript** — `--words` input ([#9](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/9))
  - Done when: integration fixture
- [ ] **3. Fix the source instead of warning** — VFR->CFR, HDR->SDR via ffmpeg-skill / color-grading
  - Done when: no warn-only path
- [ ] **4. (agent side) SkillSpec measured_motion -> pipeline** — CONFIRM
  - Done when: tracked in video-production-agent

## Boundaries

Pip, Titled, Captioned overlap ffmpeg-skill B-roll, motion-graphics titles, subtitle burn-in; this skill owns only the measurement-driven Remotion compositions.

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (42 tools, treated as complete). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
