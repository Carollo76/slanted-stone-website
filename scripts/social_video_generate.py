#!/usr/bin/env python3
"""
Social Video Generator v2 — Slanted Stone Chalet

Generates a daily social video using multiple AI models, rotating
through several visual formats so the feed doesn't look samey.

Format rotation (deterministic by day_of_year % len):
    0. ai_cinematic       - Kling v3 image-to-video, slow cinematic motion
    1. ai_ugc_lifestyle   - Hailuo 2.3, adds people / lifestyle action
    2. ai_dreamy          - Luma Ray 2, ethereal atmospheric motion
    3. ai_cinematic       - (Kling again, different photo + theme)
    4. ai_ugc_lifestyle   - (Hailuo, different photo + theme)
    5. ai_dreamy          - (Luma, different photo + theme)

Aspect ratio: 9:16 (1080x1920) — optimised for Instagram Reels / Stories
Duration: 8-10 seconds (vs 3 sec from previous SVD setup)
Frame rate: 30fps native output

Output: writes the final video to /tmp/video.mp4 and emits the chosen
format / photo / model details to $GITHUB_OUTPUT for the downstream
posting steps.

Required env vars:
    REPLICATE_API_TOKEN   - Replicate API token
    ANTHROPIC_API_KEY     - For caption generation via Claude
    GITHUB_OUTPUT         - Set automatically by GitHub Actions
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Photos — curated for AI video. Each has a description Claude can read.
# Wide shots, exteriors, and atmospheric scenes animate well; tight
# close-ups with small objects warp badly so we leave those out.
# --------------------------------------------------------------------------- #

PHOTOS = [
    ("Hero front house.jpg", "Front exterior of chalet, cedar and stone facade, golden hour"),
    ("Hero Inside sauna.jpg", "Interior of Finnish barrel sauna, warm wood, steam, low light"),
    ("Hero firepit skilift chair.jpg", "Firepit area at dusk with orange ski lift chair swing"),
    ("hero great room.jpg", "Great room with vaulted ceilings, stone fireplace, leather sofas"),
    ("great room fireplace.jpg", "Stone fireplace with TV, cozy seating area, warm glow"),
    ("back of house.jpg", "Back exterior of chalet surrounded by forest"),
    ("RBP58894.jpg", "Chalet front exterior in winter snow, wide shot"),
    ("RBP58944.jpg", "Master bedroom, neutral tones, plush bedding, soft light"),
    ("RBP59043.jpg", "Antler chandelier with snow visible through windows"),
    ("RBP59133-Edit.jpg", "Great room wide shot, stone fireplace, two-story windows"),
    ("RBP59138-Edit.jpg", "Great room from different angle, leather sofa, natural light"),
    ("RBP59168.jpg", "Gourmet kitchen wide shot with granite island, dining table"),
    ("RBP59200.jpg", "Coffee table with Poconos book and charcuterie board"),
    ("RBP59240.jpg", "Wine glasses on Adirondack chairs in snow, orange ski lift swing behind"),
    ("RBP59263.jpg", "Sauna bucket and ladle close-up with snowy forest behind"),
]

# Themes paired with format types. The theme guides the caption tone;
# the format determines the visual look.
THEMES = [
    "Property feature spotlight",
    "Local attraction / activity suggestion",
    "Seasonal vibe / mood post",
    "Guest experience / what a stay looks like",
    "Poconos travel tip",
    "Direct booking promotion (mention code INSIDER10 for 10% off)",
]

# Format definitions: (name, replicate_model, default_input_overrides, prompt_style_hint)
# Each entry tells the generator which Replicate model to call and
# how to phrase the motion prompt so we get output that matches the format.
FORMATS = [
    {
        "name": "ai_cinematic",
        "model": "kwaivgi/kling-v2.1",
        "duration": 10,
        "aspect_ratio": "9:16",
        "audio_mood": "evening",
        "style_hint": (
            "Cinematic image-to-video. The camera barely moves: micro push-in OR "
            "micro pull-back of 5-10%, that is it. Stay anchored to what is in "
            "the photo. Atmospheric motion only: steam, snow drift, "
            "leaves shifting, light gradient. No new scenery should appear. "
            "Do NOT add fire or flames unless a fire is already lit in the photo. "
            "Feels like the opening shot of a luxury travel ad."
        ),
    },
    {
        "name": "ai_ugc_lifestyle",
        "model": "minimax/hailuo-2.3",
        "duration": 6,
        "aspect_ratio": "9:16",
        "audio_mood": "forest",
        "style_hint": (
            "UGC / lifestyle image-to-video. Locked-off or barely-moving handheld "
            "shot. Add subtle human action WITHIN the visible frame only: a hand "
            "appears reaching for an existing object, someone already in shot "
            "shifts position, steam rises from a visible cup or hot tub. Do NOT "
            "have people walk in from outside the frame. Do NOT add new rooms. "
            "Should look like a guest filming what is already in front of them."
        ),
    },
    {
        "name": "ai_dreamy",
        "model": "luma/ray-2-720p",
        "duration": 9,
        "aspect_ratio": "9:16",
        "audio_mood": "fireplace",
        "style_hint": (
            "Dreamy, ethereal image-to-video. Camera holds nearly still. Soft "
            "atmospheric motion: lens bloom, dust motes catching light, gentle "
            "rack focus across foreground/background elements that already exist "
            "in the photo. No camera travel that would reveal new scenery. "
            "Slow, hypnotic pacing — should feel like a held breath."
        ),
    },
]

# --------------------------------------------------------------------------- #
# Date / rotation context
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
    return {
        "date": now.strftime("%Y-%m-%d"),
        "day": now.strftime("%A"),
        "month": now.strftime("%B"),
        "year": str(now.year),
        "day_of_year": now.timetuple().tm_yday,
        "season": season,
    }


def pick_rotation(ctx: dict) -> dict:
    day = ctx["day_of_year"]
    format_def = FORMATS[day % len(FORMATS)]
    photo_file, photo_desc = PHOTOS[day % len(PHOTOS)]
    theme = THEMES[day % len(THEMES)]
    return {
        "format": format_def,
        "photo_file": photo_file,
        "photo_desc": photo_desc,
        "theme": theme,
    }

# --------------------------------------------------------------------------- #
# Caption generation via Claude
# --------------------------------------------------------------------------- #

CAPTION_PROMPT_TEMPLATE = """Today is {day}, {month} {date}, {year}. Season: {season}.

