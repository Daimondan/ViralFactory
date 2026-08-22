"""Strict Story Room artifact contracts, locks, dependency staleness, and edits."""

from __future__ import annotations

import difflib
import json
from typing import Any

try:
    from .db import connect
    from .story_room_store import (
        StoryRoomConflictError,
        StoryRoomNotFoundError,
        StoryRoomScopeError,
        StoryRoomStore,
        _canonical_json,
    )
except ImportError:
    from db import connect
    from story_room_store import (
        StoryRoomConflictError,
        StoryRoomNotFoundError,
        StoryRoomScopeError,
        StoryRoomStore,
        _canonical_json,
    )


class StoryRoomArtifactValidationError(ValueError):
    """Raised when an artifact payload violates its strict contract."""


# These are generic machine contracts from AMENDMENT-020, not tenant content.
_ARTIFACT_CONTRACTS: dict[str, dict[str, type]] = {
    "creative_brief": {
        "purpose": str,
        "human_stake": str,
        "audience": str,
        "desired_effect": str,
        "available_evidence": list,
        "evidence_gaps": list,
        "red_lines": list,
        "distribution_intent": str,
        "understanding_snapshot": list,
    },
    "idea_map": {
        "core_claim": str,
        "editorial_fit": dict,
        "tension": str,
        "human_stake": str,
        "evidence_refs": list,
        "audience_promise": str,
        "emotional_job": str,
        "rejected_directions": list,
    },
    "story_map": {
        "point_of_view": str,
        "frame": str,
        "narrative_movement": list,
        "hook_direction": str,
        "ending": str,
        "format_ref": str,
        "platforms": list,
        "production_binding": dict,
        "visual_treatment_ref": dict,
        "capture_policy": dict,
        "style_for_this_piece": list,
        "red_lines": list,
    },
    "exact_copy": {
        "primary_text": str,
        "spoken_text": str,
        "on_screen_text": list,
        "platform_variants": list,
        "post_caption": dict,
        "title": str,
        "evidence_notes": list,
        "self_audit": dict,
        "direct_edit_events": list,
    },
    "asset_plan": {
        "format": str,
        "platform": str,
        "spoken_beats": list,
        "visual_roles": list,
        "soundtrack": dict,
        "caption_roles": list,
        "production_notes": list,
    },
}


