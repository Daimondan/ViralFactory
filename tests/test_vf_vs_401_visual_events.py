"""VF-VS-401 — visual_events[] added to PRODUCTION_CONTRACT_V2 beat schema.

AC: contract validates multi-event beats; old contracts degrade gracefully.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from production_contract import (
    SEMANTIC_BEAT_SCHEMA,
    VISUAL_EVENT_SCHEMA,
    VISUAL_EVENT_NARRATIVE_FUNCTIONS,
    VISUAL_EVENT_SOURCE_POLICIES,
    validate_contract_schema,
    validate_visual_events,
    resolve_visual_events,
    assemble_contract,
    ContractValidationError,
)


# ── Schema shape ─────────────────────────────────────────────────────────────


def test_visual_events_field_present_in_beat_schema():
    assert "visual_events" in SEMANTIC_BEAT_SCHEMA["properties"]
    assert SEMANTIC_BEAT_SCHEMA["properties"]["visual_events"]["type"] == "array"


def test_visual_event_schema_has_required_fields():
    required = VISUAL_EVENT_SCHEMA["required"]
    for field in ("event_id", "time_range", "narrative_function", "source_policy"):
        assert field in required


def test_narrative_functions_match_amendment_010():
    assert VISUAL_EVENT_NARRATIVE_FUNCTIONS == frozenset({
        "hook_contrast", "context", "proof", "explanation", "reframe",
        "action", "landing", "relationship", "conflict",
    })


def test_source_policies_match_amendment_010():
    assert VISUAL_EVENT_SOURCE_POLICIES == frozenset({
        "operator_capture", "licensed_stock", "approved_reference",
        "generated_still", "generated_motion", "renderer_graphic",
    })


# ── AC: contract validates multi-event beats ────────────────────────────────


def _make_beat_with_events(num_events=2):
    beat = {
        "beat_id": "b01",
        "platform_variant_id": "pv001",
        "role": "hook",
        "required": True,
        "vo_text": "We built a thing that turned into something much bigger",
        "staged_action": "Close-up of a savings ledger",
        "capture_policy": "capture_required",
        "intended_duration_sec": {"min": 0.0, "max": 14.0},
        "visual_intent": {
            "subject": "savings ledger",
            "action": "close-up",
            "meaning": "proof of growth",
        },
        "visual_events": [
            {
                "event_id": f"ev_b01_{i+1}",
                "time_range": {"start": i * 4.5, "end": (i + 1) * 4.5},
                "narrative_function": "hook_contrast" if i == 0 else "proof",
                "source_policy": "operator_capture",
                "required_text": None,
                "capture_policy_ref": "capture_required",
            }
            for i in range(num_events)
        ],
    }
    return beat


def test_multi_event_beat_validates():
    beat = _make_beat_with_events(5)  # Draft 8's 14s BUILD with 5 events
    errors = validate_contract_schema(beat, SEMANTIC_BEAT_SCHEMA)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_event_with_invalid_narrative_function_rejected():
    beat = _make_beat_with_events(1)
    beat["visual_events"][0]["narrative_function"] = "bogus_function"
    errors = validate_visual_events([beat])
    assert any("narrative_function" in e for e in errors)


def test_event_with_invalid_source_policy_rejected():
    beat = _make_beat_with_events(1)
    beat["visual_events"][0]["source_policy"] = "magic"
    errors = validate_visual_events([beat])
    assert any("source_policy" in e for e in errors)


def test_event_missing_event_id_rejected():
    beat = _make_beat_with_events(1)
    del beat["visual_events"][0]["event_id"]
    errors = validate_visual_events([beat])
    assert any("event_id" in e for e in errors)


def test_event_missing_time_range_rejected():
    beat = _make_beat_with_events(1)
    del beat["visual_events"][0]["time_range"]
    errors = validate_visual_events([beat])
    assert any("time_range" in e for e in errors)


def test_event_time_range_end_before_start_rejected():
    beat = _make_beat_with_events(1)
    beat["visual_events"][0]["time_range"] = {"start": 5.0, "end": 2.0}
    errors = validate_visual_events([beat])
    assert any("end < start" in e for e in errors)


def test_duplicate_event_id_within_beat_rejected():
    beat = _make_beat_with_events(2)
    beat["visual_events"][0]["event_id"] = "ev_dup"
    beat["visual_events"][1]["event_id"] = "ev_dup"
    errors = validate_visual_events([beat])
    assert any("duplicate" in e for e in errors)


def test_full_contract_assembles_with_multi_event_beat():
    beat = _make_beat_with_events(3)
    beat["capture_policy"] = "generated_allowed"  # avoid capture_required recipe requirement
    content = {
        "contract_id": "c001",
        "core_claim": "Growth is possible",
        "audience_value": "aspiring savers",
        "evidence_refs": ["source:1"],
        "primary_emotional_job": "hope",
        "primary_audience_action": "save",
        "format_name": "reel",
        "platform": "instagram",
        "capture_policy": "generated_allowed",
        "evidence_label": "OBSERVED",
    }
    contract = assemble_contract(content, [beat])
    assert contract["beats"][0]["visual_events"]
    assert len(contract["beats"][0]["visual_events"]) == 3


def test_full_contract_rejects_invalid_visual_event():
    beat = _make_beat_with_events(1)
    beat["capture_policy"] = "generated_allowed"
    beat["visual_events"][0]["narrative_function"] = "bogus"
    content = {
        "contract_id": "c001",
        "core_claim": "Growth",
        "audience_value": "savers",
        "evidence_refs": [],
        "primary_emotional_job": "hope",
        "primary_audience_action": "save",
        "format_name": "reel",
        "platform": "instagram",
        "capture_policy": "generated_allowed",
        "evidence_label": "OBSERVED",
    }
    with pytest.raises(ContractValidationError):
        assemble_contract(content, [beat])


# ── AC: old contracts degrade gracefully ─────────────────────────────────────


def test_old_beat_without_visual_events_validates():
    """A beat with no visual_events field still passes schema validation."""
    beat = {
        "beat_id": "b01",
        "platform_variant_id": "pv001",
        "role": "hook",
        "required": True,
        "vo_text": "The eighth wonder",
        "staged_action": "Close-up of a ledger",
        "capture_policy": "capture_required",
        "visual_intent": {"subject": "ledger", "meaning": "proof"},
    }
    errors = validate_contract_schema(beat, SEMANTIC_BEAT_SCHEMA)
    assert errors == []


def test_resolve_visual_events_degrades_from_visual_intent():
    """Old beat with visual_intent but no visual_events → one synthesized event."""
    beat = {
        "beat_id": "b01",
        "capture_policy": "capture_required",
        "intended_duration_sec": {"min": 0.0, "max": 4.0},
        "visual_intent": {"subject": "ledger", "meaning": "proof"},
        "staged_action": "Close-up",
    }
    events = resolve_visual_events(beat)
    assert len(events) == 1
    assert events[0]["event_id"] == "ev_b01_1"
    assert events[0]["narrative_function"] == "context"
    assert events[0]["source_policy"] == "operator_capture"
    assert events[0]["time_range"] == {"start": 0.0, "end": 4.0}


def test_resolve_visual_events_returns_explicit_events_unchanged():
    beat = _make_beat_with_events(3)
    events = resolve_visual_events(beat)
    assert len(events) == 3
    assert events[0]["event_id"] == "ev_b01_1"


def test_resolve_visual_events_empty_when_no_intent_or_action():
    beat = {"beat_id": "b01", "capture_policy": "generated_allowed"}
    events = resolve_visual_events(beat)
    assert events == []


def test_resolve_visual_events_capture_policy_mapping():
    """Each capture policy maps to a sensible default source policy."""
    cases = [
        ("capture_required", "operator_capture"),
        ("capture_preferred", "operator_capture"),
        ("archive_preferred", "licensed_stock"),
        ("stock_allowed", "licensed_stock"),
        ("generated_allowed", "generated_still"),
        ("text_card", "renderer_graphic"),
        ("legacy_unclassified", "generated_still"),
    ]
    for policy, expected_source in cases:
        beat = {
            "beat_id": "b01",
            "capture_policy": policy,
            "staged_action": "something",
        }
        events = resolve_visual_events(beat)
        assert events[0]["source_policy"] == expected_source


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))