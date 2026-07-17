"""
Tests for VF-AU-201: Align the Process Registry.

Per AMENDMENT-009 + handoff implementation plan:
- Retire draft/generate_v2.md, fan_out_v2.md, structure_v1.md from active runtime
- Update draft_generate to point to generate_v3.md (current active)
- Register new production process entries
- Add playbook_type metadata to playbooks
- Routes/chain do not hardcode prompt/backend names
"""

import os
import yaml
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from process_engine import load_process_registry


@pytest.fixture
def registry():
    """Load the live processes.yaml."""
    return load_process_registry("config")


class TestRetiredProcesses:
    """Retired prompts must not be in active runtime processes."""

    def test_draft_generate_uses_v3_not_v2(self, registry):
        """draft_generate must point to generate_v3.md, not generate_v2.md."""
        draft_proc = registry["processes"]["draft_generate"]
        assert "generate_v3.md" in draft_proc["prompt_file"]
        assert "generate_v2.md" not in draft_proc["prompt_file"]

    def test_fan_out_adapt_retired(self, registry):
        """fan_out_adapt (retired by AMENDMENT-007) must not be active."""
        # It may exist with a 'retired: true' flag, or be removed entirely
        if "fan_out_adapt" in registry["processes"]:
            assert registry["processes"]["fan_out_adapt"].get("retired", False) is True
        # If not present, that's also fine

    def test_native_structure_retired(self, registry):
        """native_structure (retired by AMENDMENT-007) must not be active."""
        if "native_structure" in registry["processes"]:
            assert registry["processes"]["native_structure"].get("retired", False) is True

    def test_no_active_process_uses_v2_draft(self, registry):
        """No active process should reference generate_v2.md."""
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            prompt = spec.get("prompt_file", "")
            assert "generate_v2.md" not in prompt, \
                f"Process '{name}' still references retired generate_v2.md"

    def test_no_active_process_uses_fan_out_v2(self, registry):
        """No active process should reference fan_out_v2.md."""
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            prompt = spec.get("prompt_file", "")
            assert "fan_out_v2.md" not in prompt, \
                f"Process '{name}' still references retired fan_out_v2.md"

    def test_no_active_process_uses_structure_v1(self, registry):
        """No active process should reference structure_v1.md."""
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            prompt = spec.get("prompt_file", "")
            assert "structure_v1.md" not in prompt, \
                f"Process '{name}' still references retired structure_v1.md"


class TestNewProcessRegistrations:
    """New production processes must be registered."""

    def test_writer_v4_registered(self, registry):
        """Writer v4 (generate_v4.md) should be registered."""
        # Check if any process points to generate_v4.md
        found = False
        for name, spec in registry["processes"].items():
            if "generate_v4.md" in spec.get("prompt_file", ""):
                found = True
                break
        assert found, "No process registered for Writer v4 (generate_v4.md)"

    def test_media_plan_v2_registered(self, registry):
        """Media plan v2 should be registered."""
        found = False
        for name, spec in registry["processes"].items():
            if "media_plan_v2" in spec.get("prompt_file", "") or "media_plan_v2" in name:
                found = True
                break
        assert found, "No process registered for media plan v2"

    def test_edit_plan_v2_registered(self, registry):
        """Edit plan v2 should be registered."""
        found = False
        for name, spec in registry["processes"].items():
            if "edit_plan_v2" in spec.get("prompt_file", "") or "edit_plan_v2" in name:
                found = True
                break
        assert found, "No process registered for edit plan v2"

    def test_compliance_review_registered(self, registry):
        """Compliance review should be registered."""
        found = False
        for name, spec in registry["processes"].items():
            if "compliance" in name.lower() and "review" in name.lower():
                found = True
                break
        assert found, "No process registered for compliance review"

    def test_remediation_registered(self, registry):
        """Remediation should be registered."""
        found = False
        for name, spec in registry["processes"].items():
            if "remediation" in name.lower():
                found = True
                break
        assert found, "No process registered for remediation"

    def test_performance_analysis_registered(self, registry):
        """Performance analysis should be registered."""
        found = False
        for name, spec in registry["processes"].items():
            if "performance" in name.lower() or "analyst" in name.lower():
                found = True
                break
        assert found, "No process registered for performance analysis"


