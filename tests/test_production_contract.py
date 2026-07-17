"""
Tests for Production Contract v2 schemas (VF-AU-101).

The production contract is the versioned, stable structure that carries
approved content, semantic beats, text intents, media recipes, edit segments,
compliance, and performance data through the entire Assembler pipeline.

Per AMENDMENT-009:
- Stable IDs: contract_id, platform_variant_id, beat_id, text_intent_id,
  media_recipe_id, ingredient_id, segment_id.
- Capture policy per beat (capture_required, capture_preferred, archive_preferred,
  stock_allowed, generated_allowed, text_card).
- Hash-lock covers the full Writer contract layer (not just platform_content).
"""

import json
import hashlib
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_contract import (
    PRODUCTION_CONTRACT_V2_SCHEMA,
    CONTENT_CONTRACT_SCHEMA,
    SEMANTIC_BEAT_SCHEMA,
    TEXT_INTENT_SCHEMA,
    MEDIA_RECIPE_SCHEMA,
    EDIT_SEGMENT_SCHEMA,
    CAPTURE_POLICIES,
    EVIDENCE_LABELS,
    validate_contract_schema,
    compute_writer_contract_hash,
    ContractValidationError,
)


# ── Schema shape tests ──────────────────────────────────────────────────────

class TestSchemaShape:
    """The schemas must have the required fields and correct types."""

    def test_content_contract_has_required_fields(self):
        required = CONTENT_CONTRACT_SCHEMA["required"]
        assert "contract_id" in required
        assert "core_claim" in required
        assert "audience_value" in required
        assert "evidence_refs" in required
        assert "primary_emotional_job" in required
        assert "primary_audience_action" in required
        assert "format_name" in required
        assert "platform" in required
        assert "capture_policy" in required
        assert "evidence_label" in required

    def test_beat_has_stable_id_and_required_fields(self):
        required = SEMANTIC_BEAT_SCHEMA["required"]
        assert "beat_id" in required
        assert "platform_variant_id" in required
        assert "role" in required
        assert "required" in required
        assert "vo_text" in required
        assert "staged_action" in required

    def test_text_intent_has_stable_id(self):
        required = TEXT_INTENT_SCHEMA["required"]
        assert "text_intent_id" in required
        assert "beat_id" in required
        assert "function" in required

    def test_media_recipe_has_stable_id_and_beat_ref(self):
        required = MEDIA_RECIPE_SCHEMA["required"]
        assert "media_recipe_id" in required
        assert "beat_id" in required
        assert "media_function" in required
        assert "source_policy" in required

    def test_edit_segment_has_stable_id_and_beat_ref(self):
        required = EDIT_SEGMENT_SCHEMA["required"]
        assert "segment_id" in required
        assert "beat_ids" in required
        assert "source" in required

    def test_capture_policies_include_all_from_amendment_009(self):
        assert "capture_required" in CAPTURE_POLICIES
        assert "capture_preferred" in CAPTURE_POLICIES
        assert "archive_preferred" in CAPTURE_POLICIES
        assert "stock_allowed" in CAPTURE_POLICIES
        assert "generated_allowed" in CAPTURE_POLICIES
        assert "text_card" in CAPTURE_POLICIES
        assert "legacy_unclassified" in CAPTURE_POLICIES

    def test_evidence_labels_match_viral_patterns(self):
        assert "OBSERVED" in EVIDENCE_LABELS
        assert "MEASURED" in EVIDENCE_LABELS
        assert "HYPOTHESIS" in EVIDENCE_LABELS
        assert "HOUSE_RULE" in EVIDENCE_LABELS


# ── Schema validation tests ─────────────────────────────────────────────────

