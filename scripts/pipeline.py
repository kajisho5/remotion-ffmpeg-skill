#!/usr/bin/env python3
"""The whole loop in one command: measure (analyze.py) -> draw (render.py) -> deliver and
check (deliver.py), each step verified before the next runs. Stops at the first failure
and says which step failed.

Examples:
  python3 pipeline.py talk.mp4 --project ./motion --comp Jumpcut --captions talk.srt --platform youtube
  python3 pipeline.py clip.mp4 --project ./motion --comp PeakPulse --platform reels --out-dir out/
  python3 pipeline.py talk.mp4 --project ./motion --comp Captioned --captions talk.srt   # no delivery step
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BUILTIN_COMPOSITIONS, HERE, STATE, add_common, apply_common, die, emit, info, shell_join
from deliver import PLATFORMS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", help="source video")
    p.add_argument("--project", required=True, help="Remotion project folder made by init.py")
    p.add_argument("--comp", required=True, help=f"composition id ({', '.join(BUILTIN_COMPOSITIONS)}, or yours)")
    p.add_argument("--captions", help="SRT / WebVTT / JSON cues for the timeline")
    p.add_argument("--options", help="JSON options file passed to the composition")
    p.add_argument("--platform", choices=PLATFORMS, help="deliver with this ffmpeg-skill template and check it")
    p.add_argument("--out-dir", help="where the timeline, render and deliverable go (default: next to the input)")
    p.add_argument("--beats", action="store_true", help="measure the beat grid too")
    p.add_argument("--fast", action="store_true", help="preview-quality render")
    add_common(p)
    return p


def step(name: str, script: str, args: List[str], steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    cmd = [sys.executable, str(HERE / f"{script}.py"), *args, "--json", "--timeout", str(STATE.timeout)]
    if STATE.overwrite:
        cmd.append("--overwrite")
    if STATE.dry_run:
        cmd.append("--dry-run")
    info(f"[{name}] {script}.py")
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = {"status": "failed", "error": (proc.stderr or proc.stdout).strip()[-800:], "kind": "failed"}
    data["_command"] = shell_join(cmd)
    steps.append({"step": name, "status": data.get("status"), "output": data.get("output"), "command": data["_command"]})
    if proc.returncode != 0 or data.get("status") == "failed":
        die(f"step '{name}' failed: {data.get('error') or 'verification failed'}", data.get("kind") or "failed",
            steps=steps, failed_step=data)
    return data


def main() -> None:
    a = build_parser().parse_args()
    apply_common(a)
    src = Path(a.input).expanduser()
    if not src.is_file():
        die(f"input not found: {src}", "input")
    out_dir = Path(a.out_dir).expanduser() if a.out_dir else src.parent
    if not STATE.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    tl = out_dir / f"{src.stem}.timeline.json"
    render_out = out_dir / f"{src.stem}_{a.comp}.mp4"
    steps: List[Dict[str, Any]] = []

    an_args = [str(src), "-o", str(tl)] + (["--captions", a.captions] if a.captions else []) + (["--beats"] if a.beats else [])
    analysis = step("measure", "analyze", an_args, steps)
    if STATE.dry_run and not tl.exists():
        emit({"output": None, "steps": steps,
              "note": "dry run stops after planning the measurement: render needs the timeline it would write"},
             "planned: " + " -> ".join(s["step"] for s in steps))
        return

    r_args = ["--project", a.project, "--comp", a.comp, "--timeline", str(tl), "-o", str(render_out)]
    if a.options:
        r_args += ["--options", a.options]
    if a.fast:
        r_args.append("--fast")
    rendered = step("draw", "render", r_args, steps)

    delivered = None
    if a.platform:
        delivered = step("deliver", "deliver", [str(render_out), "--platform", a.platform], steps)

    final = (delivered or {}).get("output") or rendered.get("output")
    look = rendered.get("look")
    lines = [f"measure: {analysis.get('summary')}", f"draw:    {rendered.get('summary')}"]
    if delivered:
        lines.append(f"deliver: {Path(delivered.get('checked') or '').name} "
                     f"({'PASS' if delivered.get('verified') else 'FAIL'}, warnings: {', '.join(delivered.get('warnings') or []) or 'none'})")
    lines.append(f"Look: {look}" if look else "Look: not generated")
    emit({"output": final, "timeline": str(tl), "render": rendered.get("output"),
          "deliverable": (delivered or {}).get("output"), "look": look, "verified": True,
          "warnings": analysis.get("warnings", []), "steps": steps}, "\n".join(lines))


if __name__ == "__main__":
    main()
