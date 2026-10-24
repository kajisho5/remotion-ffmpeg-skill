#!/usr/bin/env python3
"""Grade one eval run: the files an agent left in its work folder and its final reply.

    python3 evals/grade.py TASK_ID WORKDIR [--reply reply.txt] [--json]
    python3 evals/grade.py --prepare RUNS_DIR  # one folder per task with fresh fixture media
    python3 evals/grade.py --all RUNS_DIR      # RUNS_DIR/<task id>/ each with reply.txt

Checks are declared per task in evals/tasks.json. Videos are measured with ffmpeg-skill's
probe.py (FFMPEG_SKILL_DIR or an installed copy), like everything else in this skill.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE))
import _common  # noqa: E402

TASKS = {t["id"]: t for t in json.loads((HERE / "tasks.json").read_text(encoding="utf-8"))["tasks"]}
FIXTURE_HASHES_FILE = ".fixture_hashes.json"


def files(work: Path, glob: str) -> List[Path]:
    return sorted(p for p in work.rglob(glob) if "node_modules" not in p.parts and ".rfs" not in p.parts
                  and "public" not in p.parts)


def probe(path: Path) -> Dict[str, Any]:
    _common.STATE.json = True
    return _common.ffskill("probe", [str(path)], allow_fail=True)


def check(c: Dict[str, Any], work: Path, reply: str) -> Dict[str, Any]:
    t = c["type"]
    ok, detail = False, ""
    if t == "file":
        found = files(work, c["glob"])
        ok, detail = bool(found), f"{len(found)} match(es) for {c['glob']}"
        if found:
            data = json.loads(found[-1].read_text(encoding="utf-8"))
            if "captions" in c:
                ok = ok and len(data.get("captions", [])) == c["captions"]
                detail += f"; captions={len(data.get('captions', []))}"
            if "beats_usable" in c:
                ok = ok and bool((data.get("beats") or {}).get("usable")) == c["beats_usable"]
                detail += f"; beats usable={(data.get('beats') or {}).get('usable')}"
            if "min_highlights" in c:
                ok = ok and len(data.get("highlights", [])) >= c["min_highlights"]
                detail += f"; highlights={len(data.get('highlights', []))}"
    elif t == "video":
        fixtures = set(json.loads((work / FIXTURE_HASHES_FILE).read_text())) if (work / FIXTURE_HASHES_FILE).exists() else set()
        found = [f for f in files(work, c["glob"]) if f.name not in fixtures]
        if not found:
            return {"check": c, "ok": False, "detail": f"no video made (matching {c['glob']})"}
        seen = []
        for f in found:
            pr = probe(f)
            v = pr.get("video") or {}
            w, h, d = v.get("width"), v.get("height"), float(pr.get("duration") or 0)
            good = pr.get("status") != "failed"
            for key, cond in (("width", lambda: w == c["width"]), ("height", lambda: h == c["height"]),
                              ("max_duration", lambda: d <= c["max_duration"]),
                              ("min_duration", lambda: d >= c["min_duration"]),
                              ("square", lambda: w == h)):
                if key in c:
                    good = good and cond()
            seen.append(f"{f.name}: {w}x{h} {d:.2f}s")
            if good:
                return {"check": c, "ok": True, "detail": seen[-1]}
        ok, detail = False, "none meets it: " + "; ".join(seen)
    elif t == "no_file":
        found = files(work, c["glob"])
        excused = any(s.lower() in reply.lower() for s in c.get("unless_reply_has", []))
        ok, detail = (not found) or excused, f"{len(found)} match(es) for {c['glob']}" + (" (excused)" if excused and found else "")
    elif t == "no_dir":
        found = files(work, c["glob"])
        ok, detail = not found, f"{len(found)} Remotion project(s)"
    elif t == "reply_mentions":
        hit = [s for s in c["any"] if s.lower() in reply.lower()]
        ok, detail = bool(hit), f"found {hit}" if hit else f"none of {c['any']}"
    elif t == "source_untouched":
        hashes = json.loads((work / FIXTURE_HASHES_FILE).read_text()) if (work / FIXTURE_HASHES_FILE).exists() else {}
        f = work / c["file"]
        now = hashlib.sha1(f.read_bytes()).hexdigest() if f.exists() else None
        ok = now is not None and hashes.get(c["file"]) in (None, now)
        detail = ("unchanged" if c["file"] in hashes else "present (no recorded hash)") if ok else "changed or missing"
    else:
        detail = f"unknown check type {t}"
    return {"check": c, "ok": ok, "detail": detail}


def grade(task_id: str, work: Path, reply: str) -> Dict[str, Any]:
    task = TASKS[task_id]
    results = [check(c, work, reply) for c in task["checks"]]
    return {"task": task_id, "pass": all(r["ok"] for r in results), "checks": results}


def record_fixture_hashes(work: Path) -> None:
    hashes = {p.name: hashlib.sha1(p.read_bytes()).hexdigest() for p in work.iterdir()
              if p.is_file() and p.suffix in (".mp4", ".srt")}
    (work / FIXTURE_HASHES_FILE).write_text(json.dumps(hashes))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("task", nargs="?")
    p.add_argument("work", nargs="?")
    p.add_argument("--reply")
    p.add_argument("--all", metavar="RUNS_DIR")
    p.add_argument("--prepare", metavar="RUNS_DIR")
    p.add_argument("--json", action="store_true")
    a = p.parse_args()
    runs = []
    if a.prepare:
        import shutil
        import make_fixtures
        root = Path(a.prepare)
        make_fixtures.main(root / "_media")
        for tid, task in TASKS.items():
            work = root / tid
            work.mkdir(parents=True, exist_ok=True)
            for f in (root / "_media").iterdir():
                shutil.copy2(f, work / f.name)
            record_fixture_hashes(work)
            (work / "PROMPT.txt").write_text(task["prompt"] + "\n", encoding="utf-8")
        print(f"prepared {len(TASKS)} task folders in {root} (prompt in each PROMPT.txt)")
        return
    if a.all:
        for tid in TASKS:
            work = Path(a.all) / tid
            if work.is_dir():
                r = work / "reply.txt"
                runs.append(grade(tid, work, r.read_text(encoding="utf-8") if r.exists() else ""))
    else:
        reply = Path(a.reply).read_text(encoding="utf-8") if a.reply else ""
        runs.append(grade(a.task, Path(a.work), reply))
    if a.json:
        print(json.dumps(runs, ensure_ascii=False, indent=2))
    else:
        for r in runs:
            print(f"{'PASS' if r['pass'] else 'FAIL'}  {r['task']}")
            for c in r["checks"]:
                print(f"   {'ok ' if c['ok'] else 'NO '} {c['check']['type']}: {c['detail']}")
        print(f"{sum(r['pass'] for r in runs)}/{len(runs)} passed")
    sys.exit(0 if all(r["pass"] for r in runs) else 1)


if __name__ == "__main__":
    main()
