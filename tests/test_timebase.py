"""The ecosystem timebase spec's conformance vectors (velisa/timebase@1) against scripts/_common.py (docs/adr/0004).

tests/fixtures/timebase/timebase-vectors.json is a byte-for-byte copy of Velisa's docs/specs/timebase-vectors.json at
Velisa commit VELISA_COMMIT (its sha256 is checked). This skill reads rates (exact_rate; None is INVALID_RATE),
compares them, and rounds a time to its nearest frame (sec_to_frames, Math.round's rule). Every vector of those passes;
the others are counted."""
import hashlib
import json
import sys
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import _common  # noqa: E402

VECTORS = ROOT / "tests" / "fixtures" / "timebase" / "timebase-vectors.json"
VELISA_COMMIT = "b7df1d82586f0b7c00fed4074aecac75cbadf893"
VECTORS_SHA256 = "fecd9730470fd79fb0b8dce6a55ef1ac8fd743ea044a1f1541474ebd249e5aa1"
OFFERED = 44


class _Refused(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _rate(value):
    r = _common.exact_rate(value)
    if r is None:
        raise _Refused("INVALID_RATE")
    return r


def _text(v):
    if isinstance(v, Fraction):
        return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"
    return v


FUNCTIONS = {
    "parse_rate": lambda value: _rate(value),
    "same_rate": lambda a, b: _rate(a) == _rate(b),
    # the compositions' float arithmetic (Math.round(seconds * fps)) at the exact rate's float
    "frames_at": lambda seconds, rate, mode: _common.sec_to_frames(float(Fraction(seconds)), float(_rate(rate))),
}


def _offered(vec):
    if vec["fn"] not in FUNCTIONS or vec.get("optional"):
        return False
    return vec["fn"] != "frames_at" or vec["args"].get("mode") == "nearest"


class TimebaseVectors(unittest.TestCase):
    def test_the_copy_is_velisas_file(self):
        raw = VECTORS.read_bytes()
        self.assertEqual(json.loads(raw)["spec"], "velisa/timebase@1")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), VECTORS_SHA256, f"re-copy the vectors from Velisa {VELISA_COMMIT}")

    def test_every_offered_vector_passes(self):
        doc = json.loads(VECTORS.read_text(encoding="utf-8"))
        vecs = [v for v in doc["vectors"] if _offered(v)]
        for vec in vecs:
            with self.subTest(vec["id"]):
                try:
                    got = _text(FUNCTIONS[vec["fn"]](**vec["args"]))
                except _Refused as e:
                    self.assertEqual(e.code, vec.get("error"))
                    continue
                self.assertNotIn("error", vec, f"gave {got!r}")
                self.assertEqual(got, vec["expect"])
        self.assertEqual(len(vecs), OFFERED)
        self.assertEqual(len(doc["vectors"]) - len(vecs), 134 - OFFERED)

    def test_the_timeline_rate_comes_from_the_exact_stream_rate(self):
        self.assertEqual(_common.stream_rate({"fps": 29.97, "r_frame_rate": "30000/1001"}), 30000 / 1001)
        self.assertEqual(_common.stream_rate({"fps": 29.97}), 30000 / 1001)          # the probe's 3 decimals, TB-2
        self.assertEqual(_common.stream_rate({"fps": 59.94, "r_frame_rate": "60000/1001"}), 60000 / 1001)
        self.assertEqual(_common.stream_rate({"fps": 25.0, "r_frame_rate": "25/1"}), 25.0)
        self.assertEqual(_common.stream_rate({"fps": 29.85, "r_frame_rate": "30/1"}), 29.85)  # a base rate that is not the stream's
        self.assertEqual(_common.stream_rate({}), 30.0)
        # 417 s: 12497 frames at a rounded 29.97, 12498 at 30000/1001
        self.assertEqual(_common.sec_to_frames(417, _common.stream_rate({"fps": 29.97})), 12498)
        self.assertEqual(_common.sec_to_frames(417, 29.97), 12497)


if __name__ == "__main__":
    unittest.main()
