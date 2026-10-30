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
import _contract  # noqa: E402

HAVE = shutil.which("ffmpeg") and _common.find_ffmpeg_skill() is not None
PROJECT = os.environ.get("RFS_PROJECT")
TRANSCRIPT = ROOT / "tests" / "fixtures" / "transcript.json"   # transcription-skill/transcript/0.1, fictional

# The caption timeline TRANSCRIPT must produce on the 8 s fixture: every time is the transcript's own.
# seg_0001 (Japanese, no spaces) is one cue from its words; seg_0002 has no word timings, so it is one
# plain cue on the segment's times; seg_0003 splits at its 0.8 s pause; cues never cross a segment.
TRANSCRIPT_CUES = [
    {"start": 0.3, "end": 2.8, "text": "本日の講演を始めます。"},
    {"start": 3.2, "end": 4.5, "text": "Inside the silence."},
    {"start": 5.2, "end": 6.4, "text": "Welcome to the first session."},
    {"start": 7.2, "end": 7.6, "text": "Thanks."},
]
TRANSCRIPT_WORDS = [
    (0.3, 0.7, "本日"), (0.7, 0.86, "の"), (0.86, 1.4, "講演"), (1.4, 1.56, "を"), (1.56, 2.1, "始め"),
    (2.1, 2.8, "ます。"), (5.2, 5.6, " Welcome"), (5.6, 5.74, " to"), (5.74, 5.9, " the"), (5.9, 6.3, " first"),
    (6.3, 6.4, " session."), (7.2, 7.6, " Thanks."),
]

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

    def test_outputs_match_the_contract(self):
        self.assertEqual(_contract.missing_output_keys("analyze", self.result), [])
        code, res = script("analyze", self.src, "-o", self.tmp / "dry.json", "--dry-run")
        self.assertEqual(_contract.missing_output_keys("analyze", res), [])
        code, res = script("deliver", self.src, "--check-only", "--platform", "youtube")
        self.assertEqual(_contract.missing_output_keys("deliver", res), [], res)

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

    def test_transcript_drives_the_caption_timeline(self):
        tl = self.tmp / "transcript.timeline.json"
        code, res = script("analyze", self.src, "--words", TRANSCRIPT, "-o", tl, "--no-scenes")
        self.assertEqual(code, 0, res)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual(_common.validate_timeline(t), [])
        self.assertEqual(t["captions"], TRANSCRIPT_CUES)
        self.assertEqual([(w["start"], w["end"], w["text"]) for w in t["words"]], TRANSCRIPT_WORDS)
        self.assertEqual(res["summary"]["captions"], 4)
        self.assertEqual(res["summary"]["words"], 12)
        warn = "\n".join(t["warnings"])
        self.assertIn("transcript: seg_0002: word timestamps discarded", warn)   # the transcript's own warning
        self.assertIn("no word timings for seg_0002", warn)
        self.assertIn("not these exact bytes", warn)                             # fixture.json names other bytes
        for comp in ("Karaoke", "Captioned"):
            proj = self.tmp / "proj_tr"
            if not proj.exists():
                script("init", proj)
            code, res = script("render", "--project", proj, "--comp", comp, "--timeline", tl,
                               "-o", self.tmp / f"tr_{comp}.mp4", "--dry-run")
            self.assertEqual(code, 0, res)
            self.assertEqual(res["expected_frames"], _common.expected_frames(comp, t))

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_karaoke_from_transcript(self):
        tl = self.tmp / "transcript_real.timeline.json"
        code, res = script("analyze", self.src, "--words", TRANSCRIPT, "-o", tl, "--no-scenes")
        self.assertEqual(code, 0, res)
        proc = subprocess.run([sys.executable, str(SCRIPTS / "render.py"), "--project", PROJECT, "--comp", "Karaoke",
                               "--timeline", str(tl), "-o", str(self.tmp / "real_transcript_karaoke.mp4"), "--fast",
                               "--json"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:] + proc.stderr[-4000:])
        self.assertTrue(json.loads(proc.stdout)["verified"])

    def test_transcript_words_with_srt_cues(self):
        tl = self.tmp / "transcript_srt.timeline.json"
        code, res = script("analyze", self.src, "--captions", self.tmp / "cues.srt", "--words", TRANSCRIPT,
                           "-o", tl, "--no-scenes", "--no-silence")
        self.assertEqual(code, 0, res)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual(t["captions"], self.timeline["captions"])   # the SRT wins, unchanged
        self.assertEqual(len(t["words"]), 12)

    def test_transcript_refused_when_it_cannot_be_trusted(self):
        doc = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
        cases = {
            "version": dict(doc, schema="transcription-skill/transcript/0.2"),
            "missing": {k: v for k, v in doc.items() if k != "provenance"},
            "other_file": dict(doc, duration=20.0, source=dict(doc["source"], media_duration=20.0)),
        }
        for name, bad in cases.items():
            with self.subTest(name):
                f = self.tmp / f"bad_{name}.json"
                f.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
                out = self.tmp / f"bad_{name}.timeline.json"
                code, res = script("analyze", self.src, "--words", f, "-o", out, "--no-scenes", "--no-silence")
                self.assertEqual(code, 2, res)
                self.assertEqual(res["kind"], "input")
                self.assertFalse(out.exists())

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
        self.assertEqual(_contract.missing_output_keys("render", res), [])
        self.assertIn("render src/index.ts Jumpcut", res["commands"][0])

    def test_overlay_refuses_what_it_cannot_do(self):
        proj = self.tmp / "proj2"
        script("init", proj)
        for extra in (["--comp", "Jumpcut"], ["--comp", "Captioned", "--aspect", "9:16"],
                      ["--comp", "Captioned", "--fast"]):
            with self.subTest(extra=extra):
                code, res = script("render", "--project", proj, "--timeline", self.tl, "--overlay",
                                   "-o", self.tmp / "ov.mp4", "--dry-run", *extra)
                self.assertEqual(code, 2, res)
                self.assertEqual(res["kind"], "input")
        code, res = script("render", "--project", proj, "--timeline", self.tl, "--overlay", "--comp", "Captioned",
                           "-o", self.tmp / "ov.mp4", "--dry-run")
        self.assertEqual(code, 0, res)
        self.assertIn("prores-profile=4444", res["commands"][0])
        self.assertIn("overlay.py", res["commands"][1])

    def test_sparse_plans_placements_or_says_why_not(self):
        proj = self.tmp / "proj3"
        script("init", proj)
        code, res = script("render", "--project", proj, "--timeline", self.tl, "--sparse", "--comp", "Jumpcut",
                           "-o", self.tmp / "sp.mp4", "--dry-run")
        self.assertEqual((code, res["kind"]), (2, "input"))
        code, res = script("render", "--project", proj, "--timeline", self.tl, "--sparse", "--comp", "Captioned",
                           "--merge-gap", "0", "-o", self.tmp / "sp.mp4", "--dry-run")
        self.assertEqual(code, 0, res)
        sp = res["sparse"]
        if sp["used"]:
            # three cues, the middle one inside the silence: three stretches, each placed
            self.assertEqual(sp["stretches"], 3)
            self.assertEqual(res["commands"][1].count("--place"), 3)
            self.assertLess(sp["drawn_frames"], sp["source_frames"])
        else:
            self.assertIn("--place", sp["reason"])

    def test_pip_offset_is_measured_from_the_audio(self):
        # the camera is the source's own audio from 1.5 s on, over another picture
        cam = self.tmp / "camera.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", str(self.src),
                        "-f", "lavfi", "-i", "smptebars=size=320x180:rate=30:duration=6.5",
                        "-map", "1:v", "-map", "0:a", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", str(cam)], check=True)
        tl = self.tmp / "pip.timeline.json"
        code, res = script("analyze", self.src, "--pip", cam, "-o", tl, "--no-scenes")
        self.assertEqual(code, 0, res)
        pip = json.loads(tl.read_text(encoding="utf-8"))["pip"]
        self.assertAlmostEqual(pip["offset"], 1.5, delta=0.05)
        self.assertTrue(pip["measured"])
        self.assertEqual((pip["width"], pip["height"]), (320, 180))
        code, res = script("analyze", self.src, "--pip", cam, "--pip-offset", "-2", "-o", self.tmp / "p2.json",
                           "--no-scenes")
        self.assertEqual(code, 0, res)
        code, res = script("analyze", self.src, "--pip", cam, "--pip-offset", "30", "-o", self.tmp / "p3.json",
                           "--no-scenes")
        self.assertEqual((code, res["kind"]), (2, "input"))  # never overlaps
        proj = self.tmp / "proj_pip"
        script("init", proj)
        code, res = script("render", "--project", proj, "--comp", "Pip", "--timeline", tl, "--overlay",
                           "-o", self.tmp / "x.mp4", "--dry-run")
        self.assertEqual((code, res["kind"]), (2, "input"))

    def test_brand_logo_goes_to_the_template(self):
        bdir = self.tmp / "brand"
        bdir.mkdir(exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x1E6F8E:s=64x64",
                        "-frames:v", "1", str(bdir / "logo.png")], check=True)
        (bdir / "brand.json").write_text('{"colors": {"primary": "E53935"}, "logo": "logo.png"}', encoding="utf-8")
        code, res = script("deliver", self.src, "--platform", "youtube", "--brand", bdir / "brand.json",
                           "-o", self.tmp / "b.mp4", "--dry-run")
        self.assertEqual(code, 0, res)
        self.assertIn("--logo", res["commands"][0])
        self.assertIn(str((bdir / "logo.png").resolve()), res["commands"][0])

    def test_deliver_without_chapters(self):
        out = self.tmp / "plain_youtube.mp4"
        code, res = script("deliver", self.src, "--platform", "youtube", "-o", out)
        self.assertEqual(code, 0, res)
        self.assertTrue(res["verified"])
        self.assertIsNone(res["description"])

    def test_chapters_from_a_file_and_from_the_source(self):
        chf = self.tmp / "chapters.txt"
        chf.write_text("0:00 Placeholder opening\n0:04 Placeholder second part\n", encoding="utf-8")
        tl = self.tmp / "ch.timeline.json"
        code, res = script("analyze", self.src, "--chapters", chf, "-o", tl)
        self.assertEqual(code, 0, res)
        self.assertEqual(res["summary"]["chapters"], 2)
        self.assertTrue(any("three" in w for w in res["warnings"]))  # YouTube needs three
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual([c["title"] for c in t["chapters"]], ["Placeholder opening", "Placeholder second part"])
        self.assertAlmostEqual(t["chapters"][-1]["end"], 8.0, places=1)
        # deliver writes them into the file and the description block next to it
        out = self.tmp / "ch_youtube.mp4"
        code, res = script("deliver", self.src, "--platform", "youtube", "--chapters", chf, "-o", out)
        self.assertEqual(code, 0, res)
        self.assertEqual((self.tmp / "ch_youtube_description.txt").read_text(encoding="utf-8"),
                         "00:00 Placeholder opening\n00:04 Placeholder second part\n")
        # and analyze reads chapters a file already carries
        tl2 = self.tmp / "ch2.timeline.json"
        code, res = script("analyze", out, "--chapters", "source", "-o", tl2)
        self.assertEqual(code, 0, res)
        t2 = json.loads(tl2.read_text(encoding="utf-8"))
        self.assertEqual([(round(c["start"], 1), c["title"]) for c in t2["chapters"]],
                         [(0.0, "Placeholder opening"), (4.0, "Placeholder second part")])
        code, res = script("analyze", self.src, "--chapters", "source", "-o", self.tmp / "none.json")
        self.assertEqual((code, res["kind"]), (2, "input"))

    def test_several_inputs_are_joined_then_measured(self):
        b = self.tmp / "b.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=2",
                        "-f", "lavfi", "-i", "sine=f=500:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", str(b)], check=True)
        tl = self.tmp / "joined.timeline.json"
        code, res = script("analyze", self.src, b, "-o", tl, "--joined", self.tmp / "joined.mp4")
        self.assertEqual(code, 0, res)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual([c["name"] for c in t["clips"]], ["fixture.mp4", "b.mp4"])
        self.assertAlmostEqual(t["clips"][1]["start"], 8.0, delta=0.1)
        self.assertEqual((t["source"]["width"], t["source"]["fps"]), (1280, 30.0))  # normalised to the first clip
        self.assertAlmostEqual(t["source"]["duration"], 10.0, delta=0.15)

    def test_platform_aspect_comes_from_ffmpeg_skill_templates(self):
        self.assertEqual(_common.platform_aspect("reels"), "9:16")
        self.assertEqual(_common.platform_aspect("youtube"), "16:9")
        self.assertIsNone(_common.platform_aspect("podcast"))

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_beats_highlights_titles(self):
        src = self.tmp / "music.mp4"
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=4",
            "-f", "lavfi", "-i", "smptebars=size=640x360:rate=30:duration=4",
            "-f", "lavfi", "-i", "aevalsrc='sin(2*PI*80*t)*exp(-mod(t\\,0.5)*12)*(0.4+0.6*gt(t\\,4))':s=44100:d=8",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0,format=yuv420p[v]",
            "-map", "[v]", "-map", "2:a", "-c:v", "libx264", "-c:a", "aac", "-t", "8", str(src)], check=True)
        tl = self.tmp / "music.timeline.json"
        code, res = script("analyze", src, "-o", tl, "--beats", "--highlights", "1")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["summary"]["beats"])
        opts = self.tmp / "opts.json"
        opts.write_text(json.dumps({"sceneTitles": ["One", "Two"], "title": "Sample",
                                    "lowerThirds": [{"text": "Name", "sub": "Role", "start": 1, "end": 3}]}))
        for comp in ("Titled", "Highlights", "BeatMontage"):
            with self.subTest(comp=comp):
                code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", tl,
                                   "--options", opts, "-o", self.tmp / f"music_{comp}.mp4", "--fast")
                self.assertEqual(code, 0, res)
                self.assertTrue(res["verified"])

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_portrait_and_overlay(self):
        code, res = script("render", "--project", PROJECT, "--comp", "Captioned", "--timeline", self.tl,
                           "-o", self.tmp / "portrait.mp4", "--aspect", "9:16", "--fast")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["frame"], {"width": 720, "height": 1280, "fit": "blur"})
        code, res = script("render", "--project", PROJECT, "--comp", "Captioned", "--timeline", self.tl,
                           "-o", self.tmp / "overlay.mp4", "--overlay")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["mode"], "overlay")
        self.assertTrue(res["verified"])

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_sparse_matches_the_full_layer(self):
        opts = self.tmp / "titles.json"
        opts.write_text(json.dumps({"sceneTitles": ["One", "Two"],
                                    "lowerThirds": [{"text": "Name", "sub": "Role", "start": 5.5, "end": 7}]}))
        for comp, extra in (("Captioned", []), ("Titled", ["--options", opts])):
            with self.subTest(comp=comp):
                full, sparse = self.tmp / f"sp_full_{comp}.mp4", self.tmp / f"sp_sparse_{comp}.mp4"
                code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", self.tl,
                                   "-o", full, "--overlay", "--no-look", *extra)
                self.assertEqual(code, 0, res)
                code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", self.tl,
                                   "-o", sparse, "--sparse", "--merge-gap", "0", "--no-look", *extra)
                self.assertEqual(code, 0, res)
                if not res["sparse"]["used"]:
                    self.skipTest(res["sparse"]["reason"])
                self.assertTrue(res["verified"])
                self.assertLess(res["sparse"]["drawn_frames"], res["sparse"]["source_frames"])
                stats = self.tmp / f"psnr_{comp}.txt"
                subprocess.run(["ffmpeg", "-v", "error", "-i", str(full), "-i", str(sparse),
                                "-lavfi", f"[0:v][1:v]psnr=stats_file={stats.name}", "-f", "null", "-"],
                               check=True, cwd=self.tmp)
                differ = [r for r in stats.read_text().split("\n") if r.strip() and "psnr_avg:inf" not in r]
                self.assertEqual(differ, [], f"{comp}: sparse output differs from the full-length layer")

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_renders_verify(self):
        for comp in _common.BUILTIN_COMPOSITIONS:
            with self.subTest(comp=comp):
                code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", self.tl,
                                   "-o", self.tmp / f"{comp}.mp4", "--fast")
                self.assertEqual(code, 0, res)
                self.assertTrue(res["verified"])
                self.assertEqual(_contract.missing_output_keys("render", res), [])
                self.assertTrue(res["look"] and Path(res["look"]).is_file(), res.get("look_error"))


if __name__ == "__main__":
    unittest.main()
