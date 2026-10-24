#!/usr/bin/env python3
"""Caption file readers (internal module): SRT, WebVTT and a plain JSON cue list.

Cue text is kept exactly as written (line breaks included): this skill never rewrites,
shortens or paraphrases caption words -- the same rule as ffmpeg-skill.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List

_TS = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_ARROW = re.compile(r"^\s*(\S+)\s+-->\s+(\S+)")
_TAG = re.compile(r"</?(?:[bius]|c(?:\.[\w.-]+)?|v(?:\s[^>]*)?|lang(?:\s[^>]*)?|ruby|rt)>")


class CaptionError(ValueError):
    pass


def parse_timestamp(s: str) -> float:
    m = _TS.fullmatch(s.strip())
    if not m:
        raise CaptionError(f"bad timestamp: {s!r}")
    h, mi, se, ms = m.groups()
    frac = int(ms) / (10 ** len(ms))
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + frac


def _blocks(text: str) -> List[List[str]]:
    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    return [b.split("\n") for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def parse_srt_or_vtt(text: str) -> List[Dict]:
    cues: List[Dict] = []
    for lines in _blocks(text):
        if lines[0].strip().upper().startswith(("WEBVTT", "NOTE", "STYLE", "REGION")):
            continue
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue
        m = _ARROW.match(lines[idx])
        if not m:
            raise CaptionError(f"bad cue timing line: {lines[idx]!r}")
        start, end = parse_timestamp(m.group(1)), parse_timestamp(m.group(2))
        body = "\n".join(_TAG.sub("", ln) for ln in lines[idx + 1:]).strip()
        if end <= start:
            raise CaptionError(f"cue ends before it starts: {lines[idx]!r}")
        if body:
            cues.append({"start": round(start, 3), "end": round(end, 3), "text": body})
    return cues


def parse_json_cues(text: str) -> List[Dict]:
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("cues") or data.get("captions")
    if not isinstance(data, list):
        raise CaptionError("JSON captions must be a list of {start, end, text} (or {\"cues\": [...]})")
    cues = []
    for i, c in enumerate(data):
        try:
            start, end, body = float(c["start"]), float(c["end"]), str(c["text"])
        except (KeyError, TypeError, ValueError):
            raise CaptionError(f"cue {i} needs numeric start/end and text")
        if end <= start:
            raise CaptionError(f"cue {i} ends before it starts")
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": body})
    return cues


def read_captions(path: Path) -> List[Dict]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        cues = parse_json_cues(text)
    else:
        cues = parse_srt_or_vtt(text)
    return sorted(cues, key=lambda c: c["start"])


# ---------------------------------------------------------------- word timings (karaoke)

def parse_words(text: str) -> List[Dict]:
    """Word timings from a speech engine's JSON, as [{start, end, text}] in time order.

    Accepts the whisper / faster-whisper layout ({"segments": [{"words": [{"word", "start", "end"}]}]}),
    a top-level {"words": [...]} and a plain list. `text` keeps the engine's own spacing (English words
    carry a leading space, Japanese tokens none), so joining them reproduces the transcript exactly.
    """
    data = json.loads(text)
    raw: List[Dict] = []
    if isinstance(data, dict) and isinstance(data.get("segments"), list):
        for seg in data["segments"]:
            raw += list(seg.get("words") or [])
    elif isinstance(data, dict) and isinstance(data.get("words"), list):
        raw = data["words"]
    elif isinstance(data, list):
        raw = data
    else:
        raise CaptionError("word timings must be whisper JSON (segments[].words[]) or a list of {word, start, end}")
    words: List[Dict] = []
    for i, w in enumerate(raw):
        try:
            body = str(w.get("word", w.get("text")))
            start, end = float(w["start"]), float(w["end"])
        except (AttributeError, KeyError, TypeError, ValueError):
            raise CaptionError(f"word {i} needs word/text, start and end")
        if body in ("", "None") or end < start:
            continue
        words.append({"start": round(start, 3), "end": round(max(end, start + 0.01), 3), "text": body})
    if not words:
        raise CaptionError("no timed words found (was the transcript made with word timestamps?)")
    return sorted(words, key=lambda w: w["start"])


def read_words(path: Path) -> List[Dict]:
    return parse_words(path.read_text(encoding="utf-8-sig"))


def cues_from_words(words: List[Dict], max_chars: int = 32, max_gap: float = 0.7, max_len: float = 4.0) -> List[Dict]:
    """Group timed words into caption cues mechanically: a new cue after a pause longer than max_gap,
    when the cue would pass max_chars characters, or last longer than max_len seconds. The words and
    their order are the engine's; nothing is added, dropped or reworded."""
    cues: List[Dict] = []
    cur: List[Dict] = []
    for w in words:
        if cur:
            text_len = len("".join(x["text"] for x in cur + [w]).strip())
            if (w["start"] - cur[-1]["end"] > max_gap or text_len > max_chars
                    or w["end"] - cur[0]["start"] > max_len):
                cues.append(_cue(cur))
                cur = []
        cur.append(w)
    if cur:
        cues.append(_cue(cur))
    return cues


