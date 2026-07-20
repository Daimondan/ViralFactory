"""VF-INSP-001 — Inspiration evidence contracts (AMENDMENT-012).

Provider evidence contracts for the Inspiration workbench. This module defines
the normalized shape of collection runs, trend items, and append-only
observations, plus the redaction rules that keep secrets out of the DB.

Mechanical only. No LLM judgment, no keyword heuristics, no trend/momentum
inference. The first slice is read-only and cannot feed ideation, modules,
or production.

Contracts follow AMENDMENT-012 C2:
  - Collection run  — provider, endpoint, platform, region, params, times,
    status, result count, response hash, adapter/config version, redacted error.
  - Trend item      — stable provider-native identity, platform/content type,
    canonical URL, creator/title/description, safe preview/thumbnail,
    availability, first/last seen.
  - Observation     — collection-run link, item link, collected time, rank,
    exact metric names/values, provider evidence label, immutable safe-payload hash.

Observations are append-only. Item metadata may gain a new version; history is
not overwritten. Signed URLs, credentials, and secret-bearing raw payload
fields are stripped before persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit

# ─── Adapter/config version (recorded on every collection run) ───────────────
ADAPTER_VERSION = "inspiration-v1"

# ─── Evidence labels (truthful naming per AMENDMENT-012) ─────────────────────
# An endpoint meaning maps to the only label a card/section may use.
ENDPOINT_MEANING_TO_LABEL: dict[str, str] = {
    "chart": "chart",                  # may say "Trending audio"
    "recommendation": "recommendation",  # "Video inspiration" / "Provider recommendations"
    "seed": "seed",
    "regional_discovery": "regional_discovery",
}

# Section headings in the UI (config-driven, not hardcoded in templates).
SECTION_LABELS: dict[str, str] = {
    "chart": "Trending audio",
    "recommendation": "Video inspiration",
    "seed": "Provider recommendations",
    "regional_discovery": "Regional discovery",
}


class InspirationContractError(ValueError):
    """Raised when a contract field is missing, malformed, or violates C2/C3."""


# ─── Redaction ──────────────────────────────────────────────────────────────

def redact_url(url: str, secret_params: Iterable[str]) -> str:
    """Strip secret-bearing query parameters from a URL.

    Returns the URL with secret params removed. If the URL itself is empty,
    returns an empty string. Never raises on malformed input — returns the
    original string if parsing fails, so a malformed provider URL does not
    crash collection.
    """
    if not url or not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    secret = {p.casefold() for p in secret_params}
    if not parts.query:
        return url
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.casefold() not in secret]
    new_query = urlencode(kept)
    return parts._replace(query=new_query).geturl()


def redact_payload(payload: dict, secret_fields: Iterable[str]) -> dict:
    """Remove secret-bearing top-level keys from a dict payload.

    Recurses one level into nested dicts and lists of dicts so that a provider
    response like {"data": {"access_token": "..."}} is cleaned. Does NOT
    attempt to interpret nested structure beyond a shallow scan — provider
    adapters normalize first, then redaction runs on the normalized dict.
    """
    if not isinstance(payload, dict):
        return {}
    secret = {f.casefold() for f in secret_fields}
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key.casefold() in secret:
            continue
        if isinstance(value, dict):
            cleaned[key] = redact_payload(value, secret_fields)
        elif isinstance(value, list):
            cleaned[key] = [
                redact_payload(item, secret_fields) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


def redact_url_fields(payload: dict, url_fields: Iterable[str], secret_params: Iterable[str]) -> dict:
    """Sanitize any field whose value is a URL that may carry signed params."""
    if not isinstance(payload, dict):
        return {}
    fields = {f.casefold() for f in url_fields}
    cleaned = dict(payload)
    for key, value in list(cleaned.items()):
        if key.casefold() in fields and isinstance(value, str) and value:
            cleaned[key] = redact_url(value, secret_params)
        elif isinstance(value, dict):
            cleaned[key] = redact_url_fields(value, url_fields, secret_params)
        elif isinstance(value, list):
            cleaned[key] = [
                redact_url_fields(item, url_fields, secret_params) if isinstance(item, dict) else item
                for item in value
            ]
    return cleaned


def apply_redaction(payload: dict, redaction_config: dict) -> dict:
    """Full redaction pipeline: strip secret fields, then sanitize URL fields."""
    if not isinstance(payload, dict):
        return {}
    secret_fields = redaction_config.get("payload_field_names") or []
    url_fields = redaction_config.get("url_fields") or []
    secret_params = redaction_config.get("url_param_names") or []
    cleaned = redact_payload(payload, secret_fields)
    cleaned = redact_url_fields(cleaned, url_fields, secret_params)
    return cleaned


# ─── Safe payload hash ───────────────────────────────────────────────────────

def compute_safe_payload_hash(payload: dict) -> str:
    """SHA-256 of the redacted normalized payload, sorted keys, no whitespace.

    This hash is immutable evidence of what was observed, independent of any
    secret that was stripped. Two runs that observe the same redacted content
    produce the same hash.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ─── Collection run contract ─────────────────────────────────────────────────

