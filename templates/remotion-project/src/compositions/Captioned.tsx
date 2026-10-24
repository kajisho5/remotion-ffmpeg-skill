import React from "react";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { Props, fontStack, outputFrame, resolveOptions, secToFrames, type Options } from "../timeline";

/**
 * Captioned: the source, full length, with each measured caption cue popping in on its own
 * timing. Cue text is drawn exactly as written in the caption file.
 */
export const Captioned: React.FC<Props> = (props) => {
  const { timeline, options, font, overlay } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : <SourceVideo source={timeline.source} fit={outputFrame(props).fit} />}
      {timeline.captions.map((c, i) => {
        const from = secToFrames(c.start, fps);
        const dur = Math.max(1, secToFrames(c.end, fps) - from);
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`cue ${i + 1}`} layout="none">
            <CaptionCard text={c.text} durationInFrames={dur} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

/** Bottom margin: the option if set, else clear of Reels/TikTok UI on portrait frames. */
export const captionMarginPx = (o: Options, width: number, height: number): number =>
  height * (o.captionMargin ?? (height > width ? 0.2 : 0.08));

export const CaptionCard: React.FC<{ text: string; durationInFrames: number; o: Options; fontFamily: string }> = ({
  text,
  durationInFrames,
  o,
  fontFamily,
}) => {
  const frame = useCurrentFrame();
  const { fps, height, width } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 180, mass: 0.6 } });
  const fadeFrames = Math.min(6, Math.floor(durationInFrames / 3));
  const exit =
    fadeFrames > 0
      ? interpolate(frame, [durationInFrames - fadeFrames, durationInFrames], [1, 0], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
        })
      : 1;
  const size = Math.round(Math.min(width, height) * o.captionSize);
  const lang = /[\u3040-\u30ff]/.test(text)
    ? "ja"
    : /[\uac00-\ud7af]/.test(text)
      ? "ko"
      : /[\u3400-\u9fff]/.test(text)
        ? "ja"
        : undefined;
  const cjk = lang !== undefined;
  return (
    <AbsoluteFill
      style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: captionMarginPx(o, width, height) }}
    >
      <div
        lang={lang}
        style={{
          maxWidth: width * 0.86,
          padding: `${size * 0.28}px ${size * 0.6}px`,
          borderRadius: size * 0.35,
          background: "rgba(0,0,0,0.62)",
          borderBottom: `${Math.max(2, Math.round(size * 0.08))}px solid ${o.accent}`,
          color: o.textColor,
          fontFamily,
          fontWeight: 700,
          fontSize: size,
          lineHeight: 1.3,
          textAlign: "center",
          whiteSpace: "pre-wrap",
          // Japanese: break between phrases (文節), not inside a word; balance the lines so a
          // cue never ends with one orphaned character. Latin: normal word breaks.
          wordBreak: (cjk ? "auto-phrase" : "normal") as React.CSSProperties["wordBreak"],
          textWrap: "balance",
          overflowWrap: "break-word",
          opacity: Math.min(enter, exit),
          transform: `translateY(${(1 - enter) * size * 0.6}px) scale(${0.92 + 0.08 * enter})`,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};
