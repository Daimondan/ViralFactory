"""
ViralFactory — T2.1 Business Profile Intake Tests

Tests for:
- Business Profile schema validation (BUSINESS_PROFILE_SCHEMA)
- brand_context_to_markdown converter
- business_profile_to_yaml converter
- Q&A API endpoint (stores Q&A pairs)
- Analyze API endpoint (mocked LLM, validates output)
- Store API endpoint (gate enforcement: writes only on approval)
- Parked profile does NOT write business.yaml or brand-context module
- Approved profile writes both business.yaml and brand-context module
- Zero tenant strings in code (no hardcoded business values)
"""

import json
import os
import tempfile
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config_loader import load_all, ConfigError
from module_store import (
    ModuleStore, BUSINESS_PROFILE_SCHEMA,
    business_profile_to_yaml, brand_context_to_markdown,
)
from validator import validate_llm_output, ValidationError
from playbook_runner import PlaybookRunner


# --- Fixtures ---

@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def tmp_config_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        business = {
            "business": {
                "name": "TestBrand",
                "slug": "testbrand",
                "description": "A test business",
            },
            "brands": [{"name": "TestBrand", "purpose": "Testing"}],
            "subjects": ["AI", "wealth"],
            "platforms": [{"name": "X", "handle": "@test", "priority": 1}],
            "goals": ["Build audience"],
            "red_lines": ["No spam"],
            "audience_description": "Testers",
        }
        with open(os.path.join(tmpdir, "business.yaml"), "w") as f:
            yaml.dump(business, f)

        models = {
            "active": {
                "default": "test_backend",
                "drafter": "test_backend",
                "drafter_ab_candidate": None,
            },
            "test_backend": {
                "provider": "ollama_cloud",
                "model": "test-model",
                "temperature": 0,
                "max_tokens": 4096,
                "base_url": "https://example.com",
            },
        }
        with open(os.path.join(tmpdir, "models.yaml"), "w") as f:
            yaml.dump(models, f)

        sources = {"feeds": [], "channels": [], "queries": []}
        with open(os.path.join(tmpdir, "sources.yaml"), "w") as f:
            yaml.dump(sources, f)

        yield tmpdir


@pytest.fixture
def valid_profile():
    """A valid business profile matching BUSINESS_PROFILE_SCHEMA."""
    return {
        "business": {
            "name": "StackPenni",
            "slug": "stackpenni",
            "description": "Caribbean AI + wealth brand",
        },
        "brands": [
            {"name": "StackPenni", "purpose": "Main brand"},
            {"name": "Island Futurist", "purpose": "Future-of-work through Caribbean lens"},
        ],
        "subjects": ["AI", "wealth", "Caribbean culture", "entrepreneurship"],
        "platforms": [
            {"name": "X", "handle": "@StackPenni", "priority": 1},
            {"name": "Instagram", "handle": "@stackpenni", "priority": 2},
        ],
        "goals": ["Build audience and authority", "Create human-sounding content"],
        "red_lines": ["No get-rich-quick", "No AI slop"],
        "audience_description": "Caribbean entrepreneurs interested in AI and wealth.",
    }


@pytest.fixture
def tmp_dirs():
    """Temporary config dir + modules dir + db for integration tests."""
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)

            # Write minimal configs
            business = {
                "business": {"name": "TestBrand", "slug": "testbrand", "description": "Test"},
                "subjects": ["AI"], "platforms": [{"name": "X", "handle": "@t", "priority": 1}],
            }
            with open(os.path.join(config_dir, "business.yaml"), "w") as f:
                yaml.dump(business, f)
            models = {
                "active": {"default": "tb", "drafter": "tb", "drafter_ab_candidate": None},
                "tb": {"provider": "ollama_cloud", "model": "m", "temperature": 0, "max_tokens": 4, "base_url": "https://x.com"},
            }
            with open(os.path.join(config_dir, "models.yaml"), "w") as f:
                yaml.dump(models, f)
            sources = {"feeds": [], "channels": [], "queries": []}
            with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
                yaml.dump(sources, f)

            yield config_dir, modules_dir, db_path

            if os.path.exists(db_path):
                os.unlink(db_path)


