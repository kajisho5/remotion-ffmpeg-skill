"""Unit tests that need no ffmpeg, Node or ffmpeg-skill: python3 -m unittest discover -s tests"""
import argparse
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import _captions  # noqa: E402
import _common  # noqa: E402
import _sparse  # noqa: E402
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


class Brand(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.d = Path(tempfile.mkdtemp(prefix="rfs-brand-"))
        (self.d / "fonts").mkdir()
        (self.d / "fonts" / "House.ttf").write_bytes(b"\0")

    def write(self, data):
        p = self.d / "brand.json"
        p.write_text(__import__("json").dumps(data), encoding="utf-8")
        return str(p)

    def test_only_what_the_file_states(self):
        opts, ff, notes = _common.brand_look(self.write({
            "colors": {"primary": "E53935", "text": "#f5f5f5"}, "font": "House Sans",
            "font_file": "fonts/House.ttf", "logo": "logo.png",
            "styles": {"caption": {"colour": "0xFFEE00", "size": 30}}}))
        self.assertEqual(opts["accent"], "#E53935")
        self.assertEqual(opts["textColor"], "#FFEE00")  # the caption colour wins over colors.text
        self.assertTrue(opts["fontFamily"].startswith("'House Sans', 'Noto Sans JP'"))
        self.assertEqual(ff, str((self.d / "fonts" / "House.ttf").resolve()))
        self.assertTrue(any("logo" in n for n in notes) and any("size" in n for n in notes))
        self.assertEqual(_common.validate_options(opts), [])
        self.assertEqual(_common.brand_look(self.write({"loudness": {"lufs": -16}}))[0], {})

    def test_options_win_and_font_file_flag_wins(self):
        a = argparse.Namespace(options=None, brand=self.write({"colors": {"primary": "112233"},
                                                                 "font_file": "fonts/House.ttf"}),
                               font_file="/explicit.ttf")
        opt = self.d / "o.json"
        opt.write_text('{"accent": "#000000"}', encoding="utf-8")
        a.options = str(opt)
        self.assertEqual(_common.load_look(a)["accent"], "#000000")
        self.assertEqual(a.font_file, "/explicit.ttf")

    def test_bad_colour_is_refused(self):
        with self.assertRaises(SystemExit):
            _common.brand_look(self.write({"colors": {"primary": "red"}}))

    def test_font_stack_matches_typescript(self):
        ts = (Path(__file__).resolve().parent.parent / "templates/remotion-project/src/timeline.ts").read_text()
        self.assertIn(f'fontFamily: "{_common.DEFAULT_FONT_STACK}",', ts)


class Chapters(unittest.TestCase):
    def test_youtube_format_kept_as_written(self):
        ch = _captions.parse_chapters("0:00 Intro\n1:05 - Setup and tools\n# comment\n\n1:02:03.5 Q&A\n", 4000)
        self.assertEqual([(c["start"], c["title"]) for c in ch], [(0, "Intro"), (65, "Setup and tools"), (3723.5, "Q&A")])
        self.assertEqual([c["end"] for c in ch], [65, 3723.5, 4000])

    def test_refusals(self):
        for text in ("0:00\n", "1:00 B\n0:30 A\n", "0:00 A\n99:00 B\n", "x Intro\n", "", "1:2:3:4 A\n"):
            with self.subTest(text=text), self.assertRaises(_captions.CaptionError):
                _captions.parse_chapters(text, 600)

    def test_youtube_rules_are_warnings(self):
        ok = _captions.parse_chapters("0:00 A\n0:10 B\n0:20 C\n", 30)
        self.assertEqual(_captions.youtube_chapter_warnings(ok), [])
        bad = _captions.parse_chapters("0:05 A\n0:09 B\n", 30)
        w = " ".join(_captions.youtube_chapter_warnings(bad))
        self.assertIn("0:00", w)
        self.assertIn("three", w)
        self.assertIn("10 s", w)

    def test_option_and_parity(self):
        self.assertEqual(_common.validate_options({"chapterSeconds": 3}), [])
        self.assertTrue(_common.validate_options({"chapterSeconds": -1}))
        ts = (Path(__file__).resolve().parent.parent / "templates/remotion-project/src/timeline.ts").read_text()
        self.assertIn(f"chapterSeconds: {_sparse.CHAPTER_SECONDS:g},", ts)


class Sparse(unittest.TestCase):
    T = {"source": {"fps": 30.0, "duration": 60.0},
         "captions": [{"start": 1, "end": 3, "text": "a"}, {"start": 3.5, "end": 5, "text": "b"},
                      {"start": 30, "end": 32, "text": "c"}],
         "words": [{"start": 1.01, "end": 1.4, "text": " a"}, {"start": 29.99, "end": 30.6, "text": " c"}],
         "scenes": [{"start": 0, "end": 60}], "peaks": [{"time": 10, "rms": 0.5}]}

    def test_close_cues_share_a_stretch(self):
        self.assertEqual(_sparse.caption_stretches(self.T, 2.0), [(30, 150), (900, 960)])
        self.assertEqual(_sparse.caption_stretches(self.T, 0.0), [(30, 90), (105, 150), (900, 960)])

    def test_packed_back_to_back_with_one_blank_frame(self):
        packed, _, layout = _sparse.pack(self.T, _sparse.caption_stretches(self.T, 2.0))
        self.assertEqual(layout, [(0, 120, 30), (121, 60, 900)])
        self.assertEqual(_sparse.packed_frames(layout), 181)
        self.assertEqual(_common.sec_to_frames(packed["source"]["duration"], 30.0), 181)
        self.assertEqual([_common.sec_to_frames(c["start"], 30.0) for c in packed["captions"]], [0, 75, 121])
        self.assertEqual(packed["scenes"], [])
        self.assertEqual(packed["peaks"], [])

    def test_shift_is_whole_frames_so_sub_frame_word_times_survive(self):
        packed, _, _ = _sparse.pack(self.T, _sparse.caption_stretches(self.T, 2.0))
        w0, w1 = packed["words"]
        self.assertAlmostEqual(w0["start"] * 30, 1.01 * 30 - 30, places=6)
        # a word starting just before its cue still goes with it (Karaoke assigns words by midpoint)
        self.assertAlmostEqual(w1["start"] * 30, 29.99 * 30 - (900 - 121), places=6)

    def test_place_ranges_sit_half_a_frame_inside(self):
        _, _, layout = _sparse.pack(self.T, _sparse.caption_stretches(self.T, 2.0))
        self.assertEqual(_sparse.place_args(layout, 30.0),
                         ["--place", "0.000000-3.983333@1.000000", "--place", "4.016667-6.016667@30.000000"])

    def test_titled_moves_lower_thirds_and_titled_scene_cards(self):
        t = {"source": {"fps": 30.0, "duration": 60.0}, "captions": [],
             "scenes": [{"start": 0, "end": 20}, {"start": 20, "end": 21}, {"start": 21, "end": 60}]}
        o = {"sceneTitles": ["", "Part two", "Part three"],
             "lowerThirds": [{"text": "Name", "sub": "Role", "start": 40, "end": 44}]}
        spans = _sparse.plan_stretches("Titled", t, o, 0.0)
        # scene 2: 1 s scene -> 1 s card, touching scene 3's card (capped at 2.5 s); the lower third;
        # scene 1 has no title and draws nothing
        self.assertEqual(spans, [(600, 705), (1200, 1320)])
        spans = _sparse.plan_stretches("Titled", t, o, 2.0)
        self.assertEqual(spans, [(600, 705), (1200, 1320)])
        tl, opts, layout = _sparse.pack(t, spans, o)
        self.assertEqual(layout, [(0, 105, 600), (106, 120, 1200)])
        self.assertEqual(len(tl["scenes"]), 3)  # matched to sceneTitles by index
        self.assertEqual([_common.sec_to_frames(x, 30.0) for x in (tl["scenes"][1]["start"], tl["scenes"][1]["end"])], [0, 30])
        self.assertEqual([_common.sec_to_frames(x, 30.0) for x in (tl["scenes"][2]["start"], tl["scenes"][2]["end"])], [30, 105])
        self.assertEqual(_common.sec_to_frames(opts["lowerThirds"][0]["start"], 30.0), 106)
        self.assertEqual(opts["lowerThirds"][0]["text"], "Name")
        self.assertEqual(o["lowerThirds"][0]["start"], 40)  # the caller's options are not changed

    def test_chapter_cards_are_drawn_and_moved(self):
        t = {"source": {"fps": 30.0, "duration": 100.0}, "captions": [], "scenes": [],
             "chapters": [{"start": 0, "end": 2, "title": "A"}, {"start": 2, "end": 50, "title": "B"},
                          {"start": 50, "end": 100, "title": "C"}]}
        spans = _sparse.plan_stretches("Titled", t, {}, 0.0)
        self.assertEqual(spans, [(0, 180), (1500, 1620)])  # A (2 s) touches B's 4 s card
        tl, _, layout = _sparse.pack(t, spans, {})
        self.assertEqual([_common.sec_to_frames(c["start"], 30.0) for c in tl["chapters"]], [0, 60, 181])
        self.assertEqual([_common.sec_to_frames(c["end"], 30.0) for c in tl["chapters"]], [60, 180, 301])
        self.assertEqual([c["title"] for c in tl["chapters"]], ["A", "B", "C"])
        self.assertEqual(_sparse.plan_stretches("Titled", t, {"chapterSeconds": 0}, 0.0), [])

    def test_scene_card_length_matches_titled_tsx(self):
        tsx = (Path(__file__).resolve().parent.parent / "templates/remotion-project/src/compositions/Titled.tsx").read_text()
        self.assertIn(f"Math.round(fps * {_sparse.SCENE_CARD_SECONDS:g})", tsx)

    def test_cue_past_the_end_is_kept_inside(self):
        t = {"source": {"fps": 30.0, "duration": 2.0}, "captions": [{"start": 1.5, "end": 9, "text": "x"}]}
        self.assertEqual(_sparse.caption_stretches(t, 2.0), [(45, 60)])


if __name__ == "__main__":
    unittest.main()
