#!/usr/bin/env python3
"""Measure a source video with ffmpeg-skill and write a timeline.json that the Remotion
compositions read as props: real duration/fps/size, scene cuts, silences and the speech
ranges between them, audio peaks, an optional beat grid, and captions from a file.

Every number comes from a measurement (ffmpeg-skill's probe.py / scenes.py / silence.py);
nothing is guessed. Warnings flag sources Remotion handles badly (variable frame rate, HDR).
Several inputs are joined first with ffmpeg-skill join.py (size, fps and audio normalised to the
first clip) and measured as one source; the clip boundaries are kept in the timeline.

Examples:
  python3 analyze.py talk.mp4                              # -> talk.timeline.json
  python3 analyze.py talk.mp4 --captions talk.srt -o tl.json
  python3 analyze.py music.mp4 --beats                     # also measure the beat grid
  python3 analyze.py talk.mp4 --threshold -42 --min-silence 0.8   # quiet room
  python3 analyze.py intro.mp4 talk.mov outro.mp4 --captions all.srt  # joined, then measured
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (STATE, TIMELINE_SCHEMA, SKILL_ID, add_common, apply_common, default_output, die,
                     emit, ffmpeg_skill_version, ffskill, ffskill_cmd, info, refuse_existing,
                     require_ffmpeg_skill, shell_join, version)
from _captions import CaptionError, cues_from_words, parse_chapters, read_captions, read_words, youtube_chapter_warnings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", nargs="+", help="source video (or audio) file; several are joined in order first")
    p.add_argument("--joined", help="with several inputs: where the joined source goes (default: <first>_joined.mp4)")
    p.add_argument("--join-transition", default="none",
                   help="with several inputs: ffmpeg-skill join.py --transition (default none = straight cuts)")
    p.add_argument("--join-duration", type=float, default=0.5, help="transition length in seconds (default 0.5)")
    p.add_argument("-o", "--output", help="timeline file (default: <name>.timeline.json)")
    p.add_argument("--captions", help="SRT, WebVTT or JSON cue list to carry into the timeline (text kept as written)")
    p.add_argument("--words", help="word timings from a speech engine (whisper JSON with word timestamps) for the "
                                    "Karaoke composition; without --captions the cues are grouped from these words")
    p.add_argument("--chapters", metavar="FILE|source",
                   help="chapter list, one `TIME TITLE` per line (YouTube's format, the same file ffmpeg-skill "
                        "metadata.py --chapters writes into the container), or `source` for the chapters already "
                        "in the input file; titles are kept as written")
    p.add_argument("--beats", action="store_true", help="also measure the beat grid (scenes.py --beats)")
    p.add_argument("--highlights", type=int, metavar="N",
                   help="also rank N highlight ranges (scenes.py --highlights; audio energy) for the Highlights composition")
    p.add_argument("--target", type=float, metavar="SECONDS", help="with --highlights: total length the picks add up to")
    p.add_argument("--no-scenes", action="store_true", help="skip scene-cut detection")
    p.add_argument("--no-silence", action="store_true", help="skip silence detection (speech = whole file)")
    p.add_argument("--threshold", type=float, help="silence level in dBFS for silence.py (default -35)")
    p.add_argument("--min-silence", type=float, help="shortest gap in seconds that counts as silence (default 0.6)")
    p.add_argument("--margin", type=float, help="seconds of silence kept around speech (default 0.15)")
    p.add_argument("--scene-threshold", type=float, help="scenes.py --threshold (default 8)")
    add_common(p)
    return p


def silence_args(a: argparse.Namespace) -> List[str]:
    out: List[str] = ["--list"]
    for flag, val in (("--threshold", a.threshold), ("--min-silence", a.min_silence), ("--margin", a.margin)):
        if val is not None:
            out += [flag, str(val)]
    return out


def scene_args(a: argparse.Namespace) -> List[str]:
    out: List[str] = []
    if a.scene_threshold is not None:
        out += ["--threshold", str(a.scene_threshold)]
    if a.beats:
        out.append("--beats")
    if getattr(a, "highlights", None):
        out += ["--highlights", str(a.highlights)]
        if a.target:
            out += ["--target", str(a.target)]
    return out


def warnings_for(probe: Dict[str, Any]) -> List[str]:
    w: List[str] = []
    v = probe.get("video") or {}
    if v.get("variable_frame_rate_suspected"):
        w.append("variable frame rate suspected: Remotion renders on a fixed frame grid, so cuts and captions "
                 "can drift. Make a constant-frame-rate copy first (ffmpeg-skill export.py / fit.py --fps).")
    if v.get("hdr") or v.get("hdr_signal") or v.get("bt2020_or_hdr"):
        w.append("HDR / BT.2020 source: Remotion composites in the browser's SDR colour space, so the picture "
                 "will look washed out. Convert first: ffmpeg-skill color.py --to-sdr.")
    if v.get("rotation"):
        w.append(f"source is rotated {v.get('rotation')} degrees by metadata; check the first still.py frame.")
    fps = v.get("fps")
    if fps and abs(fps - round(fps)) > 1e-3 and abs(fps * 1001 / 1000 - round(fps * 1001 / 1000)) > 1e-3:
        w.append(f"unusual frame rate {fps}: the compositions use it as-is.")
    return w


def main() -> None:
    a = build_parser().parse_args()
    apply_common(a)
    inputs = [Path(i).expanduser() for i in a.input]
    missing = [str(i) for i in inputs if not i.is_file()]
    if missing:
        die(f"input not found: {', '.join(missing)}", "input")
    src = inputs[0]
    joined: Path = Path(a.joined).expanduser() if a.joined else default_output(src, "_joined", ".mp4")
    out = Path(a.output) if a.output else default_output(joined if len(inputs) > 1 else src, ".timeline", ".json")
    refuse_existing(out)
    skill = require_ffmpeg_skill()

    captions: List[Dict[str, Any]] = []
    if a.captions:
        cpath = Path(a.captions).expanduser()
        if not cpath.is_file():
            die(f"captions file not found: {cpath}", "input")
        try:
            captions = read_captions(cpath)
        except (CaptionError, ValueError) as e:
            die(f"cannot read {cpath}: {e}", "input")

    words: List[Dict[str, Any]] = []
    if a.words:
        wpath = Path(a.words).expanduser()
        if not wpath.is_file():
            die(f"word timings file not found: {wpath}", "input")
        try:
            words = read_words(wpath)
        except (CaptionError, ValueError) as e:
            die(f"cannot read {wpath}: {e}", "input")
        if not captions:
            captions = cues_from_words(words)

    join_args = [*map(str, inputs), "-o", str(joined), "--transition", a.join_transition,
                 "--duration", str(a.join_duration)] + (["--overwrite"] if STATE.overwrite else [])
    plan = ([shell_join(ffskill_cmd("join", join_args))] if len(inputs) > 1 else []) + \
        [shell_join(ffskill_cmd("probe", [str(joined if len(inputs) > 1 else src)]))]
    if STATE.dry_run:
        target = str(joined if len(inputs) > 1 else src)
        if not a.no_scenes:
            plan.append(shell_join(ffskill_cmd("scenes", [target, *scene_args(a)])))
        if not a.no_silence:
            plan.append(shell_join(ffskill_cmd("silence", [target, *silence_args(a)])))
        emit({"output": str(out), "commands": plan}, f"would write {out} after {len(plan)} ffmpeg-skill steps")
        return

    clips: List[Dict[str, Any]] = []
    pre_commands: List[str] = []
    if len(inputs) > 1:
        refuse_existing(joined)
        durations = []
        for f in inputs:
            pr = ffskill("probe", [str(f)])
            # The picture's own length: a stream-copied clip's audio can run a few ms past it.
            durations.append(float((pr.get("video") or {}).get("duration") or pr.get("duration") or 0))
            pre_commands.append(pr["_command"])
        info(f"joining {len(inputs)} clips with ffmpeg-skill join.py -> {joined}")
        jn = ffskill("join", join_args)
        pre_commands.append(jn["_command"])
        overlap = a.join_duration if a.join_transition != "none" else 0.0
        t = 0.0
        for i, (f, d) in enumerate(zip(inputs, durations)):
            start = max(0.0, t - (overlap if i > 0 else 0.0))
            clips.append({"name": f.name, "path": str(f.resolve()), "start": round(start, 3), "end": round(start + d, 3)})
            t = start + d
        src = joined

    probe = ffskill("probe", [str(src)])
    video, audio = probe.get("video"), probe.get("audio")
    duration = float(probe.get("duration") or (video or {}).get("duration") or (audio or {}).get("duration") or 0)
    if duration <= 0:
        die(f"{src} has no measurable duration", "input")
    commands = pre_commands + [probe["_command"]]
    if clips:
        # The last boundary is the measured joined duration (encoders can round the tail by a frame).
        clips[-1]["end"] = round(duration, 3)

    scenes: List[Dict[str, float]] = [{"start": 0.0, "end": round(duration, 3)}]
    peaks: List[Dict[str, float]] = []
    beats: Any = None
    highlights: List[Dict[str, float]] = []
    if a.highlights and (a.no_scenes or not video):
        die("--highlights needs scene detection on a video source", "input")
    if video and not a.no_scenes:
        sc = ffskill("scenes", [str(src), *scene_args(a)])
        commands.append(sc["_command"])
        scenes = [{"start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3)}
                  for s in sc.get("scenes", [])] or scenes
        peaks = [{"time": round(float(p["time"]), 3), "rms": float(p.get("rms", 0))}
                 for p in sc.get("audio_peaks", [])]
        if a.beats:
            grid = sc.get("beat_grid") or {}
            beats = {"times": [round(float(b), 3) for b in (sc.get("beats") or [])],
                     "tempo_bpm": grid.get("tempo_bpm"), "confidence": grid.get("confidence"),
                     "usable": bool(grid.get("usable")) and bool(sc.get("beats"))}
        # Chronological order: the composition plays them as they happen in the source.
        highlights = sorted(({"start": round(float(h["start"]), 3), "end": round(float(h["end"]), 3)}
                             for h in (sc.get("highlights") or []) if float(h["end"]) > float(h["start"])),
                            key=lambda h: h["start"])

    silences: List[List[float]] = []
    speech: List[List[float]] = [[0.0, round(duration, 3)]]
    if audio and not a.no_silence:
        si = ffskill("silence", [str(src), *silence_args(a)])
        commands.append(si["_command"])
        silences = [[round(float(s), 3), round(float(e), 3)] for s, e in si.get("silences", [])]
        keep = [[round(float(s), 3), round(float(e), 3)] for s, e in si.get("keep", []) if float(e) > float(s)]
        speech = keep or speech

    chapters: List[Dict[str, Any]] = []
    if a.chapters == "source":
        chapters = [{"start": round(float(c["start"] or 0), 3), "end": round(float(c["end"] or duration), 3),
                     "title": str(c["title"]).strip()}
                    for c in probe.get("chapters") or [] if str(c.get("title") or "").strip()]
        if not chapters:
            die(f"{src} has no titled chapters of its own (give a chapters file instead)", "input")
    elif a.chapters:
        chpath = Path(a.chapters).expanduser()
        if not chpath.is_file():
            die(f"chapters file not found: {chpath}", "input")
        try:
            chapters = parse_chapters(chpath.read_text(encoding="utf-8-sig"), duration)
        except CaptionError as e:
            die(f"{chpath}: {e}", "input")

    v = video or {}
    timeline: Dict[str, Any] = {
        "schema": TIMELINE_SCHEMA,
        "generator": {"name": SKILL_ID, "version": version(),
                      "ffmpeg_skill": ffmpeg_skill_version(skill)},
        "source": {
            "path": str(src.resolve()),
            "name": src.name,
            "duration": round(duration, 3),
            "fps": float(v.get("fps") or 30.0),
            "width": int(v.get("width") or 1920),
            "height": int(v.get("height") or 1080),
            "has_video": bool(video),
            "has_audio": bool(audio),
        },
        "scenes": scenes,
        "silences": silences,
        "speech": speech,
        "peaks": peaks,
        "beats": beats,
        "highlights": highlights,
        "clips": clips,
        "captions": captions,
        "words": words,
        "chapters": chapters,
        "warnings": warnings_for(probe) + youtube_chapter_warnings(chapters) if chapters else warnings_for(probe),
    }
    if not video:
        timeline["warnings"].append("audio-only source: width/height/fps default to 1920x1080 at 30 fps; "
                                    "render with --aspect / --width to choose the frame.")
    for w in timeline["warnings"]:
        info(f"warning: {w}")

    out.parent.mkdir(parents=True, exist_ok=True)
    import json
    out.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    speech_total = sum(e - s for s, e in speech)
    emit({"output": str(out), "commands": commands, "verified": True,
          "summary": {"duration": timeline["source"]["duration"], "fps": timeline["source"]["fps"],
                      "size": f"{timeline['source']['width']}x{timeline['source']['height']}",
                      "scenes": len(scenes), "silences": len(silences),
                      "speech_seconds": round(speech_total, 3), "peaks": len(peaks),
                      "captions": len(captions), "chapters": len(chapters), "beats": bool(beats and beats.get("usable")),
                      "tempo_bpm": (beats or {}).get("tempo_bpm"), "highlights": len(highlights),
                      "clips": len(clips) or 1, "words": len(words)},
          "warnings": timeline["warnings"]},
         f"wrote {out}: {timeline['source']['duration']}s, {len(scenes)} scenes, {len(silences)} silences "
         f"(speech {speech_total:.2f}s), {len(peaks)} peaks, {len(captions)} captions")


if __name__ == "__main__":
    main()
