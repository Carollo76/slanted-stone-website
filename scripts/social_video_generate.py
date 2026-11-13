#!/usr/bin/env python3
"""
Social Video Generator v3 — Slanted Stone Chalet

Builds a short, hook-first vertical video for the Wed/Fri social post:

  1. Picks 3 shots that suit the season. Real clips you filmed come first
     (clips/<season>/ and clips/any/); AI shots made from the listing photos
     fill whatever is left. Snow photos are only used December to March.
  2. Asks Claude for a short hook line, one motion prompt per AI shot, and
     the Facebook / Instagram / Google Business captions.
  3. Animates each AI shot with Kling 3.0 on Replicate (no people, no
     generated audio), in parallel.
  4. Cuts the shots together at 1080x1920 with ffmpeg and puts the hook line
     on screen for the first few seconds.

The workflow then lays a music track over it (see audio/README.md) and sends
it to Slack for approval.

Output: /tmp/video.mp4 plus captions in /tmp/*_caption.txt, and details in
$GITHUB_OUTPUT for the later workflow steps.

Required env vars:
    ANTHROPIC_API_KEY     - For the hook line, motion prompts and captions.
    REPLICATE_API_TOKEN   - For AI shots. Not needed when every shot is a
                            real clip.

Optional env vars:
    ANTHROPIC_MODEL       - Claude model override (default: claude-fable-5).
                            Must accept output_config.effort (Haiku 4.5 does not).
    VIDEO_MODEL           - Replicate model for AI shots
                            (default: kwaivgi/kling-v3-video).
    VIDEO_MODE            - Kling 3.0 quality: "pro" (1080p, default) or
                            "standard" (720p, cheaper).
    SHOT_COUNT            - Shots per video, 3 or 4 (default 3).
    SEASON_OVERRIDE       - winter / spring / summer / fall, for testing.
    GITHUB_OUTPUT         - Set automatically by GitHub Actions.
"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIO_ROOT = REPO_ROOT / "audio"
CLIPS_ROOT = REPO_ROOT / "clips"
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}
CLIP_EXTS = {".mp4", ".mov", ".m4v"}
WORK_DIR = Path("/tmp/shots")
OUTPUT_VIDEO = Path("/tmp/video.mp4")

SHOT_SECONDS = 5          # each shot on screen
HOOK_SECONDS = 2.8        # hook line on screen for the first shot
WIDTH, HEIGHT, FPS = 1080, 1920, 30

DEFAULT_VIDEO_MODEL = "kwaivgi/kling-v3-video"

# Things the image-to-video model must never add. The old "lifestyle" format
# asked for hands and guests, and AI people are what made the videos look fake.
NEGATIVE_PROMPT = (
    "people, person, man, woman, child, hands, faces, crowd, animals, pets, "
    "text, captions, watermark, logo, fire, flames, embers, candles, new rooms, "
    "new furniture, warped walls, melting objects, distortion, flicker"
)

# --------------------------------------------------------------------------- #
# Photos. season "snow" = only December to March (the photo shows snow
# outside); "any" = fine all year. hook = strong enough to open a video.
# Descriptions match what is actually in each photo so Claude doesn't ask the
# video model for things that aren't there.
# --------------------------------------------------------------------------- #

PHOTOS = [
    # Snow season (Dec to Mar)
    {"file": "Hero front house.jpg", "season": "snow", "hook": True,
     "desc": "Front of the chalet in deep snow: cedar siding, big A-frame windows, covered porch, bright winter day"},
    {"file": "RBP58896.jpg", "season": "snow", "hook": False,
     "desc": "Front of the chalet seen from the snowy driveway, wide shot, bare winter trees"},
    {"file": "back of house.jpg", "season": "snow", "hook": True,
     "desc": "Back of the chalet in snow with the hot tub, barrel sauna and fire pit seating, bare forest around"},
    {"file": "Hero firepit skilift chair.jpg", "season": "snow", "hook": True,
     "desc": "Fire pit ring with black Adirondack chairs in snow, orange ski lift chair swing behind, winter forest"},
    {"file": "RBP59236.jpg", "season": "snow", "hook": True,
     "desc": "Orange ski lift chair swing hanging from a timber frame in a snowy forest"},
    {"file": "RBP59240.jpg", "season": "snow", "hook": True,
     "desc": "Glasses of red wine on Adirondack chair arms in the snow, orange ski lift swing behind"},
    {"file": "RBP59244.jpg", "season": "snow", "hook": True,
     "desc": "Hot tub with the cover open on a snowy deck, forest behind"},
    {"file": "RBP59249.jpg", "season": "snow", "hook": True,
     "desc": "Cedar barrel sauna in the snowy woods, door open, white robe hanging inside"},
    {"file": "Hero Inside sauna.jpg", "season": "snow", "hook": True,
     "desc": "Inside the barrel sauna looking out its round glass end at snowy woods, bucket and ladle on the bench"},
    {"file": "RBP59263.jpg", "season": "snow", "hook": False,
     "desc": "Wooden sauna bucket and ladle close-up, snowy ground blurred behind"},
    {"file": "smores kit.jpg", "season": "snow", "hook": False,
     "desc": "S'mores station box with chocolate bars, marshmallows and graham crackers set in the snow"},
    {"file": "RBP59043.jpg", "season": "snow", "hook": False,
     "desc": "Antler chandelier under the vaulted ceiling, snowy trees through the tall windows"},
    {"file": "RBP59123.jpg", "season": "snow", "hook": False,
     "desc": "Great room with two leather sofas and a wood coffee table, snowy forest through the big windows"},
    {"file": "hero great room.jpg", "season": "snow", "hook": False,
     "desc": "Great room seen from the loft: leather sofas, stone fireplace wall, antler chandelier, snow outside"},

    # All year
    {"file": "great room fireplace.jpg", "season": "any", "hook": True,
     "desc": "Great room facing the floor-to-ceiling stone fireplace, leather sofas, loft balcony above"},
    {"file": "RBP59128.jpg", "season": "any", "hook": True,
     "desc": "Great room centred on the stone fireplace with a TV above, two leather sofas facing each other"},
    {"file": "RBP59133.jpg", "season": "any", "hook": False,
     "desc": "Great room wide shot: stone fireplace, arched built-in shelves, leather sofa, high ceiling"},
    {"file": "RBP59153.jpg", "season": "any", "hook": True,
     "desc": "Long dining table set for eight with the kitchen and pendant lights behind"},
    {"file": "RBP59163.jpg", "season": "any", "hook": False,
     "desc": "Kitchen island with bar stools, granite top and glass pendant lights"},
    {"file": "RBP59195.jpg", "season": "any", "hook": False,
     "desc": "Pro-style gas range with brass knobs, kettle on the burner, tiled backsplash"},
    {"file": "RBP59201.jpg", "season": "any", "hook": False,
     "desc": "Charcuterie board and a Poconos book on the wood coffee table, leather sofa behind"},
    {"file": "RBP59206.jpg", "season": "any", "hook": True,
     "desc": "Close-up of a charcuterie board: cheeses, salami, strawberries, grapes, crackers"},
    {"file": "RBP59218.jpg", "season": "any", "hook": False,
     "desc": "Live-edge river dining table with river stones set in clear resin, close-up"},
    {"file": "RBP59158.jpg", "season": "any", "hook": False,
     "desc": "Place setting with white plate, napkin ring and wine glass, fruit bowl behind"},
    {"file": "RBP58971.jpg", "season": "any", "hook": False,
     "desc": "Game loft with giant bean bags, angled ceiling and a wall TV"},
    {"file": "RBP58979.jpg", "season": "any", "hook": True,
     "desc": "Retro Pac-Man arcade cabinet in the game loft, screen lit"},
    {"file": "shuffleboard.jpg", "season": "any", "hook": True,
     "desc": "Long wooden shuffleboard table running down the game loft"},
    {"file": "RBP59058.jpg", "season": "any", "hook": True,
     "desc": "Kids' bunk room with birch tree mural, deer decals, wooden bunk beds and a trundle"},
    {"file": "wooded kids room.jpg", "season": "any", "hook": False,
     "desc": "Kids' bunk room with birch trees painted on the walls and wooden stairs up to the top bunk"},
    {"file": "RBP58909.jpg", "season": "any", "hook": False,
     "desc": "Primary bed with upholstered headboard, chunky knit throw and rolled towels"},
    {"file": "RBP58988.jpg", "season": "any", "hook": False,
     "desc": "Bedroom with wood headboard, white bedding and a rust-orange throw"},
    {"file": "RBP58919.jpg", "season": "any", "hook": False,
     "desc": "Reading chair with a 'cozy' pillow beside a vase of pampas grass"},
]

THEMES = [
    "Property feature spotlight",
    "Local attraction / activity suggestion",
    "Seasonal vibe / mood post",
    "Guest experience / what a stay looks like",
    "Poconos travel tip",
    "Direct booking promotion (mention code INSIDER10 for 10% off)",
]

SNOW_MONTHS = {12, 1, 2, 3}

# --------------------------------------------------------------------------- #
# Date context
# --------------------------------------------------------------------------- #

def build_context() -> dict:
    now = datetime.now(timezone.utc)
    month_num = now.month
    if 3 <= month_num <= 5:
        season = "Spring"
    elif 6 <= month_num <= 8:
        season = "Summer"
    elif 9 <= month_num <= 11:
        season = "Fall"
    else:
        season = "Winter"
    override = os.environ.get("SEASON_OVERRIDE", "").strip().capitalize()
    if override in {"Winter", "Spring", "Summer", "Fall"}:
        season = override
        snow = season == "Winter"
    else:
        snow = month_num in SNOW_MONTHS
    return {
        "date": now.strftime("%Y-%m-%d"),
        "day": now.strftime("%A"),
        "month": now.strftime("%B"),
        "year": str(now.year),
        "day_of_year": now.timetuple().tm_yday,
        "season": season,
        "snow": snow,
    }

# --------------------------------------------------------------------------- #
# Shot selection
# --------------------------------------------------------------------------- #

def shot_count() -> int:
    try:
        n = int(os.environ.get("SHOT_COUNT", "3"))
    except ValueError:
        n = 3
    return min(max(n, 3), 4)


def find_clips(season: str) -> list[Path]:
    clips: list[Path] = []
    for folder in (season.lower(), "any"):
        d = CLIPS_ROOT / folder
        if d.is_dir():
            clips += sorted(
                p for p in d.iterdir()
                if p.suffix.lower() in CLIP_EXTS and not p.name.startswith(".")
            )
    return clips


def photo_pool(snow: bool) -> list[dict]:
    return [p for p in PHOTOS if p["season"] == "any" or (snow and p["season"] == "snow")]


def pick_shots(ctx: dict, n: int) -> list[dict]:
    """Real clips first (a clip opens the video when there is one), then AI
    shots from season-appropriate photos. Seeded by date so a re-run on the
    same day picks the same shots."""
    rng = random.Random(ctx["date"])
    shots: list[dict] = []

    clips = find_clips(ctx["season"])
    rng.shuffle(clips)
    for clip in clips[:n]:
        shots.append({"kind": "clip", "path": clip, "name": clip.name})

    if len(shots) < n:
        pool = photo_pool(ctx["snow"])
        rng.shuffle(pool)
        if not shots:
            # Open with a photo that makes a good hook; in snow season, a snow one.
            pool.sort(key=lambda p: (not p["hook"], ctx["snow"] and p["season"] != "snow"))
        for photo in pool[: n - len(shots)]:
            shots.append({"kind": "ai", "photo": photo["file"], "desc": photo["desc"],
                          "name": photo["file"]})
    return shots


def pick_theme(ctx: dict) -> str:
    return THEMES[ctx["day_of_year"] % len(THEMES)]

# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #

def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd[:4])} ...\n{result.stderr[-2000:]}")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        raise RuntimeError(f"Could not read the length of {path.name}") from None


def clip_frame_b64(path: Path) -> str:
    """One frame from the middle of a clip, small, for Claude to look at."""
    frame = WORK_DIR / f"{path.stem}_frame.jpg"
    mid = max(probe_duration(path) / 2, 0)
    run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-ss", f"{mid:.2f}",
         "-i", str(path), "-frames:v", "1", "-vf", "scale=512:-2", str(frame)])
    return base64.b64encode(frame.read_bytes()).decode()


def normalise(src: Path, dst: Path) -> None:
    """Any phone clip or AI shot -> SHOT_SECONDS of 1080x1920, 30fps, no sound.
    Horizontal footage is centre-cropped to vertical."""
    length = probe_duration(src)
    start = 0.4 if length >= SHOT_SECONDS + 0.8 else 0.0
    dur = min(SHOT_SECONDS, length - start)
    if dur < 2:
        raise RuntimeError(f"{src.name} is too short ({length:.1f}s); clips need 3 seconds or more")
    run([
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
        "-ss", f"{start:.2f}", "-i", str(src), "-t", f"{dur:.2f}", "-an",
        "-vf", (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1,format=yuv420p"),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(dst),
    ])


def find_font() -> str | None:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def wrap_hook(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return "\n".join(textwrap.wrap(text, width=18)[:3])


def assemble(pieces: list[Path], hook_text: str, dst: Path) -> None:
    listing = WORK_DIR / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in pieces))
    vf = None
    font = find_font()
    if hook_text and font:
        hook_file = WORK_DIR / "hook.txt"
        hook_file.write_text(wrap_hook(hook_text))
        fade = (f"if(lt(t,0.15),0,if(lt(t,0.45),(t-0.15)/0.3,"
                f"if(lt(t,{HOOK_SECONDS - 0.3:.2f}),1,"
                f"if(lt(t,{HOOK_SECONDS}),({HOOK_SECONDS}-t)/0.3,0))))")
        vf = (f"drawtext=fontfile={font}:textfile={hook_file}:fontsize=76:fontcolor=white:"
              f"line_spacing=14:box=1:boxcolor=black@0.45:boxborderw=28:"
              f"x=(w-text_w)/2:y=h*0.17:alpha='{fade}'")
    elif hook_text:
        print("[warn] No font found; video goes out without the hook line on screen")
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
           "-f", "concat", "-safe", "0", "-i", str(listing)]
    if vf:
        cmd += ["-vf", vf]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)]
    run(cmd)

# --------------------------------------------------------------------------- #
# Caption + shot plan via Claude
# --------------------------------------------------------------------------- #

CAPTION_PROMPT_TEMPLATE = """Today is {day}, {month} {date}, {year}. Season: {season}.

