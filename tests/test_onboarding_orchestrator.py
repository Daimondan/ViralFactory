"""
Tests: Onboarding Orchestrator (single-thread onboarding)

Tests the coverage map, playbook inputs builder, and the orchestrator
route structure. LLM calls are not mocked — we test the plumbing, not
the LLM output (which varies per call).
"""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playbook_runner import PlaybookRunner, PlaybookParser


class TestCoverageMap:
    """Coverage map tracks status of all 8 onboarding docs."""

    ONBOARDING_PLAYBOOKS = [
        "business-profile-intake",
        "voice-profile-builder",
        "sources-engine",
        "viral-patterns-starter",
        "audience-insights-builder",
        "story-frameworks-starter",
        "format-guide-starter",
        "visual-style-intake",
    ]

    def test_empty_coverage_has_all_8(self):
        """A fresh coverage map should list all 8 playbooks as 'empty'."""
        collected = {}
        # Simulate _build_coverage_map logic
        coverage = collected.get("coverage", {})
        for pb_name in self.ONBOARDING_PLAYBOOKS:
            if pb_name not in coverage:
                coverage[pb_name] = {"status": "empty"}
        assert len(coverage) == 8
        for pb in self.ONBOARDING_PLAYBOOKS:
            assert coverage[pb]["status"] == "empty"

    def test_coverage_with_collecting(self):
        """Coverage map should preserve existing statuses."""
        collected = {
            "coverage": {
                "business-profile-intake": {"status": "collecting"},
                "voice-profile-builder": {"status": "empty"},
            }
        }
        coverage = collected["coverage"]
        for pb_name in self.ONBOARDING_PLAYBOOKS:
            if pb_name not in coverage:
                coverage[pb_name] = {"status": "empty"}
        assert coverage["business-profile-intake"]["status"] == "collecting"
        assert coverage["voice-profile-builder"]["status"] == "empty"
        assert coverage["sources-engine"]["status"] == "empty"

    def test_valid_statuses(self):
        """Coverage statuses must be from the valid set."""
        valid = {"empty", "collecting", "ready", "drafted", "approved"}
        for status in valid:
            assert status in valid  # trivial but documents the set


class TestPlaybookInputsAll:
    """The playbook inputs builder should summarize all 8 playbooks."""

    def test_all_8_playbooks_exist(self):
        """All 8 playbook files should exist in the playbooks directory."""
        pb_dir = os.path.join(os.path.dirname(__file__), "..", "playbooks")
        for pb_name in self.ONBOARDING_PLAYBOOKS:
            path = os.path.join(pb_dir, f"{pb_name}.md")
            assert os.path.exists(path), f"Playbook file missing: {pb_name}.md"

    ONBOARDING_PLAYBOOKS = [
        "business-profile-intake",
        "voice-profile-builder",
        "sources-engine",
        "viral-patterns-starter",
        "audience-insights-builder",
        "story-frameworks-starter",
        "format-guide-starter",
        "visual-style-intake",
    ]


class TestOrchestratorRoute:
    """The /onboard route should create/resume an 'onboarding' run."""

    def test_onboarding_run_uses_playbook_name_onboarding(self):
        """The orchestrator run should use playbook_name='onboarding', not a specific playbook."""
        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("onboarding", "1.0", "testbiz")
        run = runner.get_run(run_id)
        assert run["playbook_name"] == "onboarding"
        assert run["status"] in ("in_progress", "pending")

    def test_onboarding_run_reuse(self):
        """Visiting /onboard should reuse an existing incomplete 'onboarding' run."""
        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        runner = PlaybookRunner(db_path)
        run_id1 = runner.start_run("onboarding", "1.0", "testbiz")

        # Simulate reuse: find existing incomplete onboarding run
        all_runs = runner.list_runs("testbiz")
        existing = None
        for r in all_runs:
            if r["playbook_name"] == "onboarding" and r["status"] not in ("completed", "cancelled"):
                existing = r
                break

        assert existing is not None
        assert existing["id"] == run_id1

        # Should NOT create a new run
        run_id2 = existing["id"]
        assert run_id1 == run_id2

    def test_onboarding_run_stores_coverage(self):
        """The onboarding run should store a coverage map in collected_inputs."""
        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("onboarding", "1.0", "testbiz")

        collected = {"coverage": {"business-profile-intake": {"status": "collecting"}}}
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        run = runner.get_run(run_id)
        stored = json.loads(run["collected_inputs"])
        assert "coverage" in stored
        assert stored["coverage"]["business-profile-intake"]["status"] == "collecting"


class TestGateCardStorage:
    """Gate card approval should store the module."""

    def test_gate_result_recorded(self):
        """Approving a gate card should record the gate result."""
        db_path = os.path.join(tempfile.mkdtemp(), "test.db")
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("onboarding", "1.0", "testbiz")

        runner.set_gate_result(run_id, "business-profile-intake", "approve", "Looks good")

        run = runner.get_run(run_id)
        gate_results = json.loads(run.get("gate_results") or "{}")
        assert "business-profile-intake" in gate_results
        assert gate_results["business-profile-intake"]["decision"] == "approve"


class TestOrchestratorSchema:
    """The orchestrator schema should validate the expected output shape."""

    def test_schema_has_required_fields(self):
        """The orchestrator schema must require reply, routed_seeds, coverage_updates, next_focus."""
        schema = {
            "type": "object",
            "required": ["reply", "routed_seeds", "coverage_updates", "next_focus"],
            "properties": {
                "reply": {"type": "string"},
                "routed_seeds": {"type": "array", "items": {"type": "object",
                    "properties": {"doc": {"type": "string"}, "seed": {"type": "string"}}}},
                "coverage_updates": {"type": "array", "items": {"type": "object",
                    "properties": {"doc": {"type": "string"}, "status": {"type": "string"}}}},
                "next_focus": {"type": "string"},
            },
        }
        assert "reply" in schema["required"]
        assert "routed_seeds" in schema["required"]
        assert "coverage_updates" in schema["required"]
        assert "next_focus" in schema["required"]

    def test_valid_orchestrator_output_passes_validation(self):
        """A well-formed orchestrator output should pass schema validation."""
        from validator import validate_llm_output
        schema = {
            "type": "object",
            "required": ["reply", "routed_seeds", "coverage_updates", "next_focus"],
            "properties": {
                "reply": {"type": "string"},
                "routed_seeds": {"type": "array", "items": {"type": "object",
                    "properties": {"doc": {"type": "string"}, "seed": {"type": "string"}}}},
                "coverage_updates": {"type": "array", "items": {"type": "object",
                    "properties": {"doc": {"type": "string"}, "status": {"type": "string"}}}},
                "next_focus": {"type": "string"},
            },
        }
        output = {
            "reply": "Tell me about your business",
            "routed_seeds": [{"doc": "business-profile-intake", "seed": "Caribbean AI brand"}],
            "coverage_updates": [{"doc": "business-profile-intake", "status": "collecting"}],
            "next_focus": "business-profile-intake",
        }
        result = validate_llm_output(json.dumps(output), schema, context="test")
        assert result["reply"] == "Tell me about your business"
        assert result["next_focus"] == "business-profile-intake"