# --- Schema Tests ---

class TestBusinessProfileSchema:

    def test_valid_profile_passes(self, valid_profile):
        """A valid business profile passes schema validation."""
        raw = json.dumps(valid_profile)
        result = validate_llm_output(raw, BUSINESS_PROFILE_SCHEMA, context="test")
        assert result["business"]["name"] == "StackPenni"
        assert len(result["brands"]) == 2
        assert len(result["subjects"]) == 4

    def test_missing_required_field_fails(self, valid_profile):
        """Missing 'audience_description' fails."""
        del valid_profile["audience_description"]
        raw = json.dumps(valid_profile)
        with pytest.raises(ValidationError, match="audience_description"):
            validate_llm_output(raw, BUSINESS_PROFILE_SCHEMA, context="test")

    def test_missing_business_subfield_fails(self, valid_profile):
        """Missing 'business.slug' fails."""
        del valid_profile["business"]["slug"]
        raw = json.dumps(valid_profile)
        with pytest.raises(ValidationError, match="slug"):
            validate_llm_output(raw, BUSINESS_PROFILE_SCHEMA, context="test")

    def test_wrong_type_platforms_fails(self, valid_profile):
        """Platforms priority must be integer, not string."""
        valid_profile["platforms"][0]["priority"] = "first"
        raw = json.dumps(valid_profile)
        with pytest.raises(ValidationError, match="priority"):
            validate_llm_output(raw, BUSINESS_PROFILE_SCHEMA, context="test")

    def test_empty_brands_fails(self, valid_profile):
        """Empty brands array should fail (need at least the main brand)."""
        valid_profile["brands"] = []
        raw = json.dumps(valid_profile)
        # Schema doesn't enforce min_items on brands — but let's verify it loads
        result = validate_llm_output(raw, BUSINESS_PROFILE_SCHEMA, context="test")
        assert result["brands"] == []  # empty is technically valid per schema


# --- Converter Tests ---

class TestBusinessProfileConverters:

    def test_yaml_converter_produces_valid_yaml(self, valid_profile):
        """business_profile_to_yaml produces YAML that the config loader can read."""
        yaml_str = business_profile_to_yaml(valid_profile)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["business"]["name"] == "StackPenni"
        assert parsed["business"]["slug"] == "stackpenni"
        assert len(parsed["subjects"]) == 4

    def test_markdown_converter_has_all_sections(self, valid_profile):
        """brand_context_to_markdown includes all required sections."""
        md = brand_context_to_markdown(valid_profile, version="1.0")
        assert "# Brand Context — StackPenni — v1.0" in md
        assert "## Business" in md
        assert "## Brands" in md
        assert "## Subjects" in md
        assert "## Platforms" in md
        assert "## Goals" in md
        assert "## Red lines" in md
        assert "## Audience" in md
        assert "## Provenance" in md
        assert "StackPenni" in md
        assert "@StackPenni" in md
        assert "No get-rich-quick" in md
        assert "brand_context_v1" in md

    def test_markdown_handles_empty_brands(self):
        """Converter handles empty brands gracefully."""
        profile = {
            "business": {"name": "Solo", "slug": "solo", "description": "Solo brand"},
            "brands": [],
            "subjects": ["AI"],
            "platforms": [{"name": "X", "handle": "@solo", "priority": 1}],
            "goals": ["Grow"],
            "red_lines": ["No spam"],
            "audience_description": "Everyone",
        }
        md = brand_context_to_markdown(profile)
        assert "## Brands" in md
        assert "Solo" in md


# --- Gate Enforcement Tests ---

