#!/usr/bin/env python3
"""Render a composition from a measured timeline with Remotion, then verify the result with
ffmpeg-skill: probe the output against the frame count, fps and size the timeline implies,
and pull a contact sheet (look.py) so the picture can be checked before anything ships.

Examples:
  python3 render.py --project ./motion --comp Captioned --timeline talk.timeline.json -o captioned.mp4
  python3 render.py --project ./motion --comp Jumpcut --timeline talk.timeline.json --options look.json
  python3 render.py --project ./motion --comp PeakPulse --timeline tl.json --frames 0-89 --fast
  python3 render.py --project ./motion --comp Captioned --timeline tl.json --codec prores -o master.mov
"""
import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _sparse
from _common import (BUILTIN_COMPOSITIONS, STATE, add_common, add_frame_args, apply_common, die, emit, expected_frames,
                     ffskill, ffskill_cmd, frame_size, info, load_options, load_timeline, prepare_props, refuse_existing,
                     remotion_bin, require_ffmpeg_skill, require_project, remotion_error, run, shell_join)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--project", required=True, help="Remotion project folder made by init.py")
    p.add_argument("--comp", required=True,
                   help=f"composition id ({', '.join(BUILTIN_COMPOSITIONS)}, or one you added)")
    p.add_argument("--timeline", required=True, help="timeline.json written by analyze.py")
    p.add_argument("--options", help="JSON object of look-and-feel options (see references/timeline.md)")
    p.add_argument("-o", "--output", help="output file (default: <source>_<comp>.mp4, .mov for prores)")
    p.add_argument("--codec", choices=["h264", "prores"], default="h264",
                   help="h264 (default) or prores (ProRes 422 HQ master, .mov)")
    p.add_argument("--crf", type=int, help="h264 quality (Remotion default 18; lower = better)")
    p.add_argument("--frames", help="render only this frame range, e.g. 0-89 (inclusive)")
    p.add_argument("--fast", action="store_true", help="preview quality: half resolution, quicker encode")
    p.add_argument("--concurrency", default="100%",
                   help="parallel browser tabs: a number up to the CPU cores, or a percentage (default 100%%: all "
                        "cores -- about twice as fast as Remotion's own default of half the cores)")
    p.add_argument("--no-look", action="store_true", help="skip the contact sheet")
    p.add_argument("--overlay", action="store_true",
                   help="draw the graphics only as a transparent ProRes 4444 layer and composite it over the "
                        "untouched source with ffmpeg-skill overlay.py (Captioned / PeakPulse, source frame only); "
                        "with --keep-graphics the layer is kept for an editing app (Premiere, Resolve, Final Cut)")
    p.add_argument("--keep-graphics", action="store_true", help="with --overlay: keep the transparent graphics .mov")
    p.add_argument("--sparse", action="store_true",
                   help="overlay mode that draws only the frames where captions show (Captioned / Karaoke) and "
                        "places each stretch at its time with ffmpeg-skill overlay.py --place: much faster on long "
                        "footage with gaps between captions. Falls back to the full-length layer (and says why) "
                        "when this ffmpeg-skill has no --place or the source does not start at 0")
    p.add_argument("--merge-gap", type=float, default=2.0,
                   help="with --sparse: captions closer than this many seconds are drawn as one stretch (default 2)")
    add_frame_args(p)
    add_common(p)
    return p


def parse_frames(spec: Optional[str]) -> Optional[Tuple[int, int]]:
    if not spec:
        return None
    try:
        a, b = (int(x) for x in spec.split("-", 1))
    except ValueError:
        die(f"--frames must look like 0-89, got {spec!r}", "input")
    if a < 0 or b < a:
        die(f"--frames range is empty or negative: {spec!r}", "input")
    return a, b


