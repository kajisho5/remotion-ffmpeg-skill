"""Release version resolution (.github/scripts/resolve_version.py): pure decisions, no network."""
import ast
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

    def test_dependency_pull_requests_release_a_patch(self):
        # Velisa D37 addendum: a Dependabot pull request ships, as a patch, even with the bot's own major label.
        self.assertEqual(rv.bump_for(["dependencies"], "chore(deps): bump x from 1.0.0 to 1.0.1"), "patch")
        self.assertEqual(rv.bump_for(["dependencies", "github_actions"], "chore(deps): bump actions/checkout"), "patch")
        self.assertEqual(rv.bump_for(["dependencies", "major"], "chore(deps): bump x from 1 to 2"), "patch")
        self.assertEqual(rv.decide([{"subject": "chore(deps): bump x", "labels": ["dependencies"]},
                                    {"subject": "docs", "labels": ["docs"]}])[0], "patch")

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

    def test_media_test_classes_skip_without_ffmpeg(self):
        # The release step runs without FFmpeg (ADR 0003). A class that makes media in setUpClass needs a class-level
        # skip guard, or setUpClass raises before any per-test skip is read (ADR 0005). CI installs FFmpeg and runs them.
        source = (Path(__file__).resolve().parent / "test_integration.py").read_text(encoding="utf-8")
        unguarded = []
        for node in ast.parse(source).body:
            if not isinstance(node, ast.ClassDef):
                continue
            if not any(isinstance(f, ast.FunctionDef) and f.name == "setUpClass" for f in node.body):
                continue
            guards = [d for d in node.decorator_list if isinstance(d, ast.Call) and ast.unparse(d.func) == "unittest.skipUnless"
                      and "HAVE" in ast.unparse(d.args[0])]
            if not guards:
                unguarded.append(node.name)
        self.assertEqual(unguarded, [])


if __name__ == "__main__":
    unittest.main()
