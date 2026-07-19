"""VF-VS-402 — Visual Director process: prompt + schema + validator + registry.

AC: schema-validated, provenance-logged, no audience copy, no tenant strings,
registered in Process Registry with playbook_type: production.
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from pipeline import VISUAL_DIRECTOR_SCHEMA  # noqa: E402
from production_contract import (  # noqa: E402
    VISUAL_EVENT_NARRATIVE_FUNCTIONS,
    VISUAL_EVENT_SOURCE_POLICIES,
    validate_visual_events,
)
from process_engine import load_process_registry  # noqa: E402


def _validate_visual_director_output(output: dict) -> list[str]:
    """Validate the top-level shape + recurse into visual_events."""
    errors: list[str] = []
    if "beats" not in output:
        errors.append("Missing required field: beats")
        return errors
    beats = output["beats"]
    if not isinstance(beats, list) or not beats:
        errors.append("beats must be a non-empty array")
        return errors
    # Reuse the production_contract visual_events validator for each beat
    errors.extend(validate_visual_events(beats))
    # Check beat_id presence
    for i, beat in enumerate(beats):
        if "beat_id" not in beat or not beat["beat_id"]:
            errors.append(f"beats[{i}]: missing beat_id")
        if "visual_events" not in beat or not beat["visual_events"]:
            errors.append(f"beats[{i}]: missing or empty visual_events")
    return errors


# ── Schema shape ─────────────────────────────────────────────────────────────


def test_visual_director_schema_has_required_top_level():
    assert "beats" in VISUAL_DIRECTOR_SCHEMA["required"]
    assert VISUAL_DIRECTOR_SCHEMA["properties"]["beats"]["type"] == "array"
    assert VISUAL_DIRECTOR_SCHEMA["properties"]["beats"]["minItems"] == 1


def test_visual_director_event_enums_match_contract():
    """The schema's narrative_function and source_policy enums must match the
    production contract's VISUAL_EVENT_* enums."""
    event_props = (
        VISUAL_DIRECTOR_SCHEMA["properties"]["beats"]["items"]
        ["properties"]["visual_events"]["items"]["properties"]
    )
    assert set(event_props["narrative_function"]["enum"]) == set(VISUAL_EVENT_NARRATIVE_FUNCTIONS)
    assert set(event_props["source_policy"]["enum"]) == set(VISUAL_EVENT_SOURCE_POLICIES)


def test_valid_visual_director_output_passes_schema():
    output = {
        "beats": [
            {
                "beat_id": "b01",
                "visual_events": [
                    {
                        "event_id": "ev_b01_1",
                        "time_range": {"start": 0.0, "end": 4.5},
                        "narrative_function": "hook_contrast",
                        "source_policy": "operator_capture",
                        "required_text": None,
                        "capture_policy_ref": "capture_required",
                    },
                    {
                        "event_id": "ev_b01_2",
                        "time_range": {"start": 4.5, "end": 14.0},
                        "narrative_function": "proof",
                        "source_policy": "operator_capture",
                        "required_text": None,
                        "capture_policy_ref": "capture_required",
                    },
                ],
            }
        ]
    }
    errors = _validate_visual_director_output(output)
    assert errors == [], f"Expected no errors, got: {errors}"


def test_invalid_narrative_function_rejected():
    output = {
        "beats": [{
            "beat_id": "b01",
            "visual_events": [{
                "event_id": "ev_b01_1",
                "time_range": {"start": 0.0, "end": 4.0},
                "narrative_function": "bogus",
                "source_policy": "operator_capture",
            }],
        }]
    }
    errors = _validate_visual_director_output(output)
    assert any("narrative_function" in e for e in errors)


def test_missing_beats_rejected():
    errors = _validate_visual_director_output({})
    assert any("beats" in e for e in errors)


def test_empty_beats_rejected():
    output = {"beats": []}
    errors = _validate_visual_director_output(output)
    assert len(errors) > 0


def test_beat_missing_visual_events_rejected():
    output = {"beats": [{"beat_id": "b01"}]}
    errors = _validate_visual_director_output(output)
    assert any("visual_events" in e for e in errors)


# ── Prompt file ──────────────────────────────────────────────────────────────


def _prompt_path():
    return os.path.join(ROOT, "prompts", "assembly", "visual_director_v1.md")


def test_prompt_file_exists():
    assert os.path.exists(_prompt_path()), "visual_director_v1.md must exist"


def test_prompt_file_has_version():
    content = open(_prompt_path()).read()
    assert "version:" in content
    assert "1.1" in content


def test_prompt_file_has_no_tenant_strings():
    """No brand names, no domain-specific terms."""
    content = open(_prompt_path()).read().lower()
    forbidden = ["stackpenni", "penni", "caribbean", "barbados", "fitzroy", "stackwell"]
    for word in forbidden:
        assert word not in content, (
            f"Tenant string '{word}' found in Visual Director prompt — must be generic"
        )


def test_prompt_file_has_no_provider_names():
    """No provider/backend names (word-boundary match to avoid false hits)."""
    content = open(_prompt_path()).read().lower()
    forbidden = ["fal", "kling", "veo", "openai", "anthropic", "elevenlabs"]
    for word in forbidden:
        # Word-boundary regex so 'fal' doesn't match 'false'
        assert not re.search(r"\b" + re.escape(word) + r"\b", content), (
            f"Provider name '{word}' found in Visual Director prompt"
        )


def test_prompt_file_states_assembler_side_boundary():
    content = open(_prompt_path()).read().lower()
    assert "assembler" in content
    assert "not audience copy" in content or "no audience copy" in content


# ── Process Registry ─────────────────────────────────────────────────────────


def test_visual_director_registered_in_process_registry():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    assert "visual_director_v1" in registry["processes"], (
        "visual_director_v1 must be registered in config/processes.yaml"
    )


def test_visual_director_registry_entry_has_correct_fields():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    proc = registry["processes"]["visual_director_v1"]
    assert proc["prompt_file"] == "assembly/visual_director_v1.md"
    assert proc["schema"] == "VISUAL_DIRECTOR_SCHEMA"
    assert proc["backend"] == "drafter"


def test_visual_director_has_playbook_type_production():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    proc = registry["processes"]["visual_director_v1"]
    assert proc.get("playbook_type") == "production", (
        "Visual Director must have playbook_type: production per AMENDMENT-010"
    )


def test_visual_director_not_marked_retired():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    proc = registry["processes"]["visual_director_v1"]
    assert not proc.get("retired", False)


def test_visual_director_schema_resolves():
    """The schema reference in processes.yaml must resolve to the Python schema."""
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    from process_engine import _resolve_schema
    schema = _resolve_schema("VISUAL_DIRECTOR_SCHEMA", registry)
    assert schema is VISUAL_DIRECTOR_SCHEMA


def test_visual_director_inputs_include_contract_beats_and_vo_timeline():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    inputs = registry["processes"]["visual_director_v1"]["inputs"]
    assert "contract_beats" in inputs
    assert "vo_timeline" in inputs
    assert "visual_style" in inputs


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))