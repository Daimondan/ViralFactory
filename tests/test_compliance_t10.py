"""
Tests for T10.1 — Compliance contract prompts + schemas + validators (AMENDMENT-008).

Covers:
- Schema validation for compliance contract, compliance review, remediation instruction
- Domain-specific validators (required beats, unique beat_ids, compliant=all-verified)
- Union type support in the generic validator (planned_time_range: ["object", "null"])
- Enum validation (requirement_type, verification_method, verdict, status)
- Prompt files exist and are versioned
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validator import validate_json_schema, ValidationError
from pipeline import (
    COMPLIANCE_CONTRACT_SCHEMA,
    COMPLIANCE_REVIEW_SCHEMA,
    REMEDIATION_INSTRUCTION_SCHEMA,
)
from compliance_validators import (
    validate_compliance_contract,
    validate_compliance_review,
    validate_remediation_instruction,
)


PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts", "assembly")


# ── Prompt files exist and are versioned ────────────────────────────────────

class TestPromptFiles:
    def test_compliance_contract_prompt_exists(self):
        path = os.path.join(PROMPTS_DIR, "compliance_contract_v1.md")
        assert os.path.exists(path), f"Missing prompt: {path}"
        with open(path) as f:
            content = f.read()
        assert "<!-- version:" in content, "Prompt must have version comment"

    def test_compliance_review_prompt_exists(self):
        path = os.path.join(PROMPTS_DIR, "compliance_review_v1.md")
        assert os.path.exists(path), f"Missing prompt: {path}"
        with open(path) as f:
            content = f.read()
        assert "<!-- version:" in content, "Prompt must have version comment"

    def test_remediation_instruction_prompt_exists(self):
        path = os.path.join(PROMPTS_DIR, "remediation_instruction_v1.md")
        assert os.path.exists(path), f"Missing prompt: {path}"
        with open(path) as f:
            content = f.read()
        assert "<!-- version:" in content, "Prompt must have version comment"

    def test_prompts_have_required_variables(self):
        """Prompts must contain the variable placeholders they need."""
        with open(os.path.join(PROMPTS_DIR, "compliance_contract_v1.md")) as f:
            contract_prompt = f.read()
        assert "{asset_content}" in contract_prompt
        assert "{edit_plan_json}" in contract_prompt

        with open(os.path.join(PROMPTS_DIR, "compliance_review_v1.md")) as f:
            review_prompt = f.read()
        assert "{approved_script}" in review_prompt
        assert "{compliance_contract_json}" in review_prompt
        assert "{final_file_facts}" in review_prompt

        with open(os.path.join(PROMPTS_DIR, "remediation_instruction_v1.md")) as f:
            remediation_prompt = f.read()
        assert "{approved_script}" in remediation_prompt
        assert "{compliance_review_json}" in remediation_prompt


# ── Compliance Contract Schema ──────────────────────────────────────────────

class TestComplianceContractSchema:
    def _valid_contract(self):
        return {
            "beats": [
                {
                    "beat_id": "b1",
                    "source_excerpt": "This changes everything",
                    "requirement_type": "spoken_dialogue",
                    "required": True,
                    "planned_segment_ids": ["seg_0", "seg_1"],
                    "planned_time_range": {"start": 0.0, "end": 5.5},
                    "verification_method": "audio_transcript_match",
                },
                {
                    "beat_id": "b2",
                    "source_excerpt": "Hands opening a biscuit tin",
                    "requirement_type": "visual_element",
                    "required": True,
                    "planned_segment_ids": ["seg_0"],
                    "planned_time_range": {"start": 0.0, "end": 3.0},
                    "verification_method": "keyframe_visual_match",
                },
            ],
            "summary": "2 beats identified.",
        }

    def test_valid_contract_passes(self):
        result = validate_compliance_contract(self._valid_contract())
        assert result["beats"][0]["beat_id"] == "b1"

    def test_missing_beats_rejected(self):
        contract = self._valid_contract()
        contract["beats"] = []
        with pytest.raises(ValidationError, match="at least 1"):
            validate_compliance_contract(contract)

    def test_missing_required_field_rejected(self):
        contract = self._valid_contract()
        del contract["beats"][0]["beat_id"]
        with pytest.raises(ValidationError, match="beat_id"):
            validate_compliance_contract(contract)

    def test_invalid_requirement_type_rejected(self):
        contract = self._valid_contract()
        contract["beats"][0]["requirement_type"] = "not_a_real_type"
        with pytest.raises(ValidationError, match="one of"):
            validate_compliance_contract(contract)

    def test_invalid_verification_method_rejected(self):
        contract = self._valid_contract()
        contract["beats"][0]["verification_method"] = "guess"
        with pytest.raises(ValidationError, match="one of"):
            validate_compliance_contract(contract)

    def test_null_planned_time_range_accepted(self):
        """Union type: planned_time_range can be null (no plan mapping)."""
        contract = self._valid_contract()
        contract["beats"][0]["planned_time_range"] = None
        result = validate_compliance_contract(contract)
        assert result["beats"][0]["planned_time_range"] is None

    def test_empty_planned_segment_ids_accepted(self):
        """A beat with no plan mapping (empty array) is valid — it's a gap."""
        contract = self._valid_contract()
        contract["beats"][0]["planned_segment_ids"] = []
        result = validate_compliance_contract(contract)
        assert result["beats"][0]["planned_segment_ids"] == []

    def test_required_beat_without_verification_method_rejected(self):
        """Domain-specific: required beat must have a verification_method."""
        contract = self._valid_contract()
        contract["beats"][0]["verification_method"] = ""
        with pytest.raises(ValidationError, match="required but has no verification_method"):
            validate_compliance_contract(contract)

    def test_required_beat_without_source_excerpt_rejected(self):
        """Domain-specific: required beat must have a source_excerpt."""
        contract = self._valid_contract()
        contract["beats"][0]["source_excerpt"] = ""
        with pytest.raises(ValidationError, match="required but has no source_excerpt"):
            validate_compliance_contract(contract)

    def test_optional_beat_without_verification_method_accepted(self):
        """Optional beats (required=false) don't need verification_method."""
        contract = self._valid_contract()
        contract["beats"][0]["required"] = False
        contract["beats"][0]["verification_method"] = ""
        result = validate_compliance_contract(contract)
        assert result is not None

    def test_duplicate_beat_ids_rejected(self):
        """Domain-specific: beat_ids must be unique."""
        contract = self._valid_contract()
        contract["beats"][1]["beat_id"] = "b1"  # duplicate
        with pytest.raises(ValidationError, match="duplicate beat_id"):
            validate_compliance_contract(contract)

    def test_missing_summary_rejected(self):
        contract = self._valid_contract()
        del contract["summary"]
        with pytest.raises(ValidationError, match="summary"):
            validate_compliance_contract(contract)


