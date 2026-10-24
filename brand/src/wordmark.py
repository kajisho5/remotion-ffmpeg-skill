#!/usr/bin/env python3
"""Outline the "remotion-ffmpeg-skill" wordmark from Inter SemiBold (SIL Open Font License 1.1).

    npm pack @fontsource/inter@5.1.0 && tar xzf fontsource-inter-5.1.0.tgz
    python3 brand/src/wordmark.py package/files/inter-latin-600-normal.woff brand/logo
"""
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

TEXT = "remotion-ffmpeg-skill"
COLOURS = {"white": "#F5F5F7", "black": "#1D1D1F"}


def main(font_path: str, out_dir: str) -> None:
    f = TTFont(font_path)
    gs, cmap, upm = f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm
    asc, desc = f["hhea"].ascent, f["hhea"].descent
    track = -0.01 * upm
    x, parts = 0.0, []
    for ch in TEXT:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (1, 0, 0, -1, x, asc)))
        if pen.getCommands():
            parts.append(pen.getCommands())
        x += gs[g].width + track
    w, h = x - track, asc - desc
    for name, colour in COLOURS.items():
        Path(out_dir, f"wordmark-{name}.svg").write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w / upm * 64:.0f}" '
            f'height="{h / upm * 64:.0f}"><title>{TEXT}</title><path fill="{colour}" d="{" ".join(parts)}"/></svg>',
            encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
