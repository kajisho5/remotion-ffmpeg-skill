# 0004. The timeline's frame rate is the exact stream rate

2026-11-20. The ecosystem rule is Velisa ADR-026 (decision D40, spec `velisa/timebase@1`, rules TB-1 and TB-2). Issue #28.

## Context

`analyze.py` wrote `source.fps` as ffmpeg-skill probe's `fps`, which is rounded to 3 decimals. For a 30000/1001 source that is 29.97. Three things then used that rounded rate:

- the compositions (`Math.round(seconds * fps)` in `src/timeline.ts`);
- `expected_frames()` / `sec_to_frames()` here;
- Remotion's encoder.

At 29.97, frame positions drift from 30000/1001 by 0.1 frame an hour, which is one frame in about 9 hours. 417 s is already 12497 frames at 29.97 against 12498 at 30000/1001.

## Decision

- `_common.exact_rate` reads a rate by TB-2:
  - an `N/D` value is taken as written;
  - a decimal that is not an integer and lies within 0.005 of base x 1000/1001 (base 24, 30, 48, 60, 120 or 240) is that NTSC rate;
  - any other decimal is its exact value.

  It never uses `limit_denominator`.
- `_common.stream_rate` gives the rate a timeline is drawn at, as the float of that exact fraction:
  - ffprobe's `r_frame_rate` when it is the stream's own rate (within 0.001 of the probe's `fps`);
  - otherwise the probe's `fps` read by TB-2, so 29.97 becomes 30000/1001.

  `analyze.py` writes it to `source.fps` and to `pip.fps`.
- The compositions and `expected_frames()` keep computing in floats with round half up (`Math.round`), so the two still agree to the frame. Only the rate they multiply by changes, to 29.97002997... at 30000/1001.
- A timeline written before this change keeps its `fps`, and its render verifies against that same value. Nothing re-reads it.
- `tests/fixtures/timebase/timebase-vectors.json` is a byte-for-byte copy of Velisa's `docs/specs/timebase-vectors.json` at Velisa commit `b7df1d82586f0b7c00fed4074aecac75cbadf893`. `.gitattributes` keeps it LF on Windows. `tests/test_timebase.py` checks its sha256 and runs the 44 vectors of what this skill has: rates, the same rate, and nearest frames.
- `tests/test_integration.NtscRate` analyses a 30000/1001 source. With a project installed, it renders the source and requires the file's `r_frame_rate` to be `30000/1001`.

## Consequences

- The timeline schema and the contract are unchanged. `source.fps` is still a number, now 29.97002997002997 instead of 29.97 for an NTSC source.
- Integer-rate sources are unchanged.
