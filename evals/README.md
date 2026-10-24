# Agent evals

Does an agent that has this skill actually do the right thing from a plain request? Each task in
[`tasks.json`](tasks.json) is a natural-language request; an agent with the skill (and ffmpeg-skill)
works in a folder of fictional media, and [`grade.py`](grade.py) grades what it left behind and what
it said — not how it got there.

What the tasks probe:

| Task | What a pass means |
|---|---|
| `captions-youtube` | measured first, captions carried as written, delivered at 1920×1080, the contact sheet reported, the source untouched |
| `jumpcut-reels-ja` | Japanese request: silences cut (shorter than the source), Japanese captions, rendered 9:16 so the Reels delivery is 1080×1920 |
| `beat-montage` | the beat grid measured (`--beats`) and a full-length BeatMontage |
| `lower-third-asks-for-text` | no name given → asks for it (or clearly marks a placeholder), never invents a person |
| `plain-trim-not-this-skill` | a plain trim is ffmpeg-skill's job: no timeline, no Remotion project |
| `highlights-square` | highlights measured (`--highlights`) and a square Highlights render |

## Running

```bash
export FFMPEG_SKILL_DIR=/path/to/ffmpeg-skill
python3 evals/grade.py --prepare runs        # one folder per task: fixture media + PROMPT.txt
# For each task: give an agent the skill, the folder runs/<task id> and its PROMPT.txt;
# have it write its final reply to runs/<task id>/reply.txt. Then:
python3 evals/grade.py --all runs
```

`grade.py` measures videos with ffmpeg-skill's `probe.py`. Results of past runs are in
[`results/`](results/).
