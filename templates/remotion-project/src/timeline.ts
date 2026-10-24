// The timeline.json contract written by analyze.py (schema remotion-ffmpeg-skill/timeline@1).
// Every number here was measured by ffmpeg-skill; compositions only read it.

export type Range = [number, number];

export type Source = {
  /** Path the skill measured. Not used by the browser. */
  path?: string;
  /** staticFile() path inside public/, set by render.py / still.py. null = no picture (placeholder). */
  src: string | null;
  name: string;
  duration: number;
  fps: number;
  width: number;
  height: number;
  has_video: boolean;
  has_audio: boolean;
};

export type Caption = { start: number; end: number; text: string };
export type Peak = { time: number; rms: number };
export type Scene = { start: number; end: number };

export type Timeline = {
  schema: string;
  source: Source;
  scenes: Scene[];
  silences: Range[];
  speech: Range[];
  peaks: Peak[];
  beats?: unknown;
  captions: Caption[];
  warnings?: string[];
};

/** Look-and-feel knobs. Every field is optional in the props; defaults below. */
export type Options = {
  accent: string;
  textColor: string;
  fontFamily: string;
  /** Caption font size as a fraction of the frame height. */
  captionSize: number;
  /** Caption block bottom margin as a fraction of the frame height. */
  captionMargin: number;
  /** Jumpcut: zoom applied to every other cut (1 = off). */
  punchIn: number;
  /** PeakPulse: strength of the pulse, 0..1. */
  pulse: number;
  /** PeakPulse: show the progress bar along the bottom edge. */
  progressBar: boolean;
};

export const DEFAULT_OPTIONS: Options = {
  accent: "#ffcc00",
  textColor: "#ffffff",
  fontFamily: "'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', 'Noto Sans', 'Helvetica Neue', Arial, sans-serif",
  captionSize: 0.055,
  captionMargin: 0.08,
  punchIn: 1.12,
  pulse: 0.6,
  progressBar: true,
};

export type Props = { timeline: Timeline; options?: Partial<Options> };

export const resolveOptions = (o?: Partial<Options>): Options => ({ ...DEFAULT_OPTIONS, ...(o ?? {}) });

export const secToFrames = (seconds: number, fps: number): number => Math.round(seconds * fps);

/** Speech ranges, or the whole source when analyze.py found no silence. */
export const speechRanges = (t: Timeline): Range[] =>
  t.speech && t.speech.length > 0 ? t.speech : [[0, t.source.duration]];

// Durations: must match expected_frames() in scripts/_common.py (render.py verifies the output against it).
export const fullLengthFrames = (t: Timeline): number =>
  Math.max(1, secToFrames(t.source.duration, t.source.fps));

export const jumpcutFrames = (t: Timeline): number => {
  const fps = t.source.fps;
  const total = speechRanges(t).reduce(
    (sum, [s, e]) => sum + Math.max(1, secToFrames(e, fps) - secToFrames(s, fps)),
    0,
  );
  return Math.max(1, total);
};

export type TimedCue = { from: number; durationInFrames: number; text: string };

/**
 * Map caption cues from source time onto the Jumpcut timeline (speech ranges played back to back).
 * Each piece of a cue that overlaps a kept range becomes its own cue; pieces inside removed
 * silences disappear. Neighbouring pieces of the same cue that end up adjacent are merged.
 */
export const retimeCaptions = (t: Timeline): TimedCue[] => {
  const fps = t.source.fps;
  const out: TimedCue[] = [];
  let offset = 0;
  for (const [s, e] of speechRanges(t)) {
    const a = secToFrames(s, fps);
    const b = a + Math.max(1, secToFrames(e, fps) - a);
    for (const c of t.captions) {
      const ca = Math.max(a, secToFrames(c.start, fps));
      const cb = Math.min(b, secToFrames(c.end, fps));
      if (cb <= ca) continue;
      const from = offset + (ca - a);
      const last = out[out.length - 1];
      if (last && last.text === c.text && last.from + last.durationInFrames === from) {
        last.durationInFrames += cb - ca;
      } else {
        out.push({ from, durationInFrames: cb - ca, text: c.text });
      }
    }
    offset += b - a;
  }
  return out;
};

/** Fictional sample for Remotion Studio previews; real renders always pass a measured timeline. */
export const SAMPLE_TIMELINE: Timeline = {
  schema: "remotion-ffmpeg-skill/timeline@1",
  source: {
    src: null,
    name: "sample (no source)",
    duration: 8,
    fps: 30,
    width: 1280,
    height: 720,
    has_video: false,
    has_audio: false,
  },
  scenes: [
    { start: 0, end: 4 },
    { start: 4, end: 8 },
  ],
  silences: [[3, 5]],
  speech: [
    [0, 3.15],
    [4.85, 8],
  ],
  peaks: [
    { time: 1.5, rms: 0.09 },
    { time: 6.2, rms: 0.07 },
  ],
  captions: [
    { start: 0.4, end: 2.8, text: "Sample caption for the preview" },
    { start: 5.0, end: 7.6, text: "Second line, placeholder text" },
  ],
};
