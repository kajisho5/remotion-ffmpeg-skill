"""Integration tests with real media. Need ffmpeg and ffmpeg-skill (FFMPEG_SKILL_DIR or installed);
skipped otherwise. Set RFS_PROJECT to an installed Remotion project (init.py --install) to also run
real renders -- slow (a Chromium render per composition), so off by default."""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "tests"))
import _common  # noqa: E402
import _contract  # noqa: E402
import analyze  # noqa: E402
from tmp_dirs import tmp_dir  # noqa: E402

HAVE = shutil.which("ffmpeg") and _common.find_ffmpeg_skill() is not None
PROJECT = os.environ.get("RFS_PROJECT")
TRANSCRIPT = ROOT / "tests" / "fixtures" / "transcript.json"
NEEDS_KINETIC = {"KineticType"}   # draws only a schedule analyze.py --kinetic wrote from words or measured beats   # transcription-skill/transcript/0.1, fictional

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
        cls.tmp = tmp_dir(cls, "rfs-")
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

    EMPHASIS = ["講演", {"text": "first", "style": "box"}, {"text": "Thanks", "at": 7.4, "style": "color"}]

    def emphasis_timeline(self, name, entries):
        efile = self.tmp / f"{name}.emphasis.json"
        efile.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        tl = self.tmp / f"{name}.timeline.json"
        code, res = script("analyze", self.src, "--words", TRANSCRIPT, "--emphasis", efile, "-o", tl, "--no-scenes")
        return code, res, tl

    def test_emphasis_words_at_their_word_times(self):
        code, res, tl = self.emphasis_timeline("emph", self.EMPHASIS)
        self.assertEqual(code, 0, res)
        self.assertEqual(_contract.missing_output_keys("analyze", res), [])
        self.assertEqual(res["summary"]["emphasis"], 3)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual(_common.validate_timeline(t), [])
        self.assertEqual([(e["start"], e["end"], e["text"], e["cue"]) for e in t["emphasis"]],
                         [(0.86, 1.4, "講演", 0), (5.9, 6.3, "first", 2), (7.2, 7.6, "Thanks", 3)])
        self.assertEqual(t["captions"], TRANSCRIPT_CUES)     # the captions themselves are untouched
        proj = self.tmp / "proj_emph"
        script("init", proj)
        code, res = script("render", "--project", proj, "--comp", "Emphasis", "--timeline", tl,
                           "-o", self.tmp / "emph.mp4", "--dry-run")
        self.assertEqual(code, 0, res)
        self.assertEqual(res["expected_frames"], 240)

    def test_emphasis_refuses_a_word_not_in_the_cue(self):
        code, res, _ = self.emphasis_timeline("emph_bad", [{"text": "first", "at": 7.4}])
        self.assertEqual((code, res.get("kind")), (2, "input"), res)
        self.assertIn("not a whole word of the cue at 7.4 s", res["error"])
        code, res = script("analyze", self.src, "--emphasis-auto", "numbers", "-o", self.tmp / "emph_nw.json")
        self.assertNotEqual(code, 0)
        self.assertEqual(res["kind"], "input")
        self.assertIn("need --words", res["error"])
        code, res = script("analyze", self.src, "--words", TRANSCRIPT, "--emphasis-auto", ",", "-o", self.tmp / "e.json")
        self.assertEqual((code, res.get("kind")), (2, "input"), res)

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_emphasis_shows_each_word_at_its_time(self):
        code, res, tl = self.emphasis_timeline("emph_real", self.EMPHASIS)
        self.assertEqual(code, 0, res)
        plain = self.tmp / "emph_plain.timeline.json"
        t = json.loads(tl.read_text(encoding="utf-8"))
        # the reference: the same words marked up, but never spoken (their time after the end), so the only
        # difference between the two is when the emphasis shows -- text shaping around the span is the same
        never = [{**e, "start": 1000.0, "end": 1001.0} for e in t["emphasis"]]
        plain.write_text(json.dumps({**t, "emphasis": never}, ensure_ascii=False), encoding="utf-8")
        # the frame before each word starts and the frame it starts on (講演 0.86 s -> frame 26, first 5.9 s ->
        # frame 177); Thanks opens its cue, so the frame before shows no cue and a frame inside the word is used
        frames = {"講演": (25, 26), "first": (176, 177), "Thanks": (215, 222)}
        shots = {}
        for name, timeline in (("emph", tl), ("plain", plain)):
            out_dir = self.tmp / f"stills_{name}"
            args = [a for f in sorted(x for p in frames.values() for x in p) for a in ("--frame", f)]
            code, res = script("still", "--project", PROJECT, "--comp", "Emphasis", "--timeline", timeline,
                               "--out-dir", out_dir, *args)
            self.assertEqual(code, 0, res)
            shots[name] = dict(zip(res["frames"], res["outputs"]))
        for word, (before, at) in frames.items():
            with self.subTest(word=word):
                self.assertLess(changed_pixels(shots["emph"][before], shots["plain"][before]), 10,
                                f"{word} is emphasised before it is spoken")
                self.assertGreater(changed_pixels(shots["emph"][at], shots["plain"][at]), 400,
                                   f"{word} is not emphasised when it is spoken")
        proc = subprocess.run([sys.executable, str(SCRIPTS / "render.py"), "--project", PROJECT, "--comp", "Emphasis",
                               "--timeline", str(tl), "-o", str(self.tmp / "real_emphasis.mp4"), "--fast", "--json"],
                              capture_output=True, text=True)
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

    def test_deliver_keeps_a_deliberate_still_picture(self):
        # ffmpeg-skill 4.0's templates also run check.py --content, whose `frozen` row fails a picture held on purpose
        # (a title card); deliver keeps the platform rows only on every version (docs/design-decisions.md)
        still = self.tmp / "still.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x1E6F8E:s=1280x720:r=30:d=4",
                        "-f", "lavfi", "-i", "sine=f=440:d=4", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", str(still)], check=True)
        out = self.tmp / "still_youtube.mp4"
        code, res = script("deliver", still, "--platform", "youtube", "-o", out)
        self.assertEqual(code, 0, res)
        self.assertTrue(res["verified"], res)
        self.assertTrue(out.is_file())
        self.assertNotIn("frozen", [c["check"] for c in res["checks"]])

    def test_deliver_with_british_spelling_kit(self):
        brand = Path(__file__).parent / "fixtures" / "colours-british-spelling.json"
        original = brand.read_bytes()
        code, result = script("deliver", self.src, "--platform", "youtube", "--brand", brand,
                              "-o", self.tmp / "kit_youtube.mp4")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["verified"], result)
        self.assertEqual(brand.read_bytes(), original)

    def test_still_and_render_share_the_projected_delivery_look(self):
        from deliver import kit_projection
        brand = Path(__file__).parent / "fixtures" / "colours-british-spelling.json"
        native = self.tmp / "projected-brand.json"
        native.write_text(json.dumps(kit_projection(brand)), encoding="utf-8")
        project = self.tmp / "brand-project"
        self.assertEqual(script("init", project)[0], 0)
        common = ["--project", project, "--timeline", self.tl, "--comp", "Captioned", "--dry-run"]
        code, rendered = script("render", *common, "--brand", native, "-o", self.tmp / "brand-video.mp4")
        self.assertEqual(code, 0, rendered)
        code, still = script("still", *common, "--brand", brand, "--frame", "0")
        self.assertEqual(code, 0, still)
        self.assertIn(Path(rendered["props"]).name, still["commands"][0])

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
                if comp in NEEDS_KINETIC:   # no --kinetic schedule in this timeline: refused (class KineticType renders it)
                    self.assertEqual((code, res.get("kind")), (2, "input"), res)
                    continue
                self.assertEqual(code, 0, res)
                self.assertTrue(res["verified"])
                self.assertEqual(_contract.missing_output_keys("render", res), [])
                self.assertTrue(res["look"] and Path(res["look"]).is_file(), res.get("look_error"))


