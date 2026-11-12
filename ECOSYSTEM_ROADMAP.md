# Roadmap — remotion-ffmpeg-skill

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **映像 (Visual)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR. This repository's own feature roadmap stays in [ROADMAP.md](ROADMAP.md); this file covers only its place in the ecosystem.

## Where it stands

v0.12.1. analyze, init, still, render, deliver, pipeline, doctor; compositions BeatMontage, Captioned, Highlights, Jumpcut, Karaoke, PeakPulse, Pip, Titled. 89 tests, CI on 3 OSes. Delegates heavily to ffmpeg-skill.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| 計測連動モーショングラフィックス(Remotion) | done |  |

## Wiring

Wired in the agent as a CONFIRM `video.measured_motion` run as `pipeline` (step 4, video-production-agent#108, pinned 0.12.1). Delegates to ffmpeg-skill probe, scenes, silence, sync, check, join, look, metadata, overlay, render, fit and color (`--conform`).

## Steps

- [x] **1. Contract in the OS schema shape** — `skill` object or skill_id, provides[], dependencies[] (depends_on is a map today)
  - Done when: OS schema validation passes
- [x] **2. Captions from a transcription-skill transcript** — `--words` input ([#9](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/9))
  - Done when: integration fixture
- [x] **3. Fix the source instead of warning** — VFR->CFR, HDR->SDR via ffmpeg-skill / color-grading ([#10](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/10))
  - Done when: no warn-only path
- [x] **4. (agent side) SkillSpec measured_motion -> pipeline** — CONFIRM ([video-production-agent#108](https://github.com/kajisho5/video-production-agent/pull/108), its ADR-093: `remotion.comp` + `remotion.project` → a CONFIRM `video.measured_motion` run as `pipeline` after the edits; pinned contract v0.12.1)
  - Done when: tracked in video-production-agent
- [x] **5. ffmpeg-skill 3.0.0** — declared range `>=2.0.0 <4.0.0`; CI also against 3.0.0 pinned ([#12](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/12))
- [ ] **6. Source-less runs** — `analyze --blank DURATION --size WxH --fps N [--music FILE]`: a timeline with no footage (the music, when given, is measured for beats and peaks as a source's audio is), so any composition can draw kinetic typography or a visualizer from nothing. Field review 2026-11-05 (Velisa ROADMAP, third round)
  - なぜ要るか：音楽だけ・文字だけの映像を、今の計測連動の仕組みのまま作れる
  - Done when: `pipeline --blank 15 --size 1080x1920 --music bgm.wav --comp PeakPulse` renders 15.0 s, 1080x1920, with the music
- [ ] **7. KineticType composition** — per-character and per-word reveals, mask wipes, tracking animation and scale pops, timed to the measured beat grid or to word timings (lyrics, a transcription-skill transcript); typed props, CJK per character. 参考：video-shotcraft（Apache-2.0、考え方のみ）
  - なぜ要るか：ビートや歌詞に合った文字演出を、計測した時刻で正確に打てる
  - Done when: on a 120 BPM fixture every word starts on a beat within one frame; a Japanese line animates per character with the CJK font staged
- [ ] **8. Visualizer compositions** — bars, spectrum, radial and waveform drawn from the audio per frame (`@remotion/media-utils` visualizeAudio; Remotion's licence applies), beat-reactive shapes from the measured grid, lyrics through Karaoke, and a `--loop` mode whose length is a whole number of bars, for loops in an edit
  - なぜ要るか：ループ素材・音楽PV・ポッドキャストの映像化を一つの部品で賄える
  - Done when: a fixture's loop render's last and first frames pass qc-skill's loop seam check; bars react to a test tone at the right frame
- [ ] **9. Three.js scenes** — a `ThreeScene` composition on `@remotion/three` (MIT; Remotion's licence applies) driven by the frame and a seed, with the GL backend Remotion renders with reported by doctor (`angle` / `swangle`); same frame, same pixels on one machine
  - なぜ要るか：ビート連動の3Dタイポやパーティクルを、計測データと同じタイムラインで描ける
  - Done when: two renders of a fixture have the same framemd5 on the CI machine; doctor names the backend
- [x] **10. Emphasis captions (YouTube style)** — captions where chosen words (given by the caller, or the transcript's numbers and nouns when asked) pop, change colour or get a box, plus speech-bubble and comment-style cards; the words are the caption's own, never rewritten ([#18](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/18): `Emphasis` composition, `analyze.py --emphasis` / `--emphasis-auto numbers,names`; "nouns" is capitalised or katakana names, as no part-of-speech model is shipped)
  - なぜ要るか：YouTuber 風の強調テロップと吹き出しを、字幕の時刻から自動で付けられる
  - Done when: a fixture with three emphasised words shows each at its word time; a word not in the cue is refused
- [ ] **11. Style presets and layer output** — `--style swiss|minimal|neon|glitch|wafu|corporate` as an options bundle (a brand kit wins key by key), and `--layers` writing each graphic group as its own transparent ProRes 4444 with a manifest (times, position) beside the composite
  - なぜ要るか：一言でトーンを決め、After Effects や NLE で組み直せるレイヤー素材も同時に出せる
  - Done when: each style renders a still in CI; `--layers` files composite back to the full render within a stated PSNR

## Boundaries

Pip, Titled, Captioned overlap ffmpeg-skill B-roll, motion-graphics titles, subtitle burn-in; this skill owns only the measurement-driven Remotion compositions.

Terms of use: Remotion itself is free for individuals and for companies with up to 3 employees; larger companies need a Remotion company licence (README, "Licence"). That is a condition of using Remotion, separate from this skill's MIT licence, and applies to every render the agent plans through this skill.

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (3.x, 42 tools, contract_version 2.0; treated as complete, proposals go to Velisa's ROADMAP). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
