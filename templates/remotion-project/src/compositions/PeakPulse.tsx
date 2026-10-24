import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { Props, outputFrame, resolveOptions, secToFrames } from "../timeline";

/**
 * PeakPulse: the source, full length, with motion driven by measurements instead of guesses --
 * a frame-edge glow that hits on each audio peak ffmpeg-skill found (scaled by its loudness),
 * a tick at every scene cut, and a progress bar.
 */
export const PeakPulse: React.FC<Props> = (props) => {
  const { timeline, options, overlay } = props;
  const o = resolveOptions(options);
  const frame = useCurrentFrame();
  const { fps, width, height, durationInFrames } = useVideoConfig();

  const maxRms = Math.max(1e-6, ...timeline.peaks.map((p) => p.rms));
  // Strongest decaying hit among peaks at or before this frame.
  let hit = 0;
  for (const p of timeline.peaks) {
    const pf = secToFrames(p.time, fps);
    if (pf > frame) continue;
    const age = frame - pf;
    const decay = Math.exp(-age / (fps * 0.18));
    hit = Math.max(hit, decay * (p.rms / maxRms));
  }
  const glow = Math.round(Math.min(width, height) * 0.06 * o.pulse * hit);

  const cuts = timeline.scenes.slice(1).map((s) => secToFrames(s.start, fps));
  const flash = cuts.reduce((m, cf) => {
    const age = frame - cf;
    return age >= 0 && age < fps * 0.25 ? Math.max(m, 1 - age / (fps * 0.25)) : m;
  }, 0);

  const progress = interpolate(frame, [0, Math.max(1, durationInFrames - 1)], [0, 1], { extrapolateRight: "clamp" });
  const barH = Math.max(4, Math.round(height * 0.008));

  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {/* In overlay mode the source (and its slight zoom on peaks) is left to the composite step. */}
      {overlay ? null : <SourceVideo source={timeline.source} fit={outputFrame(props).fit} style={{ transform: `scale(${1 + 0.02 * o.pulse * hit})` }} />}
      <AbsoluteFill style={{ boxShadow: `inset 0 0 ${glow * 2}px ${glow}px ${o.accent}`, opacity: 0.85, pointerEvents: "none" }} />
      {flash > 0 ? <AbsoluteFill style={{ backgroundColor: "white", opacity: 0.18 * flash }} /> : null}
      {o.progressBar ? (
        <AbsoluteFill style={{ justifyContent: "flex-end" }}>
          <div style={{ position: "relative", height: barH, background: "rgba(255,255,255,0.18)" }}>
            <div style={{ width: `${progress * 100}%`, height: "100%", background: o.accent }} />
            {cuts.map((cf, i) => (
              <div
                key={i}
                style={{
                  position: "absolute",
                  left: `${(cf / Math.max(1, durationInFrames - 1)) * 100}%`,
                  top: -barH,
                  width: Math.max(2, Math.round(barH / 2)),
                  height: barH * 3,
                  background: o.textColor,
                }}
              />
            ))}
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
};