# ── Compliance Review Schema ────────────────────────────────────────────────

class TestComplianceReviewSchema:
    def _valid_review(self, verdict="compliant"):
        return {
            "verdict": verdict,
            "coverage": [
                {
                    "beat_id": "b1",
                    "status": "verified",
                    "evidence": "Transcript at 0:03 contains the line",
                    "action_needed": None,
                },
                {
                    "beat_id": "b2",
                    "status": "verified",
                    "evidence": "Keyframe 1 shows hands opening a tin",
                    "action_needed": None,
                },
            ],
            "issues": [],
            "safe_remediation_scope": [],
            "summary": "All beats verified.",
        }

    def test_valid_compliant_review_passes(self):
        result = validate_compliance_review(self._valid_review())
        assert result["verdict"] == "compliant"

    def test_compliant_with_unverified_beat_rejected(self):
        """Domain-specific: compliant verdict requires all beats verified."""
        review = self._valid_review("compliant")
        review["coverage"][0]["status"] = "missing"
        with pytest.raises(ValidationError, match="compliant.*missing"):
            validate_compliance_review(review)

    def test_compliant_with_partial_beat_rejected(self):
        review = self._valid_review("compliant")
        review["coverage"][0]["status"] = "partial"
        with pytest.raises(ValidationError, match="compliant.*partial"):
            validate_compliance_review(review)

    def test_non_compliant_with_missing_beat_accepted(self):
        review = self._valid_review("needs_operator_decision")
        review["coverage"][0]["status"] = "missing"
        review["issues"] = [
            {
                "severity": "high",
                "description": "VO dialogue missing",
                "beat_id": "b1",
                "remediable": False,
            }
        ]
        result = validate_compliance_review(review)
        assert result["verdict"] == "needs_operator_decision"

    def test_invalid_verdict_rejected(self):
        review = self._valid_review("not_a_verdict")
        with pytest.raises(ValidationError, match="one of"):
            validate_compliance_review(review)

    def test_invalid_status_rejected(self):
        review = self._valid_review("needs_rerender")
        review["coverage"][0]["status"] = "maybe"
        with pytest.raises(ValidationError, match="one of"):
            validate_compliance_review(review)

    def test_null_action_needed_accepted(self):
        review = self._valid_review("compliant")
        review["coverage"][0]["action_needed"] = None
        result = validate_compliance_review(review)
        assert result["coverage"][0]["action_needed"] is None

    def test_missing_coverage_rejected(self):
        review = self._valid_review()
        del review["coverage"]
        with pytest.raises(ValidationError, match="coverage"):
            validate_compliance_review(review)


