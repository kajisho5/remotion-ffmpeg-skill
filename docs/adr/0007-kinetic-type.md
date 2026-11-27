# 0007. KineticType: a schedule from measurements, drawn as written

2026-11-27. ECOSYSTEM_ROADMAP step 7.

## Context

Kinetic type here is the measured kind only: words on the beat grid, or at the times a speech engine measured. Kinetic typography from a request with no measured timing is hyperframes-skill's ([Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156), O17).

"Every word starts on a beat within one frame" has to be checked in the rendered pixels. A check in the browser's own arithmetic is not enough.

## Decision

- Python computes the schedule and TypeScript draws it. `analyze.py --kinetic words|beats|auto` writes `kinetic` into the timeline (`scripts/_kinetic.py`). The composition computes no time of its own. A unit starts on frame `round(start * fps)` on both sides, as every other time in this skill does.
- Text comes from the caption cues (`--captions`, e.g. a lyric SRT, or the cues grouped from `--words`) and is never changed. A unit is a word, split at whitespace. In text written without spaces (Japanese, Chinese), a unit is one character. Punctuation and the long-vowel mark stay with the character before them.
- `words`: each word of a cue (midpoint inside the cue, as Karaoke takes them) starts at its own measured time. `beats`: each unit takes the next measured beat at or after its cue's start. Units are `--kinetic-step` beats apart, and a beat is used by one unit at most. `auto` means words when given, else beats. With no usable measurement the schedule is refused (`kind: input`). There is no fallback to spread or guessed times.
- A line shows from its first unit until its cue ends. When the beats run past the cue, the line stays up until its last unit plus 0.25 s, and a warning says so. When the beats run out, the remaining units are not drawn, and a warning says so. A line never runs into the next one.
- Drawing: a unit is drawn invisibly before its start frame and visibly on it. Hidden units keep their place, so nothing reflows. Only transforms, opacity and clip paths animate. `kineticStyle` is `pop`, `wipe` (a mask), `tracking` (characters close in through transforms, not letter-spacing, which would reflow) or `rise`. `kineticReveal: "char"` lets the characters follow each other `kineticStagger` s apart, the first on the unit's start. CJK text gets the font ffmpeg-skill finds, as captions do.
- `render.py --comp KineticType` refuses a timeline without `kinetic`.

## Consequences

- The contract changes additively: analyze.py gains `--kinetic` and `--kinetic-step`, its summary gains `kinetic` (the number of units), the timeline gains the optional `kinetic` key, the options gain the four `kinetic*` keys, and `KineticType` joins the built-in compositions.
- Measured (`test_integration.KineticType`, 120 BPM fixture: an 80 Hz hit every 0.5 s, on a `--blank` run with that music): all 11 units ("Neon lights over town", then 今日もいい天気 one character each) start on a measured beat, and on the true 0.5 s grid, within one frame. In the pixels: a render with unit *i* never shown matches the real render byte for byte on the frame before the unit's start, and differs on its start frame. This holds for each English word and for two of the Japanese characters, with the CJK font staged.
- It needs ffmpeg-skill 3.2.0 or later (an audio-only file measured for beats). The CI leg on 3.0.0 skips the class.
