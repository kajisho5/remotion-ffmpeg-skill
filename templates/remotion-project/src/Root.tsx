import React from "react";
import { Composition, type CalculateMetadataFunction } from "remotion";
import { Captioned } from "./compositions/Captioned";
import { Jumpcut } from "./compositions/Jumpcut";
import { PeakPulse } from "./compositions/PeakPulse";
import { SAMPLE_TIMELINE, fullLengthFrames, jumpcutFrames, outputFrame, type Props, type Timeline } from "./timeline";

// Length and fps come from the measured timeline, never from constants; the frame is the
// source's probed size unless render.py was given another shape (--aspect).
const metadataFrom =
  (frames: (t: Timeline) => number): CalculateMetadataFunction<Props> =>
  ({ props }) => {
    const f = outputFrame(props);
    return { durationInFrames: frames(props.timeline), fps: props.timeline.source.fps, width: f.width, height: f.height };
  };

const defaultProps: Props = { timeline: SAMPLE_TIMELINE, options: {}, frame: null, font: null };
const base = { durationInFrames: 240, fps: 30, width: 1280, height: 720, defaultProps };

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Captioned" component={Captioned} {...base} calculateMetadata={metadataFrom(fullLengthFrames)} />
    <Composition id="Jumpcut" component={Jumpcut} {...base} calculateMetadata={metadataFrom(jumpcutFrames)} />
    <Composition id="PeakPulse" component={PeakPulse} {...base} calculateMetadata={metadataFrom(fullLengthFrames)} />
  </>
);
