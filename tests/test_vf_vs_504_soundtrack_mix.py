"""VF-VS-504 — Soundtrack mix review.

AC: missing approved music/SFX fails; unapproved VO-only yields
needs_operator_decision.
"""

import os
import subprocess
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from services.render_review import RenderReviewService
from soundtrack_plan import make_vo_only_plan, make_music_bed_plan


@pytest.fixture
def service(tmp_path):
    return RenderReviewService(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def audio_file(tmp_path):
    """Create a 2-second audio file with a tone for ffprobe/volumedetect."""
    path = str(tmp_path / "test_audio.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:a", "aac", path],
        capture_output=True, timeout=10,
    )
    assert os.path.exists(path), "Failed to create test audio file"
    return path


# ── AC: missing approved music/SFX fails ─────────────────────────────────────


def test_music_bed_mode_without_music_bed_ref_fails(service, audio_file):
    """music_bed mode but music_bed_ref is missing → needs_operator_decision."""
    plan = make_music_bed_plan("c001", "bed_01", {"type": "royalty_free"}, 5.0)
    plan["music_bed_ref"] = None  # remove the ref
    plan["operator_approval"] = "gate_token"
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["verdict"] == "needs_operator_decision"
    assert any("music_bed_ref" in iss for iss in result["issues"])


def test_music_bed_mode_without_ducking_fails(service, audio_file):
    """music_bed mode but ducking missing → needs_operator_decision."""
    plan = make_music_bed_plan("c001", "bed_01", {"type": "royalty_free"}, 5.0)
    plan["ducking"] = None
    plan["operator_approval"] = "gate_token"
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["verdict"] == "needs_operator_decision"
    assert any("ducking" in iss for iss in result["issues"])


# ── AC: unapproved VO-only yields needs_operator_decision ────────────────────


def test_unapproved_vo_only_yields_needs_operator_decision(service, audio_file):
    """VO-only plan without operator_approval → needs_operator_decision."""
    plan = make_vo_only_plan("c001", "Valid rationale.")
    # operator_approval is None
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["verdict"] == "needs_operator_decision"
    assert any("operator_approval" in iss for iss in result["issues"])


def test_approved_vo_only_passes(service, audio_file):
    """VO-only plan with operator_approval → compliant."""
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["operator_approval"] = "gate_token_123"
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["verdict"] == "compliant"
    assert result["checks"]["vo_present"] is True


def test_approved_music_bed_passes(service, audio_file):
    """music_bed plan with ref + ducking + approval → compliant."""
    plan = make_music_bed_plan(
        "c001", "bed_01",
        {"type": "royalty_free", "id": "RF-123", "url": "https://example.com"},
        5.0,
        ducking={"attenuation_db": -12, "envelope": []},
    )
    plan["operator_approval"] = "gate_token_123"
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["verdict"] == "compliant"
    assert result["checks"]["music_present"] is True


# ── No audio stream ──────────────────────────────────────────────────────────


def test_no_audio_stream_fails(service, tmp_path):
    """A video file with no audio stream → needs_operator_decision."""
    path = str(tmp_path / "video_only.mp4")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=2",
         "-c:v", "libx264", "-an", path],
        capture_output=True, timeout=10,
    )
    assert os.path.exists(path)
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["operator_approval"] = "gate_token"
    result = service.check_soundtrack_mix(path, plan)
    assert result["verdict"] == "needs_operator_decision"
    assert any("No audio stream" in iss for iss in result["issues"])


# ── SFX presence ─────────────────────────────────────────────────────────────


def test_sfx_cues_marked_present(service, audio_file):
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["operator_approval"] = "gate_token"
    plan["sfx_cues"] = [
        {"event_id": "sfx_01", "source": "synth:pop", "timestamp": 1.0, "gain": 0.5, "purpose": "accent"},
    ]
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["checks"]["sfx_present"] is True


# ── vo_only with music_bed_ref deviation ─────────────────────────────────────


def test_vo_only_with_music_bed_ref_flagged(service, audio_file):
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["operator_approval"] = "gate_token"
    plan["music_bed_ref"] = {"source_id": "bed_01", "licence": {"type": "rf"}, "cost_usd": 0}
    result = service.check_soundtrack_mix(audio_file, plan)
    assert result["verdict"] == "needs_operator_decision"
    assert any("diverge" in iss for iss in result["issues"])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))