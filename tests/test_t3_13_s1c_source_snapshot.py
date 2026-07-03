"""
Tests for T3.13 S1c: Mechanical RSS source snapshot.

AC:
- Snapshot table populated from a fixture feed; feed failure degrades gracefully with marker.
- Content-hash cached per feed URL with 6-hour TTL.
- Feedparser + trafilatura used (boring-library mechanics, no LLM).
"""
import os
import json
import pytest
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from source_snapshot import SourceSnapshot


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


class TestSourceSnapshot:
    """S1c: Mechanical RSS source snapshot — dumb fetch, no LLM."""

    def test_table_created(self, db_path):
        """The source_snapshot table is created on init."""
        snap = SourceSnapshot(db_path=db_path)
        import sqlite3
        conn = sqlite3.connect(db_path)
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "source_snapshot" in tables

    def test_fetch_feed_returns_items(self, db_path):
        """fetch_feed parses a feed and returns items with title/summary/url."""
        snap = SourceSnapshot(db_path=db_path)

        # Mock feedparser.parse to return a fake feed
        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "AI breaks another barrier",
            "summary": "Latest developments in AI technology.",
            "link": "https://example.com/article1",
        }.get(key, default)
        fake_entry.content = []

        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        with patch("source_snapshot.feedparser.parse", return_value=fake_parsed):
            items = snap.fetch_feed("https://example.com/feed", "TestFeed")

        assert len(items) == 1
        assert items[0]["title"] == "AI breaks another barrier"
        assert items[0]["url"] == "https://example.com/article1"
        assert items[0]["source_name"] == "TestFeed"

    def test_fetch_feed_failure_returns_empty(self, db_path):
        """Feed failure (parse error) returns empty list."""
        snap = SourceSnapshot(db_path=db_path)

        with patch("source_snapshot.feedparser.parse", side_effect=Exception("Network error")):
            items = snap.fetch_feed("https://broken.example.com/feed", "Broken")

        assert items == []

    def test_get_snapshot_caches_and_reuses(self, db_path):
        """get_snapshot caches the result and reuses it within TTL."""
        snap = SourceSnapshot(db_path=db_path)

        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "Cached article",
            "summary": "Summary",
            "link": "https://example.com/cached",
        }.get(key, default)
        fake_entry.content = []
        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        call_count = [0]
        def mock_parse(url):
            call_count[0] += 1
            return fake_parsed

        with patch("source_snapshot.feedparser.parse", mock_parse):
            # First call — should fetch
            items1 = snap.get_snapshot("https://example.com/feed", "TestFeed")
            assert items1 is not None
            assert len(items1) == 1
            assert call_count[0] == 1

            # Second call — should use cache (no new fetch)
            items2 = snap.get_snapshot("https://example.com/feed", "TestFeed")
            assert items2 is not None
            assert call_count[0] == 1  # still only 1 fetch

    def test_get_snapshot_refetches_after_ttl(self, db_path):
        """get_snapshot refetches when the cached entry is older than TTL."""
        snap = SourceSnapshot(db_path=db_path)

        # Insert a stale cached entry
        import sqlite3
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute("""
            INSERT INTO source_snapshot (feed_url, feed_name, items, content_hash, fetched_at)
            VALUES (?, ?, ?, ?, ?)
        """, ("https://example.com/feed", "TestFeed", json.dumps([{"title": "old"}]), "old_hash", stale_time))
        conn.commit()
        conn.close()

        # Mock a fresh fetch
        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "Fresh article",
            "summary": "New summary",
            "link": "https://example.com/fresh",
        }.get(key, default)
        fake_entry.content = []
        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        with patch("source_snapshot.feedparser.parse", return_value=fake_parsed):
            items = snap.get_snapshot("https://example.com/feed", "TestFeed")

        assert items is not None
        assert items[0]["title"] == "Fresh article"  # not "old"

    def test_build_snapshot_text_with_items(self, db_path):
        """build_snapshot_text produces formatted text from feed items."""
        snap = SourceSnapshot(db_path=db_path)

        fake_entry = MagicMock()
        fake_entry.get = lambda key, default="": {
            "title": "Breaking AI news",
            "summary": "Important development",
            "link": "https://example.com/breaking",
        }.get(key, default)
        fake_entry.content = []
        fake_parsed = MagicMock()
        fake_parsed.entries = [fake_entry]

        feeds = [{"name": "TestFeed", "url": "https://example.com/feed", "enabled": True, "type": "rss"}]

        with patch("source_snapshot.feedparser.parse", return_value=fake_parsed):
            text = snap.build_snapshot_text(feeds)

        assert "Breaking AI news" in text
        assert "TestFeed" in text
        assert "https://example.com/breaking" in text

    def test_build_snapshot_text_empty_feeds(self, db_path):
        """build_snapshot_text returns empty string for no feeds."""
        snap = SourceSnapshot(db_path=db_path)
        text = snap.build_snapshot_text([])
        assert text == ""

    def test_build_snapshot_text_feed_failure_degrades(self, db_path):
        """Feed failure degrades to (snapshot unavailable) marker."""
        snap = SourceSnapshot(db_path=db_path)

        with patch("source_snapshot.feedparser.parse", side_effect=Exception("Network error")):
            text = snap.build_snapshot_text([
                {"name": "Broken", "url": "https://broken.example.com/feed", "enabled": True, "type": "rss"}
            ])

        assert text == "(snapshot unavailable)"

    def test_disabled_feeds_skipped(self, db_path):
        """Disabled feeds are not fetched."""
        snap = SourceSnapshot(db_path=db_path)

        call_count = [0]
        def mock_parse(url):
            call_count[0] += 1
            fake_parsed = MagicMock()
            fake_parsed.entries = []
            return fake_parsed

        with patch("source_snapshot.feedparser.parse", mock_parse):
            text = snap.build_snapshot_text([
                {"name": "Disabled", "url": "https://example.com/feed", "enabled": False, "type": "rss"}
            ])

        assert call_count[0] == 0  # never fetched