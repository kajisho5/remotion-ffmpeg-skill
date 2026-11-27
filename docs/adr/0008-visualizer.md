# 0008. Visualizer: the audio at its frame, loops of whole measured bars

2026-11-27. ECOSYSTEM_ROADMAP step 8.

## Context

The audio visualizer is this skill's ([Velisa ownership decisions 2026-11-12](https://github.com/kajisho5/Velisa/pull/156), O17). PeakPulse and BeatMontage react to measured peaks and beats. Nothing drew the audio itself.

The roadmap asks for two things. Bars must react to a test tone on the right frame. A loop for an edit must pass qc-skill's loop seam check (its `video.loop_seam`, ADR-026).

## Decision

- A new `Visualizer` composition decodes the source's own audio in the browser with `@remotion/media-utils` (`useAudioData`, `visualizeAudio`, `visualizeAudioWaveform`; MIT). The template pins it at `4.0.540`, the same version as `remotion` and `@remotion/cli`. Remotion packages must all be one version, and there is no lockfile, as before.
- `@remotion/media-utils` is part of Remotion. Remotion's licence (free for individuals and companies of up to 3 employees, a company licence above that; README "Licence") applies to it as it does to every render. Nothing here changes those terms.
- Each frame shows the audio around that frame's time and nothing later:
  - a 1024-sample FFT (`visualizeAudio`, `numberOfSamples` 512) centred on `frame / fps`;
  - `smoothing: false`, because Remotion's smoothing averages the frames before and after, and a tone would then show a frame early;
  - bars spread logarithmically over the bins, levels on a 60 dB scale.
- `visualizer` picks `bars`, `spectrum`, `radial` or `waveform` (an 80 ms window). Every style also draws a ring that hits on each measured beat. The caption cues are drawn by Karaoke's own cue component, so lyrics with `--words` light up word by word.
- A loop: `loopBars` (0 = as many as fit, N = N bars) of `beatsPerBar` measured beats.
  - The seam falls halfway between two measured beats, where beat-driven motion is quietest. The loop runs from halfway between beats 0 and 1 to halfway between beats k and k+1, with k = bars x beatsPerBar.
  - A loop that starts on a beat put the beat's hit on the seam. It measured a seam ratio of 14.2, against 0.89 for the halfway seam.
  - The length rule is `visualizerRange` in `src/timeline.ts` and `loop_range` in `_common.py`. `expected_frames()` now takes the options.
  - render.py refuses, before rendering, a loop that the beats cannot hold, and a Visualizer source with no audio.
- CI checks out qc-skill (no dependencies) and runs its `video.loop_seam` check on the loop render with `max_seam_ratio` 1.3, qc-skill's suggested start. The same measure is also computed in the test itself, so the check holds without qc-skill too.

## Consequences

- The contract changes additively. `Visualizer` joins the built-in compositions. The options gain `visualizer`, `visualizerBars`, `loopBars` and `beatsPerBar`. The template gains one dependency.
- Measured on the fixtures in `test_integration.Visualizer`:
  - Tone test: silence, then 440 Hz from 1.000 s. Frame 29 shows flat bars (mean grey 2.2 in the bar area). Frame 30 shows risen bars (63).
  - Loop test: a 120 BPM 80 Hz hit, `--blank 8 --beats`, `loopBars: 0`, which makes 3 bars, 180 frames from frame 8. qc-skill PASSes it at ratio 0.889. The same loop cut one frame short FAILs at 3.1.
- The audio is decoded whole in the browser, so memory grows with the source's length. A long source is better drawn as a loop or a `--frames` range.
