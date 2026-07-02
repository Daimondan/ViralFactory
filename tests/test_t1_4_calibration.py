"""
ViralFactory — T1.4 Calibration Gate Tests

Tests for:
- Calibration sample schema validation (label, emphasis, text required)
- Store voice endpoint (v1.0 on approve, v0.9 on 3-round fallback)
- Module versioning (v1.0 stored, v0.9 path works)
- Gate result recorded on store
"""

import os
import json
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validator import validate_json_schema, validate_llm_output, ValidationError
from module_store import ModuleStore, voice_profile_to_markdown


CALIBRATION_SCHEMA = {
    "type": "object",
    "required": ["samples"],
    "properties": {
        "samples": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["label", "emphasis", "text"],
                "properties": {
                    "label": {"type": "string"},
                    "emphasis": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        },
    },
}


VALID_CALIBRATION = {
    "samples": [
        {"label": "A", "emphasis": "punchy, direct", "text": "Caribbean wealth isn't about the bank. It's about the people. That's it."},
        {"label": "B", "emphasis": "storytelling", "text": "My grandmother used to say 'one hand can't clap.' She meant it literally. That's why I built this."},
        {"label": "C", "emphasis": "conversational", "text": "Look, the receipts are in the culture. Not just in some spreadsheet. That's the whole point."},
    ]
}


class TestCalibrationSchema:

    def test_valid_calibration_accepted(self):
        """Valid calibration samples pass validation."""
        result = validate_json_schema(VALID_CALIBRATION, CALIBRATION_SCHEMA)
        assert len(result["samples"]) == 3
        assert result["samples"][0]["label"] == "A"

    def test_missing_samples_rejected(self):
        """Missing samples array is rejected."""
        with pytest.raises(ValidationError, match="samples"):
            validate_json_schema({}, CALIBRATION_SCHEMA)

    def test_sample_missing_text_rejected(self):
        """A sample without text is rejected."""
        data = json.loads(json.dumps(VALID_CALIBRATION))
        del data["samples"][0]["text"]
        with pytest.raises(ValidationError, match="text"):
            validate_json_schema(data, CALIBRATION_SCHEMA)

    def test_sample_missing_label_rejected(self):
        """A sample without label is rejected."""
        data = json.loads(json.dumps(VALID_CALIBRATION))
        del data["samples"][1]["label"]
        with pytest.raises(ValidationError, match="label"):
            validate_json_schema(data, CALIBRATION_SCHEMA)

    def test_sample_text_must_be_string(self):
        """Sample text must be a string."""
        data = json.loads(json.dumps(VALID_CALIBRATION))
        data["samples"][0]["text"] = 123
        with pytest.raises(ValidationError, match="text"):
            validate_json_schema(data, CALIBRATION_SCHEMA)

    def test_full_json_validation(self):
        """Full pipeline: raw JSON → validated."""
        raw = json.dumps(VALID_CALIBRATION)
        result = validate_llm_output(raw, CALIBRATION_SCHEMA, context="calibration")
        assert len(result["samples"]) == 3


class TestStoreVoiceProfile:

    @pytest.fixture
    def store(self, tmp_path):
        return ModuleStore(modules_dir=str(tmp_path / "modules"))

    def test_store_v1_on_approve(self, store):
        """v1.0 is stored when the user approves."""
        profile = {
            "identity_line": "Test identity",
            "audience": "Test audience",
            "positive_patterns": [{"dimension": "lexicon", "pattern": "test", "evidence": ["quote"]}],
            "dialect_features": [{"feature": "test", "evidence": ["quote"], "do_not_sanitize": True}],
            "anti_patterns": [{"pattern": "none", "evidence_of_absence": "not found"}],
            "tells_checklist": [{"tell": "uniform length", "check": "check it"}],
        }
        md = voice_profile_to_markdown(profile, "TestBrand", "1.0")
        path = store.store("testbrand", "voice-profile", md, "1.0",
                           provenance={"approved": True, "version": "1.0"})
        assert os.path.exists(path)
        loaded = store.load("testbrand", "voice-profile")
        assert "v1.0" in loaded
        assert "Test identity" in loaded

    def test_store_v09_on_fallback(self, store):
        """v0.9 is stored when 3 rounds don't converge."""
        profile = {
            "identity_line": "Test identity",
            "audience": "Test audience",
            "positive_patterns": [{"dimension": "lexicon", "pattern": "test", "evidence": ["quote"]}],
            "dialect_features": [{"feature": "test", "evidence": ["quote"], "do_not_sanitize": True}],
            "anti_patterns": [{"pattern": "none", "evidence_of_absence": "not found"}],
            "tells_checklist": [{"tell": "uniform length", "check": "check it"}],
        }
        md = voice_profile_to_markdown(profile, "TestBrand", "0.9")
        path = store.store("testbrand", "voice-profile", md, "0.9",
                           provenance={"approved": False, "version": "0.9",
                                      "note": "3 rounds did not converge — refine via Feedback Log"})
        assert os.path.exists(path)
        loaded = store.load("testbrand", "voice-profile")
        assert "v0.9" in loaded

    def test_v09_then_v10_version_history(self, store):
        """v0.9 stored first, then v1.0 — both visible in version history."""
        profile = {
            "identity_line": "Test", "audience": "Test",
            "positive_patterns": [], "dialect_features": [],
            "anti_patterns": [], "tells_checklist": [],
        }

        # First store v0.9
        md09 = voice_profile_to_markdown(profile, "Brand", "0.9")
        store.store("brand", "voice-profile", md09, "0.9")

        # Then store v1.0 (after refinement)
        md10 = voice_profile_to_markdown(profile, "Brand", "1.0")
        store.store("brand", "voice-profile", md10, "1.0")

        # Current is v1.0
        current = store.load("brand", "voice-profile")
        assert "v1.0" in current

        # v0.9 is archived
        versions = store.list_versions("brand", "voice-profile")
        assert len(versions) >= 1
        assert any(v["version"] == "0.9" for v in versions)


