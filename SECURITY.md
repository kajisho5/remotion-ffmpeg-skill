# Security policy

## Reporting a vulnerability

Please report security problems privately through GitHub's **Report a vulnerability** button on the
[Security tab](https://github.com/kajisho5/remotion-ffmpeg-skill/security/advisories/new), not in a public issue.
You will get an answer within a week.

## What this skill does with your files

- Runs only on your machine: no network calls of its own, no API keys, no telemetry. Remotion downloads its headless browser once on the first render; npm installs the pinned Remotion packages when you ask it to (`init.py --install`).
- Never modifies a source: sources and fonts are hard-linked (or copied once) into the Remotion project's `public/` folder; outputs never replace an existing file without `--overwrite`.
- Never runs a shell: every external step is an argument list (`subprocess` without `shell=True`), and every FFmpeg operation goes through ffmpeg-skill's own scripts.
- Caption and option files are data: text is drawn as written and never executed.
