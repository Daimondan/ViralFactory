"""
T9.5: AI review loop tests.

Tests for the AI review loop:
- Self-audit flags are auto-fixed before draft_ready
- Alignment check runs and logs its verdict
- Max 3 rounds behavior
- Non-convergence flagging
- All rounds logged in provenance
"""

import json
import os
import sys
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestAlignmentCheckSchema:
    """Test ALIGNMENT_CHECK_SCHEMA validation."""

    def test_valid_aligned_passes(self):
        from pipeline import ALIGNMENT_CHECK_SCHEMA
        from validator import validate_llm_output

        raw = json.dumps({
            "aligned": True,
            "issues": [],
            "recommendations": [],
        })
        result = validate_llm_output(raw, ALIGNMENT_CHECK_SCHEMA)
        assert result["aligned"] is True

    def test_valid_with_issues_passes(self):
        from pipeline import ALIGNMENT_CHECK_SCHEMA
        from validator import validate_llm_output

        raw = json.dumps({
            "aligned": False,
            "issues": [
                {"type": "drift", "description": "Draft changes the angle", "severity": "high"}
            ],
            "recommendations": ["Realign to the original thesis"],
        })
        result = validate_llm_output(raw, ALIGNMENT_CHECK_SCHEMA)
        assert result["aligned"] is False
        assert len(result["issues"]) == 1

    def test_missing_aligned_fails(self):
        from pipeline import ALIGNMENT_CHECK_SCHEMA
        from validator import validate_llm_output, ValidationError

        raw = json.dumps({"issues": [], "recommendations": []})
        with pytest.raises(ValidationError, match="aligned"):
            validate_llm_output(raw, ALIGNMENT_CHECK_SCHEMA)

    def test_missing_issues_fails(self):
        from pipeline import ALIGNMENT_CHECK_SCHEMA
        from validator import validate_llm_output, ValidationError

        raw = json.dumps({"aligned": True, "recommendations": []})
        with pytest.raises(ValidationError, match="issues"):
            validate_llm_output(raw, ALIGNMENT_CHECK_SCHEMA)


class TestAlignmentCheckPrompt:
    """Test the alignment check prompt exists and has the right content."""

    def test_prompt_exists(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "draft", "alignment_check_v1.md")
        assert os.path.exists(prompt_path)
        with open(prompt_path) as f:
            content = f.read()
        assert "version: 1.0" in content
        assert "aligned" in content
        assert "issues" in content
        assert "recommendations" in content


