# ADR 0001: Render determinism

- Status: accepted
- Date: 2026-11-13
- Roadmap: ECOSYSTEM_ROADMAP.md step 13

## Context

The agent and qc-skill need to know whether a re-render can be compared with an earlier one by hash, or only by
looking at it. The contract said nothing about this. The sibling skills state it per tool as `deterministic` and
`idempotency_hint` (`bit_exact`, `content_equivalent`, `environment_dependent`). This ADR records what was measured
here and what the contract now promises.

## Measurement

Machine: Linux x86-64, 4 cores, no GPU. Remotion 4.0.540, chrome-headless-shell 156.0.8078.4 (Chrome for Testing),
FFmpeg 6.1.1, ffmpeg-skill 3.8.3. Fixture: the integration test's 8 s, 1280x720, 30 fps clip with captions from an
SRT file (`tests/test_integration.make_fixture`). For each render we compared the md5 of every decoded video frame
(`ffmpeg -f framemd5`), the md5 of the decoded audio (`-f md5`) and the sha256 of the file. The project's
`remotion.config.ts` pointed `Config.setBrowserExecutable` at the machine's chrome-headless-shell, because this machine
cannot download one. CI uses the build Remotion downloads.

| What | Renders | Result |
|---|---|---|
| All 9 compositions, H.264 full size, twice per run, two separate runs | 36 | identical per composition: frames, audio and file |
| Captioned, PeakPulse, Karaoke with `--concurrency 1` and with `--fast` | 24 | identical to each other and across runs; `--concurrency 1` gave the same bytes as all cores |
| Captioned, PeakPulse with `--codec prores` and with `--overlay` | 16 | identical |
| Graphics actually drawn: Titled with titles and a lower third, Karaoke / Emphasis / Captioned from transcript word timings (CJK auto font), Highlights / BeatMontage / PeakPulse on a beat fixture, Pip with a camera; twice each | 16 | identical |
| `still.py`, every composition, two frames, twice per run, two runs | 36 runs, 72 PNGs | identical |
| `pipeline.py --platform youtube --fast`, twice per run, two runs | 4 | render and deliverable identical; `timeline.json` differs only in `source.path` (another folder) |
| `analyze.py` twice on the same file | 2 | identical `timeline.json` |
| `init.py` twice (without `--install`) | 2 | identical folders |

On the first fixture, Pip (no camera), Titled (no titles) and Highlights (no highlights) draw no graphics of their
own, which is why the drawn-graphics row exists.

What makes runs differ, measured on Captioned with CJK word captions at `--fast`:

| Change | Frames differing | PSNR (average / lowest) |
|---|---|---|
| chrome-headless-shell 153.0.8010.12 instead of 156.0.8078.4 | 240 / 240 | 43.3 dB / 37.9 dB |
| `Config.setChromiumOpenGlRenderer("swangle")` | 240 / 240 | 42.1 dB / 38.0 dB |
| `angle`, `egl`, `swiftshader`, `vulkan` (no GPU on this machine) | 0 | identical to the default |
| `--font-file` FreeSans instead of the auto Noto Sans CJK | every frame with a caption | 29.2 dB / 25.1 dB |
| `--concurrency 1` instead of all cores | 0 | identical |

## Decision

Per tool, in `contract --json` (`tools[].deterministic`, `tools[].idempotency_hint`), with the conditions under the
top-level `determinism` key. Both are additive: `contract_version` stays `1.0`.

| Tool | deterministic | idempotency_hint | Why |
|---|---|---|---|
| analyze | yes | `content_equivalent` | byte-identical when run twice on the same file; `timeline.json` records the input's absolute path, and the `--conform` and several-input join copies were not compared |
| init | yes | `content_equivalent` | the copied project is identical; `--install` resolves the npm registry at that moment |
| still | yes | `bit_exact` | PNGs byte-identical, every composition |
| render | yes | `bit_exact` | files byte-identical, every composition, every mode measured |
| deliver | yes | `bit_exact` | the deliverable was byte-identical |
| pipeline | yes | `content_equivalent` | render and deliverable byte-identical; its `timeline.json` records paths |
| doctor | no | `environment_dependent` | it reports the machine |

No built-in composition was found not reproducible, so `determinism.not_reproducible_compositions` is empty. A
composition that ever fails the check is named there, and the CI test skips it by name. A skill-wide claim does not
hide it.

### Conditions (all must hold for `bit_exact`)

- The same machine.
- The same inputs: the same files at the same paths, with the same options and the same `--options` / `--brand` files.
- The same Remotion version (the template pins it), the same Chromium (chrome-headless-shell) build and GL backend,
  and the same FFmpeg, x264 and ffmpeg-skill.
- The same fonts. The CJK auto font is whatever ffmpeg-skill finds installed, and `--font-file` is staged into the
  project.

`--concurrency` is not a condition: one tab and all cores gave the same bytes.

### Does not hold

- Another Chromium build. Remotion and chrome-headless-shell updates change every frame slightly (table above). Compare
  by content, not by hash.
- Another GL backend set in the project's `remotion.config.ts`.
- A different font: the text is shaped differently.
- A different input path: `timeline.json` bytes differ. Its numbers do not.

### Unverified

- Across operating systems. CI checks Linux, macOS and Windows each against itself, never one against another.
- Across GPUs or GL backends. `render.py` passes no `--gl`, so Remotion's default headless backend is used.
  Without a GPU, every backend except `swangle` gave the default's bytes. A machine with a GPU was not tested.
- Another FFmpeg or x264 build.
- `analyze.py --conform`, several-input joins and `init.py --install`.
- Across two machines with the same OS and toolchain.

## Consequences

- A caller may compare two renders from one machine and toolchain by sha256. Across machines or toolchain updates, it
  compares by content: per-frame PSNR, as `test_integration.Analyze.test_real_sparse_matches_the_full_layer` does.
- `tests/test_integration.Determinism` runs on every CI OS. It renders Captioned and PeakPulse twice, the second time
  with `--concurrency 1`, and renders two stills twice. It then checks the level `render` and `still` state.
  `tests/test_contract.Repeatability` checks that every tool states both fields.
- A change that makes a composition non-reproducible (randomness, wall-clock time, an unseeded effect) fails CI. The
  fix is to make it reproducible, or to name it in `not_reproducible_compositions` and lower its hint.