class TestSchemaValidation:
    """validate_contract_schema must reject malformed contracts."""

    def test_valid_content_contract_passes(self):
        contract = {
            "contract_id": "c001",
            "core_claim": "Compound interest is the eighth wonder",
            "audience_value": "Understand how saving early compounds",
            "evidence_refs": ["source:14", "capture:22"],
            "primary_emotional_job": "conviction",
            "primary_audience_action": "save",
            "format_name": "reel",
            "platform": "instagram",
            "capture_policy": "capture_required",
            "authenticity_anchor": "real receipt from first savings",
            "performance_hypothesis": "Proof-first treatment may drive saves",
            "evidence_label": "HYPOTHESIS",
        }
        errors = validate_contract_schema(contract, CONTENT_CONTRACT_SCHEMA)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_missing_id_fails(self):
        contract = {
            "contract_id": "",  # empty ID
            "core_claim": "test",
            "audience_value": "test",
            "evidence_refs": [],
            "primary_emotional_job": "conviction",
            "primary_audience_action": "save",
            "format_name": "reel",
            "platform": "instagram",
            "capture_policy": "capture_required",
            "evidence_label": "HYPOTHESIS",
        }
        errors = validate_contract_schema(contract, CONTENT_CONTRACT_SCHEMA)
        assert len(errors) > 0
        assert any("contract_id" in e for e in errors)

    def test_invalid_capture_policy_fails(self):
        contract = {
            "contract_id": "c001",
            "core_claim": "test",
            "audience_value": "test",
            "evidence_refs": [],
            "primary_emotional_job": "conviction",
            "primary_audience_action": "save",
            "format_name": "reel",
            "platform": "instagram",
            "capture_policy": "capture_made_up",
            "evidence_label": "HYPOTHESIS",
        }
        errors = validate_contract_schema(contract, CONTENT_CONTRACT_SCHEMA)
        assert len(errors) > 0
        assert any("capture_policy" in e for e in errors)

    def test_invalid_evidence_label_fails(self):
        contract = {
            "contract_id": "c001",
            "core_claim": "test",
            "audience_value": "test",
            "evidence_refs": [],
            "primary_emotional_job": "conviction",
            "primary_audience_action": "save",
            "format_name": "reel",
            "platform": "instagram",
            "capture_policy": "capture_required",
            "evidence_label": "GUESS",
        }
        errors = validate_contract_schema(contract, CONTENT_CONTRACT_SCHEMA)
        assert len(errors) > 0
        assert any("evidence_label" in e for e in errors)

    def test_valid_beat_passes(self):
        beat = {
            "beat_id": "b01",
            "platform_variant_id": "pv001",
            "role": "hook",
            "required": True,
            "vo_text": "The eighth wonder of the world",
            "register": "authoritative",
            "evidence_refs": ["source:14"],
            "intended_duration_sec": {"min": 2.0, "max": 4.0},
            "viewer_state_before": "curious",
            "viewer_state_after": "engaged",
            "staged_action": "Close-up of a savings ledger",
            "capture_policy": "capture_required",
        }
        errors = validate_contract_schema(beat, SEMANTIC_BEAT_SCHEMA)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_beat_missing_id_fails(self):
        beat = {
            "beat_id": "",
            "platform_variant_id": "pv001",
            "role": "hook",
            "required": True,
            "vo_text": "test",
            "staged_action": "test",
            "capture_policy": "capture_required",
        }
        errors = validate_contract_schema(beat, SEMANTIC_BEAT_SCHEMA)
        assert len(errors) > 0
        assert any("beat_id" in e for e in errors)

    def test_beat_duplicate_id_detected(self):
        """Duplicate beat IDs within a contract must be flagged."""
        beats = [
            {"beat_id": "b01", "platform_variant_id": "pv001", "role": "hook",
             "required": True, "vo_text": "test1", "staged_action": "test",
             "capture_policy": "capture_required"},
            {"beat_id": "b01", "platform_variant_id": "pv001", "role": "setup",
             "required": True, "vo_text": "test2", "staged_action": "test",
             "capture_policy": "capture_preferred"},
        ]
        from production_contract import find_duplicate_ids
        dupes = find_duplicate_ids(beats, "beat_id")
        assert "b01" in dupes

    def test_segment_references_unknown_beat(self):
        """A segment referencing an unknown beat_id must be flagged."""
        from production_contract import validate_segment_beat_references
        beats = [{"beat_id": "b01"}, {"beat_id": "b02"}]
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:1"},
            {"segment_id": "s02", "beat_ids": ["b99"], "source": "upload:2"},  # unknown beat
        ]
        errors = validate_segment_beat_references(segments, beats)
        assert len(errors) == 1
        assert "b99" in errors[0]

    def test_recipe_references_unknown_beat(self):
        """A media recipe referencing an unknown beat_id must be flagged."""
        from production_contract import validate_recipe_beat_references
        beats = [{"beat_id": "b01"}, {"beat_id": "b02"}]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "capture_required"},
            {"media_recipe_id": "r02", "beat_id": "b99", "media_function": "context",
             "source_policy": "stock_allowed"},  # unknown beat
        ]
        errors = validate_recipe_beat_references(recipes, beats)
        assert len(errors) == 1
        assert "b99" in errors[0]

    def test_text_intent_references_unknown_beat(self):
        """A text intent referencing an unknown beat_id must be flagged."""
        from production_contract import validate_text_intent_beat_references
        beats = [{"beat_id": "b01"}, {"beat_id": "b02"}]
        intents = [
            {"text_intent_id": "t01", "beat_id": "b01", "function": "hook", "text": "test"},
            {"text_intent_id": "t02", "beat_id": "b99", "function": "caption", "text": "test"},  # unknown
        ]
        errors = validate_text_intent_beat_references(intents, beats)
        assert len(errors) == 1
        assert "b99" in errors[0]

    def test_required_capture_cannot_resolve_to_generated(self):
        """capture_required beat mapped to generated media must fail."""
        from production_contract import validate_capture_policy_consistency
        beats = [
            {"beat_id": "b01", "capture_policy": "capture_required"},
            {"beat_id": "b02", "capture_policy": "generated_allowed"},
        ]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "source_policy": "capture_required",
             "primary": {"kind": "generated_image"}},  # VIOLATION
            {"media_recipe_id": "r02", "beat_id": "b02", "source_policy": "generated_allowed",
             "primary": {"kind": "generated_image"}},  # OK
        ]
        errors = validate_capture_policy_consistency(beats, recipes)
        assert len(errors) == 1
        assert "b01" in errors[0]

    def test_capture_required_blocks_when_missing_recipe(self):
        """A capture_required beat with no recipe must be flagged."""
        from production_contract import validate_capture_policy_consistency
        beats = [
            {"beat_id": "b01", "capture_policy": "capture_required"},
        ]
        recipes = []  # no recipe for b01
        errors = validate_capture_policy_consistency(beats, recipes)
        assert len(errors) == 1
        assert "b01" in errors[0]

    def test_unsupported_evidence_label_rejected(self):
        """Evidence labels must match the allowed set."""
        contract = {
            "contract_id": "c001",
            "core_claim": "test",
            "audience_value": "test",
            "evidence_refs": [],
            "primary_emotional_job": "conviction",
            "primary_audience_action": "save",
            "format_name": "reel",
            "platform": "instagram",
            "capture_policy": "capture_required",
            "evidence_label": "DEFINITELY_TRUE",
        }
        errors = validate_contract_schema(contract, CONTENT_CONTRACT_SCHEMA)
        assert any("evidence_label" in e for e in errors)

    def test_no_positional_fallback_in_segment(self):
        """Segments must use beat_ids, not positional indices."""
        from production_contract import validate_no_positional_fallback
        segments_ok = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:1"},
        ]
        segments_bad = [
            {"segment_id": "s01", "beat_ids": [], "source": "upload:1", "position": 0},
        ]
        assert validate_no_positional_fallback(segments_ok) == []
        errors = validate_no_positional_fallback(segments_bad)
        assert len(errors) > 0


