import React from "react";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { Props, fontStack, outputFrame, resolveOptions, secToFrames, type Options } from "../timeline";

/**
 * Titled: the source, full length, with lower thirds the user wrote (options.lowerThirds) and a
 * title card at the start of each measured scene (options.sceneTitles, in scene order). The skill
 * places text where the measurements say; it never writes the text.
 */
export const Titled: React.FC<Props> = (props) => {
  const { timeline, options, font, overlay } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const { fps } = useVideoConfig();
  const sceneCards = timeline.scenes
    .map((sc, i) => ({ sc, text: o.sceneTitles[i] }))
    .filter((x): x is { sc: { start: number; end: number }; text: string } => Boolean(x.text));
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : <SourceVideo source={timeline.source} fit={outputFrame(props).fit} />}
      {sceneCards.map(({ sc, text }, i) => {
        const from = secToFrames(sc.start, fps);
        const dur = Math.max(1, Math.min(secToFrames(sc.end, fps), from + Math.round(fps * 2.5)) - from);
        return (
          <Sequence key={`s${i}`} from={from} durationInFrames={dur} name={`scene title ${i + 1}`} layout="none">
            <SceneCard text={text} len={dur} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
      {o.lowerThirds.map((lt, i) => {
        const from = secToFrames(lt.start, fps);
        const dur = Math.max(1, secToFrames(lt.end, fps) - from);
        return (
          <Sequence key={`l${i}`} from={from} durationInFrames={dur} name={`lower third ${i + 1}`} layout="none">
            <LowerThirdCard text={lt.text} sub={lt.sub} len={dur} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const useInOut = (len: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 160 } });
  const fade = Math.min(8, Math.floor(len / 3));
  const exit = fade > 0 ? interpolate(frame, [len - fade, len], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  return { enter, exit };
};

const LowerThirdCard: React.FC<{ text: string; sub?: string; len: number; o: Options; fontFamily: string }> = ({
  text,
  sub,
  len,
  o,
  fontFamily,
}) => {
  const { width, height } = useVideoConfig();
  const { enter, exit } = useInOut(len);
  const short = Math.min(width, height);
  const size = Math.round(short * 0.05);
  const portrait = height > width;
  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "flex-start",
        padding: `0 0 ${height * (portrait ? 0.26 : 0.1)}px ${width * 0.06}px`,
      }}
    >
      <div style={{ opacity: exit, transform: `translateX(${(1 - enter) * -width * 0.08}px)` }}>
        <div
          style={{
            display: "inline-block",
            background: o.accent,
            color: "#111",
            fontFamily,
            fontWeight: 800,
            fontSize: size,
            padding: `${size * 0.2}px ${size * 0.45}px`,
            whiteSpace: "pre-wrap",
          }}
        >
          {text}
        </div>
        {sub ? (
          <div
            style={{
              background: "rgba(0,0,0,0.7)",
              color: o.textColor,
              fontFamily,
              fontWeight: 500,
              fontSize: Math.round(size * 0.62),
              padding: `${size * 0.16}px ${size * 0.45}px`,
              whiteSpace: "pre-wrap",
              width: "fit-content",
              opacity: interpolate(enter, [0.4, 1], [0, 1], { extrapolateLeft: "clamp" }),
            }}
          >
            {sub}
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

const SceneCard: React.FC<{ text: string; len: number; o: Options; fontFamily: string }> = ({ text, len, o, fontFamily }) => {
  const { width, height } = useVideoConfig();
  const { enter, exit } = useInOut(len);
  const size = Math.round(Math.min(width, height) * 0.08);
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", background: `rgba(0,0,0,${0.35 * exit})` }}>
      <div
        style={{
          color: o.textColor,
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          maxWidth: width * 0.84,
          textAlign: "center",
          whiteSpace: "pre-wrap",
          textWrap: "balance",
          opacity: Math.min(enter, exit),
          transform: `scale(${0.9 + 0.1 * enter})`,
          textShadow: "0 4px 24px rgba(0,0,0,0.6)",
        }}
      >
        {text}
        <div style={{ height: Math.max(3, size * 0.06), background: o.accent, marginTop: size * 0.2, transform: `scaleX(${enter})` }} />
      </div>
    </AbsoluteFill>
  );
};
