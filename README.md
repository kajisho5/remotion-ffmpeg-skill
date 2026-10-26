# media branch

Images for the README of [remotion-ffmpeg-skill](https://github.com/kajisho5/remotion-ffmpeg-skill) and the sources of its brand assets. Kept off `main` so the skill itself ships only text and the icons it needs.

- `assets/` — demo GIFs and stills (fictional footage)
- `brand/AppIcon.icon` — the app icon, a Liquid Glass bundle made with [fresnel](https://github.com/kajisho5/fresnel)
- `brand/src/` — the icon spec and layers, and the wordmark script (Inter SemiBold, SIL Open Font License 1.1)
- `brand/social/github-social-preview.png` — GitHub social preview (1280×640)

Rebuild the icon: `npx fresnel-icon build brand/src/icon.spec.json -o brand/AppIcon.icon`, then `npx fresnel-icon render brand/AppIcon.icon -s 512 -o icon-512.png`.
