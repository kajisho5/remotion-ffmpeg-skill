import React from "react";
import { AbsoluteFill, OffthreadVideo, Sequence, staticFile, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { Props, fontStack, outputFrame, pipFrames, resolveOptions, secToFrames } from "../timeline";
import { CaptionCard } from "./Captioned";

/**
 * Pip: the source (a screen recording, slides) with a second recording (a camera) in a corner,
 * kept in sync by the offset ffmpeg-skill measured between their audio tracks. The camera only
 * shows while it has pictures; captions from the timeline are drawn on top, as in Captioned.
 */
export const Pip: React.FC<Props> = (props) => {
  const { timeline, options, font } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const { fps, width, height, durationInFrames } = useVideoConfig();
  const pip = timeline.pip;
  const short = Math.min(width, height);
  const circle = o.pipShape === "circle";
  const w = Math.round(circle ? short * o.pipSize : width * o.pipSize);
  const h = circle ? w : Math.round((w * (pip?.height || 9)) / (pip?.width || 16));
  const margin = Math.round(short * 0.04);
  const [vert, horiz] = o.pipCorner.split("-") as ["top" | "bottom", "left" | "right"];
  const box: React.CSSProperties = {
    position: "absolute",
    width: w,
    height: h,
    [vert]: margin,
    [horiz]: margin,
    overflow: "hidden",
    borderRadius: circle ? "50%" : Math.round(short * 0.018),
    border: `${Math.max(2, Math.round(short * 0.004))}px solid ${o.accent}`,
    boxShadow: "0 8px 30px rgba(0,0,0,0.45)",
    background: "#000",
  };
  const [from, dur, trimBefore] = pip ? pipFrames(pip, fps, durationInFrames) : [0, 1, 0];
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <SourceVideo source={timeline.source} fit={outputFrame(props).fit} />
      {pip && pip.src ? (
        <Sequence from={from} durationInFrames={dur} name="camera" layout="none">
          <div style={box}>
            <OffthreadVideo
              src={staticFile(pip.src)}
              trimBefore={trimBefore}
              muted={!o.pipAudio}
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          </div>
        </Sequence>
      ) : null}
      {timeline.captions.map((c, i) => {
        const start = secToFrames(c.start, fps);
        const len = Math.max(1, secToFrames(c.end, fps) - start);
        return (
          <Sequence key={i} from={start} durationInFrames={len} name={`cue ${i + 1}`} layout="none">
            <CaptionCard text={c.text} durationInFrames={len} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
