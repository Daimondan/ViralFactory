"""
Generate the AI Thinking reel VO using Chatterbox voice cloning.
Per-frame generation using Daimon's WhatsApp voice notes as reference.
Outputs to data/media/voice_previews/ai_thinking_chatterbox/
"""
import json
import os
import sys
import time
import shutil
import subprocess

# Add VF src to path
sys.path.insert(0, "/home/daimon/ViralFactory/src")
os.chdir("/home/daimon/ViralFactory")

import yaml
from vo_generator import VOGenerator

# Load config
with open("config/models.yaml") as f:
    models_config = yaml.safe_load(f)

# Read the script frames
with open("/tmp/vf_ai_thinking_draft.json") as f:
    draft = json.load(f)

posts = draft["platform_content"][0]["posts"]
if isinstance(posts, str):
    posts = json.loads(posts)

# Frame 6 is on-screen text only — skip it for VO
spoken_frames = []
for i, post in enumerate(posts, 1):
    # Skip frames that are only on-screen text
    if post.strip().startswith("ON-SCREEN TEXT"):
        print(f"Frame {i}: SKIP (on-screen text only): {post[:80]}")
        continue
    # Strip the beat label prefix (HOOK:, SETUP:, etc.)
    text = post
    for prefix in ["HOOK:", "SETUP:", "TURN:", "PAYOFF:", "CLOSE:"]:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    spoken_frames.append((i, text))
    print(f"Frame {i}: {len(text)} chars — {text[:80]}...")

print(f"\nTotal spoken frames: {len(spoken_frames)}")
print(f"Total chars: {sum(len(t) for _, t in spoken_frames)}")

# Create output directory
output_dir = os.path.join("data", "media", "voice_previews", "ai_thinking_chatterbox")
os.makedirs(output_dir, exist_ok=True)

# Reference audio — deepest male clip (67Hz F0), 41 seconds
reference_audio = "/home/daimon/ViralFactory/modules/stackpenni/voice-samples/PTT-20240310-WA0003.wav"

print(f"\nReference audio: {reference_audio}")
print(f"Engine: chatterbox (CPU, Turbo model)")
print(f"Expected RTF: ~7-8x — 85s of audio will take ~10-12 min")
print()

# Initialize VO generator
vo_gen = VOGenerator(models_config, db_path="data/viralfactory.db")
cb_config = vo_gen._get_chatterbox_config()
print(f"Chatterbox config: model={cb_config['model']}, device={cb_config['device']}, "
      f"exaggeration={cb_config['exaggeration']}, cfg_weight={cb_config['cfg_weight']}")

segments = []
total_start = time.time()

for i, (frame_num, text) in enumerate(spoken_frames, 1):
    print(f"\n--- Generating frame {frame_num} ({len(text)} chars) ---")
    print(f"    Text: {text[:100]}...")
    frame_start = time.time()

    out_path = os.path.join(output_dir, f"frame_{frame_num}.wav")

    try:
        tmp_path = vo_gen._call_chatterbox(text, reference_audio, cb_config)

        # Move to output
        shutil.move(tmp_path, out_path)

        # Get duration
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", out_path],
            capture_output=True, text=True, timeout=10,
        )
        duration = float(r.stdout.strip() or 0)

        elapsed = time.time() - frame_start
        rtf = elapsed / duration if duration > 0 else 0

        print(f"    ✅ Generated: {duration:.1f}s audio in {elapsed:.1f}s (RTF {rtf:.1f}x)")

        segments.append({
            "frame": frame_num,
            "path": out_path,
            "duration": duration,
            "text": text[:200],
            "generation_time": elapsed,
            "rtf": rtf,
        })

    except Exception as e:
        print(f"    ❌ Failed: {e}")
        segments.append({
            "frame": frame_num,
            "error": str(e),
        })

total_elapsed = time.time() - total_start
total_audio = sum(s.get("duration", 0) for s in segments)
print(f"\n{'='*60}")
print(f"COMPLETE: {len(segments)} frames, {total_audio:.1f}s audio, {total_elapsed:.1f}s total")
print(f"Overall RTF: {total_elapsed/total_audio:.1f}x" if total_audio > 0 else "")

# Concatenate all frames into one file
segment_paths = [s["path"] for s in segments if "path" in s]
if segment_paths:
    print(f"\nConcatenating {len(segment_paths)} segments...")
    combined_path = os.path.join(output_dir, "ai_thinking_full_vo.wav")

    cmd = ["ffmpeg", "-y"]
    for p in segment_paths:
        cmd.extend(["-i", p])
    n = len(segment_paths)
    filter_complex = "".join(f"[{i}:a]" for i in range(n)) + f"concat=n={n}:v=0:a=1[out]"
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1",
        combined_path,
    ])
    subprocess.run(cmd, capture_output=True, timeout=120)

    # Get combined duration
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", combined_path],
        capture_output=True, text=True, timeout=10,
    )
    combined_dur = float(r.stdout.strip() or 0)
    print(f"Combined VO: {combined_path} ({combined_dur:.1f}s)")

# Save metadata
meta_path = os.path.join(output_dir, "metadata.json")
with open(meta_path, "w") as f:
    json.dump({
        "reference_audio": reference_audio,
        "engine": "chatterbox",
        "total_audio_duration": total_audio,
        "total_generation_time": total_elapsed,
        "overall_rtf": total_elapsed / total_audio if total_audio > 0 else 0,
        "segments": segments,
        "combined_path": combined_path if segment_paths else None,
    }, f, indent=2)

print(f"\nMetadata saved to {meta_path}")
print("DONE")