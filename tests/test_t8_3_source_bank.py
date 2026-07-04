"""
Tests for T8.3: Source Bank as addressable store.

AC:
- New `sources` table exists with correct schema
- source_snapshot.py writes fetched items into this table (dedupe on content_hash) as source_type='rss_item'
- Materials intake registers source_type='operator_material' rows
- business_slug scoping everywhere
- Dedupe on content_hash works
"""
import os
import json
import pytest
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore
from source_snapshot import SourceSnapshot


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    return PipelineStore(db_path=db_path)


@pytest.fixture
def snap(db_path):
    return SourceSnapshot(db_path=db_path, business_slug="test-biz")


class TestSourceBankSchema:
    """T8.3: sources table schema and migrations."""

    def test_sources_table_exists(self, store, db_path):
        """sources table is created on PipelineStore init."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "sources" in tables

    def test_sources_table_columns(self, store, db_path):
        """sources table has all required columns."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sources)").fetchall()]
        conn.close()
        expected = {
            "id", "business_slug", "source_type", "title", "url",
            "summary", "content", "origin", "first_seen", "content_hash", "status"
        }
        assert expected.issubset(set(cols))

    def test_idea_cards_has_source_refs(self, store, db_path):
        """idea_cards table gains source_refs column (migration)."""
        import sqlite3
        conn = sqlite3.connect(db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(idea_cards)").fetchall()]
        conn.close()
        assert "source_refs" in cols
        assert "production_error" in cols


class TestSourceBankCRUD:
    """T8.3: PipelineStore source management methods."""

    def test_add_source(self, store):
        """add_source creates a source row and returns its ID."""
        sid = store.add_source(
            business_slug="test-biz",
            source_type="rss_item",
            title="Breaking AI news",
            url="https://example.com/breaking",
            summary="Important development",
            content="Full article text here",
            origin="system",
            content_hash="abc123",
        )
        assert sid is not None and sid > 0

    def test_get_source(self, store):
        """get_source retrieves a source by ID."""
        sid = store.add_source(
            "test-biz", "rss_item", "Test Source",
            url="https://example.com",
            summary="A summary",
            content="Full content",
            content_hash="hash1",
        )
        src = store.get_source(sid)
        assert src is not None
        assert src["title"] == "Test Source"
        assert src["source_type"] == "rss_item"
        assert src["content"] == "Full content"

    def test_list_sources(self, store):
        """list_sources returns sources for a business, most recent first."""
        store.add_source("biz-a", "rss_item", "Source A", content_hash="h1")
        store.add_source("biz-a", "rss_item", "Source B", content_hash="h2")
        store.add_source("biz-b", "rss_item", "Source C", content_hash="h3")
        sources = store.list_sources("biz-a")
        assert len(sources) == 2
        assert all(s["business_slug"] == "biz-a" for s in sources)

    def test_dedupe_on_content_hash(self, store):
        """Adding a source with an existing content_hash returns the existing ID."""
        sid1 = store.add_source(
            "test-biz", "rss_item", "First",
            content="Content X", content_hash="same-hash",
        )
        sid2 = store.add_source(
            "test-biz", "rss_item", "Second (dup)",
            content="Content Y", content_hash="same-hash",
        )
        assert sid1 == sid2  # deduped — same ID returned

    def test_business_slug_scoping(self, store):
        """Same content_hash in different businesses creates separate rows."""
        sid1 = store.add_source(
            "biz-a", "rss_item", "A",
            content="Content", content_hash="shared-hash",
        )
        sid2 = store.add_source(
            "biz-b", "rss_item", "B",
            content="Content", content_hash="shared-hash",
        )
        assert sid1 != sid2  # different businesses = different rows

    def test_resolve_source_refs(self, store):
        """resolve_source_refs returns full records for given IDs."""
        s1 = store.add_source("biz", "rss_item", "Source 1", content_hash="h1")
        s2 = store.add_source("biz", "rss_item", "Source 2", content_hash="h2")
        s3 = store.add_source("biz", "rss_item", "Source 3", content_hash="h3")
        resolved = store.resolve_source_refs("biz", [s1, s2, s3])
        assert len(resolved) == 3
        titles = {r["title"] for r in resolved}
        assert titles == {"Source 1", "Source 2", "Source 3"}

    def test_resolve_source_refs_filters_wrong_business(self, store):
        """resolve_source_refs only returns sources belonging to the given business."""
        s1 = store.add_source("biz-a", "rss_item", "A", content_hash="h1")
        s2 = store.add_source("biz-b", "rss_item", "B", content_hash="h2")
        resolved = store.resolve_source_refs("biz-a", [s1, s2])
        assert len(resolved) == 1
        assert resolved[0]["title"] == "A"

    def test_resolve_source_refs_empty(self, store):
        """resolve_source_refs with empty list returns empty."""
        assert store.resolve_source_refs("biz", []) == []

    def test_archive_source(self, store):
        """archive_source soft-deletes (status='archived')."""
        sid = store.add_source("biz", "rss_item", "To archive", content_hash="h1")
        store.archive_source(sid)
        src = store.get_source(sid)
        assert src["status"] == "archived"
        # Archived sources don't appear in default list
        active = store.list_sources("biz", status="active")
        assert len(active) == 0

    def test_resolve_source_refs_skips_archived(self, store):
        """resolve_source_refs only returns active sources."""
        sid = store.add_source("biz", "rss_item", "Active", content_hash="h1")
        sid2 = store.add_source("biz", "rss_item", "Archived", content_hash="h2")
        store.archive_source(sid2)
        resolved = store.resolve_source_refs("biz", [sid, sid2])
        assert len(resolved) == 1
        assert resolved[0]["title"] == "Active"


class TestSnapshotWritesToSources:
    """T8.3: source_snapshot.py writes items into the sources table."""

    def test_fetch_registers_sources(self, snap, db_path):
        """fetch_feed writes items to the sources table when business_slug is set."""
        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "AI Breakthrough",
            "summary": "Major advance in LLM reasoning",
            "link": "https://example.com/breakthrough",
        }.get(key, default)
        fake_entry.content = []
        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        with patch("source_snapshot.feedparser.parse", return_value=fake_parsed):
            items = snap.fetch_feed("https://example.com/feed", "TechFeed")

        assert len(items) == 1
        # Verify the item was written to the sources table
        store = PipelineStore(db_path=db_path)
        # DIVERGENCE-007: RSS sources enter with status='new', not 'active'
        sources = store.list_sources("test-biz", status="new")
        assert len(sources) == 1
        assert sources[0]["title"] == "AI Breakthrough"
        assert sources[0]["source_type"] == "rss_item"
        assert sources[0]["url"] == "https://example.com/breakthrough"

    def test_fetch_dedupes_sources(self, snap, db_path):
        """Re-fetching the same feed doesn't create duplicate sources."""
        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "Same Article",
            "summary": "Same summary",
            "link": "https://example.com/same",
        }.get(key, default)
        fake_entry.content = []
        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        with patch("source_snapshot.feedparser.parse", return_value=fake_parsed):
            snap.fetch_feed("https://example.com/feed", "Feed")
            snap.fetch_feed("https://example.com/feed", "Feed")

        store = PipelineStore(db_path=db_path)
        # DIVERGENCE-007: RSS sources enter with status='new', not 'active'
        sources = store.list_sources("test-biz", status="new")
        assert len(sources) == 1  # deduped

    def test_fetch_no_business_slug_skips_registration(self, db_path):
        """Without business_slug, items are NOT registered in sources table."""
        snap = SourceSnapshot(db_path=db_path, business_slug="")
        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "Test",
            "summary": "Summary",
            "link": "https://example.com/test",
        }.get(key, default)
        fake_entry.content = []
        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        with patch("source_snapshot.feedparser.parse", return_value=fake_parsed):
            snap.fetch_feed("https://example.com/feed", "Feed")

        store = PipelineStore(db_path=db_path)
        sources = store.list_sources("test-biz")
        assert len(sources) == 0


