"""Contract and MCP transport tests (no media, no Node needed)."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "mcp"))

import _contract  # noqa: E402
import server  # noqa: E402


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = _contract.build()

    def test_every_public_script_is_described_and_nothing_else(self):
        self.assertEqual(sorted(_contract.TOOL_META), _contract.public_tools())

    def test_roles_and_schema_shape(self):
        for t in self.c["tools"]:
            with self.subTest(tool=t["name"]):
                self.assertIn(t["role"], _contract.ROLES)
                s = t["inputSchema"]
                self.assertEqual(s["type"], "object")
                self.assertFalse(s["additionalProperties"])
                for req in s["required"]:
                    self.assertIn(req, s["properties"])
                self.assertNotIn("json", s["properties"])  # the transport adds --json itself

    def test_schema_follows_argparse(self):
        render = next(t for t in self.c["tools"] if t["name"] == "render")
        props = render["inputSchema"]["properties"]
        self.assertEqual(props["codec"]["enum"], ["h264", "prores"])
        self.assertEqual(props["aspect"]["enum"][0], "source")
        self.assertEqual(props["overlay"]["type"], "boolean")
        self.assertEqual(sorted(render["inputSchema"]["required"]), ["comp", "project", "timeline"])
        analyze = next(t for t in self.c["tools"] if t["name"] == "analyze")
        self.assertEqual(analyze["inputSchema"]["properties"]["input"]["type"], "array")
        still = next(t for t in self.c["tools"] if t["name"] == "still")
        self.assertEqual(still["inputSchema"]["properties"]["at"]["type"], "array")

    def test_cli_prints_the_contract(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "_contract.py"), "--json"],
                             capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(out.stdout)["skill"], "remotion-ffmpeg-skill")


class Outputs(unittest.TestCase):
    def test_every_tool_declares_result_and_dry_run_shapes(self):
        for name in _contract.TOOL_META:
            self.assertEqual(set(_contract.OUTPUTS[name]), {"result", "dry_run"}, name)

    def test_doctor_and_dry_runs_conform(self):
        def run(*args):
            p = subprocess.run([sys.executable, *map(str, args), "--json"], capture_output=True, text=True)
            return json.loads(p.stdout)
        doc = run(ROOT / "scripts" / "doctor.py")
        self.assertEqual(_contract.missing_output_keys("doctor", doc), [])
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            doc = run(ROOT / "scripts" / "init.py", Path(d) / "p", "--dry-run")
            self.assertEqual(_contract.missing_output_keys("init", doc), [])
            doc = run(ROOT / "scripts" / "render.py", "--project", Path(d) / "nope", "--comp", "Captioned",
                      "--timeline", Path(d) / "missing.json")
            self.assertEqual(doc["status"], "failed")
            self.assertEqual(_contract.missing_output_keys("render", doc), [])


class Packaging(unittest.TestCase):
    def test_versions_agree(self):
        pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(plugin["version"], pkg["version"])
        self.assertIn(f"## {pkg['version']}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))

    def test_installer_ships_what_skill_md_needs(self):
        js = (ROOT / "cli" / "remotion-ffmpeg-skill.js").read_text(encoding="utf-8")
        for item in ("SKILL.md", "scripts", "templates", "references", "mcp"):
            self.assertIn(f"'{item}'", js)


class Transport(unittest.TestCase):
    def test_argv_from_structured_arguments(self):
        argv = server.build_argv("render", {"project": "p", "comp": "Jumpcut", "timeline": "t.json",
                                            "aspect": "9:16", "fast": True, "no_look": False, "dry_run": True})
        self.assertEqual(argv[:2], ["--project", "p"])
        self.assertIn("--aspect", argv)
        self.assertIn("--fast", argv)
        self.assertNotIn("--no-look", argv)
        self.assertEqual(argv[-2:], ["--dry-run", "--json"])

    def test_positional_and_repeatable(self):
        argv = server.build_argv("still", {"project": "p", "comp": "Captioned", "timeline": "t", "at": [1.5, 6]})
        self.assertEqual(argv.count("--at"), 2)
        argv = server.build_argv("analyze", {"input": ["a.mp4"], "captions": "a.srt"})
        self.assertEqual(argv[0], "a.mp4")
        argv = server.build_argv("analyze", {"input": ["a.mp4", "b.mov"]})
        self.assertEqual(argv[:2], ["a.mp4", "b.mov"])

    def test_generated_reference_is_current(self):
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "_docs.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_bad_arguments_are_input_errors(self):
        for args in ({"bogus": 1}, {"comp": "Captioned"}):
            res = server.call_tool("render", args)
            self.assertTrue(res["isError"])
            self.assertEqual(json.loads(res["content"][0]["text"])["kind"], "input")

    def test_json_rpc_over_stdio(self):
        msgs = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "nope"},
        ]
        proc = subprocess.run([sys.executable, str(ROOT / "mcp" / "server.py")],
                              input="\n".join(json.dumps(m) for m in msgs) + "\nnot json\n",
                              capture_output=True, text=True, timeout=60)
        replies = [json.loads(l) for l in proc.stdout.splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, None])  # no reply to the notification
        self.assertEqual(replies[0]["result"]["serverInfo"]["name"], "remotion-ffmpeg-skill")
        self.assertEqual([t["name"] for t in replies[1]["result"]["tools"]][0], "analyze")
        self.assertEqual(replies[2]["error"]["code"], -32602)
        self.assertEqual(replies[3]["error"]["code"], -32601)
        self.assertEqual(replies[4]["error"]["code"], -32700)


if __name__ == "__main__":
    unittest.main()
