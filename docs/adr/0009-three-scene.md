# 0009. ThreeScene: WebGL from the frame and a seed, on a named GL backend

2026-11-27. ECOSYSTEM_ROADMAP step 9. Extends ADR 0001.

## Context

Beat-driven 3D type or particles belong on the same measured timeline as the 2D compositions. WebGL output depends on Chromium's OpenGL backend. ADR 0001 found that `swangle` and the other backends give different bytes. render.py set no backend, and Chrome chose one.

## Decision

- A new `ThreeScene` composition on `@remotion/three` 4.0.540, pinned with Remotion. It uses `three` 0.186.1 and `@react-three/fiber` 9.8.2, with `@types/three` 0.186.0 for the typecheck. All four are MIT and pinned to exact versions. Like the rest of the template there is no lockfile, and `init.py --install` resolves the rest. Remotion's own licence (README "Licence") applies to these packages and renders as to any other.
- The scene is a function of the frame number and `options.seed` alone. Particles are placed by a seeded generator (mulberry32). Their motion is computed from `frame / fps`. The centre shape hits on the measured beats, or on the measured peaks without a grid, with PeakPulse's decay. There is no `useFrame`, no clock, no `Math.random`. The orbit turns the scene under a fixed camera, because a camera prop set once would not follow the frame.
- render.py and still.py gain `--gl` (angle, egl, swiftshader, swangle, vulkan, angle-egl).
  - ThreeScene's default is `swangle`. On the GPU-less test machine, `angle` (Remotion 4's own recommendation for Three.js), `egl`, `swiftshader` and `vulkan` could not create a WebGL context. `swangle` and `angle-egl` could.
  - The 2D compositions still pass no `--gl` unless one is given, so their bytes stay as ADR 0001 measured them.
- `doctor.py --project` has a `gl backend` row. It shows a `Config.setChromiumOpenGlRenderer` override in the project's `remotion.config.ts` when there is one. Otherwise it shows render.py's defaults (`ThreeScene: swangle`; the others: none set).

## Consequences

- The contract changes additively. `ThreeScene` joins the built-in compositions. render and still gain `gl`. The options gain `seed` and `threeParticles`. doctor gains a row. `determinism.holds` gains the ThreeScene line.
- Measured (`test_integration.ThreeScene`, 320x180, 60 frames, swangle): two renders, one of them with `--concurrency 1`, have the same framemd5 and the same file sha256. Another seed changes the frames.
- Unverified: a machine with a GPU, where `angle` is the better choice and its bytes will differ from `swangle`'s; and agreement across operating systems. Each CI OS checks itself only, as in ADR 0001.