class TestMaterialsRegisterSources:
    """T8.3: Materials intake registers operator_material sources."""

    def test_ingest_text_creates_source(self, db_path):
        """ingest_text creates a sources row with source_type='operator_material'."""
        from materials import MaterialsIntake
        ms = MaterialsIntake(db_path=db_path)
        mid = ms.ingest_text(
            content="This is my voice. I speak with a Caribbean accent and use Bajan dialect.",
            business_slug="test-biz",
            material_type="pasted",
        )
        assert mid > 0
        # Check sources table
        store = PipelineStore(db_path=db_path)
        sources = store.list_sources("test-biz")
        assert len(sources) == 1
        assert sources[0]["source_type"] == "operator_material"
        assert sources[0]["origin"] == "operator"
        assert "Caribbean accent" in sources[0]["content"]

    def test_ingest_text_dedupes_sources(self, db_path):
        """Ingesting the same content twice dedupes on content_hash."""
        from materials import MaterialsIntake
        ms = MaterialsIntake(db_path=db_path)
        content = "Same content for dedupe test."
        ms.ingest_text(content=content, business_slug="test-biz", material_type="pasted")
        ms.ingest_text(content=content, business_slug="test-biz", material_type="pasted")
        store = PipelineStore(db_path=db_path)
        sources = store.list_sources("test-biz")
        assert len(sources) == 1  # deduped

    def test_audio_material_skips_source_registration(self, db_path):
        """Audio materials don't create sources rows (transcription pending)."""
        from materials import MaterialsIntake
        ms = MaterialsIntake(db_path=db_path)
        # Audio materials have normalized_content=None
        mid = ms.ingest_text(
            content="[Audio: transcription pending]",
            business_slug="test-biz",
            material_type="audio",
        )
        store = PipelineStore(db_path=db_path)
        sources = store.list_sources("test-biz")
        # Audio type is explicitly skipped
        assert len(sources) == 0

    def test_no_business_slug_skips_source_registration(self, db_path):
        """Without business_slug, no sources row is created."""
        from materials import MaterialsIntake
        ms = MaterialsIntake(db_path=db_path)
        ms.ingest_text(
            content="Content without business",
            business_slug="",
            material_type="pasted",
        )
        store = PipelineStore(db_path=db_path)
        sources = store.list_sources("test-biz")
        assert len(sources) == 0