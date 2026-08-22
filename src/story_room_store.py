"""Append-only, tenant-scoped storage for the Story Room experiment."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from .db import connect
except ImportError:
    from db import connect


class StoryRoomError(Exception):
    """Base Story Room storage error."""


class StoryRoomScopeError(StoryRoomError):
    """Raised when a record belongs to another tenant."""


class StoryRoomConflictError(StoryRoomError):
    """Raised when an idempotency key is reused for different data."""


class StoryRoomNotFoundError(StoryRoomError):
    """Raised when a tenant-scoped Story Room record does not exist."""


_EVENT_ACTORS = {"operator", "ai", "system", "tool"}
_EVENT_TYPES = {"message", "attachment", "research_result", "tool_result", "decision", "failure"}
_UNDERSTANDING_KINDS = {"known", "assumed", "missing", "locked"}
_ARTIFACT_STATUSES = {"working", "ready_for_review", "locked", "rejected", "stale"}
_DECISION_ACTIONS = {"lock", "reject", "supersede"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class StoryRoomStore:
    """Owns the additive Story Room tables and their append-only writes."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        conn = connect(self.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS stories (
                    story_id TEXT PRIMARY KEY,
                    business_slug TEXT NOT NULL,
                    title TEXT NOT NULL,
                    active_stage TEXT NOT NULL DEFAULT 'brief',
                    status TEXT NOT NULL DEFAULT 'active',
                    current_artifact_refs_json TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (business_slug, idempotency_key)
                );
                CREATE INDEX IF NOT EXISTS idx_stories_tenant
                    ON stories (business_slug, updated_at DESC);

                CREATE TABLE IF NOT EXISTS story_events (
                    event_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    actor TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (business_slug, story_id, sequence_number),
                    UNIQUE (business_slug, story_id, idempotency_key),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );
                CREATE INDEX IF NOT EXISTS idx_story_events_order
                    ON story_events (business_slug, story_id, sequence_number);

                CREATE TABLE IF NOT EXISTS story_contributions (
                    contribution_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    contribution_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL DEFAULT '[]',
                    content_hash TEXT NOT NULL,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (business_slug, story_id, idempotency_key),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );
                CREATE INDEX IF NOT EXISTS idx_story_contributions_story
                    ON story_contributions (business_slug, story_id, created_at);

                CREATE TABLE IF NOT EXISTS story_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    current_version_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (business_slug, story_id, artifact_type),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );

                CREATE TABLE IF NOT EXISTS story_artifact_versions (
                    artifact_version_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    based_on_json TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'working',
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (artifact_id, version),
                    UNIQUE (business_slug, story_id, artifact_id, idempotency_key),
                    FOREIGN KEY (artifact_id) REFERENCES story_artifacts(artifact_id),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );
                CREATE INDEX IF NOT EXISTS idx_story_artifact_versions_lineage
                    ON story_artifact_versions (business_slug, story_id, artifact_id, version);

                CREATE TABLE IF NOT EXISTS story_artifact_decisions (
                    decision_id TEXT PRIMARY KEY,
                    artifact_version_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    action TEXT NOT NULL,
                    bound_content_hash TEXT NOT NULL,
                    feedback TEXT,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (business_slug, story_id, artifact_version_id, idempotency_key),
                    FOREIGN KEY (artifact_version_id) REFERENCES story_artifact_versions(artifact_version_id),
                    FOREIGN KEY (artifact_id) REFERENCES story_artifacts(artifact_id),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );

                CREATE TABLE IF NOT EXISTS story_understanding_entries (
                    entry_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    statement TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL,
                    supersedes_entry_id TEXT,
                    current INTEGER NOT NULL DEFAULT 1,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE (business_slug, story_id, idempotency_key),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id),
                    FOREIGN KEY (supersedes_entry_id) REFERENCES story_understanding_entries(entry_id)
                );
                CREATE INDEX IF NOT EXISTS idx_story_understanding_current
                    ON story_understanding_entries (business_slug, story_id, current);

                CREATE TABLE IF NOT EXISTS story_tool_runs (
                    tool_run_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    tool_type TEXT NOT NULL,
                    input_refs_json TEXT NOT NULL DEFAULT '{}',
                    output_refs_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL,
                    error_json TEXT,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    UNIQUE (business_slug, story_id, idempotency_key),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );
                CREATE INDEX IF NOT EXISTS idx_story_tool_runs_story
                    ON story_tool_runs (business_slug, story_id, created_at);
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise StoryRoomNotFoundError("Expected Story Room row was not found")
        return dict(row)

    def table_names(self) -> set[str]:
        conn = connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND (name = 'stories' OR name LIKE 'story_%')"
            ).fetchall()
            return {row["name"] for row in rows}
        finally:
            conn.close()

    def _story(self, conn: sqlite3.Connection, business_slug: str, story_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM stories WHERE story_id = ?", (story_id,)).fetchone()
        if row is None:
            raise StoryRoomNotFoundError(f"Story '{story_id}' not found")
        if row["business_slug"] != business_slug:
            raise StoryRoomScopeError(f"Story '{story_id}' belongs to another tenant")
        return row

    def _existing_idempotent(
        self,
        conn: sqlite3.Connection,
        table: str,
        business_slug: str,
        story_id: str,
        idempotency_key: str | None,
    ) -> sqlite3.Row | None:
        if not idempotency_key:
            return None
        return conn.execute(
            f"SELECT * FROM {table} WHERE business_slug = ? AND story_id = ? AND idempotency_key = ?",
            (business_slug, story_id, idempotency_key),
        ).fetchone()

    def create_story(
        self,
        business_slug: str,
        title: str,
        active_stage: str = "brief",
        status: str = "active",
        current_artifact_refs: dict[str, Any] | None = None,
        story_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        refs = current_artifact_refs or {}
        conn = connect(self.db_path)
        try:
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM stories WHERE business_slug = ? AND idempotency_key = ?",
                    (business_slug, idempotency_key),
                ).fetchone()
                if existing:
                    if existing["title"] != title or existing["active_stage"] != active_stage:
                        raise StoryRoomConflictError("idempotency key reused for different story")
                    return self._row(existing)
            story_id = story_id or _new_id("story")
            existing = conn.execute("SELECT * FROM stories WHERE story_id = ?", (story_id,)).fetchone()
            if existing:
                if existing["business_slug"] != business_slug:
                    raise StoryRoomScopeError(f"Story '{story_id}' belongs to another tenant")
                return self._row(existing)
            now = _now()
            conn.execute(
                """INSERT INTO stories
                   (story_id, business_slug, title, active_stage, status,
                    current_artifact_refs_json, idempotency_key, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (story_id, business_slug, title, active_stage, status, _canonical_json(refs), idempotency_key, now, now),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM stories WHERE story_id = ?", (story_id,)).fetchone())
        finally:
            conn.close()

    def get_story(self, business_slug: str, story_id: str) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            return self._row(self._story(conn, business_slug, story_id))
        finally:
            conn.close()

    def append_event(
        self,
        business_slug: str,
        story_id: str,
        actor: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        if actor not in _EVENT_ACTORS:
            raise ValueError(f"Unsupported Story Room event actor: {actor}")
        if event_type not in _EVENT_TYPES:
            raise ValueError(f"Unsupported Story Room event type: {event_type}")
        payload_json = _canonical_json(payload)
        payload_hash = _content_hash(payload)
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            existing = self._existing_idempotent(conn, "story_events", business_slug, story_id, idempotency_key)
            if existing:
                if existing["content_hash"] != payload_hash or existing["actor"] != actor or existing["event_type"] != event_type:
                    raise StoryRoomConflictError("event idempotency key reused for different event")
                return self._row(existing)
            conn.execute("BEGIN IMMEDIATE")
            sequence = conn.execute(
                "SELECT COALESCE(MAX(sequence_number), 0) + 1 AS next_sequence FROM story_events WHERE story_id = ?",
                (story_id,),
            ).fetchone()["next_sequence"]
            event_id = _new_id("event")
            conn.execute(
                """INSERT INTO story_events
                   (event_id, story_id, business_slug, sequence_number, actor, event_type,
                    payload_json, content_hash, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, story_id, business_slug, sequence, actor, event_type, payload_json,
                 payload_hash, idempotency_key, created_at or _now()),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_events WHERE event_id = ?", (event_id,)).fetchone())
        finally:
            conn.close()

    def list_events(self, business_slug: str, story_id: str) -> list[dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            return [self._row(row) for row in conn.execute(
                "SELECT * FROM story_events WHERE business_slug = ? AND story_id = ? ORDER BY sequence_number",
                (business_slug, story_id),
            )]
        finally:
            conn.close()

    def add_contribution(
        self,
        business_slug: str,
        story_id: str,
        contribution_type: str,
        payload: dict[str, Any],
        source_refs: list[str] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        refs = source_refs or []
        payload_hash = _content_hash({"type": contribution_type, "payload": payload, "source_refs": refs})
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            existing = self._existing_idempotent(conn, "story_contributions", business_slug, story_id, idempotency_key)
            if existing:
                if existing["content_hash"] != payload_hash:
                    raise StoryRoomConflictError("contribution idempotency key reused for different contribution")
                return self._row(existing)
            contribution_id = _new_id("contribution")
            conn.execute(
                """INSERT INTO story_contributions
                   (contribution_id, story_id, business_slug, contribution_type, payload_json,
                    source_refs_json, content_hash, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (contribution_id, story_id, business_slug, contribution_type, _canonical_json(payload),
                 _canonical_json(refs), payload_hash, idempotency_key, _now()),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_contributions WHERE contribution_id = ?", (contribution_id,)).fetchone())
        finally:
            conn.close()

    def create_artifact(
        self, business_slug: str, story_id: str, artifact_type: str, artifact_id: str | None = None
    ) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            existing = conn.execute(
                "SELECT * FROM story_artifacts WHERE business_slug = ? AND story_id = ? AND artifact_type = ?",
                (business_slug, story_id, artifact_type),
            ).fetchone()
            if existing:
                return self._row(existing)
            artifact_id = artifact_id or _new_id("artifact")
            conn.execute(
                "INSERT INTO story_artifacts (artifact_id, story_id, business_slug, artifact_type, created_at) VALUES (?, ?, ?, ?, ?)",
                (artifact_id, story_id, business_slug, artifact_type, _now()),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone())
        finally:
            conn.close()

    def create_artifact_version(
        self,
        business_slug: str,
        story_id: str,
        artifact_id: str,
        content: dict[str, Any],
        idempotency_key: str | None = None,
        based_on: list[str] | None = None,
        status: str = "working",
        expected_current_version_id: str | None = None,
    ) -> dict[str, Any]:
        if status not in _ARTIFACT_STATUSES:
            raise ValueError(f"Unsupported artifact status: {status}")
        based_on = based_on or []
        content_hash = _content_hash(content)
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            artifact = conn.execute(
                "SELECT * FROM story_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
            if artifact is None:
                raise StoryRoomNotFoundError(f"Artifact '{artifact_id}' not found")
            if artifact["business_slug"] != business_slug or artifact["story_id"] != story_id:
                raise StoryRoomScopeError(f"Artifact '{artifact_id}' belongs to another scope")
            existing = self._existing_idempotent(conn, "story_artifact_versions", business_slug, story_id, idempotency_key)
            if existing:
                if existing["content_hash"] != content_hash:
                    raise StoryRoomConflictError("artifact version idempotency key reused for different content")
                return self._row(existing)
            conn.execute("BEGIN IMMEDIATE")
            artifact = conn.execute(
                "SELECT current_version_id FROM story_artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
            if expected_current_version_id is not None and artifact["current_version_id"] != expected_current_version_id:
                raise StoryRoomConflictError("Artifact current version changed during compare-and-set")
            version = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM story_artifact_versions WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()["next_version"]
            version_id = _new_id("artifact_version")
            conn.execute(
                """INSERT INTO story_artifact_versions
                   (artifact_version_id, artifact_id, story_id, business_slug, version,
                    content_json, content_hash, based_on_json, status, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (version_id, artifact_id, story_id, business_slug, version, _canonical_json(content),
                 content_hash, _canonical_json(based_on), status, idempotency_key, _now()),
            )
            conn.execute(
                "UPDATE story_artifacts SET current_version_id = ? WHERE artifact_id = ?",
                (version_id, artifact_id),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_artifact_versions WHERE artifact_version_id = ?", (version_id,)).fetchone())
        finally:
            conn.close()

    def get_artifact_version(self, business_slug: str, artifact_version_id: str) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT * FROM story_artifact_versions WHERE artifact_version_id = ?", (artifact_version_id,)
            ).fetchone()
            if row is None:
                raise StoryRoomNotFoundError(f"Artifact version '{artifact_version_id}' not found")
            if row["business_slug"] != business_slug:
                raise StoryRoomScopeError(f"Artifact version '{artifact_version_id}' belongs to another tenant")
            return self._row(row)
        finally:
            conn.close()

    def record_artifact_decision(
        self,
        business_slug: str,
        story_id: str,
        artifact_version_id: str,
        action: str,
        idempotency_key: str | None = None,
        feedback: str | None = None,
    ) -> dict[str, Any]:
        if action not in _DECISION_ACTIONS:
            raise ValueError(f"Unsupported artifact decision: {action}")
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            version = conn.execute(
                "SELECT * FROM story_artifact_versions WHERE artifact_version_id = ?", (artifact_version_id,)
            ).fetchone()
            if version is None:
                raise StoryRoomNotFoundError(f"Artifact version '{artifact_version_id}' not found")
            if version["business_slug"] != business_slug or version["story_id"] != story_id:
                raise StoryRoomScopeError(f"Artifact version '{artifact_version_id}' belongs to another scope")
            existing = self._existing_idempotent(conn, "story_artifact_decisions", business_slug, story_id, idempotency_key)
            if existing:
                if existing["bound_content_hash"] != version["content_hash"] or existing["action"] != action:
                    raise StoryRoomConflictError("decision idempotency key reused for a different decision")
                return self._row(existing)
            decision_id = _new_id("decision")
            conn.execute(
                """INSERT INTO story_artifact_decisions
                   (decision_id, artifact_version_id, artifact_id, story_id, business_slug,
                    action, bound_content_hash, feedback, idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (decision_id, artifact_version_id, version["artifact_id"], story_id, business_slug,
                 action, version["content_hash"], feedback, idempotency_key, _now()),
            )
            new_status = {"lock": "locked", "reject": "rejected", "supersede": "stale"}[action]
            conn.execute(
                "UPDATE story_artifact_versions SET status = ? WHERE artifact_version_id = ?",
                (new_status, artifact_version_id),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_artifact_decisions WHERE decision_id = ?", (decision_id,)).fetchone())
        finally:
            conn.close()

    def add_understanding(
        self,
        business_slug: str,
        story_id: str,
        kind: str,
        statement: str,
        scope: str,
        evidence_refs: list[str],
        created_by: str,
        idempotency_key: str,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        if kind not in _UNDERSTANDING_KINDS:
            raise ValueError(f"Unsupported understanding kind: {kind}")
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            existing = self._existing_idempotent(conn, "story_understanding_entries", business_slug, story_id, idempotency_key)
            if existing:
                if existing["statement"] != statement or existing["kind"] != kind:
                    raise StoryRoomConflictError("understanding idempotency key reused for different entry")
                return self._row(existing)
            if supersedes:
                prior = conn.execute(
                    "SELECT * FROM story_understanding_entries WHERE entry_id = ?", (supersedes,)
                ).fetchone()
                if prior is None:
                    raise StoryRoomNotFoundError(f"Understanding entry '{supersedes}' not found")
                if prior["business_slug"] != business_slug or prior["story_id"] != story_id:
                    raise StoryRoomScopeError(f"Understanding entry '{supersedes}' belongs to another scope")
                conn.execute("UPDATE story_understanding_entries SET current = 0 WHERE entry_id = ?", (supersedes,))
            entry_id = _new_id("understanding")
            conn.execute(
                """INSERT INTO story_understanding_entries
                   (entry_id, story_id, business_slug, kind, statement, scope,
                    evidence_refs_json, created_by, supersedes_entry_id, current,
                    idempotency_key, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
                (entry_id, story_id, business_slug, kind, statement, scope,
                 _canonical_json(evidence_refs), created_by, supersedes, idempotency_key, _now()),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_understanding_entries WHERE entry_id = ?", (entry_id,)).fetchone())
        finally:
            conn.close()

    def list_understanding(self, business_slug: str, story_id: str, current_only: bool = True) -> list[dict[str, Any]]:
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            sql = "SELECT * FROM story_understanding_entries WHERE business_slug = ? AND story_id = ?"
            args: list[Any] = [business_slug, story_id]
            if current_only:
                sql += " AND current = 1"
            sql += " ORDER BY created_at, entry_id"
            return [self._row(row) for row in conn.execute(sql, args)]
        finally:
            conn.close()

    def record_tool_run(
        self,
        business_slug: str,
        story_id: str,
        tool_type: str,
        input_refs: dict[str, Any],
        output_refs: dict[str, Any] | None = None,
        status: str = "started",
        error: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        attempt: int = 1,
    ) -> dict[str, Any]:
        conn = connect(self.db_path)
        try:
            self._story(conn, business_slug, story_id)
            existing = self._existing_idempotent(conn, "story_tool_runs", business_slug, story_id, idempotency_key)
            if existing:
                if existing["input_refs_json"] != _canonical_json(input_refs):
                    raise StoryRoomConflictError("tool idempotency key reused for different input")
                return self._row(existing)
            run_id = _new_id("tool_run")
            completed_at = _now() if status in {"succeeded", "failed", "cancelled"} else None
            conn.execute(
                """INSERT INTO story_tool_runs
                   (tool_run_id, story_id, business_slug, tool_type, input_refs_json,
                    output_refs_json, status, error_json, attempt, idempotency_key,
                    created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, story_id, business_slug, tool_type, _canonical_json(input_refs),
                 _canonical_json(output_refs or {}), status, _canonical_json(error) if error else None,
                 attempt, idempotency_key, _now(), completed_at),
            )
            conn.commit()
            return self._row(conn.execute("SELECT * FROM story_tool_runs WHERE tool_run_id = ?", (run_id,)).fetchone())
        finally:
            conn.close()