def ffmpeg_skill_at_least(*want: int) -> bool:
    v = _common.ffmpeg_skill_version(_common.find_ffmpeg_skill()) if _common.find_ffmpeg_skill() else None
    try:
        return tuple(int(x) for x in (v or "0").split(".")[:3]) >= want
    except ValueError:
        return False


@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")
class Blank(unittest.TestCase):
    """analyze.py / pipeline.py --blank: a timeline with no footage, the music measured as a source's audio is."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp_dir(cls, "rfs-blank-")
        cls.music = cls.tmp / "bgm.wav"   # 15 s of a decaying 80 Hz hit every 0.5 s (120 BPM), fictional test audio
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc='0.8*sin(2*PI*80*t)*exp(-mod(t\\,0.5)*12)':s=44100:d=15", str(cls.music)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_music_is_never_overwritten(self):
        code, res = script("analyze", "--blank", "2", "--music", self.music, "-o", self.music, "--overwrite")
        self.assertEqual((code, res.get("kind")), (2, "input"), res)
        self.assertIn("never overwritten", res["error"])
        code, res = script("pipeline", self.music, "--music", self.music, "--project", self.tmp, "--comp", "Captioned")
        self.assertEqual((code, res.get("kind")), (2, "input"), res)
        self.assertIn("needs --blank", res["error"])

    def test_blank_without_music(self):
        tl = self.tmp / "silent.timeline.json"
        code, res = script("analyze", "--blank", "4", "--size", "640x360", "--fps", "25", "-o", tl)
        self.assertEqual(code, 0, res)
        self.assertEqual(_contract.missing_output_keys("analyze", res), [])
        self.assertEqual(res["commands"], [])
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual(_common.validate_timeline(t), [])
        self.assertEqual({k: t["source"][k] for k in ("duration", "fps", "width", "height", "has_video", "has_audio",
                                                      "blank")},
                         {"duration": 4.0, "fps": 25.0, "width": 640, "height": 360, "has_video": False,
                          "has_audio": False, "blank": True})
        self.assertEqual(_common.expected_frames("Captioned", t), 100)

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_every_composition_on_a_blank(self):
        tl = self.tmp / "tiny.timeline.json"
        code, res = script("analyze", "--blank", "1", "--size", "320x180", "-o", tl)
        self.assertEqual(code, 0, res)
        # KineticType needs a --kinetic schedule, Visualizer audio: a blank without music has neither (both refused)
        for comp in (c for c in _common.BUILTIN_COMPOSITIONS if c not in NEEDS_KINETIC | {"Visualizer"}):
            with self.subTest(comp=comp):
                code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", tl,
                                   "-o", self.tmp / f"tiny_{comp}.mp4", "--no-look")
                self.assertEqual(code, 0, res)
                self.assertTrue(res["verified"])

    @unittest.skipUnless(ffmpeg_skill_at_least(3, 2, 0), "ffmpeg-skill measures audio-only files from 3.2.0")
    def test_music_is_measured_for_peaks_and_beats(self):
        tl = self.tmp / "bgm.timeline.json"
        code, res = script("analyze", "--blank", "12", "--size", "1080x1920", "--music", self.music, "--beats", "-o", tl)
        self.assertEqual(code, 0, res)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual(_common.validate_timeline(t), [])
        self.assertTrue(t["source"]["has_audio"])
        self.assertEqual(Path(t["source"]["path"]), self.music.resolve())
        self.assertTrue(t["beats"]["usable"], t["beats"])
        self.assertAlmostEqual(t["beats"]["tempo_bpm"], 120, delta=1)
        self.assertTrue(all(b < 12 for b in t["beats"]["times"]))           # cut at the blank's end
        self.assertTrue(any("cut at the blank's end" in w for w in t["warnings"]))
        self.assertEqual(t["blank"]["music"]["duration"], 15.0)

    @unittest.skipUnless(PROJECT and ffmpeg_skill_at_least(3, 2, 0),
                         "needs RFS_PROJECT and ffmpeg-skill 3.2.0 or later")
    def test_real_pipeline_blank_with_music(self):
        out = self.tmp / "out"
        code, res = script("pipeline", "--blank", "15", "--size", "1080x1920", "--music", self.music,
                           "--project", PROJECT, "--comp", "PeakPulse", "--out-dir", out)
        self.assertEqual(code, 0, res)
        self.assertTrue(res["verified"])
        probe = _common.ffskill("probe", [res["render"]])
        self.assertEqual(probe["video"]["nb_frames"], 450)                   # 15.0 s at 30 fps
        self.assertEqual((probe["video"]["width"], probe["video"]["height"]), (1080, 1920))
        self.assertTrue(probe.get("audio"))


@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")
class KineticType(unittest.TestCase):
    """KineticType on a 120 BPM fixture: each word (or CJK character) starts on a measured beat, to the frame."""

    LYRICS = ("1\n00:00:00,400 --> 00:00:02,600\nNeon lights over town\n\n"
              "2\n00:00:03,000 --> 00:00:05,600\n今日もいい天気\n")     # fictional lyric lines

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp_dir(cls, "rfs-kin-")
        cls.music = cls.tmp / "beat120.wav"   # a decaying 80 Hz hit every 0.5 s: 120 BPM, beats on 0.5 s multiples
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc='0.8*sin(2*PI*80*t)*exp(-mod(t\\,0.5)*12)':s=44100:d=8", str(cls.music)], check=True)
        (cls.tmp / "lyrics.srt").write_text(cls.LYRICS, encoding="utf-8")
        cls.tl = cls.tmp / "kin.timeline.json"
        cls.code, cls.res = script("analyze", "--blank", "8", "--size", "640x360", "--music", cls.music, "--beats",
                                   "--captions", cls.tmp / "lyrics.srt", "--kinetic", "beats", "-o", cls.tl)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        if not ffmpeg_skill_at_least(3, 2, 0):
            self.skipTest("ffmpeg-skill measures audio-only files from 3.2.0")
        self.assertEqual(self.code, 0, self.res)
        self.t = json.loads(self.tl.read_text(encoding="utf-8"))

    def test_every_word_is_on_a_beat(self):
        self.assertEqual(_common.validate_timeline(self.t), [])
        self.assertEqual(self.res["summary"]["kinetic"], 11)
        fps = self.t["source"]["fps"]
        beats = self.t["beats"]["times"]
        units = [u for ln in self.t["kinetic"]["lines"] for u in ln["units"]]
        self.assertEqual([u["text"] for u in units], ["Neon", "lights", "over", "town", "今", "日", "も", "い", "い",
                                                      "天", "気"])
        for u in units:
            nearest = min(beats, key=lambda b: abs(b - u["start"]))
            self.assertLessEqual(abs(u["start"] - nearest) * fps, 1.0, u)          # on a measured beat
            self.assertLessEqual(abs(u["start"] - round(u["start"] * 2) / 2) * fps, 1.0, u)   # the true 120 BPM grid
        plain = self.tmp / "plain.timeline.json"
        plain.write_text(json.dumps({**self.t, "kinetic": None}), encoding="utf-8")
        proj = self.tmp / "proj"
        script("init", proj)
        code, res = script("render", "--project", proj, "--comp", "KineticType", "--timeline", plain, "--dry-run")
        self.assertEqual((code, res.get("kind")), (2, "input"), res)
        self.assertIn("--kinetic", res["error"])

    def stills(self, timeline: Path, frames, name: str):
        code, res = script("still", "--project", PROJECT, "--comp", "KineticType", "--timeline", timeline,
                           *[x for f in frames for x in ("--frame", f)], "--out-dir", self.tmp / name)
        self.assertEqual(code, 0, res)
        return res, [sha256(Path(p)) for p in res["outputs"]]

    def unit_starts_on_its_frame(self, li: int, ui: int):
        """The render with unit (li, ui) never shown matches the real one on the frame before its start and
        differs on its start frame: the unit enters exactly on round(start * fps)."""
        fps = self.t["source"]["fps"]
        start = _common.sec_to_frames(self.t["kinetic"]["lines"][li]["units"][ui]["start"], fps)
        hidden = json.loads(json.dumps(self.t))
        hidden["kinetic"]["lines"][li]["units"][ui]["start"] = 1000.0
        alt = self.tmp / f"hide_{li}_{ui}.timeline.json"
        alt.write_text(json.dumps(hidden, ensure_ascii=False), encoding="utf-8")
        res, real = self.stills(self.tl, [start - 1, start], f"real_{li}_{ui}")
        _, other = self.stills(alt, [start - 1, start], f"hide_{li}_{ui}")
        self.assertEqual(real[0], other[0], f"unit {li}.{ui} shows before frame {start}")
        self.assertNotEqual(real[1], other[1], f"unit {li}.{ui} does not show on frame {start}")
        return res

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_each_word_enters_on_its_beat_frame(self):
        for ui in range(4):
            with self.subTest(word=ui):
                self.unit_starts_on_its_frame(0, ui)

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_japanese_line_per_character_with_the_cjk_font(self):
        res = self.unit_starts_on_its_frame(1, 2)
        if not res.get("font"):
            self.skipTest("no CJK font found on this machine")
        self.assertIn("for ja captions", res["font"])
        self.unit_starts_on_its_frame(1, 3)
        code, res = script("render", "--project", PROJECT, "--comp", "KineticType", "--timeline", self.tl,
                           "-o", self.tmp / "kin.mp4", "--fast")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["verified"])


QC_SKILL_DIR = os.environ.get("QC_SKILL_DIR")


def rgb_frames(path: Path, which):
    """The given frames of a video as 8-bit RGB byte strings (decoded by ffmpeg, at the stream's own size)."""
    probe = _common.ffskill("probe", [str(path)])
    w, h = probe["video"]["width"], probe["video"]["height"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    size = w * h * 3
    frames = [raw[i:i + size] for i in range(0, len(raw), size)]
    return [frames[i] for i in which], len(frames)


def mean_abs(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")
class Visualizer(unittest.TestCase):
    """The Visualizer draws the audio at its frame, and its --loop length is a whole number of measured bars."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp_dir(cls, "rfs-vis-")
        cls.tone = cls.tmp / "tone.wav"   # silence, then a 440 Hz test tone from exactly 1.000 s
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc='0.6*sin(2*PI*440*t)*gte(t\\,1)':s=44100:d=3", str(cls.tone)], check=True)
        cls.beat = cls.tmp / "beat120.wav"   # 120 BPM: an 80 Hz hit every 0.5 s
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                        "aevalsrc='0.8*sin(2*PI*80*t)*exp(-mod(t\\,0.5)*12)':s=44100:d=8", str(cls.beat)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def timeline(self, name, *args):
        tl = self.tmp / f"{name}.timeline.json"
        code, res = script("analyze", "--blank", *args, "--size", "640x360", "-o", tl)
        self.assertEqual(code, 0, res)
        return tl

    def test_loop_needs_measured_bars(self):
        if not ffmpeg_skill_at_least(3, 2, 0):
            self.skipTest("ffmpeg-skill measures audio-only files from 3.2.0")
        tl = self.timeline("beat", "8", "--music", self.beat, "--beats")
        t = json.loads(tl.read_text(encoding="utf-8"))
        # 16 beats 0.5 s apart: 3 whole bars of 4 with a beat on each side for the seam; seam halfway between beats
        self.assertEqual(_common.loop_range(t, {"loopBars": 0}), (8, 180, 3))
        self.assertEqual(_common.expected_frames("Visualizer", t, {"loopBars": 2}), 120)
        self.assertEqual(_common.expected_frames("Visualizer", t), 240)
        opts = self.tmp / "toomany.json"
        opts.write_text(json.dumps({"loopBars": 9}), encoding="utf-8")
        proj = self.tmp / "proj"
        script("init", proj)
        code, res = script("render", "--project", proj, "--comp", "Visualizer", "--timeline", tl, "--options", opts,
                           "--dry-run")
        self.assertEqual((code, res.get("kind")), (2, "input"), res)
        self.assertIn("hold 3 whole bar", res["error"])
        silent = self.timeline("silent", "2")
        code, res = script("render", "--project", proj, "--comp", "Visualizer", "--timeline", silent, "--dry-run")
        self.assertEqual((code, res.get("kind")), (2, "input"), res)

    @unittest.skipUnless(PROJECT and ffmpeg_skill_at_least(3, 2, 0), "needs RFS_PROJECT and ffmpeg-skill 3.2.0+")
    def test_real_bars_react_to_a_tone_on_its_frame(self):
        tl = self.timeline("tone", "3", "--music", self.tone, "--no-silence")
        code, res = script("still", "--project", PROJECT, "--comp", "Visualizer", "--timeline", tl,
                           "--frame", "29", "--frame", "30", "--out-dir", self.tmp / "tone")
        self.assertEqual(code, 0, res)
        bars = []
        for png in res["outputs"]:   # the bars' half of the frame (the ring sits above it), mean of its grey levels
            raw = subprocess.run(["ffmpeg", "-v", "error", "-i", png, "-vf", "crop=640:150:0:210,format=gray",
                                  "-f", "rawvideo", "-"], capture_output=True, check=True).stdout
            bars.append(sum(raw) / len(raw))
        self.assertLess(bars[0], 5.0, bars)          # frame 29 (0.967 s): no tone yet, flat 2 px bars
        self.assertGreater(bars[1], 30.0, bars)      # frame 30 (1.000 s): the tone starts, the bars rise

    @unittest.skipUnless(PROJECT and ffmpeg_skill_at_least(3, 2, 0), "needs RFS_PROJECT and ffmpeg-skill 3.2.0+")
    def test_real_loop_seam(self):
        tl = self.timeline("loop", "8", "--music", self.beat, "--beats")
        opts = self.tmp / "loop.json"
        opts.write_text(json.dumps({"loopBars": 0}), encoding="utf-8")
        out = self.tmp / "loop.mp4"
        code, res = script("render", "--project", PROJECT, "--comp", "Visualizer", "--timeline", tl, "--options", opts,
                           "-o", out, "--no-look")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["verified"])
        # qc-skill's measure (video.loop_seam, ADR-026): the last -> first step against the median step inside the
        # 4 frames on each side; one frame short (a loop that is not whole bars) jumps
        n = 180
        (first, last), total = rgb_frames(out, [0, n - 1])
        self.assertEqual(total, n)
        inside_idx = list(range(0, 5)) + list(range(n - 5, n))
        fr, _ = rgb_frames(out, inside_idx)
        steps = sorted([mean_abs(fr[i], fr[i + 1]) for i in range(4)] + [mean_abs(fr[i], fr[i + 1]) for i in range(5, 9)])
        reference = (steps[3] + steps[4]) / 2
        ratio = mean_abs(last, first) / reference
        self.assertLessEqual(ratio, 1.3, (ratio, reference))
        short_last, _ = rgb_frames(out, [n - 2])
        self.assertGreater(mean_abs(short_last[0], first) / reference, 1.3)
        if QC_SKILL_DIR:
            req = self.tmp / "qc.json"
            req.write_text(json.dumps({"operation": "check", "kind": "video", "input": str(out),
                                       "rules": {"video": {"loop_seam": {"max_seam_ratio": 1.3}}}}), encoding="utf-8")
            proc = subprocess.run([sys.executable, "-m", "qc_skill.cli", "run", str(req), "--json", "--no-cache",
                                   "--workspace", str(self.tmp)], capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": str(Path(QC_SKILL_DIR) / "src")})
            check = next(c for c in json.loads(proc.stdout)["report"]["checks"]
                         if c["check_id"] == "video.loop_seam_within_limit")
            self.assertEqual(check["status"], "PASS", check)


@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")
class NtscRate(unittest.TestCase):
    """velisa/timebase@1 (docs/adr/0004): a 30000/1001 source is drawn at 30000/1001, not at the probe's 29.97."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp_dir(cls, "rfs-ntsc-")
        cls.src = cls.tmp / "ntsc.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30000/1001:duration=3",
                        "-f", "lavfi", "-i", "sine=f=440:d=3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                        "-shortest", str(cls.src)], check=True)
        cls.tl = cls.tmp / "ntsc.timeline.json"
        code, res = script("analyze", cls.src, "-o", cls.tl)
        assert code == 0, res
        cls.timeline = json.loads(cls.tl.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_timeline_rate_is_the_exact_ntsc_rate(self):
        self.assertEqual(self.timeline["source"]["fps"], 30000 / 1001)
        self.assertEqual(_common.expected_frames("Captioned", self.timeline),
                         _common.sec_to_frames(self.timeline["source"]["duration"], 30000 / 1001))

    @unittest.skipUnless(PROJECT, "set RFS_PROJECT to an installed project for real renders")
    def test_real_render_carries_30000_1001(self):
        out = self.tmp / "ntsc-out.mp4"
        code, res = script("render", "--project", PROJECT, "--comp", "Captioned", "--timeline", self.tl, "-o", out, "--fast")
        self.assertEqual(code, 0, res)
        self.assertTrue(res["verified"])
        rate = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                               "-of", "default=nw=1:nk=1", str(out)], capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(rate, "30000/1001")


def hdr_tags(transfer: str):
    """BT.2020 + PQ / HLG on the frames, the stream and in the H.264 VUI itself (FFmpeg 7+ no longer lets
    the output options alone override the untagged frames lavfi makes)."""
    vui = {"smpte2084": 16, "arib-std-b67": 18}[transfer]
    return (f"setparams=color_primaries=bt2020:color_trc={transfer}:colorspace=bt2020nc",
            ["-color_primaries", "bt2020", "-color_trc", transfer, "-colorspace", "bt2020nc",
             "-bsf:v", f"h264_metadata=colour_primaries=9:transfer_characteristics={vui}:matrix_coefficients=9"])


def make_vfr(d: Path, name: str = "vfr.mp4", transfer: str = "") -> Path:
    """4 s at a 30 fps base rate with every 8th-10th frame of each ten dropped: variable frame rate
    (10-bit and tagged HDR with `transfer`)."""
    out = d / name
    vf, tags = hdr_tags(transfer) if transfer else ("", [])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=4",
                    "-f", "lavfi", "-i", "sine=f=440:d=4",
                    "-vf", "select='lt(mod(n\\,10)\\,7)'" + (f",{vf}" if vf else ""),
                    "-fps_mode", "vfr", "-c:v", "libx264", "-pix_fmt", "yuv420p10le" if transfer else "yuv420p",
                    *tags, "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def make_hdr(d: Path, transfer: str, name: str) -> Path:
    """3 s, 30 fps, 10-bit, tagged BT.2020 with a PQ (smpte2084) or HLG (arib-std-b67) transfer."""
    out = d / name
    vf, tags = hdr_tags(transfer)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=3",
                    "-f", "lavfi", "-i", "sine=f=440:d=3", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p10le",
                    *tags, "-c:a", "aac", "-shortest", str(out)], check=True)
    return out


def frame_intervals(path: Path):
    """Every interval between consecutive video frames, from ffprobe's packet timestamps (test-side check)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True).stdout
    pts = sorted(float(x.strip().rstrip(",")) for x in out.split() if x.strip().rstrip(",") not in ("", "N/A"))
    return [b - a for a, b in zip(pts, pts[1:])]


def colour_tags(path: Path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=color_transfer,color_primaries,color_space", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def changed_pixels(a, b, level: int = 60) -> int:
    """Pixels where two same-size images differ by more than `level` in any channel (test-side check)."""
    def rgb(p):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              capture_output=True, check=True).stdout
    x, y = rgb(a), rgb(b)
    assert len(x) == len(y), "images differ in size"
    return sum(1 for i in range(0, len(x), 3) if max(abs(x[i] - y[i]), abs(x[i + 1] - y[i + 1]),
                                                     abs(x[i + 2] - y[i + 2])) > level)


def sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(HAVE, "needs ffmpeg and ffmpeg-skill")
class Conform(unittest.TestCase):
    """A VFR or HDR source is never only warned about: it is refused, or with --conform measured and
    drawn on a CFR / SDR BT.709 copy that ffmpeg-skill made, with the original untouched."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp_dir(cls, "rfs-conform-")
        cls.vfr = make_vfr(cls.tmp)
        cls.pq = make_hdr(cls.tmp, "smpte2084", "pq.mp4")
        cls.hlg = make_hdr(cls.tmp, "arib-std-b67", "hlg.mp4")
        cls.hlg_vfr = make_vfr(cls.tmp, "hlg_vfr.mp4", "arib-std-b67")
        cls.hashes = {p: sha256(p) for p in (cls.vfr, cls.pq, cls.hlg, cls.hlg_vfr)}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def tearDown(self):
        for p, h in self.hashes.items():
            self.assertEqual(sha256(p), h, f"{p.name} was modified")

    def test_fixtures_are_what_they_claim(self):
        for path, want in ((self.vfr, ["vfr"]), (self.pq, ["hdr"]), (self.hlg, ["hdr"]), (self.hlg_vfr, ["vfr", "hdr"])):
            pr = _common.ffskill("probe", [str(path)])
            self.assertEqual(analyze.conform_needs(pr), want, path.name)
        self.assertGreater(max(frame_intervals(self.vfr)) - min(frame_intervals(self.vfr)), 0.03)

    def test_refused_without_conform(self):
        d = self.tmp / "refused"
        d.mkdir()
        for orig, need in ((self.vfr, "vfr"), (self.pq, "hdr"), (self.hlg, "hdr")):
            path = Path(shutil.copyfile(orig, d / orig.name))
            for dry in ([], ["--dry-run"]):
                with self.subTest(path.name, dry=bool(dry)):
                    out = self.tmp / f"refused_{path.stem}.timeline.json"
                    code, res = script("analyze", path, "-o", out, *dry)
                    self.assertEqual(code, 2, res)
                    self.assertEqual(res["kind"], "input")
                    self.assertIn("--conform", res["error"])
                    self.assertIn(need, res["conform_needed"])
                    self.assertFalse(out.exists())
                    self.assertEqual(sorted(f.name for f in d.iterdir()), sorted(f.name for f in d.glob("*.mp4")))
                    self.assertFalse((d / f"{path.stem}_conformed.mp4").exists())

    def assert_conformed(self, src: Path, reasons, steps):
        tl = self.tmp / f"{src.stem}.timeline.json"
        code, res = script("analyze", src, "--conform", "-o", tl, "--no-scenes")
        self.assertEqual(code, 0, res)
        self.assertEqual(_contract.missing_output_keys("analyze", res), [])
        self.assertEqual(res["summary"]["conformed"], reasons)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertEqual(_common.validate_timeline(t), [])
        copy = Path(t["source"]["path"])
        self.assertEqual(copy, (self.tmp / f"{src.stem}_conformed.mp4").resolve())
        c = t["conform"]
        self.assertEqual(c["reasons"], reasons)
        self.assertEqual(c["output"], str(copy))
        self.assertEqual(c["original"]["path"], str(src.resolve()))
        self.assertEqual(c["original"]["fingerprint"], "sha256:" + self.hashes[src])
        self.assertEqual([(st["reason"], st["tool"]) for st in c["steps"]], steps)
        self.assertTrue(all(st["command"] in res["commands"] for st in c["steps"]))
        self.assertFalse([w for w in t["warnings"] if "frame rate" in w or "HDR" in w], t["warnings"])
        self.assertFalse(list(self.tmp.glob(".rfs-conform-*")))   # the intermediate between two steps is gone
        # Measured: ffmpeg-skill's probe of the copy, and the frame timestamps and colour tags themselves.
        pr = _common.ffskill("probe", [str(copy)])
        self.assertEqual(analyze.conform_needs(pr), [])
        self.assertEqual(t["source"]["fps"], 30.0)
        intervals = frame_intervals(copy)
        self.assertTrue(intervals and all(abs(d - 1 / 30) < 1e-3 for d in intervals), (min(intervals), max(intervals)))
        self.assertAlmostEqual(t["source"]["duration"], c["original"]["duration"], delta=0.1)
        return t, copy

    def test_vfr_becomes_cfr(self):
        t, copy = self.assert_conformed(self.vfr, ["vfr"], [("vfr", "ffmpeg-skill fit.py")])
        self.assertEqual(t["conform"]["original"]["r_frame_rate"], "30/1")
        self.assertTrue(t["conform"]["original"]["variable_frame_rate_suspected"])

    def test_pq_and_hlg_become_sdr_bt709(self):
        for src in (self.pq, self.hlg):
            with self.subTest(src.name):
                t, copy = self.assert_conformed(src, ["hdr"], [("hdr", "ffmpeg-skill color.py")])
                self.assertEqual(colour_tags(copy), {"color_space": "bt709", "color_transfer": "bt709",
                                                     "color_primaries": "bt709"})
                self.assertEqual(t["conform"]["measured"]["color_transfer"], "bt709")
                self.assertIn(t["conform"]["original"]["color_transfer"], ("smpte2084", "arib-std-b67"))
                self.assertTrue(t["conform"]["steps"][0]["notes"])   # ffmpeg-skill's own "tone-mapped ..." note

    def test_vfr_hdr_is_conformed_in_order(self):
        t, copy = self.assert_conformed(self.hlg_vfr, ["vfr", "hdr"],
                                        [("vfr", "ffmpeg-skill fit.py"), ("hdr", "ffmpeg-skill color.py")])
        self.assertEqual(colour_tags(copy)["color_transfer"], "bt709")

    def test_dry_run_plans_the_conform(self):
        out = self.tmp / "dry_conform.timeline.json"
        code, res = script("analyze", self.pq, "--conform", "--conformed", self.tmp / "dry_copy.mp4", "-o", out,
                           "--dry-run")
        self.assertEqual(code, 0, res)
        self.assertTrue(any("color.py" in c and "--to-sdr" in c for c in res["commands"]), res["commands"])
        self.assertTrue(any("scenes.py" in c and "dry_copy.mp4" in c for c in res["commands"]))
        self.assertFalse(out.exists())
        self.assertFalse((self.tmp / "dry_copy.mp4").exists())

    def test_conform_flags_need_conform_and_never_overwrite_the_original(self):
        code, res = script("analyze", self.vfr, "--conform-fps", "25", "-o", self.tmp / "x.json")
        self.assertEqual((code, res["kind"]), (2, "input"))
        code, res = script("analyze", self.vfr, "--conform", "--conformed", self.vfr, "-o", self.tmp / "y.json",
                           "--overwrite")
        self.assertEqual((code, res["kind"]), (2, "input"), res)

    def test_pip_camera_is_conformed_too(self):
        src = make_fixture(self.tmp)
        cam = Path(shutil.copyfile(self.hlg, self.tmp / "camera_hlg.mp4"))
        code, res = script("analyze", src, "--pip", cam, "--pip-offset", "0.5", "-o", self.tmp / "p0.json",
                           "--no-scenes", "--no-silence")
        self.assertEqual((code, res["kind"]), (2, "input"), res)
        self.assertIn("--pip camera", res["error"])
        tl = self.tmp / "pip.timeline.json"
        code, res = script("analyze", src, "--pip", cam, "--pip-offset", "0.5", "--conform", "-o", tl,
                           "--no-scenes", "--no-silence", "--overwrite")
        self.assertEqual(code, 0, res)
        t = json.loads(tl.read_text(encoding="utf-8"))
        self.assertIsNone(t["conform"])                      # the SDR CFR source itself is used as it is
        self.assertEqual(res["summary"]["conformed"], [])
        self.assertEqual(t["pip"]["conform"]["reasons"], ["hdr"])
        self.assertEqual(t["pip"]["path"], t["pip"]["conform"]["output"])
        self.assertEqual(Path(t["pip"]["path"]).name, "camera_hlg_conformed.mp4")
        self.assertEqual(colour_tags(Path(t["pip"]["path"]))["color_transfer"], "bt709")

    def test_render_draws_on_the_conformed_copy(self):
        tl = self.tmp / "render_src.timeline.json"
        code, res = script("analyze", self.pq, "--conform", "--conformed", self.tmp / "pq_render.mp4", "-o", tl,
                           "--no-scenes")
        self.assertEqual(code, 0, res)
        t = json.loads(tl.read_text(encoding="utf-8"))
        proj = self.tmp / "proj"
        script("init", proj)
        # --overlay plans the composite over the timeline's source: the conformed copy, not the original
        code, res = script("render", "--project", proj, "--comp", "Captioned", "--timeline", tl,
                           "-o", self.tmp / "pq_captioned.mp4", "--overlay", "--dry-run")
        self.assertEqual(code, 0, res)
        overlay = next(c for c in res["commands"] if "overlay.py" in c)
        self.assertIn("pq_render.mp4", overlay)
        self.assertNotIn(str(self.pq), overlay)
        self.assertEqual(res["expected_frames"], _common.expected_frames("Captioned", t))
        if PROJECT:
            out = self.tmp / "pq_captioned_real.mp4"
            code, res = script("render", "--project", PROJECT, "--comp", "Captioned", "--timeline", tl,
                               "-o", out, "--fast", "--no-look")
            self.assertEqual(code, 0, res)
            self.assertTrue(res["verified"])
            # Remotion tags its own transfer (sRGB); what matters is that no HDR signal reached the render
            self.assertNotIn(colour_tags(out).get("color_transfer"), ("smpte2084", "arib-std-b67"))
            self.assertNotEqual(colour_tags(out).get("color_primaries"), "bt2020")
            self.assertTrue(list((Path(PROJECT) / "public" / "media").glob("*_pq_render.mp4")))


def framemd5(path: Path):
    """md5 of every decoded video frame (ffmpeg framemd5), test-side."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "framemd5", "-"],
                         capture_output=True, text=True, check=True).stdout
    return [ln.rsplit(",", 1)[1].strip() for ln in out.splitlines() if ln.strip() and not ln.startswith("#")]


def audio_md5(path: Path) -> str:
    """md5 of the decoded audio, test-side."""
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:a:0", "-f", "md5", "-"],
                          capture_output=True, text=True, check=True).stdout.strip()


@unittest.skipUnless(HAVE and PROJECT, "needs ffmpeg, ffmpeg-skill and RFS_PROJECT (an installed project)")
class Determinism(unittest.TestCase):
    """The contract's repeatability claim (docs/adr/0001-render-determinism.md), checked on this machine: two
    compositions rendered twice -- the second time with one browser tab -- and two stills, at the level the
    contract states. A composition listed as not reproducible would be skipped here, by name."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tmp_dir(cls, "rfs-det-")
        cls.src = make_fixture(cls.tmp)
        (cls.tmp / "cues.srt").write_text(SRT, encoding="utf-8")
        cls.tl = cls.tmp / "fixture.timeline.json"
        code, res = script("analyze", cls.src, "--captions", cls.tmp / "cues.srt", "-o", cls.tl)
        assert code == 0, res
        cls.c = _contract.build()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def hint(self, tool: str) -> str:
        return next(t for t in self.c["tools"] if t["name"] == tool)["idempotency_hint"]

    def test_render_twice_matches_at_the_stated_level(self):
        level = self.hint("render")
        self.assertIn(level, ("bit_exact", "content_equivalent"))
        for comp in ("Captioned", "PeakPulse"):
            if comp in self.c["determinism"]["not_reproducible_compositions"]:
                continue
            with self.subTest(comp=comp):
                outs = []
                for i, extra in enumerate(([], ["--concurrency", "1"])):
                    out = self.tmp / f"det_{comp}_{i}.mp4"
                    code, res = script("render", "--project", PROJECT, "--comp", comp, "--timeline", self.tl,
                                       "-o", out, "--fast", "--no-look", *extra)
                    self.assertEqual(code, 0, res)
                    self.assertTrue(res["verified"])
                    outs.append(out)
                a, b = (framemd5(o) for o in outs)
                self.assertEqual(len(a), len(b))
                differ = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
                self.assertEqual(differ, [], f"{comp}: frames differ between two renders")
                self.assertEqual(audio_md5(outs[0]), audio_md5(outs[1]), f"{comp}: audio differs")
                if level == "bit_exact":
                    self.assertEqual(sha256(outs[0]), sha256(outs[1]), f"{comp}: files differ in bytes")

    def test_still_twice_is_byte_identical(self):
        self.assertEqual(self.hint("still"), "bit_exact")
        shots = []
        for i in range(2):
            code, res = script("still", "--project", PROJECT, "--comp", "Captioned", "--timeline", self.tl,
                               "--at", "1", "--at", "5.5", "--out-dir", self.tmp / f"still_{i}")
            self.assertEqual(code, 0, res)
            shots.append([sha256(Path(p)) for p in res["outputs"]])
        self.assertEqual(shots[0], shots[1])


if __name__ == "__main__":
    unittest.main()
