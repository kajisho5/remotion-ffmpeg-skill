import React from "react";
import { AbsoluteFill, Audio, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { Props, beatTimes, highlightRanges, outputFrame, resolveOptions, secToFrames } from "../timeline";

/**
 * BeatMontage: the source's audio plays straight through, unbroken, while the picture cuts on the
 * beat grid ffmpeg-skill measured (every options.beatsPerCut beats), cycling through the measured
 * scenes -- or the highlights, when analyze.py ranked some. No beat grid (or not confident): it cuts
 * on scene changes only, never on invented beats.
 */
export const BeatMontage: React.FC<Props> = (props) => {
  const { timeline, options } = props;
  const o = resolveOptions(options);
  const fit = outputFrame(props).fit;
  const { fps, durationInFrames } = useVideoConfig();
  const beats = beatTimes(timeline);
  const step = Math.max(1, Math.round(o.beatsPerCut));
  // Cut points (output frames): every Nth measured beat, else the measured scene starts.
  const cutTimes = beats.length > 0 ? beats.filter((_, i) => i % step === 0) : timeline.scenes.map((s) => s.start);
  const cuts = Array.from(new Set([0, ...cutTimes.map((t) => secToFrames(t, fps))]))
    .filter((f) => f >= 0 && f < durationInFrames)
    .sort((a, b) => a - b);
  // Picture pool: highlights if ranked, else scenes (each a [start, end] range of the source).
  const pool =
    timeline.highlights && timeline.highlights.length > 0
      ? highlightRanges(timeline)
      : timeline.scenes.map((s) => [s.start, s.end] as [number, number]);
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      {cuts.map((from, i) => {
        const to = i + 1 < cuts.length ? cuts[i + 1] : durationInFrames;
        const len = Math.max(1, to - from);
        const [ps, pe] = pool[i % pool.length];
        const poolLen = Math.max(1, secToFrames(pe, fps) - secToFrames(ps, fps));
        // Each visit to a range moves further into it; the shot stays inside the range when it fits
        // (a range shorter than the shot starts at its own beginning).
        const room = poolLen - len;
        const start = secToFrames(ps, fps) + (room > 0 ? (Math.floor(i / pool.length) * len) % (room + 1) : 0);
        const src = { ...timeline.source, has_audio: false };
        return (
          <Sequence key={i} from={from} durationInFrames={len} name={`shot ${i + 1}`}>
            <SourceVideo source={src} fit={fit} trimBefore={start} trimAfter={start + len} />
            {i > 0 ? <BeatFlash accent={o.accent} /> : null}
          </Sequence>
        );
      })}
      {timeline.source.src && timeline.source.has_audio ? <Audio src={staticFile(timeline.source.src)} /> : null}
    </AbsoluteFill>
  );
};

const BeatFlash: React.FC<{ accent: string }> = ({ accent }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const a = interpolate(frame, [0, fps * 0.15], [1, 0], { extrapolateRight: "clamp" });
  if (a <= 0) return null;
  const glow = Math.round(Math.min(width, height) * 0.05 * a);
  return <AbsoluteFill style={{ boxShadow: `inset 0 0 ${glow * 2}px ${glow}px ${accent}`, opacity: a }} />;
};
