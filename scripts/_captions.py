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
from typing import Any, Dict, List, Optional, Tuple

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


# ---------------------------------------------------------------- emphasis (YouTube-style captions)

EMPHASIS_STYLES = ("pop", "color", "box")
EMPHASIS_AUTO = ("numbers", "names")
_SENTENCE_END = (".", "!", "?", "。", "！", "？")


def _fold(s: str) -> str:
    """Lower case, one character for one character, so offsets in the folded text are offsets in the original."""
    return "".join(ch.lower() if len(ch.lower()) == 1 else ch for ch in s)


def _is_punct(s: str) -> bool:
    return all(unicodedata.category(ch)[0] in ("P", "Z") or ch.isspace() for ch in s)


def read_emphasis(text: str) -> List[Dict[str, Any]]:
    """`--emphasis FILE`: the words to emphasise, as written by the caller. A JSON list (or {"words": [...]})
    of strings or {"text", "at"?, "style"?}: `at` (seconds) picks the cue showing at that time, `style`
    is pop, color or box (default: the emphasisStyle option)."""
    data = json.loads(text)
    if isinstance(data, dict):
        data = data.get("words")
    if not isinstance(data, list) or not data:
        raise CaptionError('emphasis must be a non-empty JSON list of words or {"text", "at"?, "style"?}')
    out: List[Dict[str, Any]] = []
    for i, e in enumerate(data):
        if isinstance(e, str):
            e = {"text": e}
        if not isinstance(e, dict) or not isinstance(e.get("text"), str) or not e["text"].strip():
            raise CaptionError(f"emphasis[{i}] needs a non-empty text")
        unknown = set(e) - {"text", "at", "style"}
        if unknown:
            raise CaptionError(f"emphasis[{i}]: unknown key(s) {sorted(unknown)} (known: text, at, style)")
        at = e.get("at")
        if at is not None and not _num(at):
            raise CaptionError(f"emphasis[{i}]: at must be seconds")
        style = e.get("style")
        if style is not None and style not in EMPHASIS_STYLES:
            raise CaptionError(f"emphasis[{i}]: style must be one of {', '.join(EMPHASIS_STYLES)}")
        out.append({"text": e["text"].strip(), "at": at, "style": style})
    return out


def _cue_tokens(cue: Dict[str, Any], words: List[Dict[str, Any]]) -> Tuple[str, List[Tuple[int, int, int]]]:
    """The cue's timed words (by midpoint, as the compositions assign them) joined with their own spacing,
    and per word (global index, offset where its text starts after the leading space, offset where it ends)."""
    joined, toks = "", []
    for gi, w in enumerate(words):
        mid = (w["start"] + w["end"]) / 2
        if not cue["start"] <= mid <= cue["end"]:
            continue
        lead = len(w["text"]) - len(w["text"].lstrip())
        toks.append((gi, len(joined) + lead, len(joined) + len(w["text"])))
        joined += w["text"]
    return joined, toks


def _find(target: str, joined: str, toks: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int, int]]:
    """Every whole-word occurrence of target in the cue's words: (first word, last word, start, end offsets).
    It starts where a word starts and ends where a word ends, or before only that word's trailing punctuation."""
    folded, t, hits = _fold(joined), _fold(target), []
    starts = {a: k for k, (_, a, _) in enumerate(toks)}
    pos = folded.find(t)
    while pos >= 0:
        end = pos + len(t)
        k = starts.get(pos)
        if k is not None:
            for m in range(k, len(toks)):
                if toks[m][1] < end <= toks[m][2] and _is_punct(joined[end:toks[m][2]]):
                    hits.append((toks[k][0], toks[m][0], pos, end))
                    break
        pos = folded.find(t, pos + 1)
    return hits


def _cjk(ch: str) -> bool:
    return "\u3040" <= ch <= "\u30ff" or "\u3400" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" or "\uff00" <= ch <= "\uffef"


def _text_hits(target: str, text: str) -> List[Tuple[int, int]]:
    """Whole-word occurrences of target in a cue's own text, as [start, end) code-point offsets. Between
    Latin letters or digits a boundary is needed (`foot` is not in `football`); CJK text has no spaces, so
    there the timed words decide what a word is."""
    folded, t, out = _fold(text), _fold(target), []
    pos = folded.find(t)
    while pos >= 0:
        end = pos + len(t)
        before = text[pos - 1] if pos else ""
        after = text[end] if end < len(text) else ""
        glued = lambda x, y: bool(x and y and x.isalnum() and y.isalnum() and not (_cjk(x) or _cjk(y)))
        if not glued(before, text[pos]) and not glued(text[end - 1], after):
            out.append((pos, end))
        pos = folded.find(t, pos + 1)
    return out


def _auto_candidates(kind: str, joined: str, toks: List[Tuple[int, int, int]]) -> List[Tuple[int, str]]:
    """(position among the cue's words, word) of each qualifying word: only that word, not every
    occurrence of its spelling, is emphasised."""
    out = []
    for k, (_, a, b) in enumerate(toks):
        word = joined[a:b]
        core = word.rstrip("".join(ch for ch in word if _is_punct(ch)))
        if not core:
            continue
        if kind == "numbers" and any(unicodedata.category(ch) == "Nd" for ch in core):
            out.append((k, core))
        elif kind == "names":
            prev = joined[:a].rstrip()
            katakana = len(core) >= 2 and all("\u30a0" <= ch <= "\u30ff" for ch in core)
            capital = (core[0].isupper() and core[0].isascii() and k > 0 and prev and not prev.endswith(_SENTENCE_END))
            if katakana or capital:
                out.append((k, core))
    return out