def remotion_render_cmd(project: Path, comp: str, output: Path, props: Path, a: argparse.Namespace) -> List[str]:
    if getattr(a, "overlay", False):
        # Transparent graphics layer: PNG frames keep the alpha, ProRes 4444 carries it.
        cmd = [str(remotion_bin(project)), "render", "src/index.ts", comp, str(output), f"--props={props}",
               "--codec=prores", "--prores-profile=4444", "--image-format=png", "--pixel-format=yuva444p10le",
               "--log=warn"]
        if a.frames:
            cmd.append(f"--frames={a.frames}")
        if a.concurrency:
            cmd.append(f"--concurrency={a.concurrency}")
        return cmd
    cmd = [str(remotion_bin(project)), "render", "src/index.ts", comp, str(output), f"--props={props}",
           f"--codec={a.codec}", "--log=warn"]
    if a.codec == "prores":
        cmd.append("--prores-profile=hq")
    if a.crf is not None and a.codec == "h264":
        cmd.append(f"--crf={a.crf}")
    if a.frames:
        cmd.append(f"--frames={a.frames}")
    if a.fast:
        cmd += ["--scale=0.5"]
        if a.codec == "h264" and a.crf is None:
            cmd.append("--crf=28")
    if a.concurrency:
        cmd.append(f"--concurrency={a.concurrency}")
    return cmd


def verify(out_probe: Dict[str, Any], timeline: Dict[str, Any], comp: str,
           frames: Optional[Tuple[int, int]], fast: bool,
           frame: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[Dict[str, Any]]]:
    src = timeline["source"]
    fps = float(src["fps"])
    v = out_probe.get("video") or {}
    rows: List[Dict[str, Any]] = []

    def row(name: str, ok: bool, value: Any, expected: Any) -> None:
        rows.append({"check": name, "status": "PASS" if ok else "FAIL", "value": value, "expected": expected})

    scale = 0.5 if fast else 1.0
    fw, fh = frame_size(timeline, frame)
    ew, eh = int(round(fw * scale)), int(round(fh * scale))
    # Remotion rounds odd scaled sizes to even numbers for H.264.
    row("size", abs(int(v.get("width") or 0) - ew) <= 1 and abs(int(v.get("height") or 0) - eh) <= 1,
        f"{v.get('width')}x{v.get('height')}", f"{ew}x{eh}")
    out_fps = float(v.get("fps") or 0)
    row("fps", abs(out_fps - fps) < 0.01, out_fps, fps)

    want = (frames[1] - frames[0] + 1) if frames else expected_frames(comp, timeline)
    duration = float(out_probe.get("duration") or v.get("duration") or 0)
    nb = v.get("nb_frames")
    if want is not None and isinstance(nb, int) and nb > 0:
        # The video stream's own frame count: exact, unaffected by audio padding.
        row("frames", nb == want, nb, want)
    elif want is not None:
        want_s = want / fps
        # No frame count in the container: one frame of slack plus AAC priming/padding (~1024 samples).
        row("duration", abs(duration - want_s) <= (1.0 / fps) + 0.05, round(duration, 3), round(want_s, 3))
    else:
        rows.append({"check": "duration", "status": "INFO", "value": round(duration, 3),
                     "expected": "custom composition: no built-in expectation"})
    if src.get("has_audio") and comp in BUILTIN_COMPOSITIONS:
        row("audio", bool(out_probe.get("audio")), "present" if out_probe.get("audio") else "missing", "present")
    return all(r["status"] != "FAIL" for r in rows), rows


