"""Planner-led, config-driven soundtrack discovery (VF-VS-512).

The Soundtrack Planner owns search-query judgment. This module only normalizes,
deduplicates, caps, caches, and executes configured provider requests. Discovery
observations never imply production rights.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

import requests

logger = logging.getLogger(__name__)


class SoundtrackDiscoveryError(ValueError):
    """Raised when the planner/discovery contract cannot execute safely."""


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
    return {
        "source": source,
        "external_id": str(external_id),
        "audio_id": str(audio_id) if audio_id else str(external_id),
        "title": title or "",
        "artist": artist or "",
        "duration_s": float(duration_s) if duration_s else 0.0,
        "preview_url": preview_url or "",
        "download_url": download_url or "",
        "license_observation": license_type or "",
        "rights_status": "unknown",
        "usage_count": int(usage_count),
        "raw": raw or {},
    }


def normalize_search_queries(
    search_queries: list[str], *, max_queries: int, max_query_chars: int
) -> list[str]:
    """Normalize planner output without deriving or adding query meaning."""
    if not isinstance(search_queries, list):
        raise SoundtrackDiscoveryError("search_queries must be an array")
    if max_queries < 1 or max_query_chars < 1:
        raise SoundtrackDiscoveryError("search query limits must be positive")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_query in search_queries:
        if not isinstance(raw_query, str):
            raise SoundtrackDiscoveryError("every search_queries item must be text")
        query = " ".join(raw_query.split())[:max_query_chars]
        key = query.casefold()
        if query and key not in seen:
            normalized.append(query)
            seen.add(key)
        if len(normalized) >= max_queries:
            break
    if not normalized:
        raise SoundtrackDiscoveryError("search_queries must contain planner-authored text")
    return normalized


def _limits(source: dict) -> tuple[int, float]:
    limits = source.get("limits") or {}
    return (
        max(1, int(limits.get("max_candidates", 1))),
        max(0.1, float(limits.get("timeout_seconds", 10))),
    )


def _bundle_adapter(query: str, source: dict, credentials: dict) -> list[dict]:
    limit, timeout = _limits(source)
    candidates: list[dict] = []
    audio_types = source.get("audio_types") or ["music", "original_sound"]
    for audio_type in audio_types:
        try:
            response = requests.get(
                source["endpoint"],
                params={
                    "teamId": credentials.get("team_id", ""),
                    "audioType": audio_type,
                    "searchQuery": query,
                    "region": source.get("region", ""),
                },
                headers={"x-api-key": credentials["api_key"]},
                timeout=timeout,
            )
            response.raise_for_status()
            for item in response.json().get("audio", []):
                duration_ms = item.get("duration_in_ms") or 0
                candidates.append(_make_candidate(
                    source=source["name"],
                    external_id=item.get("audio_id", ""),
                    audio_id=item.get("audio_id", ""),
                    title=item.get("title", ""),
                    artist=item.get("display_artist", "") or item.get("ig_username", ""),
                    duration_s=duration_ms / 1000.0 if duration_ms else 0.0,
                    preview_url=item.get("download_url", ""),
                    download_url=item.get("download_url", ""),
                    license_type="",
                    usage_count=item.get("usage_count") or 0,
                    raw=item,
                ))
        except (KeyError, requests.RequestException, ValueError) as exc:
            logger.warning("Soundtrack provider %s failed: %s", source.get("name"), exc)
    return candidates[:limit]


def _pixabay_adapter(query: str, source: dict, credentials: dict) -> list[dict]:
    limit, timeout = _limits(source)
    try:
        response = requests.get(
            source["endpoint"],
            params={
                "key": credentials["api_key"],
                "q": query,
                "per_page": limit,
                "region": source.get("region", ""),
            },
            timeout=timeout,
        )
        response.raise_for_status()
        hits = response.json().get("hits", [])
    except (KeyError, requests.RequestException, ValueError) as exc:
        logger.warning("Soundtrack provider %s failed: %s", source.get("name"), exc)
        return []
    return [
        _make_candidate(
            source=source["name"],
            external_id=item.get("id", ""),
            title=item.get("tags", ""),
            artist=item.get("user", ""),
            duration_s=item.get("duration") or 0,
            preview_url=item.get("audio", ""),
            download_url=item.get("audio", ""),
            license_type="",
            raw=item,
        )
        for item in hits[:limit]
    ]


PROVIDER_ADAPTERS: dict[str, Callable[[str, dict, dict], list[dict]]] = {
    "bundle_social_instagram": _bundle_adapter,
    "pixabay_audio": _pixabay_adapter,
}
_CACHE: dict[tuple, tuple[float, list[dict]]] = {}


def _credentials(source: dict) -> dict:
    values = {}
    for key, config_key in (("api_key", "api_key_env"), ("team_id", "team_id_env")):
        env_name = source.get(config_key)
        if env_name:
            values[key] = os.environ.get(env_name, "")
    return values


def _validate_source(source: dict) -> list[str]:
    errors = []
    for field in ("name", "adapter", "endpoint", "region"):
        if not source.get(field):
            errors.append(f"provider {field} is required")
    capabilities = source.get("capabilities")
    if not isinstance(capabilities, list) or "audio_search" not in capabilities:
        errors.append("provider lacks audio_search capability")
    return errors


def _filter_candidates(
    candidates: list[dict],
    min_duration_s: float = 30.0,
    require_preview_url: bool = True,
) -> list[dict]:
    return [
        candidate for candidate in candidates
        if (not require_preview_url or candidate.get("preview_url"))
        and (
            candidate.get("duration_s", 0) == 0
            or candidate.get("duration_s", 0) >= min_duration_s
        )
    ]


def discover_soundtrack_candidates(search_queries: list[str], config: dict) -> dict:
    """Execute planner-authored queries against configured provider adapters."""
    discovery = config.get("discovery") or {}
    queries = normalize_search_queries(
        search_queries,
        max_queries=int(discovery.get("max_queries", 1)),
        max_query_chars=int(discovery.get("max_query_chars", 1)),
    )
    max_requests = max(0, int((discovery.get("budget") or {}).get("max_requests", 0)))
    ttl = max(0, int(discovery.get("cache_ttl_seconds", 0)))
    all_candidates: list[dict] = []
    sources_searched: list[str] = []
    errors: list[str] = []
    request_count = 0

    for source in discovery.get("sources") or []:
        if not source.get("enabled", False):
            continue
        source_errors = _validate_source(source)
        adapter = PROVIDER_ADAPTERS.get(source.get("adapter"))
        if not adapter:
            source_errors.append("provider adapter is not registered")
        credentials = _credentials(source)
        if source.get("api_key_env") and not credentials.get("api_key"):
            source_errors.append("provider credential is unavailable")
        if source.get("team_id_env") and not credentials.get("team_id"):
            source_errors.append("provider team credential is unavailable")
        if source_errors:
            errors.extend(f"{source.get('name', 'provider')}: {error}" for error in source_errors)
            continue

        sources_searched.append(source["name"])
        for query in queries:
            if request_count >= max_requests:
                break
            cache_key = (
                source["name"], source["endpoint"], source["region"], query.casefold()
            )
            cached = _CACHE.get(cache_key)
            if cached and time.monotonic() - cached[0] <= ttl:
                results = cached[1]
            else:
                results = adapter(query, source, credentials)
                _CACHE[cache_key] = (time.monotonic(), results)
                request_count += 1
            all_candidates.extend(results)

    seen: set[tuple[str, str]] = set()
    deduped = []
    for candidate in all_candidates:
        key = (candidate["source"], candidate["external_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    filtered = _filter_candidates(
        deduped,
        min_duration_s=float(discovery.get("min_duration_s", 0)),
        require_preview_url=bool(discovery.get("require_preview_url", False)),
    )
    return {
        "candidates": filtered,
        "queries": queries,
        "sources_searched": sources_searched,
        "total_found": len(deduped),
        "total_filtered": len(filtered),
        "request_count": request_count,
        "errors": errors,
    }
