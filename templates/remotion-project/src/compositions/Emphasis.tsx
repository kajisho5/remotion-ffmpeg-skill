import React from "react";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SourceVideo } from "../lib/SourceVideo";
import { useStagedFont } from "../lib/useStagedFont";
import { captionMarginPx } from "./Captioned";
import {
  Props,
  fontStack,
  outputFrame,
  resolveOptions,
  secToFrames,
  type Bubble,
  type Caption,
  type CommentCard,
  type Emphasis as EmphasisWord,
  type Options,
} from "../timeline";

/**
 * Emphasis: YouTube-style captions. Each caption cue shows as written; the words analyze.py --emphasis
 * placed on it pop, take the accent colour or get an accent box from the time the speech engine measured
 * them to the end of the cue. Speech bubbles and comment-style cards (the user's text, options `bubbles`
 * and `comments`) show at their own times. Nothing here chooses or rewrites a word.
 */
export const Emphasis: React.FC<Props> = (props) => {
  const { timeline, options, font, overlay } = props;
  useStagedFont(font);
  const o = resolveOptions(options);
  const family = fontStack(o, font);
  const { fps } = useVideoConfig();
  const words = timeline.words ?? [];
  const emphasis = timeline.emphasis ?? [];
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : <SourceVideo source={timeline.source} fit={outputFrame(props).fit} />}
      {timeline.captions.map((c, i) => {
        const from = secToFrames(c.start, fps);
        const dur = Math.max(1, secToFrames(c.end, fps) - from);
        // The cue's words by midpoint, as analyze.py placed the emphasis on them; [global index, word].
        const own = words
          .map((w, gi) => [gi, w] as [number, Caption])
          .filter(([, w]) => (w.start + w.end) / 2 >= c.start && (w.start + w.end) / 2 <= c.end);
        return (
          <Sequence key={`c${i}`} from={from} durationInFrames={dur} name={`cue ${i + 1}`} layout="none">
            <EmphasisCue
              cue={c}
              from={from}
              words={own}
              emphasis={emphasis.filter((e) => e.cue === i)}
              len={dur}
              o={o}
              fontFamily={family}
            />
          </Sequence>
        );
      })}
      {o.bubbles.map((b, i) => {
        const from = secToFrames(b.start, fps);
        const dur = Math.max(1, secToFrames(b.end, fps) - from);
        return (
          <Sequence key={`b${i}`} from={from} durationInFrames={dur} name={`bubble ${i + 1}`} layout="none">
            <SpeechBubble bubble={b} len={dur} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
      {o.comments.map((c, i) => {
        const from = secToFrames(c.start, fps);
        const dur = Math.max(1, secToFrames(c.end, fps) - from);
        // Cards showing at once stack downwards in the order given.
        const slot = o.comments.slice(0, i).filter((p) => p.start < c.end && p.end > c.start).length;
        return (
          <Sequence key={`m${i}`} from={from} durationInFrames={dur} name={`comment ${i + 1}`} layout="none">
            <Comment card={c} slot={slot} len={dur} o={o} fontFamily={family} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const langOf = (text: string): string | undefined =>
  /[぀-ヿ㐀-鿿]/.test(text) ? "ja" : /[가-힯]/.test(text) ? "ko" : undefined;

const useInOut = (len: number) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 14, stiffness: 180, mass: 0.6 } });
  const fade = Math.min(6, Math.floor(len / 3));
  const exit = fade > 0 ? interpolate(frame, [len - fade, len], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) : 1;
  return { frame, enter, exit };
};

const EmphasisCue: React.FC<{
  cue: Caption;
  from: number;
  words: [number, Caption][];
  emphasis: EmphasisWord[];
  len: number;
  o: Options;
  fontFamily: string;
}> = ({ cue, from, words, emphasis, len, o, fontFamily }) => {
  const { fps, width, height } = useVideoConfig();
  const { frame, enter, exit } = useInOut(len);
  const size = Math.round(Math.min(width, height) * o.captionSize * 1.1);
  // Source time of this frame, nudged by a microsecond as in Karaoke so a word starting exactly on a
  // frame shows on that frame.
  const now = (from + frame) / fps + 1e-6;
  const firstOf = new Map(emphasis.map((e) => [e.words[0], e]));
  const parts: React.ReactNode[] = [];
  for (let k = 0; k < words.length; k++) {
    const [gi, w] = words[k];
    const e = firstOf.get(gi);
    const lead = w.text.match(/^\s*/)?.[0] ?? "";
    if (!e) {
      parts.push(<React.Fragment key={k}>{w.text}</React.Fragment>);
      continue;
    }
    // The run of the cue's own words the emphasis covers; its text is a prefix of that run (what is left
    // is the last word's trailing punctuation, drawn plain).
    let run = w.text.slice(lead.length);
    while (k + 1 < words.length && words[k + 1][0] <= e.words[1]) {
      k += 1;
      run += words[k][1].text;
    }
    const rest = run.slice(e.text.length);
    parts.push(
      <React.Fragment key={k}>
        {lead}
        <Emphasised text={run.slice(0, e.text.length)} style={e.style ?? o.emphasisStyle} at={e.start} now={now} o={o} />
        {rest}
      </React.Fragment>,
    );
  }
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: captionMarginPx(o, width, height) }}>
      <div
        lang={langOf(cue.text)}
        style={{
          maxWidth: width * 0.88,
          padding: `${size * 0.25}px ${size * 0.55}px`,
          borderRadius: size * 0.3,
          background: "rgba(0,0,0,0.6)",
          color: o.textColor,
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          lineHeight: 1.45,
          textAlign: "center",
          whiteSpace: "pre-wrap",
          textWrap: "balance",
          opacity: Math.min(enter, exit),
          transform: `translateY(${(1 - enter) * size * 0.5}px)`,
        }}
      >
        {words.length === 0 ? cue.text : parts}
      </div>
    </AbsoluteFill>
  );
};

/** One emphasised word: plain until it is spoken, then popped, coloured or boxed until the cue ends. */
const Emphasised: React.FC<{ text: string; style: "pop" | "color" | "box"; at: number; now: number; o: Options }> = ({
  text,
  style,
  at,
  now,
  o,
}) => {
  const on = now >= at;
  const t = now - at;
  const scale = !on
    ? 1
    : style === "pop"
      ? interpolate(t, [0, 0.08, 0.25], [1, 1.35, 1.15], { extrapolateRight: "clamp" })
      : interpolate(t, [0, 0.06, 0.18], [1, 1.12, 1], { extrapolateRight: "clamp" });
  const boxed = on && style === "box";
  return (
    <span
      style={{
        display: "inline-block",
        transform: `scale(${scale})`,
        transformOrigin: "50% 70%",
        color: on ? (boxed ? "#111111" : o.accent) : o.textColor,
        background: boxed ? o.accent : "transparent",
        borderRadius: "0.18em",
        padding: "0 0.12em",
        margin: "0 -0.12em",
        textShadow: on && style === "pop" ? "0 0.06em 0 rgba(0,0,0,0.65)" : "none",
      }}
    >
      {text}
    </span>
  );
};

/** A speech bubble in the upper part of the frame, its tail pointing down-left or down-right. */
const SpeechBubble: React.FC<{ bubble: Bubble; len: number; o: Options; fontFamily: string }> = ({ bubble, len, o, fontFamily }) => {
  const { width, height } = useVideoConfig();
  const { enter, exit } = useInOut(len);
  const size = Math.round(Math.min(width, height) * o.captionSize);
  const right = bubble.side === "right";
  const tail = size * 0.6;
  return (
    <AbsoluteFill
      style={{ justifyContent: "flex-start", alignItems: right ? "flex-end" : "flex-start", padding: `${height * 0.1}px ${width * 0.08}px` }}
    >
      <div
        lang={langOf(bubble.text)}
        style={{
          position: "relative",
          maxWidth: width * 0.5,
          padding: `${size * 0.45}px ${size * 0.7}px`,
          borderRadius: size * 0.9,
          background: "#ffffff",
          color: "#111111",
          fontFamily,
          fontWeight: 800,
          fontSize: size,
          lineHeight: 1.3,
          whiteSpace: "pre-wrap",
          boxShadow: `0 ${size * 0.12}px ${size * 0.4}px rgba(0,0,0,0.35)`,
          opacity: exit,
          transform: `scale(${enter})`,
          transformOrigin: right ? "85% 100%" : "15% 100%",
        }}
      >
        {bubble.text}
        <div
          style={{
            position: "absolute",
            bottom: -tail * 0.8,
            [right ? "right" : "left"]: size * 0.9,
            width: 0,
            height: 0,
            borderLeft: `${tail * 0.5}px solid transparent`,
            borderRight: `${tail * 0.5}px solid transparent`,
            borderTop: `${tail}px solid #ffffff`,
            transform: `skewX(${right ? 25 : -25}deg)`,
          }}
        />
      </div>
    </AbsoluteFill>
  );
};

/** A comment-style card sliding in at the top left (a live-chat / comment look), cards at once stacked. */
const Comment: React.FC<{ card: CommentCard; slot: number; len: number; o: Options; fontFamily: string }> = ({
  card,
  slot,
  len,
  o,
  fontFamily,
}) => {
  const { width, height } = useVideoConfig();
  const { enter, exit } = useInOut(len);
  const size = Math.round(Math.min(width, height) * o.captionSize * 0.7);
  const avatar = size * 2;
  return (
    <AbsoluteFill style={{ justifyContent: "flex-start", alignItems: "flex-start", padding: `${height * 0.06}px ${width * 0.04}px` }}>
      <div
        lang={langOf(card.text)}
        style={{
          marginTop: slot * size * 4.2,
          display: "flex",
          alignItems: "center",
          gap: size * 0.6,
          maxWidth: width * 0.55,
          padding: `${size * 0.5}px ${size * 0.8}px ${size * 0.5}px ${size * 0.5}px`,
          borderRadius: size * 0.6,
          background: "rgba(255,255,255,0.94)",
          color: "#111111",
          fontFamily,
          fontSize: size,
          lineHeight: 1.3,
          boxShadow: `0 ${size * 0.1}px ${size * 0.4}px rgba(0,0,0,0.3)`,
          opacity: Math.min(enter, exit),
          transform: `translateX(${(1 - enter) * -width * 0.1}px)`,
        }}
      >
        <div
          style={{
            flex: "none",
            width: avatar,
            height: avatar,
            borderRadius: "50%",
            background: o.accent,
            color: "#111111",
            fontWeight: 800,
            fontSize: size * 1.1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {card.author ? Array.from(card.author.trim())[0] ?? "" : ""}
        </div>
        <div style={{ whiteSpace: "pre-wrap" }}>
          {card.author ? <div style={{ fontWeight: 800, fontSize: size * 0.85, opacity: 0.7 }}>{card.author}</div> : null}
          <div style={{ fontWeight: 600 }}>{card.text}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
