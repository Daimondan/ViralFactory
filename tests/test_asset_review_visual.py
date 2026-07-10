"""Tests for ASSET-REVIEW-2: Vision-based visual inspection.

Per CORRECTION-final-output-review-and-audio-fix-v1.0:
- Keyframes extracted via ffmpeg at 20%, 40%, 60%, 80% of duration (plus first frame)
- Vision-capable LLM called with keyframes + asset content + plan
- Results saved to provenance with full input/output
- Results displayed to operator in the assets UI alongside the video
- If the vision model is not configured, degrade gracefully
- Prompt file versioned (asset_review_v1.md), logged in provenance
"""

import json
import os
import subprocess
import sqlite3
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asset_review import AssetReviewer


def _make_video(path, duration=5, size="320x240"):
    """Create a test video file."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=30",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", path],
        capture_output=True, timeout=30,
    )
    return path


class TestKeyframeExtraction:
    """Test keyframe extraction from videos."""

    def test_extract_keyframes_5_frames(self, tmp_path):
        """Should extract 5 keyframes from a 5s video (0, 1, 2, 3, 4s)."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=5)
        keyframe_dir = str(tmp_path / "keyframes")
        os.makedirs(keyframe_dir, exist_ok=True)

        keyframes = reviewer._extract_keyframes(video, keyframe_dir, max_frames=5)

        assert len(keyframes) == 5
        for idx, path in keyframes:
            assert os.path.exists(path), f"Keyframe {idx} file missing"
            assert path.endswith(".jpg")

    def test_extract_keyframes_single_frame(self, tmp_path):
        """Should extract 1 keyframe (frame 0) when max_frames=1."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)
        keyframe_dir = str(tmp_path / "keyframes")
        os.makedirs(keyframe_dir, exist_ok=True)

        keyframes = reviewer._extract_keyframes(video, keyframe_dir, max_frames=1)

        assert len(keyframes) == 1
        assert keyframes[0][0] == 0  # first frame

    def test_extract_keyframes_empty_for_invalid_video(self, tmp_path):
        """Should return empty list for a non-existent video."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        keyframes = reviewer._extract_keyframes("/nonexistent.mp4", str(tmp_path), 5)
        assert keyframes == []


class TestImageEncoding:
    """Test base64 encoding of images."""

    def test_encode_image_b64(self, tmp_path):
        """Should encode an image as a data URL."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        # Create a small test image
        img_path = str(tmp_path / "test.jpg")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=10x10:d=1",
             "-frames:v", "1", img_path],
            capture_output=True, timeout=10,
        )
        data_url = reviewer._encode_image_b64(img_path)
        assert data_url.startswith("data:image/jpeg;base64,")
        assert len(data_url) > 50  # Should have actual base64 data


class TestVisualInspectionGracefulDegradation:
    """Test that visual inspection degrades gracefully when not configured."""

    def test_skipped_when_disabled(self, tmp_path):
        """Should skip when asset_review.enabled = false."""
        config = {"asset_review": {"enabled": False}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)

        result = reviewer.run_visual_inspection(
            video, {"segments": []}, "test content", 1, 1)

        assert result["status"] == "skipped"
        assert result["verdict"] == "skipped"

    def test_skipped_when_no_api_key(self, tmp_path, monkeypatch):
        """Should skip when API key is not set."""
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)

        result = reviewer.run_visual_inspection(
            video, {"segments": []}, "test content", 1, 1)

        assert result["status"] == "skipped"
        assert "not configured" in result["summary"].lower() or "not set" in result["summary"].lower()

    def test_skipped_when_no_model_configured(self, tmp_path, monkeypatch):
        """Should skip when no vision_model is configured."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)

        result = reviewer.run_visual_inspection(
            video, {"segments": []}, "test content", 1, 1)

        assert result["status"] == "skipped"


class TestVisualInspectionWithMockedAPI:
    """Test visual inspection with mocked vision API calls."""

    def test_vision_call_succeeds(self, tmp_path, monkeypatch):
        """Full visual inspection with mocked API should save results."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {
            "asset_review": {
                "enabled": True,
                "vision_model": "test-vision-model",
                "vision_api_key_env": "OPENROUTER_API_KEY",
                "max_keyframes": 3,
            }
        }
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)

        # Set up asset_media table
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER, kind TEXT, path TEXT,
                model TEXT, prompt TEXT, cost_usd REAL, created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO asset_media (asset_id, kind, path, model, prompt, cost_usd, created_at) "
            "VALUES (1, 'final_cut', ?, 'ffmpeg', '', NULL, '2026-01-01')",
            (video,),
        )
        conn.commit()
        conn.close()

        # Mock the vision API call
        mock_findings = {
            "verdict": "pass",
            "issues": [],
            "summary": "All 3 frames match the script. No issues found.",
        }

        with patch.object(reviewer, '_call_vision_model', return_value=mock_findings):
            result = reviewer.run_visual_inspection(
                video,
                {"segments": [{"source": "generated:1", "in": 0, "out": 3}]},
                "This is a test script about biscuit tins",
                asset_id=1, media_id=1, business_slug="test",
            )

        assert result["status"] == "complete"
        assert result["verdict"] == "pass"
        assert result["review_id"] > 0

        # Verify saved to DB
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_reviews WHERE review_type = 'visual'",
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["verdict"] == "pass"
        assert row["model"] == "test-vision-model"
        assert row["prompt_file"] == "assembly/asset_review_v1.md"

    def test_vision_call_fails_gracefully(self, tmp_path, monkeypatch):
        """Vision API failure should return issues_found, not crash."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {
            "asset_review": {
                "enabled": True,
                "vision_model": "test-vision-model",
                "max_keyframes": 2,
            }
        }
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)

        with patch.object(reviewer, '_call_vision_model',
                          side_effect=Exception("API timeout")):
            result = reviewer.run_visual_inspection(
                video, {"segments": []}, "test content", 1, 1)

        assert result["status"] == "failed"
        assert result["verdict"] == "issues_found"
        assert "API" in result["summary"] or "timeout" in result["summary"].lower()

    def test_provenance_logged(self, tmp_path, monkeypatch):
        """Visual inspection should log to provenance."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {
            "asset_review": {
                "enabled": True,
                "vision_model": "test-vision-model",
                "max_keyframes": 2,
            }
        }
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "video.mp4"), duration=3)

        # Set up asset_media table
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER, kind TEXT, path TEXT,
                model TEXT, prompt TEXT, cost_usd REAL, created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO asset_media (asset_id, kind, path, model, prompt, cost_usd, created_at) "
            "VALUES (1, 'final_cut', ?, 'ffmpeg', '', NULL, '2026-01-01')",
            (video,),
        )
        conn.commit()
        conn.close()

        mock_findings = {"verdict": "issues_found", "issues": [], "summary": "Test"}

        with patch.object(reviewer, '_call_vision_model', return_value=mock_findings):
            reviewer.run_visual_inspection(
                video, {"segments": []}, "test content",
                asset_id=1, media_id=1, business_slug="test",
            )

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%Visual inspection%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0, "Visual inspection not logged to provenance"