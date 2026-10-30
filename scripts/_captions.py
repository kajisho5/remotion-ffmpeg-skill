#!/usr/bin/env python3
"""Caption file readers (internal module): SRT, WebVTT, a plain JSON cue list, whisper word timings and
transcription-skill transcripts.

Cue text is kept exactly as written (line breaks included): this skill never rewrites,
shortens or paraphrases caption words -- the same rule as ffmpeg-skill.
"""
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

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


# ---------------------------------------------------------------- transcription-skill transcripts

TRANSCRIPT_SCHEMA = "transcription-skill/transcript/0.1"
_TRANSCRIPT_END_TOLERANCE = 0.5     # transcription-skill validate.py END_TOLERANCE
_TRANSCRIPT_CONTAINMENT = 0.01      # transcription-skill validate.py CONTAINMENT_TOLERANCE
_TRANSCRIPT_REQUIRED = ("schema", "id", "asset_id", "language", "language_source", "language_confidence", "duration",
                        "segments", "source", "engine", "engine_version", "created_at", "provenance", "warnings")
_SEGMENT_REQUIRED = ("id", "start", "end", "text", "raw_text", "confidence", "words", "speaker_id")
_WORD_REQUIRED = ("start", "end", "text", "confidence")
_SOURCE_REQUIRED = ("filename", "fingerprint", "size_bytes", "media_duration")
_PROVENANCE_REQUIRED = ("engine", "engine_version", "execution_mode", "model", "model_version", "parameters",
                        "parameters_hash", "cache_key", "created_at", "processing_seconds", "skill_version", "skill", "tool")
_FINGERPRINT = re.compile(r"sha256:[0-9a-f]{64}")
_SPACE = re.compile(r"[\s 　]+")


def is_transcript(data: Any) -> bool:
    """A document that names a schema is read as a transcript (and refused if it is not one we know)."""
    return isinstance(data, dict) and "schema" in data


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))


def _conf_ok(v: Any) -> bool:
    return v is None or (_num(v) and 0.0 <= v <= 1.0)


def validate_transcript(doc: Any) -> List[str]:
    """Errors against transcription-skill's Transcript contract (schemas/transcript.schema.json and the
    timing rules of its validate.py). Empty list = valid. An unknown schema version is an error: its
    fields could mean something else."""
    if not isinstance(doc, dict):
        return ["a transcript must be a JSON object"]
    if doc.get("schema") != TRANSCRIPT_SCHEMA:
        return [f"unsupported transcript schema {doc.get('schema')!r}: this version reads {TRANSCRIPT_SCHEMA} only"]
    errs = [f"missing required field: {k}" for k in _TRANSCRIPT_REQUIRED if k not in doc]
    if errs:
        return errs
    for k in ("id", "asset_id", "engine", "engine_version", "created_at"):
        if not isinstance(doc[k], str) or not doc[k]:
            errs.append(f"{k} must be a non-empty string")
    if not isinstance(doc["language"], str) or not re.fullmatch(r"[a-z]{2,3}|unknown", doc["language"]):
        errs.append(f"language must be an ISO 639 code or 'unknown', got {doc['language']!r}")
    if doc["language_source"] not in ("requested", "detected", "unknown"):
        errs.append(f"language_source must be requested, detected or unknown, got {doc['language_source']!r}")
    if not _conf_ok(doc["language_confidence"]):
        errs.append("language_confidence must be null or a number in [0, 1]")
    if not isinstance(doc["warnings"], list) or not all(isinstance(w, str) for w in doc["warnings"]):
        errs.append("warnings must be a list of strings")
    dur = doc["duration"]
    if not _num(dur) or dur <= 0:
        errs.append(f"duration must be a positive number, got {dur!r}")
        dur = None
    src = doc["source"]
    if not isinstance(src, dict):
        errs.append("source must be an object")
    else:
        errs += [f"source.{k} is required" for k in _SOURCE_REQUIRED if k not in src]
        if not isinstance(src.get("fingerprint"), str) or not _FINGERPRINT.fullmatch(src["fingerprint"]):
            errs.append("source.fingerprint must be 'sha256:<64 hex>'")
        if not isinstance(src.get("filename"), str) or not src["filename"]:
            errs.append("source.filename must be a non-empty string")
        md = src.get("media_duration")
        if "media_duration" in src and (not _num(md) or md <= 0):
            errs.append("source.media_duration must be a positive number")
        elif dur is not None and _num(md) and abs(md - dur) > 1e-6:
            errs.append("duration must equal source.media_duration")
    prov = doc["provenance"]
    if not isinstance(prov, dict):
        errs.append("provenance must be an object")
    else:
        errs += [f"provenance.{k} is required" for k in _PROVENANCE_REQUIRED if k not in prov]
        if prov.get("skill", "transcription-skill") != "transcription-skill":
            errs.append(f"provenance.skill must be transcription-skill, got {prov.get('skill')!r}")
        if not str(prov.get("tool", "transcription/")).startswith("transcription/"):
            errs.append("provenance.tool must be a transcription/* tool name")
    segs = doc["segments"]
    if not isinstance(segs, list):
        return errs + ["segments must be a list"]
    ids = set()
    prev: Optional[Dict[str, Any]] = None
    for i, seg in enumerate(segs):
        where = f"segments[{i}]"
        if not isinstance(seg, dict):
            errs.append(f"{where}: must be an object")
            continue
        missing = [k for k in _SEGMENT_REQUIRED if k not in seg]
        if missing:
            errs.append(f"{where}: missing {missing}")
            continue
        if not isinstance(seg["id"], str) or not seg["id"] or seg["id"] in ids:
            errs.append(f"{where}: id must be a unique non-empty string")
        ids.add(seg["id"])
        s, e = seg["start"], seg["end"]
        if not _num(s) or not _num(e):
            errs.append(f"{where}: start/end must be numbers")
            continue
        if s < 0 or e <= s:
            errs.append(f"{where}: needs 0 <= start < end, got [{s}, {e}]")
        if dur is not None and e > dur + _TRANSCRIPT_END_TOLERANCE:
            errs.append(f"{where}: end {e} is past the media duration {dur}")
        if prev is not None and (s < prev["start"] or s < prev["end"] - _TRANSCRIPT_CONTAINMENT):
            errs.append(f"{where}: starts before the previous segment ends (not ordered / overlapping)")
        prev = seg
        if not isinstance(seg["text"], str) or not isinstance(seg["raw_text"], str):
            errs.append(f"{where}: text and raw_text must be strings")
        if not _conf_ok(seg["confidence"]):
            errs.append(f"{where}: confidence must be null or a number in [0, 1]")
        words = seg["words"]
        if words is None:
            continue
        if not isinstance(words, list):
            errs.append(f"{where}: words must be null or a list")
            continue
        wprev = None
        for j, w in enumerate(words):
            ww = f"{where}.words[{j}]"
            if not isinstance(w, dict) or any(k not in w for k in _WORD_REQUIRED):
                errs.append(f"{ww}: must have {list(_WORD_REQUIRED)}")
                continue
            ws, we = w["start"], w["end"]
            if not _num(ws) or not _num(we):
                errs.append(f"{ww}: start/end must be numbers")
                continue
            if ws < 0 or we <= ws:
                errs.append(f"{ww}: needs 0 <= start < end, got [{ws}, {we}]")
            if ws < s - _TRANSCRIPT_CONTAINMENT or we > e + _TRANSCRIPT_CONTAINMENT:
                errs.append(f"{ww}: [{ws}, {we}] is outside its segment [{s}, {e}]")
            if wprev is not None and ws < wprev - _TRANSCRIPT_CONTAINMENT:
                errs.append(f"{ww}: words not in time order")
            wprev = we
            if not isinstance(w["text"], str) or not w["text"].strip():
                errs.append(f"{ww}: text must be a non-empty string")
            if not _conf_ok(w["confidence"]):
                errs.append(f"{ww}: confidence must be null or a number in [0, 1]")
    return errs


