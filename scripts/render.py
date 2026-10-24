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
    p.add_argument("--concurrency", help="Remotion --concurrency (number or percentage)")
    p.add_argument("--no-look", action="store_true", help="skip the contact sheet")
    p.add_argument("--overlay", action="store_true",
                   help="draw the graphics only as a transparent ProRes 4444 layer and composite it over the "
                        "untouched source with ffmpeg-skill overlay.py (Captioned / PeakPulse, source frame only); "
                        "with --keep-graphics the layer is kept for an editing app (Premiere, Resolve, Final Cut)")
    p.add_argument("--keep-graphics", action="store_true", help="with --overlay: keep the transparent graphics .mov")
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

    if a.overlay:
        if a.comp == "Jumpcut":
            die("--overlay cannot do Jumpcut: its cuts and punch-in zooms move the picture itself", "input")
        if a.aspect not in (None, "source") or a.width is not None or a.fit not in (None, "contain"):
            die("--overlay draws on the source's own frame: drop --aspect / --width / --fit", "input")
        if a.fast or a.codec != "h264" or frames:
            die("--overlay renders the full length at full size to H.264: drop --fast / --codec / --frames", "input")
        if not timeline["source"].get("has_video"):
            die("--overlay needs a video source to composite onto", "input")

    props_path, frame, font_note = prepare_props(project, a.comp, timeline, options, a)
    if font_note:
        info(font_note)
    graphics = output.with_name(output.stem + ".graphics.mov") if a.overlay else output
    cmd = remotion_render_cmd(project, a.comp, graphics, props_path, a)
    ov_args = [timeline["source"]["path"], "--video", str(graphics), "--position", "0,0", "--margin", "0",
               "-o", str(output)] + (["--overwrite"] if STATE.overwrite else [])
    if STATE.dry_run:
        plan = [shell_join(cmd)] + ([shell_join(ffskill_cmd("overlay", ov_args))] if a.overlay else [])
        emit({"output": str(output), "commands": plan, "props": str(props_path),
              "expected_frames": (frames[1] - frames[0] + 1) if frames else expected_frames(a.comp, timeline),
              "frame": frame, "font": font_note},
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
    if a.overlay:
        info(f"compositing the graphics over the source with ffmpeg-skill overlay.py -> {output}")
        ov = ffskill("overlay", ov_args)
        commands.append(ov["_command"])
        if not a.keep_graphics:
            graphics.unlink(missing_ok=True)

    probe = ffskill("probe", [str(output)])
    ok, rows = verify(probe, timeline, a.comp, frames, a.fast, frame)
    look: Optional[str] = None
    commands.append(probe["_command"])
    if not a.no_look:
        lk = ffskill("look", [str(output), "--tiles", "3x2"], allow_fail=True)
        if lk.get("status") == "completed":
            look = lk.get("output")
            commands.append(lk.get("_command", ""))
    v = probe.get("video") or {}
    summary = (f"{output.name}: {float(probe.get('duration') or 0):.2f} s, {v.get('width')}x{v.get('height')}, "
               f"{v.get('fps')} fps, {'audio' if probe.get('audio') else 'no audio'}")
    result = {"status": "completed" if ok else "failed", "output": str(output), "verified": ok,
              "verification": rows, "commands": commands, "look": look, "summary": summary,
              "frame": frame, "font": font_note, "mode": "overlay" if a.overlay else "full",
              "graphics": str(graphics) if a.overlay and a.keep_graphics else None,
              "kind": None if ok else "failed"}
    table = "\n".join(f"  {r['check']:<9} {r['status']:<4}  {r['value']} (expected {r['expected']})" for r in rows)
    emit(result, summary + "\n" + table + (f"\nLook: {look}" if look else "") +
         ("" if ok else "\nverification FAILED: " + ", ".join(r["check"] for r in rows if r["status"] == "FAIL")))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
