"""Evidence and authority boundary for Story Room understanding entries."""

from __future__ import annotations

from typing import Any

try:
    from .db import connect
    from .story_room_store import StoryRoomStore
except ImportError:
    from db import connect
    from story_room_store import StoryRoomStore


class StoryRoomEvidenceError(ValueError):
    """Raised when an understanding entry lacks exact scoped evidence/authority."""


class StoryRoomUnderstandingService:
    """Apply the Known/Assumed/Missing/Locked rules before storage."""

    def __init__(self, store: StoryRoomStore):
        self.store = store

    def _require_evidence(self, business_slug: str, story_id: str, refs: list[str]) -> None:
        if not refs:
            raise StoryRoomEvidenceError("Known entries require exact evidence refs")
        conn = connect(self.store.db_path)
        try:
            self.store._story(conn, business_slug, story_id)
            for ref in refs:
                if ref.startswith("event_"):
                    row = conn.execute(
                        "SELECT story_id, business_slug FROM story_events WHERE event_id = ?", (ref,)
                    ).fetchone()
                elif ref.startswith("contribution_"):
                    row = conn.execute(
                        "SELECT story_id, business_slug FROM story_contributions WHERE contribution_id = ?", (ref,)
                    ).fetchone()
                elif ref.startswith("artifact_version_"):
                    row = conn.execute(
                        "SELECT story_id, business_slug FROM story_artifact_versions WHERE artifact_version_id = ?", (ref,)
                    ).fetchone()
                else:
                    raise StoryRoomEvidenceError(f"Evidence ref '{ref}' is not an exact Story Room ref")
                if row is None:
                    raise StoryRoomEvidenceError(f"Evidence ref '{ref}' not found")
                if row["story_id"] != story_id or row["business_slug"] != business_slug:
                    raise StoryRoomEvidenceError(f"Evidence ref '{ref}' is outside the Story Room scope")
        finally:
            conn.close()

    def _require_verified_lock(
        self, business_slug: str, story_id: str, decision_id: str | None
    ) -> None:
        if not decision_id:
            raise StoryRoomEvidenceError("Locked entries require a verified lock decision")
        conn = connect(self.store.db_path)
        try:
            row = conn.execute(
                "SELECT action, story_id, business_slug FROM story_artifact_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
            if row is None or row["action"] != "lock":
                raise StoryRoomEvidenceError("Locked entries require a verified lock decision")
            if row["story_id"] != story_id or row["business_slug"] != business_slug:
                raise StoryRoomEvidenceError("Verified lock decision is outside the Story Room scope")
        finally:
            conn.close()

    def add_entry(
        self,
        business_slug: str,
        story_id: str,
        kind: str,
        statement: str,
        scope: str,
        evidence_refs: list[str],
        created_by: str,
        idempotency_key: str,
        *,
        supersedes: str | None = None,
        verified_decision_id: str | None = None,
    ) -> dict[str, Any]:
        if kind == "known" and created_by in {"ai", "tool"}:
            self._require_evidence(business_slug, story_id, evidence_refs)
        elif kind == "locked":
            self._require_evidence(business_slug, story_id, evidence_refs)
            self._require_verified_lock(business_slug, story_id, verified_decision_id)
        elif kind not in {"assumed", "missing", "known", "locked"}:
            raise StoryRoomEvidenceError(f"Unsupported understanding kind: {kind}")
        return self.store.add_understanding(
            business_slug,
            story_id,
            kind,
            statement,
            scope,
            evidence_refs,
            created_by,
            idempotency_key,
            supersedes=supersedes,
        )
