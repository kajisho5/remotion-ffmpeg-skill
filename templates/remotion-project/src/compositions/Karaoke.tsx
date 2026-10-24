import React from "react";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { captionMarginPx } from "./Captioned";
import { Props, fontStack, outputFrame, resolveOptions, secToFrames, type Caption, type Options } from "../timeline";

/**
 * Karaoke: each caption cue with its words lit one by one at the times the speech engine measured
 * (analyze.py --words). The current word takes the accent colour and lifts, spoken words stay white,
 * words still to come are dimmed. Cues without timed words fall back to a plain caption.
 */
export const Karaoke: React.FC<Props> = (props) => {
  const { timeline, options, font, overlay } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const { fps } = useVideoConfig();
  const words = timeline.words ?? [];
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : <SourceVideo source={timeline.source} fit={outputFrame(props).fit} />}
      {timeline.captions.map((c, i) => {
        const from = secToFrames(c.start, fps);
        const dur = Math.max(1, secToFrames(c.end, fps) - from);
        // Words that belong to this cue: their midpoint falls inside it.
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

const KaraokeCue: React.FC<{ cue: Caption; words: Caption[]; len: number; o: Options; fontFamily: string }> = ({
  cue,
  words,
  len,
  o,
  fontFamily,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 180, mass: 0.6 } });
  const fade = Math.min(6, Math.floor(len / 3));
  const exit = fade > 0 ? interpolate(frame, [len - fade, len], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  const size = Math.round(Math.min(width, height) * o.captionSize * 1.1);
  const now = cue.start + frame / fps; // source time at this frame
  const lang = /[぀-ヿ]/.test(cue.text) ? "ja" : /[가-힯]/.test(cue.text) ? "ko" : undefined;
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: captionMarginPx(o, width, height) }}>
      <div
        lang={lang}
        style={{
          maxWidth: width * 0.88,
          padding: `${size * 0.25}px ${size * 0.55}px`,
          borderRadius: size * 0.3,
          background: "rgba(0,0,0,0.6)",
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          lineHeight: 1.35,
          textAlign: "center",
          whiteSpace: "pre-wrap",
          textWrap: "balance",
          opacity: Math.min(enter, exit),
          transform: `translateY(${(1 - enter) * size * 0.5}px)`,
        }}
      >
        {words.length === 0 ? (
          <span style={{ color: o.textColor }}>{cue.text}</span>
        ) : (
          words.map((w, i) => {
            const spoken = now >= w.end;
            const active = now >= w.start && now < w.end;
            // A lift, not a scale: scaling a word would grow it over the spaces beside it.
            const lift = active ? interpolate(now, [w.start, Math.min(w.end, w.start + 0.12)], [-0.12, -0.05], { extrapolateRight: "clamp" }) : 0;
            // The engine's leading space stays a plain text node between words: inside an
            // inline-block it would collapse and glue the words together.
            const lead = w.text.match(/^\s*/)?.[0] ?? "";
            return (
              <React.Fragment key={i}>
                {lead}
                <span
                  style={{
                    color: active ? o.accent : spoken ? o.textColor : "rgba(255,255,255,0.45)",
                    display: "inline-block",
                    transform: `translateY(${lift}em)`,
                    textShadow: active ? `0 0 0.35em ${o.accent}` : "none",
                  }}
                >
                  {w.text.slice(lead.length)}
                </span>
              </React.Fragment>
            );
          })
        )}
      </div>
    </AbsoluteFill>
  );
};