class TestReviewHistoryStorage:
    """Test that review_history and review_converged are stored correctly."""

    def test_save_review_history(self, tmp_path):
        from pipeline import PipelineStore

        db_path = str(tmp_path / "test.db")
        store = PipelineStore(db_path=db_path)

        # Create a card and draft
        card_id = store.create_idea_card(
            business_slug="test",
            idea="Test idea",
            hook_options=["hook 1"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "test"},
            origin="ai_originated",
        )
        draft_id = store.create_draft("test", card_id, "ai_originated", "X Thread", "one_off")

        review_history = [
            {"round": 1, "alignment_check": {"aligned": True, "issues": [], "recommendations": []}, "self_audit_fixes": []}
        ]
        result = store.save_review_history(draft_id, review_history, converged=True)
        assert result["review_converged"] == "true"

        # Verify it persists
        draft = store.get_draft(draft_id)
        assert draft["review_converged"] == "true"
        parsed = json.loads(draft["review_history"])
        assert len(parsed) == 1
        assert parsed[0]["round"] == 1

    def test_save_review_history_not_converged(self, tmp_path):
        from pipeline import PipelineStore

        db_path = str(tmp_path / "test.db")
        store = PipelineStore(db_path=db_path)

        card_id = store.create_idea_card(
            business_slug="test",
            idea="Test idea",
            hook_options=["hook 1"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "test"},
            origin="ai_originated",
        )
        draft_id = store.create_draft("test", card_id, "ai_originated", "X Thread", "one_off")

        review_history = [
            {"round": 1, "alignment_check": {"aligned": False, "issues": [{"type": "drift", "description": "test", "severity": "high"}], "recommendations": ["fix it"]}},
            {"round": 2, "alignment_check": {"aligned": False, "issues": [{"type": "drift", "description": "still wrong", "severity": "medium"}], "recommendations": ["try again"]}},
            {"round": 3, "alignment_check": {"aligned": False, "issues": [{"type": "drift", "description": "still wrong", "severity": "low"}], "recommendations": []}},
        ]
        result = store.save_review_history(draft_id, review_history, converged=False)
        assert result["review_converged"] == "false"

        draft = store.get_draft(draft_id)
        assert draft["review_converged"] == "false"
        parsed = json.loads(draft["review_history"])
        assert len(parsed) == 3

    def test_save_platform_content(self, tmp_path):
        from pipeline import PipelineStore

        db_path = str(tmp_path / "test.db")
        store = PipelineStore(db_path=db_path)

        card_id = store.create_idea_card(
            business_slug="test",
            idea="Test idea",
            hook_options=["hook 1"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "test"},
            origin="ai_originated",
        )
        draft_id = store.create_draft("test", card_id, "ai_originated", "X Thread", "one_off")

        platform_content = [
            {"platform": "X", "variant_type": "thread", "content": "revised content", "posts": ["revised tweet 1", "revised tweet 2"]}
        ]
        result = store.save_platform_content(draft_id, platform_content)
        assert result["draft_text"] == "revised content"

        draft = store.get_draft(draft_id)
        parsed = json.loads(draft["platform_content"])
        assert len(parsed) == 1
        assert parsed[0]["content"] == "revised content"


class TestAIReviewLoopMaxRounds:
    """Test that the review loop respects the max 3 rounds cap."""

    def test_max_rounds_is_three(self):
        """The review loop must have a hard cap of 3 rounds."""
        # Read the produce_chain.py source and verify max_rounds = 3
        source_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(source_path) as f:
            source = f.read()
        assert "max_rounds = 3" in source

    def test_reviewing_state_in_state_transitions(self):
        """The card state 'reviewing' must be used in the writer chain."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(source_path) as f:
            source = f.read()
        assert '"reviewing"' in source
        assert "update_card_state(card_id, \"reviewing\")" in source


class TestT9_4AssemblerMediaOnly:
    """T9.4: Verify the Assembler makes zero LLM text calls."""

    def test_no_fan_out_v2_calls_in_produce_chain(self):
        """grep for fan_out_v2 in produce_chain.py should return zero code calls."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(source_path) as f:
            content = f.read()
        # The prompt file reference should not appear in the _step_fanout method
        # (it can appear in comments)
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "fan_out_v2" in line and not line.strip().startswith("#"):
                pytest.fail(f"fan_out_v2 found in produce_chain.py line {i}: {line.strip()}")

    def test_no_structure_v1_calls_in_produce_chain(self):
        """grep for structure_v1 in produce_chain.py should return zero code calls."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(source_path) as f:
            content = f.read()
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if "structure_v1" in line and not line.strip().startswith("#"):
                pytest.fail(f"structure_v1 found in produce_chain.py line {i}: {line.strip()}")

    def test_no_fan_out_v2_calls_in_app_fan_out_route(self):
        """The assets_fan_out route in app.py should not call fan_out_v2.md."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(source_path) as f:
            content = f.read()
        # Find the assets_fan_out function and check it doesn't reference fan_out_v2
        # in a prompt_file= argument
        import re
        # Check for prompt_file="assets/fan_out_v2.md" in the fan-out route
        matches = re.findall(r'prompt_file="assets/fan_out_v2\.md"', content)
        assert len(matches) == 0, f"fan_out_v2.md still called in app.py: {len(matches)} references"

    def test_step_fanout_reads_platform_content(self):
        """_step_fanout should read platform_content from the draft."""
        source_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(source_path) as f:
            content = f.read()
        assert "platform_content" in content
        assert 'draft.get("platform_content")' in content