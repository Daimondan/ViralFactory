"""VF-VS-501 — Soundtrack plan contract.

AC: vo_only requires rationale + approval; music_bed requires licence + cost;
validation rejects silent VO-only.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from soundtrack_plan import (
    SOUNDTRACK_MODES,
    SOUNDTRACK_PLAN_SCHEMA,
    SOUNDTRACK_PLAN_VERSION,
    validate_soundtrack_plan,
    is_valid_soundtrack_plan,
    requires_operator_approval,
    is_approved,
    compute_soundtrack_plan_hash,
    make_vo_only_plan,
    make_music_bed_plan,
    SoundtrackPlanValidationError,
)


# ── Schema shape ─────────────────────────────────────────────────────────────


def test_modes_match_amendment_010():
    assert SOUNDTRACK_MODES == frozenset({
        "vo_only", "music_bed", "source_sound", "vo_plus_bed",
    })


def test_version_is_1():
    assert SOUNDTRACK_PLAN_VERSION == "1.0"


def test_schema_has_required_fields():
    required = SOUNDTRACK_PLAN_SCHEMA["required"]
    for f in ("contract_id", "mode", "sfx_cues", "operator_approval"):
        assert f in required


# ── AC: vo_only requires rationale + approval ────────────────────────────────


def test_vo_only_with_rationale_validates():
    plan = make_vo_only_plan("c001", "The VO is the full message; music would distract.")
    errors = validate_soundtrack_plan(plan)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_vo_only_without_rationale_rejected():
    """AC: validation rejects silent VO-only."""
    plan = make_vo_only_plan("c001", "")
    errors = validate_soundtrack_plan(plan)
    assert any("vo_only_rationale" in e for e in errors)


def test_vo_only_requires_approval():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    assert requires_operator_approval(plan) is True
    assert is_approved(plan) is False


def test_vo_only_approved_with_gate_token():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["operator_approval"] = "gate_token_abc"
    assert is_approved(plan) is True
    assert requires_operator_approval(plan) is False


# ── AC: music_bed requires licence + cost ────────────────────────────────────


def test_music_bed_with_licence_and_cost_validates():
    plan = make_music_bed_plan(
        "c001",
        source_id="bed_01",
        licence={"type": "royalty_free", "id": "RF-12345", "url": "https://example.com"},
        cost_usd=0.0,
    )
    errors = validate_soundtrack_plan(plan)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_music_bed_without_licence_rejected():
    plan = make_music_bed_plan("c001", "bed_01", licence=None, cost_usd=5.0)
    errors = validate_soundtrack_plan(plan)
    assert any("licence" in e for e in errors)


def test_music_bed_without_cost_rejected():
    plan = make_music_bed_plan(
        "c001", "bed_01",
        licence={"type": "royalty_free"}, cost_usd=None,
    )
    # cost_usd=None will be in the dict; check validation catches it
    plan["music_bed_ref"]["cost_usd"] = None
    errors = validate_soundtrack_plan(plan)
    assert any("cost_usd" in e for e in errors)


def test_music_bed_without_source_id_rejected():
    plan = make_music_bed_plan(
        "c001", "", licence={"type": "royalty_free"}, cost_usd=5.0,
    )
    errors = validate_soundtrack_plan(plan)
    assert any("source_id" in e for e in errors)


def test_vo_plus_bed_requires_music_bed_ref():
    plan = {
        "contract_id": "c001",
        "mode": "vo_plus_bed",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": None,
        "operator_approval": None,
    }
    errors = validate_soundtrack_plan(plan)
    assert any("music_bed_ref" in e for e in errors)


# ── source_sound mode ────────────────────────────────────────────────────────


def test_source_sound_with_rationale_validates():
    plan = {
        "contract_id": "c001",
        "mode": "source_sound",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": None,
        "source_sound_rationale": "On-location ambient sound is the point of the piece.",
        "operator_approval": None,
    }
    errors = validate_soundtrack_plan(plan)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_source_sound_without_rationale_rejected():
    plan = {
        "contract_id": "c001",
        "mode": "source_sound",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": None,
        "source_sound_rationale": None,
        "operator_approval": None,
    }
    errors = validate_soundtrack_plan(plan)
    assert any("source_sound_rationale" in e for e in errors)


# ── Ducking bounds ───────────────────────────────────────────────────────────


def test_ducking_attenuation_within_bounds():
    plan = make_music_bed_plan(
        "c001", "bed_01",
        licence={"type": "royalty_free"}, cost_usd=5.0,
        ducking={"attenuation_db": -12, "envelope": []},
    )
    errors = validate_soundtrack_plan(plan)
    assert errors == []


def test_ducking_attenuation_too_extreme_rejected():
    plan = make_music_bed_plan(
        "c001", "bed_01",
        licence={"type": "royalty_free"}, cost_usd=5.0,
        ducking={"attenuation_db": -40, "envelope": []},
    )
    errors = validate_soundtrack_plan(plan)
    assert any("attenuation_db" in e for e in errors)


# ── SFX cues ─────────────────────────────────────────────────────────────────


def test_sfx_cue_gain_out_of_bounds_rejected():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["sfx_cues"] = [{
        "event_id": "sfx_01",
        "source": "synth:pop",
        "timestamp": 1.5,
        "gain": 1.5,  # > 1.0
        "purpose": "accent",
    }]
    errors = validate_soundtrack_plan(plan)
    assert any("gain" in e for e in errors)


def test_sfx_cue_negative_timestamp_rejected():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["sfx_cues"] = [{
        "event_id": "sfx_01",
        "source": "synth:pop",
        "timestamp": -1.0,
        "gain": 0.5,
        "purpose": "accent",
    }]
    errors = validate_soundtrack_plan(plan)
    assert any("timestamp" in e for e in errors)


def test_sfx_cue_duplicate_event_id_rejected():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["sfx_cues"] = [
        {"event_id": "sfx_01", "source": "synth:pop", "timestamp": 1.0, "gain": 0.5, "purpose": "a"},
        {"event_id": "sfx_01", "source": "synth:pop", "timestamp": 2.0, "gain": 0.5, "purpose": "b"},
    ]
    errors = validate_soundtrack_plan(plan)
    assert any("duplicate" in e for e in errors)


# ── Invalid mode ─────────────────────────────────────────────────────────────


def test_invalid_mode_rejected():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    plan["mode"] = "silent"
    errors = validate_soundtrack_plan(plan)
    assert any("mode" in e for e in errors)


# ── Hash ─────────────────────────────────────────────────────────────────────


def test_hash_is_deterministic():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h1 = compute_soundtrack_plan_hash(plan)
    h2 = compute_soundtrack_plan_hash(plan)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


def test_hash_changes_when_mode_changes():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h1 = compute_soundtrack_plan_hash(plan)
    plan["mode"] = "music_bed"
    h2 = compute_soundtrack_plan_hash(plan)
    assert h1 != h2


# ── Helpers ──────────────────────────────────────────────────────────────────


def test_is_valid_helper():
    plan = make_vo_only_plan("c001", "Valid rationale.")
    assert is_valid_soundtrack_plan(plan) is True


def test_is_valid_helper_rejects_invalid():
    plan = make_vo_only_plan("c001", "")
    assert is_valid_soundtrack_plan(plan) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))