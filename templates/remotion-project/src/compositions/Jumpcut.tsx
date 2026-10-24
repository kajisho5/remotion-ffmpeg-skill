import React from "react";
import { AbsoluteFill, Sequence, Series, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { CaptionCard } from "./Captioned";
import { Props, resolveOptions, retimeCaptions, secToFrames, speechRanges } from "../timeline";

/**
 * Jumpcut: plays only the speech ranges ffmpeg-skill measured (silences removed), and punches
 * in on every other cut so the jumps read as intentional. Captions are re-timed onto the new
 * timeline; the part of a cue that falls inside a removed silence is dropped, its text is never rewritten.
 */
export const Jumpcut: React.FC<Props> = ({ timeline, options }) => {
  const o = resolveOptions(options);
  const { fps } = useVideoConfig();
  const ranges = speechRanges(timeline);
  const cues = retimeCaptions(timeline);
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <Series>
        {ranges.map(([s, e], i) => {
          const a = secToFrames(s, fps);
          const len = Math.max(1, secToFrames(e, fps) - a);
          const zoom = i % 2 === 1 ? o.punchIn : 1;
          return (
            <Series.Sequence key={i} durationInFrames={len} name={`cut ${i + 1}`}>
              <Punch zoom={zoom} len={len}>
                <SourceVideo source={timeline.source} trimBefore={a} trimAfter={a + len} />
              </Punch>
            </Series.Sequence>
          );
        })}
      </Series>
      {cues.map((c, i) => (
        <Sequence key={i} from={c.from} durationInFrames={c.durationInFrames} name={`cue ${i + 1}`} layout="none">
          <CaptionCard text={c.text} durationInFrames={c.durationInFrames} o={o} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const Punch: React.FC<{ zoom: number; len: number; children: React.ReactNode }> = ({ zoom, len, children }) => {
  const frame = useCurrentFrame();
  // A slow drift inside each cut keeps the frame alive; the step between cuts is the jump.
  const drift = interpolate(frame, [0, len], [0, 0.015], { extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ transform: `scale(${zoom + drift})` }}>{children}</AbsoluteFill>;
};
