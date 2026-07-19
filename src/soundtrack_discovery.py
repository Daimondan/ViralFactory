"""Soundtrack discovery service (VF-VS-510, DIVERGENCE-015).

Searches commercial-safe audio catalogs via API, collects candidates, and
filters by hard constraints (duration, commercial-safe, preview available).

Sources are config-driven — no business values in code. The discovery service
is purely mechanical: it searches, filters, and returns candidates. The LLM
ranking step (VF-VS-511) does the judgment.

Config block (config/models.yaml):
  soundtrack:
    discovery:
      sources:
        - name: "bundle_instagram"
          provider: "bundle.social"
          api_key_env: "BUNDLE_SOCIAL_API_KEY"
          team_id_env: "BUNDLE_TEAM_ID"
        - name: "pixabay"
          provider: "pixabay"
          api_key_env: "PIXABAY_API_KEY"
      search_queries_from: "draft.visual_direction.music"
      min_duration_s: 30
      require_preview_url: true
      require_commercial_safe: true
      max_candidates_per_source: 50
"""

from __future__ import annotations

import json
import os
import logging
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class SoundtrackDiscoveryError(Exception):
    """Raised when discovery fails critically (all sources down)."""


# ── Candidate shape ──────────────────────────────────────────────────────────

def _make_candidate(
    source: str,
    external_id: str,
    title: str,
    artist: str,
    duration_s: float,
    preview_url: str,
    download_url: str,
    license_type: str,
    audio_id: str = "",
    usage_count: int = 0,
    raw: dict | None = None,
) -> dict:
    """Build a normalized candidate dict."""
    return {
        "source": source,
        "external_id": str(external_id),
        "audio_id": str(audio_id) if audio_id else str(external_id),
        "title": title or "",
        "artist": artist or "",
        "duration_s": float(duration_s) if duration_s else 0.0,
        "preview_url": preview_url or "",
        "download_url": download_url or "",
        "license": license_type,
        "commercial_safe": True,
        "usage_count": int(usage_count),
        "raw": raw or {},
    }


# ── Bundle.social (Instagram audio) ─────────────────────────────────────────

BUNDLE_API_BASE = "https://api.bundle.social/api/v1"
BUNDLE_LICENSE = "Meta-authorized Instagram audio (commercial-safe for Reels)"