# ── Hash-lock tests ──────────────────────────────────────────────────────────

class TestWriterContractHash:
    """The hash-lock must cover the full Writer contract (AMENDMENT-009 Condition 4)."""

    def test_hash_is_deterministic(self):
        writer_contract = {
            "platform_content": [{"platform": "instagram", "content": "test"}],
            "beats": [{"beat_id": "b01", "vo_text": "hello"}],
            "primary_audience_action": "save",
            "capture_policy": "capture_required",
        }
        h1 = compute_writer_contract_hash(writer_contract)
        h2 = compute_writer_contract_hash(writer_contract)
        assert h1 == h2

    def test_hash_changes_when_content_changes(self):
        c1 = {"platform_content": [{"platform": "x", "content": "A"}], "beats": [], "primary_audience_action": "save", "capture_policy": "capture_required"}
        c2 = {"platform_content": [{"platform": "x", "content": "B"}], "beats": [], "primary_audience_action": "save", "capture_policy": "capture_required"}
        assert compute_writer_contract_hash(c1) != compute_writer_contract_hash(c2)

    def test_hash_changes_when_beat_vo_text_changes(self):
        c1 = {"platform_content": [], "beats": [{"beat_id": "b01", "vo_text": "A"}], "primary_audience_action": "save", "capture_policy": "capture_required"}
        c2 = {"platform_content": [], "beats": [{"beat_id": "b01", "vo_text": "B"}], "primary_audience_action": "save", "capture_policy": "capture_required"}
        assert compute_writer_contract_hash(c1) != compute_writer_contract_hash(c2)

    def test_hash_changes_when_capture_policy_changes(self):
        c1 = {"platform_content": [], "beats": [], "primary_audience_action": "save", "capture_policy": "capture_required"}
        c2 = {"platform_content": [], "beats": [], "primary_audience_action": "save", "capture_policy": "capture_preferred"}
        assert compute_writer_contract_hash(c1) != compute_writer_contract_hash(c2)

    def test_hash_changes_when_audience_action_changes(self):
        c1 = {"platform_content": [], "beats": [], "primary_audience_action": "save", "capture_policy": "capture_required"}
        c2 = {"platform_content": [], "beats": [], "primary_audience_action": "share", "capture_policy": "capture_required"}
        assert compute_writer_contract_hash(c1) != compute_writer_contract_hash(c2)

    def test_hash_changes_when_evidence_refs_change(self):
        c1 = {"platform_content": [], "beats": [{"beat_id": "b01", "vo_text": "x", "evidence_refs": ["source:1"]}], "primary_audience_action": "save", "capture_policy": "capture_required"}
        c2 = {"platform_content": [], "beats": [{"beat_id": "b01", "vo_text": "x", "evidence_refs": ["source:2"]}], "primary_audience_action": "save", "capture_policy": "capture_required"}
        assert compute_writer_contract_hash(c1) != compute_writer_contract_hash(c2)

    def test_hash_returns_sha256_hex(self):
        h = compute_writer_contract_hash({"platform_content": [], "beats": [], "primary_audience_action": "save", "capture_policy": "capture_required"})
        assert len(h) == 64  # SHA-256 hex
        int(h, 16)  # valid hex


