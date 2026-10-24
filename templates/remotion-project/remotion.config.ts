// Remotion CLI settings for projects made by remotion-ffmpeg-skill.
// render.py passes codec, props and output on the command line; only defaults live here.
import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