COLLECTION_RUN_REQUIRED = (
    "business_slug", "provider", "endpoint_key", "platform", "region",
    "status", "adapter_version", "started_at", "ended_at",
)
COLLECTION_RUN_STATUS_OK = "ok"
COLLECTION_RUN_STATUS_EMPTY = "empty"
COLLECTION_RUN_STATUS_PARTIAL = "partial"
COLLECTION_RUN_STATUS_ERROR = "error"
COLLECTION_RUN_STATUS_RATE_LIMITED = "rate_limited"
COLLECTION_RUN_STATUS_AUTH_FAILED = "auth_failed"
COLLECTION_RUN_VALID_STATUSES = {
    COLLECTION_RUN_STATUS_OK, COLLECTION_RUN_STATUS_EMPTY,
    COLLECTION_RUN_STATUS_PARTIAL, COLLECTION_RUN_STATUS_ERROR,
    COLLECTION_RUN_STATUS_RATE_LIMITED, COLLECTION_RUN_STATUS_AUTH_FAILED,
}


def validate_collection_run(run: dict) -> list[str]:
    """Return a list of error strings; empty list means valid."""
    errors: list[str] = []
    if not isinstance(run, dict):
        return ["collection run must be a dict"]
    for field in COLLECTION_RUN_REQUIRED:
        if field not in run:
            errors.append(f"collection run missing required field: {field}")
        elif isinstance(run[field], str) and not run[field].strip():
            errors.append(f"collection run field is empty: {field}")
    status = run.get("status")
    if status and status not in COLLECTION_RUN_VALID_STATUSES:
        errors.append(f"collection run has invalid status: {status}")
    # result_count is optional but must be a non-negative int if present
    rc = run.get("result_count")
    if rc is not None and (not isinstance(rc, int) or rc < 0):
        errors.append("collection run result_count must be a non-negative integer")
    # response_hash optional; if present must be a hex string
    rh = run.get("response_hash")
    if rh is not None and not re.fullmatch(r"[0-9a-f]*", str(rh)):
        errors.append("collection run response_hash must be a hex string")
    return errors


def make_collection_run(
    *,
    business_slug: str,
    provider: str,
    endpoint_key: str,
    platform: str,
    region: str,
    status: str,
    started_at: str,
    ended_at: str,
    request_params: dict | None = None,
    result_count: int = 0,
    response_hash: str = "",
    adapter_version: str = ADAPTER_VERSION,
    error_class: str = "",
    error_message: str = "",
) -> dict:
    """Construct a validated collection run dict.

    `request_params` is the sanitized request parameters (no secrets).
    `error_class`/`error_message` are redacted diagnostics for failure runs.
    """
    run = {
        "business_slug": business_slug,
        "provider": provider,
        "endpoint_key": endpoint_key,
        "platform": platform,
        "region": region,
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "request_params": request_params or {},
        "result_count": int(result_count),
        "response_hash": response_hash,
        "adapter_version": adapter_version,
        "error_class": error_class,
        "error_message": error_message,
    }
    errors = validate_collection_run(run)
    if errors:
        raise InspirationContractError("; ".join(errors))
    return run


# ─── Trend item contract ─────────────────────────────────────────────────────

TREND_ITEM_REQUIRED = (
    "business_slug", "provider", "platform", "content_type",
    "native_id", "canonical_url",
)
CONTENT_TYPES = {"audio", "video"}