# ── Remediation Instruction Schema ─────────────────────────────────────────

class TestRemediationInstructionSchema:
    def _valid_remediation(self, escalate=False):
        return {
            "escalate": escalate,
            "actions": [] if escalate else [
                {
                    "action_id": "a1",
                    "type": "revise_plan_timing",
                    "target": "canvas.duration_target",
                    "change": {"from": 18, "to": 95},
                    "reason": "VO is 92s, plan is 18s",
                    "beat_ids_affected": ["b3"],
                }
            ],
            "estimated_cost_usd": 0.0 if escalate else 0.40,
            "summary": "Fix timeline" if not escalate else "Escalate",
        }

    def test_valid_remediation_passes(self):
        result = validate_remediation_instruction(self._valid_remediation())
        assert result["escalate"] is False
        assert len(result["actions"]) == 1

    def test_escalate_with_actions_rejected(self):
        """Domain-specific: escalate=true should have no actions."""
        remediation = self._valid_remediation(escalate=True)
        remediation["actions"] = [self._valid_remediation()["actions"][0]]
        with pytest.raises(ValidationError, match="escalate.*actions"):
            validate_remediation_instruction(remediation)

    def test_no_escalate_no_actions_rejected(self):
        """Domain-specific: escalate=false needs at least one action."""
        remediation = self._valid_remediation(escalate=False)
        remediation["actions"] = []
        with pytest.raises(ValidationError, match="no actions"):
            validate_remediation_instruction(remediation)

    def test_negative_cost_rejected(self):
        remediation = self._valid_remediation()
        remediation["estimated_cost_usd"] = -1.0
        with pytest.raises(ValidationError, match="negative"):
            validate_remediation_instruction(remediation)

    def test_invalid_action_type_rejected(self):
        remediation = self._valid_remediation()
        remediation["actions"][0]["type"] = "change_approved_text"
        with pytest.raises(ValidationError, match="one of"):
            validate_remediation_instruction(remediation)

    def test_escalate_only_passes(self):
        result = validate_remediation_instruction(self._valid_remediation(escalate=True))
        assert result["escalate"] is True
        assert result["actions"] == []


# ── Union type support in generic validator ────────────────────────────────

class TestUnionTypeSupport:
    """T10.1: The validator must handle union types like ["object", "null"]."""

    def test_union_object_null_accepts_object(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"type": ["object", "null"], "properties": {"x": {"type": "number"}}},
            },
        }
        data = {"value": {"x": 42}}
        result = validate_json_schema(data, schema)
        assert result["value"]["x"] == 42

    def test_union_object_null_accepts_null(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"type": ["object", "null"]},
            },
        }
        data = {"value": None}
        result = validate_json_schema(data, schema)
        assert result["value"] is None

    def test_union_string_null_accepts_string(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"type": ["string", "null"]},
            },
        }
        data = {"value": "hello"}
        result = validate_json_schema(data, schema)
        assert result["value"] == "hello"

    def test_union_rejects_wrong_type(self):
        schema = {
            "type": "object",
            "properties": {
                "value": {"type": ["object", "null"]},
            },
        }
        data = {"value": "not_an_object"}
        with pytest.raises(ValidationError, match="one of"):
            validate_json_schema(data, schema)


# ── Enum validation in generic validator ───────────────────────────────────

class TestEnumValidation:
    """T10.1: The validator must check enum values."""

    def test_enum_valid_value_accepted(self):
        schema = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "green", "blue"]},
            },
        }
        data = {"color": "red"}
        result = validate_json_schema(data, schema)
        assert result["color"] == "red"

    def test_enum_invalid_value_rejected(self):
        schema = {
            "type": "object",
            "properties": {
                "color": {"type": "string", "enum": ["red", "green", "blue"]},
            },
        }
        data = {"color": "yellow"}
        with pytest.raises(ValidationError, match="one of"):
            validate_json_schema(data, schema)

    def test_enum_in_array_item_properties(self):
        """Enum validation works for properties of items in arrays."""
        schema = {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {
                            "status": {"type": "string", "enum": ["ok", "fail"]},
                        },
                    },
                }
            },
        }
        data = {"items": [{"status": "ok"}, {"status": "bad"}]}
        with pytest.raises(ValidationError, match="one of"):
            validate_json_schema(data, schema)