# ── Full contract assembly test ──────────────────────────────────────────────

class TestFullContractAssembly:
    """The complete production contract must assemble all layers correctly."""

    def test_full_contract_has_all_layers(self):
        from production_contract import assemble_contract
        contract = assemble_contract(
            content_contract={
                "contract_id": "c001",
                "core_claim": "test",
                "audience_value": "test",
                "evidence_refs": [],
                "primary_emotional_job": "conviction",
                "primary_audience_action": "save",
                "format_name": "reel",
                "platform": "instagram",
                "capture_policy": "capture_required",
                "evidence_label": "HYPOTHESIS",
            },
            beats=[
                {"beat_id": "b01", "platform_variant_id": "pv001", "role": "hook",
                 "required": True, "vo_text": "hello", "staged_action": "close-up",
                 "capture_policy": "capture_required"},
            ],
            text_intents=[
                {"text_intent_id": "t01", "beat_id": "b01", "function": "hook", "text": "Wonder"},
            ],
            media_recipes=[
                {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
                 "source_policy": "capture_required",
                 "primary": {"kind": "upload", "ingredient_id": "upload:22"}},
            ],
            edit_segments=[
                {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:22"},
            ],
        )
        assert contract["contract_id"] == "c001"
        assert len(contract["beats"]) == 1
        assert len(contract["text_intents"]) == 1
        assert len(contract["media_recipes"]) == 1
        assert len(contract["edit_segments"]) == 1
        assert "writer_contract_hash" in contract

    def test_assemble_contract_rejects_orphan_text_intent(self):
        from production_contract import assemble_contract
        with pytest.raises(ContractValidationError) as exc_info:
            assemble_contract(
                content_contract={
                    "contract_id": "c001",
                    "core_claim": "test", "audience_value": "test",
                    "evidence_refs": [], "primary_emotional_job": "x",
                    "primary_audience_action": "save", "format_name": "reel",
                    "platform": "ig", "capture_policy": "capture_required",
                    "evidence_label": "HYPOTHESIS",
                },
                beats=[{"beat_id": "b01", "platform_variant_id": "pv001", "role": "hook",
                        "required": True, "vo_text": "x", "staged_action": "x",
                        "capture_policy": "capture_required"}],
                text_intents=[
                    {"text_intent_id": "t01", "beat_id": "b99", "function": "hook", "text": "x"},
                ],
                media_recipes=[],
                edit_segments=[],
            )
        assert "b99" in str(exc_info.value)

    def test_assemble_contract_rejects_duplicate_beat_id(self):
        from production_contract import assemble_contract
        with pytest.raises(ContractValidationError) as exc_info:
            assemble_contract(
                content_contract={
                    "contract_id": "c001",
                    "core_claim": "test", "audience_value": "test",
                    "evidence_refs": [], "primary_emotional_job": "x",
                    "primary_audience_action": "save", "format_name": "reel",
                    "platform": "ig", "capture_policy": "capture_required",
                    "evidence_label": "HYPOTHESIS",
                },
                beats=[
                    {"beat_id": "b01", "platform_variant_id": "pv001", "role": "hook",
                     "required": True, "vo_text": "x", "staged_action": "x",
                     "capture_policy": "capture_required"},
                    {"beat_id": "b01", "platform_variant_id": "pv001", "role": "setup",
                     "required": True, "vo_text": "y", "staged_action": "y",
                     "capture_policy": "capture_preferred"},
                ],
                text_intents=[],
                media_recipes=[],
                edit_segments=[],
            )
        assert "duplicate" in str(exc_info.value).lower() or "b01" in str(exc_info.value)