def _search_bundle_instagram(
    query: str, api_key: str, team_id: str, limit: int = 50,
) -> list[dict]:
    """Search Bundle.social Instagram audio API."""
    candidates = []
    # Search both music and original_sound types
    for audio_type in ("music", "original_sound"):
        try:
            resp = requests.get(
                f"{BUNDLE_API_BASE}/misc/instagram/audio",
                params={
                    "teamId": team_id,
                    "audioType": audio_type,
                    "searchQuery": query,
                },
                headers={"x-api-key": api_key},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            for a in data.get("audio", []):
                duration_ms = a.get("duration_in_ms") or 0
                duration_s = duration_ms / 1000.0 if duration_ms else 0.0
                candidates.append(_make_candidate(
                    source="bundle_instagram",
                    external_id=a.get("audio_id", ""),
                    audio_id=a.get("audio_id", ""),
                    title=a.get("title", ""),
                    artist=a.get("display_artist", "") or a.get("ig_username", ""),
                    duration_s=duration_s,
                    preview_url=a.get("download_url", ""),
                    download_url=a.get("download_url", ""),
                    license_type=BUNDLE_LICENSE,
                    raw=a,
                ))
        except requests.RequestException as e:
            logger.warning("Bundle.social audio search failed for '%s' (%s): %s",
                           query, audio_type, e)
    return candidates[:limit]


# ── Pixabay audio ────────────────────────────────────────────────────────────

PIXABAY_API_BASE = "https://pixabay.com/api"
PIXABAY_LICENSE = "Pixabay License (free, commercial-safe, no attribution required)"


def _search_pixabay(
    query: str, api_key: str, limit: int = 50,
) -> list[dict]:
    """Search Pixabay audio API."""
    try:
        resp = requests.get(
            f"{PIXABAY_API_BASE}/audio/",
            params={"key": api_key, "q": query, "per_page": min(limit, 50)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.warning("Pixabay audio search failed for '%s': %s", query, e)
        return []

    candidates = []
    for m in data.get("hits", []):
        candidates.append(_make_candidate(
            source="pixabay",
            external_id=m.get("id", ""),
            title=m.get("tags", f"Track {m.get('id')}"),
            artist=m.get("user", ""),
            duration_s=float(m.get("duration", 0)),
            preview_url=m.get("audio", ""),
            download_url=m.get("audio", ""),
            license_type=PIXABAY_LICENSE,
            raw=m,
        ))
    return candidates[:limit]


# ── Query derivation ──────────────────────────────────────────────────────────

def _derive_search_queries(
    audio_intent: dict, visual_direction: dict | None = None,
) -> list[str]:
    """Derive search queries from the Writer's audio/visual intent.

    The Writer produces `visual_direction.music` with mood, genre, tempo.
    We map those to short search terms (max 100 chars per Bundle.social API
    limit). No business values — the mapping is structural.
    """
    queries = []

    # From visual_direction.music block
    music_block = (visual_direction or {}).get("music", {})
    mood = music_block.get("mood", "")
    genre = music_block.get("genre", "")

    # Use short keywords — the full mood/genre strings can exceed the
    # 100-char API limit. Extract the first few words.
    def _short(s, max_words=3):
        words = str(s).split()
        return " ".join(words[:max_words])

    mood_short = _short(mood)
    genre_short = _short(genre)

    if mood_short and genre_short:
        queries.append(f"{mood_short} {genre_short}")
    if mood_short:
        queries.append(mood_short)
    if genre_short:
        queries.append(genre_short)

    # From beat audio_intent blocks
    intents = audio_intent.get("audio_intents", [])
    for intent in intents:
        ai = intent.get("audio_intent", {})
        if ai.get("mood") and ai["mood"] not in [q for q in queries]:
            queries.append(_short(ai["mood"]))

    # Fallback: if no queries derived, use a generic term
    if not queries:
        queries.append("instrumental")

    # Deduplicate, limit to 6 queries, truncate each to 90 chars (safe margin)
    seen = set()
    unique = []
    for q in queries:
        ql = q.lower().strip()[:90]
        if ql and ql not in seen:
            seen.add(ql)
            unique.append(q[:90])
    return unique[:6]


# ── Filter ───────────────────────────────────────────────────────────────────

def _filter_candidates(
    candidates: list[dict],
    min_duration_s: float = 30.0,
    require_preview_url: bool = True,
) -> list[dict]:
    """Filter candidates by hard constraints."""
    filtered = []
    for c in candidates:
        if require_preview_url and not c.get("preview_url"):
            continue
        if c["duration_s"] > 0 and c["duration_s"] < min_duration_s:
            continue
        if not c.get("commercial_safe", True):
            continue
        filtered.append(c)
    return filtered


# ── Main entry point ─────────────────────────────────────────────────────────

def discover_soundtrack_candidates(
    audio_intent: dict,
    visual_direction: dict | None,
    config: dict,
) -> dict:
    """Discover soundtrack candidates from configured sources.

    Args:
        audio_intent: Beat-level audio intents from the Writer.
        visual_direction: The draft's visual_direction block (contains music).
        config: The soundtrack config block from models.yaml.

    Returns:
        {
            "candidates": [...],
            "queries": [...],
            "sources_searched": [...],
            "errors": [...],
        }
    """
    discovery_config = config.get("discovery", {})
    sources = discovery_config.get("sources", [])
    min_duration_s = float(discovery_config.get("min_duration_s", 30))
    require_preview = bool(discovery_config.get("require_preview_url", True))
    max_per_source = int(discovery_config.get("max_candidates_per_source", 50))

    queries = _derive_search_queries(audio_intent, visual_direction)

    all_candidates = []
    sources_searched = []
    errors = []

    for source_cfg in sources:
        provider = source_cfg.get("provider", "")
        api_key_env = source_cfg.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "")

        if provider == "bundle.social":
            team_id_env = source_cfg.get("team_id_env", "")
            team_id = os.environ.get(team_id_env, "")
            if not api_key or not team_id:
                errors.append(f"{provider}: missing API key or team ID")
                continue
            sources_searched.append(provider)
            for q in queries:
                results = _search_bundle_instagram(
                    q, api_key, team_id, max_per_source,
                )
                all_candidates.extend(results)

        elif provider == "pixabay":
            if not api_key:
                errors.append(f"{provider}: missing API key")
                continue
            sources_searched.append(provider)
            for q in queries:
                results = _search_pixabay(q, api_key, max_per_source)
                all_candidates.extend(results)

        else:
            errors.append(f"Unknown provider: {provider}")

    # Deduplicate by source + external_id
    seen = set()
    deduped = []
    for c in all_candidates:
        key = f"{c['source']}:{c['external_id']}"
        if key not in seen:
            seen.add(key)
            deduped.append(c)

    # Filter by hard constraints
    filtered = _filter_candidates(deduped, min_duration_s, require_preview)

    return {
        "candidates": filtered,
        "queries": queries,
        "sources_searched": sources_searched,
        "total_found": len(deduped),
        "total_filtered": len(filtered),
        "errors": errors,
    }