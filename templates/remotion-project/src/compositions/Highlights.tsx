import React from "react";
import { AbsoluteFill, Series, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { Props, fontStack, highlightRanges, outputFrame, resolveOptions, secToFrames, type Options } from "../timeline";

/**
 * Highlights: the highlight ranges ffmpeg-skill ranked (analyze.py --highlights, audio energy) played
 * back to back in source order, a flash on each cut, a "2 / 5" counter, and the user's title over the
 * first one. Which ranges count as highlights is ffmpeg-skill's measured proposal, not a verdict.
 */
export const Highlights: React.FC<Props> = (props) => {
  const { timeline, options, font } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const fit = outputFrame(props).fit;
  const { fps } = useVideoConfig();
  const ranges = highlightRanges(timeline);
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <Series>
        {ranges.map(([s, e], i) => {
          const a = secToFrames(s, fps);
          const len = Math.max(1, secToFrames(e, fps) - a);
          return (
            <Series.Sequence key={i} durationInFrames={len} name={`highlight ${i + 1}`}>
              <SourceVideo source={timeline.source} fit={fit} trimBefore={a} trimAfter={a + len} />
              {i > 0 ? <CutFlash /> : null}
              <Counter index={i} total={ranges.length} o={o} fontFamily={family} />
              {i === 0 && o.title ? <Title text={o.title} len={len} o={o} fontFamily={family} /> : null}
            </Series.Sequence>
          );
        })}
      </Series>
    </AbsoluteFill>
  );
};

const CutFlash: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = interpolate(frame, [0, fps * 0.2], [0.5, 0], { extrapolateRight: "clamp" });
  return a > 0 ? <AbsoluteFill style={{ backgroundColor: "white", opacity: a }} /> : null;
};

const Counter: React.FC<{ index: number; total: number; o: Options; fontFamily: string }> = ({ index, total, o, fontFamily }) => {
  const { width, height } = useVideoConfig();
  if (total <= 1) return null;
  const size = Math.round(Math.min(width, height) * 0.035);
  return (
    <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "flex-end", padding: size }}>
      <div
        style={{
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          color: o.textColor,
          background: "rgba(0,0,0,0.55)",
          borderLeft: `${Math.max(3, size * 0.15)}px solid ${o.accent}`,
          padding: `${size * 0.2}px ${size * 0.5}px`,
        }}
      >
        {index + 1} / {total}
      </div>
    </AbsoluteFill>
  );
};

const Title: React.FC<{ text: string; len: number; o: Options; fontFamily: string }> = ({ text, len, o, fontFamily }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 15 } });
  const shown = Math.min(len, Math.round(fps * 2.5));
  const exit = interpolate(frame, [shown - 8, shown], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const size = Math.round(Math.min(width, height) * 0.075);
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div
        style={{
          fontFamily,
          fontWeight: 900,
          fontSize: size,
          color: o.textColor,
          maxWidth: width * 0.84,
          textAlign: "center",
          whiteSpace: "pre-wrap",
          textWrap: "balance",
          opacity: Math.min(enter, exit),
          transform: `translateY(${(1 - enter) * size}px)`,
          textShadow: `0 0 ${size * 0.4}px rgba(0,0,0,0.8)`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