def resolve_emphasis(captions: List[Dict[str, Any]], words: List[Dict[str, Any]], entries: List[Dict[str, Any]],
                     auto: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Place each emphasised word on the caption cue that shows it, at the time the speech engine measured.

    The emphasised text is a slice of the cue's own words (case and spelling as spoken in the caption),
    never the caller's spelling and never rewritten. A caller's word that is not a whole word of the cue
    (or of any cue, without `at`) is refused; nothing is moved, guessed or interpolated. `auto` adds the
    cue's own numbers ("numbers") and capitalised / katakana names ("names") without a style.
    The word must also be a whole word of the cue's own text (that text is what is drawn); `span` is its
    [start, end) code-point offsets there.
    Returns ([{start, end, text, style, cue, span, words: [first, last], by}], warnings)."""
    if not entries and not auto:
        raise CaptionError("nothing to emphasise: give words (--emphasis) or kinds (--emphasis-auto)")
    if not words:
        raise CaptionError("emphasis needs word timings (--words): a word's time is measured, never guessed")
    if not captions:
        raise CaptionError("emphasis needs caption cues")
    tokens = [_cue_tokens(c, words) for c in captions]
    out: List[Dict[str, Any]] = []
    warnings: List[str] = []
    taken = set()

    def matches(ci: int, target: str) -> List[Tuple[Tuple[int, int, int, int], Tuple[int, int]]]:
        """The timed whole-word hits of target in cue ci, each paired with the same occurrence in the
        cue's own text (n-th with n-th). The caption text is what is drawn, so the two must agree."""
        timed = _find(target, *tokens[ci])
        if not timed:
            return []
        in_text = _text_hits(target, captions[ci]["text"])
        if len(in_text) != len(timed):
            raise CaptionError(f"emphasis {target!r}: cue {ci + 1} ({captions[ci]['text']!r}) has it "
                               f"{len(in_text)} time(s) as a whole word but its word timings {len(timed)}; the "
                               "caption and the word timings disagree, so its time cannot be placed")
        return list(zip(timed, in_text))

    def add(ci: int, hit: Tuple[int, int, int, int], span_text: Tuple[int, int], style: Optional[str], by: str) -> bool:
        first, last, _, _ = hit
        span = set(range(first, last + 1))
        if span & taken:
            return False
        taken.update(span)
        a, b = span_text
        out.append({"start": words[first]["start"], "end": words[last]["end"], "text": captions[ci]["text"][a:b],
                    "style": style, "cue": ci, "span": [a, b], "words": [first, last], "by": by})
        return True

    for e in entries:
        if e["at"] is not None:
            cues = [i for i, c in enumerate(captions) if c["start"] <= e["at"] < c["end"]]
            if not cues:
                raise CaptionError(f"emphasis {e['text']!r}: no caption cue shows at {e['at']:g} s")
        else:
            cues = list(range(len(captions)))
        found, untimed_hit = 0, None
        for ci in cues:
            if _fold(e["text"]) not in _fold(captions[ci]["text"]):
                continue
            if not tokens[ci][1]:
                untimed_hit = ci
            for hit, span_text in matches(ci, e["text"]):
                if not add(ci, hit, span_text, e["style"], "caller"):
                    raise CaptionError(f"emphasis {e['text']!r} overlaps another emphasised word in cue {ci + 1}")
                found += 1
        if not found and untimed_hit is not None:
            raise CaptionError(f"emphasis {e['text']!r}: cue {untimed_hit + 1} ({captions[untimed_hit]['text']!r}) "
                               "has no word timings, so its time is not measured")
        if not found:
            where = (f"the cue at {e['at']:g} s ({captions[cues[0]]['text']!r})" if e["at"] is not None
                     else "any caption cue")
            raise CaptionError(f"emphasis {e['text']!r} is not a whole word of {where}: only the caption's own, "
                               "timed words can be emphasised")
    for kind in auto:
        if kind not in EMPHASIS_AUTO:
            raise CaptionError(f"--emphasis-auto: unknown kind {kind!r} (known: {', '.join(EMPHASIS_AUTO)})")
        n = 0
        for ci, (joined, toks) in enumerate(tokens):
            for k, cand in _auto_candidates(kind, joined, toks):
                try:
                    pairs = matches(ci, cand)
                except CaptionError as err:
                    warnings.append(f"{err} (skipped)")
                    continue
                n += sum(add(ci, hit, span_text, None, kind) for hit, span_text in pairs if hit[0] == toks[k][0])
        if not n:
            warnings.append(f"emphasis: no {kind} found in the timed caption words")
    untimed = [i + 1 for i, (_, toks) in enumerate(tokens) if not toks]
    if untimed and (entries or auto):
        warnings.append("emphasis: cue(s) " + ", ".join(map(str, untimed)) + " have no word timings, so nothing "
                        "in them can be emphasised")
    return sorted(out, key=lambda x: x["start"]), warnings


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
