"""
Tests for text overlay burn-in in the AssemblyRenderer.

Verifies that the renderer:
1. Correctly collects overlays from segments with cumulative timeline positions
2. Renders PIL PNG overlays and composites them via ffmpeg
3. Burns overlays into a real video using ffmpeg
4. Handles missing overlays gracefully (returns None)
5. Handles overlay burn failures gracefully (keeps un-overlaid video)
6. Renders text with special characters without errors
7. Resolves overlay styles from config
8. Resolves font paths from config
"""

import os
import subprocess
import sys
import tempfile
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


class TestOverlayBurnIn:
    """Tests for the _burn_overlays method and overlay rendering pipeline."""

    def test_no_overlays_returns_none(self, tmp_path):
        """When the plan has no overlays, _burn_overlays returns None."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        plan = {"canvas": {"resolution": "1080x1920"}}
        segments = [{"source": "generated:1", "in": 0, "out": 3}]
        result = renderer._burn_overlays(plan, segments, str(tmp_path / "fake.mp4"),
                                         str(tmp_path), 1, 1, 1, "test")
        assert result is None

    def test_overlays_collected_with_cumulative_positions(self, tmp_path):
        """Overlays from different segments get cumulative timeline timestamps.

        With PIL rendering, the text is burned into PNGs and the ffmpeg
        filter chain contains timed overlay filters (not drawtext). We verify
        the timing expressions are correct.
        """
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        plan = {"canvas": {"resolution": "1080x1920"}}
        segments = [
            {"source": "generated:1", "in": 0, "out": 5,
             "overlays": [{"type": "caption", "text": "Hook text", "start": 0.5, "end": 2.5,
                            "style_ref": "hook", "position": "center"}]},
            {"source": "generated:2", "in": 0, "out": 4,
             "overlays": [{"type": "caption", "text": "Second overlay", "start": 1.0, "end": 3.0,
                            "style_ref": "default", "position": "bottom"}]},
        ]
        # Call _burn_overlays with a real video file
        video_file = str(tmp_path / "test.mp4")
        _make_video(video_file, duration=9)

        # We need to intercept the ffmpeg call to check the filter chain
        original_run = subprocess.run
        captured_cmd = []

        def mock_run(cmd, *args, **kwargs):
            captured_cmd.append(cmd)
            # Actually run ffmpeg so we get a real output file
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            result = renderer._burn_overlays(plan, segments, video_file,
                                             str(tmp_path), 1, 1, 1, "test")

        # The filter_complex should contain both overlays with cumulative positions
        filter_complex_args = [c for c in captured_cmd if "-filter_complex" in c]
        assert len(filter_complex_args) > 0
        filter_str = filter_complex_args[0][filter_complex_args[0].index("-filter_complex") + 1]

        # First overlay: 0.5 to 2.5 (segment 0 starts at 0)
        assert "between(t,0.50,2.50)" in filter_str
        # Second overlay: 5.0 + 1.0 = 6.0 to 5.0 + 3.0 = 8.0 (segment 1 starts at 5)
        assert "between(t,6.00,8.00)" in filter_str
        # PIL approach: overlay filters (not drawtext)
        assert "overlay=0:0" in filter_str

    def test_overlay_styles_resolved(self, tmp_path):
        """style_ref maps to concrete parameters from config."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        hook_style = renderer._resolve_overlay_style("hook")
        assert hook_style["fontsize"] == 72
        assert hook_style["fontcolor"] == "white"

        default_style = renderer._resolve_overlay_style("default")
        assert default_style["fontsize"] == 48

        highlight_style = renderer._resolve_overlay_style("highlight")
        assert highlight_style["fontcolor"] == "yellow"

        # Unknown style falls back to default
        unknown = renderer._resolve_overlay_style("nonexistent")
        assert unknown["fontsize"] == 48

    def test_font_path_resolution(self, tmp_path):
        """Font path resolves from config or falls back to system default."""
        # No config → system default
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        font = renderer._get_font_path()
        assert "DejaVuSans-Bold" in font or os.path.exists(font)

        # Config with custom font path
        custom_font = str(tmp_path / "custom.ttf")
        with open(custom_font, "w") as f:
            f.write("")  # fake font file
        renderer2 = AssemblyRenderer({"rendering": {"font_path": custom_font}},
                                     db_path=str(tmp_path / "test2.db"))
        assert renderer2._get_font_path() == custom_font

    def test_display_font_resolution(self, tmp_path):
        """Display font (Anton) resolves from config or falls back to default."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        font = renderer._get_display_font_path()
        assert os.path.exists(font) or "DejaVuSans" in font

    def test_overlay_position_mapping(self, tmp_path):
        """Position names map to pixel y-coordinates for PIL rendering."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        # Safe zone adjusted: top=120, bottom=h-350, bottom-third=0.65*h
        assert renderer._overlay_position_y("top", 1920) == 120
        assert isinstance(renderer._overlay_position_y("center", 1920), int)
        assert renderer._overlay_position_y("bottom", 1920) == 1470  # 1920-450
        assert renderer._overlay_position_y("bottom-third", 1920) == 1248  # int(1920*0.65)
        # Unknown position falls back to center
        assert isinstance(renderer._overlay_position_y("unknown", 1920), int)

    def test_real_overlay_burn_in(self, tmp_path):
        """End-to-end: burn a text overlay into a real video and verify the output.

        This test creates a real video, burns a text overlay into it using PIL,
        and checks that the output file exists and is a valid video with the
        expected duration.
        """
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create a real video
        video_file = str(tmp_path / "input.mp4")
        _make_video(video_file, duration=4)

        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 4,
                 "overlays": [
                     {"type": "caption", "text": "TEST OVERLAY",
                      "start": 0.5, "end": 3.0,
                      "style_ref": "hook", "position": "center"},
                 ]},
            ],
        }

        result = renderer._burn_overlays(plan, plan["segments"], video_file,
                                           str(tmp_path), 1, 1, 1, "test")

        # Should return the file path (overlaid in-place)
        assert result is not None
        assert os.path.exists(video_file)

        # Verify it's still a valid video
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", video_file],
            capture_output=True, text=True, timeout=10,
        )
        assert probe.returncode == 0
        data = json.loads(probe.stdout)
        dur = float(data.get("format", {}).get("duration", 0))
        assert dur > 3.0  # Should still be ~4 seconds

    def test_overlay_burn_failure_graceful(self, tmp_path):
        """If the overlay burn fails, the original video is preserved."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create a real video
        video_file = str(tmp_path / "input.mp4")
        _make_video(video_file, duration=2)

        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 2,
                 "overlays": [{"type": "caption", "text": "Test",
                                "start": 0, "end": 1}]},
            ],
        }

        # Mock subprocess.run to simulate ffmpeg failure for the overlay pass
        original_run = subprocess.run
        call_count = [0]

        def mock_run(cmd, *args, **kwargs):
            call_count[0] += 1
            # Let _log_render's provenance DB calls through (they don't use subprocess.run)
            # but make the overlay ffmpeg call fail
            if "-filter_complex" in cmd and "overlay" in " ".join(cmd):
                mock_result = MagicMock()
                mock_result.returncode = 1
                mock_result.stderr = "fake ffmpeg error"
                mock_result.stdout = ""
                return mock_result
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            result = renderer._burn_overlays(plan, plan["segments"], video_file,
                                             str(tmp_path), 1, 1, 1, "test")

        # Should return None (overlay failed, original preserved)
        assert result is None
        assert os.path.exists(video_file)  # Original still there

    def test_text_with_special_characters(self, tmp_path):
        """Text with special characters renders without errors in PIL."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3,
                 "overlays": [{"type": "caption", "text": "It's 100% real",
                                "start": 0, "end": 2}]},
            ],
        }

        video_file = str(tmp_path / "test.mp4")
        _make_video(video_file, duration=3)

        # Should not raise — PIL handles special characters natively
        result = renderer._burn_overlays(plan, plan["segments"], video_file,
                                         str(tmp_path), 1, 1, 1, "test")
        # Should succeed (no text escaping needed with PIL)
        assert result is not None
        assert os.path.exists(video_file)

    def test_multi_line_overlay(self, tmp_path):
        """Multi-line text overlays render correctly with PIL auto-wrapping."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        plan = {
            "canvas": {"resolution": "1080x1920"},
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3,
                 "overlays": [{"type": "caption",
                                "text": "AI: heavy lifting\nYOU: heavy thinking",
                                "start": 0, "end": 2,
                                "style_ref": "emphasis", "position": "center"}]},
            ],
        }

        video_file = str(tmp_path / "test.mp4")
        _make_video(video_file, duration=3)

        result = renderer._burn_overlays(plan, plan["segments"], video_file,
                                         str(tmp_path), 1, 1, 1, "test")
        assert result is not None
        assert os.path.exists(video_file)

    def test_brand_color_styles(self, tmp_path):
        """Brand color overlay styles resolve correctly from config."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        gold = renderer._resolve_overlay_style("bold-prosperity-gold")
        assert gold["fontcolor"] == "#F2B705"
        assert gold["fontsize"] == 64

        teal = renderer._resolve_overlay_style("deep-ocean-teal")
        assert teal["fontcolor"] == "#0A4D5C"

        coral = renderer._resolve_overlay_style("split-screen-coral-divider")
        assert coral["fontcolor"] == "#E8654A"

        emphasis = renderer._resolve_overlay_style("emphasis")
        assert emphasis["fontsize"] == 56