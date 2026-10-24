#!/usr/bin/env python3
"""Create a Remotion project wired for measured timelines: the three built-in compositions
(Captioned, Jumpcut, PeakPulse), the timeline types, and pinned Remotion versions.

Examples:
  python3 init.py ./motion              # copy the template (then: cd motion && npm install)
  python3 init.py ./motion --install    # copy and run npm install
"""
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import BUILTIN_COMPOSITIONS, ROOT, STATE, add_common, apply_common, die, emit, info, run, shell_join

TEMPLATE = ROOT / "templates" / "remotion-project"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("directory", help="new project folder (must not exist, or be empty)")
    p.add_argument("--install", action="store_true", help="run npm install after copying")
    add_common(p)
    return p


def main() -> None:
    a = build_parser().parse_args()
    apply_common(a)
    dst = Path(a.directory).expanduser().resolve()
    if dst.exists() and any(dst.iterdir()) and not STATE.overwrite:
        die(f"{dst} exists and is not empty; pick a new folder (or --overwrite to copy over it)", "input")
    if not (TEMPLATE / "package.json").is_file():
        die(f"template missing: {TEMPLATE}", "failed")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    commands = [f"copy {TEMPLATE} -> {dst}"]
    if a.install:
        if not npm:
            die("npm not found: install Node.js (https://nodejs.org) to render with Remotion", "missing_tool")
        commands.append(shell_join([npm, "install", "--no-audit", "--no-fund"]))
    if STATE.dry_run:
        emit({"output": str(dst), "commands": commands}, f"would create {dst}")
        return

    shutil.copytree(TEMPLATE, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("node_modules", ".rfs", "out"))
    installed = False
    if a.install:
        info("npm install (Remotion, React) ...")
        proc = run([npm, "install", "--no-audit", "--no-fund"], cwd=dst)
        if proc.returncode != 0:
            die("npm install failed:\n" + "\n".join((proc.stderr or "").strip().splitlines()[-20:]), "failed")
        installed = True
    emit({"output": str(dst), "commands": commands, "installed": installed, "entry": "src/index.ts",
          "compositions": list(BUILTIN_COMPOSITIONS)},
         f"created {dst}" + ("" if installed else f"\nnext: cd {dst} && npm install"))


if __name__ == "__main__":
    main()