def ffskill_can_place() -> bool:
    """Whether this ffmpeg-skill's overlay.py has --place (ffmpeg-skill PR #353)."""
    import subprocess
    try:
        proc = subprocess.run(ffskill_cmd("overlay", ["--help"]), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "--place" in (proc.stdout or "")


def sparse_plan(timeline: Dict[str, Any], a: argparse.Namespace) -> Dict[str, Any]:
    """What --sparse will draw, or why it falls back to the full-length layer."""
    src = timeline["source"]
    fps = float(src["fps"])
    total = expected_frames(a.comp, timeline) or 1
    plan: Dict[str, Any] = {"used": False, "reason": None, "stretches": 0, "drawn_frames": total,
                            "source_frames": total, "timeline": None, "place": []}
    stretches = _sparse.caption_stretches(timeline, a.merge_gap)
    start = None
    if stretches and src.get("path") and not STATE.dry_run:
        # the source as it is now (older timelines do not record where its first picture sits)
        start = (ffskill("probe", [str(src["path"])], allow_fail=True).get("video") or {}).get("start_time")
    if not stretches:
        plan["reason"] = "no captions to draw"
    elif len(stretches) > _sparse.MAX_STRETCHES:
        plan["reason"] = (f"{len(stretches)} caption stretches (over {_sparse.MAX_STRETCHES}); raise --merge-gap")
    elif isinstance(start, (int, float)) and abs(start) > 0.5 / fps:
        plan["reason"] = (f"the source's first picture is at {start:.3f} s, not 0: placed stretches would be "
                          "shifted by that much")
    elif not ffskill_can_place():
        plan["reason"] = "this ffmpeg-skill's overlay.py has no --place yet (update ffmpeg-skill)"
    else:
        packed, layout = _sparse.pack(timeline, stretches)
        drawn = _sparse.packed_frames(layout)
        if drawn >= total:
            plan["reason"] = "captions cover the whole source: nothing to skip"
        else:
            plan.update(used=True, stretches=len(layout), drawn_frames=drawn, timeline=packed,
                        place=_sparse.place_args(layout, fps))
    if plan["reason"]:
        info(f"--sparse: drawing the full length instead ({plan['reason']})")
    else:
        info(f"--sparse: drawing {plan['drawn_frames']} of {total} frames in {plan['stretches']} stretch(es)")
    return plan


def main() -> None:
    a = build_parser().parse_args()
    apply_common(a)
    timeline_path = Path(a.timeline).expanduser()
    timeline = load_timeline(timeline_path)
    project = require_project(Path(a.project).expanduser(), need_install=not STATE.dry_run)
    options = load_options(a.options)
    frames = parse_frames(a.frames)
    require_ffmpeg_skill()

    ext = ".mov" if a.codec == "prores" else ".mp4"
    if a.output:
        output = Path(a.output).expanduser()
        if a.codec == "prores" and output.suffix.lower() != ".mov":
            die("--codec prores needs a .mov output", "input")
    else:
        stem = Path(timeline["source"].get("name") or "render").stem
        output = timeline_path.with_name(f"{stem}_{a.comp}{ext}")
    output = output.resolve()
    refuse_existing(output)

    if a.sparse:
        if a.comp not in _sparse.SPARSE_COMPOSITIONS:
            die(f"--sparse draws caption stretches only: {a.comp} is not one of "
                f"{', '.join(_sparse.SPARSE_COMPOSITIONS)} (use --overlay for the full-length layer)", "input")
        if a.merge_gap < 0:
            die("--merge-gap cannot be negative", "input")
        a.overlay = True
    if a.overlay:
        if a.comp in ("Jumpcut", "Highlights", "BeatMontage"):
            die(f"--overlay cannot do {a.comp}: its cuts move the picture itself (overlay works for "
                "Captioned, PeakPulse, Titled, Karaoke)", "input")
        if a.aspect not in (None, "source") or a.width is not None or a.fit not in (None, "contain"):
            die("--overlay draws on the source's own frame: drop --aspect / --width / --fit", "input")
        if a.fast or a.codec != "h264" or frames:
            die("--overlay renders the full length at full size to H.264: drop --fast / --codec / --frames", "input")
        if not timeline["source"].get("has_video"):
            die("--overlay needs a video source to composite onto", "input")

    sparse = sparse_plan(timeline, a) if a.sparse else None
    drawn = sparse["timeline"] if sparse and sparse["used"] else timeline
    props_path, frame, font_note = prepare_props(project, a.comp, drawn, options, a)
    if font_note:
        info(font_note)
    graphics = output.with_name(output.stem + ".graphics.mov") if a.overlay else output
    cmd = remotion_render_cmd(project, a.comp, graphics, props_path, a)
    ov_args = [timeline["source"]["path"], "--video", str(graphics), "--position", "0,0", "--margin", "0",
               "-o", str(output)] + (["--overwrite"] if STATE.overwrite else [])
    if sparse and sparse["used"]:
        ov_args += sparse["place"]
    sparse_note = None if not sparse else {k: sparse[k] for k in ("used", "reason", "stretches", "drawn_frames",
                                                                  "source_frames")}
    if STATE.dry_run:
        plan = [shell_join(cmd)] + ([shell_join(ffskill_cmd("overlay", ov_args))] if a.overlay else [])
        emit({"output": str(output), "commands": plan, "props": str(props_path),
              "expected_frames": (frames[1] - frames[0] + 1) if frames else expected_frames(a.comp, timeline),
              "frame": frame, "font": font_note, "sparse": sparse_note},
             f"would render {a.comp} -> {output}")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    if a.overlay and graphics.exists():
        graphics.unlink()
    info(f"rendering {a.comp} with Remotion -> {graphics}")
    proc = run(cmd, cwd=project)
    if proc.returncode != 0 or not graphics.is_file() or graphics.stat().st_size == 0:
        tail = remotion_error((proc.stderr or "") + "\n" + (proc.stdout or ""))
        die(f"Remotion render failed (exit {proc.returncode}):\n{tail}", "failed", command=shell_join(cmd))
    commands = [shell_join(cmd)]
    if sparse and sparse["used"]:
        # the packed layer must hold exactly the frames the placements read
        gp = ffskill("probe", [str(graphics)])
        nb = (gp.get("video") or {}).get("nb_frames")
        if isinstance(nb, int) and nb != sparse["drawn_frames"]:
            die(f"--sparse: the drawn layer has {nb} frames, the placements expect {sparse['drawn_frames']}",
                "failed", command=shell_join(cmd))
    if a.overlay:
        info(f"compositing the graphics over the source with ffmpeg-skill overlay.py -> {output}")
        ov = ffskill("overlay", ov_args)
        commands.append(ov["_command"])
        if not a.keep_graphics:
            graphics.unlink(missing_ok=True)

    probe = ffskill("probe", [str(output)])
    ok, rows = verify(probe, timeline, a.comp, frames, a.fast, frame)
    look: Optional[str] = None
    look_error: Optional[str] = None
    commands.append(probe["_command"])
    if not a.no_look:
        lk = ffskill("look", [str(output), "--tiles", "3x2"], allow_fail=True)
        if lk.get("status") == "completed":
            look = lk.get("output")
            if look and not Path(look).is_absolute():
                look = str((Path.cwd() / look).resolve())
            commands.append(lk.get("_command", ""))
        else:
            look_error = f"{lk.get('kind') or 'failed'}: {str(lk.get('error') or '')[-400:]}"
            if "drawtext" in look_error:
                look_error += (" -- this FFmpeg build has no drawtext filter. macOS Homebrew: `brew install ffmpeg-full` "
                               "(the plain ffmpeg formula dropped it); use still.py frames to look meanwhile")
            info(f"warning: contact sheet failed ({look_error}); view the render itself")
    v = probe.get("video") or {}
    summary = (f"{output.name}: {float(probe.get('duration') or 0):.2f} s, {v.get('width')}x{v.get('height')}, "
               f"{v.get('fps')} fps, {'audio' if probe.get('audio') else 'no audio'}")
    result = {"status": "completed" if ok else "failed", "output": str(output), "verified": ok,
              "verification": rows, "commands": commands, "look": look, "summary": summary,
              "frame": frame, "font": font_note, "mode": "overlay" if a.overlay else "full", "look_error": look_error,
              "graphics": str(graphics) if a.overlay and a.keep_graphics else None, "sparse": sparse_note,
              "kind": None if ok else "failed",
              "error": None if ok else "verification failed: " + ", ".join(r["check"] for r in rows if r["status"] == "FAIL")}
    table = "\n".join(f"  {r['check']:<9} {r['status']:<4}  {r['value']} (expected {r['expected']})" for r in rows)
    emit(result, summary + "\n" + table + (f"\nLook: {look}" if look else "") +
         ("" if ok else "\nverification FAILED: " + ", ".join(r["check"] for r in rows if r["status"] == "FAIL")))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
