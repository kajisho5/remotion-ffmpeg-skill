"""Release version resolution (.github/scripts/resolve_version.py): pure decisions, no network."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".github" / "scripts"))
import resolve_version as rv  # noqa: E402


class Bump(unittest.TestCase):
    def test_labels_win_over_subjects(self):
        self.assertEqual(rv.bump_for(["enhancement"], "tidy README"), "minor")
        self.assertEqual(rv.bump_for(["bug"], "feat: something"), "patch")
        self.assertEqual(rv.bump_for(["docs"], "update docs"), "none")

    def test_conventional_subjects_without_a_pr(self):
        self.assertEqual(rv.bump_for([], "feat: karaoke captions"), "minor")
        self.assertEqual(rv.bump_for([], "feat(render): all cores"), "minor")
        self.assertEqual(rv.bump_for([], "fix: Windows path"), "patch")
        self.assertEqual(rv.bump_for([], "Add a thing"), "none")  # unlabelled push never releases

    def test_major_is_refused(self):
        with self.assertRaises(rv.Refused):
            rv.bump_for(["major"], "x")
        with self.assertRaises(rv.Refused):
            rv.bump_for([], "feat: BREAKING drop Python 3.10")

    def test_decide_takes_the_largest(self):
        best, counted = rv.decide([{"subject": "fix: a", "labels": []}, {"subject": "feat: b", "labels": []},
                                   {"subject": "docs", "labels": ["docs"]}])
        self.assertEqual(best, "minor")
        self.assertEqual(len(counted), 2)

    def test_next_version(self):
        self.assertEqual(rv.next_version("0.4.0", "minor"), "0.5.0")
        self.assertEqual(rv.next_version("0.4.3", "patch"), "0.4.4")
        self.assertEqual(rv.next_version("0.4.3", "none"), "0.4.3")

    def test_notes(self):
        _, counted = rv.decide([{"subject": "feat: karaoke", "labels": [], "pr": 7},
                                {"subject": "fix: path", "labels": [], "pr": None}])
        text = rv.notes(counted)
        self.assertIn("### Added\n\n- karaoke (#7)", text)
        self.assertIn("### Fixed\n\n- path", text)


if __name__ == "__main__":
    unittest.main()
