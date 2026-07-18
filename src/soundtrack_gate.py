"""Soundtrack preview gate (VF-VS-503, AMENDMENT-010 Condition 4).

The operator hears the proposed bed and representative SFX separately and
under the VO before approval. VO-only delivery is explicitly approved, not
defaulted. No soundtrack mode change without a gate token.

This module provides the gate logic — it does NOT render audio. It manages
the approval state and enforces the business rule: no music/SFX acquisition
until the operator approves the soundtrack plan.

The actual UI route renders preview audio (bed alone, SFX alone, bed under VO)
and calls this gate to record the operator's decision.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


class SoundtrackGateError(Exception):
    """Raised when the soundtrack gate rejects an action."""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS soundtrack_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    business_slug TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    mode TEXT NOT NULL,
    verdict TEXT NOT NULL,  -- approved | rejected | replaced
    reason TEXT,
    gate_token TEXT,
    replacement_plan_hash TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(contract_id, plan_hash)
);
"""


class SoundtrackPreviewGate:
    """Manages soundtrack plan approval state.

    The gate is a persistent record: every decision (approve, reject, replace)
    is logged with the plan hash so the system can prove the operator saw and
    approved the specific plan before any music/SFX was acquired.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_approval(
        self,
        contract_id: str,
        business_slug: str,
        plan_hash: str,
        mode: str,
        gate_token: str,
        reason: str | None = None,
    ) -> dict:
        """Record that the operator approved the soundtrack plan.

        The gate_token is the operator's explicit approval. Once recorded,
        the plan's `operator_approval` field is set to this token.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            """INSERT OR REPLACE INTO soundtrack_approvals
               (contract_id, business_slug, plan_hash, mode, verdict, reason, gate_token, created_at)
               VALUES (?, ?, ?, ?, 'approved', ?, ?, ?)""",
            (contract_id, business_slug, plan_hash, mode, reason, gate_token, ts),
        )
        conn.commit()
        conn.close()
        return {
            "contract_id": contract_id,
            "plan_hash": plan_hash,
            "verdict": "approved",
            "gate_token": gate_token,
        }

    def record_rejection(
        self,
        contract_id: str,
        business_slug: str,
        plan_hash: str,
        mode: str,
        reason: str,
    ) -> dict:
        """Record that the operator rejected the soundtrack plan."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            """INSERT OR REPLACE INTO soundtrack_approvals
               (contract_id, business_slug, plan_hash, mode, verdict, reason, gate_token, created_at)
               VALUES (?, ?, ?, ?, 'rejected', ?, NULL, ?)""",
            (contract_id, business_slug, plan_hash, mode, reason, ts),
        )
        conn.commit()
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
        gate_token: str,
        reason: str | None = None,
    ) -> dict:
        """Record that the operator replaced the plan with a new one."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        conn.execute(
            """INSERT OR REPLACE INTO soundtrack_approvals
               (contract_id, business_slug, plan_hash, mode, verdict, reason, gate_token, replacement_plan_hash, created_at)
               VALUES (?, ?, ?, ?, 'replaced', ?, ?, ?, ?)""",
            (contract_id, business_slug, original_plan_hash, mode, reason, gate_token, replacement_plan_hash, ts),
        )
        conn.commit()
        conn.close()
        return {
            "contract_id": contract_id,
            "original_plan_hash": original_plan_hash,
            "replacement_plan_hash": replacement_plan_hash,
            "verdict": "replaced",
            "gate_token": gate_token,
        }

    def get_approval(self, contract_id: str, plan_hash: str) -> dict | None:
        """Get the approval record for a specific plan."""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            """SELECT contract_id, plan_hash, mode, verdict, reason, gate_token, replacement_plan_hash, created_at
               FROM soundtrack_approvals WHERE contract_id = ? AND plan_hash = ?""",
            (contract_id, plan_hash),
        ).fetchone()
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
        """True if the plan has an approval record with a gate token."""
        record = self.get_approval(contract_id, plan_hash)
        return record is not None and record["verdict"] == "approved" and record["gate_token"] is not None

    def require_approval(self, contract_id: str, plan_hash: str) -> dict:
        """Raise if the plan is not approved. Returns the approval record if it is."""
        record = self.get_approval(contract_id, plan_hash)
        if record is None:
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} for contract {contract_id} "
                f"has not been previewed or approved by the operator"
            )
        if record["verdict"] == "rejected":
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} was rejected by the operator: {record['reason']}"
            )
        if record["verdict"] == "replaced":
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} was replaced — use the replacement plan instead"
            )
        if not record["gate_token"]:
            raise SoundtrackGateError(
                f"Soundtrack plan {plan_hash[:12]} has no gate token — approval incomplete"
            )
        return record

    def build_preview_manifest(
        self,
        plan: dict,
        vo_file_path: str | None = None,
        bed_file_path: str | None = None,
    ) -> dict:
        """Build a manifest of what the operator should hear in the preview.

        The preview has three listening modes:
        1. Bed alone (if music_bed) — the operator hears the bed without VO.
        2. SFX alone — the operator hears each SFX cue in isolation.
        3. Bed under VO (if music_bed) — the operator hears the ducked bed under the VO.

        For vo_only, the preview is the VO alone — the operator explicitly
        approves that no music/SFX is needed.
        """
        mode = plan.get("mode", "")
        sfx_cues = plan.get("sfx_cues") or []

        manifest = {
            "mode": mode,
            "tracks": [],
            "instructions": "",
        }

        if mode == "vo_only":
            manifest["tracks"].append({
                "name": "vo_only",
                "file": vo_file_path,
                "description": "Voiceover only — no music, no SFX. The operator must explicitly approve this as the intended soundtrack.",
            })
            manifest["instructions"] = (
                "This piece is proposed as VO-only. Listen to the VO and confirm "
                "that no music or SFX is needed. VO-only is explicitly approved, "
                "not defaulted."
            )
        elif mode in ("music_bed", "vo_plus_bed"):
            manifest["tracks"].append({
                "name": "bed_alone",
                "file": bed_file_path,
                "description": "Music bed alone — hear the bed without VO.",
            })
            manifest["tracks"].append({
                "name": "bed_under_vo",
                "file": None,  # mixed preview rendered separately
                "description": "Music bed ducked under VO — hear how the bed sits beneath the voice.",
                "vo_file": vo_file_path,
                "bed_file": bed_file_path,
                "ducking": plan.get("ducking"),
            })
            manifest["instructions"] = (
                "Listen to the bed alone first, then the bed under the VO. "
                "Confirm the ducking keeps the VO intelligible. Then review SFX."
            )
        elif mode == "source_sound":
            manifest["tracks"].append({
                "name": "source_sound",
                "file": vo_file_path,
                "description": "Source media original audio — the on-location sound is the primary audio.",
            })
            manifest["instructions"] = (
                "This piece uses source sound. Listen and confirm the ambient "
                "audio is the intended primary audio."
            )

        # SFX tracks — each cue in isolation
        for cue in sfx_cues:
            manifest["tracks"].append({
                "name": f"sfx_{cue.get('event_id', '')}",
                "file": None,  # synthesized preview
                "description": f"SFX cue '{cue.get('event_id', '')}' at {cue.get('timestamp', 0):.1f}s — {cue.get('purpose', '')}",
                "source": cue.get("source", ""),
                "gain": cue.get("gain", 0.5),
            })

        return manifest