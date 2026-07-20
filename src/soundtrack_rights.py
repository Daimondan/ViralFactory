"""Rights evidence and local soundtrack artifacts (VF-VS-511)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


RIGHTS_STATUSES = frozenset({"verified", "restricted", "unknown", "expired"})


class RightsValidationError(ValueError):
    """Raised when rights or acquired media fail closed."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_url(url: str) -> str:
    """Persist only a stable URL without credentials, query strings, or fragments."""
    if not url:
        return ""
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def validate_rights_record(record: dict) -> list[str]:
    """Return mechanical render-eligibility errors for a rights snapshot."""
    errors: list[str] = []
    required_text = (
        "candidate_id", "rights_source", "terms_url", "terms_retrieved_at",
        "terms_evidence_hash", "acquisition_method",
    )
    for field in required_text:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{field} is required")

    status = record.get("rights_status")
    if status not in RIGHTS_STATUSES:
        errors.append(f"rights_status must be one of {sorted(RIGHTS_STATUSES)}")
    elif status != "verified":
        errors.append(f"rights_status '{status}' is not render-eligible")

    evidence_hash = record.get("terms_evidence_hash", "")
    if not isinstance(evidence_hash, str) or len(evidence_hash) != 64:
        errors.append("terms_evidence_hash must be a SHA-256 hex digest")
    else:
        try:
            int(evidence_hash, 16)
        except ValueError:
            errors.append("terms_evidence_hash must be a SHA-256 hex digest")

    for field in (
        "commercial_use_allowed", "synchronization_allowed",
        "download_authorized",
    ):
        if record.get(field) is not True:
            errors.append(f"{field} must be evidence-backed true")

    for field in (
        "platform_constraints", "territory_constraints",
        "account_type_constraints",
    ):
        value = record.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            errors.append(f"{field} must be an array of non-empty strings")

    if not isinstance(record.get("attribution_required"), bool):
        errors.append("attribution_required must be boolean")
    elif record["attribution_required"] and not (
        isinstance(record.get("attribution_text"), str)
        and record["attribution_text"].strip()
    ):
        errors.append("attribution_text is required when attribution is required")

    expires_at = record.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                errors.append("rights evidence is expired")
        except ValueError:
            errors.append("expires_at must be an ISO timestamp or null")

    cost = record.get("cost_usd")
    if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
        errors.append("cost_usd must be a non-negative number")
    elif cost > 0 and not record.get("cost_approval_id"):
        errors.append("paid acquisition requires a fresh cost approval record")

    return errors