class TestFlaskCalibration:

    def test_calibrate_page_loads(self):
        """The calibration page loads."""
        from app import create_app
        app = create_app(config_dir="config", db_path="data/viralfactory_test.db")
        client = app.test_client()
        resp = client.get("/onboard/voice-profile-builder/1/calibrate")
        assert resp.status_code == 200
        assert b"Voice Calibration" in resp.data

    def test_store_voice_without_profile(self):
        """Storing without a profile returns error."""
        from app import create_app
        db = "data/viralfactory_test.db"
        if os.path.exists(db):
            os.unlink(db)
        app = create_app(config_dir="config", db_path=db)
        client = app.test_client()

        # No run exists, so should get 404
        resp = client.post("/api/run/999/store-voice",
            data=json.dumps({"version": "1.0", "approved": True}),
            content_type="application/json")
        assert resp.status_code == 404

    def test_store_voice_parked_does_not_write_module(self, tmp_path, monkeypatch):
        """R1: POST store-voice with approved=false must NOT write a module file."""
        from app import create_app
        from playbook_runner import PlaybookRunner

        db = str(tmp_path / "test.db")
        # Use absolute config path so chdir doesn't break it
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        app = create_app(config_dir=config_dir, db_path=db)
        client = app.test_client()

        # Run from tmp_path so the hardcoded "modules" dir lands here
        monkeypatch.chdir(tmp_path)

        runner = PlaybookRunner(db)
        run_id = runner.start_run("voice-profile-builder", "1.0", "testbrand")
        runner.add_llm_output(run_id, "3", {
            "identity_line": "Test",
            "audience": "Test",
            "positive_patterns": [],
            "dialect_features": [],
            "anti_patterns": [],
            "tells_checklist": [],
        })

        # POST with approved=false (park)
        resp = client.post(f"/api/run/{run_id}/store-voice",
            data=json.dumps({"version": "1.0", "approved": False, "note": "needs work"}),
            content_type="application/json")

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["approved"] is False
        assert "path" not in body

        # No module file should exist on disk
        modules_path = tmp_path / "modules"
        assert not modules_path.exists(), \
            "Module directory was created even though approved=false — gate bypass!"

    def test_store_voice_approved_writes_module(self, tmp_path, monkeypatch):
        """R1 companion: POST store-voice with approved=true DOES write the module."""
        from app import create_app
        from playbook_runner import PlaybookRunner

        db = str(tmp_path / "test.db")
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        app = create_app(config_dir=config_dir, db_path=db)
        client = app.test_client()

        monkeypatch.chdir(tmp_path)

        runner = PlaybookRunner(db)
        run_id = runner.start_run("voice-profile-builder", "1.0", "testbrand")
        runner.add_llm_output(run_id, "3", {
            "identity_line": "Test",
            "audience": "Test",
            "positive_patterns": [],
            "dialect_features": [],
            "anti_patterns": [],
            "tells_checklist": [],
        })

        resp = client.post(f"/api/run/{run_id}/store-voice",
            data=json.dumps({"version": "1.0", "approved": True, "note": "looks good"}),
            content_type="application/json")

        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["approved"] is True
        assert "path" in body
        assert os.path.exists(body["path"]), "Module file should exist when approved=true"

    # Cleanup
    @pytest.fixture(autouse=True)
    def cleanup(self):
        db = "data/viralfactory_test.db"
        if os.path.exists(db):
            os.unlink(db)
        yield
        if os.path.exists(db):
            os.unlink(db)