You are the social media manager for Slanted Stone Chalet, a luxury vacation rental in Pocono Pines, PA.

PROPERTY AMENITIES:
- Finnish barrel sauna
- Hot tub
- Game loft with shuffleboard
- Stone firepit with smores station
- Ski lift chair swing
- Gourmet kitchen
- Forest views from every window
- Sleeps 8, 4 bedrooms

NEARBY ATTRACTIONS (with drive times):
- Pocono Raceway (11 min)
- Bradys Lake (12 min)
- Kalahari Waterpark (14 min)
- Tobyhanna State Park (15 min)
- Camelback Mountain (20 min)
- Mount Airy Casino (20 min)
- Delaware Water Gap (30 min)

TODAY'S ASSIGNED PHOTO: {photo_file}
  Description: {photo_desc}

TODAY'S ASSIGNED THEME: {theme}

TODAY'S VIDEO FORMAT: {format_name}
  Visual style guidance: {style_hint}

You MUST follow the assigned photo, theme, and format above.

CRITICAL VIDEO PROMPT RULES (the model is image-to-video and tends to hallucinate
new scenery when it pans). The prompt MUST:
  - Describe motion that stays inside what is already visible in the photo.
  - NEVER use phrases like "camera drifts toward X" or "moves toward X" where X
    is a room, fireplace, window, object, or scene. The model invents a NEW X
    in the direction of motion.
  - NEVER mention rooms, doorways, hallways, or objects not visible in the photo.
  - NEVER mention "another room", "the next room", "down the hall", etc.
  - Use motion verbs anchored to the existing frame: "subtle push-in",
    "slow pan left", "gentle parallax", "soft drift right", "slight zoom out".
  - For human presence (UGC formats), describe people entering or moving
    naturally WITHIN the visible space, never appearing from a place
    outside the frame.
  - Prefer atmospheric motion (light shifts, particles, steam, breeze) over
    camera movement when the photo is busy.
  - NEVER introduce fire, flames, a firepit, candles, or glowing embers. Only
    describe flame motion when a fire is ALREADY clearly lit and visible in the
    photo, and even then anchor it strictly to the firebox or hearth it sits in
    (e.g. "existing flames in the firebox flicker"). If no lit fire is visible,
    do not mention fire, flame, embers, or "warm glow" at all — the image-to-video
    model will hallucinate a fire onto a coffee table, rug, or floor.

Captions should feel like a human host, not a marketing bot.

