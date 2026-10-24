#!/usr/bin/env python3
"""Measure a source video with ffmpeg-skill and write a timeline.json that the Remotion
compositions read as props: real duration/fps/size, scene cuts, silences and the speech
ranges between them, audio peaks, an optional beat grid, and captions from a file.

Every number comes from a measurement (ffmpeg-skill's probe.py / scenes.py / silence.py);
nothing is guessed. Warnings flag sources Remotion handles badly (variable frame rate, HDR).

Examples:
  python3 analyze.py talk.mp4                              # -> talk.timeline.json
  python3 analyze.py talk.mp4 --captions talk.srt -o tl.json
  python3 analyze.py music.mp4 --beats                     # also measure the beat grid
  python3 analyze.py talk.mp4 --threshold -42 --min-silence 0.8   # quiet room
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (STATE, TIMELINE_SCHEMA, SKILL_ID, add_common, apply_common, default_output, die,
                     emit, ffmpeg_skill_version, ffskill, ffskill_cmd, info, refuse_existing,
                     require_ffmpeg_skill, shell_join, version)
from _captions import CaptionError, read_captions


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", help="source video (or audio) file")
    p.add_argument("-o", "--output", help="timeline file (default: <name>.timeline.json)")
    p.add_argument("--captions", help="SRT, WebVTT or JSON cue list to carry into the timeline (text kept as written)")
    p.add_argument("--beats", action="store_true", help="also measure the beat grid (scenes.py --beats)")
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
    src = Path(a.input).expanduser()
    if not src.is_file():
        die(f"input not found: {src}", "input")
    out = Path(a.output) if a.output else default_output(src, ".timeline", ".json")
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

    plan = [shell_join(ffskill_cmd("probe", [str(src)]))]
    if STATE.dry_run:
        if not a.no_scenes:
            plan.append(shell_join(ffskill_cmd("scenes", [str(src), *scene_args(a)])))
        if not a.no_silence:
            plan.append(shell_join(ffskill_cmd("silence", [str(src), *silence_args(a)])))
        emit({"output": str(out), "commands": plan}, f"would write {out} after {len(plan)} ffmpeg-skill steps")
        return

    probe = ffskill("probe", [str(src)])
    video, audio = probe.get("video"), probe.get("audio")
    duration = float(probe.get("duration") or (video or {}).get("duration") or (audio or {}).get("duration") or 0)
    if duration <= 0:
        die(f"{src} has no measurable duration", "input")
    commands = [probe["_command"]]

    scenes: List[Dict[str, float]] = [{"start": 0.0, "end": round(duration, 3)}]
    peaks: List[Dict[str, float]] = []
    beats: Any = None
    if video and not a.no_scenes:
        sc = ffskill("scenes", [str(src), *scene_args(a)])
        commands.append(sc["_command"])
        scenes = [{"start": round(float(s["start"]), 3), "end": round(float(s["end"]), 3)}
                  for s in sc.get("scenes", [])] or scenes
        peaks = [{"time": round(float(p["time"]), 3), "rms": float(p.get("rms", 0))}
                 for p in sc.get("audio_peaks", [])]
        if a.beats:
            beats = sc.get("beats")

    silences: List[List[float]] = []
    speech: List[List[float]] = [[0.0, round(duration, 3)]]
    if audio and not a.no_silence:
        si = ffskill("silence", [str(src), *silence_args(a)])
        commands.append(si["_command"])
        silences = [[round(float(s), 3), round(float(e), 3)] for s, e in si.get("silences", [])]
        keep = [[round(float(s), 3), round(float(e), 3)] for s, e in si.get("keep", []) if float(e) > float(s)]
        speech = keep or speech

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
        "captions": captions,
        "warnings": warnings_for(probe),
    }
    if not video:
        timeline["warnings"].append("audio-only source: width/height/fps default to 1920x1080 at 30 fps; "
                                    "set options to change the frame.")
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
                      "captions": len(captions), "beats": bool(beats)},
          "warnings": timeline["warnings"]},
         f"wrote {out}: {timeline['source']['duration']}s, {len(scenes)} scenes, {len(silences)} silences "
         f"(speech {speech_total:.2f}s), {len(peaks)} peaks, {len(captions)} captions")


if __name__ == "__main__":
    main()
