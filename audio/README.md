# Social Video Background Music

Music tracks used by `scripts/social_video_generate.py` to score the
Wed/Fri auto-generated social videos.

## How it works

1. The generator looks for a real track (any file not named `placeholder-*`)
   in `audio/<season>/` (`winter`, `spring`, `summer`, `fall`), then
   `audio/any/`, then the older mood folders (`fireplace`, `evening`,
   `forest`, `rain`, `ambient`).
2. Only when there is no real track anywhere does it fall back to the
   `placeholder-*` synth pads, and the log says so. Those pads are what make
   the videos sound flat: add real tracks and they stop being used.
3. If even those are missing, the workflow uses a tamed synthesized ambient
   so we never broadcast silence.
4. The workflow loops the chosen track to the video's length (about 15s),
   applies a 1s fade in/out, and mixes it at ~60% volume.

## Quick start

Drop 3 to 5 all-year tracks into `audio/any/` (cozy, acoustic, lo-fi,
warm piano) and a few wintery ones into `audio/winter/`, which takes over
from December 1. Add `spring/`, `summer/` and `fall/` tracks as those
seasons come round.

## What to drop here

- Instrumental tracks with a clear start. Only the first ~15 seconds are
  used, so pick tracks that open strong (no long fade-in).
- `.mp3`, `.m4a`, `.wav`, `.aac`, or `.ogg`.
- One per file. Drop multiple in the same mood folder for variety —
  the picker chooses randomly per video.

## ⚠️ Licensing — read this

The video posts to Facebook and Instagram Reels under a **business**
account. Meta scans Reels audio for copyright and will mute / take down
posts using unlicensed music. Only use tracks that are explicitly:

- **Free for commercial use**, AND
- **Allowed on social media / monetized content**, AND
- **No attribution required** (or attribution that we can satisfy
  without crediting in-video — most platforms don't let us add credits).

### Recommended sources (in order of safety)

1. **YouTube Audio Library** — studio.youtube.com → Audio Library.
   Filter "Attribution not required". All free for commercial use,
   downloadable as mp3. **Safest pick.**
2. **Pixabay Music** — pixabay.com/music. Free for commercial use, no
   attribution required for most tracks. Sign up free, download as mp3.
3. **Uppbeat** — uppbeat.io free tier. Some tracks attribution-required;
   only use the **"No credit required"** filter.

### Avoid

- Spotify / Apple Music / SoundCloud rips
- "Royalty-free" sites that require attribution (Bensound, etc.)
- AI-generated cover songs of popular artists (Meta blocks these too)

## Folder map

- `winter/`, `spring/`, `summer/`, `fall/` — used in that season (first choice)
- `any/` — all-year tracks, used when the season folder is empty
- `fireplace/`, `evening/`, `forest/`, `rain/`, `ambient/` — older mood
  folders, still used as a last resort before the placeholder pads