You are the social media manager for Slanted Stone Chalet, a luxury vacation rental in Pocono Pines, PA.

PROPERTY AMENITIES:
- Finnish barrel sauna
- Hot tub
- Game loft with shuffleboard and a Pac-Man arcade
- Stone firepit with smores station
- Ski lift chair swing
- Gourmet kitchen
- Forest views from every window
- Sleeps 8: three bedrooms plus a kids' bunk room (a converted office). Never call it four bedrooms; three is the permitted count.

NEARBY ATTRACTIONS (with drive times):
- Pocono Raceway (11 min)
- Bradys Lake (12 min)
- Kalahari Waterpark (14 min)
- Tobyhanna State Park (15 min)
- Camelback Mountain (20 min)
- Mount Airy Casino (20 min)
- Delaware Water Gap (30 min)

TODAY'S THEME: {theme}

TODAY'S VIDEO is {count} short shots cut together, {seconds} seconds each, in this order:
{shot_list}

Shots marked REAL CLIP are footage the owner filmed at the chalet; a frame from each is attached
in the same order. Shots marked AI SHOT will be animated from the listed photo by an
image-to-video model.

1. HOOK LINE. Write one hook line that appears on screen over shot 1 for under 3 seconds.
   It must stop the scroll: specific, concrete, about what a guest gets or feels, and true
   for this season and for what shot 1 shows. 3 to 7 words. No hashtags, no emoji, no
   exclamation marks, no prices.
   Good: "Hot tub. Snowfall. No plans." / "Your group's new favorite cabin" /
   "15 minutes from Camelback's slopes". Bad: "Welcome to Slanted Stone Chalet",
   "Book now!", anything generic that could be any rental.

