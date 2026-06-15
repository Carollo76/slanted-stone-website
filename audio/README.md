# Social Video Background Music

Music tracks used by `scripts/social_video_generate.py` to score the
Wed/Fri auto-generated social videos.

## How it works

1. The generator picks a `audio_mood` (one of: `fireplace`, `forest`,
   `rain`, `evening`, `ambient`) based on the rotating video format.
2. `pick_audio_track(mood)` looks in `audio/<mood>/` and returns a
   random file. If that folder is empty it falls back to `audio/ambient/`.
3. If both are empty, the workflow uses a *tamed* synthesized
   ambient (no aggressive tremolo) so we never broadcast silence
   or anything embarrassing.
4. The workflow loops the chosen track to the video's duration,
   applies a 1s fade in/out, and mixes it at ~60% volume.

## What to drop here

- Short instrumental tracks. **10–60 seconds is ideal**; longer is fine,
  shorter loops cleanly.
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

## Folder map → mood

- `fireplace/` — warm, cozy, indoor (paired with sauna / fireplace / great-room photos)
- `forest/` — outdoor, organic, light (UGC/lifestyle format videos)
- `rain/` — atmospheric, melancholy
- `evening/` — relaxed, golden-hour, end-of-day (cinematic format videos)
- `ambient/` — generic fallback when the mood folder is empty
