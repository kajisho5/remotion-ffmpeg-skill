# 0010. Style presets are option bundles; layers are one group per file

2026-11-27. ECOSYSTEM_ROADMAP step 11.

## Context

A caller wants to set a tone in one word. An editor wants to rebuild the graphics in After Effects or an NLE. The existing `--overlay --keep-graphics` gives a single transparent layer that holds every group.

## Decision

- `--style swiss|minimal|neon|glitch|wafu|corporate` on render.py, still.py and pipeline.py.
  - Each style is a bundle of ordinary options (`scripts/_looks.py` STYLES): colours, font stack, background, caption size, the new `captionBox`, and the kinetic and visualizer styles.
  - The order is style, then `--brand`, then `--options`. Each wins key by key over the one before, so a brand kit's colours and font always beat a style's.
  - A style adds no drawing code. Every key it sets is an option that the options check validates. A unit test checks each style against that validation.
  - `wafu` is a Japanese look and is opt-in like the others; nothing picks it by default.
- `captionBox` (Captioned, Karaoke, Emphasis): the caption box colour. `swiss` and `wafu` need it, because their dark text on the default dark box was unreadable. `null` keeps the dark box.
- `render.py --layers` (Captioned, Karaoke, Titled, Emphasis, KineticType):
  - Each composition draws only `props.layer` when it is set (`showLayer` in `src/timeline.ts`). render.py renders the composite as usual, then each group of `LAYER_GROUPS` in overlay mode: transparent ProRes 4444, PNG frames, full frame.
  - Each layer is probed with ffmpeg-skill (frame count, size, alpha pixel format).
  - The manifest `<output>.layers.json` (`remotion-ffmpeg-skill/layers@1`) gives the base, the stacking order, each layer's position (full frame at 0,0) and the times it draws. The times are computed by the same rules as the Sequences (as `_sparse.py` does for `--sparse`).
  - A group that shows nothing gets no file, and its manifest entry says why.
  - Not with `--overlay`, `--sparse`, `--fast` or `--frames`. Not for compositions that change the picture itself (Jumpcut, Highlights, BeatMontage, Pip) or that are one drawing (PeakPulse, Visualizer, ThreeScene).
- The layers are full frame, not cropped to the graphic's bounds. A crop would need the drawn pixels measured, and a full frame lines up in any editor at 0,0.

## Consequences

- The contract changes additively. render, still and pipeline gain `style`. render gains `layers` (`layers` in its result and dry-run plan; its `writes` string is unchanged). The options gain `captionBox`, and the props gain `layer`.
- Measured (`test_integration.StylesAndLayers`, 640x360 blank, 8 s):
  - Each of the six styles renders a still, and the six stills all differ.
  - Emphasis with captions, a bubble and a comment wrote three layers. Stacked over the background in order, they match the composite at 53.5 dB or better on every frame (58.8 dB on average). The stated bound is 45 dB.
- Over a detailed video source, the composite itself is a re-encode (JPEG frames, H.264). It differs from the original pixels by about 29 dB on a lavfi test pattern, whatever the layers do. The bound is therefore measured on a flat background, where only the layers can differ.