2. MOTION PROMPTS. For each AI SHOT write a motion prompt; for each REAL CLIP write "".
   The image-to-video model hallucinates new scenery when it moves, so each prompt MUST:
  - Describe motion that stays inside what is already visible in the photo.
  - Use small camera moves anchored to the frame: "slow 5% push-in", "gentle parallax",
    "soft drift right", "slight pull-back". Never "moves toward X" or "reveals X".
  - NEVER mention rooms, doorways, hallways, or objects not in the photo description.
  - NEVER add people, hands, guests, pets or animals. The shots show the place, empty.
  - Prefer atmosphere over camera travel: light shifting, steam from the hot tub,
    snow falling (only if snow is in the photo), branches swaying outside.
  - NEVER introduce fire, flames, candles or embers unless a lit fire is clearly in the
    photo, and then only the existing flames in their firebox.
  - Under 60 words each.
  Example: "Locked-off shot with an almost imperceptible push-in on the leather sofas.
  Soft daylight shifts across the stone fireplace; bare branches sway gently outside the
  windows. Camera holds steady."

3. CAPTIONS. Captions should feel like a human host, not a marketing bot, and should fit
   what the shots actually show and the season.

Output EXACTLY this JSON, nothing else:
{{
  "hook_text": "3 to 7 word hook line",
  "shot_prompts": [{prompt_slots}],
  "facebook_caption": "Facebook caption. Warm, conversational. No hashtags. Under 300 chars.",
  "instagram_caption": "Instagram caption with 3-5 relevant hashtags at the end. Under 400 chars.",
  "gbp_caption": "Google Business Profile post. Professional but warm. Include CTA. Under 300 chars."
}}
shot_prompts must have exactly {count} entries, one per shot in order."""


def describe_shots(shots: list[dict]) -> str:
    lines = []
    for i, shot in enumerate(shots, 1):
        if shot["kind"] == "clip":
            lines.append(f"  Shot {i}: REAL CLIP ({shot['name']}), see attached frame")
        else:
            lines.append(f"  Shot {i}: AI SHOT from photo {shot['photo']}: {shot['desc']}")
    return "\n".join(lines)


def call_claude(content: list[dict], api_key: str) -> dict:
    anthropic_model = os.environ.get("ANTHROPIC_MODEL", "claude-fable-5")
    # Claude Fable 5 always thinks before it answers, and the thinking tokens
    # count against max_tokens. Allow plenty and keep effort low.
    body = json.dumps({
        "model": anthropic_model,
        "max_tokens": 16000,
        "output_config": {"effort": "low"},
        "messages": [{"role": "user", "content": content}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            response = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")
        raise RuntimeError(
            f"Claude API call failed ({e.code}, model={anthropic_model}): {msg[:1000]}"
        ) from e

    # The reply starts with a thinking block, so collect every text block.
    blocks = response.get("content")
    if not isinstance(blocks, list):
        blocks = []
    text_blocks = [
        block["text"]
        for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    ]
    stop_reason = response.get("stop_reason")
    if stop_reason != "end_turn" or not text_blocks:
        block_types = [
            block.get("type", "unknown") if isinstance(block, dict) else "unknown"
            for block in blocks
        ]
        raise RuntimeError(
            "Claude did not return a complete caption "
            f"(model={anthropic_model}, stop_reason={stop_reason}, "
            f"block_types={block_types})"
        )
    text = "\n".join(text_blocks).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def generate_plan(ctx: dict, shots: list[dict], theme: str, api_key: str) -> dict:
    prompt = CAPTION_PROMPT_TEMPLATE.format(
        day=ctx["day"], month=ctx["month"], date=ctx["date"].split("-")[-1],
        year=ctx["year"], season=ctx["season"], theme=theme,
        count=len(shots), seconds=SHOT_SECONDS, shot_list=describe_shots(shots),
        prompt_slots=", ".join(f'"shot {i} prompt or empty"' for i in range(1, len(shots) + 1)),
    )
    content: list[dict] = [{"type": "text", "text": prompt}]
    for shot in shots:
        if shot["kind"] == "clip":
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": "image/jpeg",
                "data": clip_frame_b64(shot["path"])}})
    plan = call_claude(content, api_key)

    prompts = plan.get("shot_prompts")
    if not isinstance(prompts, list) or len(prompts) != len(shots):
        raise RuntimeError(f"Claude returned {prompts!r} for {len(shots)} shots")
    for shot, motion in zip(shots, prompts):
        if shot["kind"] == "ai":
            if not isinstance(motion, str) or not motion.strip():
                raise RuntimeError(f"No motion prompt for {shot['name']}")
            shot["prompt"] = motion.strip()
    for key in ("hook_text", "facebook_caption", "instagram_caption", "gbp_caption"):
        if not isinstance(plan.get(key), str):
            raise RuntimeError(f"Claude's reply has no {key}")
    return plan

# --------------------------------------------------------------------------- #
# Replicate
# --------------------------------------------------------------------------- #

# api.replicate.com sits behind Cloudflare, which started answering urllib's
# default "Python-urllib/x.y" User-Agent with 403 "error code: 1010" (seen on
# the Nov 13, 2026 run). fetch_rates.py hit the same wall with PriceLabs.
USER_AGENT = "slantedstone-video/1.0 (+https://slantedstone.com)"


def replicate_create_prediction(model_slug: str, input_payload: dict, token: str) -> str:
    body = json.dumps({"input": input_payload}).encode()
    req = urllib.request.Request(
        f"https://api.replicate.com/v1/models/{model_slug}/predictions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Prefer": "wait=0",
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        msg = e.read().decode(errors="replace")
        raise RuntimeError(f"Replicate create failed ({e.code}) for {model_slug}: {msg}") from e
    prediction_id = data.get("id")
    if not prediction_id:
        raise RuntimeError(f"Replicate did not return a prediction id: {data}")
    print(f"[info] Replicate prediction {prediction_id} created for {model_slug}")
    return prediction_id


def replicate_poll(prediction_id: str, token: str, timeout_seconds: int = 900) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        req = urllib.request.Request(
            f"https://api.replicate.com/v1/predictions/{prediction_id}",
            headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
        status = data.get("status")
        print(f"[info] Prediction {prediction_id} status: {status}")
        if status == "succeeded":
            output = data.get("output")
            if isinstance(output, list):
                return output[0]
            if isinstance(output, str):
                return output
            raise RuntimeError(f"Unexpected output shape: {output!r}")
        if status in ("failed", "canceled"):
            raise RuntimeError(f"Prediction {prediction_id} {status}: {data.get('error')}")
        time.sleep(8)
    raise RuntimeError(f"Prediction {prediction_id} timed out after {timeout_seconds}s")


def download_to(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    print(f"[info] Downloaded {url} -> {dest}")


def encode_image_url(photo_file: str) -> str:
    return "https://slantedstone.com/images/" + urllib.parse.quote(photo_file)


def build_input_for(model: str, image_url: str, video_prompt: str) -> dict:
    """Input field names differ a little between Kling versions."""
    payload = {
        "start_image": image_url,
        "prompt": video_prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "duration": SHOT_SECONDS,
    }
    if model.startswith("kwaivgi/kling-v3"):
        mode = os.environ.get("VIDEO_MODE", "pro").strip().lower()
        payload["mode"] = mode if mode in {"standard", "pro"} else "pro"
        payload["generate_audio"] = False  # music is added by the workflow
        return payload
    if model.startswith("kwaivgi/kling-v2.1"):
        payload["mode"] = "pro"
        return payload
    if model.startswith("kwaivgi/kling"):
        return payload
    raise ValueError(f"No input adapter for model {model}")


def render_ai_shot(shot: dict, index: int, model: str, token: str) -> Path:
    payload = build_input_for(model, encode_image_url(shot["photo"]), shot["prompt"])
    print(f"[info] Shot {index}: {model} with {json.dumps(payload)}")
    prediction_id = replicate_create_prediction(model, payload, token)
    url = replicate_poll(prediction_id, token)
    raw = WORK_DIR / f"shot{index}_raw.mp4"
    download_to(url, raw)
    return raw

# --------------------------------------------------------------------------- #
# Music
# --------------------------------------------------------------------------- #

def pick_audio_track(season: str, rng: random.Random) -> str | None:
    """Real tracks win: audio/<season>/, then audio/any/, then the older mood
    folders. The placeholder-* synth pads are only used when nothing real has
    been added yet."""
    folders = [season.lower(), "any", "fireplace", "evening", "forest", "rain", "ambient"]
    real: list[Path] = []
    placeholders: list[Path] = []
    for name in folders:
        folder = AUDIO_ROOT / name
        if not folder.is_dir():
            continue
        tracks = sorted(p for p in folder.iterdir()
                        if p.suffix.lower() in AUDIO_EXTS and not p.name.startswith("."))
        real_here = [t for t in tracks if not t.name.startswith("placeholder")]
        placeholders += [t for t in tracks if t.name.startswith("placeholder")]
        if real_here and name in (season.lower(), "any"):
            return str(rng.choice(real_here).relative_to(REPO_ROOT))
        real += real_here
    if real:
        return str(rng.choice(real).relative_to(REPO_ROOT))
    if placeholders:
        print("[warn] No real music in audio/ yet; using a placeholder pad (see audio/README.md)")
        return str(rng.choice(placeholders).relative_to(REPO_ROOT))
    return None

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    replicate_token = os.environ.get("REPLICATE_API_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    github_output = os.environ.get("GITHUB_OUTPUT")
    model = os.environ.get("VIDEO_MODEL", "").strip() or DEFAULT_VIDEO_MODEL

    if not anthropic_key:
        print("[error] Missing env var: ANTHROPIC_API_KEY", file=sys.stderr)
        return 1
    if not shutil.which("ffmpeg"):
        print("[error] ffmpeg is not installed", file=sys.stderr)
        return 1

    if WORK_DIR.exists():
        shutil.rmtree(WORK_DIR)
    WORK_DIR.mkdir(parents=True)

    ctx = build_context()
    shots = pick_shots(ctx, shot_count())
    theme = pick_theme(ctx)
    print(f"[info] Date context: {ctx}")
    print(f"[info] Theme: {theme}")
    for i, shot in enumerate(shots, 1):
        print(f"[info] Shot {i}: {shot['kind']} {shot['name']}")

    ai_shots = [(i, s) for i, s in enumerate(shots, 1) if s["kind"] == "ai"]
    if ai_shots and not replicate_token:
        print("[error] Missing env var: REPLICATE_API_TOKEN (needed for AI shots)", file=sys.stderr)
        return 1

    print("[info] Writing hook line, motion prompts and captions via Claude...")
    plan = generate_plan(ctx, shots, theme, anthropic_key)
    print(f"[info] Hook: {plan['hook_text']}")

    raw: dict[int, Path] = {i: s["path"] for i, s in enumerate(shots, 1) if s["kind"] == "clip"}
    if ai_shots:
        with ThreadPoolExecutor(max_workers=len(ai_shots)) as pool:
            futures = {i: pool.submit(render_ai_shot, s, i, model, replicate_token)
                       for i, s in ai_shots}
            for i, fut in futures.items():
                raw[i] = fut.result()

    pieces = []
    for i in range(1, len(shots) + 1):
        piece = WORK_DIR / f"shot{i}.mp4"
        normalise(raw[i], piece)
        pieces.append(piece)
    assemble(pieces, plan["hook_text"], OUTPUT_VIDEO)
    print(f"[info] Video ready: {OUTPUT_VIDEO} ({probe_duration(OUTPUT_VIDEO):.1f}s)")

    Path("/tmp/fb_caption.txt").write_text(plan["facebook_caption"])
    Path("/tmp/ig_caption.txt").write_text(plan["instagram_caption"])
    Path("/tmp/gbp_caption.txt").write_text(plan["gbp_caption"])
    Path("/tmp/hook_text.txt").write_text(plan["hook_text"])
    Path("/tmp/video_prompt.txt").write_text(
        "\n\n".join(f"Shot {i}: {s.get('prompt', '(real clip)')}" for i, s in enumerate(shots, 1)))

    audio_track = pick_audio_track(ctx["season"], random.Random(ctx["date"] + "music"))
    print(f"[info] Audio track: {audio_track or 'none, workflow will use its synth fallback'}")

    cover = next((s["photo"] for s in shots if s["kind"] == "ai"), "")
    sources = ", ".join(s["name"] for s in shots)
    used_model = model if ai_shots else "real clips only"
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"photo={sources}\n")
            f.write(f"cover_photo={cover}\n")
            f.write("format=multi_shot\n")
            f.write(f"model={used_model}\n")
            f.write(f"ai_shots={len(ai_shots)}\n")
            f.write("audio_mood=fireplace\n")
            f.write(f"audio_track={audio_track or ''}\n")
            f.write("video_ready=true\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