def validate_trend_item(item: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(item, dict):
        return ["trend item must be a dict"]
    for field in TREND_ITEM_REQUIRED:
        if field not in item:
            errors.append(f"trend item missing required field: {field}")
    if item.get("content_type") and item["content_type"] not in CONTENT_TYPES:
        errors.append(f"trend item content_type must be one of {CONTENT_TYPES}")
    # native_id must be a non-empty string (provider-native identity)
    nid = item.get("native_id")
    if nid is not None and (not isinstance(nid, str) or not nid.strip()):
        errors.append("trend item native_id must be a non-empty string")
    return errors


def make_trend_item(
    *,
    business_slug: str,
    provider: str,
    platform: str,
    content_type: str,
    native_id: str,
    canonical_url: str = "",
    title: str = "",
    creator: str = "",
    description: str = "",
    preview_url: str = "",
    thumbnail_url: str = "",
    availability: str = "unknown",
) -> dict:
    item = {
        "business_slug": business_slug,
        "provider": provider,
        "platform": platform,
        "content_type": content_type,
        "native_id": native_id,
        "canonical_url": canonical_url,
        "title": title,
        "creator": creator,
        "description": description,
        "preview_url": preview_url,
        "thumbnail_url": thumbnail_url,
        "availability": availability,
    }
    errors = validate_trend_item(item)
    if errors:
        raise InspirationContractError("; ".join(errors))
    return item


# ─── Observation contract ────────────────────────────────────────────────────

OBSERVATION_REQUIRED = (
    "collection_run_id", "trend_item_id", "collected_at",
    "evidence_label", "safe_payload_hash",
)
EVIDENCE_LABELS = set(ENDPOINT_MEANING_TO_LABEL.values())


def validate_observation(obs: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(obs, dict):
        return ["observation must be a dict"]
    for field in OBSERVATION_REQUIRED:
        if field not in obs:
            errors.append(f"observation missing required field: {field}")
    label = obs.get("evidence_label")
    if label and label not in EVIDENCE_LABELS:
        errors.append(f"observation evidence_label must be one of {EVIDENCE_LABELS}")
    # rank optional; if present must be int >= 1 (rank 1 = top)
    rank = obs.get("rank")
    if rank is not None and (not isinstance(rank, int) or rank < 1):
        errors.append("observation rank must be a positive integer")
    # metrics optional; if present must be a dict of {name: {value, ...}}
    metrics = obs.get("metrics")
    if metrics is not None and not isinstance(metrics, dict):
        errors.append("observation metrics must be a dict")
    # safe_payload_hash must be 64-char hex
    sph = obs.get("safe_payload_hash")
    if sph and not re.fullmatch(r"[0-9a-f]{64}", str(sph)):
        errors.append("observation safe_payload_hash must be a 64-char SHA-256 hex")
    return errors


def make_observation(
    *,
    collection_run_id: int,
    trend_item_id: int,
    collected_at: str,
    evidence_label: str,
    safe_payload_hash: str,
    rank: int | None = None,
    metrics: dict | None = None,
    availability: str = "unknown",
) -> dict:
    obs = {
        "collection_run_id": collection_run_id,
        "trend_item_id": trend_item_id,
        "collected_at": collected_at,
        "rank": rank,
        "metrics": metrics or {},
        "evidence_label": evidence_label,
        "safe_payload_hash": safe_payload_hash,
        "availability": availability,
    }
    errors = validate_observation(obs)
    if errors:
        raise InspirationContractError("; ".join(errors))
    return obs


# ─── Metric normalization (mechanical, no inference) ───────────────────────

def normalize_metric(name: str, value, *, unit: str = "") -> dict:
    """A single observation metric preserves exact provider name, value, unit.

    Missing values are stored as None (unavailable), never coerced to zero.
    The metric name is preserved verbatim from the provider (e.g.
    "usage_count", "views", "likes") — not renamed or scored.
    """
    if not name:
        raise InspirationContractError("metric name is required")
    normalized = value
    if isinstance(normalized, str) and normalized.isdigit():
        normalized = int(normalized)
    elif isinstance(normalized, str) and normalized.replace(".", "", 1).isdigit():
        normalized = float(normalized)
    return {
        "name": str(name),
        "value": normalized if normalized is not None else None,
        "unit": str(unit),
    }


# ─── Time helpers ────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_stale(collected_at: str, stale_after_seconds: int) -> bool:
    """True if the collected_at timestamp is older than stale_after_seconds."""
    if not collected_at:
        return True
    try:
        ts = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return True
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    return age > stale_after_seconds