"""
Tests for zip file handling in MaterialsIntake.
Covers: zip extraction, nested directories, junk filtering, PDF/image support,
and the session upload path for zips.
"""

import os
import zipfile
import json
import pytest
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def intake(db_path, tmp_path):
    from materials import MaterialsIntake
    upload_dir = str(tmp_path / "uploads")
    return MaterialsIntake(db_path=db_path, upload_dir=upload_dir)


@pytest.fixture
def zip_file(tmp_path):
    """Create a test zip with mixed file types and nested directories."""
    zip_path = str(tmp_path / "test_archive.zip")

    with zipfile.ZipFile(zip_path, "w") as zf:
        # Text file
        zf.writestr("notes.txt", "This is a text note about AI and wealth.")
        # Markdown file
        zf.writestr("readme.md", "# Brand Doc\n\nStackPenni is a Caribbean AI brand.")
        # JSON file
        zf.writestr("data/config.json", json.dumps({"brand": "StackPenni", "topics": ["AI", "wealth"]}))
        # Nested directory with text
        zf.writestr("subfolder/more.txt", "More content in a subfolder.")
        # Hidden file (should be skipped)
        zf.writestr(".hidden", "This should be skipped")
        # __MACOSX junk (should be skipped)
        zf.writestr("__MACOSX/notes.txt", "macOS metadata junk")
        # Directory entry (should be skipped)
        zf.writestr("empty_dir/", "")

    return zip_path


