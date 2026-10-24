"""Sparse overlay rendering: draw only the frames where captions show, then lay each drawn stretch
back at its own time with ffmpeg-skill `overlay.py --place`.

Remotion renders every frame in a browser, so a 30-minute talk with captions on a third of it spends
two thirds of the render on empty transparent frames. Here the caption cues are grouped into
stretches (cues closer than `merge_gap` seconds share one), the stretches are packed back to back
in a short timeline, Remotion draws that, and overlay.py places each stretch over the untouched
source. Frame numbers stay integers end to end, so the result matches the full-length overlay.
"""
import copy
from typing import Any, Dict, List, Optional, Tuple

from _common import sec_to_frames

SPARSE_COMPOSITIONS = ("Captioned", "Karaoke")
# One overlay filter per stretch: past this many, the filter chain costs more than it saves.
MAX_STRETCHES = 400


def caption_stretches(timeline: Dict[str, Any], merge_gap: float) -> List[Tuple[int, int]]:
    """[(first_frame, end_frame)] of the frames that show a caption, cues closer than merge_gap merged."""
    fps = float(timeline["source"]["fps"])
    total = sec_to_frames(float(timeline["source"]["duration"]), fps)
    gap = sec_to_frames(merge_gap, fps)
    cues = sorted((sec_to_frames(c["start"], fps), sec_to_frames(c["end"], fps)) for c in timeline.get("captions") or [])
    out: List[List[int]] = []
    for s, e in cues:
        # the same rule as the compositions: a cue lasts at least one frame, inside the source
        s = max(0, min(s, total - 1))
        e = min(total, max(e, s + 1))
        if out and s <= out[-1][1] + gap:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def pack(timeline: Dict[str, Any], stretches: List[Tuple[int, int]]) -> Tuple[Dict[str, Any], List[Tuple[int, int, int]]]:
    """A timeline with the stretches back to back (one blank frame between them) and, per stretch,
    (packed_first_frame, length_frames, source_first_frame)."""
    fps = float(timeline["source"]["fps"])
    layout: List[Tuple[int, int, int]] = []
    p = 0
    for s, e in stretches:
        layout.append((p, e - s, s))
        p += (e - s) + 1
    packed_frames = max(1, p - 1)

    def offset(t: float) -> Optional[int]:
        """Whole frames to move a time by: its stretch's source start minus its packed start. Only
        whole frames, so a word timed between two frames keeps exactly where it falls in its frame."""
        f = sec_to_frames(t, fps)
        for pp, n, s in layout:
            if s <= f <= s + n:
                return s - pp
        return None

    out = copy.deepcopy(timeline)
    out["source"]["duration"] = packed_frames / fps
    for key in ("captions", "words"):
        moved = []
        for c in timeline.get(key) or []:
            # a word belongs where Karaoke puts it: by its midpoint
            k = offset(c["start"] if key == "captions" else (c["start"] + c["end"]) / 2)
            if k is not None:
                moved.append({**c, "start": c["start"] - k / fps, "end": c["end"] - k / fps})
        out[key] = moved
    # Captioned and Karaoke draw nothing else; measurements on the source clock would only mislead.
    for k in ("scenes", "silences", "speech", "peaks", "highlights", "clips"):
        out[k] = []
    out["beats"] = None
    return out, layout


def place_args(layout: List[Tuple[int, int, int]], fps: float) -> List[str]:
    """overlay.py --place arguments. Range edges sit half a frame inside the stretch, so the blank
    frame between stretches is never picked up whatever the float rounding of a timestamp."""
    args: List[str] = []
    for pp, n, s in layout:
        a = max(0.0, (pp - 0.5) / fps)
        b = (pp + n - 0.5) / fps
        args += ["--place", f"{a:.6f}-{b:.6f}@{s / fps:.6f}"]
    return args


def packed_frames(layout: List[Tuple[int, int, int]]) -> int:
    return max(1, sum(n for _, n, _ in layout) + len(layout) - 1)
