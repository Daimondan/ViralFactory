"""
Tests for T10.5 — Bounded remediation loop (AMENDMENT-008).

Tests the core loop logic with mocked LLM calls:
- Text-boundary firewall (hash lock + verification)
- Cost guard (absent = disabled, exceeded = stop)
- Three-round cap (non-convergent)
- Escalation (LLM says escalate=true)
- Compliant on first review (no remediation)
- Remediation actions applied to plan
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from remediation_loop import (
    compute_platform_content_hash,
    verify_text_boundary,
    check_remediation_cost,
    run_remediation_loop,
    _apply_remediation_action,
    DEFAULT_MAX_ROUNDS,
)


# ── Text-boundary firewall ──────────────────────────────────────────────────

class TestTextBoundaryFirewall:
    def test_hash_is_deterministic(self):
        content = [{"platform": "instagram", "content": "Hello world"}]
        h1 = compute_platform_content_hash(content)
        h2 = compute_platform_content_hash(content)
        assert h1 == h2

    def test_hash_changes_on_content_change(self):
        content1 = [{"platform": "instagram", "content": "Hello world"}]
        content2 = [{"platform": "instagram", "content": "Hello WORLD"}]
        assert compute_platform_content_hash(content1) != compute_platform_content_hash(content2)

    def test_hash_accepts_json_string(self):
        content = [{"platform": "instagram", "content": "Hello"}]
        h1 = compute_platform_content_hash(content)
        h2 = compute_platform_content_hash(json.dumps(content, sort_keys=True, ensure_ascii=False))
        assert h1 == h2

    def test_verify_text_boundary_unchanged(self):
        content = [{"platform": "instagram", "content": "Hello"}]
        h = compute_platform_content_hash(content)
        assert verify_text_boundary(h, content) is True

    def test_verify_text_boundary_changed(self):
        content = [{"platform": "instagram", "content": "Hello"}]
        h = compute_platform_content_hash(content)
        modified = [{"platform": "instagram", "content": "Changed"}]
        assert verify_text_boundary(h, modified) is False


# ── Cost guard ──────────────────────────────────────────────────────────────

class TestCostGuard:
    def test_disabled_when_max_cost_absent(self):
        result = check_remediation_cost(
            cumulative_cost=0, max_cost=None, new_action_cost=0.5
        )
        assert result["within_budget"] is False
        assert "disabled" in result["reason"].lower()

    def test_within_budget(self):
        result = check_remediation_cost(
            cumulative_cost=0.5, max_cost=2.0, new_action_cost=0.3
        )
        assert result["within_budget"] is True
        assert result["cumulative"] == 0.8

    def test_exceeds_budget(self):
        result = check_remediation_cost(
            cumulative_cost=1.8, max_cost=2.0, new_action_cost=0.5
        )
        assert result["within_budget"] is False
        assert "exceed" in result["reason"].lower()
        assert result["cumulative"] == 2.3

    def test_exact_budget(self):
        result = check_remediation_cost(
            cumulative_cost=1.5, max_cost=2.0, new_action_cost=0.5
        )
        assert result["within_budget"] is True


# ── Remediation action application ─────────────────────────────────────────

class TestApplyRemediationAction:
    def _plan(self):
        return {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 5.0},
                {"source": "generated:2", "in": 0, "out": 5.0},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 18},
            "audio": {"vo": {"take_id": "vo_1", "ducking": False}, "original_audio": False},
        }

    def test_revise_duration_target(self):
        plan = self._plan()
        modified = _apply_remediation_action(
            plan, "revise_plan_timing", "canvas.duration_target",
            {"from": 18, "to": 95}
        )
        assert modified["canvas"]["duration_target"] == 95
        # Original is not mutated
        assert plan["canvas"]["duration_target"] == 18

    def test_revise_segment_out(self):
        plan = self._plan()
        modified = _apply_remediation_action(
            plan, "revise_plan_timing", "segments[1].out",
            {"from": 5, "to": 30}
        )
        assert modified["segments"][1]["out"] == 30

    def test_adjust_audio_ducking(self):
        plan = self._plan()
        modified = _apply_remediation_action(
            plan, "adjust_audio_mixing", "audio.vo.ducking",
            {"from": False, "to": True}
        )
        assert modified["audio"]["vo"]["ducking"] is True

    def test_adjust_music_volume(self):
        plan = self._plan()
        modified = _apply_remediation_action(
            plan, "adjust_audio_mixing", "audio.music.volume",
            {"from": 0.3, "to": 0.2}
        )
        assert modified["audio"]["music"]["volume"] == 0.2

    def test_unsupported_action_returns_none(self):
        plan = self._plan()
        modified = _apply_remediation_action(
            plan, "regenerate_media_prompts", "segment[0].source",
            {"prompt": "new prompt"}
        )
        assert modified is None


# ── Remediation loop integration (mocked LLM) ──────────────────────────────

@pytest.fixture
def loop_setup(tmp_path):
    """Setup for remediation loop tests."""
    db_path = str(tmp_path / "test.db")

    # Seed DB with an edit plan
    from pipeline import PipelineStore
    store = PipelineStore(db_path)
    card_id = store.create_idea_card(
        business_slug="test", idea="Test",
        hook_options=["hook"], treatment={}, origin="test",
    )
    draft_id = store.create_draft("test", card_id, "test", "reel", "scope")
    asset_id = store.create_asset("test", draft_id, "instagram", "reel", "content")
    plan_id = store.save_edit_plan(draft_id, asset_id, {"segments": [], "canvas": {}})

    models_config = {
        "active": {"default": "test_backend"},
        "test_backend": {"model": "test-model", "provider": "test"},
        "asset_review": {
            "enabled": True,
            "max_remediation_cost_usd": 2.0,
            "max_remediation_rounds": 3,
        },
    }

    return {
        "db_path": db_path,
        "plan_id": plan_id,
        "models_config": models_config,
        "platform_content": [{"platform": "instagram", "content": "Test script"}],
    }


class TestRemediationLoop:
    def _compliant_review(self):
        return {
            "verdict": "compliant",
            "coverage": [{"beat_id": "b1", "status": "verified", "evidence": "ok", "action_needed": None}],
            "issues": [],
            "safe_remediation_scope": [],
            "summary": "All verified.",
        }

    def _non_compliant_review(self):
        return {
            "verdict": "revise_plan",
            "coverage": [{"beat_id": "b1", "status": "missing", "evidence": "not found", "action_needed": "fix"}],
            "issues": [{"severity": "high", "description": "Missing", "remediable": True}],
            "safe_remediation_scope": ["revise_plan_timing"],
            "summary": "Needs fix.",
        }

    def _remediation_response(self, escalate=False, cost=0.3):
        return {
            "escalate": escalate,
            "actions": [] if escalate else [
                {
                    "action_id": "a1",
                    "type": "revise_plan_timing",
                    "target": "canvas.duration_target",
                    "change": {"from": 18, "to": 95},
                    "reason": "VO is 92s",
                    "beat_ids_affected": ["b1"],
                }
            ],
            "estimated_cost_usd": cost,
            "summary": "Fix timeline" if not escalate else "Escalate",
        }

    def test_compliant_on_first_review(self, loop_setup):
        """No remediation needed — compliant on first review."""
        s = loop_setup
        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.return_value = self._compliant_review()

            result = run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {"duration_target": 95}},
                final_file_path="/tmp/test.mp4",
                models_config=s["models_config"],
                db_path=s["db_path"],
            )

        assert result["final_verdict"] == "compliant"
        assert len(result["rounds"]) == 1
        assert result["total_cost_usd"] == 0

    def test_remediation_disabled_when_cost_not_set(self, loop_setup):
        """When max_remediation_cost_usd is absent, remediation is disabled."""
        s = loop_setup
        config = dict(s["models_config"])
        config["asset_review"] = {"enabled": True}  # no max_remediation_cost_usd

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.return_value = self._non_compliant_review()

            result = run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {"duration_target": 18}},
                final_file_path="/tmp/test.mp4",
                models_config=config,
                db_path=s["db_path"],
            )

        assert result["final_verdict"] == "needs_operator_decision"
        assert "disabled" in result["summary"].lower()

    def test_escalation_when_llm_says_escalate(self, loop_setup):
        """LLM says escalate=true → needs_operator_decision."""
        s = loop_setup

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            # First call = compliance review (non-compliant), second = remediation (escalate)
            mock_inst.complete.side_effect = [
                self._non_compliant_review(),
                self._remediation_response(escalate=True),
            ]

            result = run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {"duration_target": 18}},
                final_file_path="/tmp/test.mp4",
                models_config=s["models_config"],
                db_path=s["db_path"],
            )

        assert result["final_verdict"] == "needs_operator_decision"
        assert len(result["rounds"]) == 2  # round 0 + round 1 (escalate)

    def test_cost_cap_stops_loop(self, loop_setup):
        """Cost cap exceeded → stops with cost_cap verdict."""
        s = loop_setup
        config = dict(s["models_config"])
        config["asset_review"]["max_remediation_cost_usd"] = 0.10  # very low cap

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            # Non-compliant review, then remediation with cost > cap
            mock_inst.complete.side_effect = [
                self._non_compliant_review(),
                self._remediation_response(cost=0.50),  # exceeds $0.10 cap
            ]

            result = run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {"duration_target": 18}},
                final_file_path="/tmp/test.mp4",
                models_config=config,
                db_path=s["db_path"],
            )

        assert result["final_verdict"] == "cost_cap"

    def test_non_convergent_after_max_rounds(self, loop_setup):
        """Non-convergent after 3 rounds → non_convergent verdict."""
        s = loop_setup

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            side_effects = []
            for _ in range(4):  # 4 rounds (0..3)
                side_effects.append(self._non_compliant_review())  # compliance review
                side_effects.append(self._remediation_response(cost=0.1))  # remediation
            mock_inst.complete.side_effect = side_effects

            result = run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {"duration_target": 18}},
                final_file_path="/tmp/test.mp4",
                models_config=s["models_config"],
                db_path=s["db_path"],
            )

        assert result["final_verdict"] == "non_convergent"
        assert len(result["rounds"]) == 4  # round 0 + 3 remediation rounds

    def test_platform_content_hash_locked(self, loop_setup):
        """The platform_content hash is locked at loop entry and never changes."""
        s = loop_setup

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.return_value = self._compliant_review()

            result = run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {}},
                final_file_path="",
                models_config=s["models_config"],
                db_path=s["db_path"],
            )

        expected_hash = compute_platform_content_hash(s["platform_content"])
        assert result["platform_content_hash"] == expected_hash

    def test_round_history_saved_to_db(self, loop_setup):
        """Each round is appended to review_round_history in the DB."""
        s = loop_setup
        from pipeline import PipelineStore

        with patch("llm_adapter.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.return_value = self._compliant_review()

            run_remediation_loop(
                asset_id=1, media_id=1, plan_id=s["plan_id"],
                platform_content=s["platform_content"],
                approved_script="Test script",
                compliance_contract={"beats": [{"beat_id": "b1", "required": True}]},
                edit_plan={"segments": [], "canvas": {}},
                final_file_path="",
                models_config=s["models_config"],
                db_path=s["db_path"],
            )

        store = PipelineStore(s["db_path"])
        history = store.get_review_round_history(s["plan_id"])
        assert len(history) >= 1
        assert history[0]["round"] == 0
        assert history[0]["verdict"] == "compliant"