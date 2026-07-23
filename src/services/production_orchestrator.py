"""
VF-CW-002 — ProductionSession aggregate and durable state machine.

Tenant-scoped one-session-per-platform-asset persistence with compare-and-set
state transitions, transition history, active requirement/manifest/render
pointers, and idempotent attempts.

State machine:
    planning_components → generating_components → component_review_required
    → manifest_ready → assembling → final_review_required
    → gate3_approved | blocked | failed

AMENDMENT-014 adds composition sub-states:
    manifest_ready → composition_planning → composition_review_required
    → composition_ratified → assembling

Failure paths:
    composition_planning → blocked
    composition_review_required → composition_planning (operator requested changes)
    composition_ratified → composition_planning (post-ratification change detected)

No route writes state directly. All transitions go through ProductionSessionService.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


# ── States ─────────────────────────────────────────────────────────────

# AMENDMENT-013 base states
STATE_PLANNING_COMPONENTS = "planning_components"
STATE_GENERATING_COMPONENTS = "generating_components"
STATE_COMPONENT_REVIEW_REQUIRED = "component_review_required"
STATE_MANIFEST_READY = "manifest_ready"
STATE_ASSEMBLING = "assembling"
STATE_FINAL_REVIEW_REQUIRED = "final_review_required"
STATE_GATE3_APPROVED = "gate3_approved"
STATE_BLOCKED = "blocked"
STATE_FAILED = "failed"

# AMENDMENT-014 composition sub-states (between manifest_ready and assembling)
STATE_COMPOSITION_PLANNING = "composition_planning"
STATE_COMPOSITION_REVIEW_REQUIRED = "composition_review_required"
STATE_COMPOSITION_RATIFIED = "composition_ratified"

# Valid transitions: {from_state: {to_state: reason}}
VALID_TRANSITIONS = {
    STATE_PLANNING_COMPONENTS: {
        STATE_GENERATING_COMPONENTS: "requirements planned",
        STATE_BLOCKED: "planning failed",
        STATE_FAILED: "fatal error",
    },
    STATE_GENERATING_COMPONENTS: {
        STATE_COMPONENT_REVIEW_REQUIRED: "candidates generated",
        STATE_BLOCKED: "generation failed",
        STATE_FAILED: "fatal error",
    },
    STATE_COMPONENT_REVIEW_REQUIRED: {
        STATE_GENERATING_COMPONENTS: "operator requested changes",
        STATE_MANIFEST_READY: "manifest frozen",
        STATE_BLOCKED: "comteness blocked",
        STATE_FAILED: "fatal error",
    },
    STATE_MANIFEST_READY: {
        STATE_COMPOSITION_PLANNING: "composition plan generation started",
        STATE_ASSEMBLING: "composition skipped (legacy path)",
        STATE_COMPONENT_REVIEW_REQUIRED: "manifest invalidated",
        STATE_BLOCKED: "manifest error",
        STATE_FAILED: "fatal error",
    },
    # AMENDMENT-014 composition sub-states
    STATE_COMPOSITION_PLANNING: {
        STATE_COMPOSITION_REVIEW_REQUIRED: "plan generated, previews ready",
        STATE_BLOCKED: "plan generation failed",
        STATE_FAILED: "fatal error",
    },
    STATE_COMPOSITION_REVIEW_REQUIRED: {
        STATE_COMPOSITION_PLANNING: "operator requested changes",
        STATE_COMPOSITION_RATIFIED: "operator ratified plan",
        STATE_BLOCKED: "plan error",
        STATE_FAILED: "fatal error",
    },
    STATE_COMPOSITION_RATIFIED: {
        STATE_ASSEMBLING: "renderer spec compiled",
        STATE_COMPOSITION_PLANNING: "post-ratification change detected",
        STATE_BLOCKED: "spec compilation failed",
        STATE_FAILED: "fatal error",
    },
    STATE_ASSEMBLING: {
        STATE_FINAL_REVIEW_REQUIRED: "render complete",
        STATE_BLOCKED: "render failed",
        STATE_FAILED: "fatal error",
    },
    STATE_FINAL_REVIEW_REQUIRED: {
        STATE_GATE3_APPROVED: "gate 3 approved",
        STATE_ASSEMBLING: "operator requested re-render",
        STATE_BLOCKED: "evidence incomplete",
        STATE_FAILED: "fatal error",
    },
    STATE_GATE3_APPROVED: {
        STATE_FINAL_REVIEW_REQUIRED: "gate 3 invalidated",
        STATE_FAILED: "fatal error",
    },
    # Blocked and failed are recoverable
    STATE_BLOCKED: {
        STATE_PLANNING_COMPONENTS: "retry from planning",
        STATE_GENERATING_COMPONENTS: "retry from generation",
        STATE_COMPONENT_REVIEW_REQUIRED: "retry from review",
        STATE_MANIFEST_READY: "retry from manifest",
        STATE_COMPOSITION_PLANNING: "retry from composition planning",
        STATE_COMPOSITION_REVIEW_REQUIRED: "retry from composition review",
        STATE_COMPOSITION_RATIFIED: "retry from ratification",
        STATE_ASSEMBLING: "retry from assembly",
        STATE_FINAL_REVIEW_REQUIRED: "retry from final review",
        STATE_FAILED: "escalated to failure",
    },
    STATE_FAILED: {
        STATE_PLANNING_COMPONENTS: "retry from scratch",
    },
}

# Human-wait states — these should NOT have stale running jobs
HUMAN_WAIT_STATES = {
    STATE_COMPONENT_REVIEW_REQUIRED,
    STATE_COMPOSITION_REVIEW_REQUIRED,
    STATE_FINAL_REVIEW_REQUIRED,
}

# States where the operator needs to take action
OPERATOR_ACTION_STATES = HUMAN_WAIT_STATES | {STATE_BLOCKED}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS production_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    draft_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    format TEXT,
    writer_contract_hash TEXT,
    current_state TEXT NOT NULL DEFAULT 'planning_components',
    state_reason TEXT,
    active_requirements_version INTEGER,
    active_manifest_version INTEGER,
    active_render_version INTEGER,
    active_composition_plan_hash TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE INDEX IF NOT EXISTS idx_prod_sessions_business ON production_sessions(business_slug);
CREATE INDEX IF NOT EXISTS idx_prod_sessions_asset ON production_sessions(asset_id);
CREATE INDEX IF NOT EXISTS idx_prod_sessions_draft ON production_sessions(draft_id);
CREATE INDEX IF NOT EXISTS idx_prod_sessions_state ON production_sessions(current_state);

CREATE TABLE IF NOT EXISTS production_session_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    from_state TEXT,                     -- NULL for initial creation
    to_state TEXT NOT NULL,
    reason TEXT,
    actor TEXT NOT NULL DEFAULT 'system',
    attempt INTEGER NOT NULL DEFAULT 1,
    transitioned_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES production_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_transitions_session ON production_session_transitions(session_id);
"""


