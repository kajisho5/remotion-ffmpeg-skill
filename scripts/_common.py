#!/usr/bin/env python3
"""Shared helpers for remotion-ffmpeg-skill (internal module, not a tool).

Three jobs live here so every public script behaves the same way:

* CLI conventions copied from ffmpeg-skill: --json, --dry-run, --overwrite, --timeout,
  one JSON object on stdout, human lines on stderr, a typed error ("kind") on failure.
* Finding and calling ffmpeg-skill. This skill never runs a raw ffmpeg/ffprobe command of
  its own: measuring (probe, scenes, silence), checking (check.py) and delivering
  (render.py --template) all go through ffmpeg-skill's scripts and their --json output.
* Preparing a Remotion render: copying/linking the source into the project's public/
  folder, writing the props file, finding the project-local `remotion` binary.

Python 3.10+ standard library only.
"""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SKILL_ID = "remotion-ffmpeg-skill"
TIMELINE_SCHEMA = "remotion-ffmpeg-skill/timeline@1"

# Exit codes follow ffmpeg-skill: 2 = bad input / refused, 3 = missing tool, 1 = the step ran and failed.
EXIT_FOR_KIND = {"input": 2, "missing_tool": 3, "timeout": 4, "failed": 1}


class State:
    json = False
    dry_run = False
    overwrite = False
    timeout = 1800.0


STATE = State()


def version() -> str:
    try:
        return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return "0.0.0"


# ---------------------------------------------------------------- CLI conventions

