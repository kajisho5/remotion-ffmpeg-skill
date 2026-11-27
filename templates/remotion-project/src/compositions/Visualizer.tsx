import React from "react";
import { AbsoluteFill, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { createSmoothSvgPath, useAudioData, visualizeAudio, visualizeAudioWaveform } from "@remotion/media-utils";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { KaraokeCue } from "./Karaoke";
import { Props, beatTimes, fontStack, outputFrame, resolveOptions, secToFrames, visualizerRange, type Options } from "../timeline";

/** FFT size / 2 that visualizeAudio is asked for: 1024 samples (23 ms at 44.1 kHz), centred on the frame's time. */
const FFT_BINS = 512;

/**
 * Visualizer: the source's own audio drawn each frame (@remotion/media-utils, decoded in the browser) as bars,
 * a spectrum, radial bars or a waveform, a ring that hits on every measured beat, and the caption cues as
 * Karaoke draws them. With loopBars it is a loop: from the first measured beat over a whole number of measured
 * bars, so its last frame runs into its first. No smoothing across frames: what a frame shows is the audio
 * around that frame's time and nothing later.
 */
export const Visualizer: React.FC<Props> = (props) => {
  const { timeline, options, font, overlay } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const { fps } = useVideoConfig();
  const [start] = visualizerRange(timeline, o);
  const words = timeline.words ?? [];
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : (
        <SourceVideo background={o.background} source={timeline.source} fit={outputFrame(props).fit} trimBefore={start > 0 ? start : undefined} />
      )}
      {timeline.source.src ? <Drawing src={timeline.source.src} start={start} o={o} beats={beatTimes(timeline)} /> : null}
      {timeline.captions.map((c, i) => {
        const from = secToFrames(c.start, fps) - start;
        const dur = Math.max(1, secToFrames(c.end, fps) - secToFrames(c.start, fps));
        if (from + dur <= 0) return null;
        const own = words.filter((w) => (w.start + w.end) / 2 >= c.start && (w.start + w.end) / 2 <= c.end);
        return (
          <Sequence key={i} from={from} durationInFrames={dur} name={`cue ${i + 1}`} layout="none">
            <KaraokeCue cue={c} words={own} len={dur} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

/** Bin edges for `n` bars over FFT_BINS bins, spaced logarithmically (low frequencies get more bars). */
const edges = (n: number): number[] => {
  const out: number[] = [1];
  for (let i = 1; i <= n; i++) {
    const e = Math.round(Math.pow(FFT_BINS, i / n));
    out.push(Math.max(out[i - 1] + 1, Math.min(FFT_BINS, e)));
  }
  return out;
};

/** A magnitude as 0..1 on a 60 dB scale. */
const level = (m: number): number => Math.max(0, Math.min(1, (20 * Math.log10(Math.max(m, 1e-9)) + 60) / 60));

const Drawing: React.FC<{ src: string; start: number; o: Options; beats: number[] }> = ({ src, start, o, beats }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const audioData = useAudioData(staticFile(src));
  const sourceFrame = start + frame;
  const n = Math.max(8, Math.min(256, Math.round(o.visualizerBars)));
  // the ring: the strongest decaying hit of the measured beats at or before this frame
  let hit = 0;
  for (const b of beats) {
    const bf = secToFrames(b, fps);
    if (bf > sourceFrame) break;
    hit = Math.exp(-(sourceFrame - bf) / (fps * 0.15));
  }
  if (!audioData) return null;
  const short = Math.min(width, height);
  let values: number[];
  if (o.visualizer === "waveform") {
    values = visualizeAudioWaveform({ audioData, frame: sourceFrame, fps, windowInSeconds: 0.08, numberOfSamples: n });
  } else {
    const mags = visualizeAudio({ audioData, frame: sourceFrame, fps, numberOfSamples: FFT_BINS, smoothing: false });
    const e = edges(n);
    values = Array.from({ length: n }, (_, i) => level(Math.max(...mags.slice(e[i], e[i + 1]))));
  }
  const ring = (
    <div
      style={{
        position: "absolute",
        left: width / 2 - short * 0.12,
        top: height / 2 - short * 0.12,
        width: short * 0.24,
        height: short * 0.24,
        borderRadius: "50%",
        border: `${Math.max(2, Math.round(short * 0.012))}px solid ${o.accent}`,
        opacity: 0.35 + 0.65 * hit,
        transform: `scale(${1 + 0.25 * hit})`,
      }}
    />
  );
  if (o.visualizer === "radial") {
    const r = short * 0.16;
    return (
      <AbsoluteFill>
        {ring}
        {values.map((v, i) => {
          const len = Math.max(2, v * short * 0.24);
          const angle = (i / n) * 360;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: width / 2 - short * 0.006,
                top: height / 2,
                width: short * 0.012,
                height: len,
                background: o.textColor,
                borderRadius: short * 0.006,
                transformOrigin: "50% 0",
                transform: `rotate(${angle + 180}deg) translateY(${r}px)`,
              }}
            />
          );
        })}
      </AbsoluteFill>
    );
  }
  if (o.visualizer === "spectrum" || o.visualizer === "waveform") {
    const mid = height * 0.5;
    const amp = height * 0.3;
    const points = values.map((v, i) => ({
      x: (width * (i + 0.5)) / n,
      y: o.visualizer === "waveform" ? mid - v * amp : height * 0.85 - v * height * 0.5,
    }));
    const path = createSmoothSvgPath({ points });
    return (
      <AbsoluteFill>
        {ring}
        <svg width={width} height={height} style={{ position: "absolute" }}>
          {o.visualizer === "spectrum" ? (
            <path d={`${path} L ${points[n - 1].x} ${height * 0.85} L ${points[0].x} ${height * 0.85} Z`} fill={o.accent} fillOpacity={0.75} />
          ) : (
            <path d={path} fill="none" stroke={o.accent} strokeWidth={Math.max(2, short * 0.008)} />
          )}
        </svg>
      </AbsoluteFill>
    );
  }
  const slot = width / n;
  return (
    <AbsoluteFill>
      {ring}
      {values.map((v, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: i * slot + slot * 0.15,
            width: slot * 0.7,
            bottom: height * 0.06,
            height: Math.max(2, v * height * 0.45),
            background: i % 2 === 0 ? o.accent : o.textColor,
            borderRadius: slot * 0.2,
          }}
        />
      ))}
    </AbsoluteFill>
  );
};
