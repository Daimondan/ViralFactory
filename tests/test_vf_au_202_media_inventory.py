"""
Tests for VF-AU-202: Scoped render-ready inventory service.

Produces one scoped render-ready inventory contract per asset.
- Asset-scoped: only media for this specific asset_id
- Privacy-isolated: session uploads never leak into public assembly
- Tenant-isolated: only this business's media
- Excludes: unrelated uploads, remote-only URLs, submitted jobs, missing files, unapproved references
"""

import json
import os
import pytest
import sys
import sqlite3
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.media_inventory import MediaInventoryService, InventoryItem


@pytest.fixture
def db_path(tmp_path):
    """Create a test DB with the asset_media and materials tables."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS asset_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER,
            kind TEXT,
            path TEXT,
            prompt TEXT,
            owner_type TEXT DEFAULT 'asset',
            provider TEXT,
            cost_usd REAL,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_slug TEXT,
            material_type TEXT,
            channel TEXT,
            file_path TEXT,
            metadata TEXT
        );
        CREATE TABLE IF NOT EXISTS reference_assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_slug TEXT,
            asset_type TEXT,
            status TEXT DEFAULT 'pending',
            file_path TEXT,
            metadata TEXT
        );
    """)
    conn.commit()
    conn.close()
    return path


class TestInventoryScoping:
    """The inventory must be asset-scoped — only this asset's media."""

    def test_only_returns_media_for_this_asset(self, db_path):
        """Media from a different asset_id must not appear."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', 'img1.png', 'asset')")
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (2, 'image', 'img2.png', 'asset')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        assert len(inv.items) == 1
        assert inv.items[0].ingredient_id == "asset_media:1"

    def test_excludes_draft_visuals(self, db_path):
        """Draft visual previews (owner_type='draft') must not be in assembly inventory."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', 'real.png', 'asset')")
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', 'preview.png', 'draft')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        paths = [i.path for i in inv.items]
        assert "real.png" in paths
        assert "preview.png" not in paths

    def test_excludes_remote_only_urls(self, db_path, tmp_path):
        """Media with only a remote URL and no local path must not be render-ready."""
        local_path = str(tmp_path / "img.png")
        with open(local_path, "w") as f:
            f.write("fake image")
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', ?, 'asset')", (local_path,))
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'video', 'https://remote.com/vid.mp4', 'asset')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        # Only the local path should be included; the remote URL is not render-ready
        ready = [i for i in inv.items if i.is_render_ready]
        assert len(ready) == 1
        assert local_path in ready[0].path

    def test_excludes_missing_files(self, db_path):
        """Media whose local file doesn't exist must be flagged as not render-ready."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', '/nonexistent/img.png', 'asset')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        assert len(inv.items) == 1
        assert not inv.items[0].is_render_ready
        assert "missing" in inv.items[0].status.lower() or "not found" in inv.items[0].status.lower()


class TestPrivacyIsolation:
    """Session uploads must never appear in public assembly inventory."""

    def test_session_uploads_excluded(self, db_path):
        """Session upload materials (channel='session_upload') must be excluded."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO materials (business_slug, material_type, channel, file_path) VALUES ('stackpenni', 'voice', 'session_upload', '/voice/sample.wav')")
        conn.execute("INSERT INTO materials (business_slug, material_type, channel, file_path) VALUES ('stackpenni', 'image', 'capture_upload', '/photos/receipt.png')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(
            asset_id=1, business_slug="stackpenni",
            capture_upload_ids=[],  # no linked captures
        )
        # Session uploads must not appear
        channels = [i.source_type for i in inv.items if hasattr(i, 'source_type')]
        assert "session_upload" not in channels

    def test_only_linked_capture_uploads_included(self, db_path):
        """Only the specific capture_upload IDs linked to this card are included."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO materials (id, business_slug, material_type, channel, file_path) VALUES (10, 'stackpenni', 'image', 'capture_upload', '/photos/linked.png')")
        conn.execute("INSERT INTO materials (id, business_slug, material_type, channel, file_path) VALUES (11, 'stackpenni', 'image', 'capture_upload', '/photos/unrelated.png')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(
            asset_id=1, business_slug="stackpenni",
            capture_upload_ids=[10],  # only material 10 is linked
        )
        paths = [i.path for i in inv.items]
        assert "/photos/linked.png" in paths
        assert "/photos/unrelated.png" not in paths


class TestTenantIsolation:
    """Media from a different business must not appear."""

    def test_other_business_media_excluded(self, db_path):
        """Reference assets from a different business must be excluded."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO reference_assets (business_slug, asset_type, status, file_path) VALUES ('stackpenni', 'character', 'approved', '/ref/char.png')")
        conn.execute("INSERT INTO reference_assets (business_slug, asset_type, status, file_path) VALUES ('other_business', 'character', 'approved', '/ref/other.png')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        paths = [i.path for i in inv.items]
        assert "/ref/char.png" in paths
        assert "/ref/other.png" not in paths


class TestReferenceAssets:
    """Only approved reference assets are included; unapproved/retired are blocked."""

    def test_approved_reference_included(self, db_path, tmp_path):
        ref_path = str(tmp_path / "char.png")
        with open(ref_path, "w") as f:
            f.write("fake ref")
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO reference_assets (business_slug, asset_type, status, file_path) VALUES ('stackpenni', 'character', 'approved', ?)", (ref_path,))
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        ref_items = [i for i in inv.items if i.source_type == "reference_asset"]
        assert len(ref_items) == 1
        assert ref_items[0].is_render_ready

    def test_unapproved_reference_excluded(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO reference_assets (business_slug, asset_type, status, file_path) VALUES ('stackpenni', 'character', 'pending', '/ref/pending.png')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        ref_items = [i for i in inv.items if i.source_type == "reference_asset"]
        assert len(ref_items) == 0

    def test_retired_reference_excluded(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO reference_assets (business_slug, asset_type, status, file_path) VALUES ('stackpenni', 'character', 'retired', '/ref/old.png')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        ref_items = [i for i in inv.items if i.source_type == "reference_asset"]
        assert len(ref_items) == 0


class TestInventoryItem:
    """InventoryItem should carry all required metadata."""

    def test_item_has_ingredient_id(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', '/local/img.png', 'asset')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        assert inv.items[0].ingredient_id.startswith("asset_media:")
        assert inv.items[0].kind == "image"
        assert inv.items[0].path == "/local/img.png"

    def test_inventory_summary(self, db_path):
        """The inventory should provide a summary with counts."""
        conn = sqlite3.connect(db_path)
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'image', '/local/img.png', 'asset')")
        conn.execute("INSERT INTO asset_media (asset_id, kind, path, owner_type) VALUES (1, 'video', '/local/vid.mp4', 'asset')")
        conn.commit()
        conn.close()

        service = MediaInventoryService(db_path)
        inv = service.build_inventory(asset_id=1, business_slug="stackpenni")
        summary = inv.summary
        assert summary["total_items"] == 2
        assert summary["render_ready"] >= 0
        assert "by_kind" in summary