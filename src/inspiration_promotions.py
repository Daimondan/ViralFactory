"""VF-INSP-005 — Bookmark and promotion paths (AMENDMENT-012 C5).

Deliberately distinct actions that promote an observation without rewriting
observation history:

- Bookmark: keeps an inspiration reference without making it grounding material.
- Add to Source Bank: creates a source candidate with status='new', linked to
  its observation and collection provenance. Does not immediately feed ideation.
- Propose experiment: creates an async-gate proposal with evidence.
- Propose pattern: creates a module proposal; approval required before bump.

No observation silently changes a module, process, source status, idea input,
or soundtrack. Each action's destination and undo/history are visible. Bulk
operations exist for queues that can exceed 50 items.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from inspiration_contracts import InspirationContractError


class PromotionError(ValueError):
    """Raised when a promotion action violates C5."""


PROMOTION_ACTIONS = frozenset({"bookmark", "add_to_source_bank", "propose_experiment", "propose_pattern"})
PROMOTION_STATUSES = frozenset({"active", "reverted"})


class PromotionStore:
    """Append-only bookmark and promotion records for Inspiration observations."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS insp_bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_slug TEXT NOT NULL,
        trend_item_id INTEGER NOT NULL,
        observation_id INTEGER NOT NULL,
        action TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'active',
        destination TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        reverted_at TEXT,
        FOREIGN KEY (trend_item_id) REFERENCES insp_trend_items(id),
        FOREIGN KEY (observation_id) REFERENCES insp_observations(id)
    );
    CREATE INDEX IF NOT EXISTS idx_insp_bookmarks_tenant
        ON insp_bookmarks(business_slug, trend_item_id, action);
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def bookmark(self, *, business_slug: str, trend_item_id: int,
                 observation_id: int, note: str = "") -> dict:
        """Bookmark an inspiration reference without making it grounding material."""
        return self._add_action(
            business_slug=business_slug,
            trend_item_id=trend_item_id,
            observation_id=observation_id,
            action="bookmark",
            note=note,
            destination="bookmark",
        )

    def add_to_source_bank(self, *, business_slug: str, trend_item_id: int,
                           observation_id: int, note: str = "", db_path: str = "") -> dict:
        """Create a source candidate with status='new', linked to observation
        provenance. Also inserts a row into the sources table so it appears
        in the Source Bank UI for review. The existing Source Bank Keep gate
        remains intact — status='new' does not feed ideation until approved."""
        result = self._add_action(
            business_slug=business_slug,
            trend_item_id=trend_item_id,
            observation_id=observation_id,
            action="add_to_source_bank",
            note=note,
            destination="source_bank",
        )
        # Insert into the actual sources table
        if db_path:
            import hashlib as _hashlib
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            # Get the trend item details
            item = conn.execute(
                "SELECT * FROM insp_trend_items WHERE id=?", (trend_item_id,)
            ).fetchone()
            if item:
                title = dict(item).get("title", "") or dict(item).get("creator", "") or f"Inspiration item #{trend_item_id}"
                url = dict(item).get("canonical_url", "") or dict(item).get("preview_url", "")
                summary = f"From Inspiration Center: {dict(item).get('provider', '')} — {dict(item).get('platform', '')}"
                if note:
                    summary += f" | Note: {note}"
                content_hash = _hashlib.sha256(
                    f"{business_slug}:{trend_item_id}:{observation_id}".encode()
                ).hexdigest()[:16]
                # Check if already exists
                existing = conn.execute(
                    "SELECT id FROM sources WHERE business_slug=? AND content_hash=?",
                    (business_slug, content_hash),
                ).fetchone()
                if not existing:
                    conn.execute(
                        """INSERT INTO sources
                           (business_slug, source_type, title, url, summary, content,
                            origin, first_seen, content_hash, status)
                           VALUES (?, 'inspiration', ?, ?, ?, '', 'operator', ?, ?, 'new')""",
                        (business_slug, title, url, summary,
                         self._now(), content_hash),
                    )
                    conn.commit()
            conn.close()
        return result

    def propose_experiment(self, *, business_slug: str, trend_item_id: int,
                           observation_id: int, note: str = "") -> dict:
        """Create an async-gate proposal with evidence. No module or process
        changes until approved."""
        return self._add_action(
            business_slug=business_slug,
            trend_item_id=trend_item_id,
            observation_id=observation_id,
            action="propose_experiment",
            note=note,
            destination="experiment_queue",
        )

    def propose_pattern(self, *, business_slug: str, trend_item_id: int,
                        observation_id: int, note: str = "") -> dict:
        """Create a module proposal. Approval is required before a module
        version bump."""
        return self._add_action(
            business_slug=business_slug,
            trend_item_id=trend_item_id,
            observation_id=observation_id,
            action="propose_pattern",
            note=note,
            destination="module_proposal_queue",
        )

    def _add_action(self, *, business_slug: str, trend_item_id: int,
                    observation_id: int, action: str, note: str = "",
                    destination: str = "") -> dict:
        if action not in PROMOTION_ACTIONS:
            raise PromotionError(f"action must be one of {PROMOTION_ACTIONS}")
        if not business_slug:
            raise PromotionError("business_slug is required")
        if not isinstance(trend_item_id, int) or trend_item_id < 1:
            raise PromotionError("trend_item_id must be a positive integer")
        if not isinstance(observation_id, int) or observation_id < 1:
            raise PromotionError("observation_id must be a positive integer")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            # Verify the observation and item exist and belong to this tenant
            obs = conn.execute(
                "SELECT id, business_slug, trend_item_id FROM insp_observations WHERE id = ?",
                (observation_id,),
            ).fetchone()
            if not obs:
                raise PromotionError(f"observation {observation_id} not found")
            if obs["business_slug"] != business_slug:
                raise PromotionError("observation does not belong to this tenant")
            if obs["trend_item_id"] != trend_item_id:
                raise PromotionError("observation does not match trend_item_id")
            # Prevent duplicate active bookmark of the same type on the same item
            existing = conn.execute(
                """SELECT id FROM insp_bookmarks
                   WHERE business_slug=? AND trend_item_id=? AND action=? AND status='active'""",
                (business_slug, trend_item_id, action),
            ).fetchone()
            if existing:
                raise PromotionError(f"item {trend_item_id} already has an active {action}")
            ts = self._now()
            cursor = conn.execute(
                """INSERT INTO insp_bookmarks
                   (business_slug, trend_item_id, observation_id, action, note,
                    status, destination, created_at, reverted_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL)""",
                (business_slug, trend_item_id, observation_id, action,
                 note[:2000], destination, ts),
            )
            bookmark_id = cursor.lastrowid
            conn.commit()
            return {
                "id": bookmark_id,
                "business_slug": business_slug,
                "trend_item_id": trend_item_id,
                "observation_id": observation_id,
                "action": action,
                "note": note[:2000],
                "status": "active",
                "destination": destination,
                "created_at": ts,
            }

    def revert(self, *, bookmark_id: int) -> dict:
        """Revert (undo) a promotion action. The action history is preserved —
        the record stays but is marked 'reverted'."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM insp_bookmarks WHERE id = ?", (bookmark_id,)
            ).fetchone()
            if not row:
                raise PromotionError(f"bookmark {bookmark_id} not found")
            if row["status"] == "reverted":
                raise PromotionError("bookmark is already reverted")
            ts = self._now()
            conn.execute(
                "UPDATE insp_bookmarks SET status='reverted', reverted_at=? WHERE id=?",
                (ts, bookmark_id),
            )
            conn.commit()
            return dict(row) | {"status": "reverted", "reverted_at": ts}

    def list_bookmarks(self, *, business_slug: str,
                       action: str | None = None) -> list[dict]:
        """List all bookmarks/promotions for a tenant. Used for the bookmark
        view and bulk operations."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if action:
                rows = conn.execute(
                    """SELECT b.*, i.title AS item_title, i.creator AS item_creator,
                              i.platform AS item_platform, i.provider AS item_provider
                       FROM insp_bookmarks b
                       LEFT JOIN insp_trend_items i ON i.id = b.trend_item_id
                       WHERE b.business_slug=? AND b.action=?
                       ORDER BY b.created_at DESC""",
                    (business_slug, action),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT b.*, i.title AS item_title, i.creator AS item_creator,
                              i.platform AS item_platform, i.provider AS item_provider
                       FROM insp_bookmarks b
                       LEFT JOIN insp_trend_items i ON i.id = b.trend_item_id
                       WHERE b.business_slug=?
                       ORDER BY b.created_at DESC""",
                    (business_slug,),
                ).fetchall()
            return [dict(r) for r in rows]

    def get_bookmark(self, bookmark_id: int) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM insp_bookmarks WHERE id = ?", (bookmark_id,)
            ).fetchone()
            return dict(row) if row else None

    def bulk_revert(self, *, business_slug: str, bookmark_ids: list[int]) -> dict:
        """Revert multiple bookmarks at once. Used for queues that can exceed 50.
        Returns {reverted: [...], errors: [...]}."""
        reverted = []
        errors = []
        for bid in bookmark_ids:
            try:
                result = self.revert(bookmark_id=bid)
                if result.get("business_slug") == business_slug:
                    reverted.append(bid)
                else:
                    errors.append({"id": bid, "error": "tenant mismatch"})
            except PromotionError as exc:
                errors.append({"id": bid, "error": str(exc)})
        return {"reverted": reverted, "errors": errors}