"""P0-4 regression coverage for unconditional final audio mastering."""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from assembly import AssemblyRenderer


def _make_tone_video(path: str, duration: float = 4) -> None:
    """Generate a video with a deliberately loud mono tone."""
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x568:rate=30",
            "-f", "lavfi", "-i", f"sine=frequency=1000:duration={duration}",
            "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", path,
        ],
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_final_master_normalization_runs_without_sfx_and_outputs_stereo(tmp_path):
    """P0-4: final mastering is unconditional, after any optional SFX stage."""
    renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
    video_file = str(tmp_path / "input.mp4")
    _make_tone_video(video_file)

    renderer._finalize_audio_master(video_file, str(tmp_path), 1)

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=channels,sample_rate", "-of", "json", video_file,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["channels"] == 2
    assert stream["sample_rate"] == "48000"

    loudness = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", video_file,
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True, timeout=30,
    )
    assert "I:         -14.0 LUFS" in loudness.stderr
