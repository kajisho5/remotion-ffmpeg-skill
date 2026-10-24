"""Integration tests with real media. Need ffmpeg and ffmpeg-skill (FFMPEG_SKILL_DIR or installed);
skipped otherwise. Set RFS_PROJECT to an installed Remotion project (init.py --install) to also run
real renders -- slow (a Chromium render per composition), so off by default."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import _common  # noqa: E402

HAVE = shutil.which("ffmpeg") and _common.find_ffmpeg_skill() is not None
PROJECT = os.environ.get("RFS_PROJECT")

SRT = """1
00:00:00,300 --> 00:00:02,800
Placeholder caption one.

2
00:00:03,200 --> 00:00:04,500
Inside the silence.

3
00:00:05,200 --> 00:00:07,600
Placeholder caption two.
"""


def make_fixture(d: Path) -> Path:
    """8 s, 1280x720 30 fps, two shots, tone - 2 s silence - tone (fictional test media)."""
    out = d / "fixture.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
        "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=30:duration=4",
        "-f", "lavfi", "-i", "sine=f=440:d=3", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
        "-f", "lavfi", "-i", "sine=f=660:d=3",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a]aresample=44100,aformat=channel_layouts=mono[a1];"
        "[4:a]aresample=44100,aformat=channel_layouts=mono[a2];[a1][3:a][a2]concat=n=3:v=0:a=1[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out),
    ], check=True)
    return out


def script(name, *args):
    proc = subprocess.run([sys.executable, str(SCRIPTS / f"{name}.py"), *map(str, args), "--json"],
                          capture_output=True, text=True)
    return proc.returncode, json.loads(proc.stdout)


@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")
class Analyze(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="rfs-"))
        cls.src = make_fixture(cls.tmp)
        (cls.tmp / "cues.srt").write_text(SRT, encoding="utf-8")
        cls.tl = cls.tmp / "fixture.timeline.json"
        code, cls.result = script("analyze", cls.src, "--captions", cls.tmp / "cues.srt", "-o", cls.tl)
        assert code == 0, cls.result
        cls.timeline = json.loads(cls.tl.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_measured_source(self):
        s = self.timeline["source"]
        self.assertEqual((s["width"], s["height"], s["fps"]), (1280, 720, 30.0))
        self.assertAlmostEqual(s["duration"], 8.0, places=1)
        self.assertEqual(_common.validate_timeline(self.timeline), [])

    def test_scene_cut_and_silence_found(self):
        self.assertEqual(len(self.timeline["scenes"]), 2)
        self.assertAlmostEqual(self.timeline["scenes"][1]["start"], 4.0, places=1)
        self.assertEqual(len(self.timeline["silences"]), 1)
        s, e = self.timeline["silences"][0]
        self.assertAlmostEqual(s, 3.0, delta=0.1)
        self.assertAlmostEqual(e, 5.0, delta=0.1)
        self.assertEqual(len(self.timeline["speech"]), 2)

    def test_captions_carried_as_written(self):
        self.assertEqual([c["text"] for c in self.timeline["captions"]],
                         ["Placeholder caption one.", "Inside the silence.", "Placeholder caption two."])

    def test_existing_output_refused(self):
        code, res = script("analyze", self.src, "-o", self.tl)
        self.assertEqual(code, 2)
        self.assertEqual(res["kind"], "input")

    def test_render_dry_run_plans_exact_frames(self):
        proj = self.tmp / "proj"
        code, res = script("init", proj)
        self.assertEqual(code, 0, res)
        code, res = script("render", "--project", proj, "--comp", "Jumpcut", "--timeline", self.tl,
                           "-o", self.tmp / "j.mp4", "--dry-run")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["expected_frames"], _common.expected_frames("Jumpcut", self.timeline))
        self.assertIn("render src/index.ts Jumpcut", res["commands"][0])

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_renders_verify(self):
        for comp in _common.BUILTIN_COMPOSITIONS:
            with self.subTest(comp=comp):
                code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", self.tl,
                                   "-o", self.tmp / f"{comp}.mp4", "--fast")
                self.assertEqual(code, 0, res)
                self.assertTrue(res["verified"])
                self.assertTrue(res["look"] and Path(res["look"]).is_file())


if __name__ == "__main__":
    unittest.main()