def _cue(ws: List[Dict]) -> Dict:
    return {"start": ws[0]["start"], "end": ws[-1]["end"], "text": "".join(w["text"] for w in ws).strip()}


# ---------------------------------------------------------------- chapters

def _chapter_time(tok: str) -> float:
    """seconds, mm:ss or hh:mm:ss (with optional .ms) -- the syntax of ffmpeg-skill's chapters.txt."""
    parts = tok.split(":")
    if not 1 <= len(parts) <= 3 or not all(p.replace(".", "", 1).isdigit() for p in parts):
        raise CaptionError(f"not a time: {tok!r} (use 0:00, 2:15 or 1:03:00)")
    if any("." in p for p in parts[:-1]):
        raise CaptionError(f"not a time: {tok!r}")
    v = 0.0
    for p in parts:
        v = v * 60 + float(p)
    return v


def parse_chapters(text: str, duration: float) -> List[Dict[str, Any]]:
    """`TIME TITLE` per line (YouTube's description format, ffmpeg-skill metadata.py's chapters.txt)
    -> [{start, end, title}]. Titles are the user's text: a line without one is an error, never
    a made-up "Chapter 2"."""
    out: List[Dict[str, Any]] = []
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        start = _chapter_time(parts[0])
        title = parts[1].strip() if len(parts) > 1 else ""
        # "0:00 - Intro" / "0:00 – Intro": the separator is not part of the title
        for sep in ("- ", "– ", "— ", ": "):
            if title.startswith(sep):
                title = title[len(sep):].strip()
        if not title:
            raise CaptionError(f"line {n}: chapter at {parts[0]} has no title")
        if out and start <= out[-1]["start"]:
            raise CaptionError(f"line {n}: chapter at {parts[0]} does not come after the previous one")
        if duration and start >= duration:
            raise CaptionError(f"line {n}: chapter at {parts[0]} starts at or after the end ({duration:.3f} s)")
        out.append({"start": start, "title": title})
    if not out:
        raise CaptionError("no chapters found (one per line: `0:00 Intro`)")
    for i, c in enumerate(out):
        c["end"] = out[i + 1]["start"] if i + 1 < len(out) else duration
    return out


def youtube_chapter_warnings(chapters: List[Dict[str, Any]]) -> List[str]:
    """YouTube only turns a description list into chapters when the first is at 0:00, there are at
    least three, and each lasts at least 10 seconds."""
    w = []
    if chapters and chapters[0]["start"] != 0:
        w.append("chapters: the first does not start at 0:00, so YouTube will not show them as chapters")
    if len(chapters) < 3:
        w.append("chapters: fewer than three, so YouTube will not show them as chapters")
    short = [c["title"] for c in chapters if c["end"] - c["start"] < 10]
    if short:
        w.append("chapters shorter than 10 s (YouTube ignores the list): " + ", ".join(short))
    return w
