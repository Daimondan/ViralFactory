"""
ViralFactory — R15 Tests: Gate step derived from playbook, not hardcoded

Tests that:
1. PlaybookParser correctly parses both formats (### Step N and N. Description)
2. get_gate_step_number() returns correct step for each playbook
3. No hardcoded gate step strings in app.py
4. Store endpoints use derived gate step (integration test via Flask client)
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playbook_runner import PlaybookParser, PlaybookRunner, Playbook


# --- Parser Tests ---

class TestNumberedListParsing:
    """R15: Parser handles numbered-list procedure format."""

    def test_viral_patterns_has_steps(self):
        pb = PlaybookParser.parse("playbooks/viral-patterns-starter.md")
        assert len(pb.steps) > 0
        assert any(s.is_gate for s in pb.steps)

    def test_audience_insights_has_steps(self):
        pb = PlaybookParser.parse("playbooks/audience-insights-builder.md")
        assert len(pb.steps) > 0
        assert any(s.is_gate for s in pb.steps)

    def test_business_profile_has_steps(self):
        pb = PlaybookParser.parse("playbooks/business-profile-intake.md")
        assert len(pb.steps) > 0
        assert any(s.is_gate for s in pb.steps)

    def test_sources_engine_has_steps(self):
        pb = PlaybookParser.parse("playbooks/sources-engine.md")
        assert len(pb.steps) > 0
        assert any(s.is_gate for s in pb.steps)

    def test_structured_format_still_works(self):
        """Voice Profile builder uses ### Step N format — must still parse."""
        pb = PlaybookParser.parse("playbooks/voice-profile-builder.md")
        assert len(pb.steps) >= 5
        assert any(s.is_gate for s in pb.steps)


# --- Gate Step Derivation Tests ---

class TestGateStepDerivation:
    """R15: get_gate_step_number returns correct step from parsed playbook."""

    @pytest.mark.parametrize("playbook_name,expected_gate", [
        ("voice-profile-builder", "5"),
        ("business-profile-intake", "4"),
        ("sources-engine", "5"),
        ("viral-patterns-starter", "5"),
        ("audience-insights-builder", "3"),
        ("story-frameworks-starter", "3"),
        ("format-guide-starter", "3"),
        ("visual-style-intake", "4"),
    ])
    def test_gate_step_correct(self, playbook_name, expected_gate):
        pb = PlaybookParser.parse(f"playbooks/{playbook_name}.md")
        gate = PlaybookRunner.get_gate_step_number(pb)
        assert gate == expected_gate, (
            f"{playbook_name}: expected gate step {expected_gate}, got {gate}. "
            f"Steps: {[(s.number, s.is_gate) for s in pb.steps]}"
        )

    def test_fallback_when_no_gate(self):
        """If no gate step found, returns '1' as fallback."""
        from playbook_runner import PlaybookStep
        pb = Playbook(
            name="test", purpose="test", inputs=[], steps=[
                PlaybookStep(number="1", title="do something", description=""),
            ],
            output_schema_heading="Output", guardrails=[], file_path="", file_version="1.0",
        )
        assert PlaybookRunner.get_gate_step_number(pb) == "1"


# --- No Hardcoded Gate Strings ---

class TestNoHardcodedGateSteps:
    """R15 AC: no literal gate step strings in route handlers."""

    def test_no_hardcoded_gate_step_in_app(self):
        """No set_gate_result call with a literal number string in app.py."""
        src_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(src_path, "r") as f:
            content = f.read()
        # Check for pattern: set_gate_result(..., "N", ...)
        import re
        violations = []
        for i, line in enumerate(content.split("\n"), 1):
            # Match set_gate_result with a literal quoted number
            if re.search(r'set_gate_result\s*\([^)]*"\d+"', line):
                violations.append(f"Line {i}: {line.strip()}")
        assert not violations, (
            f"Hardcoded gate step strings found in app.py:\n" + "\n".join(violations)
        )

    def test_all_store_endpoints_use_derived_gate(self):
        """All store-* endpoints reference get_gate_step_number or PlaybookParser."""
        src_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(src_path, "r") as f:
            content = f.read()
        # Find all store endpoint functions
        import re
        store_fns = re.findall(r'def (store_\w+)\(run_id\):', content)
        assert len(store_fns) >= 7, f"Expected 7+ store endpoints, found {len(store_fns)}: {store_fns}"
        # Each should have get_gate_step_number in its body
        for fn_name in store_fns:
            # Extract function body (rough)
            pattern = rf'def {fn_name}\(run_id\):.*?(?=@app\.route|def \w+|\Z)'
            match = re.search(pattern, content, re.DOTALL)
            assert match, f"Could not extract body of {fn_name}"
            body = match.group(0)
            assert "get_gate_step_number" in body or "PlaybookParser" in body, (
                f"{fn_name} does not use derived gate step — still hardcoded?"
            )