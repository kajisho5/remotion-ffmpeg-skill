import React from "react";
import { Composition, type CalculateMetadataFunction } from "remotion";
import { Captioned } from "./compositions/Captioned";
import { Jumpcut } from "./compositions/Jumpcut";
import { PeakPulse } from "./compositions/PeakPulse";
import { SAMPLE_TIMELINE, fullLengthFrames, jumpcutFrames, type Props, type Timeline } from "./timeline";

// Frame size, fps and length come from the measured timeline, never from constants:
// the composition is exactly as long and as large as the source ffmpeg-skill probed.
const metadataFrom =
  (frames: (t: Timeline) => number): CalculateMetadataFunction<Props> =>
  ({ props }) => ({
    durationInFrames: frames(props.timeline),
    fps: props.timeline.source.fps,
    width: props.timeline.source.width,
    height: props.timeline.source.height,
  });

const defaultProps: Props = { timeline: SAMPLE_TIMELINE, options: {} };
const base = { durationInFrames: 240, fps: 30, width: 1280, height: 720, defaultProps };

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Captioned" component={Captioned} {...base} calculateMetadata={metadataFrom(fullLengthFrames)} />
    <Composition id="Jumpcut" component={Jumpcut} {...base} calculateMetadata={metadataFrom(jumpcutFrames)} />
    <Composition id="PeakPulse" component={PeakPulse} {...base} calculateMetadata={metadataFrom(fullLengthFrames)} />
  </>
);
