# Roadmap

Status: ✅ done · 🔜 next · 💡 idea. Order inside a section is priority order.

## Done
- ✅ Timeline from ffmpeg-skill measurements (probe, scenes, silence, peaks, beats, highlights) + captions
- ✅ Captioned, Jumpcut, PeakPulse, Titled, Highlights, BeatMontage
- ✅ Verified renders (exact frame count, fps, size, audio) + contact sheet
- ✅ Delivery through ffmpeg-skill templates and check.py
- ✅ 9:16 / 1:1 / 4:5 output, blur / contain / cover fit; platform aspect in pipeline
- ✅ CJK captions with an auto-staged font; phrase-based Japanese line breaks
- ✅ Transparent graphics layer (`--overlay --keep-graphics`)
- ✅ Several inputs joined by ffmpeg-skill before measuring
- ✅ Machine-readable contract + MCP server
- ✅ Agent evals (6 tasks, grader, first run 6/6)

## Next
- 🔜 More eval tasks (overlay layer, several inputs, options typos) and repeated runs
- 🔜 Render only the captioned ranges for long footage (segment renders composited by ffmpeg-skill)
- 🔜 macOS and Windows runs in CI
- 🔜 Word-level karaoke captions from timed words (ffmpeg-skill transcription word timings)

## Ideas
- 💡 Brand file (`brand.json`, shared with ffmpeg-skill) for colours, fonts and logo
- 💡 Chapter cards from YouTube chapter lists
- 💡 Picture-in-picture from a second measured source (screen + camera)
- 💡 Speaker-change captions colouring (needs diarisation from a local engine)
- 💡 Remotion Lambda rendering for long jobs (opt-in, needs the user's AWS)
