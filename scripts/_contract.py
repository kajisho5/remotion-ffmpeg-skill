#!/usr/bin/env python3
"""Machine-readable execution contract for remotion-ffmpeg-skill (internal module, not a tool).

    python3 scripts/_contract.py --json        # every public tool: role, writes, verification, input schema
    python3 scripts/_contract.py doctor --json  # same as doctor.py --json

Input schemas are generated from each script's own build_parser(), so the CLI stays the single
source of truth; the facts a parser cannot express (role, what it writes, how it verifies,
which ffmpeg-skill scripts it calls) live in TOOL_META and are checked by tests/test_contract.py.
The MCP server (mcp/server.py) is built from this contract and nothing else.
"""
import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _common import SKILL_ID, TIMELINE_SCHEMA, version  # noqa: E402

CONTRACT_VERSION = "1.0"

ROLES = {
    "analysis": "measures media and writes a data file (no media)",
    "execution": "writes a new media artifact; inputs are never modified",
    "verification": "checks an artifact or the environment; writes no media",
    "setup": "creates a project folder",
    "orchestration": "runs other tools in order, each verified before the next",
}

# Tool order = workflow order (also the MCP tools/list order).
TOOL_META: Dict[str, Dict[str, Any]] = {
    "analyze": {
        "role": "analysis",
        "summary": "Measure a source with ffmpeg-skill and write timeline.json (+ captions from a file).",
        "writes": "timeline.json (+ the joined source for several inputs, the conformed copy with --conform)",
        "verification": "every number comes from ffmpeg-skill probe/scenes/silence; a VFR or HDR source is refused, "
                        "or with --conform conformed and re-measured (CFR at the asked rate, SDR BT.709) before use; "
                        "warnings for rotation and odd frame rates",
        "ffmpeg_skill": ["probe", "scenes", "silence", "join (several inputs)", "sync (--pip)",
                         "fit (--conform: VFR -> CFR)", "color (--conform: HDR -> SDR)"],
        "dry_run": True,
    },
    "init": {
        "role": "setup",
        "summary": "Create a Remotion project with the built-in compositions (optionally npm install).",
        "writes": "project folder",
        "verification": "refuses a non-empty folder; npm install exit status",
        "ffmpeg_skill": [],
        "dry_run": True,
    },
    "still": {
        "role": "execution",
        "summary": "Render single frames as PNG to check the look before a full render.",
        "writes": "PNG files",
        "verification": "frames must lie inside the composition; view the PNGs",
        "ffmpeg_skill": ["_contract doctor (CJK font lookup)"],
        "dry_run": True,
    },
    "render": {
        "role": "execution",
        "summary": "Render a composition from a timeline, verify it (frames, fps, size, audio) and write a contact sheet.",
        "writes": "video file (+ contact sheet PNG)",
        "verification": "exact frame count / fps / size / audio against the timeline; non-zero exit on mismatch",
        "ffmpeg_skill": ["probe", "look", "overlay (--overlay; --place with --sparse)", "_contract doctor (CJK font lookup)"],
        "dry_run": True,
    },
    "deliver": {
        "role": "execution",
        "summary": "Run an ffmpeg-skill delivery template (YouTube, Reels, ...) and its compliance check.",
        "writes": "deliverable video",
        "verification": "ffmpeg-skill check.py table; non-zero exit on any FAIL row",
        "ffmpeg_skill": ["render --template", "metadata (--chapters)", "check"],
        "dry_run": True,
    },
    "pipeline": {
        "role": "orchestration",
        "summary": "analyze -> render -> deliver in one call, stopping at the first failed step.",
        "writes": "timeline.json, render, deliverable",
        "verification": "each step's own verification",
        "ffmpeg_skill": ["probe", "scenes", "silence", "fit (--conform)", "color (--conform)", "look",
                         "render --template", "check"],
        "dry_run": True,
    },
    "doctor": {
        "role": "verification",
        "summary": "What this machine can do: Python, Node/npm, ffmpeg-skill, ffmpeg, a project's Remotion install.",
        "writes": None,
        "verification": "reports only",
        "ffmpeg_skill": ["_contract doctor"],
        "dry_run": False,
    },
}

