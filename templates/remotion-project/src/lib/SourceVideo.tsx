import React from "react";
import { AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Source } from "../timeline";

type Props = {
  source: Source;
  /** First source frame to show (composition fps = source fps). */
  trimBefore?: number;
  /** Source frame to stop at. */
  trimAfter?: number;
  style?: React.CSSProperties;
};

/** The measured source as the bottom layer, or a neutral placeholder when there is no picture. */
export const SourceVideo: React.FC<Props> = ({ source, trimBefore, trimAfter, style }) => {
  if (!source.src) {
    return <Placeholder label={source.name} />;
  }
  return (
    <AbsoluteFill style={style}>
      <OffthreadVideo
        src={staticFile(source.src)}
        trimBefore={trimBefore}
        trimAfter={trimAfter}
        muted={!source.has_audio}
        style={{ width: "100%", height: "100%", objectFit: "contain" }}
      />
    </AbsoluteFill>
  );
};

const Placeholder: React.FC<{ label: string }> = ({ label }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const grid = Math.round(height / 12);
  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(135deg, #1b1f2a 0%, #2b3245 100%)",
        backgroundImage:
          `linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),` +
          `linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px),` +
          `linear-gradient(135deg, #1b1f2a 0%, #2b3245 100%)`,
        backgroundSize: `${grid}px ${grid}px, ${grid}px ${grid}px, 100% 100%`,
        alignItems: "center",
        justifyContent: "center",
        color: "rgba(255,255,255,0.55)",
        fontFamily: "monospace",
        fontSize: Math.round(height * 0.035),
      }}
    >
      <div>{label}</div>
      <div style={{ fontSize: Math.round(height * 0.028), marginTop: height * 0.01 }}>
        {width}x{height} · {(frame / fps).toFixed(2)}s
      </div>
    </AbsoluteFill>
  );
};
