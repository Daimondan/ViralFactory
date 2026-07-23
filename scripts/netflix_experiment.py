#!/usr/bin/env python3
"""
Experiment: Netflix documentary trend inspired 10s video.
Fitzroy sits in a chair, rustles around, adjusts lapel mic — interview prep.
TikTok-style text caption overlay added via ffmpeg.

Uses the project's own MediaAdapter (fal.ai: nano-banana-2 image + kling-3 video).
"""
import os
import sys
import time
import json
import yaml
import requests

# ── Load env vars from .env ───────────────────────────────────────────
from pathlib import Path
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from media_adapter import MediaAdapter

# ── Config ────────────────────────────────────────────────────────────
with open(PROJECT_ROOT / "config" / "models.yaml") as f:
    models_config = yaml.safe_load(f)

FITZROY_REF = str(PROJECT_ROOT / "data/media/reference/stackpenni/character_ref/fitzroy/reference_render.png")

FACE_CANON = (
    "Elderly Black Barbadian man, age 74, deep brown weathered skin, "
    "close-cropped white-grey hair, neat short white-grey beard, "
    "deep smile lines and lined forehead, kind heavy-lidded eyes, "
    "thin gold-rimmed reading glasses often pushed up or held in hand, "
    "medium build with a straight proud posture."
)
WARDROBE_CANON = (
    "Cream short-sleeve guayabera shirt with subtle vertical pleats, "
    "dark navy trousers, worn gold ring on right hand, "
    "brown felt trilby hat worn or resting nearby. "
    "No other jewelry, no modern athletic wear."
)

# Still: Fitzroy in a simple chair, mid-adjustment of a small lapel mic
# clipped to his guayabera. Documentary interview lighting, shallow DOF.
IMAGE_PROMPT = (
    f"{FACE_CANON} {WARDROBE_CANON} "
    "Seated in a simple wooden chair in a warmly lit home study, "
    "adjusting a small black lapel microphone clipped to the collar of his shirt, "
    "fingers delicately repositioning the mic clip, looking down briefly at it, "
    "a thin boom microphone just visible at the top of frame, "
    "documentary interview setup, soft window light from camera left, "
    "shallow depth of field, muted earthy background of bookshelves blurred behind, "
    "cinematic single-camera interview framing, medium shot from chest up, "
    "natural realistic photography, warm golden hour interior light, "
    "vertical 9:16 composition."
)

CAPTION_TEXT = "preparing for my netflix documentary on the boring reality of building wealth"

