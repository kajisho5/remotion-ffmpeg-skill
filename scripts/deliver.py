#!/usr/bin/env python3
"""Turn a Remotion render into a platform deliverable with ffmpeg-skill: its delivery
template (frame, loudness, codec for YouTube, Reels, TikTok, ...) and then check.py's
compliance table. Without --platform it only checks the file as it is.

Examples:
  python3 deliver.py captioned.mp4 --platform youtube          # -> captioned_youtube.mp4 + check
  python3 deliver.py jumpcut.mp4 --platform reels -o reel.mp4
  python3 deliver.py master.mov --check-only --platform x      # measure, change nothing
  python3 deliver.py titled.mp4 --platform youtube --chapters chapters.txt   # + chapter markers
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _captions import parse_chapters
from _common import (STATE, add_common, apply_common, default_output, die, emit, ffskill, ffskill_cmd, info,
                     refuse_existing, require_ffmpeg_skill, shell_join)

# ffmpeg-skill's templates/*.json names (render.py --list-templates).
PLATFORMS = ["youtube", "youtube-shorts", "shorts", "reels", "tiktok", "x", "facebook", "linkedin", "podcast", "audiogram"]


def youtube_description(chapters_file: Path) -> str:
    """The chapter list as YouTube reads it from a description: `00:00 Title` per line."""
    chapters = parse_chapters(chapters_file.read_text(encoding="utf-8-sig"), 0)
    long = chapters[-1]["start"] >= 3600

    def fmt(t: float) -> str:
        t = int(t)
        h, m, sec = t // 3600, t % 3600 // 60, t % 60
        return f"{h}:{m:02d}:{sec:02d}" if long else f"{m:02d}:{sec:02d}"
    return "\n".join(f"{fmt(c['start'])} {c['title']}" for c in chapters) + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("input", help="rendered video")
    p.add_argument("--platform", choices=PLATFORMS, help="ffmpeg-skill delivery template to run")
    p.add_argument("-o", "--output", help="deliverable path (default: <name>_<platform>.mp4)")
    p.add_argument("--check-only", action="store_true", help="run check.py only, write nothing")
    p.add_argument("--chapters", metavar="FILE",
                   help="also write these chapters (`TIME TITLE` per line) into the deliverable with ffmpeg-skill "
                        "metadata.py, plus the YouTube description block next to it (<name>_description.txt)")
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

    if a.chapters:
        if a.check_only or not a.platform:
            die("--chapters writes into the deliverable: it needs --platform and no --check-only", "input")
        if not Path(a.chapters).expanduser().is_file():
            die(f"chapters file not found: {a.chapters}", "input")
    target = src
    if a.platform and not a.check_only:
        out = Path(a.output).expanduser() if a.output else default_output(src, f"_{a.platform}", ".mp4")
        refuse_existing(out)
        templated = out.with_name(out.stem + ".nochapters" + out.suffix) if a.chapters else out
        args = ["--template", a.platform, str(src), "-o", str(templated)]
        if STATE.overwrite or a.chapters:
            args.append("--overwrite")
        description = out.with_name(out.stem + "_description.txt")
        meta_args = [str(templated), "--chapters", str(Path(a.chapters).expanduser()), "-o", str(out)] + (
            ["--overwrite"] if STATE.overwrite else [])
        if STATE.dry_run:
            commands.append(shell_join(ffskill_cmd("render", args)))
            if a.chapters:
                commands.append(shell_join(ffskill_cmd("metadata", meta_args)))
            commands.append(shell_join(ffskill_cmd("check", [str(out), "--platform", a.platform])))
            emit({"output": str(out), "commands": commands}, f"would deliver {out}")
            return
        r = ffskill("render", args)
        commands.append(r["_command"])
        if a.chapters:
            m = ffskill("metadata", meta_args)
            commands.append(m["_command"])
            templated.unlink(missing_ok=True)
            description.write_text(youtube_description(Path(a.chapters).expanduser()), encoding="utf-8")
            info(f"wrote {description} (paste into the YouTube description)")
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
          "description": str(target.with_name(target.stem + "_description.txt")) if a.chapters else None,
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
