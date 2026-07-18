"""Tests for ASSET-REVIEW-3 (audio inspection) and ASSET-REVIEW-4 (content alignment).

ASSET-REVIEW-3:
- Audio extracted and transcribed when audio stream present
- Looping detection: if the same 5+ word phrase appears 3+ times, flag as looping
- Unexpected audio: if plan says original_audio=false and no music, but audio has content → flag
- Graceful degradation if whisper is not available

ASSET-REVIEW-4:
- Aggregates mechanical + visual + audio into a single verdict
- ready_for_operator | needs_operator_decision | needs_rerender
- High-severity issues (looping) → needs_rerender
- Medium issues → needs_operator_decision
- No issues → ready_for_operator
"""

import json
import os
import subprocess
import sqlite3
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asset_review import AssetReviewer


def _make_video_with_audio(path, duration=3, freq=440):
    """Create a video with audio."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
         "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", path],
        capture_output=True, timeout=30,
    )
    return path


def _make_silent_video(path, duration=3):
    """Create a video with silent audio track."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
         "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
         "-t", str(duration),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", path],
        capture_output=True, timeout=30,
    )
    return path


def _make_video_no_audio(path, duration=3):
    """Create a video with no audio stream."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        capture_output=True, timeout=30,
    )
    return path


class TestLoopingDetection:
    """Test the looping detection heuristic."""

    def test_detects_repeated_phrases(self, tmp_path):
        """Should flag when the same 5-word phrase appears 3+ times."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        transcript = "the quick brown fox jumps over the lazy dog " * 3
        assert reviewer._detect_looping(transcript) is True

    def test_no_looping_for_unique_text(self, tmp_path):
        """Should not flag unique text as looping."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        transcript = "the quick brown fox jumps over the lazy dog once upon a time"
        assert reviewer._detect_looping(transcript) is False

    def test_no_looping_for_short_text(self, tmp_path):
        """Should not flag short text as looping."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        assert reviewer._detect_looping("hello world") is False

    def test_no_looping_for_empty(self, tmp_path):
        """Should not flag empty transcript."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        assert reviewer._detect_looping("") is False


class TestAudioInspection:
    """ASSET-REVIEW-3: Audio inspection."""

    def test_no_audio_stream_passes(self, tmp_path):
        """Video with no audio stream should pass (nothing to inspect)."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video_no_audio(str(tmp_path / "video.mp4"))

        result = reviewer.run_audio_inspection(
            video, {"audio": {"original_audio": False}}, 1, 1)

        assert result["verdict"] == "pass"
        assert "No audio stream" in result["summary"]

    def test_silent_audio_when_expected_passes(self, tmp_path):
        """Silent audio when plan says no audio → pass."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        result = reviewer.run_audio_inspection(
            video, {"audio": {"original_audio": False, "music": {}}}, 1, 1)

        assert result["verdict"] == "pass"
        assert "silent as specified" in result["summary"]

    def test_silent_audio_when_audio_expected_flagged(self, tmp_path):
        """Silent audio when plan expects audio → issues_found."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        result = reviewer.run_audio_inspection(
            video, {"audio": {"original_audio": True}}, 1, 1)

        assert result["verdict"] == "issues_found"
        assert "silent" in result["summary"].lower()

    def test_non_silent_audio_no_speech_flagged(self, tmp_path):
        """Non-silent audio with no speech (ambient sound) → flagged.

        We mock whisper to return empty transcript — simulates ambient sound
        that whisper can't transcribe.
        """
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video_with_audio(str(tmp_path / "video.mp4"), freq=100)

        with patch.object(reviewer, '_transcribe_audio', return_value=""):
            result = reviewer.run_audio_inspection(
                video, {"audio": {"original_audio": False, "music": {}}}, 1, 1)

        assert result["verdict"] == "issues_found"
        assert "speech" in result["summary"].lower() or "ambient" in result["summary"].lower()

    def test_looping_audio_flagged(self, tmp_path):
        """Transcript with repeated phrases → looping flag."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video_with_audio(str(tmp_path / "video.mp4"))

        looping_transcript = "the biscuit tin is open now " * 4
        with patch.object(reviewer, '_transcribe_audio', return_value=looping_transcript):
            result = reviewer.run_audio_inspection(
                video, {"audio": {"original_audio": True}}, 1, 1)

        assert result["verdict"] == "issues_found"
        assert result["findings"]["is_looping"] is True

    def test_unexpected_audio_flagged(self, tmp_path):
        """Plan says no audio but transcript has speech → flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video_with_audio(str(tmp_path / "video.mp4"))

        with patch.object(reviewer, '_transcribe_audio',
                          return_value="this is some unexpected speech content"):
            result = reviewer.run_audio_inspection(
                video, {"audio": {"original_audio": False, "music": {}}}, 1, 1)

        assert result["verdict"] == "issues_found"
        assert any("speech" in w.lower() for w in result["findings"]["warnings"]), \
            f"Expected speech-related warning, got: {result['findings']['warnings']}"

    def test_provenance_logged(self, tmp_path):
        """Audio inspection should log to provenance."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        reviewer.run_audio_inspection(
            video, {"audio": {"original_audio": False}}, 1, 1, business_slug="test")

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%Audio inspection%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0

    def test_whisper_not_installed_degrades_gracefully(self, tmp_path):
        """If faster-whisper is not installed, should not crash."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video_with_audio(str(tmp_path / "video.mp4"))

        # _transcribe_audio returns empty string if whisper not installed
        with patch.object(reviewer, '_transcribe_audio', return_value=""):
            result = reviewer.run_audio_inspection(
                video, {"audio": {"original_audio": False, "music": {}}}, 1, 1)

        # Should flag "no speech detected" rather than crash
        assert result["status"] == "complete"
        assert result["verdict"] in ("pass", "issues_found")

    def test_vo_take_counts_as_expected_audio_without_whisper(self, tmp_path):
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video_with_audio(str(tmp_path / "video.mp4"))

        with patch.object(reviewer, '_transcribe_audio', return_value=None):
            result = reviewer.run_audio_inspection(
                video, {"audio": {"original_audio": False,
                                  "music": {}, "vo": {"take_id": "take-1"}}}, 1, 1)

        assert result["verdict"] == "pass"
        assert result["findings"]["expects_sound"] is True
        assert result["findings"]["transcription_available"] is False