# What each tool's --json result carries (beyond the shared status / dry_run / output), as
# key -> short type. "result" is a completed run, "dry_run" a --dry-run plan. tests check real
# outputs against these, so the contract cannot promise a key a script stopped writing.
OUTPUTS: Dict[str, Dict[str, Dict[str, str]]] = {
    "analyze": {
        "result": {"commands": "list[str]", "verified": "bool", "summary": "object: duration, fps, size, scenes, "
                   "silences, speech_seconds, peaks, captions, chapters, beats, tempo_bpm, highlights, clips, words, "
                   "conformed (list: vfr / hdr)",
                   "warnings": "list[str]"},
        "dry_run": {"commands": "list[str]"},
    },
    "init": {
        "result": {"commands": "list[str]", "installed": "bool", "entry": "str", "compositions": "list[str]"},
        "dry_run": {"commands": "list[str]"},
    },
    "still": {
        "result": {"outputs": "list[str] (PNG paths)", "frames": "list[int]", "commands": "list[str]",
                   "verified": "bool", "frame": "object|null {width, height, fit}", "font": "str|null"},
        "dry_run": {"outputs": "list[str]", "frames": "list[int]", "commands": "list[str]"},
    },
    "render": {
        "result": {"verified": "bool", "verification": "list[{check, status, value, expected}]",
                   "commands": "list[str]", "look": "str|null (contact sheet PNG)", "look_error": "str|null",
                   "summary": "str", "frame": "object|null", "font": "str|null", "mode": "full|overlay",
                   "graphics": "str|null (kept ProRes 4444 layer)",
                   "sparse": "null|{used, reason, stretches, drawn_frames, source_frames} (--sparse)",
                   "kind": "null|failed",
                   "error": "null|str (which verification rows failed)"},
        "dry_run": {"commands": "list[str]", "props": "str", "expected_frames": "int|null", "frame": "object|null",
                    "font": "str|null", "sparse": "null|object (--sparse)"},
    },
    "deliver": {
        "result": {"checked": "str", "platform": "str|null", "verified": "bool",
                   "description": "str|null (YouTube description block with the chapters, --chapters)",
                   "checks": "list[{check, status, value, expected, ...}] (ffmpeg-skill check.py rows)",
                   "failed": "list[str]", "warnings": "list[str]", "commands": "list[str]",
                   "kind": "null|failed", "error": "null|str"},
        "dry_run": {"commands": "list[str]"},
    },
    "pipeline": {
        "result": {"timeline": "str", "render": "str", "deliverable": "str|null", "look": "str|null",
                   "verified": "bool", "warnings": "list[str]", "steps": "list[{step, status, output, command}]"},
        "dry_run": {"steps": "list[{step, status, output, command}]"},
    },
    "doctor": {
        "result": {"ok": "bool", "version": "str", "checks": "list[{check, ok, value, fix}]",
                   "ffmpeg_skill_doctor": "object|null"},
        "dry_run": {},
    },
}
SHARED_OUTPUT = {"status": "completed|failed", "dry_run": "bool", "output": "str|null (main artifact)"}
FAILURE_OUTPUT = {"status": "failed", "error": "str", "kind": "input|missing_tool|timeout|failed", "dry_run": "bool"}


def missing_output_keys(tool: str, doc: Dict[str, Any]) -> List[str]:
    """Keys the contract promises for this result that `doc` lacks (empty = conforms)."""
    if doc.get("status") == "failed":
        return [k for k in FAILURE_OUTPUT if k not in doc]
    which = "dry_run" if doc.get("dry_run") else "result"
    want = list(OUTPUTS[tool][which]) + [k for k in SHARED_OUTPUT if not (tool == "doctor" and k == "output")]
    return [k for k in want if k not in doc]


# Flags every tool takes; the MCP server adds --json itself.
SHARED = {"json", "dry_run", "overwrite", "timeout", "help"}


def public_tools() -> List[str]:
    return sorted(p.stem for p in HERE.glob("*.py") if not p.stem.startswith("_"))


def _json_type(action: argparse.Action) -> Dict[str, Any]:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return {"type": "boolean"}
    t: Dict[str, Any]
    if action.type is int:
        t = {"type": "integer"}
    elif action.type is float:
        t = {"type": "number"}
    else:
        t = {"type": "string"}
    if action.choices:
        t["enum"] = list(action.choices)
    if isinstance(action, argparse._AppendAction) or action.nargs in ("+", "*"):
        t = {"type": "array", "items": t}
        if action.nargs == "+":
            t["minItems"] = 1
    return t


