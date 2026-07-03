"""
ViralFactory — Materials Library Tests

CORRECTION-final-assembly-and-materials-editing-v1.0 Part 2

Tests:
- Edit saves to normalized_content, raw_content untouched, edit logged
- Exclude drops material from corpus; toggle back restores it
- Restore to original re-copies raw → normalized
- Corrected text reaches a subsequent drafting package (get_corpus returns edited content)
- Flask routes: /materials, /materials/<id>, edit/exclude/restore APIs
"""

import os
import json
import tempfile
import pytest
import yaml
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from materials import MaterialsIntake


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
def tmp_upload_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def intake(tmp_db, tmp_upload_dir):
    return MaterialsIntake(db_path=tmp_db, upload_dir=tmp_upload_dir)


@pytest.fixture
def tmp_dirs():
    """Config + modules + db for Flask app tests."""
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)
            business = {
                "business": {"name": "Test", "slug": "testbrand", "description": "T"},
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


# --- Unit tests ---

class TestSaveEdit:
    """Editing normalized_content saves correctly, raw untouched, edit logged."""

    def test_edit_updates_normalized_content(self, intake):
        """Save edit writes to normalized_content."""
        mid = intake.ingest_text(
            "Caribbean wealth is about community.",
            business_slug="test", material_type="pasted", channel="social_post",
        )
        updated = intake.save_edit(mid, "Caribbean wealth is about community and culture.")
        assert "and culture" in updated["normalized_content"]

    def test_raw_content_untouched_after_edit(self, intake):
        """raw_content is never modified by save_edit."""
        original_text = "Caribbean wealth is about community."
        mid = intake.ingest_text(
            original_text, business_slug="test",
            material_type="pasted", channel="social_post",
        )
        intake.save_edit(mid, "Completely different text.")
        mat = intake.get_material(mid)
        assert mat["raw_content"] == original_text

    def test_edit_logged_in_material_edits(self, intake):
        """Each edit creates a row in material_edits."""
        mid = intake.ingest_text("Original.", business_slug="test")
        intake.save_edit(mid, "First edit.")
        intake.save_edit(mid, "Second edit.")
        history = intake.get_edit_history(mid)
        assert len(history) == 2
        # Newest first
        assert history[0]["edited_at"] >= history[1]["edited_at"]

    def test_word_count_recomputed_on_edit(self, intake):
        """word_count updates to reflect new content."""
        mid = intake.ingest_text("one two three", business_slug="test")
        assert intake.get_material(mid)["word_count"] == 3
        intake.save_edit(mid, "one two three four five six")
        assert intake.get_material(mid)["word_count"] == 6


class TestExclude:
    """Excluded materials drop out of corpus but are never deleted."""

    def test_exclude_drops_from_corpus(self, intake):
        """Excluded material disappears from get_corpus."""
        mid = intake.ingest_text("Sample text here.", run_id=100, business_slug="test")
        # Confirm it's in corpus
        corpus = intake.get_corpus(100)
        assert len(corpus["samples"]) == 1
        assert corpus["total_words"] > 0

        # Exclude it
        intake.toggle_exclude(mid, True)
        corpus = intake.get_corpus(100)
        assert len(corpus["samples"]) == 0
        assert corpus["total_words"] == 0

    def test_exclude_does_not_delete(self, intake):
        """Excluded material still exists in the database."""
        mid = intake.ingest_text("Sample text.", run_id=100, business_slug="test")
        intake.toggle_exclude(mid, True)
        mat = intake.get_material(mid)
        assert mat is not None
        assert mat["excluded"] == 1

    def test_toggle_back_restores_to_corpus(self, intake):
        """Toggling excluded back to False restores it to corpus."""
        mid = intake.ingest_text("Sample text.", run_id=100, business_slug="test")
        intake.toggle_exclude(mid, True)
        assert len(intake.get_corpus(100)["samples"]) == 0

        intake.toggle_exclude(mid, False)
        corpus = intake.get_corpus(100)
        assert len(corpus["samples"]) == 1
        assert corpus["total_words"] > 0


class TestRestoreToRaw:
    """Restore to original re-copies raw → normalized."""

    def test_restore_undoes_edits(self, intake):
        """Restore sets normalized_content back to raw_content."""
        original = "Original text content here."
        mid = intake.ingest_text(original, business_slug="test")
        intake.save_edit(mid, "Edited content that's different.")
        assert "Edited" in intake.get_material(mid)["normalized_content"]

        restored = intake.restore_to_raw(mid)
        assert restored["normalized_content"] == original

    def test_restore_logged_as_edit(self, intake):
        """Restore is logged in material_edits like any other edit."""
        mid = intake.ingest_text("Original.", business_slug="test")
        intake.save_edit(mid, "Edited.")
        intake.restore_to_raw(mid)
        history = intake.get_edit_history(mid)
        assert len(history) == 2  # one edit + one restore


class TestEditReachesDraftingPackage:
    """An edit to a material changes what a subsequent draft call receives."""

    def test_corrected_text_appears_in_corpus(self, intake):
        """get_corpus returns the edited content, not the original."""
        mid = intake.ingest_text(
            "The qwick brown fox jumps.",
            run_id=200, business_slug="test",
        )
        # Fix the typo
        intake.save_edit(mid, "The quick brown fox jumps.")
        corpus = intake.get_corpus(200)
        assert len(corpus["samples"]) == 1
        assert "quick" in corpus["samples"][0]["content_preview"]
        assert "qwick" not in corpus["samples"][0]["content_preview"]


# --- Flask route tests ---

class TestMaterialsRoutes:
    """Flask routes for the Materials Library."""

    def test_materials_page_loads(self, tmp_dirs):
        """GET /materials loads with 200."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.get("/materials")
        assert resp.status_code == 200

    def test_materials_page_shows_materials(self, tmp_dirs):
        """Materials page lists uploaded materials."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        # Add a material first
        intake = MaterialsIntake(db_path=db_path)
        intake.ingest_text("Test material content.", business_slug="testbrand",
                           material_type="pasted", channel="social_post")
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.get("/materials")
        assert resp.status_code == 200
        assert b"Test material content" in resp.data

    def test_material_detail_page_loads(self, tmp_dirs):
        """GET /materials/<id> loads with 200."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path=db_path)
        mid = intake.ingest_text("Detail content here.", business_slug="testbrand")
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.get(f"/materials/{mid}")
        assert resp.status_code == 200
        assert b"Detail content here" in resp.data

    def test_material_detail_404(self, tmp_dirs):
        """GET /materials/999 returns 404."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.get("/materials/999")
        assert resp.status_code == 404

    def test_api_edit_saves_content(self, tmp_dirs):
        """POST /api/materials/<id>/edit saves normalized_content."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path=db_path)
        mid = intake.ingest_text("Original content.", business_slug="testbrand")
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.post(f"/api/materials/{mid}/edit",
                           json={"content": "Edited via API."})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        # Verify it persisted
        mat = intake.get_material(mid)
        assert mat["normalized_content"] == "Edited via API."
        assert mat["raw_content"] == "Original content."

    def test_api_exclude_toggles_flag(self, tmp_dirs):
        """POST /api/materials/<id>/exclude toggles the excluded flag."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path=db_path)
        mid = intake.ingest_text("Exclude me.", business_slug="testbrand",
                                 run_id=300)
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.post(f"/api/materials/{mid}/exclude",
                           json={"excluded": True})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["excluded"] is True
        # Verify corpus is empty now
        corpus = intake.get_corpus(300)
        assert len(corpus["samples"]) == 0

    def test_api_restore_works(self, tmp_dirs):
        """POST /api/materials/<id>/restore restores to raw."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path=db_path)
        mid = intake.ingest_text("Original.", business_slug="testbrand")
        intake.save_edit(mid, "Modified.")
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.post(f"/api/materials/{mid}/restore", json={})
        assert resp.status_code == 200
        mat = intake.get_material(mid)
        assert mat["normalized_content"] == "Original."

    def test_api_edit_404_for_missing(self, tmp_dirs):
        """POST /api/materials/999/edit returns 404."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.post("/api/materials/999/edit", json={"content": "test"})
        assert resp.status_code == 404

    def test_materials_page_shows_excluded_badge(self, tmp_dirs):
        """Excluded materials show an 'Excluded' badge on the list page."""
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        intake = MaterialsIntake(db_path=db_path)
        mid = intake.ingest_text("Will be excluded.", business_slug="testbrand")
        intake.toggle_exclude(mid, True)
        app = create_app(config_dir=config_dir, db_path=db_path)
        client = app.test_client()
        resp = client.get("/materials")
        assert b"Excluded" in resp.data
