import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { ThreeCanvas } from "@remotion/three";
import { SourceVideo } from "../lib/SourceVideo";
import { Props, beatTimes, outputFrame, resolveOptions, secToFrames } from "../timeline";

/** mulberry32: a small seeded generator, so the same seed always places the same particles. */
const seeded = (seed: number) => {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

/**
 * ThreeScene: a Three.js scene (@remotion/three) over the source, a function of the frame number and
 * options.seed alone -- no clock, no requestAnimationFrame, no Math.random -- so the same frame gives the same
 * pixels on one machine and GL backend (render.py --gl; doctor.py names it). A field of seeded particles drifts
 * round a centre shape while the camera orbits; the shape hits on every measured beat (or measured audio peak
 * when no beat grid was measured), with the same decay PeakPulse uses.
 */
export const ThreeScene: React.FC<Props> = (props) => {
  const { timeline, options, overlay } = props;
  const o = resolveOptions(options);
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const beats = beatTimes(timeline);
  const maxRms = Math.max(1e-6, ...timeline.peaks.map((p) => p.rms));
  const events = beats.length > 0 ? beats.map((t) => ({ t, s: 1 })) : timeline.peaks.map((p) => ({ t: p.time, s: p.rms / maxRms }));
  let hit = 0;
  for (const ev of events) {
    const f = secToFrames(ev.t, fps);
    if (f > frame) continue;
    hit = Math.max(hit, ev.s * Math.exp(-(frame - f) / (fps * 0.15)));
  }
  const count = Math.max(1, Math.min(5000, Math.round(o.threeParticles)));
  const particles = useMemo(() => {
    const rnd = seeded(o.seed);
    return Array.from({ length: count }, () => {
      const r = 2.2 + rnd() * 4;
      const theta = rnd() * Math.PI * 2;
      const y = (rnd() - 0.5) * 4;
      return { r, theta, y, speed: 0.2 + rnd() * 0.6, size: 0.02 + rnd() * 0.05 };
    });
  }, [o.seed, count]);
  const t = frame / fps;
  const cam = 0.25 * t;
  return (
    <AbsoluteFill style={{ backgroundColor: overlay ? "transparent" : "black" }}>
      {overlay ? null : <SourceVideo background={o.background} source={timeline.source} fit={outputFrame(props).fit} />}
      <ThreeCanvas
        width={width}
        height={height}
        gl={{ antialias: true, alpha: true, preserveDrawingBuffer: true }}
        camera={{ fov: 50, near: 0.1, far: 100, position: [0, 0, 9] }}
        style={{ position: "absolute", inset: 0 }}
      >
        <ambientLight intensity={0.5} />
        <directionalLight position={[4, 6, 5]} intensity={1.6} />
        {/* the "orbit": the scene turns under a fixed camera, a function of the frame */}
        <group rotation={[0.25, -cam, 0]}>
        <mesh rotation={[t * 0.6, t * 0.9, 0]} scale={1 + 0.35 * hit}>
          <icosahedronGeometry args={[1.3, 1]} />
          <meshStandardMaterial color={o.accent} emissive={o.accent} emissiveIntensity={0.15 + 0.85 * hit} flatShading />
        </mesh>
        {particles.map((p, i) => {
          const a = p.theta + t * p.speed * 0.5;
          return (
            <mesh key={i} position={[Math.cos(a) * p.r, p.y + Math.sin(t * p.speed + i) * 0.15, Math.sin(a) * p.r]}>
              <sphereGeometry args={[p.size * (1 + hit), 8, 8]} />
              <meshBasicMaterial color={o.textColor} />
            </mesh>
          );
        })}
        </group>
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
