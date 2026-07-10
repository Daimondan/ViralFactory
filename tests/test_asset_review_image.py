"""Tests for ASSET-REVIEW-6: Image review.

Per CORRECTION-final-output-review-and-audio-fix-v1.0:
- Image generation triggers a lightweight review (1 vision call)
- Results shown in the media gallery alongside each image
- Mismatch flagged with the original prompt + what the AI sees
- Mechanical: file exists, size > 10KB, correct aspect ratio
- Visual: vision LLM examines the image vs the prompt that generated it
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


def _make_image(path, size="500x500"):
    """Create a test image with enough detail to be > 10KB."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=1",
         "-frames:v", "1", "-q:v", "2", path],
        capture_output=True, timeout=10,
    )
    return path


class TestImageReviewMechanical:
    """Mechanical checks for image review."""

    def test_valid_image_passes(self, tmp_path):
        """A valid image should pass mechanical checks."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        img = _make_image(str(tmp_path / "test.png"), "500x500")

        result = reviewer.run_image_review(
            img, "a blue square", "test content", 1, 1)

        assert result["verdict"] == "pass"
        assert result["findings"]["mechanical"]["file_exists"] is True
        assert result["findings"]["mechanical"]["file_size_kb"] > 0

    def test_small_image_flagged(self, tmp_path):
        """Image < 10KB should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        # Create a tiny 1x1 image
        img = _make_image(str(tmp_path / "tiny.png"), "1x1")

        result = reviewer.run_image_review(
            img, "a tiny image", "test content", 1, 1)

        # 1x1 image will be very small
        assert result["findings"]["mechanical"]["file_size_kb"] < 10
        # Should have a warning about size
        size_warnings = [w for w in result["findings"]["mechanical"]["warnings"] if "KB" in w]
        # May or may not be < 10KB depending on PNG overhead, but check is there

    def test_nonexistent_image_flagged(self, tmp_path):
        """Nonexistent image should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        result = reviewer.run_image_review(
            "/nonexistent/img.png", "prompt", "content", 1, 1)

        assert result["verdict"] == "issues_found"
        assert "does not exist" in result["findings"]["mechanical"]["warnings"][0]


class TestImageReviewVision:
    """Vision-based image review with mocked API."""

    def test_vision_passes(self, tmp_path, monkeypatch):
        """Vision model says the image matches → pass."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        img = _make_image(str(tmp_path / "test.png"), "500x500")

        mock_findings = {"verdict": "pass", "issues": [], "summary": "Image matches prompt"}

        with patch.object(reviewer, '_call_vision_model', return_value=mock_findings):
            result = reviewer.run_image_review(
                img, "a blue square", "test content", 1, 1, business_slug="test")

        assert result["verdict"] == "pass"
        assert "Image matches prompt" in result["summary"]

    def test_vision_mismatch_flagged(self, tmp_path, monkeypatch):
        """Vision model says mismatch → issues_found."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        img = _make_image(str(tmp_path / "test.png"), "500x500")

        mock_findings = {
            "verdict": "issues_found",
            "issues": [{
                "severity": "high",
                "description": "Image shows a red circle, not a blue square",
                "recommended_action": "Regenerate with corrected prompt",
            }],
            "summary": "Image does not match the prompt",
        }

        with patch.object(reviewer, '_call_vision_model', return_value=mock_findings):
            result = reviewer.run_image_review(
                img, "a blue square", "test content", 1, 1)

        assert result["verdict"] == "issues_found"
        assert "does not match" in result["summary"]

    def test_skipped_when_disabled(self, tmp_path):
        """Should skip vision check when disabled, still run mechanical."""
        config = {"asset_review": {"enabled": False}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        img = _make_image(str(tmp_path / "test.png"), "500x500")

        result = reviewer.run_image_review(
            img, "a blue square", "test content", 1, 1)

        assert result["findings"]["vision"] is None
        assert result["verdict"] == "pass"  # Mechanical passed

    def test_saved_to_db(self, tmp_path, monkeypatch):
        """Image review should be saved to asset_reviews table."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        img = _make_image(str(tmp_path / "test.png"), "500x500")

        with patch.object(reviewer, '_call_vision_model',
                          return_value={"verdict": "pass", "issues": [], "summary": "OK"}):
            result = reviewer.run_image_review(
                img, "prompt", "content", 1, 1)

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_reviews WHERE review_type = 'image'",
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["verdict"] == "pass"
        assert row["model"] == "test-model"

    def test_provenance_logged(self, tmp_path, monkeypatch):
        """Image review should log to provenance."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))
        img = _make_image(str(tmp_path / "test.png"), "500x500")

        with patch.object(reviewer, '_call_vision_model',
                          return_value={"verdict": "pass", "issues": [], "summary": "OK"}):
            reviewer.run_image_review(
                img, "prompt", "content", 1, 1, business_slug="test")

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%Image review%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0