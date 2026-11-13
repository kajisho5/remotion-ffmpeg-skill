# Design decisions

Behaviours that can look like bugs but are deliberate. Each names the reason and the test that pins it.
Report one as a defect only if its reason no longer holds.

| Behaviour | Why | Pinned by |
|---|---|---|
| No script runs `ffmpeg` / `ffprobe` itself; everything goes through ffmpeg-skill | one place for FFmpeg guarantees (originals untouched, measured plans, typed errors) | `TOOL_META[*].ffmpeg_skill`; code review |
| A render that does not match its timeline exits non-zero even though a file was written | an unverified file is not a deliverable; the agent must report the failed rows | `test_unit.Verify` |
| Frame counts use round-half-up in Python | the TypeScript compositions use `Math.round`; both must agree to the frame | `test_unit.Frames.test_round_half_up_like_javascript`, `TemplateParity` |
| Caption, title and lower-third text is never generated or shortened | words belong to the user; the skill only places them | `test_unit.Captions.test_text_is_never_rewritten` and the agent task `lower-third-asks-for-text` in `evals/tasks.json` |
| `--overlay` refuses Jumpcut / Highlights / BeatMontage | their cuts move the picture itself; a transparent layer cannot express that | `test_integration.Analyze.test_overlay_refuses_what_it_cannot_do` |
| `--overlay` is kept although it is not faster | it produces a ProRes 4444 graphics layer for editing apps | `references/gotchas.md` |
| Sources are hard-linked or copied, never symlinked | Remotion's server 404s on outside symlinks | `references/gotchas.md` |
| Unknown option keys are errors | a typo would otherwise silently do nothing in the browser | `test_unit.Options` |
| Highlights are stored in source order, not rank order | a reel reads chronologically; the ranking is ffmpeg-skill's proposal, not a verdict | `analyze.py` |
| BeatMontage cuts on scene changes when no usable beat grid exists | never invent beats | `BeatMontage.tsx` doc comment |
| Without `--width`, a changed aspect keeps the source's short side | no upscaling (720p → 720×1280) | `test_unit.OutputFrame` |
| `--sparse` falls back to the full-length layer instead of failing | the picture is the same either way, only slower; a missing `--place` or a source whose first picture is not at 0 would otherwise misplace stretches. `sparse.reason` says why | `test_integration.Analyze.test_sparse_plans_placements_or_says_why_not` |
| Karaoke's clock is nudged by a microsecond | a word boundary exactly on a frame (5.2 + 21/30 vs 5.9) must resolve the same way in the full and the packed (`--sparse`) timeline | `test_integration.Analyze.test_real_sparse_matches_the_full_layer` |
| `--words` refuses a transcription-skill transcript of any schema other than `transcription-skill/transcript/0.1`, or one that breaks that contract | an unknown version's fields may mean something else; a caption timeline built on a guess would put words at the wrong times | `test_unit.Transcript.test_unknown_versions_are_refused`, `test_contract_violations_are_refused`, `test_integration.Analyze.test_transcript_refused_when_it_cannot_be_trusted` |
| A transcript segment without word timings becomes one plain cue on the segment's own times; word times are never interpolated or split | the transcript only measured the segment; spreading its words over it would invent timings (transcription-skill: "never invents data") | `test_unit.Transcript.test_segment_without_word_timings_is_one_plain_cue`, `test_times_are_never_invented` |
| Transcript cues never span two segments | the space between segments is not recorded in the transcript, and the engine's segment boundary is a measured pause | `test_integration.Analyze.test_transcript_drives_the_caption_timeline` |
| A transcript whose duration differs from the source by over 0.5 s is refused; a different fingerprint only warns | a different length means a different file; the same length with other bytes is usually a re-mux or the extracted audio, whose times still hold | `test_integration.Analyze.test_transcript_refused_when_it_cannot_be_trusted` |
| A VFR or HDR / BT.2020 source (and a `--pip` camera) is refused unless `--conform` is given; there is no warn-and-continue path | conforming re-encodes the whole source (time, disk) and HDR → SDR tone-mapping changes the look, a judgement the user makes (ffmpeg-skill itself keeps HDR unless asked); drawing on it unconformed drifts (VFR) or washes out (HDR). The refusal names the flag, so the agent asks once and re-runs | `test_unit.Conform`, `test_integration.Conform.test_refused_without_conform` |
| `--conform` draws on a copy, `<name>_conformed.mp4`, made by ffmpeg-skill `fit.py --fps` then `color.py --to-sdr`, and re-measures it: not CFR at the asked rate, not BT.709, or a different length is `kind: failed` | the original is never modified; the copy must measure as asked before anything is drawn on it; `conform` in the timeline records the original's fingerprint and every step | `test_integration.Conform` (VFR, PQ, HLG, HLG + VFR, `--pip` camera) |
| The CFR rate is the stream's base rate (`r_frame_rate`), not its average | the base rate is the grid the frames sit on, so none is dropped (gaps repeat a frame); a phone clip's average (29.85) is no frame grid. Above 120 (a timebase, as screen recorders write) the average is used; `--conform-fps` overrides | `test_unit.Conform.test_rate_keeps_every_frame` |
| `--emphasis` refuses a word that is not a whole, timed word of its caption cue (or of the cue showing at `at`), and needs `--words` | the caption's words are the user's: emphasis only marks them, so a word that is not there is a mistake to report, not text to add; a part of a word (`講` of `講演`) or a cue without word timings has no measured time, and a guessed one would make the pop miss the speech | `test_unit.EmphasisWords.test_a_word_not_in_the_cue_is_refused`, `test_integration.Analyze.test_emphasis_refuses_a_word_not_in_the_cue` |
| An emphasised word shows plain until its measured start and stays emphasised to the end of its cue; its text is the caption's own slice (case, trailing punctuation outside) | the viewer sees it light up when it is said and can still read it after; matching ignores case, so the caller's spelling never replaces the caption's | `test_unit.EmphasisWords.test_three_words_at_their_word_times`, `test_integration.Analyze.test_real_emphasis_shows_each_word_at_its_time` |
| `--emphasis-auto names` means capitalised mid-sentence words and katakana words, not all nouns | finding nouns needs a part-of-speech model this skill does not ship; the heuristic is stated, opt-in, and only ever marks the caption's own words | `test_unit.EmphasisWords.test_auto_numbers_and_names_come_from_the_captions` |
| `render` and `still` are `bit_exact` only on one machine and toolchain; `analyze` and `pipeline` are `content_equivalent` | measured: every composition rendered twice gave identical bytes, also with `--concurrency 1`, ProRes and `--overlay`; but `timeline.json` records absolute paths, and other OSes, GPUs and Chromium builds were not compared ([ADR 0001](adr/0001-render-determinism.md)) | `test_integration.Determinism`, `test_contract.Repeatability` |
| `references/scripts.md` is generated | it cannot drift from the parsers | `test_contract.Transport.test_generated_reference_is_current` |
| ffmpeg-skill `>=2.0.0 <4.0.0` (3.x accepted) | ffmpeg-skill 3.0.0 removed Python 3.9 and FFmpeg 5.x, changed `cut.py`'s defaults and `contract_version` (2.0, for `cut.py`'s keys). This skill does not call `cut.py`, every flag it passes is still there (3.x promises none is removed), and CI already ran Python 3.12 with FFmpeg ≥ 6.1 | CI runs ffmpeg-skill main on every OS and 3.0.0, pinned by commit, on Linux; `test_contract` checks the range |


## Title and caption boundaries

Settled by the [Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156) (O9, O11; Velisa
`docs/ecosystem/DECISION_LOG.md` D20, D22). A caller choosing a skill for moving text reads this rule. No contract change.

- **Titles (O9).** `Titled`'s lower thirds and scene titles stay inside this skill's compositions. They are not offered as
  a separate title product. Titles burned into a programme are motion-graphics-skill's (`タイトル・テロップ`); title and
  stinger material files are hyperframes-skill's (`テロップ・スティンガー・ループ素材`).
- **Captions (O11).** Caption effects timed to words are this skill's (`語の時刻に合わせた字幕演出`): `Captioned` with
  `--words`, `Karaoke`, `Emphasis`. Animated captions made from subtitle cues alone (fade / pop / slide, karaoke without
  word timings) are subtitle-skill's (`動く字幕(字幕キュー由来)`), which passes ffmpeg-skill `caption --animate` /
  `--karaoke` through.

The Japanese design memo with measurements is [`design.ja.md`](design.ja.md).
