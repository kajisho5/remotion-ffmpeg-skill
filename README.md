# remotion-ffmpeg-skill

**ffmpeg-skill measures the footage. Remotion draws from those measurements. ffmpeg-skill checks and delivers the result.**

An [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) for Claude Code, Cursor and Codex that puts Remotion motion graphics on *real recordings* — and never guesses a number. Composition length, fps and frame size come from the probe; cuts come from measured silences; pulses hit on measured audio peaks; captions keep the timing of your SRT. Every render is verified frame-for-frame against its timeline and inspected with a contact sheet before it ships.

Built on [**ffmpeg-skill**](https://github.com/kajisho5/ffmpeg-skill). Unofficial — not affiliated with Remotion.

![Jumpcut: the silences ffmpeg-skill measured are gone, every other cut punches in, captions re-timed to the new cut](assets/demo-jumpcut.gif)

<sub>Fictional demo footage. Left to right in time: ffmpeg-skill measured two silences and a scene cut; Remotion played only the speech ranges with punch-in zooms and re-timed captions; render.py verified 201 of 201 frames.</sub>

## Why this and not just Remotion's own skills?

[Remotion's official Agent Skills](https://www.remotion.dev/docs/ai/skills) teach an agent to *write* good Remotion code. This skill closes the loop around it:

| | Remotion skills | remotion-ffmpeg-skill |
|---|---|---|
| Writes Remotion compositions | ✅ | ✅ (three ready-made, timeline-driven) |
| Knows the source's real duration / fps / size / silences / scene cuts / audio peaks | — | ✅ measured by ffmpeg-skill |
| Warns before drawing on VFR or HDR footage | — | ✅ |
| Verifies the render (exact frame count, fps, size, audio) | — | ✅ non-zero exit on mismatch |
| Looks at the result (contact sheet) | — | ✅ |
| Delivers for YouTube / Reels / TikTok / Shorts / X with loudness and compliance checks | — | ✅ ffmpeg-skill templates + `check.py` |

They work well together: install both if you write custom compositions.

## Install

```bash
npx ffmpeg-skill              # the measuring/delivery half (required)
npx remotion-ffmpeg-skill     # this skill, next to it in ~/.claude/skills
```

`--cursor`, `--codex`, `--all`, `--project` work for both. Requirements: Python 3.10+, Node.js 18+, FFmpeg (ffmpeg-skill's `doctor` tells you what's missing). Remotion's headless browser downloads itself on the first render.

## What you can ask for

- "Put animated captions from `talk.srt` on `talk.mp4` and make it a YouTube upload."
- "Cut the silences out of this recording, jump-cut style, and keep the subtitles in sync."
- "Make graphics that hit on the loud moments of `clip.mp4`, as a Reel."
- "Japanese captions, vertical, for TikTok." — renders 9:16 with a blurred fill, stages a CJK font automatically, breaks lines between phrases.

## Under the hood

```bash
S=~/.claude/skills/remotion-ffmpeg-skill/scripts

python3 $S/init.py ./motion --install                       # Remotion project (pinned versions)
python3 $S/analyze.py talk.mp4 --captions talk.srt          # -> talk.timeline.json (all measured)
python3 $S/still.py  --project ./motion --comp Jumpcut --timeline talk.timeline.json --at 2
python3 $S/render.py --project ./motion --comp Jumpcut --timeline talk.timeline.json -o jumpcut.mp4
python3 $S/deliver.py jumpcut.mp4 --platform youtube        # template + compliance table

# or all of it, each step verified before the next:
python3 $S/pipeline.py talk.mp4 --project ./motion --comp Jumpcut --captions talk.srt --platform youtube
```

Every script takes `--json`, `--dry-run`, `--overwrite`, `--timeout`, like ffmpeg-skill.

### MCP

```bash
claude mcp add remotion-ffmpeg-skill -- python3 ~/.claude/skills/remotion-ffmpeg-skill/mcp/server.py
```

Tool names and input schemas come from the machine-readable contract (`npx remotion-ffmpeg-skill contract --json`), generated from the scripts' own argument parsers.

### Compositions

| Id | Length | What it draws |
|---|---|---|
| `Captioned` | source duration | caption cards that spring in on each cue (text exactly as written) |
| `Jumpcut` | sum of measured speech ranges | silences removed, punch-in on every other cut, captions re-timed |
| `PeakPulse` | source duration | edge glow + zoom on measured audio peaks or beats, flash on scene cuts, progress bar |
| `Titled` | source duration | your lower thirds + a title card at each measured scene change |
| `Highlights` | sum of ranked highlights | ffmpeg-skill's audio-energy highlights back to back, counter, title |
| `BeatMontage` | source duration | audio unbroken, picture cuts on the measured beat grid |

**Any shape:** `--aspect 9:16 | 1:1 | 4:5 | 16:9` with `--fit blur | contain | cover`; `pipeline.py --platform reels` picks 9:16 from ffmpeg-skill's own template so nothing gets cropped on delivery.

<img src="assets/portrait-ja-still.png" width="270" alt="9:16 still with a Japanese caption, blurred fill behind the 16:9 source">

**Fonts:** Japanese / Chinese / Korean captions get the CJK font ffmpeg-skill finds on the machine, loaded before the first frame — no tofu. `--font-file` for your own.

**A layer for your editor:** `--overlay --keep-graphics` renders the graphics alone as transparent ProRes 4444 and composites it over the untouched source with ffmpeg-skill — keep the `.mov` for Premiere, Resolve or Final Cut.

Colours, font, caption size, zoom and pulse strength are options (`--options look.json`); the timeline format and every option are in [`references/timeline.md`](references/timeline.md). Add your own composition to the generated project and render it with `--comp YourId`.

### What render.py verifies

```text
jumpcut.mp4: 6.32 s, 1280x720, 30.0 fps, audio
  size      PASS  1280x720 (expected 1280x720)
  fps       PASS  30.0 (expected 30.0)
  frames    PASS  189 (expected 189)
  audio     PASS  present (expected present)
Look: jumpcut_sheet.png
```

Frame numbers are `Math.round(seconds × fps)` on both sides (TypeScript and Python), so the expected count is exact, not "close enough".

## Licence

This skill is MIT. **Remotion itself has its own licence**: free for individuals and for-profit organisations with up to 3 employees; larger companies need a [Remotion company licence](https://www.remotion.dev/license). Using this skill does not change that.

## Speed

Remotion renders in a headless browser. Measured on a 2-core Linux machine: a 30 s 1080p30 render takes about 170 s (≈ 5–6× the clip length). Check with `still.py` and `--fast` before a full render of long footage; more CPU cores help (`--concurrency`).

## Status

0.2.0. Tested on Linux (Node 22, Remotion 4.0.538, ffmpeg-skill 2.12.0); macOS and Windows not yet. Planned: agent evals, multi-clip sources, rendering only the captioned ranges for long footage.
