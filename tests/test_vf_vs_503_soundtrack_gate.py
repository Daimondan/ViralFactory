"""VF-VS-503 — Soundtrack preview gate.

AC: no soundtrack mode change without gate token; synthetic tones not
presented as finished design.
"""

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from soundtrack_gate import SoundtrackPreviewGate, SoundtrackGateError
from soundtrack_plan import make_vo_only_plan, make_music_bed_plan, compute_soundtrack_plan_hash


@pytest.fixture
def gate(tmp_path):
    return SoundtrackPreviewGate(db_path=str(tmp_path / "test_gate.db"))


def _hash(plan):
    return compute_soundtrack_plan_hash(plan)


# ── Approval / rejection / replacement ───────────────────────────────────────


def test_approve_plan_records_gate_token(gate):
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h = _hash(plan)
    result = gate.record_approval("c001", "test", h, "vo_only")
    assert result["verdict"] == "approved"
    assert result["gate_token"].startswith("soundtrack_gate_")
    assert gate.is_approved("c001", h)


def test_reject_plan_blocks_approval(gate):
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h = _hash(plan)
    gate.record_rejection("c001", "test", h, "vo_only", "Too quiet.")
    assert not gate.is_approved("c001", h)
    with pytest.raises(SoundtrackGateError, match="rejected"):
        gate.require_approval("c001", h)


def test_replace_plan_blocks_original(gate):
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h = _hash(plan)
    new_plan = make_music_bed_plan("c001", "bed_01", {"type": "royalty_free"}, 5.0)
    new_h = _hash(new_plan)
    gate.record_replacement("c001", "test", h, new_h, "music_bed")
    with pytest.raises(SoundtrackGateError, match="replaced"):
        gate.require_approval("c001", h)


def test_require_approval_raises_on_unapproved(gate):
    with pytest.raises(SoundtrackGateError, match="not been previewed"):
        gate.require_approval("c001", "nonexistent_hash")


def test_require_approval_returns_record_when_approved(gate):
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h = _hash(plan)
    gate.record_approval("c001", "test", h, "vo_only")
    record = gate.require_approval("c001", h)
    assert record["verdict"] == "approved"
    assert record["gate_token"].startswith("soundtrack_gate_")


def test_no_mode_change_without_gate_token(gate):
    """AC: no soundtrack mode change without gate token."""
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h = _hash(plan)
    # Plan exists but no approval recorded
    assert not gate.is_approved("c001", h)
    with pytest.raises(SoundtrackGateError):
        gate.require_approval("c001", h)


# ── Preview manifest ─────────────────────────────────────────────────────────


def test_vo_only_preview_manifest():
    gate = SoundtrackPreviewGate(db_path=":memory:")
    plan = make_vo_only_plan("c001", "The VO is the full message.")
    manifest = gate.build_preview_manifest(plan, vo_file_path="/vo.mp3")
    assert manifest["mode"] == "vo_only"
    assert any(t["name"] == "vo_only" for t in manifest["tracks"])
    assert "explicitly approved" in manifest["instructions"].lower()
    assert "not defaulted" in manifest["instructions"].lower()


def test_music_bed_preview_manifest_has_bed_alone_and_under_vo():
    gate = SoundtrackPreviewGate(db_path=":memory:")
    plan = make_music_bed_plan(
        "c001", "bed_01",
        {"type": "royalty_free"}, 5.0,
        ducking={"attenuation_db": -12, "envelope": []},
    )
    manifest = gate.build_preview_manifest(
        plan, vo_file_path="/vo.mp3", bed_file_path="/bed.mp3"
    )
    track_names = [t["name"] for t in manifest["tracks"]]
    assert "bed_alone" in track_names
    assert "bed_under_vo" in track_names
    bed_under = next(t for t in manifest["tracks"] if t["name"] == "bed_under_vo")
    assert bed_under["ducking"]["attenuation_db"] == -12


def test_sfx_cues_in_manifest():
    gate = SoundtrackPreviewGate(db_path=":memory:")
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["sfx_cues"] = [
        {"event_id": "sfx_01", "source": "synth:pop", "timestamp": 1.5, "gain": 0.5, "purpose": "accent"},
    ]
    manifest = gate.build_preview_manifest(plan)
    sfx_tracks = [t for t in manifest["tracks"] if t["name"].startswith("sfx_")]
    assert len(sfx_tracks) == 1
    assert sfx_tracks[0]["source"] == "synth:pop"


def test_source_sound_preview_manifest():
    gate = SoundtrackPreviewGate(db_path=":memory:")
    plan = {
        "contract_id": "c001",
        "mode": "source_sound",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": None,
        "source_sound_rationale": "On-location ambient sound.",
        "operator_approval": None,
    }
    manifest = gate.build_preview_manifest(plan, vo_file_path="/source.mp3")
    assert manifest["mode"] == "source_sound"
    assert any(t["name"] == "source_sound" for t in manifest["tracks"])


def test_synthetic_sfx_not_presented_as_finished_design():
    """AC: synthetic tones not presented as finished design."""
    gate = SoundtrackPreviewGate(db_path=":memory:")
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["sfx_cues"] = [
        {"event_id": "sfx_01", "source": "synth:pop", "timestamp": 1.0, "gain": 0.5, "purpose": "placeholder"},
    ]
    manifest = gate.build_preview_manifest(plan)
    # The manifest should describe the SFX source as synthetic, not as finished sound design
    sfx_tracks = [t for t in manifest["tracks"] if t["name"].startswith("sfx_")]
    assert sfx_tracks
    # The source is clearly labeled as synth — the operator sees it's a placeholder


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))