def input_schema(parser: argparse.ArgumentParser) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    required: List[str] = []
    positional: List[str] = []
    for a in parser._actions:
        if a.dest in SHARED or isinstance(a, argparse._HelpAction):
            continue
        schema = _json_type(a)
        if a.help and a.help is not argparse.SUPPRESS:
            schema["description"] = a.help.replace("%%", "%")
        if a.default not in (None, False, argparse.SUPPRESS) and not isinstance(a, argparse._AppendAction):
            schema["default"] = a.default
        props[a.dest] = schema
        if not a.option_strings:
            positional.append(a.dest)
            required.append(a.dest)
        elif a.required:
            required.append(a.dest)
    props["dry_run"] = {"type": "boolean", "description": "plan only: return the commands, write nothing"}
    props["overwrite"] = {"type": "boolean", "description": "allow replacing an existing output file"}
    props["timeout"] = {"type": "number", "description": "wall-clock limit per external step in seconds (default 1800)"}
    return {"type": "object", "properties": props, "required": required, "x-positional": positional,
            "additionalProperties": False}


def flag_for(parser: argparse.ArgumentParser) -> Dict[str, str]:
    """dest -> the long option string the CLI accepts (for building argv from structured arguments)."""
    out: Dict[str, str] = {}
    for a in parser._actions:
        longs = [o for o in a.option_strings if o.startswith("--")]
        if longs:
            out[a.dest] = longs[0]
    return out


def tool_spec(name: str) -> Dict[str, Any]:
    mod = importlib.import_module(name)
    parser = mod.build_parser()
    meta = TOOL_META[name]
    doc = (mod.__doc__ or "").strip()
    return {
        "name": name,
        "script": f"scripts/{name}.py",
        "role": meta["role"],
        "summary": meta["summary"],
        "description": doc.split("\n\n")[0].replace("\n", " "),
        "writes": meta["writes"],
        "verification": meta["verification"],
        "ffmpeg_skill": meta["ffmpeg_skill"],
        "dry_run": meta["dry_run"],
        "inputSchema": input_schema(parser),
        "flags": flag_for(parser),
        "output": OUTPUTS[name],
    }


# The AI Video Production OS registry's keys (skill_id, provides[], dependencies[]): one capability
# per public tool except doctor, all EXPERIMENTAL; ffmpeg-skill is the only Skill this one calls.
PROVIDES_EXCLUDE = {"doctor"}
FFMPEG_SKILL_RANGE = ">=2.0.0 <3.0.0"


def provides() -> List[Dict[str, str]]:
    return [{"id": f"remotion.{n}", "lifecycle": "EXPERIMENTAL", "tool_id": f"{SKILL_ID}/{n}"}
            for n in TOOL_META if n not in PROVIDES_EXCLUDE]


def dependencies() -> List[Dict[str, Any]]:
    used = sorted({s.split()[0] for m in TOOL_META.values() for s in m["ffmpeg_skill"]})
    return [{"skill_id": "ffmpeg-skill", "version_range": FFMPEG_SKILL_RANGE, "required": True,
             "url": "https://github.com/kajisho5/ffmpeg-skill", "scripts": used}]


def build() -> Dict[str, Any]:
    return {
        "skill_id": SKILL_ID,
        "skill": {"id": SKILL_ID, "version": version()},
        "version": version(),
        "contract_version": CONTRACT_VERSION,
        "provides": provides(),
        "dependencies": dependencies(),
        "timeline_schema": TIMELINE_SCHEMA,
        "depends_on": {"ffmpeg-skill": "https://github.com/kajisho5/ffmpeg-skill", "node": ">=18",
                       "python": ">=3.10"},
        "roles": ROLES,
        "output_shared": SHARED_OUTPUT,
        "output_failure": FAILURE_OUTPUT,
        "conventions": {
            "output": "one JSON object on stdout with --json; human lines on stderr",
            "errors": {"input": 2, "missing_tool": 3, "timeout": 4, "failed": 1},
            "originals": "inputs are never modified; an existing output is refused without --overwrite",
        },
        "tools": [tool_spec(n) for n in TOOL_META],
    }


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "doctor":
        sys.exit(subprocess.call([sys.executable, str(HERE / "doctor.py"), *sys.argv[2:]]))
    p = argparse.ArgumentParser(description="remotion-ffmpeg-skill execution contract")
    p.add_argument("--json", action="store_true", help="print the contract as JSON (the default output)")
    p.parse_args()
    print(json.dumps(build(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
