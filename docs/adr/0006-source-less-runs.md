# 0006. Source-less runs (`--blank`)

2026-11-27. ECOSYSTEM_ROADMAP step 6.

## Context

Every composition took its length, rate and frame from a probed source. Music-only or text-only pictures (kinetic type over a track, a visualizer, a lyric card) had no source to probe, so they could not use the measured timeline at all.

## Decision

- `analyze.py --blank SECONDS [--size WxH] [--fps RATE] [--music FILE]` writes a `timeline@1` file with no footage. No input file is given. The defaults are 1920x1080 and 30 fps. The size must be even, between 16 and 8192 px. The rate is read by the TB-2 rule (`exact_rate`), so `29.97` is 30000/1001.
- The length, size and rate are the caller's. They are not measurements, and the timeline says so: `source.blank: true`, `source.has_video: false`, and a top-level `blank` record.
- The music is measured as a source's audio is. ffmpeg-skill `probe.py`, `scenes.py` (peaks always, the beat grid with `--beats`) and `silence.py` run on it. Peaks, beats and ranges past the blank's end are dropped. A longer track is cut at the end and a shorter one leaves silence after it. Both cases are warnings. `source.path` is the music, so render.py stages it as it stages an audio-only source. `blank.music` keeps its sha256 fingerprint and measured length.
- ffmpeg-skill measures an audio-only file from 3.2.0. An older ffmpeg-skill refuses the music, and that error is passed on. The declared range stays `>=2.0.0 <5.0.0`, because a blank run without music needs no ffmpeg-skill measurement.
- Flags that need footage are refused with `--blank`: `--joined`, `--pip`, `--pip-offset`, `--conform*`, `--highlights`, `--target` and `--chapters source`. `--size`, `--fps` and `--music` without `--blank` are refused too.
- A transcript (`--words`) is checked against the music's length and fingerprint, as it is against a source. With no music it is used as written, with a warning.
- The picture is the new `background` option: any CSS colour or gradient, default `#000000`. `SourceVideo` draws it for a blank source and plays the music under it. Every built-in composition passes the option on, so all of them render on a blank timeline. `--overlay` is still refused, because it needs a video to composite onto.
- `input` keeps `minItems: 1` in the contract. On the command line a blank run simply leaves it out; a caller that must send at least one item (an MCP client) sends the placeholder `-`, which means "no input file" and is accepted only with `--blank`. Removing `minItems` instead would loosen the schema, but contract-diff counts a removed key as breaking, so it stays.
- `pipeline.py` takes the same four flags and passes them to analyze.py. Its outputs go next to the music, or into the working folder without music. They are named `<music>_blank.*`, or `blank.*` without music.

## Consequences

- The contract changes additively. analyze.py and pipeline.py gain `blank`, `size`, `fps` and `music`; `input` is unchanged apart from its description. The timeline gains the optional `source.blank` and `blank` keys, and the options gain `background`. `contract_version` stays 1.0.
- Measured: `pipeline.py --blank 15 --size 1080x1920 --music bgm.wav --comp PeakPulse` rendered 450 frames (15.0 s at 30 fps), 1080x1920, with the music's audio. `test_integration.Blank` runs it on every CI machine where ffmpeg-skill is 3.2.0 or later. The 3.0.0 leg skips it.