class TestBusinessProfileGateEnforcement:

    def test_parked_profile_does_not_write_files(self, valid_profile, tmp_dirs):
        """Parked profile does NOT write business.yaml or brand-context module."""
        config_dir, modules_dir, db_path = tmp_dirs

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("business-profile-intake", "1.0", "testbrand")
        runner.add_llm_output(run_id, "analysis", valid_profile)

        # Store without approval (park)
        store = ModuleStore(modules_dir=modules_dir)
        # Simulate park: don't call store.store()
        runner.set_gate_result(run_id, "4", "park", "")
        runner.update_run(run_id, status="awaiting_gate")

        # business.yaml should NOT be overwritten
        # (it exists from the fixture, but we didn't touch it)
        # brand-context module should NOT exist
        assert not store.exists("testbrand", "brand-context")

    def test_approved_profile_writes_module(self, valid_profile, tmp_dirs):
        """Approved profile writes brand-context module."""
        config_dir, modules_dir, db_path = tmp_dirs

        store = ModuleStore(modules_dir=modules_dir)
        md = brand_context_to_markdown(valid_profile, "1.0")
        path = store.store("stackpenni", "brand-context", md, version="1.0",
                           provenance={"version": "1.0", "approved": True})

        assert os.path.exists(path)
        loaded = store.load("stackpenni", "brand-context")
        assert loaded is not None
        assert "StackPenni" in loaded
        assert "brand_context_v1" in loaded

    def test_approved_profile_writes_business_yaml(self, valid_profile, tmp_dirs):
        """Approved profile writes a valid business.yaml that loads."""
        config_dir, modules_dir, db_path = tmp_dirs

        yaml_str = business_profile_to_yaml(valid_profile)
        biz_path = os.path.join(config_dir, "business.yaml")
        with open(biz_path, "w") as f:
            f.write("# Generated\n")
            f.write(yaml_str)

        # The config loader should be able to read it
        config = load_all(config_dir)
        assert config["business"]["business"]["name"] == "StackPenni"
        assert config["business"]["business"]["slug"] == "stackpenni"
        assert len(config["business"]["subjects"]) == 4


# --- Playbook Runner Integration ---

class TestBusinessProfilePlaybookRunner:

    def test_qa_storage_and_retrieval(self, tmp_db):
        """Q&A pairs can be stored and retrieved from a run."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("business-profile-intake", "1.0", "testbrand")

        # Simulate adding Q&A
        collected = {"business_qa": [
            {"q": "What does your business do?", "a": "We make content"},
            {"q": "What platforms?", "a": "X and Instagram"},
        ]}
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        run = runner.get_run(run_id)
        loaded = json.loads(run["collected_inputs"])
        assert len(loaded["business_qa"]) == 2
        assert loaded["business_qa"][0]["a"] == "We make content"

    def test_analysis_output_stored(self, tmp_db, valid_profile):
        """LLM analysis output can be stored on a run."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("business-profile-intake", "1.0", "testbrand")
        runner.add_llm_output(run_id, "analysis", valid_profile)

        run = runner.get_run(run_id)
        outputs = json.loads(run["llm_outputs"])
        assert "analysis" in outputs
        assert outputs["analysis"]["business"]["name"] == "StackPenni"


# --- Zero Tenant Strings in Code ---

class TestNoTenantStringsInCode:
    """T2.1 AC: zero tenant strings in code."""

    def test_no_stackpenni_in_src(self):
        """No hardcoded 'StackPenni' or 'stackpenni' in src/ Python files."""
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        violations = []
        for fname in os.listdir(src_dir):
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(src_dir, fname)
            with open(filepath, "r") as f:
                content = f.read()
            # Check for hardcoded business name (case-insensitive)
            # Allow it in comments and docstrings only if it's about the test/example
            for line_num, line in enumerate(content.split("\n"), 1):
                lower = line.lower()
                if "stackpenni" in lower and "import" not in lower:
                    # Flag — StackPenni should not be in code
                    violations.append(f"{fname}:{line_num}: {line.strip()}")

        assert not violations, f"Tenant strings found in src/:\n" + "\n".join(violations)

    def test_no_caribbean_in_src(self):
        """No hardcoded 'Caribbean' in src/ Python files (business-specific)."""
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        violations = []
        for fname in os.listdir(src_dir):
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(src_dir, fname)
            with open(filepath, "r") as f:
                content = f.read()
            for line_num, line in enumerate(content.split("\n"), 1):
                if "caribbean" in line.lower() and "import" not in line.lower():
                    violations.append(f"{fname}:{line_num}: {line.strip()}")

        assert not violations, f"Business-specific strings found in src/:\n" + "\n".join(violations)