class StoryRoomArtifactService:
    """Compile and govern immutable human-readable Story Room artifacts."""

    def __init__(self, store: StoryRoomStore):
        self.store = store
        self._init_extensions()

    def _init_extensions(self) -> None:
        conn = connect(self.store.db_path)
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS story_artifact_revision_meta (
                    artifact_version_id TEXT PRIMARY KEY,
                    revision_kind TEXT NOT NULL DEFAULT 'ai',
                    author TEXT NOT NULL DEFAULT 'system',
                    diff_text TEXT,
                    FOREIGN KEY (artifact_version_id) REFERENCES story_artifact_versions(artifact_version_id)
                );
                CREATE TABLE IF NOT EXISTS story_artifact_dependencies (
                    dependency_id TEXT PRIMARY KEY,
                    story_id TEXT NOT NULL,
                    business_slug TEXT NOT NULL,
                    upstream_artifact_id TEXT NOT NULL,
                    upstream_version_id TEXT NOT NULL,
                    downstream_artifact_id TEXT NOT NULL,
                    downstream_version_id TEXT NOT NULL,
                    relation TEXT NOT NULL DEFAULT 'based_on',
                    created_at TEXT NOT NULL,
                    UNIQUE (upstream_version_id, downstream_version_id),
                    FOREIGN KEY (story_id) REFERENCES stories(story_id)
                );
                CREATE INDEX IF NOT EXISTS idx_story_artifact_dependencies_upstream
                    ON story_artifact_dependencies (business_slug, story_id, upstream_version_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _validate(artifact_type: str, payload: dict[str, Any]) -> None:
        contract = _ARTIFACT_CONTRACTS.get(artifact_type)
        if contract is None:
            raise StoryRoomArtifactValidationError(f"Unknown artifact type: {artifact_type}")
        if not isinstance(payload, dict):
            raise StoryRoomArtifactValidationError(f"{artifact_type} payload must be a mapping")
        missing = [key for key in contract if key not in payload]
        if missing:
            raise StoryRoomArtifactValidationError(
                f"{artifact_type} missing required field(s): {', '.join(missing)}"
            )
        unknown = sorted(set(payload) - set(contract))
        if unknown:
            raise StoryRoomArtifactValidationError(
                f"{artifact_type} has unexpected field(s): {', '.join(unknown)}"
            )
        for key, expected in contract.items():
            if not isinstance(payload[key], expected):
                raise StoryRoomArtifactValidationError(
                    f"{artifact_type}.{key} must be {expected.__name__}"
                )

    def _artifact(self, business_slug: str, story_id: str, artifact_type: str) -> dict[str, Any]:
        conn = connect(self.store.db_path)
        try:
            self.store._story(conn, business_slug, story_id)
            row = conn.execute(
                "SELECT * FROM story_artifacts WHERE business_slug = ? AND story_id = ? AND artifact_type = ?",
                (business_slug, story_id, artifact_type),
            ).fetchone()
            if row is None:
                raise StoryRoomNotFoundError(f"Artifact '{artifact_type}' not found")
            return dict(row)
        finally:
            conn.close()

    def _current_version(self, business_slug: str, story_id: str, artifact_type: str) -> dict[str, Any] | None:
        artifact = self._artifact(business_slug, story_id, artifact_type)
        if not artifact["current_version_id"]:
            return None
        return self.get_version(business_slug, artifact["current_version_id"])

    def _stale_dependents(self, old_version_id: str) -> None:
        conn = connect(self.store.db_path)
        try:
            pending = [old_version_id]
            seen: set[str] = set()
            while pending:
                upstream = pending.pop(0)
                if upstream in seen:
                    continue
                seen.add(upstream)
                rows = conn.execute(
                    "SELECT downstream_version_id FROM story_artifact_dependencies WHERE upstream_version_id = ?",
                    (upstream,),
                ).fetchall()
                for row in rows:
                    downstream = row["downstream_version_id"]
                    conn.execute(
                        "UPDATE story_artifact_versions SET status = 'stale' WHERE artifact_version_id = ? AND status != 'stale'",
                        (downstream,),
                    )
                    pending.append(downstream)
            conn.commit()
        finally:
            conn.close()

    def _record_dependencies(
        self,
        business_slug: str,
        story_id: str,
        downstream_version: dict[str, Any],
        based_on: list[str],
    ) -> None:
        if not based_on:
            return
        conn = connect(self.store.db_path)
        try:
            for upstream_version_id in based_on:
                upstream = conn.execute(
                    "SELECT artifact_id, story_id, business_slug FROM story_artifact_versions WHERE artifact_version_id = ?",
                    (upstream_version_id,),
                ).fetchone()
                if upstream is None:
                    raise StoryRoomNotFoundError(f"Upstream artifact version '{upstream_version_id}' not found")
                if upstream["business_slug"] != business_slug or upstream["story_id"] != story_id:
                    raise StoryRoomScopeError(f"Upstream artifact version '{upstream_version_id}' belongs to another scope")
                conn.execute(
                    """INSERT INTO story_artifact_dependencies
                       (dependency_id, story_id, business_slug, upstream_artifact_id,
                        upstream_version_id, downstream_artifact_id, downstream_version_id,
                        relation, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'based_on', datetime('now'))""",
                    (
                        f"dependency_{upstream_version_id}_{downstream_version['artifact_version_id']}",
                        story_id,
                        business_slug,
                        upstream["artifact_id"],
                        upstream_version_id,
                        downstream_version["artifact_id"],
                        downstream_version["artifact_version_id"],
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def create_version(
        self,
        business_slug: str,
        story_id: str,
        artifact_type: str,
        payload: dict[str, Any],
        *,
        based_on: list[str] | None = None,
        expected_current_version_id: str | None = None,
        idempotency_key: str | None = None,
        revision_kind: str = "ai",
        author: str = "system",
    ) -> dict[str, Any]:
        self._validate(artifact_type, payload)
        based_on = based_on or []
        artifact = self.store.create_artifact(business_slug, story_id, artifact_type)
        current = self._current_version(business_slug, story_id, artifact_type)
        if current is not None and expected_current_version_id != current["artifact_version_id"]:
            raise StoryRoomConflictError(
                f"Artifact '{artifact_type}' current version changed; expected current version is required"
            )
        if current is None and expected_current_version_id is not None:
            raise StoryRoomConflictError("Expected current version does not exist")
        version = self.store.create_artifact_version(
            business_slug,
            story_id,
            artifact["artifact_id"],
            payload,
            idempotency_key=idempotency_key,
            based_on=based_on,
            status="working",
            expected_current_version_id=expected_current_version_id,
        )
        diff_text = ""
        if current is not None:
            diff_text = self._diff(current["content_json"], _canonical_json(payload))
        conn = connect(self.store.db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO story_artifact_revision_meta (artifact_version_id, revision_kind, author, diff_text) VALUES (?, ?, ?, ?)",
                (version["artifact_version_id"], revision_kind, author, diff_text),
            )
            conn.commit()
        finally:
            conn.close()
        self._record_dependencies(business_slug, story_id, version, based_on)
        if current is not None:
            self._stale_dependents(current["artifact_version_id"])
        return self.get_version(business_slug, version["artifact_version_id"])

    @staticmethod
    def _diff(old_json: str, new_json: str) -> str:
        old_lines = json.dumps(json.loads(old_json), ensure_ascii=False, indent=2).splitlines()
        new_lines = json.dumps(json.loads(new_json), ensure_ascii=False, indent=2).splitlines()
        return "\n".join(difflib.unified_diff(old_lines, new_lines, fromfile="previous", tofile="current", lineterm=""))

    def direct_edit(
        self,
        business_slug: str,
        story_id: str,
        base_version_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> dict[str, Any]:
        base = self.get_version(business_slug, base_version_id)
        if base["status"] == "stale":
            raise StoryRoomConflictError("Cannot directly edit a stale artifact version")
        artifact = self._artifact_by_id(business_slug, story_id, base["artifact_id"])
        if artifact["current_version_id"] != base_version_id:
            raise StoryRoomConflictError("Direct edit requires the current artifact version")
        return self.create_version(
            business_slug,
            story_id,
            artifact["artifact_type"],
            payload,
            based_on=[base_version_id],
            expected_current_version_id=base_version_id,
            idempotency_key=idempotency_key,
            revision_kind="direct_edit",
            author="operator",
        )

    def _artifact_by_id(self, business_slug: str, story_id: str, artifact_id: str) -> dict[str, Any]:
        conn = connect(self.store.db_path)
        try:
            self.store._story(conn, business_slug, story_id)
            row = conn.execute("SELECT * FROM story_artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
            if row is None:
                raise StoryRoomNotFoundError(f"Artifact '{artifact_id}' not found")
            if row["business_slug"] != business_slug or row["story_id"] != story_id:
                raise StoryRoomScopeError(f"Artifact '{artifact_id}' belongs to another scope")
            return dict(row)
        finally:
            conn.close()

    def get_version(self, business_slug: str, artifact_version_id: str) -> dict[str, Any]:
        version = self.store.get_artifact_version(business_slug, artifact_version_id)
        conn = connect(self.store.db_path)
        try:
            meta = conn.execute(
                "SELECT revision_kind, author, diff_text FROM story_artifact_revision_meta WHERE artifact_version_id = ?",
                (artifact_version_id,),
            ).fetchone()
            if meta:
                version.update(dict(meta))
            return version
        finally:
            conn.close()

    def lock(self, business_slug: str, story_id: str, artifact_version_id: str, idempotency_key: str) -> dict[str, Any]:
        version = self.get_version(business_slug, artifact_version_id)
        artifact = self._artifact_by_id(business_slug, story_id, version["artifact_id"])
        if artifact["current_version_id"] != artifact_version_id or version["status"] == "stale":
            raise StoryRoomConflictError("Cannot lock a stale or non-current artifact version")
        return self.store.record_artifact_decision(
            business_slug, story_id, artifact_version_id, "lock", idempotency_key=idempotency_key
        )

    def require_locked_current(self, business_slug: str, story_id: str, artifact_type: str) -> dict[str, Any]:
        version = self._current_version(business_slug, story_id, artifact_type)
        if version is not None and version["status"] == "stale":
            raise StoryRoomConflictError(f"Artifact '{artifact_type}' is stale")
        if version is None or version["status"] != "locked":
            raise StoryRoomConflictError(f"Artifact '{artifact_type}' is not a current locked version")
        return version
