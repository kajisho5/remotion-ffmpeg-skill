# timeline.json and composition options

`analyze.py` writes one `timeline.json` per source. The Remotion compositions receive it as
props (`{ "timeline": ..., "options": ..., "frame": ..., "font": ..., "overlay": ... }`, written by `render.py` / `still.py` to
`<project>/.rfs/props-<comp>.json`). The TypeScript type is `Timeline` in
`templates/remotion-project/src/timeline.ts`.

## Timeline (schema `remotion-ffmpeg-skill/timeline@1`)

| Key | Type | From | Meaning |
|---|---|---|---|
| `schema` | string | — | always `remotion-ffmpeg-skill/timeline@1` |
| `generator` | object | — | this skill's version and the ffmpeg-skill version that measured |
| `source.path` | string | analyze.py | absolute path of the measured file |
| `source.src` | string \| null | render.py | `staticFile()` path inside `public/` (added at render time) |
| `source.duration` | seconds | probe.py | container duration |
| `source.fps` | number | probe.py | composition fps = source fps |
| `source.width` / `height` | px | probe.py | composition size = source size |
| `source.has_video` / `has_audio` | bool | probe.py | |
| `scenes` | `[{start, end}]` | scenes.py | shot boundaries (one scene = whole file when skipped) |
| `silences` | `[[start, end]]` | silence.py `--list` | measured silent gaps |
| `speech` | `[[start, end]]` | silence.py `--list` | ranges kept between silences (with margin) |
| `peaks` | `[{time, rms}]` | scenes.py | audio energy peaks |
| `beats` | object \| null | scenes.py `--beats` | `{times, tempo_bpm, confidence, usable}`; compositions use the times only when `usable` |
| `highlights` | `[{start, end}]` | scenes.py `--highlights` | ranked by audio energy, stored in source order (analyze.py `--highlights N [--target S]`) |
| `captions` | `[{start, end, text}]` | your SRT / VTT / JSON | text exactly as written |
| `warnings` | `[string]` | analyze.py | VFR, HDR, rotation, odd frame rate |

All times are seconds on the source timeline. Frames are `Math.round(seconds * fps)` (round
half up) in both TypeScript and Python, so render.py's expected frame count matches the
composition exactly.

## Built-in compositions

| Id | Length | What it draws |
|---|---|---|
| `Captioned` | source duration | source + caption cards that spring in on each cue and fade out |
| `Jumpcut` | sum of `speech` ranges | speech ranges back to back, punch-in zoom on every other cut, captions re-timed (parts inside removed silences dropped) |
| `PeakPulse` | source duration | source + edge glow and slight zoom on each audio peak (scaled by its rms) or on each measured beat (`driver`), flash on scene cuts, progress bar with cut ticks |
| `Titled` | source duration | source + the user's lower thirds (`lowerThirds`) + a title card at the start of each measured scene (`sceneTitles`, in order) |
| `Highlights` | sum of `highlights` (whole file if none) | ranked ranges back to back in source order, flash on cuts, "2 / 5" counter, `title` over the first |
| `BeatMontage` | source duration | audio unbroken; the picture cuts every `beatsPerCut` measured beats, cycling through highlights (or scenes); no usable grid → cuts on scene changes |

## Options (`--options look.json`)

Every key is optional.

| Key | Default | Meaning |
|---|---|---|
| `accent` | `#ffcc00` | accent colour (caption underline, glow, progress bar) |
| `textColor` | `#ffffff` | caption text colour |
| `fontFamily` | Noto Sans JP, Hiragino Sans, Yu Gothic, … | CSS font stack; the font must exist on the rendering machine |
| `captionSize` | `0.055` | caption font size as a fraction of the frame's short side |
| `captionMargin` | `null` | caption bottom margin as a fraction of frame height; `null` = 0.08 landscape, 0.2 portrait (clear of Reels / TikTok UI) |
| `punchIn` | `1.12` | Jumpcut zoom on every other cut (`1` turns it off) |
| `pulse` | `0.6` | PeakPulse strength, 0..1 |
| `progressBar` | `true` | PeakPulse progress bar |
| `driver` | `"auto"` | PeakPulse: `peaks`, `beats`, or `auto` (beats when a usable grid was measured) |
| `lowerThirds` | `[]` | Titled: `[{"text", "sub"?, "start", "end"}]`, seconds on the source timeline |
| `sceneTitles` | `[]` | Titled: one title per measured scene, in order |
| `title` | `null` | Highlights: title over the first highlight |
| `beatsPerCut` | `4` | BeatMontage: measured beats per shot |

Unknown keys and wrong types are refused by render.py / still.py before anything renders.

Example:

```json
{ "accent": "#38bdf8", "captionSize": 0.065, "punchIn": 1.08 }
```

## Render-time props (set by render.py, not measured)

| Prop | From | Meaning |
|---|---|---|
| `frame` | `--aspect`, `--width`, `--fit` | `{width, height, fit}` of the output; `null` = the source's own size. Without `--width` the short side of the source is kept (720p → 720×1280 portrait), sizes rounded to even numbers |
| `font` | `--font-file`, or automatic for CJK captions | `{src, family}`: a font staged into `public/fonts/` and loaded before the first frame |
| `overlay` | `--overlay` | `true` = graphics only on a transparent background; render.py composites them over the source with ffmpeg-skill `overlay.py` |

`fit`: `blur` (contained over a blurred, cropped copy — default when the shape changes), `contain` (bars), `cover` (crop).

## Caption files

- **SRT** and **WebVTT**: timing lines `00:00:01,000 --> 00:00:03,500` (comma or dot), multi-line cue text kept; simple formatting tags (`<i>`, `<b>`, `<c>`, `<v ...>`) are stripped.
- **JSON**: `[{"start": 1.0, "end": 3.5, "text": "..."}]` or `{"cues": [...]}`.

## Adding your own composition

1. Write a component in `src/compositions/` that takes `Props` (`{ timeline, options }`).
2. Register it in `src/Root.tsx` with a `calculateMetadata` that derives length from the timeline.
3. `render.py --comp YourId ...` — the output is still probed and contact-sheeted; the frame
   count check is replaced by an INFO row because the skill cannot know your length rule.
