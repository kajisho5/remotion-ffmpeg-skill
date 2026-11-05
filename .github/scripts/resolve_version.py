#!/usr/bin/env python3
"""Decide the next release version from what was merged since the last vX.Y.Z tag.

    python3 .github/scripts/resolve_version.py            # prints: <bump> <next version> (or "none <current>")
    python3 .github/scripts/resolve_version.py --notes F  # also writes a CHANGELOG section body to F

Signals, per change since the tag (a merged PR, or a commit pushed straight to main):
  PR labels   major -> refused (a major bump is a decision, made by hand)
              minor / feature / enhancement -> minor
              patch / fix / bug -> patch
              chore / ci / docs / documentation / dependencies only -> nothing
  commit subject (no PR) "feat:" / "feat(...):" -> minor, "fix:" -> patch, "BREAKING" -> refused
Anything else counts for nothing, so an unlabelled push never releases by accident; a version
bumped by hand in package.json always wins (the release workflow only calls this when the
current version is already tagged). PR data comes from the GitHub REST API (`gh api`).
"""
import json
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

RANK = {"none": 0, "patch": 1, "minor": 2}
LABEL_BUMP = {"minor": "minor", "feature": "minor", "enhancement": "minor",
              "patch": "patch", "fix": "patch", "bug": "patch"}


class Refused(Exception):
    pass


def bump_for(labels: List[str], subject: str) -> str:
    names = {l.lower() for l in labels}
    if "major" in names or "BREAKING" in subject:
        raise Refused(f"a major change ({subject!r}): bump package.json by hand")
    found = [LABEL_BUMP[n] for n in names if n in LABEL_BUMP]
    if found:
        return max(found, key=RANK.get)
    if re.match(r"^feat(\(.+\))?!?:", subject):
        return "minor"
    if re.match(r"^fix(\(.+\))?!?:", subject):
        return "patch"
    return "none"


def next_version(current: str, bump: str) -> str:
    major, minor, patch = (int(x) for x in current.split("."))
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    return current


def decide(changes: List[Dict]) -> Tuple[str, List[Dict]]:
    """changes: [{subject, labels, pr}] -> (overall bump, the changes that count)."""
    best, counted = "none", []
    for c in changes:
        b = bump_for(c.get("labels", []), c["subject"])
        if b != "none":
            counted.append(dict(c, bump=b))
            if RANK[b] > RANK[best]:
                best = b
    return best, counted


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def gh_json(path: str) -> Optional[object]:
    proc = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else None


def collect(repo: str, since_tag: str) -> List[Dict]:
    out: List[Dict] = []
    seen_prs = set()
    for line in git("log", "--format=%H%x09%s", f"{since_tag}..HEAD").splitlines():
        sha, subject = line.split("\t", 1)
        if "[skip release]" in subject or subject.startswith("release: v"):
            continue
        prs = gh_json(f"repos/{repo}/commits/{sha}/pulls") or []
        merged = [p for p in prs if p.get("merged_at")]
        if merged:
            pr = merged[0]
            if pr["number"] in seen_prs:
                continue
            seen_prs.add(pr["number"])
            out.append({"subject": pr["title"], "labels": [l["name"] for l in pr.get("labels", [])], "pr": pr["number"]})
        else:
            out.append({"subject": subject, "labels": [], "pr": None})
    return out


def notes(counted: List[Dict]) -> str:
    groups = {"minor": "### Added", "patch": "### Fixed"}
    lines: List[str] = []
    for bump in ("minor", "patch"):
        items = [c for c in counted if c["bump"] == bump]
        if items:
            lines.append(groups[bump])
            lines.append("")
            for c in items:
                ref = f" (#{c['pr']})" if c["pr"] else ""
                title = re.sub(r"^(feat|fix)(\(.+\))?!?:\s*", "", c["subject"])
                lines.append(f"- {title}{ref}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    import os
    repo = os.environ.get("GITHUB_REPOSITORY", "kajisho5/remotion-ffmpeg-skill")
    current = json.load(open("package.json", encoding="utf-8"))["version"]
    tag = f"v{current}"
    try:
        best, counted = decide(collect(repo, tag))
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
    print(best, next_version(current, best))
    if "--notes" in sys.argv and best != "none":
        path = sys.argv[sys.argv.index("--notes") + 1]
        open(path, "w", encoding="utf-8").write(notes(counted))


if __name__ == "__main__":
    main()
