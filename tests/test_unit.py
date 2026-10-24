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


class Words(unittest.TestCase):
    WHISPER = ('{"segments": [{"words": [{"word": " Hello", "start": 0.0, "end": 0.4}, {"word": " there.", "start": 0.4, '
               '"end": 0.9}]}, {"words": [{"word": " Next", "start": 2.0, "end": 2.3}, {"word": " part", "start": 2.3, "end": 2.7}]}]}')

    def test_whisper_layout_keeps_engine_spacing(self):
        words = _captions.parse_words(self.WHISPER)
        self.assertEqual([w["text"] for w in words], [" Hello", " there.", " Next", " part"])

    def test_plain_list_and_text_key(self):
        words = _captions.parse_words('[{"text": "これは", "start": 1, "end": 1.4}, {"text": "字幕", "start": 1.4, "end": 2}]')
        self.assertEqual("".join(w["text"] for w in words), "これは字幕")

    def test_grouping_is_mechanical_and_lossless(self):
        words = _captions.parse_words(self.WHISPER)
        cues = _captions.cues_from_words(words)
        self.assertEqual([c["text"] for c in cues], ["Hello there.", "Next part"])  # split at the 1.1 s pause
        self.assertEqual("".join(c["text"] for c in cues).replace(" ", ""),
                         "".join(w["text"] for w in words).replace(" ", ""))

    def test_no_words_is_an_error(self):
        with self.assertRaises(_captions.CaptionError):
            _captions.parse_words('{"segments": [{"text": "no word timestamps"}]}')


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

    def test_new_compositions(self):
        t = timeline(highlights=[{"start": 1.0, "end": 2.5}, {"start": 5.0, "end": 6.0}])
        self.assertEqual(_common.expected_frames("Titled", t), 240)
        self.assertEqual(_common.expected_frames("BeatMontage", t), 240)
        self.assertEqual(_common.expected_frames("Karaoke", t), 240)
        self.assertEqual(_common.expected_frames("Highlights", t), 45 + 30)
        self.assertEqual(_common.expected_frames("Highlights", timeline()), 240)  # none ranked: whole file

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


class RemotionErrorsWithoutMarker(unittest.TestCase):
    def test_keeps_the_error_line_not_the_stack(self):
        log = ("Error: concurrency is set higher than the amount of CPU cores available. Available CPU cores: 2\n"
               "    at render (/x/render.js:166:40)\n    at cli (/x/index.js:121:39)\n")
        self.assertIn("concurrency is set higher", _common.remotion_error(log))
        self.assertNotIn("render.js", _common.remotion_error(log))


class RenderCommand(unittest.TestCase):
    def ns(self, **kw):
        base = dict(codec="h264", crf=None, frames=None, fast=False, concurrency="100%")
        base.update(kw)
        return argparse.Namespace(**base)

    def test_fast_preview(self):
        cmd = render.remotion_render_cmd(Path("/p"), "Jumpcut", Path("/o.mp4"), Path("/p/.rfs/x.json"), self.ns(fast=True))
        self.assertIn("--scale=0.5", cmd)
        self.assertIn("--crf=28", cmd)
        self.assertEqual(cmd[1:5], ["render", "src/index.ts", "Jumpcut", str(Path("/o.mp4"))])

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


class OutputFrame(unittest.TestCase):
    def test_source_shape_is_none(self):
        self.assertIsNone(_common.output_frame(timeline(), None, None, None))
        self.assertIsNone(_common.output_frame(timeline(), "source", None, "contain"))

    def test_portrait_keeps_short_side_and_blurs(self):
        self.assertEqual(_common.output_frame(timeline(), "9:16", None, None),
                         {"width": 720, "height": 1280, "fit": "blur"})

    def test_explicit_width_and_even_sizes(self):
        f = _common.output_frame(timeline(), "4:5", 1081, "cover")
        self.assertEqual((f["width"] % 2, f["height"] % 2), (0, 0))
        self.assertEqual(f["fit"], "cover")
        self.assertEqual(_common.output_frame(timeline(), "1:1", None, None)["width"], 720)

    def test_landscape_from_portrait_source(self):
        t = timeline()
        t["source"].update(width=1080, height=1920)
        self.assertEqual(_common.output_frame(t, "16:9", None, None), {"width": 1920, "height": 1080, "fit": "blur"})

    def test_verify_uses_the_output_frame(self):
        frame = {"width": 720, "height": 1280, "fit": "blur"}
        probe = {"duration": 8.0, "video": {"width": 720, "height": 1280, "fps": 30.0, "nb_frames": 240},
                 "audio": {"codec": "aac"}}
        ok, rows = render.verify(probe, timeline(), "Captioned", None, False, frame)
        self.assertTrue(ok, rows)


class Options(unittest.TestCase):
    def test_valid(self):
        ok = {"accent": "#fff", "captionMargin": None, "lowerThirds": [{"text": "A", "sub": "B", "start": 1, "end": 2}],
              "sceneTitles": ["x"], "driver": "beats", "beatsPerCut": 2, "title": None, "progressBar": False}
        self.assertEqual(_common.validate_options(ok), [])

    def test_typos_and_bad_values_are_refused(self):
        p = _common.validate_options({"acent": "#fff", "driver": "loud", "beatsPerCut": 0, "pulse": True,
                                      "lowerThirds": [{"text": "A", "start": 3, "end": 2}]})
        joined = " | ".join(p)
        for word in ("acent", "driver", "beatsPerCut", "pulse", "lowerThirds[0]"):
            self.assertIn(word, joined)

    def test_matches_typescript_options(self):
        ts = (ROOT / "templates" / "remotion-project" / "src" / "timeline.ts").read_text(encoding="utf-8")
        block = ts.split("export const DEFAULT_OPTIONS: Options = {")[1].split("};")[0]
        keys = {line.split(":")[0].strip() for line in block.splitlines() if ":" in line}
        self.assertEqual(keys, set(_common._OPTION_TYPES))


class Fonts(unittest.TestCase):
    def test_caption_script(self):
        cs = _common.caption_script
        self.assertEqual(cs([{"text": "これは字幕"}]), "ja")
        self.assertEqual(cs([{"text": "자막입니다"}]), "ko")
        self.assertEqual(cs([{"text": "漢字のみ"}]), "ja")
        self.assertIsNone(cs([{"text": "Plain English"}]))
        self.assertIsNone(cs([]))


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
