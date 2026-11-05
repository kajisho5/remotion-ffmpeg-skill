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
- ✅ Pip: a camera in a corner, synced by the offset ffmpeg-skill measures between the audio tracks
- ✅ ffmpeg-skill's `brand.json` read as is: colours, caption colour, font, font file; logo placed on delivery
- ✅ Chapters: cards in Titled from a YouTube-style list or the file's own markers; markers + description block on delivery
- ✅ `--sparse` checked in CI (Linux, macOS) against ffmpeg-skill with `overlay.py --place`
- ✅ `--sparse`: draw only the stretches of long footage where captions, lower thirds or scene titles show (uses ffmpeg-skill `overlay.py --place`; falls back to the full layer without it)

## Next — to-do list

Tick a box when it ships (with its test and docs). Order inside a group is priority order.

### Release prep
- [ ] Japanese README (`README.ja.md`), linked from the top of `README.md`
- [ ] Demo GIFs in the README for Pip, chapter cards and `--sparse` (before / after timing), fictional footage only
- [ ] Agent evals for the new features: Pip (camera + screen), chapters to YouTube, a brand file

### With ffmpeg-skill
- [ ] Proposed chapters: ffmpeg-skill `metadata.py --auto-chapters` finds the breaks (silence / scene cuts), the user writes the titles, then chapter cards + markers + description block
- [ ] Captions from speech: transcription-skill word timings -> `--words` -> Karaoke / Captioned, so a bare recording goes to a captioned video in one run
- [ ] External mic first: ffmpeg-skill `sync.py --replace-audio` puts the lav / recorder audio on the picture before measuring and drawing
- [ ] Multicam + speaker names: ffmpeg-skill `multicam.py` cuts between cameras; a name title per camera from the user's list
- [ ] Music under the edit: ffmpeg-skill background music with ducking; motion follows the music's measured beats, not the speech
- [x] Fix the source before drawing: VFR -> constant frame rate, HDR -> SDR with ffmpeg-skill (`analyze.py --conform`; without it such a source is refused)
- [ ] Podcast clips: ffmpeg-skill's measured waveform drives an animated waveform + speaker photo + captions, vertical
- [ ] Redact, then draw: ffmpeg-skill `redact.py` blurs faces / personal data before the graphics go on
- [ ] Captions both ways: burned-in animated captions plus a switchable subtitle track (ffmpeg-skill `caption.py --mode mux`)
- [ ] One-run shorts: highlights -> 9:16 with captions -> Reels, TikTok and Shorts exports and checks in a single pipeline call

### On its own
- [ ] Thumbnails: candidate frames from measured scene cuts / highlights, the user's title on top, 1280×720 checked
- [ ] YouTube end screen: an end card that keeps the end-screen element areas clear for the last 20 s
- [ ] Chapter progress bar: a progress bar split at the chapters, like the YouTube player
- [ ] Bilingual captions: two caption files (e.g. Japanese + English) shown together
- [ ] Keyword emphasis: words from the user's list are enlarged and coloured when spoken (needs word timings)
- [ ] Speaker colours: captions coloured per speaker (needs speaker detection from a local engine)

## Ideas
- 💡 Remotion Lambda rendering for long jobs (opt-in, needs the user's AWS)
