"""
S1c: Mechanical RSS source snapshot — dumb fetch, no LLM, no analysis.

For each feed in sources.yaml, pull the latest ~10 item titles + first-paragraph
summaries (feedparser + trafilatura). Content-hash cached per feed URL with a
6-hour TTL. Stored in a small source_snapshot table.

This is NOT M6 — no YouTube API, no analysis, no scoring, no proposals.
It is a dumb fetch that makes the ideation input vary with the world.
M6 T6.1/T6.2 supersede it when they land.

Failures degrade to criteria-only behavior with a (snapshot unavailable) marker.
"""

import json
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

import feedparser

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False


SNAPSHOT_TTL_HOURS = 6
MAX_ITEMS_PER_FEED = 10
SUMMARY_CHAR_LIMIT = 300
SNAPSHOT_CHAR_CAP = 4000  # total cap for the source_material variable


class SourceSnapshot:
    """Mechanical RSS fetcher with content-hash cache and 6-hour TTL."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        """Create the source_snapshot table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_snapshot (
                feed_url TEXT PRIMARY KEY,
                feed_name TEXT,
                items TEXT NOT NULL,          -- JSON array of {title, summary, url, source_name}
                content_hash TEXT NOT NULL,   -- hash of the raw feed content
                fetched_at TEXT NOT NULL      -- ISO timestamp
            )
        """)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _is_stale(self, fetched_at: str, ttl_hours: int = SNAPSHOT_TTL_HOURS) -> bool:
        """Check if a snapshot is older than the TTL."""
        try:
            fetched = datetime.fromisoformat(fetched_at)
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - fetched
            return age > timedelta(hours=ttl_hours)
        except (ValueError, TypeError):
            return True

    def _hash_feed(self, feed_data: str) -> str:
        """Content-hash the raw feed data."""
        return hashlib.sha256(feed_data.encode("utf-8")).hexdigest()[:16]

    def _extract_summary(self, entry) -> str:
        """Extract a first-paragraph summary from a feed entry using trafilatura.
        Falls back to the feed's summary/description if trafilatura is unavailable."""
        # Try trafilatura on the full content first
        if HAS_TRAFILATURA and entry.get("content"):
            for content_block in entry.get("content", []):
                raw_html = content_block.get("value", "")
                if raw_html:
                    extracted = trafilatura.extract(raw_html)
                    if extracted:
                        # Take first paragraph
                        first_para = extracted.split("\n\n")[0].strip()
                        if first_para:
                            return first_para[:SUMMARY_CHAR_LIMIT]

        # Fall back to feed's own summary
        summary = entry.get("summary", "")
        if summary:
            # Strip HTML tags crudely if trafilatura unavailable
            if not HAS_TRAFILATURA:
                import re
                summary = re.sub(r"<[^>]+>", "", summary).strip()
            return summary[:SUMMARY_CHAR_LIMIT]

        return ""

    def fetch_feed(self, feed_url: str, feed_name: str = "") -> list[dict]:
        """Fetch a single feed and return parsed items. Does NOT use the cache —
        the cache is checked by get_snapshot()."""
        try:
            parsed = feedparser.parse(feed_url)
            if not parsed.entries:
                return []

            items = []
            for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
                title = entry.get("title", "").strip()
                summary = self._extract_summary(entry)
                url = entry.get("link", "")
                items.append({
                    "title": title,
                    "summary": summary,
                    "url": url,
                    "source_name": feed_name,
                })

            return items
        except Exception:
            return []

    def get_snapshot(self, feed_url: str, feed_name: str = "") -> Optional[list[dict]]:
        """Get a cached snapshot for a feed URL, or fetch fresh if stale/missing.
        Returns None on failure."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM source_snapshot WHERE feed_url = ?", (feed_url,)
        ).fetchone()
        conn.close()

        if row and not self._is_stale(dict(row)["fetched_at"]):
            items = json.loads(dict(row)["items"])
            return items

        # Fetch fresh
        items = self.fetch_feed(feed_url, feed_name)
        if not items:
            return None  # failure — caller degrades gracefully

        # Store in cache
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO source_snapshot
                (feed_url, feed_name, items, content_hash, fetched_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            feed_url, feed_name,
            json.dumps(items),
            self._hash_feed(json.dumps(items)),
            self._now(),
        ))
        conn.commit()
        conn.close()

        return items

    def build_snapshot_text(self, feeds: list[dict]) -> str:
        """Build the source_material text from all configured feeds.
        Each item carries its source name + URL as evidence link.
        Degrades to '(snapshot unavailable)' marker on failure."""
        if not feeds:
            return ""

        all_items = []
        for feed in feeds:
            if not feed.get("enabled", True):
                continue
            url = feed.get("url", "")
            name = feed.get("name", "")
            if not url:
                continue
            items = self.get_snapshot(url, name)
            if items:
                all_items.extend(items)

        if not all_items:
            return "(snapshot unavailable)"

        # Sort newest first (feedparser returns newest first already)
        # Build text, cap at SNAPSHOT_CHAR_CAP
        lines = []
        char_count = 0
        for item in all_items:
            line = f"- [{item['source_name']}] {item['title']}"
            if item["summary"]:
                line += f" — {item['summary'][:150]}"
            line += f" ({item['url']})"
            if char_count + len(line) > SNAPSHOT_CHAR_CAP:
                break
            lines.append(line)
            char_count += len(line)

        return "\n".join(lines) if lines else "(snapshot unavailable)"