"""VF-INSP-002 — Inspiration collection store and provider adapters (AMENDMENT-012).

Tenant-scoped collection-run, trend-item, and append-only observation
persistence in SQLite. Provider adapters normalize documented responses into
the evidence contract; shared HTTP, retry, rate-limit, redaction, and cache
mechanics are reused across adapters. Collection runs via scheduled or queued
manual job — never synchronously on page render.

Mechanical only. Adapters convert provider responses into the normalized
contract and preserve provider-specific metric names. Unknown response shapes
fail visibly and retain a sanitized diagnostic; they never emit empty success.

Observations are append-only. Item identity is deduped by
(business_slug, provider, native_id). A failed provider preserves the last
good snapshot and appends an error observation; it never erases prior data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlencode

import requests

from inspiration_contracts import (
    ADAPTER_VERSION,
    COLLECTION_RUN_STATUS_AUTH_FAILED,
    COLLECTION_RUN_STATUS_EMPTY,
    COLLECTION_RUN_STATUS_ERROR,
    COLLECTION_RUN_STATUS_OK,
    COLLECTION_RUN_STATUS_PARTIAL,
    COLLECTION_RUN_STATUS_RATE_LIMITED,
    ENDPOINT_MEANING_TO_LABEL,
    InspirationContractError,
    apply_redaction,
    compute_safe_payload_hash,
    is_stale,
    make_collection_run,
    make_observation,
    make_trend_item,
    normalize_metric,
    now_iso,
)

logger = logging.getLogger(__name__)

# ─── Adapter registry ───────────────────────────────────────────────────────
# Each adapter is a pure function: (fixture_or_response, provider_config) -> dict.
# Returns {"status": ..., "items": [...], "error_class": ..., "error_message": ...}
# where items are normalized trend-item dicts (before redaction/persistence).
# Adapters NEVER touch the network. The collection runner injects either a
# real HTTP response or a fixture dict, so tests use the same code path.

AdapterFn = Callable[[dict, dict], dict]


def _bundle_social_instagram_audio_adapter(response: dict, provider: dict) -> dict:
    """Bundle.social Instagram audio — ranked music + original sounds (chart)."""
    audio_type = provider.get("audio_type", "music")
    if not isinstance(response, dict):
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "response is not a dict"}
    if "audio" not in response:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "missing 'audio' key"}
    items_raw = response.get("audio")
    if not isinstance(items_raw, list):
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "'audio' is not a list"}
    items = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        native_id = str(raw.get("audio_id", "")).strip()
        if not native_id:
            continue
        duration_ms = raw.get("duration_in_ms") or 0
        item = make_trend_item(
            business_slug="",  # filled by runner
            provider=provider["name"],
            platform=provider["platform"],
            content_type="audio",
            native_id=native_id,
            canonical_url="",  # no native platform URL in this payload
            title=raw.get("title", "") or "",
            creator=raw.get("display_artist", "") or raw.get("ig_username", "") or "",
            description="",
            preview_url=raw.get("download_url", "") or "",
            thumbnail_url="",
            availability="available" if raw.get("download_url") else "link_only",
        )
        item["_metrics"] = {
            "usage_count": normalize_metric("usage_count", raw.get("usage_count")),
            "duration_s": normalize_metric("duration_s", round(duration_ms / 1000, 3) if duration_ms else None, unit="s"),
            "audio_type": normalize_metric("audio_type", audio_type),
        }
        item["_rank"] = None  # chart payload is ranked, but no explicit rank number
        item["_raw"] = raw
        items.append(item)
    status = COLLECTION_RUN_STATUS_OK if items else COLLECTION_RUN_STATUS_EMPTY
    return {"status": status, "items": items, "error_class": "", "error_message": ""}


def _tikhub_tiktok_audio_charts_adapter(response: dict, provider: dict) -> dict:
    """TikHub TikTok Top 50 / Viral 50 audio charts.
    Handles two response shapes:
    - Fixture: {data: [{music_id, title, author, ...}]}
    - Live: {data: {music_list: [{id, music_info: {id, title, author, duration, ...}, trend}]}}
    """
    chart_label = provider.get("chart_label", "TikTok chart")
    if not isinstance(response, dict):
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "response is not a dict"}
    if "data" not in response:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "missing 'data' key"}
    data = response.get("data")
    # Live shape: data is a dict with 'music_list'
    if isinstance(data, dict) and "music_list" in data:
        items_raw = data.get("music_list") or []
        # Each item: {id, music_info: {...}, trend}
        normalized = []
        for entry in items_raw if isinstance(items_raw, list) else []:
            if not isinstance(entry, dict):
                continue
            mi = entry.get("music_info") or {}
            native_id = str(mi.get("id") or entry.get("id") or "").strip()
            if not native_id:
                continue
            play_url = mi.get("play_url")
            url_list = play_url.get("url_list") if isinstance(play_url, dict) else []
            preview = url_list[0] if url_list else ""
            normalized.append({"native_id": native_id, "title": mi.get("title", ""),
                              "author": mi.get("author", ""), "duration": mi.get("duration"),
                              "play_count": mi.get("play_count"), "use_count": mi.get("use_count"),
                              "is_commercial_music": mi.get("is_commercial_music"),
                              "trend": entry.get("trend"), "preview_url": preview, "_raw": entry})
    elif isinstance(data, list):
        # Fixture shape: data is a list of {music_id, title, author, ...}
        normalized = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            native_id = str(raw.get("music_id", "")).strip()
            if not native_id:
                continue
            normalized.append({"native_id": native_id, "title": raw.get("title", ""),
                              "author": raw.get("author", ""), "duration": raw.get("duration"),
                              "play_count": raw.get("play_count"), "use_count": raw.get("use_count"),
                              "is_commercial_music": raw.get("is_commercial_music"),
                              "trend": None, "preview_url": raw.get("preview_url", ""), "_raw": raw})
    else:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "'data' is neither list nor dict with music_list"}

    items = []
    for idx, norm in enumerate(normalized):
        item = make_trend_item(
            business_slug="",
            provider=provider["name"],
            platform=provider["platform"],
            content_type="audio",
            native_id=norm["native_id"],
            canonical_url="",
            title=norm.get("title", "") or "",
            creator=norm.get("author", "") or "",
            description="",
            preview_url=norm.get("preview_url", "") or "",
            thumbnail_url="",
            availability="available" if norm.get("preview_url") else "link_only",
        )
        item["_metrics"] = {
            "play_count": normalize_metric("play_count", norm.get("play_count")),
            "use_count": normalize_metric("use_count", norm.get("use_count")),
            "duration": normalize_metric("duration", norm.get("duration"), unit="s"),
            "is_commercial_music": normalize_metric("is_commercial_music", norm.get("is_commercial_music")),
            "chart": normalize_metric("chart", chart_label),
        }
        if norm.get("trend") is not None:
            item["_metrics"]["trend"] = normalize_metric("trend", norm.get("trend"))
        item["_rank"] = idx + 1
        item["_raw"] = norm.get("_raw", {})
        items.append(item)
    status = COLLECTION_RUN_STATUS_OK if items else COLLECTION_RUN_STATUS_EMPTY
    return {"status": status, "items": items, "error_class": "", "error_message": ""}


def _tikhub_tiktok_video_feed_adapter(response: dict, provider: dict) -> dict:
    """TikHub TikTok video search (recommendation evidence).
    Handles two shapes:
    - Fixture: {data: [{video_id, desc, nickname, ...}]}
    - Live: {data: {search_item_list: [{aweme_info: {aweme_id, desc, author, statistics, video, music}}]}}
    """
    if not isinstance(response, dict):
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "response is not a dict"}
    if "data" not in response:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "missing 'data' key"}
    data = response.get("data")

    # Live shape: data is a dict with 'search_item_list' or 'aweme_list'
    if isinstance(data, dict):
        raw_list = data.get("search_item_list") or data.get("aweme_list") or []
        normalized = []
        for entry in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(entry, dict):
                continue
            ai = entry.get("aweme_info") or entry.get("search_aweme_info") or entry
            native_id = str(ai.get("aweme_id") or ai.get("id") or "").strip()
            if not native_id:
                continue
            stats = ai.get("statistics") or {}
            author = ai.get("author") or {}
            music = ai.get("music") or {}
            video = ai.get("video") or {}
            cover = video.get("cover") or video.get("origin_cover") or {}
            cover_urls = cover.get("url_list") if isinstance(cover, dict) else []
            play_addr = video.get("play_addr") or {}
            play_urls = play_addr.get("url_list") if isinstance(play_addr, dict) else []
            create_time = ai.get("create_time")
            posted_at = ""
            if isinstance(create_time, (int, float)) and create_time > 0:
                from datetime import datetime, timezone
                posted_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
            normalized.append({
                "native_id": native_id, "desc": ai.get("desc", "") or "",
                "nickname": author.get("nickname", "") or "",
                "play_count": stats.get("play_count"), "digg_count": stats.get("digg_count"),
                "comment_count": stats.get("comment_count"), "share_count": stats.get("share_count"),
                "music_id": str(music.get("id", "") or ""), "music_title": music.get("title", "") or "",
                "cover": cover_urls[0] if cover_urls else "", "play_url": play_urls[0] if play_urls else "",
                "posted_at": posted_at, "_raw": entry,
            })
    elif isinstance(data, list):
        # Fixture shape
        normalized = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            native_id = str(raw.get("video_id", "")).strip()
            if not native_id:
                continue
            create_time = raw.get("create_time")
            posted_at = ""
            if isinstance(create_time, (int, float)) and create_time > 0:
                from datetime import datetime, timezone
                posted_at = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
            normalized.append({
                "native_id": native_id, "desc": raw.get("desc", "") or "",
                "nickname": raw.get("nickname", "") or "",
                "play_count": raw.get("play_count"), "digg_count": raw.get("digg_count"),
                "comment_count": raw.get("comment_count"), "share_count": raw.get("share_count"),
                "music_id": str(raw.get("music_id", "") or ""), "music_title": raw.get("music_title", "") or "",
                "cover": raw.get("cover", "") or "", "play_url": raw.get("play_url", "") or "",
                "posted_at": posted_at, "_raw": raw,
            })
    else:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "'data' is neither list nor dict"}

    items = []
    for idx, norm in enumerate(normalized):
        item = make_trend_item(
            business_slug="",
            provider=provider["name"],
            platform=provider["platform"],
            content_type="video",
            native_id=norm["native_id"],
            canonical_url="",
            title="",
            creator=norm.get("nickname", "") or "",
            description=norm.get("desc", "") or "",
            preview_url=norm.get("play_url", "") or "",
            thumbnail_url=norm.get("cover", "") or "",
            availability="available" if norm.get("play_url") else "link_only",
        )
        item["_posted_at"] = norm.get("posted_at", "")
        item["_linked_audio_id"] = norm.get("music_id", "")
        item["_linked_audio_title"] = norm.get("music_title", "")
        item["_metrics"] = {
            "play_count": normalize_metric("play_count", norm.get("play_count")),
            "digg_count": normalize_metric("digg_count", norm.get("digg_count")),
            "comment_count": normalize_metric("comment_count", norm.get("comment_count")),
            "share_count": normalize_metric("share_count", norm.get("share_count")),
        }
        item["_rank"] = idx + 1
        item["_raw"] = norm.get("_raw", {})
        items.append(item)
    status = COLLECTION_RUN_STATUS_OK if items else COLLECTION_RUN_STATUS_EMPTY
    return {"status": status, "items": items, "error_class": "", "error_message": ""}


def _tikhub_instagram_reels_adapter(response: dict, provider: dict) -> dict:
    """TikHub Instagram Reels search.
    Handles two shapes:
    - Fixture: {data: [{code, caption, username, ...}]}
    - Live: {data: {data: {items: [{code, caption: {text}, user: {username}, video_versions: [{url}], ...}]}}}
    """
    if not isinstance(response, dict):
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "response is not a dict"}
    if "data" not in response:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "missing 'data' key"}
    data = response.get("data")

    # Live shape: data is a dict with nested data.items
    if isinstance(data, dict):
        inner = data.get("data") if isinstance(data.get("data"), (dict, list)) else data
        if isinstance(inner, dict):
            raw_list = inner.get("items") or []
        elif isinstance(inner, list):
            raw_list = inner
        else:
            raw_list = []
        normalized = []
        for raw in raw_list if isinstance(raw_list, list) else []:
            if not isinstance(raw, dict):
                continue
            native_id = str(raw.get("code", "") or raw.get("id", "") or "").strip()
            if not native_id:
                continue
            caption = raw.get("caption") or {}
            caption_text = caption.get("text", "") if isinstance(caption, dict) else str(caption or "")
            user = raw.get("user") or {}
            video_versions = raw.get("video_versions") or []
            video_url = video_versions[0].get("url", "") if video_versions and isinstance(video_versions[0], dict) else ""
            thumb = raw.get("image_versions") or {}
            thumb_urls = thumb.get("candidates") if isinstance(thumb, dict) else []
            thumb_url = thumb_urls[0].get("url", "") if thumb_urls and isinstance(thumb_urls[0], dict) else ""
            taken_at = raw.get("taken_at") or raw.get("taken_at_utc")
            posted_at = ""
            if isinstance(taken_at, (int, float)) and taken_at > 0:
                from datetime import datetime, timezone
                posted_at = datetime.fromtimestamp(int(taken_at), tz=timezone.utc).isoformat()
            normalized.append({
                "native_id": native_id, "caption": caption_text,
                "username": user.get("username", "") or "",
                "like_count": raw.get("like_count"), "comment_count": raw.get("comment_count"),
                "video_url": video_url, "thumbnail_url": thumb_url,
                "posted_at": posted_at, "_raw": raw,
            })
    elif isinstance(data, list):
        # Fixture shape
        normalized = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            native_id = str(raw.get("code", "")).strip()
            if not native_id:
                continue
            taken_at = raw.get("taken_at")
            posted_at = ""
            if isinstance(taken_at, (int, float)) and taken_at > 0:
                from datetime import datetime, timezone
                posted_at = datetime.fromtimestamp(int(taken_at), tz=timezone.utc).isoformat()
            normalized.append({
                "native_id": native_id, "caption": raw.get("caption", "") or "",
                "username": raw.get("username", "") or "",
                "like_count": raw.get("like_count"), "comment_count": raw.get("comment_count"),
                "video_url": raw.get("video_url", "") or "",
                "thumbnail_url": raw.get("thumbnail_url", "") or "",
                "posted_at": posted_at, "_raw": raw,
            })
    else:
        return {"status": COLLECTION_RUN_STATUS_ERROR, "items": [],
                "error_class": "MalformedResponse", "error_message": "'data' is neither list nor dict"}

    items = []
    for idx, norm in enumerate(normalized):
        item = make_trend_item(
            business_slug="",
            provider=provider["name"],
            platform=provider["platform"],
            content_type="video",
            native_id=norm["native_id"],
            canonical_url="",
            title="",
            creator=norm.get("username", "") or "",
            description=norm.get("caption", "") or "",
            preview_url=norm.get("video_url", "") or "",
            thumbnail_url=norm.get("thumbnail_url", "") or "",
            availability="available" if norm.get("video_url") else "link_only",
        )
        item["_posted_at"] = norm.get("posted_at", "")
        item["_metrics"] = {
            "like_count": normalize_metric("like_count", norm.get("like_count")),
            "comment_count": normalize_metric("comment_count", norm.get("comment_count")),
        }
        item["_rank"] = idx + 1
        item["_raw"] = norm.get("_raw", {})
        items.append(item)
    status = COLLECTION_RUN_STATUS_OK if items else COLLECTION_RUN_STATUS_EMPTY
    return {"status": status, "items": items, "error_class": "", "error_message": ""}


ADAPTERS: dict[str, AdapterFn] = {
    "bundle_social_instagram_audio": _bundle_social_instagram_audio_adapter,
    "tikhub_tiktok_audio_charts": _tikhub_tiktok_audio_charts_adapter,
    "tikhub_tiktok_video_feed": _tikhub_tiktok_video_feed_adapter,
    "tikhub_instagram_reels": _tikhub_instagram_reels_adapter,
}


def _platform_url(platform: str, content_type: str, native_id: str,
                   platform_urls: dict | None = None) -> str:
    """Construct a canonical platform URL from the native ID using config templates.
    Returns empty string if no template matches."""
    if not platform_urls or not native_id:
        return ""
    # Build the lookup key: platform + content_type
    key = f"{platform}_{content_type}"
    template = platform_urls.get(key, "")
    if not template:
        # Fallback: try platform alone
        template = platform_urls.get(platform, "")
    if not template:
        return ""
    return template.replace("{native_id}", native_id)


# ─── HTTP fetch (shared mechanics) ───────────────────────────────────────────

def _http_get(url: str, *, headers: dict, params: dict, timeout: int) -> requests.Response:
    """Shared HTTP GET with timeout. Adapters never call this directly; the
    runner calls it so tests inject fixtures instead."""
    return requests.get(url, headers=headers, params=params, timeout=timeout)


def _classify_http_error(status_code: int) -> tuple[str, str]:
    """Map an HTTP status to a collection-run status + error class."""
    if status_code in (401, 403):
        return COLLECTION_RUN_STATUS_AUTH_FAILED, "AuthError"
    if status_code == 429:
        return COLLECTION_RUN_STATUS_RATE_LIMITED, "RateLimitError"
    if status_code >= 500:
        return COLLECTION_RUN_STATUS_ERROR, "ServerError"
    return COLLECTION_RUN_STATUS_ERROR, "HTTPError"


# ─── Credentials (env-var only) ──────────────────────────────────────────────

def _credentials(provider: dict) -> dict:
    creds = {}
    for key, config_key in (("api_key", "api_key_env"), ("team_id", "team_id_env")):
        env_name = provider.get(config_key)
        if env_name:
            creds[key] = os.environ.get(env_name, "")
    return creds


# ─── Store ───────────────────────────────────────────────────────────────────

class InspirationStore:
    """Tenant-scoped collection-run, trend-item, and append-only observation store."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS insp_collection_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_slug TEXT NOT NULL,
        provider TEXT NOT NULL,
        endpoint_key TEXT NOT NULL,
        platform TEXT NOT NULL,
        region TEXT NOT NULL,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT NOT NULL,
        request_params TEXT NOT NULL DEFAULT '{}',
        result_count INTEGER NOT NULL DEFAULT 0,
        response_hash TEXT NOT NULL DEFAULT '',
        adapter_version TEXT NOT NULL,
        error_class TEXT NOT NULL DEFAULT '',
        error_message TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_insp_runs_tenant_provider
        ON insp_collection_runs(business_slug, provider, id);

    CREATE TABLE IF NOT EXISTS insp_trend_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_slug TEXT NOT NULL,
        provider TEXT NOT NULL,
        platform TEXT NOT NULL,
        content_type TEXT NOT NULL,
        native_id TEXT NOT NULL,
        canonical_url TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        creator TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        preview_url TEXT NOT NULL DEFAULT '',
        thumbnail_url TEXT NOT NULL DEFAULT '',
        availability TEXT NOT NULL DEFAULT 'unknown',
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        observation_count INTEGER NOT NULL DEFAULT 0,
        UNIQUE(business_slug, provider, native_id)
    );
    CREATE INDEX IF NOT EXISTS idx_insp_items_tenant_section
        ON insp_trend_items(business_slug, content_type, id);

    CREATE TABLE IF NOT EXISTS insp_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_slug TEXT NOT NULL,
        collection_run_id INTEGER NOT NULL,
        trend_item_id INTEGER NOT NULL,
        collected_at TEXT NOT NULL,
        rank INTEGER,
        metrics_json TEXT NOT NULL DEFAULT '{}',
        evidence_label TEXT NOT NULL,
        safe_payload_hash TEXT NOT NULL,
        availability TEXT NOT NULL DEFAULT 'unknown',
        posted_at TEXT NOT NULL DEFAULT '',
        linked_audio_id TEXT NOT NULL DEFAULT '',
        linked_audio_title TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (collection_run_id) REFERENCES insp_collection_runs(id),
        FOREIGN KEY (trend_item_id) REFERENCES insp_trend_items(id)
    );
    CREATE INDEX IF NOT EXISTS idx_insp_obs_item
        ON insp_observations(trend_item_id, collected_at);
    CREATE INDEX IF NOT EXISTS idx_insp_obs_run
        ON insp_observations(collection_run_id);
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_collection_run(self, run: dict) -> int:
        """Persist a validated collection run. Returns the run ID."""
        errors = []
        from inspiration_contracts import validate_collection_run
        errors = validate_collection_run(run)
        if errors:
            raise InspirationContractError("; ".join(errors))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO insp_collection_runs
                   (business_slug, provider, endpoint_key, platform, region, status,
                    started_at, ended_at, request_params, result_count, response_hash,
                    adapter_version, error_class, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    run["business_slug"], run["provider"], run["endpoint_key"],
                    run["platform"], run["region"], run["status"],
                    run["started_at"], run["ended_at"],
                    json.dumps(run.get("request_params", {})),
                    run.get("result_count", 0),
                    run.get("response_hash", ""),
                    run.get("adapter_version", ADAPTER_VERSION),
                    run.get("error_class", ""),
                    run.get("error_message", ""),
                ),
            )
            run_id = cursor.lastrowid
            conn.commit()
            return run_id

    def upsert_trend_item(self, item: dict) -> tuple[int, bool]:
        """Insert or update a trend item. Returns (item_id, is_new).
        Item metadata may gain a new version; observation history is not overwritten.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing = conn.execute(
                """SELECT id, first_seen, observation_count FROM insp_trend_items
                   WHERE business_slug=? AND provider=? AND native_id=?""",
                (item["business_slug"], item["provider"], item["native_id"]),
            ).fetchone()
            now = self._now()
            if existing:
                conn.execute(
                    """UPDATE insp_trend_items SET
                       canonical_url=?, title=?, creator=?, description=?,
                       preview_url=?, thumbnail_url=?, availability=?, last_seen=?
                       WHERE id=?""",
                    (item.get("canonical_url", ""), item.get("title", ""),
                     item.get("creator", ""), item.get("description", ""),
                     item.get("preview_url", ""), item.get("thumbnail_url", ""),
                     item.get("availability", "unknown"), now, existing["id"]),
                )
                conn.commit()
                return existing["id"], False
            cursor = conn.execute(
                """INSERT INTO insp_trend_items
                   (business_slug, provider, platform, content_type, native_id,
                    canonical_url, title, creator, description, preview_url,
                    thumbnail_url, availability, first_seen, last_seen, observation_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (item["business_slug"], item["provider"], item["platform"],
                 item["content_type"], item["native_id"],
                 item.get("canonical_url", ""), item.get("title", ""),
                 item.get("creator", ""), item.get("description", ""),
                 item.get("preview_url", ""), item.get("thumbnail_url", ""),
                 item.get("availability", "unknown"), now, now),
            )
            item_id = cursor.lastrowid
            conn.commit()
            return item_id, True

    def append_observation(self, obs: dict, *, item_id: int | None = None) -> int:
        """Append an observation. Increments the item's observation_count.
        Observations are append-only — never overwritten.
        """
        from inspiration_contracts import validate_observation
        errors = validate_observation(obs)
        if errors:
            raise InspirationContractError("; ".join(errors))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """INSERT INTO insp_observations
                   (business_slug, collection_run_id, trend_item_id, collected_at,
                    rank, metrics_json, evidence_label, safe_payload_hash,
                    availability, posted_at, linked_audio_id, linked_audio_title)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    obs.get("business_slug", ""),
                    obs["collection_run_id"], obs["trend_item_id"],
                    obs["collected_at"], obs.get("rank"),
                    json.dumps(obs.get("metrics", {})),
                    obs["evidence_label"], obs["safe_payload_hash"],
                    obs.get("availability", "unknown"),
                    obs.get("posted_at", ""),
                    obs.get("linked_audio_id", ""),
                    obs.get("linked_audio_title", ""),
                ),
            )
            obs_id = cursor.lastrowid
            # increment observation_count on the item
            conn.execute(
                """UPDATE insp_trend_items SET observation_count = observation_count + 1
                   WHERE id = ?""",
                (obs["trend_item_id"],),
            )
            conn.commit()
            return obs_id

    def get_latest_runs_by_provider(self, business_slug: str) -> list[dict]:
        """Return the most recent collection run per provider for a tenant."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT r.* FROM insp_collection_runs r
                   INNER JOIN (
                       SELECT provider, MAX(id) AS max_id
                       FROM insp_collection_runs
                       WHERE business_slug = ?
                       GROUP BY provider
                   ) latest ON r.id = latest.max_id
                   WHERE r.business_slug = ?""",
                (business_slug, business_slug),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_items_for_section(self, business_slug: str, content_type: str,
                              provider_names: list[str] | None = None) -> list[dict]:
        """Return trend items for a section (audio/video), with their latest observation."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if provider_names:
                placeholders = ",".join("?" for _ in provider_names)
                rows = conn.execute(
                    f"""SELECT i.*, o.collected_at AS obs_collected_at, o.rank AS obs_rank,
                               o.metrics_json AS obs_metrics, o.evidence_label AS obs_label,
                               o.safe_payload_hash AS obs_hash, o.availability AS obs_availability,
                               o.posted_at AS obs_posted_at, o.linked_audio_id AS obs_linked_audio_id,
                               o.linked_audio_title AS obs_linked_audio_title,
                               r.status AS run_status, r.provider AS run_provider,
                               r.region AS run_region, r.ended_at AS run_ended_at,
                               r.error_class AS run_error_class
                        FROM insp_trend_items i
                        LEFT JOIN insp_observations o ON o.id = (
                            SELECT id FROM insp_observations
                            WHERE trend_item_id = i.id
                            ORDER BY collected_at DESC LIMIT 1
                        )
                        LEFT JOIN insp_collection_runs r ON r.id = o.collection_run_id
                        WHERE i.business_slug = ? AND i.content_type = ?
                          AND i.provider IN ({placeholders})
                        ORDER BY i.provider, (o.rank IS NULL), o.rank ASC, i.id ASC""",
                    (business_slug, content_type, *provider_names),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT i.*, o.collected_at AS obs_collected_at, o.rank AS obs_rank,
                              o.metrics_json AS obs_metrics, o.evidence_label AS obs_label,
                              o.safe_payload_hash AS obs_hash, o.availability AS obs_availability,
                              o.posted_at AS obs_posted_at, o.linked_audio_id AS obs_linked_audio_id,
                              o.linked_audio_title AS obs_linked_audio_title,
                              r.status AS run_status, r.provider AS run_provider,
                              r.region AS run_region, r.ended_at AS run_ended_at,
                              r.error_class AS run_error_class
                       FROM insp_trend_items i
                       LEFT JOIN insp_observations o ON o.id = (
                           SELECT id FROM insp_observations
                           WHERE trend_item_id = i.id
                           ORDER BY collected_at DESC LIMIT 1
                       )
                       LEFT JOIN insp_collection_runs r ON r.id = o.collection_run_id
                       WHERE i.business_slug = ? AND i.content_type = ?
                       ORDER BY i.provider, (o.rank IS NULL), o.rank ASC, i.id ASC""",
                    (business_slug, content_type),
                ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["obs_metrics"] = json.loads(d.get("obs_metrics") or "{}")
                results.append(d)
            return results

    def get_observation_history(self, trend_item_id: int) -> list[dict]:
        """Return all observations for an item, oldest first (append-only history)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM insp_observations
                   WHERE trend_item_id = ?
                   ORDER BY collected_at ASC, id ASC""",
                (trend_item_id,),
            ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                d["metrics"] = json.loads(d.get("metrics_json") or "{}")
                results.append(d)
            return results


# ─── Collection runner ──────────────────────────────────────────────────────

def run_collection(
    *,
    business_slug: str,
    provider_config: dict,
    redaction_config: dict,
    store: InspirationStore,
    fetcher: Callable[[str, dict, dict, int], object] | None = None,
    response_override: dict | None = None,
    platform_urls: dict | None = None,
) -> dict:
    """Execute one collection run for one provider.

    `response_override` (fixture) takes precedence over `fetcher` (network).
    Tests pass response_override; the live smoke passes fetcher + real credentials.
    `platform_urls` is the config-driven URL template dict for constructing
    canonical platform links from native IDs.
    Returns the persisted collection run dict (with run_id).
    """
    adapter_name = provider_config.get("adapter")
    adapter = ADAPTERS.get(adapter_name)
    if not adapter:
        run = make_collection_run(
            business_slug=business_slug,
            provider=provider_config.get("name", "unknown"),
            endpoint_key=provider_config.get("chart_key", provider_config.get("endpoint_meaning", "")),
            platform=provider_config.get("platform", ""),
            region=provider_config.get("region", ""),
            status=COLLECTION_RUN_STATUS_ERROR,
            started_at=now_iso(),
            ended_at=now_iso(),
            error_class="AdapterMissing",
            error_message=f"adapter '{adapter_name}' is not registered",
        )
        run_id = store.save_collection_run(run)
        run["id"] = run_id
        return run

    started = now_iso()
    endpoint_meaning = provider_config.get("endpoint_meaning", "recommendation")
    evidence_label = ENDPOINT_MEANING_TO_LABEL.get(endpoint_meaning, "recommendation")

    # Get the response: fixture override or live HTTP
    raw_response: dict
    if response_override is not None:
        raw_response = response_override
    else:
        creds = _credentials(provider_config)
        if provider_config.get("api_key_env") and not creds.get("api_key"):
            run = make_collection_run(
                business_slug=business_slug,
                provider=provider_config["name"],
                endpoint_key=provider_config.get("chart_key", endpoint_meaning),
                platform=provider_config["platform"],
                region=provider_config.get("region", ""),
                status=COLLECTION_RUN_STATUS_AUTH_FAILED,
                started_at=started, ended_at=now_iso(),
                error_class="AuthError",
                error_message="provider credential is unavailable",
            )
            run_id = store.save_collection_run(run)
            run["id"] = run_id
            return run
        url = provider_config.get("endpoint") or (provider_config.get("base_url", "") + provider_config.get("path", ""))
        headers = {}
        params = {}
        # TikHub uses Bearer auth; Bundle.social uses x-api-key
        if provider_config.get("base_url") == "https://api.tikhub.io" or "tikhub" in provider_config.get("name", "").lower():
            headers["Authorization"] = f"Bearer {creds.get('api_key', '')}"
        else:
            headers["x-api-key"] = creds.get("api_key", "")
        if creds.get("team_id"):
            params["teamId"] = creds["team_id"]
        # Provider-specific params from config (config-driven, not hardcoded)
        # Bundle.social: audioType, searchQuery, region
        if "audio_types" in provider_config:
            # The runner iterates audio types; for live, we pass the first type
            params.setdefault("audioType", provider_config["audio_types"][0])
        if "region" in provider_config and "tikhub" not in provider_config.get("name", "").lower():
            # Only pass region to non-TikHub providers (TikHub search rejects it)
            params.setdefault("region", provider_config["region"])
        # TikHub music chart: scene param (0=Top 50, 1=Viral 50)
        if "chart_key" in provider_config:
            scene_map = {"top_50": 0, "viral_50": 1}
            params.setdefault("scene", provider_config.get("scene", scene_map.get(provider_config["chart_key"], 0)))
            params.setdefault("count", provider_config.get("limits", {}).get("max_items", 50))
        # TikHub video search: keyword param
        if "search_keyword" in provider_config:
            params.setdefault("keyword", provider_config["search_keyword"])
            params.setdefault("count", provider_config.get("limits", {}).get("max_items", 20))
        # TikHub IG reels: first param + keyword
        if provider_config.get("adapter") == "tikhub_instagram_reels":
            params.setdefault("first", provider_config.get("limits", {}).get("max_items", 12))
            if "search_keyword" in provider_config:
                params.setdefault("keyword", provider_config["search_keyword"])
        timeout = int(provider_config.get("limits", {}).get("timeout_seconds", 30))
        try:
            resp = (fetcher or _http_get)(url, headers=headers, params=params, timeout=timeout)
            status_code = getattr(resp, "status_code", 200)
            if status_code >= 400:
                status, error_class = _classify_http_error(status_code)
                run = make_collection_run(
                    business_slug=business_slug,
                    provider=provider_config["name"],
                    endpoint_key=provider_config.get("chart_key", endpoint_meaning),
                    platform=provider_config["platform"],
                    region=provider_config.get("region", ""),
                    status=status,
                    started_at=started, ended_at=now_iso(),
                    error_class=error_class,
                    error_message=f"HTTP {status_code}",
                )
                run_id = store.save_collection_run(run)
                run["id"] = run_id
                return run
            raw_response = resp.json()
        except (requests.RequestException, ValueError) as exc:
            run = make_collection_run(
                business_slug=business_slug,
                provider=provider_config["name"],
                endpoint_key=provider_config.get("chart_key", endpoint_meaning),
                platform=provider_config["platform"],
                region=provider_config.get("region", ""),
                status=COLLECTION_RUN_STATUS_ERROR,
                started_at=started, ended_at=now_iso(),
                error_class="RequestError",
                error_message=type(exc).__name__,
            )
            run_id = store.save_collection_run(run)
            run["id"] = run_id
            return run

    # Run the adapter on the response
    adapter_result = adapter(raw_response, provider_config)
    status = adapter_result["status"]
    normalized_items = adapter_result["items"]

    # Redact + hash each item's raw payload, then persist
    response_hash = compute_safe_payload_hash(apply_redaction(raw_response, redaction_config))
    ended = now_iso()
    run = make_collection_run(
        business_slug=business_slug,
        provider=provider_config["name"],
        endpoint_key=provider_config.get("chart_key", endpoint_meaning),
        platform=provider_config["platform"],
        region=provider_config.get("region", ""),
        status=status,
        started_at=started, ended_at=ended,
        request_params={},  # sanitized — no secrets
        result_count=len(normalized_items),
        response_hash=response_hash,
        error_class=adapter_result.get("error_class", ""),
        error_message=adapter_result.get("error_message", ""),
    )
    run_id = store.save_collection_run(run)
    run["id"] = run_id

    secret_params = redaction_config.get("url_param_names") or []
    # Platform URL templates for constructing canonical links from native IDs
    p_urls = platform_urls or {}
    for item in normalized_items:
        item["business_slug"] = business_slug
        # Construct canonical URL from native ID if not already set
        if not item.get("canonical_url"):
            item["canonical_url"] = _platform_url(
                item.get("platform", ""), item.get("content_type", ""),
                item.get("native_id", ""), p_urls)
        # Redact URL fields on the item itself before persistence
        for url_field in ("preview_url", "thumbnail_url", "canonical_url"):
            if item.get(url_field):
                from inspiration_contracts import redact_url
                item[url_field] = redact_url(item[url_field], secret_params)
        # Redact the raw payload before hashing/storing
        safe_raw = apply_redaction(item.pop("_raw", {}), redaction_config)
        item_id, _is_new = store.upsert_trend_item(item)
        # Build the observation
        metrics = item.pop("_metrics", {})
        rank = item.pop("_rank", None)
        posted_at = item.pop("_posted_at", "")
        linked_audio_id = item.pop("_linked_audio_id", "")
        linked_audio_title = item.pop("_linked_audio_title", "")
        safe_hash = compute_safe_payload_hash(safe_raw)
        obs = make_observation(
            collection_run_id=run_id,
            trend_item_id=item_id,
            collected_at=ended,
            evidence_label=evidence_label,
            safe_payload_hash=safe_hash,
            rank=rank,
            metrics=metrics,
            availability=item.get("availability", "unknown"),
        )
        obs["business_slug"] = business_slug
        obs["posted_at"] = posted_at
        obs["linked_audio_id"] = linked_audio_id
        obs["linked_audio_title"] = linked_audio_title
        store.append_observation(obs, item_id=item_id)

    return run