class ProductionSessionError(Exception):
    """Production session error."""
    pass


class InvalidTransitionError(ProductionSessionError):
    """Attempted an invalid state transition."""
    pass


class SessionNotFoundError(ProductionSessionError):
    """Session not found."""
    pass


class CrossTenantError(ProductionSessionError):
    """Attempted to access a session from a different tenant."""
    pass


class ProductionSessionService:
    """Tenant-scoped production session store with compare-and-set transitions.

    One session per platform asset. All state transitions go through
    transition() which validates against the state machine. Routes never
    write state directly.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(
        self,
        business_slug: str,
        draft_id: int,
        asset_id: int,
        platform: str,
        format: str = None,
        writer_contract_hash: str = None,
    ) -> dict:
        """Create a new production session for a platform asset.

        Raises if a session already exists for this asset (one per asset).
        """
        # Check for existing session
        existing = self.get_session_for_asset(business_slug, asset_id)
        if existing:
            raise ProductionSessionError(
                f"Session already exists for asset {asset_id} (session {existing['id']})"
            )

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO production_sessions
               (business_slug, draft_id, asset_id, platform, format,
                writer_contract_hash, current_state, state_reason,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'planning_components', 'session created', ?, ?)""",
            (business_slug, draft_id, asset_id, platform, format,
             writer_contract_hash, ts, ts),
        )
        session_id = cursor.lastrowid
        # Record initial transition
        conn.execute(
            """INSERT INTO production_session_transitions
               (session_id, from_state, to_state, reason, actor, attempt, transitioned_at)
               VALUES (?, NULL, 'planning_components', 'session created', 'system', 1, ?)""",
            (session_id, ts),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM production_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_session(self, business_slug: str, session_id: int) -> dict:
        """Get a session by ID, verifying tenant scope."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM production_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        conn.close()
        if not row:
            raise SessionNotFoundError(f"Session {session_id} not found")
        row = dict(row)
        if row["business_slug"] != business_slug:
            raise CrossTenantError(
                f"Session {session_id} belongs to {row['business_slug']}, not {business_slug}"
            )
        return row

    def get_session_for_asset(self, business_slug: str, asset_id: int) -> Optional[dict]:
        """Get the production session for a given asset, if one exists."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM production_sessions WHERE business_slug = ? AND asset_id = ?",
            (business_slug, asset_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_session_for_draft(
        self, business_slug: str, draft_id: int
    ) -> list[dict]:
        """Get all production sessions for a draft (one per platform asset)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM production_sessions WHERE business_slug = ? AND draft_id = ? ORDER BY id",
            (business_slug, draft_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def transition(
        self,
        business_slug: str,
        session_id: int,
        to_state: str,
        reason: str = None,
        actor: str = "system",
    ) -> dict:
        """Transition a session to a new state using compare-and-set.

        Validates that the transition is allowed by the state machine.
        Records the transition in the transition history.
        """
        session = self.get_session(business_slug, session_id)
        from_state = session["current_state"]

        # Validate transition
        allowed = VALID_TRANSITIONS.get(from_state, {})
        if to_state not in allowed:
            raise InvalidTransitionError(
                f"Invalid transition: {from_state} → {to_state}. "
                f"Allowed: {list(allowed.keys())}"
            )

        ts = self._now()
        attempt = session["attempt"]
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Compare-and-set: only update if current state hasn't changed
        cursor = conn.execute(
            """UPDATE production_sessions
               SET current_state = ?, state_reason = ?, updated_at = ?
               WHERE id = ? AND current_state = ?""",
            (to_state, reason, ts, session_id, from_state),
        )
        if cursor.rowcount == 0:
            # State changed between read and write — concurrent transition
            conn.close()
            raise InvalidTransitionError(
                f"Concurrent transition detected: session {session_id} "
                f"was {from_state} but is no longer"
            )

        # Record transition
        conn.execute(
            """INSERT INTO production_session_transitions
               (session_id, from_state, to_state, reason, actor, attempt, transitioned_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, from_state, to_state, reason, actor, attempt, ts),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM production_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def set_active_requirements(
        self, business_slug: str, session_id: int, version: int
    ) -> dict:
        """Set the active requirements version pointer."""
        session = self.get_session(business_slug, session_id)
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE production_sessions SET active_requirements_version = ?, updated_at = ? WHERE id = ?",
            (version, ts, session_id),
        )
        conn.commit()
        conn.close()
        return self.get_session(business_slug, session_id)

    def set_active_manifest(
        self, business_slug: str, session_id: int, version: int
    ) -> dict:
        """Set the active manifest version pointer."""
        session = self.get_session(business_slug, session_id)
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE production_sessions SET active_manifest_version = ?, updated_at = ? WHERE id = ?",
            (version, ts, session_id),
        )
        conn.commit()
        conn.close()
        return self.get_session(business_slug, session_id)

    def set_active_render(
        self, business_slug: str, session_id: int, version: int
    ) -> dict:
        """Set the active render version pointer."""
        session = self.get_session(business_slug, session_id)
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE production_sessions SET active_render_version = ?, updated_at = ? WHERE id = ?",
            (version, ts, session_id),
        )
        conn.commit()
        conn.close()
        return self.get_session(business_slug, session_id)

    def set_composition_plan_hash(
        self, business_slug: str, session_id: int, plan_hash: str
    ) -> dict:
        """Set the active composition plan hash (AMENDMENT-014)."""
        session = self.get_session(business_slug, session_id)
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE production_sessions SET active_composition_plan_hash = ?, updated_at = ? WHERE id = ?",
            (plan_hash, ts, session_id),
        )
        conn.commit()
        conn.close()
        return self.get_session(business_slug, session_id)

    def increment_attempt(
        self, business_slug: str, session_id: int
    ) -> dict:
        """Increment the retry attempt counter."""
        session = self.get_session(business_slug, session_id)
        ts = self._now()
        new_attempt = session["attempt"] + 1
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE production_sessions SET attempt = ?, updated_at = ? WHERE id = ?",
            (new_attempt, ts, session_id),
        )
        conn.commit()
        conn.close()
        return self.get_session(business_slug, session_id)

    def get_transition_history(
        self, business_slug: str, session_id: int
    ) -> list[dict]:
        """Get the full transition history for a session."""
        # Verify tenant scope
        self.get_session(business_slug, session_id)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM production_session_transitions WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_sessions(
        self,
        business_slug: str,
        state: str = None,
        draft_id: int = None,
    ) -> list[dict]:
        """List sessions, optionally filtered by state or draft."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM production_sessions WHERE business_slug = ?"
        params = [business_slug]
        if state:
            query += " AND current_state = ?"
            params.append(state)
        if draft_id is not None:
            query += " AND draft_id = ?"
            params.append(draft_id)
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def is_human_wait(self, state: str) -> bool:
        """Check if a state is a human-wait state (no stale running job)."""
        return state in HUMAN_WAIT_STATES