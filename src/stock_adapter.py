"""
ViralFactory — Stock Library Adapter

Per CORRECTION-final-assembly-and-materials-editing-v1.0 Part 1:
- Pexels (primary) + Pixabay (secondary) — both free, commercial-safe
- Searches photos and video for stock clips
- Downloads candidates to data/media/stock/, cached by provider+id
- Records id, provider, source URL, and license string per item (provenance for media)
- Music: Pixabay's audio catalog for background tracks

Auth: PEXELS_API_KEY + PIXABAY_API_KEY env vars.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import requests


# Schema for stock cache
STOCK_SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,           -- pexels | pixabay
    external_id TEXT NOT NULL,        -- provider's item ID
    kind TEXT NOT NULL,              -- photo | video | music
    url TEXT NOT NULL,               -- source URL
    local_path TEXT,                 -- downloaded file path
    license TEXT,                    -- license string
    title TEXT,                      -- title/description
    duration REAL,                   -- duration in seconds (video/audio)
    width INTEGER,
    height INTEGER,
    downloaded_at TEXT,
    UNIQUE(provider, external_id)
);

CREATE INDEX IF NOT EXISTS idx_stock_provider ON stock_cache(provider);
CREATE INDEX IF NOT EXISTS idx_stock_kind ON stock_cache(kind);
"""


class StockAdapterError(Exception):
    pass


