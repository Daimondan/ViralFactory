"""
M6 T6.1: Research job v1 — YouTube channel RSS feeds against sources.yaml.

Uses YouTube RSS feeds (https://www.youtube.com/feeds/videos.xml?channel_id=...)
instead of the YouTube Data API. No API key required — feedparser handles parsing.

For each enabled YouTube channel in sources.yaml, pulls latest videos with:
- Video ID, title, description, publish date
- Channel name, thumbnail URL, watch URL

Stored in the source_research table. Scheduled via cron (nightly).

NOT using YouTube Data API — RSS feeds are free, public, and don't require auth.
When the operator enables YouTube Data API on their Google Cloud project,
this module can be upgraded to use the full search endpoint.
"""

import os
import json
import sqlite3
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

import feedparser

logger = logging.getLogger("viralfactory.research")


class ResearchJob:
    """M6 T6.1: YouTube RSS research job — scans configured channels for new videos."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        self._init_table()

    def _init_table(self):
        """Create the source_research table."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS source_research (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_slug TEXT NOT NULL,
                source_name TEXT NOT NULL,
                platform TEXT NOT NULL DEFAULT 'youtube',
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                channel_name TEXT,
                thumbnail_url TEXT,
                watch_url TEXT NOT NULL,
                published_at TEXT,
                content_hash TEXT NOT NULL,
                analysis_status TEXT DEFAULT 'pending',
                analysis_result TEXT,
                analyzed_at TEXT,
                discovered_at TEXT NOT NULL,
                UNIQUE(video_id, business_slug)
            );
            CREATE INDEX IF NOT EXISTS idx_research_business ON source_research(business_slug);
            CREATE INDEX IF NOT EXISTS idx_research_status ON source_research(analysis_status);
            CREATE INDEX IF NOT EXISTS idx_research_platform ON source_research(platform);
        """)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _hash_video(self, video_id: str, title: str) -> str:
        return hashlib.sha256(f"{video_id}|{title}".encode()).hexdigest()[:16]

    def _resolve_channel_id(self, handle: str) -> Optional[str]:
        """Try to resolve a YouTube handle to a channel ID for RSS.
        YouTube RSS feeds require the channel ID (UCxxxx format).
        If the handle is already a channel ID (starts with UC), use it directly.
        Otherwise, try common patterns."""
        handle = handle.strip().lstrip("@")
        if handle.startswith("UC") and len(handle) == 24:
            return handle
        # Try fetching the channel page to extract the channel ID
        try:
            url = f"https://www.youtube.com/@{handle}"
            req_obj = __import__("urllib.request", fromlist=["Request"]).Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urlopen(req_obj, timeout=10) as resp:
                html = resp.read().decode("utf-8", errors="replace")
                # Look for channelId in the page
                import re
                match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', html)
                if match:
                    return match.group(1)
        except Exception:
            pass
        return None

    def fetch_channel_videos(self, channel_id: str, channel_name: str = "") -> list[dict]:
        """Fetch latest videos from a YouTube channel's RSS feed."""
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            parsed = feedparser.parse(rss_url)
            if not parsed.entries:
                return []

            videos = []
            for entry in parsed.entries:
                video_id = entry.get("yt_videoid", "")
                if not video_id:
                    # Try to extract from the link
                    link = entry.get("link", "")
                    if "watch?v=" in link:
                        video_id = link.split("watch?v=")[1].split("&")[0]

                if not video_id:
                    continue

                title = entry.get("title", "").strip()
                description = entry.get("summary", entry.get("description", "")).strip()
                published = entry.get("published", "")
                watch_url = entry.get("link", f"https://www.youtube.com/watch?v={video_id}")

                # Get thumbnail
                thumbnail_url = ""
                for media in entry.get("media_content", []):
                    if "thumbnail" in str(media.get("url", "")):
                        thumbnail_url = media.get("url", "")
                if not thumbnail_url:
                    for media in entry.get("media_thumbnail", []):
                        thumbnail_url = media.get("url", "")
                        break

                # Get channel name from feed
                feed_channel = parsed.feed.get("title", channel_name)

                videos.append({
                    "video_id": video_id,
                    "title": title,
                    "description": description[:500],
                    "channel_name": feed_channel,
                    "thumbnail_url": thumbnail_url,
                    "watch_url": watch_url,
                    "published_at": published,
                })

            return videos
        except Exception as e:
            logger.warning(f"Failed to fetch YouTube RSS for channel {channel_id}: {e}")
            return []

    def run(self, business_slug: str, sources_config: dict) -> dict:
        """Run the research job: scan all enabled YouTube channels in sources.yaml.
        Returns summary: {discovered, new, duplicates, channels_scanned}."""
        channels = sources_config.get("channels", [])
        youtube_channels = [ch for ch in channels if ch.get("platform", "").lower() == "youtube" and ch.get("enabled", True)]

        if not youtube_channels:
            return {"discovered": 0, "new": 0, "duplicates": 0, "channels_scanned": 0}

        discovered = 0
        new_count = 0
        dup_count = 0
        channels_scanned = 0

        for ch in youtube_channels:
            name = ch.get("name", "")
            handle = ch.get("handle", "")

            # Resolve channel ID
            channel_id = ch.get("channel_id", "")
            if not channel_id:
                channel_id = self._resolve_channel_id(handle)
                if not channel_id:
                    logger.warning(f"Could not resolve channel ID for '{name}' (handle: {handle})")
                    continue

            channels_scanned += 1
            videos = self.fetch_channel_videos(channel_id, name)

            conn = sqlite3.connect(self.db_path)
            for video in videos:
                discovered += 1
                content_hash = self._hash_video(video["video_id"], video["title"])
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO source_research
                           (business_slug, source_name, platform, video_id, title,
                            description, channel_name, thumbnail_url, watch_url,
                            published_at, content_hash, discovered_at)
                           VALUES (?, ?, 'youtube', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (business_slug, name, video["video_id"], video["title"],
                         video["description"], video["channel_name"],
                         video["thumbnail_url"], video["watch_url"],
                         video["published_at"], content_hash, self._now()),
                    )
                    if conn.total_changes > 0:
                        new_count += 1
                    else:
                        dup_count += 1
                except sqlite3.IntegrityError:
                    dup_count += 1
            conn.commit()
            conn.close()

        logger.info(f"Research job for {business_slug}: {discovered} videos found, {new_count} new, {dup_count} duplicates")
        return {
            "discovered": discovered,
            "new": new_count,
            "duplicates": dup_count,
            "channels_scanned": channels_scanned,
        }

    def list_research_items(self, business_slug: str, status: str = None, limit: int = 50) -> list[dict]:
        """List research items, optionally filtered by analysis status."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM source_research WHERE business_slug = ? AND analysis_status = ? ORDER BY discovered_at DESC LIMIT ?",
                (business_slug, status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM source_research WHERE business_slug = ? ORDER BY discovered_at DESC LIMIT ?",
                (business_slug, limit),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_research_item(self, item_id: int) -> Optional[dict]:
        """Get a single research item."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM source_research WHERE id = ?", (item_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_analysis(self, item_id: int, status: str, result: dict = None):
        """Update the analysis status and result for a research item."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE source_research SET analysis_status = ?, analysis_result = ?, analyzed_at = ? WHERE id = ?",
            (status, json.dumps(result) if result else None, ts, item_id),
        )
        conn.commit()
        conn.close()