def add_common(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("shared flags")
    g.add_argument("--json", action="store_true", help="print one JSON object on stdout")
    g.add_argument("--dry-run", action="store_true", help="plan only: print the commands, write nothing")
    g.add_argument("--overwrite", action="store_true", help="allow replacing an existing output file")
    g.add_argument("--timeout", type=float, default=1800.0, metavar="SECONDS",
                   help="wall-clock limit for each external step (default 1800)")


def apply_common(args: argparse.Namespace) -> None:
    STATE.json = bool(args.json)
    STATE.dry_run = bool(args.dry_run)
    STATE.overwrite = bool(args.overwrite)
    STATE.timeout = float(args.timeout)


def info(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def emit(result: Dict[str, Any], summary: str) -> None:
    """Print the result: JSON on stdout with --json, otherwise the one-line summary."""
    result.setdefault("status", "completed")
    result.setdefault("dry_run", STATE.dry_run)
    if STATE.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(summary)


def die(msg: str, kind: str = "input", **extra: Any) -> "NoReturn":  # type: ignore[name-defined]
    if STATE.json:
        out = {"status": "failed", "error": msg, "kind": kind, "dry_run": STATE.dry_run}
        out.update(extra)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        info(f"error ({kind}): {msg}")
    sys.exit(EXIT_FOR_KIND.get(kind, 1))


def refuse_existing(path: Path) -> None:
    if path.exists() and not STATE.overwrite:
        die(f"{path} already exists; pass --overwrite to replace it", "input")


def default_output(src: Path, suffix: str, ext: Optional[str] = None) -> Path:
    return src.with_name(f"{src.stem}{suffix}{ext if ext is not None else src.suffix}")


def run(cmd: Sequence[str], cwd: Optional[Path] = None, capture: bool = True,
        env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
    """Run one external step with the shared timeout. Never called under --dry-run by writers."""
    try:
        return subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, env=env,
                              stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.PIPE if capture else None,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=STATE.timeout)
    except subprocess.TimeoutExpired:
        die(f"timed out after {STATE.timeout:.0f}s: {' '.join(cmd[:3])} ...", "timeout")
    except FileNotFoundError:
        die(f"not found: {cmd[0]}", "missing_tool")


def shell_join(cmd: Sequence[str]) -> str:
    import shlex
    return " ".join(shlex.quote(str(c)) for c in cmd)


# ---------------------------------------------------------------- ffmpeg-skill

def _skill_candidates() -> List[Path]:
    home = Path.home()
    env = os.environ.get("FFMPEG_SKILL_DIR")
    out: List[Path] = []
    if env:
        out.append(Path(env).expanduser())
    out += [
        ROOT.parent / "ffmpeg-skill",                       # installed side by side (~/.claude/skills/*)
        Path.cwd() / ".claude" / "skills" / "ffmpeg-skill",  # project install
        home / ".claude" / "skills" / "ffmpeg-skill",
        home / ".agents" / "skills" / "ffmpeg-skill",
        home / ".cursor" / "skills" / "ffmpeg-skill",
    ]
    return out


def find_ffmpeg_skill() -> Optional[Path]:
    for c in _skill_candidates():
        if (c / "scripts" / "probe.py").is_file() and (c / "scripts" / "check.py").is_file():
            return c.resolve()
    return None


def require_ffmpeg_skill() -> Path:
    found = find_ffmpeg_skill()
    if found is None:
        die("ffmpeg-skill not found. Install it with `npx ffmpeg-skill` (it lands next to this skill), "
            "or set FFMPEG_SKILL_DIR to its folder. Looked in: "
            + ", ".join(str(c) for c in _skill_candidates()), "missing_tool")
    return found


def ffmpeg_skill_version(skill_dir: Path) -> Optional[str]:
    try:
        return json.loads((skill_dir / "package.json").read_text(encoding="utf-8")).get("version")
    except (OSError, ValueError):
        return None


def ffskill_cmd(script: str, args: Sequence[str]) -> List[str]:
    skill = require_ffmpeg_skill()
    return [sys.executable, str(skill / "scripts" / f"{script}.py"), *[str(a) for a in args], "--json"]


def ffskill(script: str, args: Sequence[str], allow_fail: bool = False) -> Dict[str, Any]:
    """Run one ffmpeg-skill script with --json and return its parsed result.

    ffmpeg-skill prints its JSON object on stdout and human progress on stderr; a non-zero exit
    still carries a JSON error object (status/kind/error) that is passed through as ours.
    """
    cmd = ffskill_cmd(script, args)
    proc = run(cmd)
    try:
        data = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except ValueError:
        data = {}
    if proc.returncode != 0 or not data or data.get("status") == "failed":
        if allow_fail:
            data.setdefault("status", "failed")
            data.setdefault("error", (proc.stderr or "").strip()[-600:])
            return data
        err = data.get("error") or (proc.stderr or "").strip()[-600:] or f"exit {proc.returncode}"
        die(f"ffmpeg-skill {script}.py failed: {err}", data.get("kind") or "failed",
            command=shell_join(cmd))
    data["_command"] = shell_join(cmd)
    return data


# ---------------------------------------------------------------- timeline

def load_timeline(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        die(f"timeline not found: {path} (make one with analyze.py)", "input")
    try:
        t = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"{path} is not valid JSON: {e}", "input")
    problems = validate_timeline(t)
    if problems:
        die(f"{path} is not a {TIMELINE_SCHEMA} file: " + "; ".join(problems), "input")
    return t


def validate_timeline(t: Any) -> List[str]:
    p: List[str] = []
    if not isinstance(t, dict):
        return ["top level must be an object"]
    if t.get("schema") != TIMELINE_SCHEMA:
        p.append(f"schema must be {TIMELINE_SCHEMA!r} (got {t.get('schema')!r})")
    src = t.get("source")
    if not isinstance(src, dict):
        p.append("source missing")
    else:
        for k in ("duration", "fps", "width", "height"):
            v = src.get(k)
            if not isinstance(v, (int, float)) or v <= 0:
                p.append(f"source.{k} must be a positive number")
    for k in ("scenes", "silences", "speech", "peaks", "captions"):
        if not isinstance(t.get(k, []), list):
            p.append(f"{k} must be a list")
    for i, c in enumerate(t.get("captions", []) or []):
        if not (isinstance(c, dict) and isinstance(c.get("start"), (int, float))
                and isinstance(c.get("end"), (int, float)) and isinstance(c.get("text"), str)
                and c["end"] > c["start"]):
            p.append(f"captions[{i}] needs start < end and text")
            break
    for i, r in enumerate(t.get("speech", []) or []):
        if not (isinstance(r, list) and len(r) == 2 and r[1] > r[0]):
            p.append(f"speech[{i}] must be [start, end] with start < end")
            break
    return p


def sec_to_frames(seconds: float, fps: float) -> int:
    # JavaScript's Math.round (round half up), not Python's round() (half to even): the TypeScript
    # compositions compute the same frame numbers and the two must agree to the frame (94.5 -> 95).
    return int(math.floor(seconds * fps + 0.5))


def expected_frames(comp: str, t: Dict[str, Any]) -> Optional[int]:
    """Duration the built-in compositions compute in calculateMetadata (src/timeline.ts mirrors this).

    Custom compositions return None: their length is whatever their own calculateMetadata says,
    and render.py then only reports the measured numbers.
    """
    fps = float(t["source"]["fps"])
    if comp in ("Captioned", "PeakPulse"):
        return max(1, sec_to_frames(float(t["source"]["duration"]), fps))
    if comp == "Jumpcut":
        ranges = t.get("speech") or [[0.0, float(t["source"]["duration"])]]
        total = sum(max(1, sec_to_frames(e, fps) - sec_to_frames(s, fps)) for s, e in ranges)
        return max(1, total)
    return None


# ---------------------------------------------------------------- Remotion project

BUILTIN_COMPOSITIONS = ("Captioned", "Jumpcut", "PeakPulse")


def remotion_bin(project: Path) -> Path:
    name = "remotion.cmd" if os.name == "nt" else "remotion"
    return project / "node_modules" / ".bin" / name


def require_project(project: Path, need_install: bool = True) -> Path:
    project = project.resolve()
    if not (project / "package.json").is_file() or not (project / "src" / "index.ts").is_file():
        die(f"{project} is not a Remotion project made by init.py (needs package.json and src/index.ts)", "input")
    if need_install and not remotion_bin(project).exists():
        die(f"Remotion is not installed in {project}: run `npm install` there (or init.py --install)",
            "missing_tool")
    return project


_NOISE = ("Detected differing memory amounts", "Memory reported by", "inadvertently set the --memory",
          "Using the lower amount of memory")


def remotion_error(text: str, limit: int = 15) -> str:
    """The useful part of a failed Remotion CLI run: what follows 'An error occurred:', else the tail
    without container-memory chatter."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip() and not any(n in ln for n in _NOISE)]
    for i, ln in enumerate(lines):
        if "An error occurred" in ln:
            return "\n".join(ln2.strip() for ln2 in lines[i + 1:i + 1 + limit])
    return "\n".join(lines[-limit:])


def stage_source(project: Path, source_path: str) -> str:
    """Make the source reachable by staticFile(): public/media/<hash>_<name>. Returns the src string."""
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        die(f"source in the timeline does not exist any more: {src}", "input")
    st = src.stat()
    tag = hashlib.sha1(f"{src}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:8]
    rel = f"media/{tag}_{src.name}"
    dst = project / "public" / rel
    if STATE.dry_run or dst.exists():
        return rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)            # same filesystem: instant, no extra space
    except OSError:
        try:
            os.symlink(src, dst)
        except OSError:
            shutil.copy2(src, dst)
    return rel


def write_props(project: Path, comp: str, timeline: Dict[str, Any], options: Dict[str, Any]) -> Tuple[Path, Dict[str, Any]]:
    t = json.loads(json.dumps(timeline))
    src = t["source"].get("path")
    t["source"]["src"] = stage_source(project, src) if src and t["source"].get("has_video", True) else None
    props = {"timeline": t, "options": options}
    path = project / ".rfs" / f"props-{comp}.json"
    if not STATE.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, props


def load_options(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.is_file():
        die(f"options file not found: {p}", "input")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        die(f"{p} is not valid JSON: {e}", "input")
    if not isinstance(data, dict):
        die(f"{p} must hold a JSON object", "input")
    return data


def now() -> float:
    return time.monotonic()