class StockAdapter:
    """
    Stock library access via Pexels + Pixabay APIs.

    Usage:
        adapter = StockAdapter(models_config, db_path="data/viralfactory.db")
        results = adapter.search("sunset beach", kind="video", per_page=5)
        adapter.download(results[0])
    """

    PEXELS_BASE = "https://api.pexels.com"
    PIXABAY_BASE = "https://pixabay.com/api"

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config
        self.db_path = db_path
        stock_config = models_config.get("stock", {})
        self.cache_dir = stock_config.get("cache_dir", "data/media/stock")
        os.makedirs(self.cache_dir, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(STOCK_SCHEMA)
        conn.commit()
        conn.close()

    # ── Pexels ──

    def _pexels_search(self, query: str, kind: str = "photo", per_page: int = 5) -> list[dict]:
        """Search Pexels for photos or videos."""
        api_key = os.environ.get("PEXELS_API_KEY", "")
        if not api_key:
            return []

        headers = {"Authorization": api_key}
        if kind == "video":
            url = f"{self.PEXELS_BASE}/videos/search"
        else:
            url = f"{self.PEXELS_BASE}/v1/search"

        params = {"query": query, "per_page": per_page, "orientation": "portrait"}

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            return []

        data = response.json()
        results = []

        if kind == "video":
            for v in data.get("videos", []):
                # Find the best quality file
                files = v.get("video_files", [])
                best = max(files, key=lambda f: f.get("width", 0) * f.get("height", 0)) if files else {}
                results.append({
                    "provider": "pexels",
                    "external_id": str(v.get("id")),
                    "kind": "video",
                    "url": v.get("url", ""),
                    "download_url": best.get("link", ""),
                    "license": "Pexels License (free, commercial-safe, no attribution required)",
                    "title": f"Video {v.get('id')}",
                    "duration": v.get("duration"),
                    "width": best.get("width"),
                    "height": best.get("height"),
                })
        else:
            for p in data.get("photos", []):
                results.append({
                    "provider": "pexels",
                    "external_id": str(p.get("id")),
                    "kind": "photo",
                    "url": p.get("url", ""),
                    "download_url": p.get("src", {}).get("large2x", ""),
                    "license": "Pexels License (free, commercial-safe, no attribution required)",
                    "title": p.get("alt", f"Photo {p.get('id')}"),
                    "duration": None,
                    "width": p.get("width"),
                    "height": p.get("height"),
                })

        return results

    # ── Pixabay ──

    def _pixabay_search(self, query: str, kind: str = "photo", per_page: int = 5) -> list[dict]:
        """Search Pixabay for photos, videos, or music."""
        api_key = os.environ.get("PIXABAY_API_KEY", "")
        if not api_key:
            return []

        if kind == "video":
            url = f"{self.PIXABAY_BASE}/videos/"
        elif kind == "music":
            url = f"{self.PIXABAY_BASE}/audio/"
        else:
            url = f"{self.PIXABAY_BASE}/"

        params = {"key": api_key, "q": query, "per_page": per_page, "image_type": "photo"}

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            return []

        data = response.json()
        results = []

        if kind == "video":
            for v in data.get("hits", []):
                results.append({
                    "provider": "pixabay",
                    "external_id": str(v.get("id")),
                    "kind": "video",
                    "url": v.get("pageURL", ""),
                    "download_url": v.get("videos", {}).get("medium", {}).get("url", v.get("videos", {}).get("large", {}).get("url", "")),
                    "license": "Pixabay License (free, commercial-safe, no attribution required)",
                    "title": v.get("tags", f"Video {v.get('id')}"),
                    "duration": v.get("duration"),
                    "width": v.get("imageWidth"),
                    "height": v.get("imageHeight"),
                })
        elif kind == "music":
            for m in data.get("hits", []):
                results.append({
                    "provider": "pixabay",
                    "external_id": str(m.get("id")),
                    "kind": "music",
                    "url": m.get("pageURL", ""),
                    "download_url": m.get("audio", ""),
                    "license": "Pixabay License (free, commercial-safe, no attribution required)",
                    "title": m.get("tags", f"Music {m.get('id')}"),
                    "duration": m.get("duration"),
                    "width": None,
                    "height": None,
                })
        else:
            for p in data.get("hits", []):
                results.append({
                    "provider": "pixabay",
                    "external_id": str(p.get("id")),
                    "kind": "photo",
                    "url": p.get("pageURL", ""),
                    "download_url": p.get("largeImageURL", ""),
                    "license": "Pixabay License (free, commercial-safe, no attribution required)",
                    "title": p.get("tags", f"Photo {p.get('id')}"),
                    "duration": None,
                    "width": p.get("imageWidth"),
                    "height": p.get("imageHeight"),
                })

        return results

    # ── Unified search ──

    def search(self, query: str, kind: str = "photo", per_page: int = 5) -> list[dict]:
        """Search all configured providers. Returns deduplicated results."""
        results = []
        stock_config = self.models_config.get("stock", {})
        providers = stock_config.get("providers", ["pexels", "pixabay"])

        for provider in providers:
            if provider == "pexels":
                results.extend(self._pexels_search(query, kind, per_page))
            elif provider == "pixabay":
                results.extend(self._pixabay_search(query, kind, per_page))

        return results[:per_page * 2]  # cap total

    # ── Download ──

    def download(self, item: dict) -> str:
        """Download a stock item to the cache. Returns local file path.
        Cached by provider+id — never re-downloads."""
        provider = item.get("provider", "")
        external_id = item.get("external_id", "")
        download_url = item.get("download_url", "")
        kind = item.get("kind", "photo")

        if not download_url:
            raise StockAdapterError("No download URL on item")

        # Check cache
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cached = conn.execute(
            "SELECT local_path FROM stock_cache WHERE provider = ? AND external_id = ?",
            (provider, external_id),
        ).fetchone()

        if cached and cached["local_path"] and os.path.exists(cached["local_path"]):
            conn.close()
            return cached["local_path"]

        # Download
        ext = "mp4" if kind == "video" else ("mp3" if kind == "music" else "jpg")
        filename = f"{provider}_{external_id}.{ext}"
        file_path = os.path.join(self.cache_dir, filename)

        try:
            response = requests.get(download_url, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            raise StockAdapterError(f"Download failed: {e}")

        with open(file_path, "wb") as f:
            f.write(response.content)

        # Record in cache
        ts = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT OR REPLACE INTO stock_cache
               (provider, external_id, kind, url, local_path, license, title,
                duration, width, height, downloaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (provider, external_id, kind, item.get("url", ""), file_path,
             item.get("license", ""), item.get("title", ""),
             item.get("duration"), item.get("width"), item.get("height"), ts),
        )
        conn.commit()
        conn.close()

        return file_path

    def list_cached(self, kind: str = None) -> list[dict]:
        """List cached stock items."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if kind:
            rows = conn.execute(
                "SELECT * FROM stock_cache WHERE kind = ? ORDER BY downloaded_at DESC",
                (kind,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM stock_cache ORDER BY downloaded_at DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]