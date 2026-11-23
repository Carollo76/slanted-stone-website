# Real video clips

Clips filmed at the chalet. The Wednesday social video uses these **before**
any AI shot, and every clip that fits the season displaces a paid one.

**This is the cost control.** AI shots are billed per generation on Replicate;
clips here are free and look better. The run is capped at one AI shot
(`MAX_AI_SHOTS` in the workflow), so:

| Clips for the season | Video is | Paid generations |
|---|---|---|
| 0 | 1 shot, all AI | 1 |
| 1 | 2 shots | 1 |
| 2 | 3 shots | 1 |
| 3 or more | 3 shots, all real | **0** |

Three clips per season makes the video free to produce. Set `MAX_AI_SHOTS` to
`0` to guarantee no spend at all, though with no clips there is then nothing
to film and the run stops.

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
