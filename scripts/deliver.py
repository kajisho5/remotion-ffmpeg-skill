#!/usr/bin/env python3
"""Turn a Remotion render into a platform deliverable with ffmpeg-skill: its delivery
template (frame, loudness, codec for YouTube, Reels, TikTok, ...) and then check.py's
compliance table. Without --platform it only checks the file as it is.

Examples:
  python3 deliver.py captioned.mp4 --platform youtube          # -> captioned_youtube.mp4 + check
  python3 deliver.py jumpcut.mp4 --platform reels -o reel.mp4
  python3 deliver.py master.mov --check-only --platform x      # measure, change nothing
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (STATE, add_common, apply_common, default_output, die, emit, ffskill, ffskill_cmd,
                     refuse_existing, require_ffmpeg_skill, shell_join)

# ffmpeg-skill's templates/*.json names (render.py --list-templates).
PLATFORMS = ["youtube", "youtube-shorts", "shorts", "reels", "tiktok", "x", "facebook", "linkedin", "podcast", "audiogram"]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", help="rendered video")
    p.add_argument("--platform", choices=PLATFORMS, help="ffmpeg-skill delivery template to run")
    p.add_argument("-o", "--output", help="deliverable path (default: <name>_<platform>.mp4)")
    p.add_argument("--check-only", action="store_true", help="run check.py only, write nothing")
    add_common(p)
    return p


def main() -> None:
    a = build_parser().parse_args()
    apply_common(a)
    src = Path(a.input).expanduser()
    if not src.is_file():
        die(f"input not found: {src}", "input")
    require_ffmpeg_skill()
    commands = []

    target = src
    if a.platform and not a.check_only:
        out = Path(a.output).expanduser() if a.output else default_output(src, f"_{a.platform}", ".mp4")
        refuse_existing(out)
        args = ["--template", a.platform, str(src), "-o", str(out)]
        if STATE.overwrite:
            args.append("--overwrite")
        if STATE.dry_run:
            commands.append(shell_join(ffskill_cmd("render", args)))
            commands.append(shell_join(ffskill_cmd("check", [str(out), "--platform", a.platform])))
            emit({"output": str(out), "commands": commands}, f"would deliver {out}")
            return
        r = ffskill("render", args)
        commands.append(r["_command"])
        target = out

    check_args = [str(target)] + (["--platform", a.platform] if a.platform else [])
    if STATE.dry_run:
        emit({"output": None, "commands": [shell_join(ffskill_cmd("check", check_args))]}, "would check")
        return
    ck = ffskill("check", check_args, allow_fail=True)
    commands.append(ck.get("_command", shell_join(ffskill_cmd("check", check_args))))
    checks = ck.get("checks", [])
    failed = [c for c in checks if c.get("status") == "FAIL"]
    warns = [c for c in checks if c.get("status") == "WARN"]
    ok = bool(checks) and not failed
    lines = [f"{c['status']:4} {c['check']}: {c.get('value')} (expected {c.get('expected')})" for c in checks]
    emit({"status": "completed" if ok else "failed", "output": str(target) if target != src else None,
          "checked": str(target), "platform": a.platform, "verified": ok, "checks": checks,
          "failed": [c["check"] for c in failed], "warnings": [c["check"] for c in warns], "commands": commands,
          "kind": None if ok else "failed",
          "error": None if ok else ("compliance check failed: " + ", ".join(c["check"] for c in failed)
                                    if failed else (ck.get("error") or "check.py returned no rows"))},
         "\n".join([f"{target.name}: {'PASS' if ok else 'FAIL'} ({len(failed)} fail, {len(warns)} warn)"] + lines))
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
