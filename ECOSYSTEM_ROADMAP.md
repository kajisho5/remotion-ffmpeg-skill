# Roadmap — remotion-ffmpeg-skill

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **映像 (Visual)**, status `active`.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR. This repository's own feature roadmap stays in [ROADMAP.md](ROADMAP.md); this file covers only its place in the ecosystem.

## Where it stands

v0.13.0. analyze, init, still, render, deliver, pipeline, doctor; compositions BeatMontage, Captioned, Emphasis (step 10), Highlights, Jumpcut, Karaoke, PeakPulse, Pip, Titled. CI on 3 OSes. Determinism is stated per tool in the contract (step 13: `render` / `still` `bit_exact` on one machine and toolchain). Delegates heavily to ffmpeg-skill.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| 計測連動モーショングラフィックス(Remotion) | done | titles (`Titled`) stay inside this skill's own compositions; burned-in titles are motion-graphics-skill's and title material files hyperframes-skill's |
| 語の時刻に合わせた字幕演出 | done | added by the [Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156) (O11): `Captioned` with `--words`, `Karaoke`, `Emphasis`. Animated captions made from subtitle cues alone are subtitle-skill's |
| オーディオビジュアライザー | partly | added by the same decisions (O17): `PeakPulse` and `BeatMontage` from measured peaks and beats ship; bars / spectrum / radial are step 8 |

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
- [x] **6. Source-less runs** — `analyze --blank DURATION --size WxH --fps N [--music FILE]`: a timeline with no footage (the music, when given, is measured for beats and peaks as a source's audio is), so any composition can draw kinetic typography or a visualizer from nothing. Field review 2026-11-05 (Velisa ROADMAP, third round)
  - なぜ要るか：音楽だけ・文字だけの映像を、今の計測連動の仕組みのまま作れる
  - Done when: `pipeline --blank 15 --size 1080x1920 --music bgm.wav --comp PeakPulse` renders 15.0 s, 1080x1920, with the music
  - Done ([#34](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/34)): `analyze.py` / `pipeline.py --blank SECONDS [--size WxH] [--fps N] [--music FILE]`; the music is measured with ffmpeg-skill probe / scenes (peaks, `--beats`) / silence (3.2.0 or later for audio-only files), cut at the blank's end; the picture is the new `background` option. Measured: the Done-when command rendered 450 frames (15.0 s at 30 fps), 1080x1920, with the music (`test_integration.Blank`). Contract additive. [ADR 0006](docs/adr/0006-source-less-runs.md)
- [x] **7. KineticType composition** — per-character and per-word reveals, mask wipes, tracking animation and scale pops, timed to the measured beat grid or to word timings (lyrics, a transcription-skill transcript); typed props, CJK per character. 参考：video-shotcraft（Apache-2.0、考え方のみ）
  - なぜ要るか：ビートや歌詞に合った文字演出を、計測した時刻で正確に打てる
  - Done when: on a 120 BPM fixture every word starts on a beat within one frame; a Japanese line animates per character with the CJK font staged
  - Done ([#35](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/35)): `analyze.py --kinetic words|beats|auto [--kinetic-step N]` writes the schedule (each word, or CJK character, at its measured word time or on the next measured beat; refused without a measurement), `KineticType` draws it (`kineticStyle` pop / wipe / tracking / rise, `kineticReveal` char / unit). Measured: on a 120 BPM fixture all 11 units start on a beat within one frame, and in the pixels each English word and two Japanese characters (CJK font staged) enter exactly on their start frame (`test_integration.KineticType`). Contract additive. [ADR 0007](docs/adr/0007-kinetic-type.md)
  - Scope after the [Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156) (O17): this skill keeps the measured versions only (beat grid, lyric or transcript word timings). Kinetic typography with no measured timing, from a JSON request alone, is hyperframes-skill's (its step 7), not built twice here
- [x] **8. Visualizer compositions** — bars, spectrum, radial and waveform drawn from the audio per frame (`@remotion/media-utils` visualizeAudio; Remotion's licence applies), beat-reactive shapes from the measured grid, lyrics through Karaoke, and a `--loop` mode whose length is a whole number of bars, for loops in an edit
  - なぜ要るか：ループ素材・音楽PV・ポッドキャストの映像化を一つの部品で賄える
  - Done when: a fixture's loop render's last and first frames pass qc-skill's loop seam check; bars react to a test tone at the right frame
  - Done ([#36](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/36)): `Visualizer` (`@remotion/media-utils` 4.0.540, pinned with Remotion; Remotion's licence applies): bars / spectrum / radial / waveform from the audio at each frame (no cross-frame smoothing), a ring on every measured beat, caption cues as Karaoke draws them; `loopBars` makes a loop of whole measured bars whose seam is halfway between two beats. Measured: on a test tone starting at 1.000 s the bars are flat on frame 29 and up on frame 30; the 120 BPM fixture's 3-bar loop passes qc-skill `video.loop_seam` at `max_seam_ratio` 1.3 (ratio 0.889; one frame short: 3.1, FAIL). CI checks out qc-skill for it. Contract additive. [ADR 0008](docs/adr/0008-visualizer.md)
  - Owner confirmed by the [Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156) (O17): `オーディオビジュアライザー` is this skill's; blender-skill's audio-driven step is deferred to this one
- [x] **9. Three.js scenes** — a `ThreeScene` composition on `@remotion/three` (MIT; Remotion's licence applies) driven by the frame and a seed, with the GL backend Remotion renders with reported by doctor (`angle` / `swangle`); same frame, same pixels on one machine
  - なぜ要るか：ビート連動の3Dタイポやパーティクルを、計測データと同じタイムラインで描ける
  - Done when: two renders of a fixture have the same framemd5 on the CI machine; doctor names the backend
  - Done ([#37](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/37)): `ThreeScene` (`@remotion/three` 4.0.540, `three` 0.186.1, `@react-three/fiber` 9.8.2, pinned; Remotion's licence applies): seeded particles round a shape that hits on the measured beats, a function of the frame and `seed` only. render.py / still.py `--gl` (ThreeScene default `swangle`: `angle` has no WebGL without a GPU in Remotion 4); `doctor.py --project` reports the `gl backend`. Measured: two renders (`--concurrency 1` for one) have the same framemd5 and sha256; another seed differs (`test_integration.ThreeScene`, every CI OS). Contract additive. [ADR 0009](docs/adr/0009-three-scene.md)
- [x] **10. Emphasis captions (YouTube style)** — captions where chosen words (given by the caller, or the transcript's numbers and nouns when asked) pop, change colour or get a box, plus speech-bubble and comment-style cards; the words are the caption's own, never rewritten ([#18](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/18): `Emphasis` composition, `analyze.py --emphasis` / `--emphasis-auto numbers,names`; "nouns" is capitalised or katakana names, as no part-of-speech model is shipped)
  - なぜ要るか：YouTuber 風の強調テロップと吹き出しを、字幕の時刻から自動で付けられる
  - Done when: a fixture with three emphasised words shows each at its word time; a word not in the cue is refused
- [x] **11. Style presets and layer output** — `--style swiss|minimal|neon|glitch|wafu|corporate` as an options bundle (a brand kit wins key by key), and `--layers` writing each graphic group as its own transparent ProRes 4444 with a manifest (times, position) beside the composite
  - なぜ要るか：一言でトーンを決め、After Effects や NLE で組み直せるレイヤー素材も同時に出せる
  - Done when: each style renders a still in CI; `--layers` files composite back to the full render within a stated PSNR
  - Done ([#38](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/38)): `--style` (render / still / pipeline) is an options bundle; `--brand` wins over it key by key, `--options` over both; new `captionBox` option. `render.py --layers` (Captioned, Karaoke, Titled, Emphasis, KineticType) writes one transparent full-frame ProRes 4444 per graphic group and `<output>.layers.json` (`layers@1`: base, order, position, times). Measured: each style renders a still and all six differ; Emphasis's three layers stacked over the background match the composite at >= 53.5 dB on every frame (stated bound 45 dB) (`test_integration.StylesAndLayers`). Contract additive. [ADR 0010](docs/adr/0010-styles-and-layers.md)
- [x] **12. Record the title and caption boundaries** — write down, in SKILL.md and docs/design-decisions.md, what the [Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156) settled: `Titled`'s lower thirds and scene titles stay inside this skill's compositions and are not offered as a separate title product (O9: burned-in titles are motion-graphics-skill's, title and stinger material files hyperframes-skill's); caption effects timed to words (`Captioned --words`, `Karaoke`, `Emphasis`) are this skill's, while animated captions made from subtitle cues alone (fade / pop / slide, karaoke without word timings) are subtitle-skill's (O11). No contract change
  - Why: a caller choosing between subtitle-skill, motion-graphics-skill and this skill for moving text reads one rule（なぜ要るか：動く文字をどのスキルで作るかを一か所に書く）
  - Done when: the decision is in docs/design-decisions.md with the decision linked, and SKILL.md's composition table points to it
  - Done ([#20](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/20)): docs/design-decisions.md "Title and caption boundaries" records O9 and O11 with the Velisa decision linked; SKILL.md's composition table points to it and routes animated captions from subtitle cues alone to subtitle-skill. No contract change
- [x] **13. State the determinism guarantee** — the contract, SKILL.md and docs/design-decisions.md say nothing today about `deterministic` or `idempotency_hint` for `render`, `still` and `pipeline`. Measure it, then state it: render each composition twice on one machine and compare (framemd5 of video, md5 of audio), record what makes runs differ (Chromium version, GL backend, fonts staged, `--concurrency`, the encoder), and write the result into the contract as the sibling skills do (`deterministic`, `idempotency_hint: bit_exact | content_equivalent`) with the conditions in an ADR. A composition that is not reproducible is named, not hidden behind a skill-wide claim
  - Why: the agent and qc-skill can only rely on a re-render matching when the guarantee is written down（なぜ要るか：再レンダーで同じ結果になるかを契約で約束し、検証できるようにする）
  - Done when: `contract --json` carries the fields for every tool; a CI test renders two compositions twice and checks the stated level; the ADR lists the conditions
  - Done ([#21](https://github.com/kajisho5/remotion-ffmpeg-skill/pull/21)): every tool carries `deterministic` and `idempotency_hint` (`render`, `still`, `deliver` `bit_exact`; `analyze`, `init`, `pipeline` `content_equivalent`; `doctor` `environment_dependent`) and the top-level `determinism` key lists the conditions, additively (`contract_version` stays 1.0). Measured: 92 renders, 4 pipeline runs and 72 stills on one machine, all byte-identical per configuration, `--concurrency` included; another Chromium build, GL backend or font changes the bytes. Cross-OS and GPU are unverified. [ADR 0001](docs/adr/0001-render-determinism.md); `test_integration.Determinism` runs on every CI OS. No composition is not reproducible

## Boundaries

Under the [Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156): titles stay inside this skill's compositions (O9); caption effects timed to words are this skill's, animated captions from subtitle cues are subtitle-skill's (O11); the audio visualizer and the beat- or lyric-measured kinetic type are this skill's, kinetic typography from nothing is hyperframes-skill's, and blender-skill stays 3D only (O17). `Pip` overlaps motion-graphics-skill's PiP (`ロゴ・PiP・クロマキー合成`, O10); this skill keeps only the version whose sync offset is measured.

Terms of use: Remotion itself is free for individuals and for companies with up to 3 employees; larger companies need a Remotion company licence (README, "Licence"). That is a condition of using Remotion, separate from this skill's MIT licence, and applies to every render the agent plans through this skill.

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (3.x, 42 tools, contract_version 2.0; treated as complete, proposals go to Velisa's ROADMAP). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
