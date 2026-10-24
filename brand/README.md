# remotion-ffmpeg-skill brand assets

The app icon is a real Liquid Glass `.icon` bundle made with [fresnel](https://github.com/kajisho5/fresnel) from `src/icon.spec.json`, `src/wave.svg` and `src/frame.svg`: measured audio levels inside the corner marks of a video frame — the skill measures the footage, then draws inside the frame.

```bash
npx fresnel-icon build brand/src/icon.spec.json -o brand/AppIcon.icon
npx fresnel-icon render brand/AppIcon.icon -s 512 -o brand/png/icon-512.png        # -a dark for the dark appearance
npx fresnel-icon export brand/AppIcon.icon -o out --formats png --sizes 1024 --appearances default,dark
```

The wordmark is outlined from Inter SemiBold (SIL Open Font License 1.1) by `src/wordmark.py`.

| File | Use |
|---|---|
| `AppIcon.icon` | the icon, editable in fresnel or Icon Composer |
| `png/icon-512.png`, `png/icon-dark-512.png` | icon, Default / Dark appearance, masked |
| `png/icon-fullbleed-1024.png`, `png/icon-dark-fullbleed-1024.png` | unmasked, opaque squares |
| `logo/logo-dark.svg`, `logo/logo-light.svg` | horizontal lockup for dark / light backgrounds |
| `logo/wordmark-white.svg`, `logo/wordmark-black.svg` | wordmark only |
| `social/github-social-preview.png` | GitHub social preview (1280×640) |

Write the name in lowercase. The icon does not use Remotion's or FFmpeg's marks; this project is not affiliated with either.
