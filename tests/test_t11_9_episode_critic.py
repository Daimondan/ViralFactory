"""
Tests for T11.9: Layer-3 critic + rubric in module.

AC: rubric text lives in the module, not in prompts/code; critic never blocks.
"""

import json
import os
import pytest
import sys
import tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestEpisodeCritic:

    def test_critic_returns_scores(self):
        """The critic returns per-criterion scores + overall + summary."""
        from episode_critic import run_episode_critic, CriticResult

        beats = [
            {"id": "b01", "role": "hook", "vo_text": "I lost everything.",
             "staged_action": "the man sits alone at an empty desk"},
            {"id": "b02", "role": "lesson", "vo_text": "Save before you spend.",
             "staged_action": "the man puts coins in a jar"},
            {"id": "b03", "role": "cta", "vo_text": "Start today.",
             "staged_action": "the man opens the door to sunlight"},
        ]
        rubric = [
            {"criterion": "Hook contains contradiction", "description": "Hook must have a contradiction or confession", "pass_hint": "clear contradiction"},
            {"criterion": "Lesson stated plainly", "description": "Lesson must be plain words", "pass_hint": "direct statement"},
        ]

        mock_critic_output = {
            "scores": [
                {"criterion": "Hook contains contradiction", "score": 0.8, "reason": "I lost everything is a confession"},
                {"criterion": "Lesson stated plainly", "score": 1.0, "reason": "Save before you spend is direct"},
            ],
            "overall_score": 0.9,
            "summary": "Strong episode — clear hook and lesson.",
        }

        with patch("episode_critic.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.return_value = mock_critic_output
            result = run_episode_critic(
                beats=beats, rubric=rubric,
                models_config={}, db_path=":memory:",
                business_slug="test",
            )

        assert isinstance(result, CriticResult)
        assert len(result.scores) == 2
        assert result.scores[0]["score"] == 0.8
        assert result.overall_score == 0.9
        assert "Strong episode" in result.summary

    def test_critic_never_blocks_on_failure(self):
        """If the LLM call fails, the critic returns a neutral result — never blocks."""
        from episode_critic import run_episode_critic

        with patch("episode_critic.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.side_effect = Exception("LLM unavailable")
            result = run_episode_critic(
                beats=[], rubric=[],
                models_config={}, db_path=":memory:",
                business_slug="test",
            )

        assert result.overall_score == 0.0
        assert "Critic unavailable" in result.summary
        assert len(result.scores) == 0

    def test_rubric_lives_in_module_not_code(self):
        """The default_rubric is a fallback — the authoritative rubric lives in the module."""
        from episode_critic import default_rubric
        rubric = default_rubric()
        assert len(rubric) >= 5
        # Each rubric item has criterion, description, pass_hint
        for item in rubric:
            assert "criterion" in item
            assert "description" in item

    def test_critic_result_serializable(self):
        """The critic result can be serialized to dict for the Gate 2 card."""
        from episode_critic import CriticResult
        result = CriticResult(
            scores=[{"criterion": "test", "score": 0.5, "reason": "test reason"}],
            overall_score=0.5,
            summary="test summary",
        )
        d = result.to_dict()
        assert d["overall_score"] == 0.5
        assert d["summary"] == "test summary"
        assert len(d["scores"]) == 1
        # Must be JSON-serializable for the Gate 2 card
        json.dumps(d)

    def test_rubric_text_built_from_module(self):
        """The rubric text passed to the LLM is built from the module's rubric list."""
        from episode_critic import run_episode_critic

        rubric = [
            {"criterion": "Test criterion", "description": "Test description", "pass_hint": "Test hint"},
        ]

        with patch("episode_critic.LLMAdapter") as MockAdapter:
            mock_inst = MockAdapter.return_value
            mock_inst.complete.return_value = {"scores": [], "overall_score": 0, "summary": ""}
            run_episode_critic(
                beats=[{"id": "b01", "role": "hook", "vo_text": "test", "staged_action": "test"}],
                rubric=rubric,
                models_config={}, db_path=":memory:",
            )

            # Check that the prompt variables include the rubric text
            call_args = mock_inst.complete.call_args
            variables = call_args[1]["variables"] if "variables" in call_args[1] else call_args[0][1]
            assert "Test criterion" in variables["rubric"]
            assert "Test description" in variables["rubric"]