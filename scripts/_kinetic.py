#!/usr/bin/env python3
"""The KineticType schedule (internal module, not a tool): when each word (or CJK character) of the caption
cues starts, from a measurement only -- the speech engine's word timings (analyze.py --words) or the measured
beat grid (analyze.py --beats). analyze.py --kinetic writes it into the timeline as `kinetic`; the composition
draws it and computes no time of its own, so the frame a unit starts on is round(start * fps) on both sides.

Kinetic typography with no measured timing belongs to hyperframes-skill (Velisa ownership decisions O17), so
there is no fallback to evenly spread or guessed times: no usable measurement, no schedule.
"""
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

KINETIC_TIMINGS = ("auto", "words", "beats")
# A character that is never a unit of its own: it stays with the character before it.
_ATTACH = set("、。，．・：；！？!?,.)]）」』】〉》〕”’ー〜ゝゞヽヾ")


class KineticError(ValueError):
    pass


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xAC00 <= o <= 0xD7AF
            or 0xF900 <= o <= 0xFAFF or 0xFF66 <= o <= 0xFF9F)


def split_units(text: str) -> List[Tuple[str, bool]]:
    """A cue's text as (unit, space before it): words split at whitespace; a run of CJK characters (written
    without spaces) is one unit per character, punctuation and the long-vowel mark staying with the character
    before. The text itself is never changed: joining the units (a space where marked) gives it back, apart
    from runs of whitespace, which become one space."""
    out: List[Tuple[str, bool]] = []
    for ti, tok in enumerate(t for t in re.split(r"\s+", unicodedata.normalize("NFC", text)) if t):
        gap = ti > 0
        if not any(_is_cjk(ch) for ch in tok):
            out.append((tok, gap))
            continue
        buf = ""
        for ch in tok:
            latin_run = buf and not _is_cjk(ch) and not _is_cjk(buf[-1]) and ch not in _ATTACH
            if buf and (ch in _ATTACH or latin_run):
                buf += ch
                continue
            if buf:
                out.append((buf, gap))
                gap = False
            buf = ch
        if buf:
            out.append((buf, gap))
    return out


def _cue_words(cue: Dict[str, Any], words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The timed words of a cue: their midpoint falls inside it (as the Karaoke composition takes them)."""
    return [w for w in words if cue["start"] <= (w["start"] + w["end"]) / 2 <= cue["end"]]


def schedule(captions: List[Dict[str, Any]], words: List[Dict[str, Any]], beats: Optional[Dict[str, Any]],
             timing: str = "auto", step: int = 1, duration: Optional[float] = None) -> Dict[str, Any]:
    """{by, step, lines, warnings}: one line per caption cue, `units` = [{text, gap, start}] in order, `start` the
    measured time the unit first shows; `start`/`end` of the line = its first unit's start and the time it clears
    (the cue's end, or later when the beats run past it -- a warning says so)."""
    if timing not in KINETIC_TIMINGS:
        raise KineticError(f"--kinetic must be one of {', '.join(KINETIC_TIMINGS)}, got {timing!r}")
    if step < 1:
        raise KineticError("--kinetic-step must be at least 1 beat per unit")
    if not captions:
        raise KineticError("--kinetic needs text: caption cues from --captions (a lyric SRT) or --words")
    beat_times = sorted(float(b) for b in ((beats or {}).get("times") or [])) if (beats or {}).get("usable") else []
    if timing == "auto":
        timing = "words" if words else "beats"
    if timing == "words" and not words:
        raise KineticError("--kinetic words needs word timings (--words): every word starts at the time the "
                           "speech engine measured")
    if timing == "beats" and not beat_times:
        why = "was not measured (add --beats)" if not beats else "is not usable (too little confidence)"
        raise KineticError(f"--kinetic beats needs the measured beat grid, which {why}; kinetic type from no "
                           "measurement is hyperframes-skill's")
    lines: List[Dict[str, Any]] = []
    warnings: List[str] = []
    bi = 0               # next beat a unit may take (beats are used in order, each by one unit at most)
    for ci, cue in enumerate(captions):
        if timing == "words":
            own = _cue_words(cue, words)
            if not own:
                warnings.append(f"kinetic: cue {ci + 1} ({cue['text'][:24]!r}) has no timed words and is not drawn")
                continue
            units = []
            for wi, w in enumerate(own):
                raw = str(w["text"])
                # a word the engine timed is one unit, its spacing the engine's own (a leading space)
                units.append({"text": raw.strip(), "gap": wi > 0 and raw[:1].isspace(),
                              "start": round(float(w["start"]), 3)})
            units = [u for u in units if u["text"]]
        else:
            parts = split_units(cue["text"])
            while bi < len(beat_times) and beat_times[bi] < cue["start"] - 1e-6:
                bi += 1
            units = []
            for text, gap in parts:
                if bi >= len(beat_times):
                    break
                units.append({"text": text, "gap": gap, "start": round(beat_times[bi], 3)})
                bi += step
            if len(units) < len(parts):
                warnings.append(f"kinetic: cue {ci + 1} ({cue['text'][:24]!r}): the measured beats ran out after "
                                f"{len(units)} of {len(parts)} units; the rest is not drawn")
            if not units:
                continue
        end = max(float(cue["end"]), units[-1]["start"] + 0.25)
        if timing == "beats" and units[-1]["start"] >= cue["end"]:
            warnings.append(f"kinetic: cue {ci + 1} ({cue['text'][:24]!r}) needs beats up to "
                            f"{units[-1]['start']:.3f} s, past its end {cue['end']:.3f} s: it stays up until then")
        if duration is not None:
            end = min(end, duration)
        lines.append({"cue": ci, "start": units[0]["start"], "end": round(end, 3), "units": units})
    # a line clears when the next one starts, so two lines never overlap
    for a, b in zip(lines, lines[1:]):
        if a["end"] > b["start"]:
            a["end"] = b["start"]
    if not lines:
        raise KineticError("--kinetic: no caption cue could be timed")
    return {"by": timing, "step": step if timing == "beats" else None, "lines": lines, "warnings": warnings}


def validate(k: Any, n_captions: int) -> List[str]:
    if k is None:
        return []
    ok = isinstance(k, dict) and k.get("by") in ("words", "beats") and isinstance(k.get("lines"), list)
    for ln in (k.get("lines") if ok else []):
        ok = ok and isinstance(ln, dict) and isinstance(ln.get("cue"), int) and 0 <= ln["cue"] < n_captions \
            and isinstance(ln.get("units"), list) and ln["units"] and isinstance(ln.get("end"), (int, float))
        for u in (ln.get("units") if ok else []):
            ok = ok and isinstance(u, dict) and isinstance(u.get("text"), str) and u["text"] \
                and isinstance(u.get("start"), (int, float)) and isinstance(u.get("gap"), bool)
    return [] if ok else ["kinetic must be {by: words|beats, lines: [{cue, start, end, units: [{text, gap, start}]}]} "
                          "-- analyze.py --kinetic writes it"]
