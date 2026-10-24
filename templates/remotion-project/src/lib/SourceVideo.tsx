import React from "react";
import { AbsoluteFill, Audio, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { Fit, Source } from "../timeline";

type Props = {
  source: Source;
  /** How the source fills the output frame when the shapes differ. */
  fit?: Fit;
  /** First source frame to play (composition fps = source fps). */
  trimBefore?: number;
  /** Source frame to stop at. */
  trimAfter?: number;
  style?: React.CSSProperties;
};

/**
 * The measured source as the bottom layer.
 * - video: OffthreadVideo, placed by `fit` (contain / cover / blur)
 * - audio only: a neutral placeholder picture with the audio playing under it
 * - nothing staged: the placeholder alone (Studio previews)
 */
export const SourceVideo: React.FC<Props> = ({ source, fit = "contain", trimBefore, trimAfter, style }) => {
  if (!source.src) {
    return <Placeholder label={source.name} />;
  }
  const src = staticFile(source.src);
  if (!source.has_video) {
    return (
      <AbsoluteFill style={style}>
        <Placeholder label={source.name} />
        {source.has_audio ? <Audio src={src} trimBefore={trimBefore} trimAfter={trimAfter} /> : null}
      </AbsoluteFill>
    );
  }
  const layer = (objectFit: "contain" | "cover", extra: React.CSSProperties = {}, muted = !source.has_audio) => (
    <OffthreadVideo
      src={src}
      trimBefore={trimBefore}
      trimAfter={trimAfter}
      muted={muted}
      style={{ width: "100%", height: "100%", objectFit, ...extra }}
    />
  );
  if (fit === "blur") {
    return (
      <AbsoluteFill style={style}>
        <AbsoluteFill style={{ overflow: "hidden" }}>
          {/* The background copy is silent: the foreground carries the audio once. */}
          {layer("cover", { filter: "blur(40px) brightness(0.55)", transform: "scale(1.15)" }, true)}
        </AbsoluteFill>
        <AbsoluteFill>{layer("contain")}</AbsoluteFill>
      </AbsoluteFill>
    );
  }
  return <AbsoluteFill style={style}>{layer(fit === "cover" ? "cover" : "contain")}</AbsoluteFill>;
};

const Placeholder: React.FC<{ label: string }> = ({ label }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const short = Math.min(width, height);
  const grid = Math.round(short / 12);
  return (
    <AbsoluteFill
      style={{
        backgroundImage:
          `linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px),` +
          `linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px),` +
          `linear-gradient(135deg, #1b1f2a 0%, #2b3245 100%)`,
        backgroundSize: `${grid}px ${grid}px, ${grid}px ${grid}px, 100% 100%`,
        alignItems: "center",
        justifyContent: "center",
        color: "rgba(255,255,255,0.55)",
        fontFamily: "monospace",
        fontSize: Math.round(short * 0.035),
      }}
    >
      <div>{label}</div>
      <div style={{ fontSize: Math.round(short * 0.028), marginTop: short * 0.01 }}>
        {width}x{height} · {(frame / fps).toFixed(2)}s
      </div>
    </AbsoluteFill>
  );
};
