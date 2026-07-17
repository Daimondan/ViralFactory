"""Tests for VF-AU-204: Media acquisition service."""

import os, sqlite3, pytest, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from services.media_acquisition import MediaAcquisitionService, AcquisitionResult


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS asset_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id INTEGER, kind TEXT,
            path TEXT, prompt TEXT, owner_type TEXT DEFAULT 'asset',
            provider TEXT, cost_usd REAL, created_at TEXT
        );
    """)
    conn.commit(); conn.close()
    return path


class TestAcquisitionLifecycle:
    def test_text_card_is_ready(self, db_path):
        svc = MediaAcquisitionService(db_path)
        result = svc.acquire({"media_recipe_id": "r01", "primary": {"kind": "text_card"}}, asset_id=1)
        assert result.status == "render_ready"
        assert "text_card" in result.ingredient_id

    def test_upload_verifies_existing(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (id, asset_id, kind, path, owner_type) VALUES (1, 1, 'image', '/local/img.png', 'asset')")
        conn.commit(); conn.close()
        svc = MediaAcquisitionService(db_path)
        result = svc.acquire({"media_recipe_id": "r01", "primary": {"kind": "upload", "ingredient_id": "asset_media:1"}}, asset_id=1)
        assert result.status == "render_ready"
        assert result.local_path == "/local/img.png"

    def test_unknown_kind_fails(self, db_path):
        svc = MediaAcquisitionService(db_path)
        result = svc.acquire({"media_recipe_id": "r01", "primary": {"kind": "hologram"}}, asset_id=1)
        assert result.status == "failed"
        assert "hologram" in result.error

    def test_no_adapter_fails_gracefully(self, db_path):
        svc = MediaAcquisitionService(db_path)
        result = svc.acquire({"media_recipe_id": "r01", "primary": {"kind": "generated_image", "generation_prompt": "test"}}, asset_id=1)
        assert result.status == "failed"
        assert "adapter" in result.error.lower()


class TestIdempotency:
    def test_idempotency_key_deterministic(self, db_path):
        svc = MediaAcquisitionService(db_path)
        k1 = svc._compute_idempotency_key(1, "r01", "prompt A")
        k2 = svc._compute_idempotency_key(1, "r01", "prompt A")
        assert k1 == k2

    def test_idempotency_key_changes_with_prompt(self, db_path):
        svc = MediaAcquisitionService(db_path)
        k1 = svc._compute_idempotency_key(1, "r01", "prompt A")
        k2 = svc._compute_idempotency_key(1, "r01", "prompt B")
        assert k1 != k2

    def test_cached_result_returns_without_new_charge(self, db_path, tmp_path):
        fake_path = str(tmp_path / "img.png")
        with open(fake_path, "w") as f: f.write("fake")
        svc = MediaAcquisitionService(db_path)
        key = svc._compute_idempotency_key(1, "r01", "test prompt")
        svc._store_idempotency(key, "asset_media:99", fake_path)
        cached = svc._check_idempotency(key)
        assert cached is not None
        assert cached["ingredient_id"] == "asset_media:99"


class TestDownloadValidation:
    def test_rejects_tiny_file(self, db_path, tmp_path):
        tiny = str(tmp_path / "tiny.png")
        with open(tiny, "w") as f: f.write("x")
        svc = MediaAcquisitionService(db_path)
        assert not svc._validate_download(tiny)

    def test_rejects_html_error(self, db_path, tmp_path):
        html = str(tmp_path / "error.html")
        with open(html, "w") as f: f.write("<!DOCTYPE html><html><body>Error</body></html>")
        svc = MediaAcquisitionService(db_path)
        assert not svc._validate_download(html)

    def test_accepts_valid_file(self, db_path, tmp_path):
        valid = str(tmp_path / "valid.png")
        with open(valid, "wb") as f: f.write(b"\x89PNG" + b"\x00" * 2000)
        svc = MediaAcquisitionService(db_path)
        assert svc._validate_download(valid)

    def test_rejects_missing_file(self, db_path):
        svc = MediaAcquisitionService(db_path)
        assert not svc._validate_download("/nonexistent/file.png")