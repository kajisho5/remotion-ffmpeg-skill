#!/usr/bin/env python3
"""Generate the fictional eval media into a folder (lavfi test patterns and tones, no real people).

    python3 evals/make_fixtures.py DIR
"""
import subprocess
import sys
from pathlib import Path

SRT = """1
00:00:00,300 --> 00:00:02,800
Welcome to the placeholder talk.

2
00:00:05,200 --> 00:00:07,600
This line comes after a pause.
"""

JA_SRT = """1
00:00:00,300 --> 00:00:02,800
これは架空の講演のテスト字幕です。

2
00:00:05,200 --> 00:00:07,600
間を空けたあとの二つ目の字幕
"""


WORDS = """{"segments": [
 {"words": [{"word": " Welcome", "start": 0.3, "end": 0.8}, {"word": " to", "start": 0.8, "end": 1.0},
            {"word": " the", "start": 1.0, "end": 1.2}, {"word": " placeholder", "start": 1.2, "end": 1.9},
            {"word": " talk.", "start": 1.9, "end": 2.8}]},
 {"words": [{"word": " This", "start": 5.2, "end": 5.5}, {"word": " line", "start": 5.5, "end": 5.9},
            {"word": " comes", "start": 5.9, "end": 6.3}, {"word": " after", "start": 6.3, "end": 6.8},
            {"word": " a", "start": 6.8, "end": 6.9}, {"word": " pause.", "start": 6.9, "end": 7.6}]}
]}
"""


def ff(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


def main(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    # talk.mp4: 8 s, 1280x720 30 fps, two shots, tone - 2 s silence - tone
    ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
       "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=30:duration=4",
       "-f", "lavfi", "-i", "sine=f=440:d=3", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
       "-f", "lavfi", "-i", "sine=f=660:d=3",
       "-filter_complex",
       "[0:v][1:v]concat=n=2:v=1:a=0[v];[2:a]aresample=44100,aformat=channel_layouts=mono[a1];"
       "[4:a]aresample=44100,aformat=channel_layouts=mono[a2];[a1][3:a][a2]concat=n=3:v=0:a=1[a]",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(d / "talk.mp4"))
    # music.mp4: 12 s, three shots, a 120 bpm kick
    ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=4",
       "-f", "lavfi", "-i", "smptebars=size=1280x720:rate=30:duration=4",
       "-f", "lavfi", "-i", "mandelbrot=size=1280x720:rate=30,trim=duration=4",
       "-f", "lavfi", "-i", "aevalsrc='sin(2*PI*80*t)*exp(-mod(t\\,0.5)*12)*(0.4+0.6*gt(t\\,8))':s=44100:d=12",
       "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]",
       "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-c:a", "aac", "-t", "12", str(d / "music.mp4"))
    (d / "talk.srt").write_text(SRT, encoding="utf-8")
    (d / "talk_words.json").write_text(WORDS, encoding="utf-8")
    (d / "talk_ja.srt").write_text(JA_SRT, encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "eval_media"))
