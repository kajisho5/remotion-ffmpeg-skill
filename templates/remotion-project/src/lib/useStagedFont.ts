import { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender, staticFile } from "remotion";
import type { FontAsset } from "../timeline";

/**
 * Load the font render.py staged into public/ before any frame is captured, so the first
 * frame already uses it (no fallback-font flash, no tofu). Fails the render loudly if the
 * font cannot be loaded rather than silently drawing in another font.
 */
export const useStagedFont = (font?: FontAsset | null): void => {
  const [handle] = useState(() => (font ? delayRender(`font ${font.family}`) : null));
  useEffect(() => {
    if (!font || handle === null) return;
    const face = new FontFace(font.family, `url(${staticFile(font.src)})`, { weight: "100 900" });
    face
      .load()
      .then((loaded) => {
        document.fonts.add(loaded);
        continueRender(handle);
      })
      .catch((err: unknown) => {
        cancelRender(new Error(`could not load font ${font.src}: ${String(err)}`));
      });
  }, [font, handle]);
};