OUTPUT_DIR = PROJECT_ROOT / "data/media/netflix_experiment"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    adapter = MediaAdapter(models_config, db_path=str(PROJECT_ROOT / "data/viralfactory.db"))

    # ── 1. Generate still (nano-banana-2, with Fitzroy ref) ──────────
    print("\n=== STEP 1: Generate interview still ===")
    print(f"Reference image: {FITZROY_REF}")
    print(f"Prompt: {IMAGE_PROMPT[:200]}...")

    img_result = adapter.generate_image(
        prompt=IMAGE_PROMPT,
        asset_id=999,  # experiment bucket
        model="nano-banana-2",
        aspect_ratio="9:16",
        context="Netflix experiment — Fitzroy interview still",
        business_slug="stackpenni",
        owner_type="asset",
        reference_images=[FITZROY_REF],
    )
    still_path = img_result["path"]
    print(f"\nStill generated: {still_path}")
    print(f"Cost: ${img_result.get('cost_usd', 0):.4f}")

    if not os.path.exists(still_path):
        print("ERROR: still file not found!")
        sys.exit(1)

    # ── 2. Animate via Kling-3 image-to-video (10s) ──────────────────
    print("\n=== STEP 2: Submit Kling-3 image-to-video (10s) ===")
    VIDEO_PROMPT = (
        "The elderly man in the chair shifts and settles into his seat, "
        "adjusts his lapel microphone with his right hand, fidgets slightly "
        "straightening his shirt collar, looks toward camera as if preparing "
        "to be interviewed, small natural gestures — leaning back, adjusting glasses, "
        "settling in. Documentary interview b-roll, subtle realistic motion."
    )

    video_result = adapter.submit_video(
        prompt=VIDEO_PROMPT,
        asset_id=999,
        model="kling-3",
        aspect_ratio="9:16",
        duration=10,
        context="Netflix experiment — Fitzroy interview animation",
        business_slug="stackpenni",
        source_image=still_path,
        mode="image_to_video",
    )
    job_id = video_result["external_job_id"]
    print(f"Submitted: job_id={job_id}, cost est: ${video_result.get('cost_usd', 0):.4f}")

    # ── 3. Poll until complete ───────────────────────────────────────
    print("\n=== STEP 3: Polling video job ===")
    max_wait = 600  # 10 minutes max
    start = time.time()
    raw_video_path = None
    while time.time() - start < max_wait:
        time.sleep(10)
        elapsed = int(time.time() - start)
        try:
            status_result = adapter.check_video_job(job_id, provider="fal", model="kling-3")
        except Exception as e:
            print(f"  [{elapsed}s] poll error: {e}")
            continue
        status = status_result.get("status", "processing")
        print(f"  [{elapsed}s] status={status}")
        if status == "completed":
            download_url = status_result.get("download_url")
            if download_url:
                raw_video_path = str(OUTPUT_DIR / "raw_interview.mp4")
                print(f"  Downloading from {download_url[:80]}...")
                r = requests.get(download_url, timeout=120)
                r.raise_for_status()
                with open(raw_video_path, "wb") as f:
                    f.write(r.content)
                print(f"  Saved raw video: {raw_video_path} ({len(r.content)} bytes)")
                break
            else:
                print("  ERROR: completed but no download_url")
                break
        elif status == "failed":
            print("  ERROR: video job failed")
            print(f"  {json.dumps(status_result, indent=2)}")
            sys.exit(1)

    if not raw_video_path or not os.path.exists(raw_video_path):
        print("ERROR: no video downloaded")
        sys.exit(1)

    # ── 4. Add TikTok-style caption with ffmpeg ──────────────────────
    print("\n=== STEP 4: Add TikTok-style text caption ===")
    final_path = str(OUTPUT_DIR / "netflix_experiment_final.mp4")

    # Use ffmpeg drawtext with a bold font, white text + black stroke,
    # positioned center-bottom (TikTok caption style).
    # Escape the caption text for ffmpeg drawtext.
    # DejaVuSans-Bold is available; it's clean and bold like TikTok captions.
    # We wrap the text into 2 lines manually for better fit on vertical video.

    # Split caption into two lines for readability on 9:16
    line1 = "preparing for my netflix documentary"
    line2 = "on the boring reality of building wealth"

    # ffmpeg drawtext escaping: escape colons, single quotes, backslashes, %
    def esc(s):
        return s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\u2019").replace("%", "\\%")

    fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    # Vertical video is 1080x1920. Place caption around y=1450 (lower third).
    # font_size=52, white text, black border (stroke) for TikTok look.
    drawtext_l1 = (
        f"drawtext=fontfile={fontfile}:"
        f"text='{esc(line1)}':"
        f"fontsize=52:fontcolor=white:"
        f"borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=1420:"
        f"line_spacing=8"
    )
    drawtext_l2 = (
        f"drawtext=fontfile={fontfile}:"
        f"text='{esc(line2)}':"
        f"fontsize=52:fontcolor=white:"
        f"borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=1495:"
        f"line_spacing=8"
    )

    # Fade in the caption at 1s, so it doesn't fight the opening visual
    # (TikTok captions often appear after a beat)
    # We use enable='between(t,1,10)' so caption shows from 1s to end.
    drawtext_l1_fade = (
        f"drawtext=fontfile={fontfile}:"
        f"text='{esc(line1)}':"
        f"fontsize=52:fontcolor=white:"
        f"borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=1420:"
        f"enable='between(t,1.5,10)'"
    )
    drawtext_l2_fade = (
        f"drawtext=fontfile={fontfile}:"
        f"text='{esc(line2)}':"
        f"fontsize=52:fontcolor=white:"
        f"borderw=4:bordercolor=black:"
        f"x=(w-text_w)/2:y=1495:"
        f"enable='between(t,1.5,10)'"
    )

    # Slight scale to ensure 1080x1920, then overlay text
    vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,{drawtext_l1_fade},{drawtext_l2_fade}"

    cmd = [
        "ffmpeg", "-y", "-i", raw_video_path,
        "-vf", vf,
        "-c:a", "copy",
        "-movflags", "+faststart",
        final_path,
    ]
    print(f"Running ffmpeg...")
    import subprocess
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: ffmpeg failed with code {result.returncode}")
        print(result.stderr[-2000:])
        sys.exit(1)

    # ── 5. Verify ────────────────────────────────────────────────────
    print("\n=== STEP 5: Verify output ===")
    if os.path.exists(final_path):
        size = os.path.getsize(final_path)
        # Get duration + resolution via ffprobe
        probe_cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=p=0", final_path,
        ]
        probe = subprocess.run(probe_cmd, capture_output=True, text=True).stdout.strip()
        print(f"Final video: {final_path}")
        print(f"Size: {size} bytes ({size/1024:.0f} KB)")
        print(f"Stream info: {probe}")
        print("\n✅ Done!")
    else:
        print("ERROR: final video not created")
        sys.exit(1)


if __name__ == "__main__":
    main()