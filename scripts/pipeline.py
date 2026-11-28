#!/usr/bin/env python3
"""The whole loop in one command: measure (analyze.py) -> draw (render.py) -> deliver and
check (deliver.py), each step verified before the next runs. Stops at the first failure
and says which step failed.

Examples:
  python3 pipeline.py talk.mp4 --project ./motion --comp Jumpcut --captions talk.srt --platform youtube
  python3 pipeline.py clip.mp4 --project ./motion --comp PeakPulse --platform reels --out-dir out/
  python3 pipeline.py talk.mp4 --project ./motion --comp Captioned --captions talk.srt   # no delivery step
  python3 pipeline.py --blank 15 --size 1080x1920 --music bgm.wav --project ./motion --comp PeakPulse   # no footage
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (ASPECTS, BUILTIN_COMPOSITIONS, FITS, HERE, STATE, add_common, apply_common, die, emit, info,
                     platform_aspect, shell_join, parse_with_blank, STYLE_NAMES)
from deliver import PLATFORMS


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", nargs="+", help="source video; several are joined in order (ffmpeg-skill join.py) first "
                                            "(with --blank: none, or `-`)")
    p.add_argument("--project", required=True, help="Remotion project folder made by init.py")
    p.add_argument("--comp", required=True, help=f"composition id ({', '.join(BUILTIN_COMPOSITIONS)}, or yours)")
    p.add_argument("--captions", help="SRT / WebVTT / JSON cues for the timeline")
    p.add_argument("--chapters", metavar="FILE|source",
                   help="chapters (`TIME TITLE` per line, or `source`): cards in Titled and, with --platform, chapter "
                        "markers in the deliverable")
    p.add_argument("--options", help="JSON options file passed to the composition")
    p.add_argument("--brand", help="ffmpeg-skill brand.json: the look of the graphics and, on delivery, the logo")
    p.add_argument("--style", choices=STYLE_NAMES,
                   help="a look in one word (render.py --style): --brand and --options win over it key by key")
    p.add_argument("--platform", choices=PLATFORMS, help="deliver with this ffmpeg-skill template and check it")
    p.add_argument("--out-dir", help="where the timeline, render and deliverable go (default: next to the input)")
    p.add_argument("--beats", action="store_true", help="measure the beat grid too")
    p.add_argument("--blank", type=float, metavar="SECONDS",
                   help="no footage: draw the composition on a plain background this many seconds long "
                        "(analyze.py --blank); give no input file")
    p.add_argument("--size", metavar="WxH", help="with --blank: frame size (default 1920x1080)")
    p.add_argument("--fps", metavar="RATE", help="with --blank: frame rate (default 30)")
    p.add_argument("--music", metavar="FILE", help="with --blank: music under it, measured for peaks and --beats")
    p.add_argument("--conform", action="store_true",
                   help="a variable-frame-rate or HDR source is made into a constant-frame-rate, SDR BT.709 copy "
                        "with ffmpeg-skill first (analyze.py --conform; the copy goes in --out-dir) and drawn on; "
                        "without it such a source is refused")
    p.add_argument("--fast", action="store_true", help="preview-quality render")
    p.add_argument("--aspect", choices=["source", *ASPECTS],
                   help="output shape (default: the shape the --platform template delivers, else the source's)")
    p.add_argument("--width", type=int, help="output width in px")
    p.add_argument("--fit", choices=FITS, help="blur (default when the shape changes), contain or cover")
    p.add_argument("--font-file", help="caption font file")
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
    a = parse_with_blank(build_parser())
    apply_common(a)
    inputs = [Path(i).expanduser() for i in a.input]
    missing = [str(i) for i in inputs if not i.is_file()]
    if missing:
        die(f"input not found: {', '.join(missing)}", "input")
    if a.blank is None and not inputs:
        die("give an input file, or --blank SECONDS for a run with no footage", "input")
    if a.blank is not None and inputs:
        die("--blank makes a run with no footage: give no input file (the music goes in --music)", "input")
    if a.blank is None:
        given = [f for f, v in (("--size", a.size), ("--fps", a.fps), ("--music", a.music)) if v is not None]
        if given:
            die(f"{', '.join(given)} {'needs' if len(given) == 1 else 'need'} --blank SECONDS", "input")
    blank_args: List[str] = []
    if a.blank is not None:
        music = Path(a.music).expanduser() if a.music else None
        blank_args = ["--blank", repr(a.blank)] + [x for flag, v in (("--size", a.size), ("--fps", a.fps),
                                                                       ("--music", a.music)) if v for x in (flag, v)]
        out_dir = Path(a.out_dir).expanduser() if a.out_dir else (music.parent if music else Path.cwd())
        stem = f"{music.stem}_blank" if music else "blank"
    else:
        src = inputs[0]
        out_dir = Path(a.out_dir).expanduser() if a.out_dir else src.parent
        stem = src.stem + ("_joined" if len(inputs) > 1 else "")
    if not STATE.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    tl = out_dir / f"{stem}.timeline.json"
    render_out = out_dir / f"{stem}_{a.comp}.mp4"
    steps: List[Dict[str, Any]] = []

    an_args = [*map(str, inputs), *blank_args, "-o", str(tl)]
    an_args += ["--joined", str(out_dir / f"{stem}.mp4")] if len(inputs) > 1 else []
    an_args += (["--captions", a.captions] if a.captions else []) + (["--beats"] if a.beats else [])
    an_args += ["--chapters", a.chapters] if a.chapters else []
    an_args += ["--conform", "--conformed", str(out_dir / f"{stem}_conformed.mp4")] if a.conform else []
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
    # Draw in the shape the delivery template will produce: a 16:9 render pushed through the Reels
    # template would be centre-cropped to 9:16 and lose the edges of every caption.
    aspect = a.aspect or platform_aspect(a.platform)
    if aspect:
        r_args += ["--aspect", aspect]
    for flag, val in (("--width", a.width), ("--fit", a.fit), ("--font-file", a.font_file), ("--brand", a.brand),
                      ("--style", a.style)):
        if val is not None:
            r_args += [flag, str(val)]
    rendered = step("draw", "render", r_args, steps)

    delivered = None
    if a.platform:
        de_args = [str(render_out), "--platform", a.platform] + (["--brand", a.brand] if a.brand else [])
        # chapter markers only when the picture keeps the source's clock (cuts would move every chapter)
        if a.chapters and a.chapters != "source" and a.comp not in ("Jumpcut", "Highlights"):
            de_args += ["--chapters", a.chapters]
        delivered = step("deliver", "deliver", de_args, steps)

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
