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
| `references/scripts.md` is generated | it cannot drift from the parsers | `test_contract.Transport.test_generated_reference_is_current` |

The Japanese design memo with measurements is [`design.ja.md`](design.ja.md).
