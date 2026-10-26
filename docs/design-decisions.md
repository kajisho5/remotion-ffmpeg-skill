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
| `references/scripts.md` is generated | it cannot drift from the parsers | `test_contract.Transport.test_generated_reference_is_current` |

The Japanese design memo with measurements is [`design.ja.md`](design.ja.md).
