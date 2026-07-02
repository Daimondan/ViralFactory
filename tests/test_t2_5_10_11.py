"""
ViralFactory — T2.5 + T2.10 + T2.11 Tests

T2.5: Module store schema-check on load + version history visible
T2.10: Security fixes (materials column allowlist + llm_adapter single-pass substitution)
T2.11: Provenance gains business_slug column
"""

import json
import os
import tempfile
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_store import ModuleStore, generate_gate_token
from playbook_runner import PlaybookRunner
from validator import validate_llm_output, ValidationError


# --- Fixtures ---

@pytest.fixture
def tmp_dirs():
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)
            business = {
                "business": {"name": "T", "slug": "testbrand", "description": "T"},
                "subjects": ["AI"],
                "platforms": [{"name": "X", "handle": "@t", "priority": 1}],
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


# ── T2.5: Schema-check on load ──

class TestSchemaCheckOnLoad:

    def test_valid_schema_loads(self, tmp_dirs):
        """Module with valid schema marker loads via load_validated()."""
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("test", "1.0", "testbrand")
        runner.set_gate_result(run_id, "1", "approve", "")
        token = generate_gate_token(run_id)

        content = "# Voice Profile — v1.0\n\n## Identity\nTest\n\n## Provenance\n- Schema: voice_profile_v1"
        store.store("testbrand", "voice-profile", content, gate_token=token, run_id=run_id)

        loaded = store.load_validated("testbrand", "voice-profile")
        assert loaded is not None
        assert "voice_profile_v1" in loaded

    def test_missing_schema_marker_raises(self, tmp_dirs):
        """Module without schema marker raises ValueError."""
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("test", "1.0", "testbrand")
        runner.set_gate_result(run_id, "1", "approve", "")
        token = generate_gate_token(run_id)

        content = "# Bad Module\n\nNo schema marker here"
        store.store("testbrand", "bad-module", content, gate_token=token, run_id=run_id)

        with pytest.raises(ValueError, match="no schema marker"):
            store.load_validated("testbrand", "bad-module")

    def test_unknown_schema_raises(self, tmp_dirs):
        """Module with unknown schema name raises ValueError."""
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("test", "1.0", "testbrand")
        runner.set_gate_result(run_id, "1", "approve", "")
        token = generate_gate_token(run_id)

        content = "# Module\n\n## Provenance\n- Schema: unknown_schema_v999"
        store.store("testbrand", "unknown", content, gate_token=token, run_id=run_id)

        with pytest.raises(ValueError, match="unknown schema"):
            store.load_validated("testbrand", "unknown")

    def test_nonexistent_module_returns_none(self, tmp_dirs):
        """Loading a module that doesn't exist returns None, not an error."""
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert store.load_validated("testbrand", "nonexistent") is None

    def test_version_history_visible(self, tmp_dirs):
        """Version history is retrievable after overwrites."""
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("test", "1.0", "testbrand")
        runner.set_gate_result(run_id, "1", "approve", "")
        token = generate_gate_token(run_id)

        # Write v1.0
        content_v1 = "# Module — v1.0\n\n## Provenance\n- Schema: voice_profile_v1"
        store.store("testbrand", "voice-profile", content_v1, version="1.0",
                    gate_token=token, run_id=run_id)

        # Write v2.0 (archives v1.0)
        content_v2 = "# Module — v2.0\n\n## Provenance\n- Schema: voice_profile_v1"
        store.store("testbrand", "voice-profile", content_v2, version="2.0",
                    gate_token=token, run_id=run_id)

        # Version history should show 1 archived version
        versions = store.list_versions("testbrand", "voice-profile")
        assert len(versions) == 1
        assert versions[0]["version"] == "1.0"


# ── T2.10: Security fixes ──

class TestMaterialsColumnAllowlist:

    def test_valid_field_accepted(self, tmp_dirs):
        """Allowed field names are accepted by _update_field."""
        from materials import MaterialsIntake
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path)
        mid = intake.ingest_text("test content", business_slug="testbrand")
        intake._update_field(mid, "normalized_content", "normalized text")
        material = intake.get_material(mid)
        assert material["normalized_content"] == "normalized text"

    def test_invalid_field_rejected(self, tmp_dirs):
        """Non-allowlisted field names raise ValueError."""
        from materials import MaterialsIntake
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path)
        mid = intake.ingest_text("test content", business_slug="testbrand")
        with pytest.raises(ValueError, match="Invalid field name"):
            intake._update_field(mid, "id; DROP TABLE materials; --", "evil")


