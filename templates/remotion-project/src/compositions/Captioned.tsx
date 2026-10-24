import React from "react";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { Props, resolveOptions, secToFrames, type Options } from "../timeline";

/**
 * Captioned: the source, full length, with each measured caption cue popping in on its own
 * timing. Cue text is drawn exactly as written in the caption file.
 */
export const Captioned: React.FC<Props> = ({ timeline, options }) => {
  const o = resolveOptions(options);
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <SourceVideo source={timeline.source} />
      {timeline.captions.map((c, i) => {
        const from = secToFrames(c.start, fps);
        const dur = Math.max(1, secToFrames(c.end, fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`cue ${i + 1}`} layout="none">
            <CaptionCard text={c.text} durationInFrames={dur} o={o} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const CaptionCard: React.FC<{ text: string; durationInFrames: number; o: Options }> = ({ text, durationInFrames, o }) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 180, mass: 0.6 } });
  const fadeFrames = Math.min(6, Math.floor(durationInFrames / 3));
  const exit = fadeFrames > 0
    ? interpolate(frame, [durationInFrames - fadeFrames, durationInFrames], [1, 0], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
      })
    : 1;
  const size = Math.round(height * o.captionSize);
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: height * o.captionMargin }}>
      <div
        style={{
          maxWidth: width * 0.86,
          padding: `${size * 0.28}px ${size * 0.6}px`,
          borderRadius: size * 0.35,
          background: "rgba(0,0,0,0.62)",
          borderBottom: `${Math.max(2, Math.round(size * 0.08))}px solid ${o.accent}`,
          color: o.textColor,
          fontFamily: o.fontFamily,
          fontWeight: 700,
          fontSize: size,
          lineHeight: 1.3,
          textAlign: "center",
          whiteSpace: "pre-wrap",
          opacity: Math.min(enter, exit),
          transform: `translateY(${(1 - enter) * size * 0.6}px) scale(${0.92 + 0.08 * enter})`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
