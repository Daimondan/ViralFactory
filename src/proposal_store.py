"""
ViralFactory — Proposal Store (M5: T5.1 + T5.2)

The async gate queue for module improvement proposals.
Proposals accumulate with visible age, pending counter, approve/reject,
and superseding (newer proposal on the same module section marks the older
superseded — visible, not deleted).

Tables:
  proposals — the async gate queue (weekly AI proposals for module updates)
  proposal_decisions — operator approve/reject decisions

Per AMENDMENT-005: proposal targets include the process registry alongside
the eight modules. Gate queue handles mapping proposals identically.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional


PROPOSAL_SCHEMA = {
    "type": "object",
    "required": ["target_module", "target_section", "proposal_type", "evidence",
                 "change_description", "exact_diff", "rationale"],
    "properties": {
        "target_module": {
            "type": "string",
            "description": "Module name: voice-profile, viral-patterns, story-frameworks, "
                           "format-guide, audience-insights, visual-style, source-bank, "
                           "feedback-log, or process-registry (per AMENDMENT-005)"
        },
        "target_section": {
            "type": "string",
            "description": "Specific section within the module (e.g. 'patterns[2]', "
                           "'affordances', 'criteria')"
        },
        "proposal_type": {
            "type": "string",
            "enum": ["add", "modify", "remove", "status_change", "mapping_change"],
            "description": "Type of proposed change"
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Concrete evidence: feedback log entries, performance data, "
                           "engagement metrics — never vibes"
        },
        "change_description": {
            "type": "string",
            "description": "Plain-language description of what changes"
        },
        "exact_diff": {
            "type": "string",
            "description": "Exact diff: what text to add/remove/replace, with context. "
                           "Must be specific enough to apply mechanically."
        },
        "rationale": {
            "type": "string",
            "description": "Why this change improves content quality or voice accuracy"
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "How confident the AI is in this proposal"
        }
    }
}


class ProposalStore:
    """Async gate queue for module improvement proposals."""

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS proposals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_slug TEXT NOT NULL,
        target_module TEXT NOT NULL,
        target_section TEXT NOT NULL,
        proposal_type TEXT NOT NULL,
        evidence TEXT NOT NULL,
        change_description TEXT NOT NULL,
        exact_diff TEXT NOT NULL,
        rationale TEXT NOT NULL,
        confidence TEXT DEFAULT 'medium',
        status TEXT NOT NULL DEFAULT 'pending',
        superseded_by INTEGER,
        reject_reason TEXT,
        provenance_id INTEGER,
        created_at TEXT NOT NULL,
        decided_at TEXT,
        FOREIGN KEY (superseded_by) REFERENCES proposals(id)
    );
    CREATE INDEX IF NOT EXISTS idx_proposals_business ON proposals(business_slug);
    CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
    CREATE INDEX IF NOT EXISTS idx_proposals_module ON proposals(target_module);
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        self._ensure_tables()

    def _ensure_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(self.SCHEMA_SQL)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_proposal(
        self,
        business_slug: str,
        target_module: str,
        target_section: str,
        proposal_type: str,
        evidence: list[str],
        change_description: str,
        exact_diff: str,
        rationale: str,
        confidence: str = "medium",
        provenance_id: int = None,
    ) -> int:
        """Create a new proposal. Automatically supersedes older pending proposals
        on the same module+section."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()

        # Check for existing pending proposals on the same module+section
        existing = conn.execute(
            """SELECT id FROM proposals
               WHERE business_slug = ? AND target_module = ? AND target_section = ?
               AND status = 'pending'""",
            (business_slug, target_module, target_section),
        ).fetchall()

        cursor = conn.execute(
            """INSERT INTO proposals
               (business_slug, target_module, target_section, proposal_type,
                evidence, change_description, exact_diff, rationale,
                confidence, status, provenance_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
            (business_slug, target_module, target_section, proposal_type,
             json.dumps(evidence), change_description, exact_diff, rationale,
             confidence, provenance_id, ts),
        )
        proposal_id = cursor.lastrowid

        # Supersede older proposals on the same module+section
        for row in existing:
            old_id = row[0]
            conn.execute(
                "UPDATE proposals SET status = 'superseded', superseded_by = ? WHERE id = ?",
                (proposal_id, old_id),
            )

        conn.commit()
        conn.close()
        return proposal_id

    def get_proposal(self, proposal_id: int) -> Optional[dict]:
        """Get a single proposal by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        d["evidence_parsed"] = json.loads(d.get("evidence") or "[]")
        return d

    def list_proposals(
        self,
        business_slug: str,
        status: str = None,
        target_module: str = None,
    ) -> list[dict]:
        """List proposals, optionally filtered by status or module."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM proposals WHERE business_slug = ?"
        params = [business_slug]
        if status:
            query += " AND status = ?"
            params.append(status)
        if target_module:
            query += " AND target_module = ?"
            params.append(target_module)
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        results = []
        for row in rows:
            d = dict(row)
            d["evidence_parsed"] = json.loads(d.get("evidence") or "[]")
            results.append(d)
        return results

    def get_pending_count(self, business_slug: str) -> int:
        """Count pending proposals across all types."""
        conn = sqlite3.connect(self.db_path)
        count = conn.execute(
            "SELECT COUNT(*) FROM proposals WHERE business_slug = ? AND status = 'pending'",
            (business_slug,),
        ).fetchone()[0]
        conn.close()
        return count

    def get_proposal_age_days(self, created_at: str) -> int:
        """Calculate age in days from created_at to now."""
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            return (now - created).days
        except (ValueError, AttributeError):
            return 0

    def approve_proposal(self, proposal_id: int, applied_by: str = "operator") -> dict:
        """Approve a proposal. Status → 'approved'. The actual module update
        is applied by the caller (version bump via ModuleStore)."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE proposals SET status = 'approved', decided_at = ? WHERE id = ?",
            (ts, proposal_id),
        )
        conn.commit()
        conn.close()
        return self.get_proposal(proposal_id)

    def reject_proposal(self, proposal_id: int, reason: str) -> dict:
        """Reject a proposal with a quick-reason."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            "UPDATE proposals SET status = 'rejected', reject_reason = ?, decided_at = ? WHERE id = ?",
            (reason, ts, proposal_id),
        )
        conn.commit()
        conn.close()
        return self.get_proposal(proposal_id)

    def bulk_approve(self, proposal_ids: list[int]) -> list[dict]:
        """Bulk approve multiple proposals (for low-risk proposals)."""
        results = []
        for pid in proposal_ids:
            results.append(self.approve_proposal(pid))
        return results

    def bulk_reject(self, proposal_ids: list[int], reason: str) -> list[dict]:
        """Bulk reject multiple proposals."""
        results = []
        for pid in proposal_ids:
            results.append(self.reject_proposal(pid, reason))
        return results

    def get_superseded_chain(self, proposal_id: int) -> list[dict]:
        """Get the chain of proposals superseded by this one."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM proposals WHERE superseded_by = ? ORDER BY id ASC",
            (proposal_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_proposal_summary(self, business_slug: str) -> dict:
        """Get summary stats for the gate queue dashboard."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        pending = conn.execute(
            "SELECT COUNT(*) as c FROM proposals WHERE business_slug = ? AND status = 'pending'",
            (business_slug,),
        ).fetchone()["c"]

        approved = conn.execute(
            "SELECT COUNT(*) as c FROM proposals WHERE business_slug = ? AND status = 'approved'",
            (business_slug,),
        ).fetchone()["c"]

        rejected = conn.execute(
            "SELECT COUNT(*) as c FROM proposals WHERE business_slug = ? AND status = 'rejected'",
            (business_slug,),
        ).fetchone()["c"]

        superseded = conn.execute(
            "SELECT COUNT(*) as c FROM proposals WHERE business_slug = ? AND status = 'superseded'",
            (business_slug,),
        ).fetchone()["c"]

        # Pending by module
        by_module = conn.execute(
            """SELECT target_module, COUNT(*) as c FROM proposals
               WHERE business_slug = ? AND status = 'pending'
               GROUP BY target_module""",
            (business_slug,),
        ).fetchall()

        # Oldest pending
        oldest = conn.execute(
            """SELECT created_at FROM proposals
               WHERE business_slug = ? AND status = 'pending'
               ORDER BY created_at ASC LIMIT 1""",
            (business_slug,),
        ).fetchone()

        conn.close()

        return {
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "superseded": superseded,
            "by_module": {r["target_module"]: r["c"] for r in by_module},
            "oldest_pending_age_days": self.get_proposal_age_days(oldest["created_at"]) if oldest else 0,
        }