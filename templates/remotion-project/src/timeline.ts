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
export type Chapter = { start: number; end: number; title: string };
/** A second recording shown picture-in-picture (analyze.py --pip). offset: seconds after the source's
 * start at which the camera's first frame belongs (measured from both audio tracks, or given). */
export type Pip = {
  path: string;
  name: string;
  src?: string | null;
  duration: number;
  width: number;
  height: number;
  fps: number;
  offset: number;
  confidence: number | null;
  measured: boolean;
  /** The camera's own conform record when analyze.py --conform conformed it. */
  conform?: Conform | null;
};
/** Provenance of a source analyze.py --conform made drawable (VFR -> CFR, HDR -> SDR BT.709 with
 * ffmpeg-skill). The compositions never read it: the source above is already the conformed copy. */
export type Conform = {
  reasons: ("vfr" | "hdr")[];
  original: { path: string; name: string; fingerprint: string } & Record<string, unknown>;
  output: string;
  steps: { reason: "vfr" | "hdr"; tool: string; args: string[]; command: string; notes: string[] }[];
  measured: Record<string, unknown>;
};
export type Beats = { times: number[]; tempo_bpm: number | null; confidence: number | null; usable: boolean };
export type Highlight = { start: number; end: number };
/** A lower third: text from the user (options), timing in source seconds. */
export type LowerThird = { text: string; sub?: string; start: number; end: number };
export type Peak = { time: number; rms: number };
export type Scene = { start: number; end: number };

export type Timeline = {
  schema: string;
  source: Source;
  scenes: Scene[];
  silences: Range[];
  speech: Range[];
  peaks: Peak[];
  beats?: Beats | null;
  highlights?: Highlight[];
  /** Several inputs joined by ffmpeg-skill: where each clip sits on the joined timeline. */
  clips?: { name: string; start: number; end: number }[];
  captions: Caption[];
  /** Word timings from a speech engine (analyze.py --words), text with the engine's own spacing. */
  words?: Caption[];
  /** Chapters from the user's list or the source's own markers (analyze.py --chapters); titles as written. */
  chapters?: Chapter[];
  pip?: Pip | null;
  /** Set when analyze.py --conform measured a conformed copy instead of the original (null otherwise). */
  conform?: Conform | null;
  warnings?: string[];
};

/** Look-and-feel knobs. Every field is optional in the props; defaults below. */
export type Options = {
  accent: string;
  textColor: string;
  fontFamily: string;
  /** Caption font size as a fraction of the frame's short side. */
  captionSize: number;
  /** Caption block bottom margin as a fraction of the frame height; null = 0.08 landscape, 0.2 portrait (clear of Reels/TikTok UI). */
  captionMargin: number | null;
  /** Jumpcut: zoom applied to every other cut (1 = off). */
  punchIn: number;
  /** PeakPulse: strength of the pulse, 0..1. */
  pulse: number;
  /** PeakPulse: show the progress bar along the bottom edge. */
  progressBar: boolean;
  /** PeakPulse: what drives the pulse -- measured audio peaks, the measured beat grid, or beats when usable. */
  driver: "auto" | "peaks" | "beats";
  /** Titled: lower thirds (text from the user, never invented). */
  lowerThirds: LowerThird[];
  /** Titled: one title per measured scene, in order; a scene without an entry gets none. */
  sceneTitles: string[];
  /** Highlights: title shown over the first highlight (optional). */
  title: string | null;
  /** BeatMontage: cut the picture every N measured beats. */
  beatsPerCut: number;
  /** Titled: seconds a chapter card stays up at the start of each chapter (0 = no chapter cards). */
  chapterSeconds: number;
  /** Pip: which corner the camera sits in. */
  pipCorner: "top-left" | "top-right" | "bottom-left" | "bottom-right";
  /** Pip: camera width as a fraction of the frame width (circle: of the short side). */
  pipSize: number;
  /** Pip: rounded rectangle or circle. */
  pipShape: "rounded" | "circle";
  /** Pip: play the camera's own audio too (off: the source's audio only). */
  pipAudio: boolean;
};

export const DEFAULT_OPTIONS: Options = {
  accent: "#ffcc00",
  textColor: "#ffffff",
  fontFamily: "'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', 'Noto Sans', 'Helvetica Neue', Arial, sans-serif",
  captionSize: 0.055,
  captionMargin: null,
  punchIn: 1.12,
  pulse: 0.6,
  progressBar: true,
  driver: "auto",
  lowerThirds: [],
  sceneTitles: [],
  title: null,
  beatsPerCut: 4,
  chapterSeconds: 4,
  pipCorner: "bottom-right",
  pipSize: 0.28,
  pipShape: "rounded",
  pipAudio: false,
};

/** Where the camera plays on the source timeline: [from, durationInFrames, trimBefore] in frames. */
export const pipFrames = (p: Pip, fps: number, total: number): [number, number, number] => {
  const from = Math.max(0, secToFrames(p.offset, fps));
  const trimBefore = Math.max(0, secToFrames(-p.offset, fps));
  const end = Math.min(total, secToFrames(p.offset + p.duration, fps));
  return [from, Math.max(1, end - from), trimBefore];
};

/** [from, durationInFrames] of the card at the start of a chapter (Titled). render.py mirrors this. */
export const chapterCardFrames = (c: Chapter, fps: number, seconds: number): [number, number] => {
  const from = secToFrames(c.start, fps);
  return [from, Math.max(1, Math.min(secToFrames(c.end, fps), from + Math.round(fps * seconds)) - from)];
};

/**
 * Output frame, chosen at render time (render.py --aspect / --width / --fit); not a measurement.
 * Absent = the source's own size. fit: how the source fills a frame of another shape --
 * contain (bars), cover (crop) or blur (contained over a blurred, cropped copy).
 */
export type Fit = "contain" | "cover" | "blur";
export type Frame = { width: number; height: number; fit: Fit };

/** A font file staged into public/ by render.py (--font-file, or a CJK font found by ffmpeg-skill). */
export type FontAsset = { src: string; family: string };

export type Props = {
  timeline: Timeline;
  options?: Partial<Options>;
  frame?: Frame | null;
  font?: FontAsset | null;
  /**
   * Graphics only, on a transparent background (render.py --overlay): the source is not drawn and
   * ffmpeg-skill composites the result over it afterwards -- much faster on long footage.
   */
  overlay?: boolean;
};

export const resolveOptions = (o?: Partial<Options>): Options => ({ ...DEFAULT_OPTIONS, ...(o ?? {}) });

export const outputFrame = (p: Props): Frame =>
  p.frame ?? { width: p.timeline.source.width, height: p.timeline.source.height, fit: "contain" };

/** Font stack with the staged font (if any) first. */
export const fontStack = (o: Options, font?: FontAsset | null): string =>
  font ? `'${font.family}', ${o.fontFamily}` : o.fontFamily;

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

/** Highlight ranges, or the whole source when analyze.py was not asked for any. */
export const highlightRanges = (t: Timeline): Range[] =>
  t.highlights && t.highlights.length > 0 ? t.highlights.map((h) => [h.start, h.end] as Range) : [[0, t.source.duration]];

export const highlightFrames = (t: Timeline): number => {
  const fps = t.source.fps;
  const total = highlightRanges(t).reduce(
    (sum, [s, e]) => sum + Math.max(1, secToFrames(e, fps) - secToFrames(s, fps)),
    0,
  );
  return Math.max(1, total);
};

/** Usable measured beat times (empty when the grid was not measured or not confident). */
export const beatTimes = (t: Timeline): number[] => (t.beats && t.beats.usable ? t.beats.times : []);

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
