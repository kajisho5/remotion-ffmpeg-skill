#!/usr/bin/env python3
"""Style presets and graphic layers (internal module, not a tool).

* STYLES: `--style NAME` on render.py / still.py / pipeline.py is a bundle of ordinary options (the keys of
  `--options`, references/timeline.md). The order is style, then the brand kit (`--brand`), then the `--options`
  file, each winning key by key over the one before -- a brand's colours and font always beat a style's.
* LAYER_GROUPS: what render.py --layers writes as separate transparent ProRes 4444 files, one per graphic group
  of a composition (each composition draws only `props.layer` when it is set), and the frames each group shows
  in, for the manifest. The composition files carry the same group names (a test checks they agree).
"""
from typing import Any, Dict, List, Optional, Tuple

from _common import sec_to_frames
from _sparse import CHAPTER_SECONDS, SCENE_CARD_SECONDS

_SANS = "'Noto Sans', 'Helvetica Neue', Arial, 'Noto Sans JP', 'Hiragino Sans', 'Yu Gothic', sans-serif"
_GROTESK = "'Helvetica Neue', Helvetica, Arial, 'Noto Sans', 'Noto Sans JP', 'Hiragino Sans', sans-serif"
_MINCHO = "'Noto Serif JP', 'Hiragino Mincho ProN', 'Yu Mincho', 'Noto Serif CJK JP', 'Noto Serif', serif"
_MONO = "'JetBrains Mono', 'Noto Sans Mono', Menlo, Consolas, 'Noto Sans JP', monospace"

STYLES: Dict[str, Dict[str, Any]] = {
    # red on white, a grotesk, flush and plain
    "swiss": {"accent": "#E30613", "textColor": "#111111", "background": "#F4F4F0", "fontFamily": _GROTESK,
              "captionBox": "rgba(255,255,255,0.92)",
              "captionSize": 0.05, "kineticStyle": "wipe", "kineticReveal": "unit", "visualizer": "bars"},
    # white on near-black, small and quiet
    "minimal": {"accent": "#FFFFFF", "textColor": "#E8E8E8", "background": "#101010", "fontFamily": _SANS,
                "captionSize": 0.045, "pulse": 0.3, "progressBar": False, "kineticStyle": "rise",
                "kineticReveal": "unit", "visualizer": "waveform"},
    # glowing pink and cyan on deep blue
    "neon": {"accent": "#FF2BD6", "textColor": "#7DF9FF", "background": "radial-gradient(circle, #1A0B3D 0%, #05010F 75%)",
             "fontFamily": _SANS, "pulse": 0.9, "kineticStyle": "pop", "visualizer": "radial"},
    # acid green on black, monospaced, hard cuts
    "glitch": {"accent": "#00FF66", "textColor": "#F2F2F2", "background": "#000000", "fontFamily": _MONO,
               "kineticStyle": "tracking", "kineticStagger": 0.02, "visualizer": "spectrum", "punchIn": 1.2},
    # vermilion and sumi ink on washi (Japanese, opt-in): a mincho face
    "wafu": {"accent": "#C73E3A", "textColor": "#2B2B2B", "background": "#F3EEDF", "fontFamily": _MINCHO,
             "captionBox": "rgba(251,248,240,0.92)",
             "captionSize": 0.052, "kineticStyle": "rise", "kineticReveal": "char", "kineticStagger": 0.06,
             "visualizer": "bars"},
    # navy and a calm blue, a plain sans
    "corporate": {"accent": "#2F6FDE", "textColor": "#FFFFFF", "background": "#0B1F3A", "fontFamily": _SANS,
                  "captionSize": 0.05, "pulse": 0.4, "kineticStyle": "rise", "kineticReveal": "unit",
                  "visualizer": "bars"},
}

# The graphic groups of each composition --layers can split (the order is the stacking order, bottom first).
LAYER_GROUPS: Dict[str, Tuple[str, ...]] = {
    "Captioned": ("captions",),
    "Karaoke": ("captions",),
    "Titled": ("sceneTitles", "chapters", "lowerThirds"),
    "Emphasis": ("captions", "bubbles", "comments"),
    "KineticType": ("text",),
}


def _span(start: float, end: float, fps: float) -> Tuple[int, int]:
    s = sec_to_frames(start, fps)
    return s, s + max(1, sec_to_frames(end, fps) - s)


def group_intervals(comp: str, group: str, timeline: Dict[str, Any],
                    options: Optional[Dict[str, Any]] = None) -> List[Tuple[int, int]]:
    """[from, end) frames in which `group` of `comp` draws anything (the Sequences of that group)."""
    fps = float(timeline["source"]["fps"])
    o = options or {}
    out: List[Tuple[int, int]] = []
    if group == "captions":
        out = [_span(c["start"], c["end"], fps) for c in timeline.get("captions") or []]
    elif group == "text":
        out = [(sec_to_frames(ln["start"], fps), sec_to_frames(ln["end"], fps))
               for ln in (timeline.get("kinetic") or {}).get("lines") or []]
    elif group == "sceneTitles":
        titles = o.get("sceneTitles") or []
        for i, sc in enumerate(timeline.get("scenes") or []):
            if i < len(titles) and titles[i]:
                s = sec_to_frames(sc["start"], fps)
                out.append((s, s + max(1, min(sec_to_frames(sc["end"], fps), s + sec_to_frames(SCENE_CARD_SECONDS, fps))
                                       - s)))
    elif group == "chapters":
        seconds = float(o.get("chapterSeconds", CHAPTER_SECONDS))
        for ch in (timeline.get("chapters") or []) if seconds > 0 else []:
            s = sec_to_frames(ch["start"], fps)
            out.append((s, s + max(1, min(sec_to_frames(ch["end"], fps), s + sec_to_frames(seconds, fps)) - s)))
    elif group in ("lowerThirds", "bubbles", "comments"):
        out = [_span(x["start"], x["end"], fps) for x in o.get(group) or []]
    merged: List[List[int]] = []
    for s, e in sorted(x for x in out if x[1] > x[0]):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]