def _spaced_words(seg: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """The segment's words with the engine's own spacing put back in front of each (`" world"`, `"字幕"`).

    transcription-skill trims each word, so the spacing is read from the segment's verbatim `raw_text`:
    a word gets one leading space when whitespace precedes it there (whitespace runs collapse to one, as
    in the transcript's own `text`). None when the words do not spell `raw_text` in order -- then the
    segment's word timings cannot be trusted to belong to its text."""
    raw = "".join(ch for ch in seg["raw_text"] if unicodedata.category(ch) not in ("Cc", "Cf") or ch in "\t\n\r")
    pos, out = 0, []
    for w in seg["words"]:
        m = _SPACE.match(raw, pos)
        lead = " " if m else ""
        pos = m.end() if m else pos
        token = _SPACE.sub(" ", w["text"]).strip()
        if not raw.startswith(token, pos):
            return None
        pos += len(token)
        out.append({"start": w["start"], "end": w["end"], "text": lead + token})
    return out if not raw[pos:].strip() else None


def parse_transcript(doc: Any) -> Dict[str, Any]:
    """A validated transcription-skill Transcript -> {words, cues, warnings, duration, fingerprint, filename}.

    Every time comes from the transcript as written (not rounded, shifted or stretched). Cues are grouped
    from the words inside each segment (cues_from_words) and never cross a segment boundary; a segment
    without usable word timings becomes one cue with the segment's own times and text, and its words
    are left out of `words` (Karaoke shows that cue plain) -- no word time is ever interpolated."""
    errs = validate_transcript(doc)
    if errs:
        more = f" (+{len(errs) - 5} more)" if len(errs) > 5 else ""
        raise CaptionError("not a valid transcription-skill transcript: " + "; ".join(errs[:5]) + more)
    words: List[Dict[str, Any]] = []
    cues: List[Dict[str, Any]] = []
    warnings = [f"transcript: {w}" for w in doc["warnings"]]
    plain: List[str] = []
    for seg in doc["segments"]:
        sw = _spaced_words(seg) if seg["words"] else None
        if sw:
            words += sw
            cues += cues_from_words(sw)
        elif seg["text"].strip():
            if seg["words"]:
                warnings.append(f"transcript {seg['id']}: its words do not spell its text; shown as one plain cue")
            else:
                plain.append(seg["id"])
            cues.append({"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()})
    if plain:
        warnings.append("transcript has no word timings for " + ", ".join(plain)
                        + " (shown as plain cues; transcribe with word timestamps for Karaoke)")
    if not cues:
        raise CaptionError("the transcript has no speech segments")
    return {"words": words, "cues": cues, "warnings": warnings, "duration": float(doc["duration"]),
            "fingerprint": doc["source"]["fingerprint"], "filename": doc["source"]["filename"]}


def read_word_timings(path: Path) -> Dict[str, Any]:
    """`--words`: a transcription-skill transcript (validated strictly) or whisper-style word JSON.
    Returns {words, cues (None for whisper JSON: grouped later only without --captions), warnings, ...}."""
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text)
    if is_transcript(data):
        return parse_transcript(data)
    return {"words": parse_words(text), "cues": None, "warnings": []}


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
