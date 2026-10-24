"""Sparse overlay rendering: draw only the frames where something shows, then lay each drawn stretch
back at its own time with ffmpeg-skill `overlay.py --place`.

Remotion renders every frame in a browser, so a 30-minute talk with captions on a third of it spends
two thirds of the render on empty transparent frames. Here the shown intervals (caption cues, or
Titled's lower thirds and scene cards) are grouped into stretches (intervals closer than `merge_gap`
seconds share one), the stretches are packed back to back in a short timeline, Remotion draws that,
and overlay.py places each stretch over the untouched source. Everything moves by whole frames, so
the result matches the full-length overlay frame for frame.
"""
import copy
from typing import Any, Dict, List, Optional, Tuple

from _common import sec_to_frames

SPARSE_COMPOSITIONS = ("Captioned", "Karaoke", "Titled")
# One overlay filter per stretch: past this many, the filter chain costs more than it saves.
MAX_STRETCHES = 400
# Titled.tsx: a scene card lasts until the scene ends, at most this long.
SCENE_CARD_SECONDS = 2.5

Layout = List[Tuple[int, int, int]]  # (packed_first_frame, length_frames, source_first_frame)


def _scene_card(sc: Dict[str, Any], fps: float) -> Tuple[int, int]:
    """[from, end) frames of a scene card, as Titled.tsx computes them."""
    s = sec_to_frames(sc["start"], fps)
    return s, s + max(1, min(sec_to_frames(sc["end"], fps), s + sec_to_frames(SCENE_CARD_SECONDS, fps)) - s)


def drawn_intervals(comp: str, timeline: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> List[Tuple[int, int]]:
    """[from, end) frames in which the composition draws anything (its Sequences)."""
    fps = float(timeline["source"]["fps"])
    o = options or {}
    out: List[Tuple[int, int]] = []
    if comp in ("Captioned", "Karaoke"):
        for c in timeline.get("captions") or []:
            s = sec_to_frames(c["start"], fps)
            out.append((s, s + max(1, sec_to_frames(c["end"], fps) - s)))
    elif comp == "Titled":
        titles = o.get("sceneTitles") or []
        for i, sc in enumerate(timeline.get("scenes") or []):
            if i < len(titles) and titles[i]:
                out.append(_scene_card(sc, fps))
        for lt in o.get("lowerThirds") or []:
            s = sec_to_frames(lt["start"], fps)
            out.append((s, s + max(1, sec_to_frames(lt["end"], fps) - s)))
    return out


def stretches(intervals: List[Tuple[int, int]], total: int, merge_gap_frames: int) -> List[Tuple[int, int]]:
    """Sorted, merged [from, end) stretches inside [0, total); intervals closer than the gap merge."""
    out: List[List[int]] = []
    for s, e in sorted(intervals):
        s = max(0, min(s, total - 1))
        e = min(total, max(e, s + 1))
        if out and s <= out[-1][1] + merge_gap_frames:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def plan_stretches(comp: str, timeline: Dict[str, Any], options: Optional[Dict[str, Any]], merge_gap: float) -> List[Tuple[int, int]]:
    fps = float(timeline["source"]["fps"])
    total = sec_to_frames(float(timeline["source"]["duration"]), fps)
    return stretches(drawn_intervals(comp, timeline, options), total, sec_to_frames(merge_gap, fps))


def caption_stretches(timeline: Dict[str, Any], merge_gap: float) -> List[Tuple[int, int]]:
    return plan_stretches("Captioned", timeline, None, merge_gap)


def pack(timeline: Dict[str, Any], spans: List[Tuple[int, int]],
         options: Optional[Dict[str, Any]] = None) -> Tuple[Dict[str, Any], Dict[str, Any], Layout]:
    """The timeline and options with the stretches back to back (one blank frame between them), and
    the layout that puts each stretch back."""
    fps = float(timeline["source"]["fps"])
    layout: Layout = []
    p = 0
    for s, e in spans:
        layout.append((p, e - s, s))
        p += (e - s) + 1

    def offset(t: float) -> Optional[int]:
        """Whole frames to move a time by: its stretch's source start minus its packed start. Only
        whole frames, so a word timed between two frames keeps exactly where it falls in its frame."""
        f = sec_to_frames(t, fps)
        for pp, n, s in layout:
            if s <= f <= s + n:
                return s - pp
        return None

    def moved(items: List[Dict[str, Any]], anchor) -> List[Dict[str, Any]]:
        out = []
        for c in items:
            k = offset(anchor(c))
            if k is not None:
                out.append({**c, "start": c["start"] - k / fps, "end": c["end"] - k / fps})
        return out

    tl = copy.deepcopy(timeline)
    tl["source"]["duration"] = packed_frames(layout) / fps
    tl["captions"] = moved(timeline.get("captions") or [], lambda c: c["start"])
    # a word belongs where Karaoke puts it: by its midpoint
    tl["words"] = moved(timeline.get("words") or [], lambda w: (w["start"] + w["end"]) / 2)
    opts = copy.deepcopy(options or {})
    if opts.get("lowerThirds"):
        opts["lowerThirds"] = moved(opts["lowerThirds"], lambda lt: lt["start"])
    # Scene cards are matched to sceneTitles by index, so every scene keeps its place in the list:
    # a titled one moves with its stretch and keeps its card length; the rest draw nothing anyway.
    titles = opts.get("sceneTitles") or []
    scenes = []
    for i, sc in enumerate(timeline.get("scenes") or []):
        if i < len(titles) and titles[i]:
            s, e = _scene_card(sc, fps)
            k = offset(sc["start"])
            if k is not None:
                scenes.append({"start": (s - k) / fps, "end": (e - k) / fps})
                continue
        scenes.append({"start": 0.0, "end": 1.0 / fps})
    tl["scenes"] = scenes if any(titles) else []
    # nothing else is drawn; measurements on the source clock would only mislead
    for key in ("silences", "speech", "peaks", "highlights", "clips"):
        tl[key] = []
    tl["beats"] = None
    return tl, opts, layout


def place_args(layout: Layout, fps: float) -> List[str]:
    """overlay.py --place arguments. Range edges sit half a frame inside the stretch, so the blank
    frame between stretches is never picked up whatever the float rounding of a timestamp."""
    args: List[str] = []
    for pp, n, s in layout:
        a = max(0.0, (pp - 0.5) / fps)
        b = (pp + n - 0.5) / fps
        args += ["--place", f"{a:.6f}-{b:.6f}@{s / fps:.6f}"]
    return args


def packed_frames(layout: Layout) -> int:
    return max(1, sum(n for _, n, _ in layout) + len(layout) - 1)
