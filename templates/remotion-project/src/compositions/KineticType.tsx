import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { Props, showLayer, fontStack, outputFrame, resolveOptions, secToFrames, type KineticLine, type Options } from "../timeline";

/**
 * KineticType: the caption cues' words (or CJK characters) entering one by one at the times analyze.py
 * --kinetic scheduled from a measurement -- each word's own time from a speech engine (--words) or the next
 * measured beat (--beats). Nothing here makes up a time: a unit is invisible before the frame of its `start`
 * and visible on it. Units keep their place in the line while hidden, so nothing reflows as they enter.
 * kineticStyle: pop (scale), wipe (a mask from the left), tracking (characters closing in), rise.
 * kineticReveal "char": a unit's characters follow each other kineticStagger seconds apart from its start.
 */
export const KineticType: React.FC<Props> = (props) => {
  const { timeline, options, font, overlay } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const lines = timeline.kinetic?.lines ?? [];
  const line = lines.find((ln) => frame >= secToFrames(ln.start, fps) && frame < secToFrames(ln.end, fps));
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : <SourceVideo background={o.background} source={timeline.source} fit={outputFrame(props).fit} />}
      {line && showLayer(props, "text") ? <Line line={line} o={o} fontFamily={family} /> : null}
    </AbsoluteFill>
  );
};

/** Frames a unit (or character) takes to settle once it has started. */
const ENTER_SECONDS = 0.18;

const Line: React.FC<{ line: KineticLine; o: Options; fontFamily: string }> = ({ line, o, fontFamily }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const size = Math.round(Math.min(width, height) * o.kineticSize);
  const enter = Math.max(1, Math.round(fps * ENTER_SECONDS));
  const endFrame = secToFrames(line.end, fps);
  const fade = Math.min(6, Math.max(0, endFrame - secToFrames(line.start, fps) - 1));
  const exit = fade > 0 ? interpolate(frame, [endFrame - fade, endFrame], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  const text = line.units.map((u) => u.text).join("");
  const lang = /[぀-ヿ]/.test(text) ? "ja" : /[가-힯]/.test(text) ? "ko" : undefined;
  const starts = line.units.map((u) => secToFrames(u.start, fps));
  // The unit that started last is the current one: it takes the accent colour.
  let current = -1;
  starts.forEach((s, i) => {
    if (s <= frame) current = i;
  });
  // progress 0 before the start frame, > 0 on it, 1 once settled
  const progress = (start: number): number => (frame < start ? 0 : Math.min(1, (frame - start + 1) / enter));
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center" }}>
      <div
        lang={lang}
        style={{
          maxWidth: width * 0.88,
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "baseline",
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          lineHeight: 1.25,
          color: o.textColor,
          opacity: exit,
        }}
      >
        {line.units.map((u, i) => {
          const chars = Array.from(u.text);
          const charStart = (j: number) =>
            o.kineticReveal === "char" ? secToFrames(u.start + j * o.kineticStagger, fps) : starts[i];
          return (
            <span
              key={i}
              style={{
                display: "inline-flex",
                whiteSpace: "pre",
                marginLeft: u.gap ? "0.28em" : 0,
                color: i === current ? o.accent : o.textColor,
              }}
            >
              {chars.map((ch, j) => {
                const p = progress(Math.max(starts[i], charStart(j)));
                return (
                  <span key={j} style={{ display: "inline-block", ...enterStyle(o.kineticStyle, p, j, chars.length) }}>
                    {ch}
                  </span>
                );
              })}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const ease = (p: number): number => 1 - Math.pow(1 - p, 3);

/** How a character looks at progress p (0 = not started: drawn invisibly so the line keeps its layout). */
const enterStyle = (style: Options["kineticStyle"], p: number, j: number, n: number): React.CSSProperties => {
  if (p <= 0) return { opacity: 0 };
  const e = ease(p);
  switch (style) {
    case "wipe":
      return { clipPath: `inset(0 ${(1 - e) * 100}% 0 0)` };
    case "tracking": {
      // characters start spread out from the unit's centre and close in: a transform, so nothing reflows
      const offset = (j - (n - 1) / 2) * 0.35 * (1 - e);
      return { opacity: Math.min(1, 0.35 + e), transform: `translateX(${offset}em)` };
    }
    case "rise":
      return { opacity: Math.min(1, 0.25 + e), transform: `translateY(${(1 - e) * 0.5}em)` };
    case "pop":
    default:
      return { opacity: Math.min(1, 0.4 + e), transform: `scale(${1 + 0.6 * (1 - e)})` };
  }
};