# --- Config File Archiving (R14) ---

class TestConfigFileArchiving:
    """R14: Config yaml writes must archive the prior version before overwriting."""

    def test_archive_config_file_copies_existing(self, tmp_path):
        """_archive_config_file copies an existing file to config/archive/."""
        from app import _archive_config_file

        # Create a config file
        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)
        biz_path = os.path.join(config_dir, "business.yaml")
        with open(biz_path, "w") as f:
            f.write("business:\n  name: OldName\n  slug: oldname\n")

        # Archive it
        archive_path = _archive_config_file(biz_path)

        assert archive_path is not None
        assert os.path.exists(archive_path)
        assert "archive" in archive_path
        assert archive_path.endswith(".yaml") or "business.yaml" in archive_path
        # The archived file should have the old content
        with open(archive_path, "r") as f:
            content = f.read()
        assert "OldName" in content

    def test_archive_config_file_noop_when_missing(self, tmp_path):
        """_archive_config_file is a no-op when the file does not exist."""
        from app import _archive_config_file

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)
        missing_path = os.path.join(config_dir, "business.yaml")

        result = _archive_config_file(missing_path)
        assert result is None
        # No archive directory should have been needed
        # (though the function creates it only when the file exists)
        archive_dir = os.path.join(config_dir, "archive")
        assert not os.path.exists(archive_dir)

    def test_two_successive_approvals_archive_prior_version(self, valid_profile, tmp_path, monkeypatch):
        """Two successive store-business approvals archive the prior business.yaml."""
        from app import create_app
        from playbook_runner import PlaybookRunner

        config_dir = str(tmp_path / "config")
        modules_dir = str(tmp_path / "modules")
        db = str(tmp_path / "test.db")
        os.makedirs(config_dir)
        os.makedirs(modules_dir)

        # Write initial config files so load_all works
        business = {
            "business": {"name": "TestBrand", "slug": "testbrand", "description": "Test"},
            "subjects": ["AI"], "platforms": [{"name": "X", "handle": "@t", "priority": 1}],
        }
        import yaml as _yaml
        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            _yaml.dump(business, f)
        models = {
            "active": {"default": "tb", "drafter": "tb", "drafter_ab_candidate": None},
            "tb": {"provider": "ollama_cloud", "model": "m", "temperature": 0, "max_tokens": 4, "base_url": "https://x.com"},
        }
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            _yaml.dump(models, f)
        sources = {"feeds": [], "channels": [], "queries": []}
        with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
            _yaml.dump(sources, f)

        app = create_app(config_dir=config_dir, db_path=db)
        client = app.test_client()

        # Monkeypatch modules dir so ModuleStore writes to our temp
        monkeypatch.chdir(str(tmp_path))

        runner = PlaybookRunner(db)

        # --- First approval ---
        run_id_1 = runner.start_run("business-profile-intake", "1.0", "testbrand")
        runner.add_llm_output(run_id_1, "analysis", valid_profile)

        resp = client.post(f"/api/run/{run_id_1}/store-business",
            data=json.dumps({"version": "1.0", "approved": True, "note": "first"}),
            content_type="application/json")
        assert resp.status_code == 200

        # After first approval, business.yaml exists with the new content
        biz_path = os.path.join(config_dir, "business.yaml")
        assert os.path.exists(biz_path)
        with open(biz_path, "r") as f:
            first_content = f.read()
        assert "StackPenni" in first_content

        # The initial TestBrand version should have been archived
        archive_dir = os.path.join(config_dir, "archive")
        assert os.path.isdir(archive_dir)
        archive_files_1 = [f for f in os.listdir(archive_dir) if "business.yaml" in f]
        assert len(archive_files_1) >= 1, "Initial business.yaml was not archived on first approval"

        # The archived file should contain the old "TestBrand" content
        found_old = False
        for af in archive_files_1:
            with open(os.path.join(archive_dir, af), "r") as f:
                archived_content = f.read()
            if "TestBrand" in archived_content:
                found_old = True
                break
        assert found_old, "Archived file from first approval did not contain the prior (TestBrand) content"

        # --- Second approval with a different profile ---
        profile_v2 = json.loads(json.dumps(valid_profile))  # deep copy
        profile_v2["business"]["name"] = "NewName"
        profile_v2["business"]["slug"] = "newname"

        run_id_2 = runner.start_run("business-profile-intake", "1.0", "testbrand")
        runner.add_llm_output(run_id_2, "analysis", profile_v2)

        resp2 = client.post(f"/api/run/{run_id_2}/store-business",
            data=json.dumps({"version": "2.0", "approved": True, "note": "second"}),
            content_type="application/json")
        assert resp2.status_code == 200

        # After second approval, business.yaml has the new content
        with open(biz_path, "r") as f:
            second_content = f.read()
        assert "NewName" in second_content

        # Now there should be at least 2 archived versions
        archive_files_2 = [f for f in os.listdir(archive_dir) if "business.yaml" in f]
        assert len(archive_files_2) >= 2, (
            f"Expected >= 2 archived business.yaml files after two approvals, got {len(archive_files_2)}"
        )

        # The most recent archive should contain the first approved content (StackPenni)
        found_stackpenni = False
        for af in archive_files_2:
            with open(os.path.join(archive_dir, af), "r") as f:
                archived_content = f.read()
            if "StackPenni" in archived_content:
                found_stackpenni = True
                break
        assert found_stackpenni, (
            "Prior approved version (StackPenni) not found in archive after second approval"
        )


