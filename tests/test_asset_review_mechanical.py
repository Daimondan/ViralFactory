"""Tests for ASSET-REVIEW-1: Mechanical post-render checks.

Per CORRECTION-final-output-review-and-audio-fix-v1.0:
- Mechanical checks run after every render (ffprobe, file size, duration, streams)
- Results saved to asset_reviews table
- Duration mismatch > 2s flagged as warning
- Missing audio stream when audio expected → flagged
- Resolution mismatch with canvas → flagged
- 0-byte file → flagged (defense in depth)
"""

import json
import os
import subprocess
import sqlite3
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asset_review import AssetReviewer, ASSET_REVIEW_SCHEMA


def _make_video(path, duration=3, with_audio=True, size="1080x1920"):
    """Create a test video file."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=30",
    ]
    if with_audio:
        cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"])
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", path])
    else:
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", path])
    subprocess.run(cmd, capture_output=True, timeout=30)
    return path


def _make_silent_video(path, duration=3, size="1080x1920"):
    """Create a video with a silent audio track."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=30",
         "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
         "-t", str(duration),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", path],
        capture_output=True, timeout=30,
    )
    return path


class TestMechanicalChecks:
    """ASSET-REVIEW-1: Mechanical post-render checks."""

    def test_table_created(self, tmp_path):
        """asset_reviews table should be created on init."""
        db = str(tmp_path / "test.db")
        reviewer = AssetReviewer({}, db_path=db)
        conn = sqlite3.connect(db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='asset_reviews'"
        ).fetchall()
        conn.close()
        assert len(tables) == 1, "asset_reviews table not created"

    def test_valid_video_passes(self, tmp_path):
        """A valid rendered video with matching plan should pass all checks."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "output.mp4"), duration=5, with_audio=True)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 5},
            "audio": {"original_audio": True},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        assert findings["file_exists"] is True
        assert findings["file_size_kb"] > 0
        assert findings["has_video_stream"] is True
        assert findings["has_audio_stream"] is True
        assert findings["resolution"] == [1080, 1920]
        assert findings["warnings"] == [], f"Unexpected warnings: {findings['warnings']}"

    def test_duration_mismatch_flagged(self, tmp_path):
        """Duration mismatch > 2s should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "output.mp4"), duration=5)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 18},
            "audio": {"original_audio": False},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        duration_warnings = [w for w in findings["warnings"] if "Duration mismatch" in w]
        assert len(duration_warnings) == 1, "Duration mismatch not flagged"

    def test_duration_within_tolerance_passes(self, tmp_path):
        """Duration within 2s tolerance should not be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "output.mp4"), duration=5)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 6},
            "audio": {"original_audio": False},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        duration_warnings = [w for w in findings["warnings"] if "Duration mismatch" in w]
        assert len(duration_warnings) == 0, "Duration within tolerance was incorrectly flagged"

    def test_resolution_mismatch_flagged(self, tmp_path):
        """Resolution mismatch with canvas should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "output.mp4"), duration=3, size="720x1280")

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": False},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        res_warnings = [w for w in findings["warnings"] if "Resolution mismatch" in w]
        assert len(res_warnings) == 1, "Resolution mismatch not flagged"

    def test_missing_audio_when_expected_flagged(self, tmp_path):
        """Audio expected but no audio stream should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "output.mp4"), duration=3, with_audio=False)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": True},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        audio_warnings = [w for w in findings["warnings"] if "no audio stream" in w]
        assert len(audio_warnings) == 1, "Missing audio when expected not flagged"

    def test_silent_audio_when_original_expected_flagged(self, tmp_path):
        """original_audio=true but output is silent should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "output.mp4"), duration=3)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": True},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        audio_warnings = [w for w in findings["warnings"] if "silent" in w.lower()]
        assert len(audio_warnings) == 1, "Silent audio when original expected not flagged"

    def test_unexpected_audio_flagged(self, tmp_path):
        """Plan says no audio but output has non-silent audio should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "output.mp4"), duration=3, with_audio=True)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": False, "music": {}},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        unexpected_warnings = [w for w in findings["warnings"] if "non-silent audio" in w]
        assert len(unexpected_warnings) == 1, "Unexpected audio not flagged"

    def test_silent_when_silent_expected_passes(self, tmp_path):
        """Plan says original_audio=false, output is silent → no audio warning."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "output.mp4"), duration=3)

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": False, "music": {}},
        }
        findings = reviewer.run_mechanical_checks(video, plan)

        audio_warnings = [w for w in findings["warnings"] if "audio" in w.lower()]
        assert len(audio_warnings) == 0, f"Silent output when silent expected was flagged: {audio_warnings}"

    def test_zero_byte_file_flagged(self, tmp_path):
        """0-byte file should be flagged (defense in depth)."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        empty_file = str(tmp_path / "empty.mp4")
        with open(empty_file, "w") as f:
            pass  # Create 0-byte file

        plan = {"canvas": {}, "audio": {}}
        findings = reviewer.run_mechanical_checks(empty_file, plan)

        size_warnings = [w for w in findings["warnings"] if "1KB" in w or "corrupt" in w]
        assert len(size_warnings) == 1, "0-byte file not flagged"

    def test_nonexistent_file_flagged(self, tmp_path):
        """Nonexistent file should be flagged."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        plan = {"canvas": {}, "audio": {}}
        findings = reviewer.run_mechanical_checks("/nonexistent/path.mp4", plan)

        assert findings["file_exists"] is False
        assert "Output file does not exist" in findings["warnings"]


