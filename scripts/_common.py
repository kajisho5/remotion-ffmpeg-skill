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
    for k in ("scenes", "silences", "speech", "peaks", "captions", "highlights", "words"):
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
    if comp in ("Captioned", "PeakPulse", "Titled", "BeatMontage", "Karaoke"):
        return max(1, sec_to_frames(float(t["source"]["duration"]), fps))
    if comp in ("Jumpcut", "Highlights"):
        if comp == "Jumpcut":
            ranges = t.get("speech") or [[0.0, float(t["source"]["duration"])]]
        else:
            ranges = [[h["start"], h["end"]] for h in (t.get("highlights") or [])] or [[0.0, float(t["source"]["duration"])]]
        total = sum(max(1, sec_to_frames(e, fps) - sec_to_frames(s, fps)) for s, e in ranges)
        return max(1, total)
    return None


# ---------------------------------------------------------------- Remotion project

BUILTIN_COMPOSITIONS = ("Captioned", "Jumpcut", "PeakPulse", "Titled", "Highlights", "BeatMontage", "Karaoke")


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
    # No marker: the Error lines themselves, without the JavaScript stack frames under them.
    errors = [ln.strip() for ln in lines if "Error" in ln and not ln.lstrip().startswith("at ")]
    if errors:
        return "\n".join(errors[-limit:])
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("at "))[-4000:] or "\n".join(lines[-limit:])


def stage_source(project: Path, source_path: str) -> str:
    """Make the source reachable by staticFile(): public/media/<hash>_<name>. Returns the src string."""
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        die(f"source in the timeline does not exist any more: {src}", "input")
    return _stage(project, src, "media")


