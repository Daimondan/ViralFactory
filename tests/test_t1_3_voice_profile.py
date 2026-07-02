"""
ViralFactory — T1.3 Voice Profile Tests

Tests for:
- VOICE_PROFILE_SCHEMA: validates correct output, rejects missing evidence
- voice_profile_to_markdown: converts JSON to the fixed markdown schema
- ModuleStore: stores, loads, versions, archives modules
- Evidence enforcement: every finding must have verbatim evidence (validator rejects without it)
"""

import os
import json
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_store import (
    ModuleStore, VOICE_PROFILE_SCHEMA, voice_profile_to_markdown,
    generate_gate_token,
)
from playbook_runner import PlaybookRunner
from validator import validate_json_schema, validate_llm_output, ValidationError


# --- Valid Voice Profile fixture ---

VALID_VOICE_PROFILE = {
    "identity_line": "A Caribbean entrepreneur speaking to peers about wealth, AI, and culture",
    "audience": "Caribbean professionals and entrepreneurs interested in AI and wealth-building",
    "positive_patterns": [
        {
            "dimension": "lexicon",
            "pattern": "Uses 'receipts' metaphorically to mean proof/evidence",
            "evidence": ["The receipts are in the culture", "Show me the receipts"],
        },
        {
            "dimension": "rhythm",
            "pattern": "Short punchy sentences after longer ones",
            "evidence": ["That's why I started StackPenni. The receipts are Caribbean."],
        },
        {
            "dimension": "openings",
            "pattern": "Starts with a bold claim",
            "evidence": ["Caribbean wealth isn't just about money in the bank"],
        },
    ],
    "dialect_features": [
        {
            "feature": "Bajan 'cyan' for 'can't'",
            "evidence": ["I cyan believe he do dat"],
            "do_not_sanitize": True,
        },
        {
            "feature": "'yuh know' as a tag question",
            "evidence": ["Is real bajan ting, yuh know?"],
            "do_not_sanitize": True,
        },
    ],
    "anti_patterns": [
        {
            "pattern": "Never uses corporate buzzwords like 'synergy' or 'leverage'",
            "evidence_of_absence": "No instances of corporate jargon across the entire corpus",
        },
    ],
    "tells_checklist": [
        {"tell": "Uniform sentence length", "check": "Check if all sentences are the same length"},
        {"tell": "Announced transitions", "check": "Check for 'furthermore', 'additionally', 'moreover'"},
        {"tell": "Generic conclusions", "check": "Check for 'in conclusion' or 'ultimately'"},
        {"tell": "User-specific: no 'synergy'", "check": "This person never uses the word synergy"},
    ],
}


# --- Schema Validation Tests ---

class TestVoiceProfileSchema:

    def test_valid_profile_accepted(self):
        """A valid Voice Profile passes schema validation."""
        result = validate_json_schema(VALID_VOICE_PROFILE, VOICE_PROFILE_SCHEMA)
        assert result["identity_line"]
        assert len(result["positive_patterns"]) == 3
        assert len(result["dialect_features"]) == 2

    def test_missing_identity_line_rejected(self):
        """Missing identity_line is rejected."""
        profile = {k: v for k, v in VALID_VOICE_PROFILE.items() if k != "identity_line"}
        with pytest.raises(ValidationError, match="identity_line"):
            validate_json_schema(profile, VOICE_PROFILE_SCHEMA)

    def test_missing_positive_patterns_rejected(self):
        """Missing positive_patterns is rejected."""
        profile = {k: v for k, v in VALID_VOICE_PROFILE.items() if k != "positive_patterns"}
        with pytest.raises(ValidationError, match="positive_patterns"):
            validate_json_schema(profile, VOICE_PROFILE_SCHEMA)

    def test_pattern_without_evidence_rejected(self):
        """A positive pattern without evidence is rejected."""
        profile = json.loads(json.dumps(VALID_VOICE_PROFILE))
        del profile["positive_patterns"][0]["evidence"]
        with pytest.raises(ValidationError, match="evidence"):
            validate_json_schema(profile, VOICE_PROFILE_SCHEMA)

    def test_dialect_without_do_not_sanitize_rejected(self):
        """A dialect feature without do_not_sanitize is rejected."""
        profile = json.loads(json.dumps(VALID_VOICE_PROFILE))
        del profile["dialect_features"][0]["do_not_sanitize"]
        with pytest.raises(ValidationError, match="do_not_sanitize"):
            validate_json_schema(profile, VOICE_PROFILE_SCHEMA)

    def test_dialect_must_be_boolean(self):
        """do_not_sanitize must be a boolean."""
        profile = json.loads(json.dumps(VALID_VOICE_PROFILE))
        profile["dialect_features"][0]["do_not_sanitize"] = "yes"
        with pytest.raises(ValidationError, match="do_not_sanitize"):
            validate_json_schema(profile, VOICE_PROFILE_SCHEMA)

    def test_tells_checklist_required(self):
        """Tells checklist is required."""
        profile = {k: v for k, v in VALID_VOICE_PROFILE.items() if k != "tells_checklist"}
        with pytest.raises(ValidationError, match="tells_checklist"):
            validate_json_schema(profile, VOICE_PROFILE_SCHEMA)

    def test_full_llm_output_validation(self):
        """Full validation pipeline works on a valid voice profile JSON string."""
        raw = json.dumps(VALID_VOICE_PROFILE)
        result = validate_llm_output(raw, VOICE_PROFILE_SCHEMA, context="voice profile")
        assert result["identity_line"]
        assert len(result["positive_patterns"]) == 3


