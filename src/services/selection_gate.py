"""
VF-RA-003 — Blind operator quality + operational selection gate.

Presents provider-anonymous A/B/C outputs for quality comparison.
Records actual cost, render latency, recovery behavior, and commercial
terms. The operator names a primary and fallback or rejects both.
No vendor becomes production default before this decision.

This is the data service for the blind selection gate. The actual
operator walkthrough happens in the UI — this service assembles the
anonymous outputs and records the decision.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS provider_selection_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    spec_hash TEXT NOT NULL,
    primary_provider TEXT,  -- NULL when rejected
    fallback_provider TEXT,
    decision TEXT NOT NULL,
    quality_observations_json TEXT,
    operational_facts_json TEXT,
    actor TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_selection_spec ON provider_selection_decisions(spec_hash);
CREATE INDEX IF NOT EXISTS idx_selection_business ON provider_selection_decisions(business_slug);
"""


class SelectionGateError(Exception):
    """Selection gate error."""
    pass


class BlindSelectionService:
    """Assembles provider-anonymous outputs for blind quality comparison.

    Provider identities are masked (A, B, C) so the operator judges
    quality without bias. Operational facts (cost, latency, recovery)
    are recorded but shown only after the decision.
    """

    ANONYMOUS_LABELS = ["A", "B", "C"]

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

    def build_blind_view(
        self,
        provider_jobs: list[dict],
    ) -> dict:
        """Build provider-anonymous A/B/C outputs for comparison.

        provider_jobs is a list of render_provider_jobs records from
        different providers, all rendering the same spec.

        Returns:
        {
            "outputs": [
                {
                    "label": "A",  # anonymous
                    "output_path": "...",
                    "output_hash": "...",
                    "render_time_s": ...,
                    # NO provider name — that's revealed after decision
                }
            ],
            "spec_hash": "...",
            "ready_for_decision": True/False,
        }
        """
        outputs = []
        for i, job in enumerate(provider_jobs):
            if job.get("status") not in ("done", "downloaded"):
                continue
            if not job.get("output_hash"):
                continue

            label = self.ANONYMOUS_LABELS[i] if i < len(self.ANONYMOUS_LABELS) else f"Provider_{i+1}"
            outputs.append({
                "label": label,
                "output_path": job.get("output_path", ""),
                "output_hash": job.get("output_hash", ""),
                "render_time_s": job.get("render_time_s"),
                # Provider name is NOT included — blind comparison
            })

        spec_hash = provider_jobs[0].get("spec_hash", "") if provider_jobs else ""

        return {
            "outputs": outputs,
            "spec_hash": spec_hash,
            "ready_for_decision": len(outputs) >= 2,  # need at least 2 for comparison
        }

    def record_decision(
        self,
        business_slug: str,
        spec_hash: str,
        primary_label: str,
        fallback_label: str = None,
        quality_observations: dict = None,
        operational_facts: dict = None,
        actor: str = "operator",
    ) -> dict:
        """Record the operator's blind selection decision.

        The labels (A, B, C) are mapped back to actual provider names
        by the caller — this service just records the decision.
        """
        if primary_label not in self.ANONYMOUS_LABELS:
            raise SelectionGateError(f"Invalid primary label: {primary_label}")

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO provider_selection_decisions
               (business_slug, spec_hash, primary_provider, fallback_provider,
                decision, quality_observations_json, operational_facts_json,
                actor, created_at)
               VALUES (?, ?, ?, ?, 'selected', ?, ?, ?, ?)""",
            (business_slug, spec_hash, primary_label, fallback_label,
             json.dumps(quality_observations, ensure_ascii=False) if quality_observations else None,
             json.dumps(operational_facts, ensure_ascii=False) if operational_facts else None,
             actor, ts),
        )
        decision_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT * FROM provider_selection_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def record_rejection(
        self,
        business_slug: str,
        spec_hash: str,
        reason: str,
        actor: str = "operator",
    ) -> dict:
        """Record that the operator rejected all providers."""
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO provider_selection_decisions
               (business_slug, spec_hash, primary_provider, fallback_provider,
                decision, quality_observations_json, actor, created_at)
               VALUES (?, ?, NULL, NULL, 'rejected', ?, ?, ?)""",
            (business_slug, spec_hash,
             json.dumps({"reason": reason}, ensure_ascii=False),
             actor, ts),
        )
        decision_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT * FROM provider_selection_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_latest_decision(
        self, business_slug: str, spec_hash: str
    ) -> Optional[dict]:
        """Get the latest selection decision for a spec."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM provider_selection_decisions
               WHERE business_slug = ? AND spec_hash = ?
               ORDER BY id DESC LIMIT 1""",
            (business_slug, spec_hash),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def has_selection(self, business_slug: str, spec_hash: str) -> bool:
        """Check if a selection has been made for this spec."""
        decision = self.get_latest_decision(business_slug, spec_hash)
        return decision is not None and decision["decision"] == "selected"