#!/usr/bin/env python3
"""Render single frames of a composition as PNG -- the cheap check before a full render.
Pick frames by time (--at, seconds on the composition timeline) or by frame number.

Examples:
  python3 still.py --project ./motion --comp Captioned --timeline tl.json --at 1.2 --at 5.5
  python3 still.py --project ./motion --comp Jumpcut --timeline tl.json --frame 0 --frame 120
  python3 still.py --project ./motion --comp PeakPulse --timeline tl.json        # first, middle, last
"""
import argparse
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (BUILTIN_COMPOSITIONS, STATE, add_common, add_frame_args, apply_common, die, emit,
                     expected_frames, info, load_look, load_timeline, prepare_props, refuse_existing, remotion_bin,
                     require_project, remotion_error, run, sec_to_frames, shell_join)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--project", required=True, help="Remotion project folder made by init.py")
    p.add_argument("--comp", required=True, help=f"composition id ({', '.join(BUILTIN_COMPOSITIONS)}, or yours)")
    p.add_argument("--timeline", required=True, help="timeline.json written by analyze.py")
    p.add_argument("--options", help="JSON object of look-and-feel options")
    p.add_argument("--at", type=float, action="append", default=[], help="time in seconds (repeatable)")
    p.add_argument("--frame", type=int, action="append", default=[], help="frame number (repeatable)")
    p.add_argument("--out-dir", help="folder for the PNGs (default: next to the timeline)")
    add_frame_args(p)
    add_common(p)
    return p


def main() -> None:
    a = build_parser().parse_args()
    apply_common(a)
    tl_path = Path(a.timeline).expanduser()
    timeline = load_timeline(tl_path)
    project = require_project(Path(a.project).expanduser(), need_install=not STATE.dry_run)
    options = load_look(a)
    fps = float(timeline["source"]["fps"])

    frames: List[int] = list(a.frame) + [sec_to_frames(t, fps) for t in a.at]
    total = expected_frames(a.comp, timeline)
    if not frames:
        if total is None:
            die("custom composition: pass --frame or --at", "input")
        frames = sorted({0, total // 2, max(0, total - 1)})
    if total is not None:
        bad = [f for f in frames if f < 0 or f >= total]
        if bad:
            die(f"frame(s) {bad} outside the composition (0..{total - 1})", "input")

    out_dir = Path(a.out_dir).expanduser() if a.out_dir else tl_path.parent
    stem = Path(timeline["source"].get("name") or "still").stem
    props_path, frame, font_note = prepare_props(project, a.comp, timeline, options, a)
    if font_note:
        info(font_note)
    outputs, commands = [], []
    for f in frames:
        out = (out_dir / f"{stem}_{a.comp}_f{f:05d}.png").resolve()
        refuse_existing(out)
        cmd = [str(remotion_bin(project)), "still", "src/index.ts", a.comp, str(out),
               f"--props={props_path}", f"--frame={f}", "--log=warn"]
        commands.append(shell_join(cmd))
        if STATE.dry_run:
            outputs.append(str(out))
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        info(f"still frame {f} ({f / fps:.3f}s) -> {out}")
        proc = run(cmd, cwd=project)
        if proc.returncode != 0 or not out.is_file():
            tail = remotion_error((proc.stderr or "") + "\n" + (proc.stdout or ""))
            die(f"Remotion still failed for frame {f}:\n{tail}", "failed", command=shell_join(cmd))
        outputs.append(str(out))
    emit({"output": outputs[0] if outputs else None, "outputs": outputs, "frames": frames,
          "commands": commands, "verified": not STATE.dry_run, "frame": frame, "font": font_note},
         ("would write " if STATE.dry_run else "Look: ") + ", ".join(outputs))


if __name__ == "__main__":
    main()
