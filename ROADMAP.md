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
- ✅ ffmpeg-skill's `brand.json` read as is: colours, caption colour, font, font file; logo placed on delivery
- ✅ Chapters: cards in Titled from a YouTube-style list or the file's own markers; markers + description block on delivery
- ✅ `--sparse`: draw only the stretches of long footage where captions, lower thirds or scene titles show (uses ffmpeg-skill `overlay.py --place`; falls back to the full layer without it)

## Next
- 🔜 Check `--sparse` in CI once ffmpeg-skill with `overlay.py --place` is released

## Ideas
- 💡 Picture-in-picture from a second measured source (screen + camera)
- 💡 Speaker-change captions colouring (needs diarisation from a local engine)
- 💡 Remotion Lambda rendering for long jobs (opt-in, needs the user's AWS)