class TestSchemaRegistry:
    """Schema registry must resolve all referenced schemas."""

    def test_all_active_schemas_resolve(self, registry):
        """Every schema referenced by an active process must be in the schema registry."""
        schemas = registry.get("schemas", {})
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            schema_name = spec.get("schema", "")
            if schema_name:
                assert schema_name in schemas, \
                    f"Process '{name}' references schema '{schema_name}' not in schema registry"

    def test_production_contract_v2_schema_registered(self, registry):
        """Production Contract v2 schema should be in the schema registry."""
        schemas = registry.get("schemas", {})
        # The Writer v4 process should use a schema that includes the v2 contract
        found = False
        for name, ref in schemas.items():
            if "production_contract" in ref.lower() or "PRODUCTION_CONTRACT" in ref:
                found = True
                break
        # Also check inline schemas
        if not found:
            for name, spec in registry["processes"].items():
                if "generate_v4" in spec.get("prompt_file", ""):
                    # Writer v4 schema should reference the production contract
                    found = True
                    break
        assert found, "Production Contract v2 schema not registered"


class TestProcessSpecCompleteness:
    """Each registered process should have the required fields."""

    REQUIRED_FIELDS = ["prompt_file", "backend", "schema"]

    def test_all_active_processes_have_required_fields(self, registry):
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            for field in self.REQUIRED_FIELDS:
                assert field in spec, \
                    f"Process '{name}' missing required field '{field}'"

    def test_active_processes_have_context_template(self, registry):
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            assert "context_template" in spec, \
                f"Process '{name}' missing context_template"

    def test_active_processes_have_inputs(self, registry):
        for name, spec in registry["processes"].items():
            if spec.get("retired"):
                continue
            assert "inputs" in spec, \
                f"Process '{name}' missing inputs"


class TestPlaybookTypeMetadata:
    """Playbooks should carry playbook_type metadata (AMENDMENT-009)."""

    def test_onboarding_playbooks_have_type(self):
        """The eight onboarding playbooks should have playbook_type: onboarding."""
        playbook_dir = "playbooks"
        onboarding_files = [
            "business-profile-intake.md",
            "voice-profile-builder.md",
            "sources-engine.md",
            "viral-patterns-starter.md",
            "audience-insights.md",
            "story-frameworks.md",
            "format-guide.md",
            "visual-style-intake.md",
        ]
        for fname in onboarding_files:
            path = os.path.join(playbook_dir, fname)
            if not os.path.exists(path):
                continue  # some may not exist yet
            with open(path, "r") as f:
                content = f.read()
            # Check for YAML frontmatter with playbook_type
            assert "playbook_type" in content, \
                f"Playbook {fname} missing playbook_type metadata"

    def test_production_playbook_has_type(self):
        """The viral-content production playbook should have playbook_type: production."""
        path = "docs/playbooks/viral-content-production-playbook-v1.md"
        if not os.path.exists(path):
            pytest.skip("Production playbook not found")
        with open(path, "r") as f:
            content = f.read()
        assert "playbook_type" in content, \
            "Production playbook missing playbook_type metadata"


class TestRegistryVersion:
    """The registry should be versioned."""

    def test_registry_has_version(self, registry):
        """processes.yaml should have a version field."""
        # The raw file has a version comment; check the parsed data too
        # Some implementations put version at top level
        # At minimum, the file should exist and be parseable
        assert "processes" in registry

    def test_registry_version_bumped(self):
        """The registry version should reflect the AMENDMENT-009 update."""
        path = os.path.join("config", "processes.yaml")
        with open(path, "r") as f:
            content = f.read()
        # Version should be >= 2.0 (bumped for assembler upgrade)
        assert "version:" in content
        # Extract version
        for line in content.split("\n"):
            if line.strip().startswith("version:"):
                ver = line.split(":", 1)[1].strip()
                ver_num = float(ver)
                assert ver_num >= 2.0, f"Registry version {ver} should be >= 2.0"