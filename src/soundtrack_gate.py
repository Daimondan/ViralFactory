"""Persistent soundtrack preview gate (VF-VS-503).

Decisions are append-only and bind to the exact immutable soundtrack-plan hash.
Approval tokens are minted server-side; callers cannot supply them.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from datetime import datetime, timezone


class SoundtrackGateError(Exception):
    """Raised when the soundtrack gate rejects an action."""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS soundtrack_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    business_slug TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    mode TEXT NOT NULL,
    verdict TEXT NOT NULL,
    reason TEXT,
    gate_token TEXT,
    replacement_plan_hash TEXT,
    created_at TEXT NOT NULL,
    CHECK(verdict IN ('approved', 'rejected', 'replaced'))
);
CREATE INDEX IF NOT EXISTS idx_soundtrack_approvals_plan
    ON soundtrack_approvals(contract_id, plan_hash, id);
CREATE TABLE IF NOT EXISTS soundtrack_previews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    business_slug TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_soundtrack_previews_plan
    ON soundtrack_previews(contract_id, plan_hash, id);
"""


class SoundtrackPreviewGate:
    """Record operator decisions for exact immutable soundtrack plans."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            directory = os.path.dirname(db_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            existing = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'soundtrack_approvals'"
            ).fetchone()
            if existing and "UNIQUE(contract_id, plan_hash)" in (existing[0] or ""):
                with conn:
                    conn.execute(
                        "ALTER TABLE soundtrack_approvals "
                        "RENAME TO soundtrack_approvals_legacy"
                    )
                    conn.executescript(SCHEMA_SQL)
                    conn.execute(
                        """INSERT INTO soundtrack_approvals
                           (contract_id, business_slug, plan_hash, mode, verdict,
                            reason, gate_token, replacement_plan_hash, created_at)
                           SELECT contract_id, business_slug, plan_hash, mode, verdict,
                                  reason, gate_token, replacement_plan_hash, created_at
                           FROM soundtrack_approvals_legacy"""
                    )
                    conn.execute("DROP TABLE soundtrack_approvals_legacy")
            else:
                conn.executescript(SCHEMA_SQL)
                conn.commit()
        finally:
            conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _mint_gate_token() -> str:
        return "soundtrack_gate_" + secrets.token_urlsafe(24)

    def record_approval(
        self,
        contract_id: str,
        business_slug: str,
        plan_hash: str,
        mode: str,
        reason: str | None = None,
    ) -> dict:
        """Append explicit approval and mint its unforgeable server token."""
        gate_token = self._mint_gate_token()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO soundtrack_approvals
                   (contract_id, business_slug, plan_hash, mode, verdict,
                    reason, gate_token, created_at)
                   VALUES (?, ?, ?, ?, 'approved', ?, ?, ?)""",
                (
                    contract_id,
                    business_slug,
                    plan_hash,
                    mode,
                    reason,
                    gate_token,
                    self._now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "contract_id": contract_id,
            "plan_hash": plan_hash,
            "verdict": "approved",
            "gate_token": gate_token,
        }

    def record_preview(
        self,
        contract_id: str,
        business_slug: str,
        plan_hash: str,
    ) -> dict:
        """Append the operator's acknowledgement of hearing this exact plan."""
        created_at = self._now()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO soundtrack_previews
                   (contract_id, business_slug, plan_hash, created_at)
                   VALUES (?, ?, ?, ?)""",
                (contract_id, business_slug, plan_hash, created_at),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "contract_id": contract_id,
            "plan_hash": plan_hash,
            "created_at": created_at,
        }

    def was_previewed(self, contract_id: str, plan_hash: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                """SELECT 1 FROM soundtrack_previews
                   WHERE contract_id = ? AND plan_hash = ? LIMIT 1""",
                (contract_id, plan_hash),
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    def record_rejection(
        self,
        contract_id: str,
        business_slug: str,
        plan_hash: str,
        mode: str,
        reason: str,
    ) -> dict:
        """Append an operator rejection."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO soundtrack_approvals
                   (contract_id, business_slug, plan_hash, mode, verdict,
                    reason, gate_token, created_at)
                   VALUES (?, ?, ?, ?, 'rejected', ?, NULL, ?)""",
                (contract_id, business_slug, plan_hash, mode, reason, self._now()),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "contract_id": contract_id,
            "plan_hash": plan_hash,
            "verdict": "rejected",
            "reason": reason,
        }

    def record_replacement(
        self,
        contract_id: str,
        business_slug: str,
        original_plan_hash: str,
        replacement_plan_hash: str,
        mode: str,
        reason: str | None = None,
    ) -> dict:
        """Append the operator's exact persisted replacement selection."""
        gate_token = self._mint_gate_token()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """INSERT INTO soundtrack_approvals
                   (contract_id, business_slug, plan_hash, mode, verdict,
                    reason, gate_token, replacement_plan_hash, created_at)
                   VALUES (?, ?, ?, ?, 'replaced', ?, ?, ?, ?)""",
                (
                    contract_id,
                    business_slug,
                    original_plan_hash,
                    mode,
                    reason,
                    gate_token,
                    replacement_plan_hash,
                    self._now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "contract_id": contract_id,
            "original_plan_hash": original_plan_hash,
            "replacement_plan_hash": replacement_plan_hash,
            "verdict": "replaced",
            "gate_token": gate_token,
        }

    def get_approval(self, contract_id: str, plan_hash: str) -> dict | None:
        """Return the latest decision for an exact plan hash."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                """SELECT contract_id, plan_hash, mode, verdict, reason,
                          gate_token, replacement_plan_hash, created_at
                   FROM soundtrack_approvals
                   WHERE contract_id = ? AND plan_hash = ?
                   ORDER BY id DESC LIMIT 1""",
                (contract_id, plan_hash),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {
            "contract_id": row[0],
            "plan_hash": row[1],
            "mode": row[2],
            "verdict": row[3],
            "reason": row[4],
            "gate_token": row[5],
            "replacement_plan_hash": row[6],
            "created_at": row[7],
        }

    def is_approved(self, contract_id: str, plan_hash: str) -> bool:
        record = self.get_approval(contract_id, plan_hash)
        return bool(
            record
            and record["verdict"] == "approved"
            and record["gate_token"]
        )

    def require_approval(self, contract_id: str, plan_hash: str) -> dict:
        record = self.get_approval(contract_id, plan_hash)
        if record is None:
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} for contract {contract_id} "
                "has not been previewed or approved by the operator"
            )
        if record["verdict"] == "rejected":
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} was rejected by the operator: "
                f"{record['reason']}"
            )
        if record["verdict"] == "replaced":
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} was replaced — use the replacement plan"
            )
        if not record["gate_token"]:
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} has no gate token"
            )
        return record

    def build_preview_manifest(
        self,
        plan: dict,
        vo_file_path: str | None = None,
        bed_file_path: str | None = None,
        mixed_file_path: str | None = None,
        source_sound_file_path: str | None = None,
    ) -> dict:
        """Build the human listening manifest from a validated persisted plan."""
        mode = plan.get("mode", "")
        tracks: list[dict] = []
        if mode == "vo_only":
            tracks.append({
                "name": "vo_only",
                "file": vo_file_path,
                "description": "Voiceover only — no music or SFX.",
            })
            instructions = (
                "Listen to the complete VO and confirm that no music or SFX is "
                "intended. VO-only must be explicitly approved, not defaulted."
            )
        elif mode in ("music_bed", "vo_plus_bed"):
            tracks.extend([
                {
                    "name": "bed_alone",
                    "file": bed_file_path,
                    "description": "Proposed music bed alone.",
                },
                {
                    "name": "bed_under_vo",
                    "file": mixed_file_path,
                    "description": "Proposed bed ducked under the complete VO.",
                    "ducking": plan.get("ducking"),
                },
            ])
            instructions = (
                "Hear the bed alone, then under the VO, and confirm the voice remains clear."
            )
        elif mode == "vo_plus_sfx":
            tracks.append({
                "name": "vo_with_sfx_reference",
                "file": vo_file_path,
                "description": "Complete VO before representative SFX cues.",
            })
            instructions = (
                "Hear the complete VO and each representative SFX cue before deciding."
            )
        elif mode == "source_sound":
            tracks.append({
                "name": "source_sound",
                "file": source_sound_file_path,
                "description": "Selected source footage audio on its own.",
            })
            instructions = (
                "Hear the selected source audio and confirm that it carries the "
                "intended emotional and narrative weight."
            )
        else:
            instructions = "No valid soundtrack preview is available."

        for cue in plan.get("sfx_cues") or []:
            source = cue.get("source", "")
            synthetic = str(source).startswith("synth:")
            tracks.append({
                "name": f"sfx_{cue.get('event_id', '')}",
                "file": None if synthetic else source,
                "description": (
                    f"Representative SFX at {float(cue.get('timestamp', 0)):.1f}s — "
                    f"{cue.get('purpose', '')}"
                ),
                "source": source,
                "gain": cue.get("gain"),
                "synthetic_placeholder": synthetic,
                "finished_design": False if synthetic else None,
            })
        return {"mode": mode, "tracks": tracks, "instructions": instructions}
