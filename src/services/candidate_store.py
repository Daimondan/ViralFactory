"""
VF-CW-004 — Immutable candidates and append-only decisions.

Candidate versions are append-only. A candidate references the owning
artifact table (vo_takes, asset_media, soundtrack artifacts/mixes,
renderer specimens) and stores its exact artifact/preview hashes and
provenance linkage.

Operator decisions are append-only and bind candidate_version_id +
artifact_hash + requirement_version_hash. Selection and approval are
explicit; a failed/regenerated/superseded version cannot be approved.
No single `approved` Boolean is the source of truth.

Status lifecycle: generating → available → (approved | rejected) → superseded | stale
Failed candidates: generating → failed
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS component_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    production_session_id INTEGER NOT NULL,
    draft_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    role TEXT NOT NULL,
    candidate_lineage_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'generating',
    artifact_ref TEXT,
    artifact_hash TEXT,
    artifact_path TEXT,
    preview_ref TEXT,
    preview_hash TEXT,
    preview_path TEXT,
    source_type TEXT,
    source_provenance_json TEXT,
    generation_provenance_json TEXT,
    rights_snapshot_json TEXT,
    cost_estimate_usd REAL,
    cost_approved INTEGER DEFAULT 0,
    beat_refs_json TEXT,
    measurement_json TEXT,
    superseded_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (production_session_id) REFERENCES production_sessions(id),
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE INDEX IF NOT EXISTS idx_candidates_session ON component_candidates(production_session_id);
CREATE INDEX IF NOT EXISTS idx_candidates_asset ON component_candidates(asset_id);
CREATE INDEX IF NOT EXISTS idx_candidates_category ON component_candidates(category, role);
CREATE INDEX IF NOT EXISTS idx_candidates_lineage ON component_candidates(candidate_lineage_id);
CREATE INDEX IF NOT EXISTS idx_candidates_status ON component_candidates(status);
CREATE INDEX IF NOT EXISTS idx_candidates_business ON component_candidates(business_slug);

CREATE TABLE IF NOT EXISTS component_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    production_session_id INTEGER NOT NULL,
    candidate_id INTEGER NOT NULL,
    candidate_version INTEGER NOT NULL,
    artifact_hash TEXT,
    requirement_version_hash TEXT,
    decision_type TEXT NOT NULL,
    feedback TEXT,
    actor TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES component_candidates(id),
    FOREIGN KEY (production_session_id) REFERENCES production_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_decisions_candidate ON component_decisions(candidate_id);
CREATE INDEX IF NOT EXISTS idx_decisions_session ON component_decisions(production_session_id);
CREATE INDEX IF NOT EXISTS idx_decisions_business ON component_decisions(business_slug);
CREATE INDEX IF NOT EXISTS idx_decisions_type ON component_decisions(decision_type);
"""


VALID_STATUSES = {
    "generating", "available", "failed", "rejected",
    "approved", "superseded", "stale",
}

VALID_DECISION_TYPES = {"select", "approve", "reject", "regenerate"}


class CandidateError(Exception):
    """Candidate or decision error."""
    pass