class TestContentAlignment:
    """ASSET-REVIEW-4: Content alignment aggregation."""

    def test_all_pass_ready_for_operator(self, tmp_path):
        """All checks pass → ready_for_operator."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
            visual={"status": "complete", "verdict": "pass", "findings": {"issues": []}},
            audio={"status": "complete", "verdict": "pass", "findings": {}},
        )

        assert result["verdict"] == "ready_for_operator"
        assert "ready" in result["summary"].lower()

    def test_mechanical_warning_needs_operator_decision(self, tmp_path):
        """Mechanical warning → needs_operator_decision."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "issues_found", "warnings": ["Duration mismatch"]},
            visual=None,
            audio=None,
        )

        assert result["verdict"] == "needs_operator_decision"
        assert result["findings"]["issue_count"] == 1

    def test_looping_audio_needs_rerender(self, tmp_path):
        """High-severity issue (looping) → needs_rerender."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
            visual=None,
            audio={
                "status": "complete",
                "verdict": "issues_found",
                "findings": {"warnings": ["Audio appears to loop — the same phrase repeats"]},
            },
        )

        assert result["verdict"] == "needs_rerender"

    def test_visual_issues_aggregated(self, tmp_path):
        """Visual issues should be aggregated into the alignment verdict."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
            visual={
                "status": "complete",
                "verdict": "issues_found",
                "findings": {
                    "issues": [{
                        "severity": "high",
                        "category": "content_mismatch",
                        "description": "Frame 2 shows a phone, not a biscuit tin",
                        "recommended_action": "Regenerate segment 2",
                    }],
                },
            },
            audio=None,
        )

        assert result["verdict"] == "needs_rerender"
        assert result["findings"]["issue_count"] == 1

    def test_provenance_logged(self, tmp_path):
        """Alignment should log to provenance."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
            business_slug="test",
        )

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%Content alignment%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0

    def test_saved_to_db(self, tmp_path):
        """Alignment should be saved to asset_reviews table."""
        db = str(tmp_path / "test.db")
        reviewer = AssetReviewer({}, db_path=db)

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
        )

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_reviews WHERE review_type = 'alignment'",
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["verdict"] == "ready_for_operator"