def _stage(project: Path, src: Path, folder: str) -> str:
    st = src.stat()
    tag = hashlib.sha1(f"{src}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:8]
    rel = f"{folder}/{tag}_{src.name}"
    dst = project / "public" / rel
    if STATE.dry_run:
        return rel
    if dst.is_symlink():          # left by an older version or by hand: Remotion cannot serve it
        dst.unlink()
    elif dst.exists():
        return rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    # A hard link (instant, no extra space), else a one-time copy. Never a symlink: Remotion's file
    # server refuses a public/ symlink that points outside the project (404 at render time).
    # Remotion's CLI itself links the whole public/ folder into its temporary bundle on macOS/Linux,
    # so the source is not copied again per render; on Windows the CLI copies public/ each time.
    try:
        os.link(src, dst)
    except OSError:
        info(f"copying {src.name} into the project (hard link not possible across drives) ...")
        shutil.copy2(src, dst)
    return rel


# ---------------------------------------------------------------- output frame

ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:5": (4, 5), "4:3": (4, 3)}
FITS = ("blur", "contain", "cover")


def even(n: float) -> int:
    return max(2, int(round(n / 2.0)) * 2)


def output_frame(timeline: Dict[str, Any], aspect: Optional[str], width: Optional[int],
                 fit: Optional[str]) -> Optional[Dict[str, Any]]:
    """The output frame for --aspect/--width/--fit, or None for the source's own size.

    Without --width the output keeps the source's short side (720p stays 720 wide when turned
    portrait: 720x1280), so nothing is upscaled; sizes are rounded to even numbers for H.264.
    """
    src = timeline["source"]
    sw, sh = int(src["width"]), int(src["height"])
    if (aspect in (None, "source")) and width is None:
        return None if fit in (None, "contain") else {"width": sw, "height": sh, "fit": fit}
    if aspect in (None, "source"):
        aw, ah = sw, sh
    else:
        aw, ah = ASPECTS[aspect]
    if width is not None:
        w = even(width)
        h = even(w * ah / aw)
    else:
        short = min(sw, sh)
        if aw <= ah:
            w = even(short)
            h = even(w * ah / aw)
        else:
            h = even(short)
            w = even(h * aw / ah)
    return {"width": w, "height": h, "fit": fit or ("blur" if aspect not in (None, "source") else "contain")}


def frame_size(timeline: Dict[str, Any], frame: Optional[Dict[str, Any]]) -> Tuple[int, int]:
    if frame:
        return int(frame["width"]), int(frame["height"])
    return int(timeline["source"]["width"]), int(timeline["source"]["height"])


def platform_aspect(platform: Optional[str]) -> Optional[str]:
    """The aspect ffmpeg-skill's delivery template for this platform produces (its frame.aspect)."""
    if not platform:
        return None
    skill = find_ffmpeg_skill()
    if skill is None:
        return None
    try:
        tpl = json.loads((skill / "templates" / f"{platform}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    aspect = (tpl.get("frame") or {}).get("aspect")
    return aspect if aspect in ASPECTS else None


# ---------------------------------------------------------------- fonts

def caption_script(captions: List[Dict[str, Any]]) -> Optional[str]:
    """ja / ko / zh when the caption text needs a CJK font, else None (Latin etc. render with system fonts)."""
    text = "".join(c.get("text", "") for c in captions)
    if any("぀" <= ch <= "ヿ" for ch in text):
        return "ja"
    if any("가" <= ch <= "힯" or "ᄀ" <= ch <= "ᇿ" for ch in text):
        return "ko"
    if any("一" <= ch <= "鿿" or "㐀" <= ch <= "䶿" for ch in text):
        return "ja"  # Han only: Japanese glyph forms by default; --font-file picks another
    return None


def cjk_font_file(script: str) -> Optional[Path]:
    """The font file ffmpeg-skill's doctor resolves for this script on this machine."""
    skill = find_ffmpeg_skill()
    if skill is None:
        return None
    proc = subprocess.run([sys.executable, str(skill / "scripts" / "_contract.py"), "doctor", "--json"],
                          capture_output=True, text=True, timeout=120)
    try:
        entry = json.loads(proc.stdout)["fonts"]["scripts"].get(script) or {}
    except (ValueError, KeyError, TypeError):
        return None
    f = entry.get("file")
    return Path(f) if entry.get("status") == "available" and f and Path(f).is_file() else None


def stage_font(project: Path, font_file: Path) -> Dict[str, str]:
    if not font_file.is_file():
        die(f"font file not found: {font_file}", "input")
    if font_file.suffix.lower() not in (".ttf", ".otf", ".ttc", ".otc", ".woff", ".woff2"):
        die(f"{font_file.name}: use a .ttf, .otf, .ttc, .woff or .woff2 font", "input")
    rel = _stage(project, font_file.resolve(), "fonts")
    return {"src": rel, "family": "RFS " + Path(rel).name.split("_", 1)[0]}


def resolve_font(project: Path, timeline: Dict[str, Any], font_file: Optional[str],
                 auto: bool) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """(font asset for the props, a note for the report). A given --font-file always wins; otherwise
    CJK captions get the CJK font ffmpeg-skill finds on this machine, so they never render as tofu."""
    if font_file:
        return stage_font(project, Path(font_file).expanduser()), f"font: {font_file}"
    script = caption_script(timeline.get("captions") or [])
    if not script or not auto:
        return None, None
    found = cjk_font_file(script)
    if found is None:
        return None, (f"captions need a {script} font and none was found on this machine: install one "
                      f"(e.g. Noto Sans CJK) or pass --font-file; the contact sheet will show tofu otherwise")
    return stage_font(project, found), f"font: {found} (found by ffmpeg-skill for {script} captions)"


def write_props(project: Path, comp: str, timeline: Dict[str, Any], options: Dict[str, Any],
                frame: Optional[Dict[str, Any]] = None, font: Optional[Dict[str, str]] = None,
                overlay: bool = False) -> Tuple[Path, Dict[str, Any]]:
    t = json.loads(json.dumps(timeline))
    src = t["source"].get("path")
    has_media = t["source"].get("has_video", True) or t["source"].get("has_audio", False)
    t["source"]["src"] = stage_source(project, src) if src and has_media and not overlay else None
    props = {"timeline": t, "options": options, "frame": frame, "font": font, "overlay": overlay}
    # Named by content: two renders running at once (different sources, shapes or options) never
    # overwrite each other's props, and identical props share one file harmlessly.
    digest = hashlib.sha1(json.dumps(props, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
    path = project / ".rfs" / f"props-{comp}-{digest}.json"
    if not STATE.dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, props


def add_frame_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("output frame and font")
    g.add_argument("--aspect", choices=["source", *ASPECTS], default=None,
                   help="output shape (default: the source's own). 9:16 for Reels/TikTok/Shorts, 1:1, 4:5, 16:9")
    g.add_argument("--width", type=int, help="output width in px (default: keep the source's short side)")
    g.add_argument("--fit", choices=FITS, help="how the source fills another shape: blur (default when the shape "
                                                "changes), contain (bars) or cover (crop)")
    g.add_argument("--font-file", help="caption font file (.ttf/.otf/.ttc/.woff2), staged into the project")
    g.add_argument("--no-auto-font", action="store_true",
                   help="don't stage the CJK font ffmpeg-skill finds for Japanese/Chinese/Korean captions")


def prepare_props(project: Path, comp: str, timeline: Dict[str, Any], options: Dict[str, Any],
                  a: argparse.Namespace) -> Tuple[Path, Optional[Dict[str, Any]], Optional[str]]:
    """Frame + font + props file for render.py / still.py. Returns (props path, frame, font note)."""
    if a.width is not None and a.width < 16:
        die("--width must be at least 16 px", "input")
    frame = output_frame(timeline, a.aspect, a.width, a.fit)
    font, note = resolve_font(project, timeline, a.font_file, not a.no_auto_font)
    props_path, _ = write_props(project, comp, timeline, options, frame, font, bool(getattr(a, "overlay", False)))
    return props_path, frame, note


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
    problems = validate_options(data)
    if problems:
        die(f"{p}: " + "; ".join(problems) + " (see references/timeline.md, Options)", "input")
    return data


# Mirrors Options in src/timeline.ts. A typo'd key would silently do nothing in the browser, so it is refused here.
_OPTION_TYPES: Dict[str, Any] = {
    "accent": str, "textColor": str, "fontFamily": str, "captionSize": (int, float),
    "captionMargin": (int, float, type(None)), "punchIn": (int, float), "pulse": (int, float),
    "progressBar": bool, "driver": str, "lowerThirds": list, "sceneTitles": list,
    "title": (str, type(None)), "beatsPerCut": int,
}


def validate_options(o: Dict[str, Any]) -> List[str]:
    p: List[str] = []
    for k, v in o.items():
        if k not in _OPTION_TYPES:
            p.append(f"unknown option {k!r} (known: {', '.join(sorted(_OPTION_TYPES))})")
        elif isinstance(v, bool) and _OPTION_TYPES[k] is not bool and bool not in (
                _OPTION_TYPES[k] if isinstance(_OPTION_TYPES[k], tuple) else (_OPTION_TYPES[k],)):
            p.append(f"{k} must be {_OPTION_TYPES[k]}, got a boolean")
        elif not isinstance(v, _OPTION_TYPES[k]):
            p.append(f"{k} has the wrong type ({type(v).__name__})")
    if "driver" in o and o["driver"] not in ("auto", "peaks", "beats"):
        p.append("driver must be auto, peaks or beats")
    if isinstance(o.get("beatsPerCut"), int) and o["beatsPerCut"] < 1:
        p.append("beatsPerCut must be at least 1")
    for i, lt in enumerate(o.get("lowerThirds") or []):
        if not (isinstance(lt, dict) and isinstance(lt.get("text"), str) and lt.get("text")
                and isinstance(lt.get("start"), (int, float)) and isinstance(lt.get("end"), (int, float))
                and lt["end"] > lt["start"] and isinstance(lt.get("sub", ""), str)):
            p.append(f"lowerThirds[{i}] needs text, start < end (seconds) and an optional sub")
    if any(not isinstance(s, str) for s in (o.get("sceneTitles") or [])):
        p.append("sceneTitles must be a list of strings")
    return p


def now() -> float:
    return time.monotonic()
