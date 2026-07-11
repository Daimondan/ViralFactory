"""
Tests for SFX mixing in the AssemblyRenderer.

Verifies that the renderer:
1. Correctly collects SFX cues from segments with cumulative timeline positions
2. Generates synthetic audio tones at the correct positions
3. Mixes SFX into a real video using ffmpeg
4. Handles missing SFX gracefully (returns None)
5. Handles SFX mix failures gracefully (keeps un-mixed video)
"""

import os
import subprocess
import sys
import json
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from assembly import AssemblyRenderer, AssemblyError


def _make_video(path: str, duration: float = 3, width: int = 1080, height: int = 1920):
    """Generate a test video with ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         path],
        capture_output=True, timeout=30,
    )
    assert os.path.exists(path), f"Failed to create test video: {path}"


def _make_silent_video(path: str, duration: float = 3, width: int = 1080, height: int = 1920):
    """Generate a test video WITHOUT an audio track."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"testsrc=duration={duration}:size={width}x{height}:rate=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         path],
        capture_output=True, timeout=30,
    )
    assert os.path.exists(path), f"Failed to create test video: {path}"


class TestSfxMixing:
    """Tests for the _mix_sfx method."""

    def test_no_sfx_returns_none(self, tmp_path):
        """When the plan has no SFX, _mix_sfx returns None."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        plan = {"canvas": {"resolution": "1080x1920"}}
        segments = [{"source": "generated:1", "in": 0, "out": 3}]
        result = renderer._mix_sfx(plan, segments, str(tmp_path / "fake.mp4"),
                                   str(tmp_path), 1, 1, 1, "test")
        assert result is None

    def test_sfx_collected_with_cumulative_positions(self, tmp_path):
        """SFX from different segments get cumulative timeline timestamps."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        plan = {"canvas": {"resolution": "1080x1920"}}
        segments = [
            {"source": "generated:1", "in": 0, "out": 5,
             "sfx": [{"t": 0.5, "type": "whoosh"}, {"t": 3.0, "type": "pop"}]},
            {"source": "generated:2", "in": 0, "out": 4,
             "sfx": [{"t": 1.0, "type": "hit"}]},
        ]
        video_file = str(tmp_path / "test.mp4")
        _make_video(video_file, duration=9)

        captured = []
        original_run = subprocess.run
        def capture_cmd(cmd, *args, **kwargs):
            if "-filter_complex" in cmd:
                fc_idx = cmd.index("-filter_complex")
                captured.append(cmd[fc_idx + 1])
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=capture_cmd):
            result = renderer._mix_sfx(plan, segments, video_file,
                                       str(tmp_path), 1, 1, 1, "test")

        assert len(captured) > 0
        filter_str = captured[0]

        # First SFX: 0.5 (segment 0, offset 0.5)
        assert "adelay=500|500" in filter_str
        # Second SFX: 3.0 (segment 0, offset 3.0)
        assert "adelay=3000|3000" in filter_str
        # Third SFX: 5.0 + 1.0 = 6.0 (segment 1 starts at 5, offset 1.0)
        assert "adelay=6000|6000" in filter_str

    def test_sfx_presets_resolved(self, tmp_path):
        """SFX type maps to synthesis parameters."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        whoosh = renderer._resolve_sfx_preset("whoosh")
        assert whoosh["freq"] == "800"
        assert whoosh["duration"] == 0.3

        pop = renderer._resolve_sfx_preset("pop")
        assert pop["freq"] == "1200"

        hit = renderer._resolve_sfx_preset("hit")
        assert hit["freq"] == "60"  # low frequency for impact

        riser = renderer._resolve_sfx_preset("riser")
        assert riser["duration"] == 0.8  # longer for tension build

        # Unknown type falls back to pop
        unknown = renderer._resolve_sfx_preset("nonexistent")
        assert unknown["freq"] == "1200"

    def test_real_sfx_mix(self, tmp_path):
        """End-to-end: mix SFX into a real video with audio."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        video_file = str(tmp_path / "input.mp4")
        _make_video(video_file, duration=4)

        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 4,
                 "sfx": [{"t": 0.5, "type": "whoosh"}, {"t": 2.0, "type": "pop"}]},
            ],
        }

        result = renderer._mix_sfx(plan, plan["segments"], video_file,
                                    str(tmp_path), 1, 1, 1, "test")

        assert result is not None
        assert os.path.exists(video_file)

        # Verify it's a valid video with audio
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", video_file],
            capture_output=True, text=True, timeout=10,
        )
        assert probe.returncode == 0
        data = json.loads(probe.stdout)
        has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
        assert has_audio

    def test_sfx_mix_on_silent_video(self, tmp_path):
        """SFX should mix into a video that has no existing audio track."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        video_file = str(tmp_path / "silent.mp4")
        _make_silent_video(video_file, duration=3)

        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3,
                 "sfx": [{"t": 0.5, "type": "pop"}]},
            ],
        }

        result = renderer._mix_sfx(plan, plan["segments"], video_file,
                                    str(tmp_path), 1, 1, 1, "test")

        assert result is not None
        assert os.path.exists(video_file)

        # Verify the video now has audio
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_streams", video_file],
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(probe.stdout)
        has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
        assert has_audio, "SFX mix should have added an audio track"

    def test_sfx_mix_failure_graceful(self, tmp_path):
        """If SFX mix fails, the original video is preserved."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        video_file = str(tmp_path / "input.mp4")
        _make_video(video_file, duration=2)

        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 2,
                 "sfx": [{"t": 0, "type": "pop"}]},
            ],
        }

        original_run = subprocess.run
        def mock_run(cmd, *args, **kwargs):
            if "-filter_complex" in cmd and "sfx" in " ".join(cmd):
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "fake ffmpeg error"
                mock_result.stdout = ""
                return mock_result
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            result = renderer._mix_sfx(plan, plan["segments"], video_file,
                                       str(tmp_path), 1, 1, 1, "test")

        assert result is None
        assert os.path.exists(video_file)  # Original preserved