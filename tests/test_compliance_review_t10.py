"""
Tests for T10.4 — Final-output LLM compliance review (AMENDMENT-008).

Tests the run_compliance_review method in AssetReviewer. Mocks the LLM
adapter to avoid real API calls. Verifies:
- The method passes the right variables to the prompt
- The domain-specific validator runs (compliant requires all beats verified)
- The review is saved with type="compliance"
- Fallback to needs_operator_decision on LLM failure
- The review_type "compliance" is recognized in get_latest_review_summary
"""

import os
import sys
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asset_review import AssetReviewer


@pytest.fixture
def reviewer(tmp_path):
    """Create an AssetReviewer with a fresh DB."""
    db_path = str(tmp_path / "test.db")
    models_config = {
        "active": {"default": "test_backend"},
        "test_backend": {"model": "test-model", "provider": "test"},
        "asset_review": {"enabled": True},
    }
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
    r = AssetReviewer(models_config, db_path=db_path, prompts_dir=prompts_dir)
    return r, db_path


class TestRunComplianceReview:
    def _valid_review_output(self):
        """Valid LLM output for compliance review — all beats verified."""
        return {
            "verdict": "compliant",
            "coverage": [
                {"beat_id": "b1", "status": "verified",
                 "evidence": "Transcript contains the line at 0:03",
                 "action_needed": None},
                {"beat_id": "b2", "status": "verified",
                 "evidence": "Keyframe 1 shows the visual",
                 "action_needed": None},
            ],
            "issues": [],
            "safe_remediation_scope": [],
            "summary": "All beats verified.",
        }

    def _non_compliant_output(self):
        """LLM output with a missing beat — needs_operator_decision."""
        return {
            "verdict": "needs_operator_decision",
            "coverage": [
                {"beat_id": "b1", "status": "verified",
                 "evidence": "Transcript contains the line",
                 "action_needed": None},
                {"beat_id": "b2", "status": "missing",
                 "evidence": "VO transcript does not contain this line. VO is 92s but plan is 18s.",
                 "action_needed": "needs_operator_decision"},
            ],
            "issues": [
                {"severity": "high",
                 "description": "VO duration 92s exceeds plan 18s — 74s of dialogue lost",
                 "beat_id": "b2",
                 "remediable": False},
            ],
            "safe_remediation_scope": [],
            "summary": "Beat b2 missing — VO exceeds plan timeline. Needs operator decision.",
        }

    def test_compliant_review_saved(self, reviewer):
        """A compliant review is saved with verdict=compliant."""
        r, db_path = reviewer

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_instance = MockAdapter.return_value
            mock_instance.complete.return_value = self._valid_review_output()

            result = r.run_compliance_review(
                asset_id=1,
                media_id=1,
                approved_script="Test script with VO dialogue",
                compliance_contract={"beats": [
                    {"beat_id": "b1", "required": True},
                    {"beat_id": "b2", "required": True},
                ]},
                edit_plan={"segments": [], "canvas": {"duration_target": 30}},
                final_file_path="/nonexistent.mp4",
                business_slug="test",
            )

        assert result["verdict"] == "compliant"
        assert result["review_type"] == "compliance"
        assert result["status"] == "complete"
        assert len(result["coverage"]) == 2

    def test_non_compliant_review_saved(self, reviewer):
        """A non-compliant review with a missing beat is saved."""
        r, db_path = reviewer

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_instance = MockAdapter.return_value
            mock_instance.complete.return_value = self._non_compliant_output()

            result = r.run_compliance_review(
                asset_id=1,
                media_id=1,
                approved_script="Test script",
                compliance_contract={"beats": [
                    {"beat_id": "b1", "required": True},
                    {"beat_id": "b2", "required": True},
                ]},
                edit_plan={"segments": [], "canvas": {"duration_target": 18}},
                final_file_path="/nonexistent.mp4",
            )

        assert result["verdict"] == "needs_operator_decision"
        assert len(result["issues"]) == 1
        assert result["issues"][0]["severity"] == "high"

    def test_compliant_with_unverified_beat_rejected_by_validator(self, reviewer):
        """The domain validator catches LLM saying compliant with an unverified beat."""
        r, db_path = reviewer
        bad_output = self._valid_review_output()
        bad_output["coverage"][0]["status"] = "missing"  # Not all verified

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_instance = MockAdapter.return_value
            mock_instance.complete.return_value = bad_output

            result = r.run_compliance_review(
                asset_id=1, media_id=1,
                approved_script="Test",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {}},
                final_file_path="",
            )

        # Validator should reject → fallback to needs_operator_decision
        assert result["verdict"] == "needs_operator_decision"
        assert result["status"] == "failed"

    def test_llm_failure_falls_back_to_operator_decision(self, reviewer):
        """If the LLM call fails, the review falls back to needs_operator_decision."""
        r, db_path = reviewer

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_instance = MockAdapter.return_value
            mock_instance.complete.side_effect = Exception("API timeout")

            result = r.run_compliance_review(
                asset_id=1, media_id=1,
                approved_script="Test",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {}},
                final_file_path="",
            )

        assert result["verdict"] == "needs_operator_decision"
        assert result["status"] == "failed"
        assert "failed" in result["summary"].lower()

    def test_review_type_compliance_in_priority(self, reviewer):
        """The 'compliance' review_type should be recognized by get_latest_review_summary."""
        r, db_path = reviewer

        # Save a compliance review directly
        r._save_review(
            asset_id=1, media_id=1, media_path="/tmp/test.mp4",
            review_type="compliance", status="complete",
            verdict="compliant", findings={"verdict": "compliant"},
            summary="All beats verified.",
        )

        summary = r.get_latest_review_summary(1)
        assert summary is not None
        assert summary["review_type"] == "compliance"
        assert summary["verdict"] == "compliant"

    def test_remediation_round_info_passed(self, reviewer):
        """The remediation round number is passed to the prompt variables."""
        r, db_path = reviewer

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_instance = MockAdapter.return_value
            mock_instance.complete.return_value = self._valid_review_output()

            r.run_compliance_review(
                asset_id=1, media_id=1,
                approved_script="Test",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {}},
                final_file_path="",
                remediation_round=2,
            )

            # Check the context contains the round number
            call_args = mock_instance.complete.call_args
            assert "round 2" in call_args.kwargs.get("context", "")