# timeline.json and composition options

`analyze.py` writes one `timeline.json` per source. The Remotion compositions receive it as
props (`{ "timeline": ..., "options": ..., "frame": ..., "font": ..., "overlay": ... }`, written by `render.py` / `still.py` to
`<project>/.rfs/props-<comp>-<hash>.json`, one file per distinct set of props so parallel renders never collide). The TypeScript type is `Timeline` in
`templates/remotion-project/src/timeline.ts`.

## Timeline (schema `remotion-ffmpeg-skill/timeline@1`)

| Key | Type | From | Meaning |
|---|---|---|---|
| `schema` | string | — | always `remotion-ffmpeg-skill/timeline@1` |
| `generator` | object | — | this skill's version and the ffmpeg-skill version that measured |
| `source.path` | string | analyze.py | absolute path of the measured file (the conformed copy after `--conform`) |
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
| `clips` | `[{name, path, start, end}]` | analyze.py with several inputs | where each input sits after ffmpeg-skill join.py joined them (empty for one input) |
| `captions` | `[{start, end, text}]` | your SRT / VTT / JSON, or grouped from `words` | text exactly as written, timed on the (joined) source |
| `chapters` | `[{start, end, title}]` | `--chapters FILE` (`TIME TITLE` per line, YouTube's format) or `--chapters source` (the file's own markers) | titles as written; each ends where the next starts. YouTube's rules (first at 0:00, at least three, each ≥ 10 s) become warnings |
| `pip` | `{path, name, duration, width, height, fps, offset, confidence, measured}` or null | `--pip CAMERA` (offset from ffmpeg-skill sync.py over both audio tracks) or `--pip-offset` | offset = seconds after the source's start at which the camera's first frame belongs (negative: the camera started first) |
| `words` | `[{start, end, text}]` | `--words` (whisper JSON with word timestamps, `{"words": [...]}` or a list) | per-word timings with the engine's own spacing; Karaoke lights them up |
| `conform` | object \| null | analyze.py `--conform` | provenance when the source was VFR or HDR: `reasons` (`vfr`, `hdr`), `original` (path, name, sha256 fingerprint, duration, frame rates, colour tags), `output` (= `source.path`), `steps` (`{reason, tool, args, command, notes}` per ffmpeg-skill call: `fit.py --fps`, then `color.py --to-sdr`), `measured` (ffmpeg-skill probe of the copy: CFR, BT.709). `pip.conform` is the same for a conformed camera. null = the source was drawn on as it is |
| `warnings` | `[string]` | analyze.py | rotation, odd frame rate, chapters, transcript (VFR and HDR are never warnings: conformed or refused) |

All times are seconds on the source timeline. Frames are `Math.round(seconds * fps)` (round
half up) in both TypeScript and Python, so render.py's expected frame count matches the
composition exactly.

## Built-in compositions

| Id | Length | What it draws |
|---|---|---|
| `Captioned` | source duration | source + caption cards that spring in on each cue and fade out |
| `Jumpcut` | sum of `speech` ranges | speech ranges back to back, punch-in zoom on every other cut, captions re-timed (parts inside removed silences dropped) |
| `PeakPulse` | source duration | source + edge glow and slight zoom on each audio peak (scaled by its rms) or on each measured beat (`driver`), flash on scene cuts, progress bar with cut ticks |
| `Titled` | source duration | source + the user's lower thirds (`lowerThirds`) + a title card at the start of each measured scene (`sceneTitles`, in order) + a chapter card at each chapter start (`chapters`, numbered n / total) |
| `Highlights` | sum of `highlights` (whole file if none) | ranked ranges back to back in source order, flash on cuts, "2 / 5" counter, `title` over the first |
| `Karaoke` | source duration | caption cues whose words light up at their measured times (current word accent + lift, spoken white, upcoming dimmed); cues without timed words show plain |
| `Pip` | source duration | the source with `pip` (a camera) in a corner while the camera has pictures, synced by `pip.offset`; captions on top as in Captioned |
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
| `pipCorner` | `"bottom-right"` | Pip: `top-left`, `top-right`, `bottom-left`, `bottom-right` |
| `pipSize` | `0.28` | Pip: camera width as a fraction of the frame width (circle: of the short side), 0.05–0.6 |
| `pipShape` | `"rounded"` | Pip: `rounded` or `circle` |
| `pipAudio` | `false` | Pip: also play the camera's own audio |
| `chapterSeconds` | `4` | Titled: how long a chapter card stays up (cut short by the next chapter; 0 = none) |

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
- **Word timings** (`--words`): whisper / faster-whisper JSON made with word timestamps (`segments[].words[]` with `word`, `start`, `end`), `{"words": [...]}` or a plain list. With no `--captions`, cues are grouped mechanically: a new cue after a pause over 0.7 s, past 32 characters or 4 s. Words are never added, dropped or reworded.
- **transcription-skill transcript** (`--words`): a JSON document with a `schema` key is read as a [transcription-skill](https://github.com/kajisho5/transcription-skill) Transcript and must be `transcription-skill/transcript/0.1`; any other schema id or version is refused. The document is checked against that contract (required fields, finite numbers, `0 ≤ start < end`, segments ordered and not overlapping, words ordered and inside their segment within 0.01 s, ends within the duration + 0.5 s, confidences in [0, 1], `duration` = `source.media_duration`) and refused on the first violation; a transcript whose `duration` differs from the measured source by more than 0.5 s is refused too (it is of another file). Times are used exactly as written — not rounded, snapped or interpolated.
  - Words are trimmed in a transcript, so each word's leading space is read back from the segment's verbatim `raw_text` (one space where `raw_text` has whitespace before the word; none between Japanese tokens). Words that do not spell `raw_text` in order are not trusted: that segment becomes one plain cue, with a warning.
  - Without `--captions`, cues are grouped from the words with the rule above **inside each segment** — a cue never spans two segments. A segment whose `words` is `null` becomes one cue with the segment's own `start`, `end` and `text`; it gets no `words`, so Karaoke shows it plain. The transcript's own `warnings` are carried into the timeline's `warnings` (prefixed `transcript:`), and so is a note when `source.fingerprint` is not the source's sha256.

## Adding your own composition

1. Write a component in `src/compositions/` that takes `Props` (`{ timeline, options }`).
2. Register it in `src/Root.tsx` with a `calculateMetadata` that derives length from the timeline.
3. `render.py --comp YourId ...` — the output is still probed and contact-sheeted; the frame
   count check is replaced by an INFO row because the skill cannot know your length rule.