Output EXACTLY this JSON, nothing else:
{{
  "video_prompt": "Motion description for the chosen model. Follow the CRITICAL RULES above. Be specific about camera movement, atmosphere, and any subjects appearing — but stay within the visible frame. Keep under 100 words.",
  "facebook_caption": "Facebook caption. Warm, conversational. No hashtags. Under 300 chars.",
  "instagram_caption": "Instagram caption with 3-5 relevant hashtags at the end. Under 400 chars.",
  "gbp_caption": "Google Business Profile post. Professional but warm. Include CTA. Under 300 chars."
}}"""


def generate_captions(ctx: dict, rotation: dict, api_key: str) -> dict:
    fmt = rotation["format"]
    prompt = CAPTION_PROMPT_TEMPLATE.format(
        day=ctx["day"], month=ctx["month"], date=ctx["date"].split("-")[-1],
        year=ctx["year"], season=ctx["season"],
        photo_file=rotation["photo_file"], photo_desc=rotation["photo_desc"],
        theme=rotation["theme"],
        format_name=fmt["name"], style_hint=fmt["style_hint"],
    )

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 800,
        "messages": [{"role": "user", "content": prompt}],
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
    with urllib.request.urlopen(req) as resp:
        response = json.loads(resp.read().decode())

    text = response["content"][0]["text"].strip()
    # Strip optional markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)

# --------------------------------------------------------------------------- #
# Replicate
# --------------------------------------------------------------------------- #

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


def replicate_poll(prediction_id: str, token: str, timeout_seconds: int = 600) -> str:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        req = urllib.request.Request(
            f"https://api.replicate.com/v1/predictions/{prediction_id}",
            headers={"Authorization": f"Bearer {token}"},
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
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as f:
        f.write(resp.read())
    print(f"[info] Downloaded {url} -> {dest}")

# --------------------------------------------------------------------------- #
# Per-model input adapters
# --------------------------------------------------------------------------- #

def encode_image_url(photo_file: str) -> str:
    base = "https://slantedstone.com/images/"
    return base + urllib.parse.quote(photo_file)


def build_input_for(format_def: dict, image_url: str, video_prompt: str) -> dict:
    """Each model has slightly different input field names. Centralise that
    quirk here so the rest of the code stays clean."""
    model = format_def["model"]
    duration = format_def["duration"]
    aspect = format_def["aspect_ratio"]

    if model.startswith("kwaivgi/kling-v2.1") or model.startswith("kwaivgi/kling-v3"):
        return {
            "start_image": image_url,
            "prompt": video_prompt,
            "duration": duration,
            "aspect_ratio": aspect,
        }
    if model.startswith("minimax/hailuo"):
        return {
            "first_frame_image": image_url,
            "prompt": video_prompt,
            "duration": duration,
            "resolution": "1080p",
        }
    if model.startswith("luma/ray"):
        return {
            "start_image_url": image_url,
            "prompt": video_prompt,
            "duration": duration,
            "aspect_ratio": aspect,
        }
    raise ValueError(f"No input adapter for model {model}")

# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    replicate_token = os.environ.get("REPLICATE_API_TOKEN")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    github_output = os.environ.get("GITHUB_OUTPUT")

    missing = [n for n, v in [
        ("REPLICATE_API_TOKEN", replicate_token),
        ("ANTHROPIC_API_KEY", anthropic_key),
    ] if not v]
    if missing:
        print(f"[error] Missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    ctx = build_context()
    rotation = pick_rotation(ctx)
    fmt = rotation["format"]

    print(f"[info] Date context: {ctx}")
    print(f"[info] Rotation: format={fmt['name']}, photo={rotation['photo_file']}, theme={rotation['theme']}")

    print("[info] Generating captions + motion prompt via Claude...")
    plan = generate_captions(ctx, rotation, anthropic_key)
    print(f"[info] Video prompt: {plan['video_prompt']}")

    image_url = encode_image_url(rotation["photo_file"])
    input_payload = build_input_for(fmt, image_url, plan["video_prompt"])
    print(f"[info] Calling {fmt['model']} with input: {json.dumps(input_payload)}")

    prediction_id = replicate_create_prediction(fmt["model"], input_payload, replicate_token)
    video_url = replicate_poll(prediction_id, replicate_token)
    print(f"[info] Generated video URL: {video_url}")

    download_to(video_url, Path("/tmp/video.mp4"))

    # Persist captions for downstream steps
    Path("/tmp/fb_caption.txt").write_text(plan["facebook_caption"])
    Path("/tmp/ig_caption.txt").write_text(plan["instagram_caption"])
    Path("/tmp/gbp_caption.txt").write_text(plan["gbp_caption"])
    Path("/tmp/video_prompt.txt").write_text(plan["video_prompt"])

    if github_output:
        with open(github_output, "a") as f:
            f.write(f"photo={rotation['photo_file']}\n")
            f.write(f"format={fmt['name']}\n")
            f.write(f"model={fmt['model']}\n")
            f.write(f"audio_mood={fmt['audio_mood']}\n")
            f.write(f"video_url={video_url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