class TestReviewSavedToDB:
    """Verify that review results are saved to the asset_reviews table."""

    def test_review_saved(self, tmp_path):
        """review_render should save a row to asset_reviews."""
        db = str(tmp_path / "test.db")
        reviewer = AssetReviewer({}, db_path=db)
        video = _make_video(str(tmp_path / "output.mp4"), duration=3, with_audio=True)

        # Set up asset_media table so we have a media_id
        conn = sqlite3.connect(db)
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

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": True},
        }
        result = reviewer.review_render(video, plan, asset_id=1, media_id=1)

        assert result["verdict"] in ("pass", "issues_found")
        assert result["review_id"] > 0

        # Verify it's in the DB
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_reviews WHERE id = ?",
            (result["review_id"],),
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["review_type"] == "mechanical"
        assert row["status"] == "complete"

    def test_provenance_logged(self, tmp_path):
        """review_render should log to provenance."""
        db = str(tmp_path / "test.db")
        reviewer = AssetReviewer({}, db_path=db)
        video = _make_video(str(tmp_path / "output.mp4"), duration=3, with_audio=True)

        # Create asset_media + provenance tables
        conn = sqlite3.connect(db)
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

        plan = {
            "canvas": {"resolution": "1080x1920", "duration_target": 3},
            "audio": {"original_audio": True},
        }
        reviewer.review_render(video, plan, asset_id=1, media_id=1, business_slug="test")

        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%Mechanical checks%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0, "Mechanical review not logged to provenance"


class TestReviewQueries:
    """Test the query helpers used by the UI."""

    def test_get_reviews_for_media(self, tmp_path):
        """get_reviews_for_media should return reviews for a specific media item."""
        db = str(tmp_path / "test.db")
        reviewer = AssetReviewer({}, db_path=db)
        video = _make_video(str(tmp_path / "output.mp4"), duration=3)

        conn = sqlite3.connect(db)
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

        plan = {"canvas": {"resolution": "1080x1920", "duration_target": 3}, "audio": {}}
        reviewer.review_render(video, plan, asset_id=1, media_id=1)

        reviews = reviewer.get_reviews_for_media(1)
        assert len(reviews) == 1
        assert reviews[0]["review_type"] == "mechanical"

    def test_get_latest_review_summary(self, tmp_path):
        """get_latest_review_summary should return the most relevant review."""
        db = str(tmp_path / "test.db")
        reviewer = AssetReviewer({}, db_path=db)
        video = _make_video(str(tmp_path / "output.mp4"), duration=3)

        conn = sqlite3.connect(db)
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

        plan = {"canvas": {"resolution": "1080x1920", "duration_target": 3}, "audio": {}}
        reviewer.review_render(video, plan, asset_id=1, media_id=1)

        summary = reviewer.get_latest_review_summary(1)
        assert summary is not None
        assert "verdict" in summary
        assert "summary" in summary