class SoundtrackRightsStore:
    """Append-only rights snapshots and immutable local artifacts."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS soundtrack_rights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        soundtrack_plan_id INTEGER NOT NULL,
        candidate_id TEXT NOT NULL,
        rights_version INTEGER NOT NULL,
        rights_json TEXT NOT NULL,
        rights_hash TEXT NOT NULL,
        terms_url TEXT NOT NULL,
        terms_evidence_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(soundtrack_plan_id, candidate_id, rights_version)
    );
    CREATE INDEX IF NOT EXISTS idx_soundtrack_rights_plan
        ON soundtrack_rights(soundtrack_plan_id, candidate_id, id);
    CREATE TABLE IF NOT EXISTS soundtrack_artifacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_id INTEGER NOT NULL,
        soundtrack_plan_id INTEGER NOT NULL,
        rights_record_id INTEGER NOT NULL,
        candidate_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        source_url TEXT NOT NULL,
        local_path TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        duration_seconds REAL NOT NULL,
        acquisition_method TEXT NOT NULL,
        acquired_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (rights_record_id) REFERENCES soundtrack_rights(id),
        UNIQUE(asset_id, content_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_soundtrack_artifacts_active
        ON soundtrack_artifacts(asset_id, active, id);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)

    def save_rights_record(
        self, asset_id: int, soundtrack_plan_id: int, record: dict
    ) -> dict:
        errors = validate_rights_record(record)
        if errors:
            raise RightsValidationError("; ".join(errors))
        safe = json.loads(json.dumps(record))
        safe["terms_url"] = sanitize_url(safe["terms_url"])
        canonical = json.dumps(safe, sort_keys=True, ensure_ascii=False)
        rights_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(self.SCHEMA)
            row = conn.execute(
                """SELECT COALESCE(MAX(rights_version), 0) AS version
                   FROM soundtrack_rights
                   WHERE soundtrack_plan_id = ? AND candidate_id = ?""",
                (soundtrack_plan_id, safe["candidate_id"]),
            ).fetchone()
            version = int(row["version"]) + 1
            cursor = conn.execute(
                """INSERT INTO soundtrack_rights
                   (asset_id, soundtrack_plan_id, candidate_id, rights_version,
                    rights_json, rights_hash, terms_url, terms_evidence_hash, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset_id, soundtrack_plan_id, safe["candidate_id"], version,
                    canonical, rights_hash, safe["terms_url"],
                    safe["terms_evidence_hash"], _now(),
                ),
            )
            return {
                "rights_record_id": int(cursor.lastrowid),
                "rights_version": version,
                "rights_hash": rights_hash,
            }

    def get_rights_record(self, rights_record_id: int) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(self.SCHEMA)
            row = conn.execute(
                "SELECT * FROM soundtrack_rights WHERE id = ?",
                (rights_record_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result.update(json.loads(result.pop("rights_json")))
        return result

    def get_active_artifact(self, asset_id: int) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(self.SCHEMA)
            row = conn.execute(
                """SELECT * FROM soundtrack_artifacts
                   WHERE asset_id = ? AND active = 1 ORDER BY id DESC LIMIT 1""",
                (asset_id,),
            ).fetchone()
        return dict(row) if row else None


def _probe_duration(path: str) -> float:
    try:
        with wave.open(path, "rb") as audio:
            return audio.getnframes() / float(audio.getframerate())
    except (wave.Error, EOFError):
        pass
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else 0.0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0.0


def acquire_rights_valid_track(
    db_path: str,
    asset_id: int,
    soundtrack_plan_id: int,
    rights_record_id: int,
    candidate: dict,
    media_root: str,
    downloader,
) -> dict:
    """Acquire, validate, hash, and atomically activate one exact recording."""
    store = SoundtrackRightsStore(db_path)
    rights = store.get_rights_record(rights_record_id)
    if not rights:
        raise RightsValidationError("rights record not found")
    if int(rights["asset_id"]) != int(asset_id):
        raise RightsValidationError("rights record does not belong to this asset")
    if int(rights["soundtrack_plan_id"]) != int(soundtrack_plan_id):
        raise RightsValidationError("rights record does not belong to this soundtrack plan")
    errors = validate_rights_record(rights)
    if errors:
        raise RightsValidationError("; ".join(errors))
    if candidate.get("candidate_id") != rights["candidate_id"]:
        raise RightsValidationError("candidate does not match the rights snapshot")
    source_url = candidate.get("download_url") or ""
    if not source_url:
        raise RightsValidationError("candidate has no authorized download URL")

    asset_dir = Path(media_root) / str(asset_id) / "soundtracks"
    asset_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(urlsplit(source_url).path).suffix or ".audio"
    fd, temp_path = tempfile.mkstemp(prefix="acquire-", suffix=suffix, dir=asset_dir)
    os.close(fd)
    try:
        downloader(source_url, temp_path)
        byte_size = os.path.getsize(temp_path) if os.path.exists(temp_path) else 0
        if byte_size <= 0:
            raise RightsValidationError("acquisition produced an empty local file")
        duration = _probe_duration(temp_path)
        if duration <= 0:
            raise RightsValidationError("acquired local file has no measurable duration")
        content_hash = hashlib.sha256(Path(temp_path).read_bytes()).hexdigest()
        final_path = asset_dir / f"{content_hash}{suffix}"
        os.replace(temp_path, final_path)
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(store.SCHEMA)
            existing = conn.execute(
                """SELECT * FROM soundtrack_artifacts
                   WHERE asset_id = ? AND content_hash = ?""",
                (asset_id, content_hash),
            ).fetchone()
            if existing:
                artifact_id = int(existing["id"])
            else:
                cursor = conn.execute(
                    """INSERT INTO soundtrack_artifacts
                       (asset_id, soundtrack_plan_id, rights_record_id, candidate_id,
                        provider, source_url, local_path, content_hash, byte_size,
                        duration_seconds, acquisition_method, acquired_at, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (
                        asset_id, soundtrack_plan_id, rights_record_id,
                        rights["candidate_id"], str(candidate.get("provider") or ""),
                        sanitize_url(source_url), str(final_path), content_hash,
                        byte_size, duration, rights["acquisition_method"], _now(),
                    ),
                )
                artifact_id = int(cursor.lastrowid)
            conn.execute(
                "UPDATE soundtrack_artifacts SET active = 0 WHERE asset_id = ?",
                (asset_id,),
            )
            conn.execute(
                "UPDATE soundtrack_artifacts SET active = 1 WHERE id = ?",
                (artifact_id,),
            )
        return {
            "status": "render_ready",
            "artifact_id": artifact_id,
            "local_path": str(final_path),
            "content_hash": content_hash,
            "byte_size": byte_size,
            "duration_seconds": duration,
            "rights_record_id": rights_record_id,
        }
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
