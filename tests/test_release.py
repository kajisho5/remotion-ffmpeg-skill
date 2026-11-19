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


class ReleaseWorkflowOrder(unittest.TestCase):
    """The release commit is pushed with GITHUB_TOKEN, so no workflow runs on it on main: release.yml tests it
    between the commit and every push (Velisa ADR-023)."""

    def test_release_commit_is_tested_before_any_push(self):
        text = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        test_step = text.index("- name: Test the release commit before pushing it")
        self.assertLess(text.index("git commit -am"), test_step)
        pushes = [i for i in range(len(text)) if text.startswith("git push", i)]
        self.assertTrue(pushes)
        for push in pushes:
            self.assertLess(test_step, push)
        self.assertIn("python3 -m unittest discover -s tests", text[test_step:pushes[0]])


if __name__ == "__main__":
    unittest.main()
