"""VF-VS-602 — Beat-aware visual inspection.

AC: review frame selection derives from plan timing.
"""

import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from asset_review import AssetReviewer


@pytest.fixture
def reviewer(tmp_path):
    return AssetReviewer(models_config={}, db_path=str(tmp_path / "test.db"))


@pytest.fixture
def video_file(tmp_path):
    """Create a 6-second test video with a tone."""
    path = str(tmp_path / "test_video.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=6",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
         "-c:v", "libx264", "-c:a", "aac", "-shortest", path],
        capture_output=True, timeout=15,
    )
    assert os.path.exists(path), "Failed to create test video"
    return path


def test_beat_aware_keyframes_derived_from_vo_segments(reviewer, video_file, tmp_path):
    """AC: review frame selection derives from plan timing."""
    vo_segments = [
        {"beat_id": "b01", "duration": 2.0, "text": "first beat"},
        {"beat_id": "b02", "duration": 4.0, "text": "second beat"},
    ]
    out_dir = str(tmp_path / "keyframes")
    os.makedirs(out_dir, exist_ok=True)
    keyframes = reviewer._extract_beat_aware_keyframes(
        video_file, out_dir, vo_segments=vo_segments
    )
    # Should produce more than 5 (the old generic count) — first/middle/last per beat + cuts
    assert len(keyframes) > 5
    # All keyframe files should exist
    for idx, path in keyframes:
        assert os.path.exists(path)


def test_beat_aware_keyframes_derived_from_plan(reviewer, video_file, tmp_path):
    """Plan segments also work for beat-aware frame selection."""
    plan = {
        "segments": [
            {"source": "generated:1", "in": 0, "out": 2.0, "beat_id": "b01"},
            {"source": "generated:2", "in": 0, "out": 4.0, "beat_id": "b02"},
        ],
        "canvas": {},
    }
    out_dir = str(tmp_path / "keyframes")
    os.makedirs(out_dir, exist_ok=True)
    keyframes = reviewer._extract_beat_aware_keyframes(
        video_file, out_dir, plan=plan
    )
    assert len(keyframes) > 5


def test_falls_back_to_generic_when_no_plan(reviewer, video_file, tmp_path):
    """No plan or VO segments → generic 5-keyframe extraction."""
    out_dir = str(tmp_path / "keyframes")
    os.makedirs(out_dir, exist_ok=True)
    keyframes = reviewer._extract_beat_aware_keyframes(
        video_file, out_dir, plan=None, vo_segments=None
    )
    # Should fall back to generic (5 frames)
    assert len(keyframes) <= 6  # 5 or fewer (some may fail)


def test_beat_aware_keyframes_cover_each_beat(reviewer, video_file, tmp_path):
    """Each beat should have at least 3 frames (first/middle/last)."""
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "first"},
    ]
    out_dir = str(tmp_path / "keyframes")
    os.makedirs(out_dir, exist_ok=True)
    keyframes = reviewer._extract_beat_aware_keyframes(
        video_file, out_dir, vo_segments=vo_segments
    )
    # 3 frames for the beat (first/middle/last), no cuts (only 1 beat)
    assert len(keyframes) >= 3


def test_keyframes_include_cut_boundaries(reviewer, video_file, tmp_path):
    """With 2 beats, frames should include before/after the cut."""
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "first"},
        {"beat_id": "b02", "duration": 3.0, "text": "second"},
    ]
    out_dir = str(tmp_path / "keyframes")
    os.makedirs(out_dir, exist_ok=True)
    keyframes = reviewer._extract_beat_aware_keyframes(
        video_file, out_dir, vo_segments=vo_segments
    )
    # 3 frames per beat (6) + 2 cut frames = 8 (minus dedup)
    assert len(keyframes) >= 6


def test_live_visual_inspection_uses_exact_plan_for_beat_aware_frames(
    reviewer, video_file, tmp_path, monkeypatch
):
    """The production visual review must invoke beat-aware extraction."""
    plan = {
        "segments": [
            {"source": "generated:1", "in": 0, "out": 2.0, "beat_id": "b01"},
            {"source": "generated:2", "in": 0, "out": 4.0, "beat_id": "b02"},
        ],
    }
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    received = []
    reviewer.models_config = {
        "asset_review": {
            "enabled": True,
            "vision_model": "test-vision",
            "vision_api_key_env": "TEST_VISION_KEY",
        }
    }
    monkeypatch.setenv("TEST_VISION_KEY", "not-a-real-key")
    monkeypatch.setattr(
        reviewer,
        "_extract_beat_aware_keyframes",
        lambda path, output_dir, plan=None, vo_segments=None: (
            received.append(plan) or [(0, str(frame))]
        ),
    )
    monkeypatch.setattr(
        reviewer,
        "_call_vision_model",
        lambda *args, **kwargs: {
            "verdict": "pass",
            "issues": [],
            "summary": "Beat-aware frames match.",
        },
    )

    result = reviewer.run_visual_inspection(
        video_file,
        plan,
        "approved content",
        asset_id=1,
        media_id=1,
        business_slug="test-business",
    )

    assert result["verdict"] == "pass"
    assert received == [plan]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