class TestSinglePassSubstitution:

    def test_no_double_substitution(self):
        """Variable values containing {other_var} are not re-interpreted."""
        from llm_adapter import LLMAdapter
        adapter = LLMAdapter.__new__(LLMAdapter)  # bypass __init__
        template = "Hello {name}, your code is {code}"
        variables = {"name": "{code}", "code": "12345"}
        result = adapter._render_prompt(template, variables)
        # {name} should be replaced with literal "{code}" — not re-interpreted
        assert result == "Hello {code}, your code is 12345"

    def test_normal_substitution_works(self):
        from llm_adapter import LLMAdapter
        adapter = LLMAdapter.__new__(LLMAdapter)
        template = "Business: {business_name}, Subjects: {subjects}"
        variables = {"business_name": "TestCo", "subjects": "AI, wealth"}
        result = adapter._render_prompt(template, variables)
        assert "TestCo" in result
        assert "AI, wealth" in result

    def test_unknown_placeholder_preserved(self):
        from llm_adapter import LLMAdapter
        adapter = LLMAdapter.__new__(LLMAdapter)
        template = "Hello {name}, unknown: {unknown_var}"
        variables = {"name": "Test"}
        result = adapter._render_prompt(template, variables)
        assert "Test" in result
        assert "{unknown_var}" in result  # preserved as-is


# ── T2.11: Provenance business_slug ──

class TestProvenanceBusinessSlug:

    def test_business_slug_column_exists(self, tmp_dirs):
        """The provenance table has a business_slug column."""
        from provenance import ProvenanceLog
        config_dir, modules_dir, db_path = tmp_dirs
        prov = ProvenanceLog(db_path)
        cols = [row[1] for row in prov.conn.execute("PRAGMA table_info(provenance)").fetchall()]
        assert "business_slug" in cols
        prov.close()

    def test_log_with_business_slug(self, tmp_dirs):
        """Provenance log accepts and stores business_slug."""
        from provenance import ProvenanceLog
        config_dir, modules_dir, db_path = tmp_dirs
        prov = ProvenanceLog(db_path)
        prov.log(
            input_hash="abc123",
            prompt_file="test/prompt.md",
            prompt_version="1.0",
            model="test-model",
            provider="ollama_cloud",
            raw_output="{}",
            validated_output={"key": "value"},
            validator_verdict="valid",
            context="test",
            business_slug="testbrand",
        )
        rows = prov.conn.execute(
            "SELECT * FROM provenance WHERE business_slug = ?", ("testbrand",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["business_slug"] == "testbrand"
        prov.close()

    def test_log_without_business_slug(self, tmp_dirs):
        """Provenance log works without business_slug (backward compat)."""
        from provenance import ProvenanceLog
        config_dir, modules_dir, db_path = tmp_dirs
        prov = ProvenanceLog(db_path)
        prov.log(
            input_hash="abc123",
            prompt_file="test/prompt.md",
            prompt_version="1.0",
            model="test-model",
            provider="ollama_cloud",
            raw_output="{}",
            validated_output={"key": "value"},
            validator_verdict="valid",
            context="test",
        )
        rows = prov.conn.execute(
            "SELECT * FROM provenance WHERE input_hash = ?", ("abc123",)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["business_slug"] is None
        prov.close()

    def test_migration_adds_column(self, tmp_dirs):
        """Existing databases without business_slug get migrated."""
        import sqlite3
        from provenance import ProvenanceLog
        config_dir, modules_dir, db_path = tmp_dirs

        # Create a provenance table WITHOUT business_slug (simulating old DB)
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE provenance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                input_hash TEXT NOT NULL,
                prompt_file TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT NOT NULL,
                raw_output TEXT,
                validated_output TEXT,
                validator_verdict TEXT NOT NULL,
                validator_errors TEXT,
                context TEXT,
                temperature REAL,
                latency_ms INTEGER,
                cached INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        conn.close()

        # Now initialize ProvenanceLog — should migrate
        prov = ProvenanceLog(db_path)
        cols = [row[1] for row in prov.conn.execute("PRAGMA table_info(provenance)").fetchall()]
        assert "business_slug" in cols
        prov.close()