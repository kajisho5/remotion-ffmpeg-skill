---
name: remotion-ffmpeg-skill
description: 'Make motion graphics on real footage with Remotion, driven by measurements from ffmpeg-skill: animated captions timed from an SRT/VTT file, automatic jump cuts that drop the silences ffmpeg-skill measured (with punch-in zooms and captions re-timed), and motion that hits on measured audio peaks and scene cuts. Every composition takes its length, fps and frame size from the probed source; every render is verified (frame count, fps, size, audio) and inspected with a contact sheet, then delivered through ffmpeg-skill templates (YouTube, Reels, TikTok, Shorts, X) and its compliance check. Use this skill when the user wants Remotion, React video, motion graphics, animated captions or titles over a video, jump cuts / silence removal with motion, audio-reactive or beat-synced graphics, or a programmatic video built from a real recording -- even when they do not say "Remotion". Needs Node.js and ffmpeg-skill; local, no API keys.'
---

# remotion-ffmpeg-skill

**ffmpeg-skill measures → Remotion draws → ffmpeg-skill checks and delivers.** Scripts live in `scripts/` next to this file; run them with `python3 <skill-dir>/scripts/<name>.py`. `--help` on a script is the full flag list; `references/timeline.md` is the timeline format and the options every composition takes.

This skill depends on [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (found next to this skill, in `~/.claude/skills/ffmpeg-skill`, or via `FFMPEG_SKILL_DIR`). It never runs a raw `ffmpeg`/`ffprobe` command itself: measuring, checking and delivering go through ffmpeg-skill's scripts, so their guarantees carry over.

Shared flags (every script): `--json` (one JSON object on stdout; prefer it), `--dry-run` (plan, write nothing), `--overwrite` (the one way to replace an existing output), `--timeout SECONDS`.

## Workflow (in this order)

1. **Project once.** No Remotion project yet: `init.py ./motion --install` (copies the template, runs `npm install`; Remotion's headless browser downloads on the first render). An existing project from this skill: reuse it.
2. **Measure.** `analyze.py SOURCE [--captions FILE.srt] [--beats] -o SOURCE.timeline.json`. Read the summary and the `warnings`: a VFR or HDR source must be fixed with ffmpeg-skill *before* drawing (`color.py --to-sdr`, a constant-frame-rate export) — Remotion renders SDR on a fixed frame grid. Never write or edit timeline numbers by hand; re-measure instead (`--threshold`, `--min-silence` for a quiet room).
3. **Preview stills.** `still.py --project ./motion --comp NAME --timeline TL --at 1.5 --at 6` and view the PNGs: caption placement, punch-in, colours. Cheap; do it before a full render.
4. **Render.** `render.py --project ./motion --comp NAME --timeline TL [--options look.json] -o OUT.mp4` (`--fast` = half-size preview, `--frames 0-89` = a range, `--codec prores -o master.mov` = a master). It verifies the output against the timeline (frame count, fps, size, audio) and exits non-zero on a mismatch.
   - **Shape:** draw in the shape it will be delivered in. `--aspect 9:16` for Reels / TikTok / Shorts (`1:1`, `4:5`, `16:9` too); `--fit blur` (default when the shape changes: contained over a blurred copy), `contain` (bars) or `cover` (crop — check the subject in the still first). Never render 16:9 and let a 9:16 template crop it: captions lose their edges. `pipeline.py --platform` picks the aspect from ffmpeg-skill's template for you.
   - **Fonts:** Japanese / Chinese / Korean captions get the CJK font ffmpeg-skill finds on the machine automatically (staged into the project, so no tofu); `--font-file F.ttf` uses a specific font; the report line `font:` says which was used, or that none was found.
   - **Editing-app layer:** `--overlay --keep-graphics` (Captioned / PeakPulse, source shape) draws the graphics alone as a transparent ProRes 4444 `.graphics.mov` and composites it over the untouched source with ffmpeg-skill `overlay.py`; hand the `.mov` to someone finishing in Premiere / Resolve / Final Cut. It is not faster than a normal render.
5. **Deliver.** `deliver.py OUT.mp4 --platform youtube|reels|tiktok|shorts|x|...` runs ffmpeg-skill's delivery template and its `check.py` table. Format rows are safe to fix; judgement rows (duration, aspect) change content — ask. Mention WARNs, don't chase them. No destination named: skip this step and say so.
6. **Look.** Not finished until the reply names the contact sheet render.py wrote (`Look: PATH`) and says what it shows. Mechanical (check and report): text is where it was asked, cues appear at their times, nothing is cut off by the frame. Judgement (say what you see, the user decides): text over a face, a jump that lands badly. No image view: `Look: PATH (pixels not inspected)` — never claim you looked.

Options files are checked before rendering: an unknown key or a wrong type is refused (`kind: input`) instead of silently doing nothing.

MCP: `mcp/server.py` exposes the same tools (schemas from `scripts/_contract.py`, `contract --json` prints them).

Everything in one go: `pipeline.py SOURCE --project ./motion --comp NAME [--captions F] [--platform P]` runs 2→4→5 with the same checks and stops at the first failed step.

## Request → script / composition

| Request | Run |
|---|---|
| "animated captions / subtitles on this video" | `analyze.py --captions` → `render.py --comp Captioned` |
| "cut the silences / jump cut / tighten this talk" (with motion) | `analyze.py` → `render.py --comp Jumpcut` (captions re-timed if given) |
| "graphics that react to the audio / hit on the beat / on cuts" | `analyze.py [--beats]` → `render.py --comp PeakPulse` (pulses on beats when the grid was measured) |
| "karaoke captions / words light up as they're spoken" | `analyze.py --words WORDS.json [--captions F.srt]` → `render.py --comp Karaoke` (word timings from a local speech engine, whisper JSON; without an SRT the cues are grouped from the words) |
| "lower thirds / name titles / chapter titles" | `render.py --comp Titled --options` with `lowerThirds` / `sceneTitles` — the text comes from the user; ask for it, never invent names |
| "highlight reel / best moments" | `analyze.py --highlights N [--target S]` → `render.py --comp Highlights` (audio-energy ranking: candidates, say so) |
| "cut to the beat / music montage" | `analyze.py --beats [--highlights N]` → `render.py --comp BeatMontage` (audio unbroken, picture cuts every `beatsPerCut` measured beats; scene cuts if no confident grid) |
| "for YouTube / Reels / TikTok ..." | `pipeline.py --platform` (renders in the template's aspect, then delivers and checks), or `render.py --aspect` + `deliver.py --platform` |
| "vertical / 9:16 / square" | `render.py --aspect 9:16` (or `1:1`, `4:5`) |
| "Japanese captions" / a specific font | nothing extra for CJK (auto font); `--font-file` for a chosen font |
| "give me the graphics as a separate layer" | `render.py --overlay --keep-graphics` |
| "change colour / font / caption size / zoom" | an `--options` JSON (`references/timeline.md`), re-render |
| several clips ("intro + talk + outro") | `analyze.py A.mp4 B.mov C.mp4` (or `pipeline.py` with several inputs): ffmpeg-skill join.py normalises and joins them, then everything is measured on the joined file |
| "preview" / "show me a frame" | `still.py` |
| a new kind of graphic | add a composition to `src/` of the project that reads `Props` from `src/timeline.ts`; render with `--comp YourId` (render.py then reports measured numbers without a built-in expectation) |
| plain cut / trim / resize / loudness with no graphics | not this skill: use ffmpeg-skill directly |
| something broke | `doctor.py [--project DIR]` |

## What this skill decides and what it does not

- **Decides (mechanical):** composition length, fps and size (from the probe); where cuts fall (from measured silences); when cues show (from the caption file); when pulses hit (from measured peaks); whether a render matches its timeline.
- **Does not decide:** names, titles and chapter names (lower thirds and scene titles are the user's text — ask), which words a caption says — cue text is drawn exactly as written, never shortened or paraphrased, even to "make it fit" (offer a smaller `captionSize` instead); what counts as a highlight; whether a look is good. Those belong to the user or the calling agent.
- **Never invents data.** No captions without a timed caption file from the user or a local speech-to-text engine; no beat grid that `--beats` did not measure.

## Rules that keep jobs from failing

- Remotion licence: free for individuals and for-profit organisations with up to 3 employees; larger companies need a Remotion company licence (https://www.remotion.dev/license). If the user is plainly a larger company, say so once.
- Keep the user's originals: sources are linked into `public/media/` of the project, never modified; outputs never overwrite an existing file without `--overwrite`.
- CJK captions: the auto font comes from ffmpeg-skill's font detection; when the report says no font was found, install one (Noto Sans CJK) or pass `--font-file` — tofu in the contact sheet is a failed job. Japanese lines break between phrases, not inside words.
- Speed (measured on a 2-core Linux machine, all cores — render.py's default): about 2.6× the clip length for 1080p30 (30 s took 80 s). Preview with `still.py` and `--fast` before a full render of long footage; tell the user the expected time before starting a long render. `--concurrency` above the core count is refused by Remotion.
- Remotion packages in a project must all be the same version; the template pins them. Don't mix in a different `remotion` version.
- A render that fails verification is a failure: report the failed rows from `--json`, don't ship it.
