# Real video clips

Clips filmed at the chalet. The Wed/Fri social video uses these **before** any
AI shots: every clip that fits the season replaces one AI shot, so it costs
nothing on Replicate and looks real. With three or more clips for the season,
a video is made entirely from real footage.

## Folders

- `winter/`, `spring/`, `summer/`, `fall/` — clips that only look right in that
  season (snow, autumn leaves, green trees, the hot tub steaming in the cold).
- `any/` — clips that work all year (inside shots: fireplace, kitchen, game
  loft, bunk room).

The script picks from `clips/<this season>/` plus `clips/any/`, shuffled by
date. The first clip picked opens the video, under the hook line.

## What makes a good clip

- **Vertical** (hold the phone upright). Horizontal clips get centre-cropped.
- **3 to 8 seconds**, steady (tripod, gimbal, or brace against something).
  Only the first 5 seconds are used.
- 1080p at 30fps is plenty and keeps files small. 4K works too.
- No people's faces, no sound needed (the music track goes on top).
- `.mov`, `.mp4` or `.m4v`. Any file name.

## How to add them

- **GitHub website:** open this folder on github.com, *Add file → Upload files*,
  drop the clips in, commit. The website takes files up to 25 MB each, which a
  5-second 1080p clip fits easily; a 4K clip may not.
- Or hand them to Claude and it will shrink them to 1080p and add them.