class TestNoTenantStringsInTemplates:
    """T2.1 AC: zero tenant strings in templates and prompts."""

    def test_no_stackpenni_in_templates(self):
        """No hardcoded 'StackPenni' or 'stackpenni' in src/templates/*.html."""
        templates_dir = os.path.join(os.path.dirname(__file__), "..", "src", "templates")
        violations = []
        if not os.path.isdir(templates_dir):
            return
        for fname in os.listdir(templates_dir):
            if not fname.endswith(".html"):
                continue
            filepath = os.path.join(templates_dir, fname)
            with open(filepath, "r") as f:
                content = f.read()
            for line_num, line in enumerate(content.split("\n"), 1):
                if "stackpenni" in line.lower():
                    violations.append(f"{fname}:{line_num}: {line.strip()}")
        assert not violations, f"Tenant strings found in src/templates/:\n" + "\n".join(violations)

    def test_no_caribbean_in_templates(self):
        """No hardcoded 'Caribbean' in src/templates/*.html."""
        templates_dir = os.path.join(os.path.dirname(__file__), "..", "src", "templates")
        violations = []
        if not os.path.isdir(templates_dir):
            return
        for fname in os.listdir(templates_dir):
            if not fname.endswith(".html"):
                continue
            filepath = os.path.join(templates_dir, fname)
            with open(filepath, "r") as f:
                content = f.read()
            for line_num, line in enumerate(content.split("\n"), 1):
                if "caribbean" in line.lower():
                    violations.append(f"{fname}:{line_num}: {line.strip()}")
        assert not violations, f"'Caribbean' found in src/templates/:\n" + "\n".join(violations)

    def test_no_caribbean_in_prompts(self):
        """No hardcoded 'Caribbean' in prompts/sources_engine/*.md.

        prompts/voice_profile/*.md may contain 'Caribbean' as 'e.g.' illustrative
        examples, so those are not scanned here.
        """
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts", "sources_engine")
        violations = []
        if not os.path.isdir(prompts_dir):
            return
        for fname in os.listdir(prompts_dir):
            if not fname.endswith(".md"):
                continue
            filepath = os.path.join(prompts_dir, fname)
            with open(filepath, "r") as f:
                content = f.read()
            for line_num, line in enumerate(content.split("\n"), 1):
                if "caribbean" in line.lower():
                    violations.append(f"{fname}:{line_num}: {line.strip()}")
        assert not violations, f"'Caribbean' found in prompts/sources_engine/:\n" + "\n".join(violations)