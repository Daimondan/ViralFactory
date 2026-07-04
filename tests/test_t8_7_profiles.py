"""
Tests for T8.7: AI Profiles.

AC:
- config/profiles.yaml exists with Researcher, Drafter, Analyst profiles
- Provenance rows carry the producing profile
- LLMAdapter.complete() accepts profile parameter
- Profile resolution test covers all three profiles
"""
import os
import json
import pytest
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    return PipelineStore(db_path=db_path)


class TestProfilesConfigExists:
    """T8.7: config/profiles.yaml exists with all three profiles."""

    def test_profiles_yaml_exists(self):
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.yaml")
        assert os.path.exists(path)

    def test_profiles_yaml_has_three_profiles(self):
        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.yaml")
        with open(path) as f:
            config = yaml.safe_load(f)
        profiles = config.get("profiles", {})
        assert "researcher" in profiles
        assert "drafter" in profiles
        assert "analyst" in profiles

    def test_researcher_profile_has_prompts(self):
        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.yaml")
        with open(path) as f:
            config = yaml.safe_load(f)
        researcher = config["profiles"]["researcher"]
        assert "prompts" in researcher
        assert "temperature" in researcher
        assert researcher["temperature"] == "generative"

    def test_drafter_profile_has_prompts(self):
        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.yaml")
        with open(path) as f:
            config = yaml.safe_load(f)
        drafter = config["profiles"]["drafter"]
        assert "prompts" in drafter
        assert drafter["temperature"] == "generative"

    def test_analyst_profile_temp_zero(self):
        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.yaml")
        with open(path) as f:
            config = yaml.safe_load(f)
        analyst = config["profiles"]["analyst"]
        assert analyst["temperature"] == "judgment"

    def test_profiles_have_descriptions(self):
        import yaml
        path = os.path.join(os.path.dirname(__file__), "..", "config", "profiles.yaml")
        with open(path) as f:
            config = yaml.safe_load(f)
        for name in ["researcher", "drafter", "analyst"]:
            assert "description" in config["profiles"][name]


class TestProvenanceProfileColumn:
    """T8.7: Provenance table has profile column and log() accepts it."""

    def test_profile_column_exists(self, db_path):
        from provenance import ProvenanceLog
        prov = ProvenanceLog(db_path)
        import sqlite3
        conn = sqlite3.connect(db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(provenance)").fetchall()]
        conn.close()
        assert "profile" in cols

    def test_log_with_profile(self, db_path):
        """ProvenanceLog.log() accepts and stores profile."""
        from provenance import ProvenanceLog
        prov = ProvenanceLog(db_path)
        prov.log(
            input_hash="test_hash",
            prompt_file="test/prompt.md",
            prompt_version="1.0",
            model="test-model",
            provider="test",
            raw_output='{"test": true}',
            validated_output={"test": True},
            validator_verdict="valid",
            context="test call",
            profile="researcher",
        )
        rows = prov.get_by_hash("test_hash")
        assert len(rows) == 1
        assert rows[0]["profile"] == "researcher"

    def test_log_without_profile_defaults_null(self, db_path):
        """ProvenanceLog.log() without profile stores NULL."""
        from provenance import ProvenanceLog
        prov = ProvenanceLog(db_path)
        prov.log(
            input_hash="test_hash_2",
            prompt_file="test/prompt.md",
            prompt_version="1.0",
            model="test-model",
            provider="test",
            raw_output='{"test": true}',
            validated_output={"test": True},
            validator_verdict="valid",
            context="test call",
        )
        rows = prov.get_by_hash("test_hash_2")
        assert len(rows) == 1
        assert rows[0]["profile"] is None


class TestLLMAdapterProfileParameter:
    """T8.7: LLMAdapter.complete() accepts profile parameter."""

    def test_complete_accepts_profile(self, db_path):
        """LLMAdapter.complete() has profile in its signature."""
        import inspect
        from llm_adapter import LLMAdapter
        sig = inspect.signature(LLMAdapter.complete)
        assert "profile" in sig.parameters
        assert sig.parameters["profile"].default is None


class TestPipelineCallsUseProfiles:
    """T8.7: Pipeline LLM calls declare their profile."""

    def test_ideas_generate_passes_researcher(self):
        """ideas_generate route passes profile='researcher'."""
        app_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(app_path) as f:
            content = f.read()
        # The ideas_generate route should pass profile="researcher"
        assert 'profile="researcher"' in content

    def test_draft_generate_passes_drafter(self):
        """draft_generate route passes profile='drafter'."""
        app_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(app_path) as f:
            content = f.read()
        assert 'profile="drafter"' in content

    def test_produce_chain_passes_drafter(self):
        """produce_chain module passes profile='drafter'."""
        chain_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(chain_path) as f:
            content = f.read()
        assert 'profile="drafter"' in content