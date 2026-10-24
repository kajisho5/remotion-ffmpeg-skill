#!/usr/bin/env python3
"""remotion-ffmpeg-skill as an MCP server (stdio, JSON-RPC 2.0) -- standard library only.

Every public script becomes a tool; names, order and input schemas come from the contract
(scripts/_contract.py), so this file is only the transport. Arguments are a flat object whose
keys are the CLI's argument names (positional ones included), or {"argv": [...]} for raw CLI
arguments. Results are the script's --json output, as text and as structuredContent; a failed
step comes back with isError: true and its typed error (kind: input / missing_tool / timeout / failed).

Run:
  python3 mcp/server.py
Claude Code:
  claude mcp add remotion-ffmpeg-skill -- python3 /path/to/remotion-ffmpeg-skill/mcp/server.py
Claude Desktop (claude_desktop_config.json):
  {"mcpServers": {"remotion-ffmpeg-skill": {"command": "python3",
                  "args": ["/path/to/remotion-ffmpeg-skill/mcp/server.py"]}}}
ffmpeg-skill must be installed next to it or pointed to with FFMPEG_SKILL_DIR (set it in "env").
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "scripts"
PROTOCOL_VERSION = "2024-11-05"

sys.path.insert(0, str(SCRIPTS))
import _contract  # noqa: E402

_CONTRACT: Dict[str, Any] = {}


def contract() -> Dict[str, Any]:
    if not _CONTRACT:
        _CONTRACT.update(_contract.build())
    return _CONTRACT


def spec(name: str) -> Optional[Dict[str, Any]]:
    return next((t for t in contract()["tools"] if t["name"] == name), None)


def build_argv(name: str, args: Dict[str, Any]) -> List[str]:
    if isinstance(args.get("argv"), list):
        argv = [str(a) for a in args["argv"]]
        return argv if "--json" in argv else argv + ["--json"]
    s = spec(name)
    if s is None:
        raise ValueError(f"unknown tool {name!r}")
    schema = s["inputSchema"]
    unknown = sorted(set(args) - set(schema["properties"]))
    if unknown:
        raise ValueError(f"{name}: unknown argument(s) {unknown}; see tools/list for the schema")
    missing = [k for k in schema["required"] if args.get(k) in (None, "")]
    if missing:
        raise ValueError(f"{name}: missing required argument(s) {missing}")
    argv: List[str] = [str(args[k]) for k in schema["x-positional"] if args.get(k) is not None]
    flags = dict(s["flags"], dry_run="--dry-run", overwrite="--overwrite", timeout="--timeout")
    for key, val in args.items():
        if key in schema["x-positional"] or val is None or val is False:
            continue
        flag = flags[key]
        if val is True:
            argv.append(flag)
        elif isinstance(val, list):
            for v in val:
                argv += [flag, str(v)]
        else:
            argv += [flag, str(val)]
    return argv + ["--json"]


def call_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    try:
        argv = build_argv(name, args or {})
    except ValueError as e:
        return {"content": [{"type": "text", "text": json.dumps({"status": "failed", "kind": "input", "error": str(e)})}],
                "isError": True}
    proc = subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py"), *argv],
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = {"status": "failed", "kind": "failed", "error": (proc.stderr or proc.stdout).strip()[-1500:]}
    failed = proc.returncode != 0 or data.get("status") == "failed"
    return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
            "structuredContent": data, "isError": failed}


def tools_list() -> Dict[str, Any]:
    out = []
    for t in contract()["tools"]:
        schema = {k: v for k, v in t["inputSchema"].items() if not k.startswith("x-")}
        desc = f"{t['summary']} Writes: {t['writes'] or 'nothing'}. Verifies: {t['verification']}."
        out.append({"name": t["name"], "description": desc, "inputSchema": schema})
    return {"tools": out}


def handle(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:  # notification (e.g. notifications/initialized): no reply
        return None
    try:
        if method == "initialize":
            result: Any = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "remotion-ffmpeg-skill", "version": contract()["version"]},
                "instructions": "Workflow: analyze (measure) -> still (preview) -> render (verified) -> deliver "
                                "(template + check). pipeline does all of it. Read the 'look' contact sheet "
                                "path a render returns before reporting.",
            }
        elif method == "tools/list":
            result = tools_list()
        elif method == "tools/call":
            p = msg.get("params") or {}
            if spec(p.get("name", "")) is None:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {p.get('name')!r}"}}
            result = call_tool(p["name"], p.get("arguments") or {})
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    except Exception as e:  # keep the server alive; report the failure to the client
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                         "error": {"code": -32700, "message": "parse error"}}) + "\n")
            sys.stdout.flush()
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
