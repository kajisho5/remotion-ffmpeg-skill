#!/usr/bin/env python3
"""Report what this machine can do: Python, Node/npm, ffmpeg-skill (and its own doctor),
and -- with --project -- whether that Remotion project is installed and its version.

Run it after a failure, not before every job.

Examples:
  python3 doctor.py
  python3 doctor.py --project ./motion --json
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import add_common, apply_common, emit, ffmpeg_skill_version, find_ffmpeg_skill, remotion_bin, version


def _version(cmd):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--project", help="Remotion project folder to inspect")
    add_common(p)
    a = p.parse_args()
    apply_common(a)

    rows = []

    def row(name, ok, value, fix=""):
        rows.append({"check": name, "ok": bool(ok), "value": value, "fix": "" if ok else fix})

    row("python", sys.version_info >= (3, 10), sys.version.split()[0], "use Python 3.10 or newer")
    node = shutil.which("node")
    row("node", node, _version([node, "--version"]) if node else None, "install Node.js from https://nodejs.org")
    npm = shutil.which("npm")
    row("npm", npm, _version([npm, "--version"]) if npm else None, "npm ships with Node.js")
    skill = find_ffmpeg_skill()
    row("ffmpeg-skill", skill, f"{skill} ({ffmpeg_skill_version(skill)})" if skill else None,
        "npx ffmpeg-skill   (or set FFMPEG_SKILL_DIR)")
    ff = None
    if skill:
        try:
            out = subprocess.run([sys.executable, str(skill / "scripts" / "_contract.py"), "doctor", "--json"],
                                 capture_output=True, text=True, timeout=60)
            ff = json.loads(out.stdout)
            row("ffmpeg", ff.get("ok", False), ff.get("ffmpeg") or None,
                "missing: " + ", ".join(map(str, ff.get("missing") or [])) + "  (python3 <ffmpeg-skill>/scripts/_contract.py doctor)")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            row("ffmpeg", False, None, "ffmpeg-skill doctor could not run")
    if a.project:
        proj = Path(a.project).expanduser().resolve()
        rb = remotion_bin(proj)
        rv = None
        pkg = proj / "node_modules" / "remotion" / "package.json"
        if pkg.is_file():
            rv = json.loads(pkg.read_text(encoding="utf-8")).get("version")
        row("remotion project", rb.exists(), f"{proj} (remotion {rv})" if rv else str(proj),
            f"cd {proj} && npm install")

    ok = all(r["ok"] for r in rows)
    lines = [f"{'ok ' if r['ok'] else 'NO '} {r['check']}: {r['value']}" + (f"  -> {r['fix']}" if r["fix"] else "")
             for r in rows]
    emit({"status": "completed", "ok": ok, "version": version(), "checks": rows, "ffmpeg_skill_doctor": ff},
         "\n".join([f"remotion-ffmpeg-skill {version()}: {'ready' if ok else 'not ready'}"] + lines))


if __name__ == "__main__":
    main()
