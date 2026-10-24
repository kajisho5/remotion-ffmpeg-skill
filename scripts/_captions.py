#!/usr/bin/env python3
"""Caption file readers (internal module): SRT, WebVTT and a plain JSON cue list.

Cue text is kept exactly as written (line breaks included): this skill never rewrites,
shortens or paraphrases caption words -- the same rule as ffmpeg-skill.
"""
import json
import re
from pathlib import Path
from typing import Dict, List

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
