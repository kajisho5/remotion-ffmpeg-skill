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
- ✅ Agent evals (12 tasks, grader; three runs, the last with a neutral prompt and both routes accepted where ffmpeg-skill alone is valid)
- ✅ Karaoke captions from word timings
- ✅ CI on Linux, macOS and Windows with real renders
- ✅ `--sparse`: draw only the stretches of long footage where captions, lower thirds or scene titles show (uses ffmpeg-skill `overlay.py --place`; falls back to the full layer without it)

## Next
- 🔜 Check `--sparse` in CI once ffmpeg-skill with `overlay.py --place` is released

## Ideas
- 💡 Brand file (`brand.json`, shared with ffmpeg-skill) for colours, fonts and logo
- 💡 Chapter cards from YouTube chapter lists
- 💡 Picture-in-picture from a second measured source (screen + camera)
- 💡 Speaker-change captions colouring (needs diarisation from a local engine)
- 💡 Remotion Lambda rendering for long jobs (opt-in, needs the user's AWS)