@pytest.fixture
def empty_zip(tmp_path):
    """Create an empty zip (no files inside)."""
    zip_path = str(tmp_path / "empty.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        pass  # nothing added
    return zip_path


class TestZipIngestion:
    """Test zip file handling in MaterialsIntake."""

    def test_zip_extracts_and_ingests_all_files(self, intake, zip_file, db_path):
        """A zip with 4 valid files produces 4 materials (junk skipped)."""
        import sqlite3
        mid = intake.ingest_zip(zip_file, run_id=1, business_slug="testbiz")

        # Check all materials were created
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT filename, material_type FROM materials WHERE run_id = 1 ORDER BY id").fetchall()
        conn.close()

        # Should have 4 materials (notes.txt, readme.md, config.json, more.txt)
        # Hidden, __MACOSX, and directory entries skipped
        assert len(rows) == 4
        filenames = [r[0] for r in rows]
        assert "notes.txt" in filenames
        assert "readme.md" in filenames
        assert "config.json" in filenames
        assert "more.txt" in filenames
        assert ".hidden" not in filenames
        assert "__MACOSX" not in str(filenames)

    def test_zip_via_ingest_file(self, intake, zip_file, db_path):
        """ingest_file() on a .zip delegates to ingest_zip()."""
        import sqlite3
        mid = intake.ingest_file(zip_file, run_id=2, business_slug="testbiz")

        assert mid > 0

        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM materials WHERE run_id = 2").fetchone()[0]
        conn.close()
        assert count == 4  # same 4 valid files

    def test_zip_empty_archive(self, intake, empty_zip, db_path):
        """An empty zip produces one material noting no files were found."""
        import sqlite3
        mid = intake.ingest_zip(empty_zip, run_id=3, business_slug="testbiz")

        assert mid > 0
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT raw_content FROM materials WHERE run_id = 3").fetchall()
        conn.close()
        assert len(rows) == 1
        assert "no readable files" in rows[0][0] or "no files" in rows[0][0]

    def test_zip_preserves_nested_paths(self, intake, zip_file, db_path):
        """Files in nested directories inside the zip are ingested."""
        import sqlite3
        intake.ingest_zip(zip_file, run_id=4, business_slug="testbiz")

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT filename FROM materials WHERE run_id = 4").fetchall()
        conn.close()
        filenames = [r[0] for r in rows]
        # more.txt was inside subfolder/ — should be ingested by its filename
        assert "more.txt" in filenames

    def test_zip_content_extracted(self, intake, zip_file, db_path):
        """Text content from files inside the zip is extracted and stored."""
        import sqlite3
        intake.ingest_zip(zip_file, run_id=5, business_slug="testbiz")

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT raw_content FROM materials WHERE run_id = 5 AND filename = 'notes.txt'").fetchall()
        conn.close()
        assert len(rows) == 1
        assert "AI and wealth" in rows[0][0]


class TestNewFileTypes:
    """Test PDF and image handling added alongside zip support."""

    def test_pdf_ingestion(self, intake, tmp_path, db_path):
        """PDF files are ingested with text extraction (or graceful fallback)."""
        # Create a minimal valid PDF
        pdf_path = str(tmp_path / "test.pdf")
        # Write a minimal PDF that won't parse (no library installed likely)
        # but the intake should handle gracefully
        with open(pdf_path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n")

        mid = intake.ingest_file(pdf_path, run_id=10, business_slug="testbiz")
        assert mid > 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT material_type, channel FROM materials WHERE id = ?", (mid,)).fetchone()
        conn.close()
        assert row[0] == "plain_text"
        assert row[1] == "document"

    def test_image_ingestion(self, intake, tmp_path, db_path):
        """Image files are stored as visual references."""
        img_path = str(tmp_path / "photo.png")
        with open(img_path, "wb") as f:
            # Minimal PNG header
            f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        mid = intake.ingest_file(img_path, run_id=11, business_slug="testbiz")
        assert mid > 0

        import sqlite3
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT material_type FROM materials WHERE id = ?", (mid,)).fetchone()
        conn.close()
        assert row[0] == "image"

    def test_binary_file_graceful(self, intake, tmp_path, db_path):
        """Unknown binary files don't crash — they get a placeholder."""
        bin_path = str(tmp_path / "data.bin")
        with open(bin_path, "wb") as f:
            f.write(bytes(range(256)) * 10)

        mid = intake.ingest_file(bin_path, run_id=12, business_slug="testbiz")
        assert mid > 0


class TestSessionZipUpload:
    """Test that the session upload endpoint handles zips."""

    @pytest.fixture
    def app(self, tmp_path):
        from app import create_app

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)

        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            f.write("""
business:
  name: "TestBiz"
  slug: "testbiz"
  description: "Test"
subjects: ["test"]
platforms:
  - name: "X"
    handle: "@test"
    priority: 1
audience_description: "Test"
""")

        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            f.write("""
active:
  default: "tb"
  drafter: "tb"
tb:
  provider: "ollama_cloud"
  model: "test"
  temperature: 0
  max_tokens: 100
  base_url: "http://localhost:1"
""")

        with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
            f.write("feeds: []\nchannels: []\nqueries: []\n")

        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        return app

    def test_session_zip_upload(self, app, tmp_path):
        """Uploading a zip through the session endpoint extracts and ingests all files."""
        from pipeline import PipelineStore
        from playbook_runner import PlaybookRunner

        # Create a playbook run
        runner = PlaybookRunner(app.config["DB_PATH"])
        run_id = runner.start_run("business-profile-intake", "1.0", "testbiz")

        # Create a zip
        zip_path = str(tmp_path / "upload.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("brand_notes.txt", "StackPenni is about Caribbean AI.")
            zf.writestr("topics.md", "# Topics\nAI, wealth, culture")

        # Upload via session endpoint
        client = app.test_client()
        with open(zip_path, "rb") as f:
            resp = client.post(f"/api/session/{run_id}/upload",
                               data={"file": (f, "upload.zip")})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["filename"] == "upload.zip"

        # Verify materials were created
        import sqlite3
        conn = sqlite3.connect(app.config["DB_PATH"])
        count = conn.execute("SELECT COUNT(*) FROM materials WHERE run_id = ?", (run_id,)).fetchone()[0]
        conn.close()
        assert count == 2  # brand_notes.txt + topics.md