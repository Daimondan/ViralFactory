"""
Tests for Production Contract v2 cross-document validators (VF-AU-102).

These validators check relationships that JSON Schema alone cannot prove:
- globally unique IDs within a contract
- all required beats represented in segments
- exact approved text hash preserved through assembly/remediation
- evidence references resolve to real sources
- required capture cannot resolve to generated/stock
- compliance coverage references known beats
- legacy_unclassified tasks flagged for operator classification
- mixed valid/invalid references correctly identified
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_contract_validators import (
    validate_full_contract,
    validate_required_beat_coverage,
    validate_evidence_references,
    validate_compliance_coverage,
    validate_hash_integrity,
    validate_legacy_capture_classification,
    ValidationResult,
)
from production_contract import (
    assemble_contract,
    compute_writer_contract_hash,
    ContractValidationError,
)


def _make_content_contract(**overrides):
    """Helper: create a minimal valid content contract."""
    base = {
        "contract_id": "c001",
        "core_claim": "Compound interest is the eighth wonder",
        "audience_value": "Understand how saving early compounds",
        "evidence_refs": ["source:14", "capture:22"],
        "primary_emotional_job": "conviction",
        "primary_audience_action": "save",
        "format_name": "reel",
        "platform": "instagram",
        "capture_policy": "capture_required",
        "evidence_label": "HYPOTHESIS",
    }
    base.update(overrides)
    return base


def _make_beat(beat_id="b01", **overrides):
    """Helper: create a minimal valid beat."""
    base = {
        "beat_id": beat_id,
        "platform_variant_id": "pv001",
        "role": "hook",
        "required": True,
        "vo_text": "The eighth wonder of the world",
        "staged_action": "Close-up of a savings ledger",
        "capture_policy": "capture_required",
        "evidence_refs": ["source:14"],
    }
    base.update(overrides)
    return base


class TestValidationResult:
    """ValidationResult should accumulate errors cleanly."""

    def test_empty_result_is_valid(self):
        r = ValidationResult()
        assert r.is_valid()
        assert r.errors == []

    def test_add_error_makes_invalid(self):
        r = ValidationResult()
        r.add_error("something wrong")
        assert not r.is_valid()
        assert "something wrong" in r.errors[0]

    def test_multiple_errors_preserved(self):
        r = ValidationResult()
        r.add_error("error 1")
        r.add_error("error 2")
        assert len(r.errors) == 2


class TestRequiredBeatCoverage:
    """Every required beat must be represented in edit segments."""

    def test_all_required_beats_covered(self):
        beats = [
            _make_beat("b01", required=True),
            _make_beat("b02", required=True),
        ]
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:1"},
            {"segment_id": "s02", "beat_ids": ["b02"], "source": "upload:2"},
        ]
        result = validate_required_beat_coverage(beats, segments)
        assert result.is_valid()

    def test_missing_required_beat_flagged(self):
        beats = [
            _make_beat("b01", required=True),
            _make_beat("b02", required=True),
        ]
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:1"},
            # b02 not represented
        ]
        result = validate_required_beat_coverage(beats, segments)
        assert not result.is_valid()
        assert any("b02" in e for e in result.errors)

    def test_optional_beat_not_required_in_segments(self):
        beats = [
            _make_beat("b01", required=True),
            _make_beat("b02", required=False),
        ]
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:1"},
            # b02 is optional — not required to be in segments
        ]
        result = validate_required_beat_coverage(beats, segments)
        assert result.is_valid()

    def test_beat_in_multiple_segments_is_ok(self):
        beats = [_make_beat("b01", required=True)]
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:1"},
            {"segment_id": "s02", "beat_ids": ["b01"], "source": "upload:2"},
        ]
        result = validate_required_beat_coverage(beats, segments)
        assert result.is_valid()


class TestEvidenceReferences:
    """Evidence references must resolve to non-empty source IDs."""

    def test_valid_evidence_refs(self):
        beats = [_make_beat("b01", evidence_refs=["source:14", "capture:22"])]
        result = validate_evidence_references(beats)
        assert result.is_valid()

    def test_empty_evidence_ref_flagged(self):
        beats = [_make_beat("b01", evidence_refs=[""])]
        result = validate_evidence_references(beats)
        assert not result.is_valid()
        assert any("b01" in e for e in result.errors)

    def test_no_evidence_refs_on_required_beat_flagged(self):
        beats = [_make_beat("b01", required=True, evidence_refs=[])]
        result = validate_evidence_references(beats)
        assert not result.is_valid()

    def test_optional_beat_without_evidence_ok(self):
        beats = [_make_beat("b01", required=False, evidence_refs=[])]
        result = validate_evidence_references(beats)
        assert result.is_valid()


class TestComplianceCoverage:
    """Compliance coverage must reference known beats."""

    def test_valid_compliance_coverage(self):
        beats = [_make_beat("b01"), _make_beat("b02")]
        compliance_beats = [
            {"beat_id": "b01", "status": "verified", "evidence": "audio match"},
            {"beat_id": "b02", "status": "verified", "evidence": "caption match"},
        ]
        result = validate_compliance_coverage(compliance_beats, beats)
        assert result.is_valid()

    def test_compliance_references_unknown_beat(self):
        beats = [_make_beat("b01")]
        compliance_beats = [
            {"beat_id": "b01", "status": "verified", "evidence": "ok"},
            {"beat_id": "b99", "status": "missing", "evidence": "not found"},
        ]
        result = validate_compliance_coverage(compliance_beats, beats)
        assert not result.is_valid()
        assert any("b99" in e for e in result.errors)

    def test_missing_required_beat_in_compliance(self):
        beats = [_make_beat("b01", required=True), _make_beat("b02", required=True)]
        compliance_beats = [
            {"beat_id": "b01", "status": "verified", "evidence": "ok"},
            # b02 missing from compliance
        ]
        result = validate_compliance_coverage(compliance_beats, beats)
        assert not result.is_valid()
        assert any("b02" in e for e in result.errors)


class TestHashIntegrity:
    """The writer contract hash must be preserved through assembly/remediation."""

    def test_hash_preserved_through_passthrough(self):
        writer_contract = {
            "platform_content": [{"platform": "ig", "content": "test"}],
            "beats": [_make_beat("b01")],
            "primary_audience_action": "save",
            "capture_policy": "capture_required",
        }
        original_hash = compute_writer_contract_hash(writer_contract)
        result = validate_hash_integrity(original_hash, writer_contract)
        assert result.is_valid()

    def test_hash_changed_detected(self):
        original = {
            "platform_content": [{"platform": "ig", "content": "A"}],
            "beats": [_make_beat("b01", vo_text="original")],
            "primary_audience_action": "save",
            "capture_policy": "capture_required",
        }
        modified = {
            "platform_content": [{"platform": "ig", "content": "B"}],
            "beats": [_make_beat("b01", vo_text="original")],
            "primary_audience_action": "save",
            "capture_policy": "capture_required",
        }
        original_hash = compute_writer_contract_hash(original)
        result = validate_hash_integrity(original_hash, modified)
        assert not result.is_valid()
        assert any("hash" in e.lower() for e in result.errors)

    def test_hash_changed_when_beat_vo_text_modified(self):
        original = {
            "platform_content": [],
            "beats": [_make_beat("b01", vo_text="original text")],
            "primary_audience_action": "save",
            "capture_policy": "capture_required",
        }
        modified = {
            "platform_content": [],
            "beats": [_make_beat("b01", vo_text="MODIFIED text")],
            "primary_audience_action": "save",
            "capture_policy": "capture_required",
        }
        original_hash = compute_writer_contract_hash(original)
        result = validate_hash_integrity(original_hash, modified)
        assert not result.is_valid()


class TestLegacyCaptureClassification:
    """Legacy unclassified capture tasks must be flagged for operator classification."""

    def test_legacy_unclassified_flagged(self):
        beats = [_make_beat("b01", capture_policy="legacy_unclassified")]
        result = validate_legacy_capture_classification(beats)
        assert not result.is_valid()
        assert any("b01" in e for e in result.errors)
        assert any("classify" in e.lower() for e in result.errors)

    def test_classified_beats_not_flagged(self):
        beats = [
            _make_beat("b01", capture_policy="capture_required"),
            _make_beat("b02", capture_policy="generated_allowed"),
        ]
        result = validate_legacy_capture_classification(beats)
        assert result.is_valid()


class TestFullContractValidation:
    """validate_full_contract runs all checks and returns a comprehensive result."""

    def test_valid_contract_passes_all_checks(self):
        contract = assemble_contract(
            content_contract=_make_content_contract(),
            beats=[_make_beat("b01"), _make_beat("b02", capture_policy="generated_allowed")],
            text_intents=[
                {"text_intent_id": "t01", "beat_id": "b01", "function": "hook", "text": "Wonder"},
            ],
            media_recipes=[
                {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
                 "source_policy": "capture_required",
                 "primary": {"kind": "upload", "ingredient_id": "upload:22"}},
                {"media_recipe_id": "r02", "beat_id": "b02", "media_function": "context",
                 "source_policy": "generated_allowed",
                 "primary": {"kind": "generated_image"}},
            ],
            edit_segments=[
                {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:22"},
                {"segment_id": "s02", "beat_ids": ["b02"], "source": "generated:1"},
            ],
        )
        result = validate_full_contract(contract)
        assert result.is_valid(), f"Expected valid, got errors: {result.errors}"

    def test_contract_with_missing_beat_coverage_fails(self):
        contract = assemble_contract(
            content_contract=_make_content_contract(),
            beats=[_make_beat("b01", required=True), _make_beat("b02", required=True)],
            text_intents=[],
            media_recipes=[
                {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
                 "source_policy": "capture_required",
                 "primary": {"kind": "upload", "ingredient_id": "upload:22"}},
                {"media_recipe_id": "r02", "beat_id": "b02", "media_function": "proof",
                 "source_policy": "capture_required",
                 "primary": {"kind": "upload", "ingredient_id": "upload:23"}},
            ],
            edit_segments=[
                {"segment_id": "s01", "beat_ids": ["b01"], "source": "upload:22"},
                # b02 not in any segment
            ],
        )
        result = validate_full_contract(contract)
        assert not result.is_valid()
        assert any("b02" in e for e in result.errors)

    def test_contract_with_capture_violation_fails(self):
        """A capture_required beat mapped to generated media must fail at assembly time."""
        with pytest.raises(ContractValidationError) as exc_info:
            assemble_contract(
                content_contract=_make_content_contract(),
                beats=[_make_beat("b01", capture_policy="capture_required")],
                text_intents=[],
                media_recipes=[
                    {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
                     "source_policy": "capture_required",
                     "primary": {"kind": "generated_image"}},  # VIOLATION
                ],
                edit_segments=[
                    {"segment_id": "s01", "beat_ids": ["b01"], "source": "generated:1"},
                ],
            )
        assert "capture" in str(exc_info.value).lower() or "generated" in str(exc_info.value).lower()

    def test_mixed_valid_invalid_references(self):
        """In a contract with mixed valid and invalid references, only invalid ones are flagged."""
        try:
            # This should raise during assembly because b99 doesn't exist
            contract = assemble_contract(
                content_contract=_make_content_contract(),
                beats=[_make_beat("b01")],
                text_intents=[
                    {"text_intent_id": "t01", "beat_id": "b01", "function": "hook", "text": "ok"},
                    {"text_intent_id": "t99", "beat_id": "b99", "function": "caption", "text": "bad"},
                ],
                media_recipes=[],
                edit_segments=[],
            )
            pytest.fail("Should have raised ContractValidationError")
        except ContractValidationError as e:
            assert "b99" in str(e)