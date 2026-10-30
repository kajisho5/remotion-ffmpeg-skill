#!/usr/bin/env python3
"""Measure a source video with ffmpeg-skill and write a timeline.json that the Remotion
compositions read as props: real duration/fps/size, scene cuts, silences and the speech
ranges between them, audio peaks, an optional beat grid, and captions from a file.

Every number comes from a measurement (ffmpeg-skill's probe.py / scenes.py / silence.py);
nothing is guessed. A source Remotion cannot draw on faithfully -- variable frame rate (it renders
on a fixed frame grid) or HDR / BT.2020 (the browser composites in SDR) -- is refused, or with
--conform first made into a constant-frame-rate, SDR BT.709 copy by ffmpeg-skill (fit.py --fps,
color.py --to-sdr); that copy is measured and drawn on, the original is never modified, and the
timeline's `conform` records the steps.
Several inputs are joined first with ffmpeg-skill join.py (size, fps and audio normalised to the
first clip) and measured as one source; the clip boundaries are kept in the timeline.

Examples:
  python3 analyze.py talk.mp4                              # -> talk.timeline.json
  python3 analyze.py talk.mp4 --captions talk.srt -o tl.json
  python3 analyze.py music.mp4 --beats                     # also measure the beat grid
  python3 analyze.py talk.mp4 --threshold -42 --min-silence 0.8   # quiet room
  python3 analyze.py intro.mp4 talk.mov outro.mp4 --captions all.srt  # joined, then measured
  python3 analyze.py talk.mp4 --words talk.transcript.json   # captions from a transcription-skill transcript
  python3 analyze.py phone_hdr.mov --conform                  # VFR / HDR: measure and draw on a CFR SDR copy
"""
import argparse
import hashlib
import shutil
import sys
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (STATE, TIMELINE_SCHEMA, SKILL_ID, add_common, apply_common, default_output, die,
                     emit, ffmpeg_skill_version, ffskill, ffskill_cmd, info, refuse_existing,
                     require_ffmpeg_skill, shell_join, version)
from _captions import (CaptionError, cues_from_words, parse_chapters, read_captions, read_word_timings,
                       youtube_chapter_warnings)

# seconds a transcript's duration may differ from the measured source (transcription-skill's own END_TOLERANCE)
TRANSCRIPT_DURATION_TOLERANCE = 0.5