# --- Markdown Conversion Tests ---

class TestVoiceProfileMarkdown:

    def test_markdown_has_fixed_headings(self):
        """The markdown has the fixed headings the drafter depends on."""
        md = voice_profile_to_markdown(VALID_VOICE_PROFILE, "StackPenni", "1.0")
        assert "# Voice Profile — StackPenni — v1.0" in md
        assert "## Identity line" in md
        assert "## Audience" in md
        assert "## Positive patterns" in md
        assert "## Dialect & register" in md
        assert "## Anti-patterns" in md
        assert "## Tells Checklist" in md
        assert "## Provenance" in md

    def test_markdown_contains_evidence(self):
        """Evidence quotes appear in the markdown."""
        md = voice_profile_to_markdown(VALID_VOICE_PROFILE, "StackPenni", "1.0")
        assert "The receipts are in the culture" in md
        assert "I cyan believe he do dat" in md

    def test_markdown_contains_dialect_marker(self):
        """Dialect features are marked DO NOT SANITIZE."""
        md = voice_profile_to_markdown(VALID_VOICE_PROFILE, "StackPenni", "1.0")
        assert "DO NOT SANITIZE" in md

    def test_markdown_contains_version(self):
        """Version appears in the markdown."""
        md = voice_profile_to_markdown(VALID_VOICE_PROFILE, "StackPenni", "1.0")
        assert "v1.0" in md
        assert "Version: 1.0" in md


# --- Module Store Tests ---

class TestModuleStore:

    @pytest.fixture
    def tmp_setup(self, tmp_path):
        """Create a ModuleStore and DB path with a helper to make approved runs."""
        db_path = str(tmp_path / "test.db")
        modules_dir = str(tmp_path / "modules")
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)

        def make_approved_run():
            runner = PlaybookRunner(db_path)
            run_id = runner.start_run("test", "1.0", "stackpenni")
            runner.set_gate_result(run_id, "1", "approve", "test")
            token = generate_gate_token(run_id)
            return run_id, token

        return store, make_approved_run

    def test_store_module(self, tmp_setup):
        """A module can be stored and loaded."""
        store, make_approved_run = tmp_setup
        run_id, token = make_approved_run()
        path = store.store("stackpenni", "voice-profile", "# Voice Profile\n\nTest content", "1.0",
                           gate_token=token, run_id=run_id)
        assert os.path.exists(path)
        loaded = store.load("stackpenni", "voice-profile")
        assert "Voice Profile" in loaded
        assert "Test content" in loaded

    def test_module_exists(self, tmp_setup):
        """exists() correctly reports module presence."""
        store, make_approved_run = tmp_setup
        assert not store.exists("stackpenni", "voice-profile")
        run_id, token = make_approved_run()
        store.store("stackpenni", "voice-profile", "content", "1.0",
                    gate_token=token, run_id=run_id)
        assert store.exists("stackpenni", "voice-profile")

    def test_version_archived_on_overwrite(self, tmp_setup):
        """When a module is overwritten, the previous version is archived."""
        store, make_approved_run = tmp_setup

        run_id, token = make_approved_run()
        store.store("stackpenni", "voice-profile", "# Voice Profile — StackPenni — v1.0\n\nv1 content", "1.0",
                    gate_token=token, run_id=run_id)

        run_id2, token2 = make_approved_run()
        store.store("stackpenni", "voice-profile", "# Voice Profile — StackPenni — v2.0\n\nv2 content", "2.0",
                    gate_token=token2, run_id=run_id2)

        # Current version is v2
        current = store.load("stackpenni", "voice-profile")
        assert "v2 content" in current

        # v1 is archived
        versions = store.list_versions("stackpenni", "voice-profile")
        assert len(versions) >= 1
        assert versions[0]["version"] == "1.0"

    def test_list_modules(self, tmp_setup):
        """list_modules returns all modules for a business."""
        store, make_approved_run = tmp_setup

        run_id, token = make_approved_run()
        store.store("stackpenni", "voice-profile", "content", "1.0",
                    gate_token=token, run_id=run_id)

        run_id2, token2 = make_approved_run()
        store.store("stackpenni", "viral-patterns", "content", "1.0",
                    gate_token=token2, run_id=run_id2)

        modules = store.list_modules("stackpenni")
        assert "voice-profile" in modules
        assert "viral-patterns" in modules

    def test_provenance_stored(self, tmp_setup):
        """Provenance is stored alongside the module."""
        store, make_approved_run = tmp_setup

        run_id, token = make_approved_run()
        prov = {"sources": ["whatsapp export"], "calibration": "approved on round 1"}
        store.store("stackpenni", "voice-profile", "content", "1.0",
                    provenance=prov, gate_token=token, run_id=run_id)
        # Provenance file exists
        prov_path = os.path.join(os.path.dirname(store._module_path("stackpenni", "voice-profile")),
                                 "voice-profile_provenance.json")
        assert os.path.exists(prov_path)
        loaded = json.loads(open(prov_path).read())
        assert loaded["calibration"] == "approved on round 1"