class CandidateStore:
    """Append-only candidate and decision store.

    Candidates are immutable once created — status changes create new
    versions or update the status field with transition tracking.
    Decisions are strictly append-only.
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

    def _compute_lineage_id(self, business_slug: str, session_id: int,
                             category: str, role: str, beat_ref: str = None) -> str:
        """Compute a stable lineage ID from scope + category + role."""
        parts = [business_slug, str(session_id), category, role]
        if beat_ref:
            parts.append(beat_ref)
        raw = "|".join(parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def create_candidate(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        category: str,
        role: str,
        beat_refs: list[str] = None,
        artifact_ref: str = None,
        artifact_hash: str = None,
        artifact_path: str = None,
        preview_ref: str = None,
        preview_hash: str = None,
        preview_path: str = None,
        source_type: str = None,
        source_provenance: dict = None,
        generation_provenance: dict = None,
        rights_snapshot: dict = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
        measurement: dict = None,
        status: str = "generating",
    ) -> dict:
        """Create a new candidate version. If a candidate with the same
        lineage already exists, this creates a new version."""
        if status not in VALID_STATUSES:
            raise CandidateError(f"Invalid status: {status}")

        lineage_id = self._compute_lineage_id(
            business_slug, production_session_id, category, role,
            beat_refs[0] if beat_refs else None,
        )

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Get next version for this lineage
        row = conn.execute(
            "SELECT MAX(version) as max_v FROM component_candidates WHERE candidate_lineage_id = ?",
            (lineage_id,),
        ).fetchone()
        next_version = (row["max_v"] or 0) + 1

        cursor = conn.execute(
            """INSERT INTO component_candidates
               (business_slug, production_session_id, draft_id, asset_id,
                category, role, candidate_lineage_id, version, status,
                artifact_ref, artifact_hash, artifact_path,
                preview_ref, preview_hash, preview_path,
                source_type, source_provenance_json, generation_provenance_json,
                rights_snapshot_json, cost_estimate_usd, cost_approved,
                beat_refs_json, measurement_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (business_slug, production_session_id, draft_id, asset_id,
             category, role, lineage_id, next_version, status,
             artifact_ref, artifact_hash, artifact_path,
             preview_ref, preview_hash, preview_path,
             source_type,
             json.dumps(source_provenance, ensure_ascii=False) if source_provenance else None,
             json.dumps(generation_provenance, ensure_ascii=False) if generation_provenance else None,
             json.dumps(rights_snapshot, ensure_ascii=False) if rights_snapshot else None,
             cost_estimate_usd, 1 if cost_approved else 0,
             json.dumps(beat_refs, ensure_ascii=False) if beat_refs else None,
             json.dumps(measurement, ensure_ascii=False) if measurement else None,
             ts, ts),
        )
        candidate_id = cursor.lastrowid

        # Supersede prior versions if this is a regeneration
        if next_version > 1:
            conn.execute(
                """UPDATE component_candidates SET status = 'superseded',
                   superseded_by = ?, updated_at = ?
                   WHERE candidate_lineage_id = ? AND version < ? AND status != 'superseded'""",
                (candidate_id, ts, lineage_id, next_version),
            )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM component_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_candidate(self, business_slug: str, candidate_id: int) -> dict:
        """Get a candidate by ID, verifying tenant scope."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM component_candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        conn.close()
        if not row:
            raise CandidateError(f"Candidate {candidate_id} not found")
        row = dict(row)
        if row["business_slug"] != business_slug:
            raise CandidateError(
                f"Candidate {candidate_id} belongs to {row['business_slug']}"
            )
        return row

    def list_candidates(
        self,
        business_slug: str,
        production_session_id: int,
        category: str = None,
        role: str = None,
        status: str = None,
    ) -> list[dict]:
        """List candidates for a session, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM component_candidates WHERE business_slug = ? AND production_session_id = ?"
        params = [business_slug, production_session_id]
        if category:
            query += " AND category = ?"
            params.append(category)
        if role:
            query += " AND role = ?"
            params.append(role)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_current_versions(
        self, business_slug: str, production_session_id: int
    ) -> list[dict]:
        """Get the current (non-superseded, non-stale) version for each lineage."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM component_candidates
               WHERE business_slug = ? AND production_session_id = ?
               AND status NOT IN ('superseded', 'stale')
               ORDER BY candidate_lineage_id, version DESC""",
            (business_slug, production_session_id),
        ).fetchall()
        conn.close()
        # Deduplicate by lineage — keep highest version
        seen = {}
        for r in rows:
            r = dict(r)
            if r["candidate_lineage_id"] not in seen:
                seen[r["candidate_lineage_id"]] = r
        return list(seen.values())

    def update_status(
        self,
        business_slug: str,
        candidate_id: int,
        new_status: str,
    ) -> dict:
        """Update a candidate's status. Cannot approve a superseded/failed/stale candidate."""
        if new_status not in VALID_STATUSES:
            raise CandidateError(f"Invalid status: {new_status}")

        candidate = self.get_candidate(business_slug, candidate_id)

        # Cannot approve invalid candidates
        if new_status == "approved" and candidate["status"] in ("superseded", "failed", "stale"):
            raise CandidateError(
                f"Cannot approve candidate in status '{candidate['status']}'"
            )

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE component_candidates SET status = ?, updated_at = ? WHERE id = ?",
            (new_status, ts, candidate_id),
        )
        conn.commit()
        conn.close()
        return self.get_candidate(business_slug, candidate_id)

    def record_decision(
        self,
        business_slug: str,
        production_session_id: int,
        candidate_id: int,
        decision_type: str,
        feedback: str = None,
        requirement_version_hash: str = None,
        actor: str = "operator",
    ) -> dict:
        """Record an append-only operator decision on a candidate."""
        if decision_type not in VALID_DECISION_TYPES:
            raise CandidateError(f"Invalid decision type: {decision_type}")

        candidate = self.get_candidate(business_slug, candidate_id)

        # Cannot approve/reject a superseded/failed/stale candidate
        if decision_type in ("approve", "reject", "select"):
            if candidate["status"] in ("superseded", "failed", "stale"):
                raise CandidateError(
                    f"Cannot {decision_type} candidate in status '{candidate['status']}'"
                )

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO component_decisions
               (business_slug, production_session_id, candidate_id,
                candidate_version, artifact_hash, requirement_version_hash,
                decision_type, feedback, actor, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (business_slug, production_session_id, candidate_id,
             candidate["version"], candidate["artifact_hash"],
             requirement_version_hash, decision_type, feedback, actor, ts),
        )
        decision_id = cursor.lastrowid

        # Update candidate status based on decision
        if decision_type == "approve":
            conn.execute(
                "UPDATE component_candidates SET status = 'approved', updated_at = ? WHERE id = ?",
                (ts, candidate_id),
            )
        elif decision_type == "reject":
            conn.execute(
                "UPDATE component_candidates SET status = 'rejected', updated_at = ? WHERE id = ?",
                (ts, candidate_id),
            )
        elif decision_type == "regenerate":
            # Mark current as superseded — a new version will be created
            conn.execute(
                "UPDATE component_candidates SET status = 'superseded', updated_at = ? WHERE id = ?",
                (ts, candidate_id),
            )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM component_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_decisions(
        self, business_slug: str, candidate_id: int
    ) -> list[dict]:
        """Get the decision history for a candidate."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM component_decisions WHERE business_slug = ? AND candidate_id = ? ORDER BY id",
            (business_slug, candidate_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_approved_candidates(
        self, business_slug: str, production_session_id: int
    ) -> list[dict]:
        """Get all approved candidates for a session."""
        return self.list_candidates(
            business_slug, production_session_id, status="approved"
        )

    def is_approved(self, business_slug: str, candidate_id: int) -> bool:
        """Check if a candidate is currently approved (not superseded or stale)."""
        candidate = self.get_candidate(business_slug, candidate_id)
        return candidate["status"] == "approved"