def file_fingerprint(path: Path) -> str:
    """`sha256:<hex>` of the file bytes -- the identity transcription-skill writes to source.fingerprint."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


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
    p.add_argument("--words", help="word timings for the Karaoke and Captioned compositions: a transcription-skill "
                                    "transcript (schema transcription-skill/transcript/0.1, validated strictly) or whisper "
                                    "JSON with word timestamps; without --captions the cues are grouped from these words")
    p.add_argument("--chapters", metavar="FILE|source",
                   help="chapter list, one `TIME TITLE` per line (YouTube's format, the same file ffmpeg-skill "
                        "metadata.py --chapters writes into the container), or `source` for the chapters already "
                        "in the input file; titles are kept as written")
    p.add_argument("--pip", metavar="CAMERA",
                   help="a second recording (camera) for the Pip composition: picture-in-picture over the source. "
                        "The offset between the two is measured from their audio with ffmpeg-skill sync.py")
    p.add_argument("--pip-offset", type=float, metavar="SECONDS",
                   help="with --pip: the camera starts this many seconds after the source (negative: before), "
                        "instead of measuring it -- for a camera without usable audio")
    p.add_argument("--pip-max-offset", type=float, default=30.0,
                   help="with --pip: largest offset sync.py searches, in seconds (default 30)")
    p.add_argument("--conform", action="store_true",
                   help="a variable-frame-rate or HDR / BT.2020 source (or --pip camera) is first made into a "
                        "constant-frame-rate, SDR BT.709 copy with ffmpeg-skill (fit.py --fps, color.py --to-sdr: "
                        "tone-mapped, so the look changes) and everything is measured and drawn on that copy; the "
                        "original is never modified. Without it such a source is refused")
    p.add_argument("--conformed", metavar="FILE",
                   help="with --conform: where the conformed copy of the source goes (default: <name>_conformed.mp4)")
    p.add_argument("--conform-fps", type=float, metavar="FPS",
                   help="with --conform: the constant frame rate for a VFR source (default: the stream's base rate, "
                        "r_frame_rate, so no frame is dropped)")
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
    """What the source can still be drawn on but deserves a look. VFR and HDR are not here: they are
    conformed (--conform) or refused before anything is measured (conform_needs)."""
    w: List[str] = []
    v = probe.get("video") or {}
    if v.get("rotation"):
        w.append(f"source is rotated {v.get('rotation')} degrees by metadata; check the first still.py frame.")
    fps = v.get("fps")
    if fps and abs(fps - round(fps)) > 1e-3 and abs(fps * 1001 / 1000 - round(fps * 1001 / 1000)) > 1e-3:
        w.append(f"unusual frame rate {fps}: the compositions use it as-is.")
    return w


# ---------------------------------------------------------------- conform (VFR -> CFR, HDR -> SDR)

def conform_needs(probe: Dict[str, Any]) -> List[str]:
    """Why Remotion cannot draw on this video as it is: "vfr" (it renders on a fixed frame grid, so
    cuts and captions drift), "hdr" (a PQ / HLG / Dolby Vision signal, or BT.2020 primaries: Chrome
    composites in SDR BT.709, so the picture comes out washed out). Empty = draw on it as it is."""
    v = probe.get("video") or {}
    needs: List[str] = []
    if v.get("variable_frame_rate_suspected"):
        needs.append("vfr")
    if v.get("hdr") or v.get("hdr_signal") or v.get("bt2020_or_hdr"):
        needs.append("hdr")
    return needs


def conform_rate(v: Dict[str, Any], override: Optional[float]) -> float:
    """The constant rate a VFR source is conformed to: --conform-fps, else the stream's base rate
    (r_frame_rate, the finest grid its frames sit on, so none is dropped; gaps repeat the previous
    frame), else its average. Within 0.02 of a whole number it is that number (as ffmpeg-skill's
    cfr_args rounds)."""
    if override:
        return float(override)
    rate: Optional[float] = None
    try:
        r = float(Fraction(str(v.get("r_frame_rate") or "")))
        rate = r if 1.0 <= r <= 120.0 else None
    except (ValueError, ZeroDivisionError):
        rate = None
    rate = rate or float(v.get("fps") or 0) or 30.0
    return float(round(rate)) if abs(rate - round(rate)) < 0.02 else round(rate, 3)


def describe_needs(needs: List[str], v: Dict[str, Any]) -> str:
    parts = []
    if "vfr" in needs:
        parts.append(f"variable frame rate (r_frame_rate {v.get('r_frame_rate')}, average {v.get('avg_frame_rate')}): "
                     "Remotion renders on a fixed frame grid, so cuts and captions would drift")
    if "hdr" in needs:
        parts.append(f"{v.get('hdr_format') or 'HDR / BT.2020'} (transfer {v.get('color_transfer')}, primaries "
                     f"{v.get('color_primaries')}): Remotion composites in SDR BT.709, so the picture would look "
                     "washed out")
    return "; ".join(parts)


def refuse_unconformed(label: str, path: Path, needs: List[str], v: Dict[str, Any]) -> None:
    fixes = []
    if "vfr" in needs:
        fixes.append(f"a constant {conform_rate(v, None):g} fps copy (ffmpeg-skill fit.py --fps)")
    if "hdr" in needs:
        fixes.append("an SDR BT.709 copy (ffmpeg-skill color.py --to-sdr; tone-mapped, so the look changes)")
    die(f"{label} {path.name} is {describe_needs(needs, v)}. Re-run with --conform to measure and draw on "
        f"{' and '.join(fixes)} -- the original is never modified -- or give a source that is already "
        "constant-frame-rate SDR", "input", conform_needed=needs)


def conform_plan(src: Path, v: Dict[str, Any], needs: List[str], out: Path, tmp: Path,
                 fps: Optional[float]) -> List[Tuple[str, str, List[str]]]:
    """(reason, ffmpeg-skill script, args) in order. VFR first: color.py on a VFR input would conform it
    to the *average* rate itself; fit.py --fps keeps HDR (x265 Main10), so color.py then tone-maps once."""
    steps: List[Tuple[str, str, List[str]]] = []
    cur = src
    if "vfr" in needs:
        dest = tmp if "hdr" in needs else out
        steps.append(("vfr", "fit", [str(cur), "--fps", f"{conform_rate(v, fps):g}", "-o", str(dest)]
                      + (["--overwrite"] if dest == out and STATE.overwrite else [])))
        cur = dest
    if "hdr" in needs:
        steps.append(("hdr", "color", [str(cur), "--to-sdr", "-o", str(out)] + (["--overwrite"] if STATE.overwrite else [])))
    return steps


def conform_source(label: str, src: Path, probe: Dict[str, Any], out: Path, fps: Optional[float],
                   commands: List[str]) -> Tuple[Path, Dict[str, Any], Dict[str, Any]]:
    """Make the CFR / SDR BT.709 copy with ffmpeg-skill, re-measure it and refuse it unless the measured
    result is what was asked for. Returns (copy, its probe, the provenance record for the timeline)."""
    v = probe.get("video") or {}
    needs = conform_needs(probe)
    if src.resolve() == out.resolve():
        die(f"--conformed {out} is the {label} itself: the original is never overwritten", "input")
    refuse_existing(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rate = conform_rate(v, fps) if "vfr" in needs else None
    info(f"conforming {label} {src.name}: {describe_needs(needs, v)} -> {out}")
    tmpdir = Path(tempfile.mkdtemp(prefix=".rfs-conform-", dir=str(out.parent)))
    steps: List[Dict[str, Any]] = []
    try:
        for reason, script, args in conform_plan(src, v, needs, out, tmpdir / "cfr.mp4", fps):
            res = ffskill(script, args)
            commands.append(res["_command"])
            steps.append({"reason": reason, "tool": f"ffmpeg-skill {script}.py",
                          "args": [a for a in args if a != "--overwrite"], "command": res["_command"],
                          "notes": res.get("notes") or []})
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    after = ffskill("probe", [str(out)])
    commands.append(after["_command"])
    av = after.get("video") or {}
    problems = []
    if av.get("variable_frame_rate_suspected"):
        problems.append(f"still variable frame rate ({av.get('r_frame_rate')} vs {av.get('avg_frame_rate')})")
    if rate is not None and abs(float(av.get("fps") or 0) - rate) > 0.01:
        problems.append(f"{av.get('fps')} fps, not the {rate:g} asked for")
    if "hdr" in needs and (conform_needs(after) or av.get("color_transfer") != "bt709"
                           or av.get("color_primaries") != "bt709"):
        problems.append(f"not SDR BT.709 (transfer {av.get('color_transfer')}, primaries {av.get('color_primaries')})")
    before_d = float(probe.get("duration") or v.get("duration") or 0)
    after_d = float(after.get("duration") or av.get("duration") or 0)
    if abs(after_d - before_d) > TRANSCRIPT_DURATION_TOLERANCE:
        problems.append(f"{after_d:.3f} s long, the {label} is {before_d:.3f} s")
    if problems:
        die(f"the conformed copy {out} of {src.name} does not measure as asked: {'; '.join(problems)}", "failed",
            commands=commands)
    record = {
        "reasons": needs,
        "original": {"path": str(src.resolve()), "name": src.name, "fingerprint": file_fingerprint(src),
                     "duration": round(before_d, 3), "fps": v.get("fps"), "r_frame_rate": v.get("r_frame_rate"),
                     "avg_frame_rate": v.get("avg_frame_rate"),
                     "variable_frame_rate_suspected": bool(v.get("variable_frame_rate_suspected")),
                     "hdr_format": v.get("hdr_format"), "color_transfer": v.get("color_transfer"),
                     "color_primaries": v.get("color_primaries"), "color_space": v.get("color_space")},
        "output": str(out.resolve()),
        "steps": steps,
        "measured": {"duration": round(after_d, 3), "fps": av.get("fps"), "r_frame_rate": av.get("r_frame_rate"),
                     "avg_frame_rate": av.get("avg_frame_rate"),
                     "variable_frame_rate_suspected": bool(av.get("variable_frame_rate_suspected")),
                     "color_transfer": av.get("color_transfer"), "color_primaries": av.get("color_primaries"),
                     "color_space": av.get("color_space"), "pix_fmt": av.get("pix_fmt")},
    }
    return out, after, record


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
    if (a.conformed or a.conform_fps is not None) and not a.conform:
        die("--conformed / --conform-fps need --conform", "input")
    if a.conform_fps is not None and not 0 < a.conform_fps <= 240:
        die(f"--conform-fps must be between 0 and 240, got {a.conform_fps:g}", "input")
    conformed: Path = (Path(a.conformed).expanduser() if a.conformed
                       else default_output(joined if len(inputs) > 1 else src, "_conformed", ".mp4"))
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
    transcript: Optional[Dict[str, Any]] = None
    if a.words:
        wpath = Path(a.words).expanduser()
        if not wpath.is_file():
            die(f"word timings file not found: {wpath}", "input")
        try:
            timed = read_word_timings(wpath)
        except (CaptionError, ValueError) as e:
            die(f"cannot read {wpath}: {e}", "input")
        words = timed["words"]
        if timed["cues"] is not None:
            transcript = timed
        if not captions:
            captions = timed["cues"] if transcript else cues_from_words(words)

    join_args = [*map(str, inputs), "-o", str(joined), "--transition", a.join_transition,
                 "--duration", str(a.join_duration)] + (["--overwrite"] if STATE.overwrite else [])
    plan = ([shell_join(ffskill_cmd("join", join_args))] if len(inputs) > 1 else []) + \
        [shell_join(ffskill_cmd("probe", [str(joined if len(inputs) > 1 else src)]))]
    if STATE.dry_run:
        target = str(joined if len(inputs) > 1 else src)
        note = None
        if len(inputs) == 1:
            # Reading the source writes nothing: plan the conform steps (or refuse) exactly as a run would.
            pr = ffskill("probe", [str(src)])
            needs = conform_needs(pr)
            if needs and not a.conform:
                refuse_unconformed("source", src, needs, pr.get("video") or {})
            if needs:
                plan += [shell_join(ffskill_cmd(script, args)) for _, script, args in
                         conform_plan(src, pr.get("video") or {}, needs, conformed,
                                      conformed.parent / ".rfs-conform-XXXX" / "cfr.mp4", a.conform_fps)]
                plan.append(shell_join(ffskill_cmd("probe", [str(conformed)])))
                target = str(conformed)
        else:
            note = "a variable-frame-rate or HDR joined file is conformed (--conform) or refused once it is measured"
        if not a.no_scenes:
            plan.append(shell_join(ffskill_cmd("scenes", [target, *scene_args(a)])))
        if not a.no_silence:
            plan.append(shell_join(ffskill_cmd("silence", [target, *silence_args(a)])))
        emit({"output": str(out), "commands": plan, **({"note": note} if note else {})},
             f"would write {out} after {len(plan)} ffmpeg-skill steps")
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
    commands = pre_commands + [probe["_command"]]
    measured_from = src
    conform: Optional[Dict[str, Any]] = None
    needs = conform_needs(probe)
    if needs and not a.conform:
        refuse_unconformed("joined source" if clips else "source", src, needs, probe.get("video") or {})
    if needs:
        src, probe, conform = conform_source("joined source" if clips else "source", src, probe, conformed,
                                             a.conform_fps, commands)
    video, audio = probe.get("video"), probe.get("audio")
    duration = float(probe.get("duration") or (video or {}).get("duration") or (audio or {}).get("duration") or 0)
    if duration <= 0:
        die(f"{src} has no measurable duration", "input")
    if clips:
        # The last boundary is the measured joined duration (encoders can round the tail by a frame).
        clips[-1]["end"] = round(duration, 3)

    transcript_warnings: List[str] = []
    if transcript:
        # The transcript's times are seconds on the file it was made from: a different length means a
        # different file, and its words would land in the wrong places.
        if abs(transcript["duration"] - duration) > TRANSCRIPT_DURATION_TOLERANCE:
            die(f"--words: the transcript is of a {transcript['duration']:.3f} s file ({transcript['filename']}), "
                f"the source measures {duration:.3f} s; transcribe this source (or the joined file)", "input")
        # A conformed copy keeps the original's times: the transcript of the original still fits it.
        if transcript["fingerprint"] not in {file_fingerprint(src), (conform or {}).get("original", {}).get("fingerprint")}:
            transcript_warnings.append(
                f"--words: the transcript was made from {transcript['filename']}, not these exact bytes "
                f"(same length, so its times are used as written)")
        transcript_warnings += transcript["warnings"]

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

    pip: Optional[Dict[str, Any]] = None
    if a.pip_offset is not None and not a.pip:
        die("--pip-offset needs --pip", "input")
    if a.pip:
        cam = Path(a.pip).expanduser()
        if not cam.is_file():
            die(f"--pip file not found: {cam}", "input")
        cp = ffskill("probe", [str(cam)])
        commands.append(cp["_command"])
        cv = cp.get("video") or {}
        if not cv:
            die(f"--pip {cam} has no video stream", "input")
        cam_needs = conform_needs(cp)
        cam_conform: Optional[Dict[str, Any]] = None
        if cam_needs and not a.conform:
            refuse_unconformed("--pip camera", cam, cam_needs, cv)
        if cam_needs:
            cam, cp, cam_conform = conform_source("--pip camera", cam, cp, default_output(cam, "_conformed", ".mp4"),
                                                  a.conform_fps, commands)
            cv = cp.get("video") or {}
        pip = {"path": str(cam.resolve()), "name": cam.name,
               "duration": round(float(cv.get("duration") or cp.get("duration") or 0), 3),
               "width": int(cv.get("width") or 0), "height": int(cv.get("height") or 0),
               "fps": float(cv.get("fps") or 0), "offset": 0.0, "confidence": None, "measured": False,
               "conform": cam_conform}
        if a.pip_offset is not None:
            pip["offset"] = round(float(a.pip_offset), 4)
        elif not (audio and cp.get("audio")):
            die("--pip: both recordings need audio to measure their offset; give --pip-offset SECONDS instead",
                "input")
        else:
            sy = ffskill("sync", [str(src), str(cam), "--max-offset", str(a.pip_max_offset)])
            commands.append(sy["_command"])
            pip.update(offset=round(float(sy.get("offset_seconds") or 0), 4),
                       confidence=sy.get("confidence"), measured=True)
        if pip["offset"] >= duration or pip["offset"] + pip["duration"] <= 0:
            die(f"--pip: with an offset of {pip['offset']:g} s the camera never overlaps the source", "input")

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
        "pip": pip,
        # Provenance of a conformed source (--conform): the original, each ffmpeg-skill step, the measured copy.
        "conform": conform,
        "warnings": warnings_for(probe) + (youtube_chapter_warnings(chapters) if chapters else []) + transcript_warnings,
    }
    if pip and pip["measured"] and (pip["confidence"] or 0) < 0.3:
        timeline["warnings"].append(f"pip: the measured offset ({pip['offset']:g} s) has low confidence "
                                    f"({pip['confidence']}); check a still, or set it with --pip-offset")
    if not video:
        timeline["warnings"].append("audio-only source: width/height/fps default to 1920x1080 at 30 fps; "
                                    "render with --aspect / --width to choose the frame.")
    for w in timeline["warnings"]:
        info(f"warning: {w}")
    for st in (conform or {}).get("steps", []):
        for n in st["notes"]:
            info(f"conform: {n}")

    out.parent.mkdir(parents=True, exist_ok=True)
    import json
    out.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    speech_total = sum(e - s for s, e in speech)
    emit({"output": str(out), "commands": commands, "verified": True,
          "summary": {"duration": timeline["source"]["duration"], "fps": timeline["source"]["fps"],
                      "size": f"{timeline['source']['width']}x{timeline['source']['height']}",
                      "scenes": len(scenes), "silences": len(silences),
                      "speech_seconds": round(speech_total, 3), "peaks": len(peaks),
                      "captions": len(captions), "chapters": len(chapters),
                      "pip_offset": pip["offset"] if pip else None, "beats": bool(beats and beats.get("usable")),
                      "tempo_bpm": (beats or {}).get("tempo_bpm"), "highlights": len(highlights),
                      "clips": len(clips) or 1, "words": len(words),
                      "conformed": (conform or {}).get("reasons", [])},
          "warnings": timeline["warnings"]},
         f"wrote {out}: {timeline['source']['duration']}s, {len(scenes)} scenes, {len(silences)} silences "
         f"(speech {speech_total:.2f}s), {len(peaks)} peaks, {len(captions)} captions"
         + (f"; measured and drawn on {src.name}, conformed ({' + '.join(conform['reasons'])}) from "
            f"{measured_from.name}" if conform else ""))


if __name__ == "__main__":
    main()
