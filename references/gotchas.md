# Gotchas

Things that went wrong while building and running this skill, and what the scripts now do about them.
Read the one you need; SKILL.md has the one-line versions.

## Frames and timing
- **Python `round()` is not JavaScript `Math.round()`.** 3.15 s × 30 fps = 94.5: Python gives 94 (half to even), the composition gives 95. render.py's expected frame count was off by one frame per half-frame boundary. Both sides now use round-half-up (`sec_to_frames`, `secToFrames`); a test pins it.
- **Count frames, not seconds.** AAC priming/padding makes a container 20–50 ms longer than its picture. render.py compares the video stream's `nb_frames` with the expected count exactly and only falls back to a duration tolerance when the container has no frame count.
- **Variable frame rate sources drift.** Remotion renders on a fixed grid; analyze.py warns on suspected VFR. Make a constant-frame-rate copy with ffmpeg-skill first.

## Files Remotion can and cannot read
- **Symlinks in `public/` 404.** Remotion's file server refuses a symlink that points outside the project. Sources and fonts are hard-linked (instant, no extra space) or copied once.
- **Remotion's CLI does not copy `public/` per render on macOS/Linux** (it links the folder into its temporary bundle); **on Windows it copies it every time.** Big sources make Windows renders slower to start.
- **Props files are named by content** (`.rfs/props-<comp>-<hash>.json`): one name per composition used to let two parallel renders overwrite each other's props.

## Picture
- **HDR / BT.2020 looks washed out.** Chrome composites in SDR. analyze.py warns; convert with ffmpeg-skill `color.py --to-sdr` first.
- **Delivery templates crop.** ffmpeg-skill's Reels / TikTok / Shorts templates fit to 9:16 by cropping, so a 16:9 render loses the edges of every caption. Render in the delivery shape (`--aspect 9:16`, or `pipeline.py --platform`, which reads the template's aspect).
- **`--overlay` is not faster.** Transparent PNG frames plus ProRes 4444 cost about what decoding the source saves (170 s vs 174 s for 30 s of 1080p30 on 2 cores). It exists for handing a graphics layer to an editing app.

## Text
- **CJK captions need a CJK font on the rendering machine**, or they render as tofu. render.py stages the font ffmpeg-skill's doctor resolves for the caption's script and loads it before the first frame; `cancelRender` stops the render if it cannot load.
- **Japanese line breaks** use `word-break: auto-phrase` (phrase boundaries) with `text-wrap: balance`; Korean gets `lang="ko"` so it is not treated as Japanese.
- **An options typo used to do nothing.** Unknown keys and wrong types are refused before rendering.

## Containers and CI
- **`remotion` packages must share one version.** The template pins them; Dependabot groups them.
- **Container memory warnings** ("Detected differing memory amounts") are noise in Docker; error extraction drops them and keeps what follows "An error occurred".
