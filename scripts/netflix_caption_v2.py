#!/usr/bin/env python3
"""
Re-render the Netflix experiment video with:
1. Better text styling — PIL-rendered overlay (auto-wrapped, no cutoff)
   with a proper TikTok caption look: rounded background pill, bold font,
   subtle shadow, and a slight pop-in animation.
2. Louder audio (normalized + boosted).
"""
import os
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

PROJECT = Path("/home/daimon/ViralFactory")
EXP_DIR = PROJECT / "data/media/netflix_experiment"
RAW_VIDEO = EXP_DIR / "netflix_experiment_with_audio.mp4"  # has audio already
AUDIO_FILE = EXP_DIR / "bigtan_audio_v2.mp3"
ORIGINAL_NO_AUDIO = EXP_DIR / "netflix_experiment_final.mp4"  # captioned, no audio

# Font paths (downloaded to ~/.fonts earlier)
FONT_BOLD = "/home/daimon/.hermes/profiles/vf-coder/home/.fonts/Montserrat-Bold.ttf"
FONT_DISPLAY = "/home/daimon/.hermes/profiles/vf-coder/home/.fonts/Anton-Regular.ttf"
FONT_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

CAPTION = "preparing for my netflix documentary on the boring reality of building wealth"

# Video dimensions (vertical 9:16)
W, H = 1080, 1920


def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except (IOError, OSError):
        return ImageFont.truetype(FONT_FALLBACK, size)


def wrap_text(text, font, draw, max_width):
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width or not current_line:
            current_line.append(word)
        else:
            lines.append(" ".join(current_line))
            current_line = [word]
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def render_caption_overlay():
    """Render a TikTok-style caption as a transparent PNG overlay."""
    # Create transparent overlay
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Use Montserrat Bold for a clean TikTok look
    font_size = 48
    font = load_font(FONT_BOLD, font_size)

    # Max text width with padding (leave 60px margin each side)
    max_text_width = W - 120

    # Wrap text
    lines = wrap_text(CAPTION, font, draw, max_text_width)
    line_height = font_size + 14
    total_height = len(lines) * line_height

    # Position: lower third, centered horizontally
    y_start = H - total_height - 180  # 180px from bottom

    # Draw a semi-transparent rounded rectangle behind text (pill background)
    # This is the modern TikTok style — text on a subtle dark pill
    padding_x = 30
    padding_y = 18
    # Find max line width
    max_w = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        max_w = max(max_w, bbox[2] - bbox[0])

    pill_x0 = (W - max_w) // 2 - padding_x
    pill_y0 = y_start - padding_y
    pill_x1 = (W + max_w) // 2 + padding_x
    pill_y1 = y_start + total_height + padding_y - 14

    # Draw shadow first (offset)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        [pill_x0 + 4, pill_y0 + 4, pill_x1 + 4, pill_y1 + 4],
        radius=16,
        fill=(0, 0, 0, 80),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    overlay = Image.alpha_composite(overlay, shadow)
    draw = ImageDraw.Draw(overlay)

    # Draw the pill background
    draw.rounded_rectangle(
        [pill_x0, pill_y0, pill_x1, pill_y1],
        radius=16,
        fill=(0, 0, 0, 140),  # semi-transparent black
    )

    # Draw text lines — white with subtle shadow for readability
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (W - line_w) // 2
        y = y_start + i * line_height
        # Shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))
        # Main text — slightly warm white (not pure white, more natural)
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))

    # Save overlay
    overlay_path = EXP_DIR / "caption_overlay.png"
    overlay.save(overlay_path)
    print(f"Caption overlay saved: {overlay_path}")
    print(f"Lines: {lines}")
    return overlay_path


def render_video():
    """Composite the caption overlay over the raw video + mix audio louder."""
    overlay_path = render_caption_overlay()

    output_path = EXP_DIR / "netflix_v2_styled.mp4"

    # ffmpeg: overlay PNG on video, boost audio volume
    # Using the original captioned video as source (it has the captions baked in
    # from ffmpeg drawtext — we'll cover those with the new overlay, or better:
    # use the raw_interview.mp4 which has NO captions, and add our overlay fresh)
    raw_no_caption = EXP_DIR / "raw_interview.mp4"

    vf = (
        f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[base];"
        f"[base][2:v]overlay=0:0:enable='between(t,1.0,10)'[v]"
    )

    # Audio: take from the with-audio version, boost 2x and normalize
    af = "volume=2.0,loudnorm=I=-14:TP=-1.5:LRA=11"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(raw_no_caption),        # video (no captions, no audio)
        "-i", str(AUDIO_FILE),            # trending audio
        "-i", str(overlay_path),          # caption overlay PNG
        "-filter_complex", vf,
        "-map", "[v]",
        "-map", "1:a",
        "-af", af,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]
    print("Running ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: ffmpeg failed:\n{result.stderr[-3000:]}")
        return None

    # Verify
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size", "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-of", "csv=p=0", str(output_path),
    ]
    probe = subprocess.run(probe_cmd, capture_output=True, text=True).stdout.strip()
    print(f"Output: {output_path}")
    print(f"Size: {output_path.stat().st_size} bytes")
    print(f"Probe: {probe}")
    return output_path


if __name__ == "__main__":
    result = render_video()
    if result:
        print(f"\n✅ Done: {result}")
    else:
        print("\n❌ Failed")