# For agents working on this repository

- Runtime use of the skill is documented in `SKILL.md`; this file is for agents that review, audit or change the repository itself.
- **Before reporting a defect, read `docs/design-decisions.md`.** It lists behaviours that look like bugs but are decisions, with the test that pins each.
- The contract (`python3 scripts/_contract.py --json`, generated `references/scripts.md`) is the authority on tool names, flags and error kinds. After changing a parser, run `python3 scripts/_docs.py`.
- Python and TypeScript must agree: a composition's length rule lives in `src/timeline.ts` and `expected_frames()`; an option lives in `Options` and `_OPTION_TYPES`. Tests check both pairs.
- Sample text and media stay fictional: no real people, venues or projects.
- Development rules are in `CONTRIBUTING.md`; known traps in `references/gotchas.md`.
