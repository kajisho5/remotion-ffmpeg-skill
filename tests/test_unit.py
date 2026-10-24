"""Unit tests that need no ffmpeg, Node or ffmpeg-skill: python3 -m unittest discover -s tests"""
import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _captions  # noqa: E402
import _common  # noqa: E402
import render  # noqa: E402


def timeline(**over):
    t = {
        "schema": _common.TIMELINE_SCHEMA,
        "source": {"path": "/x/a.mp4", "name": "a.mp4", "duration": 8.0, "fps": 30.0, "width": 1280,
                   "height": 720, "has_video": True, "has_audio": True},
        "scenes": [{"start": 0, "end": 8}], "silences": [[3.0, 5.0]],
        "speech": [[0.0, 3.15], [4.85, 8.0]], "peaks": [], "captions": [],
    }
    t.update(over)
    return t


class Captions(unittest.TestCase):
    def test_srt_multiline_and_tags(self):
        cues = _captions.parse_srt_or_vtt(
            "1\n00:00:00,300 --> 00:00:02,800\n<i>Hello</i>\nsecond line\n\n2\n00:00:03,000 --> 00:00:04,000\nnext\n")
        self.assertEqual(cues[0], {"start": 0.3, "end": 2.8, "text": "Hello\nsecond line"})
        self.assertEqual(len(cues), 2)

    def test_vtt_with_header_and_short_timestamps(self):
        cues = _captions.parse_srt_or_vtt("WEBVTT\n\nNOTE skip me\n\n00:01.500 --> 00:03.000 align:center\n<v Host>Hi</v>\n")
        self.assertEqual(cues, [{"start": 1.5, "end": 3.0, "text": "Hi"}])

    def test_text_is_never_rewritten(self):
        text = "長い字幕の文章は書いたとおりに残す、絶対に要約しない。"
        cues = _captions.parse_json_cues('[{"start": 0, "end": 1, "text": "%s"}]' % text)
        self.assertEqual(cues[0]["text"], text)

    def test_bad_cue_rejected(self):
        with self.assertRaises(_captions.CaptionError):
            _captions.parse_srt_or_vtt("1\n00:00:05,000 --> 00:00:04,000\nbackwards\n")
        with self.assertRaises(_captions.CaptionError):
            _captions.parse_json_cues('[{"start": 2, "end": 1, "text": "x"}]')


class Frames(unittest.TestCase):
    def test_round_half_up_like_javascript(self):
        self.assertEqual(_common.sec_to_frames(3.15, 30), 95)   # 94.5 -> 95 (Python round() would give 94)
        self.assertEqual(_common.sec_to_frames(4.85, 30), 146)  # 145.5 -> 146
        self.assertEqual(_common.sec_to_frames(0, 30), 0)

    def test_expected_frames(self):
        t = timeline()
        self.assertEqual(_common.expected_frames("Captioned", t), 240)
        self.assertEqual(_common.expected_frames("PeakPulse", t), 240)
        self.assertEqual(_common.expected_frames("Jumpcut", t), 95 + (240 - 146))
        self.assertIsNone(_common.expected_frames("MyOwn", t))

    def test_jumpcut_without_speech_is_whole_file(self):
        self.assertEqual(_common.expected_frames("Jumpcut", timeline(speech=[])), 240)


class Validation(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(_common.validate_timeline(timeline()), [])

    def test_problems(self):
        p = _common.validate_timeline(timeline(schema="x", speech=[[5, 2]]))
        self.assertTrue(any("schema" in s for s in p))
        self.assertTrue(any("speech" in s for s in p))
        bad = timeline()
        bad["source"]["fps"] = 0
        self.assertTrue(any("fps" in s for s in _common.validate_timeline(bad)))


class RemotionErrors(unittest.TestCase):
    def test_extracts_message_and_drops_memory_noise(self):
        log = ("Detected differing memory amounts:\nMemory reported by CGroup: 1 MB\nstack line\n"
               "An error occurred:\n Error  Error: Could not find composition with ID Nope.\n")
        self.assertEqual(_common.remotion_error(log), "Error  Error: Could not find composition with ID Nope.")


class RenderCommand(unittest.TestCase):
    def ns(self, **kw):
        base = dict(codec="h264", crf=None, frames=None, fast=False, concurrency=None)
        base.update(kw)
        return argparse.Namespace(**base)

    def test_fast_preview(self):
        cmd = render.remotion_render_cmd(Path("/p"), "Jumpcut", Path("/o.mp4"), Path("/p/.rfs/x.json"), self.ns(fast=True))
        self.assertIn("--scale=0.5", cmd)
        self.assertIn("--crf=28", cmd)
        self.assertEqual(cmd[1:5], ["render", "src/index.ts", "Jumpcut", "/o.mp4"])

    def test_prores(self):
        cmd = render.remotion_render_cmd(Path("/p"), "Captioned", Path("/o.mov"), Path("/x.json"), self.ns(codec="prores", crf=10))
        self.assertIn("--prores-profile=hq", cmd)
        self.assertFalse(any(c.startswith("--crf") for c in cmd))


class Verify(unittest.TestCase):
    def probe(self, nb=240, w=1280, h=720, fps=30.0, audio=True, duration=8.02):
        return {"duration": duration, "video": {"width": w, "height": h, "fps": fps, "nb_frames": nb},
                "audio": {"codec": "aac"} if audio else None}

    def test_pass(self):
        ok, rows = render.verify(self.probe(), timeline(), "Captioned", None, False)
        self.assertTrue(ok, rows)

    def test_frame_mismatch_fails(self):
        ok, rows = render.verify(self.probe(nb=239), timeline(), "Captioned", None, False)
        self.assertFalse(ok)
        self.assertEqual([r["check"] for r in rows if r["status"] == "FAIL"], ["frames"])

    def test_fast_is_half_size_and_frame_range(self):
        ok, rows = render.verify(self.probe(nb=90, w=640, h=360), timeline(), "Jumpcut", (0, 89), True)
        self.assertTrue(ok, rows)

    def test_missing_audio_fails(self):
        ok, _ = render.verify(self.probe(audio=False), timeline(), "PeakPulse", None, False)
        self.assertFalse(ok)

    def test_custom_composition_reports_info(self):
        ok, rows = render.verify(self.probe(nb=10), timeline(), "Custom", None, False)
        self.assertTrue(ok)
        self.assertIn("INFO", [r["status"] for r in rows])


class TemplateParity(unittest.TestCase):
    """The TypeScript duration rules must stay the same as expected_frames()."""

    def test_typescript_uses_the_same_rules(self):
        ts = (ROOT / "templates" / "remotion-project" / "src" / "timeline.ts").read_text(encoding="utf-8")
        self.assertIn("Math.round(seconds * fps)", ts)
        self.assertIn("Math.max(1, secToFrames(e, fps) - secToFrames(s, fps))", ts)
        root = (ROOT / "templates" / "remotion-project" / "src" / "Root.tsx").read_text(encoding="utf-8")
        for comp in _common.BUILTIN_COMPOSITIONS:
            self.assertIn(f'id="{comp}"', root)


if __name__ == "__main__":
    unittest.main()
