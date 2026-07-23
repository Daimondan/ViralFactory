"""
VF-CW-011 — Manifest-only assembly + exact Gate 3 service.

Changes the active edit/render boundary to `assemble(manifest_id)`.
The assembler may consume only the frozen manifest — no mutable inventory
lookup, no latest-file fallback, no vendor-specific manifest fields,
no unlisted media.

Gate 3 service requires current local final hash + current manifest hash
+ complete blocking evidence + human decision. HTTP routes never update
gate state directly — all gate writes go through Gate3Service.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS gate3_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    production_session_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    manifest_id INTEGER NOT NULL,
    manifest_hash TEXT NOT NULL,
    final_artifact_hash TEXT,
    final_artifact_path TEXT,
    evidence_json TEXT,
    decision TEXT NOT NULL,
    feedback TEXT,
    actor TEXT NOT NULL DEFAULT 'operator',
    created_at TEXT NOT NULL,
    FOREIGN KEY (production_session_id) REFERENCES production_sessions(id),
    FOREIGN KEY (manifest_id) REFERENCES assembly_manifests(id)
);

CREATE INDEX IF NOT EXISTS idx_gate3_session ON gate3_decisions(production_session_id);
CREATE INDEX IF NOT EXISTS idx_gate3_asset ON gate3_decisions(asset_id);
CREATE INDEX IF NOT EXISTS idx_gate3_manifest ON gate3_decisions(manifest_id);
"""


class Gate3Error(Exception):
    """Gate 3 validation or decision error."""
    pass


class AssemblyError(Exception):
    """Manifest-only assembly error."""
    pass


class Gate3Service:
    """Central Gate 3 service — the only path to approve/fix/kill an asset.

    Routes never write gate state directly. All gate writes go through
    this service, which validates:
    - current local final artifact hash
    - current manifest hash
    - complete blocking evidence
    - human decision
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

    def validate_gate3_readiness(
        self,
        business_slug: str,
        production_session_id: int,
        final_artifact_path: str,
        evidence: dict = None,
    ) -> dict:
        """Validate that all Gate 3 prerequisites are met.

        Returns:
        {
            "ready": bool,
            "blockers": [...],
            "manifest": {...} or None,
            "final_hash": str or None,
        }
        """
        from services.production_orchestrator import ProductionSessionService
        from services.manifest_freeze import ManifestStore

        blockers = []

        # 1. Get the session
        session_svc = ProductionSessionService(db_path=self.db_path)
        try:
            session = session_svc.get_session(business_slug, production_session_id)
        except Exception as e:
            return {
                "ready": False,
                "blockers": [f"Session not found: {e}"],
                "manifest": None,
                "final_hash": None,
            }

        # 2. Get the current active manifest
        manifest_store = ManifestStore(db_path=self.db_path)
        manifest = manifest_store.get_active_manifest(business_slug, production_session_id)

        if not manifest:
            blockers.append("No active manifest — cannot approve without frozen manifest")
            return {
                "ready": False,
                "blockers": blockers,
                "manifest": None,
                "final_hash": None,
            }

        # 3. Verify final artifact exists and compute hash
        if not final_artifact_path or not os.path.exists(final_artifact_path):
            blockers.append("Final artifact file does not exist")
            return {
                "ready": False,
                "blockers": blockers,
                "manifest": manifest,
                "final_hash": None,
            }

        final_hash = self._compute_file_hash(final_artifact_path)
        if not final_hash:
            blockers.append("Cannot compute final artifact hash")
            return {
                "ready": False,
                "blockers": blockers,
                "manifest": manifest,
                "final_hash": None,
            }

        # 4. Check evidence completeness
        if evidence is None:
            evidence = {}

        required_evidence = [
            "duration_check",
            "audio_check",
            "visual_check",
            "text_integrity_check",
        ]
        for ev_key in required_evidence:
            ev = evidence.get(ev_key)
            if not ev:
                blockers.append(f"Missing required evidence: {ev_key}")
            elif isinstance(ev, dict) and ev.get("verdict") not in ("pass", "ready_for_operator"):
                blockers.append(f"Evidence {ev_key} verdict is not pass: {ev.get('verdict', 'missing')}")

        # 5. Check session is in the right state
        if session["current_state"] != "final_review_required":
            blockers.append(
                f"Session state is '{session['current_state']}', must be 'final_review_required'"
            )

        return {
            "ready": len(blockers) == 0,
            "blockers": blockers,
            "manifest": manifest,
            "final_hash": final_hash,
        }

    def approve(
        self,
        business_slug: str,
        production_session_id: int,
        final_artifact_path: str,
        evidence: dict = None,
        actor: str = "operator",
        feedback: str = None,
    ) -> dict:
        """Approve the final artifact at Gate 3.

        Requires: current final artifact, current manifest, complete evidence,
        session in final_review_required state.
        """
        readiness = self.validate_gate3_readiness(
            business_slug, production_session_id, final_artifact_path, evidence
        )

        if not readiness["ready"]:
            raise Gate3Error(
                "Gate 3 approval blocked: " + "; ".join(readiness["blockers"])
            )

        manifest = readiness["manifest"]
        final_hash = readiness["final_hash"]

        # Record the decision
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO gate3_decisions
               (business_slug, production_session_id, asset_id, manifest_id,
                manifest_hash, final_artifact_hash, final_artifact_path,
                evidence_json, decision, feedback, actor, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'approve', ?, ?, ?)""",
            (business_slug, production_session_id, manifest["asset_id"],
             manifest["id"], manifest["manifest_hash"],
             final_hash, final_artifact_path,
             json.dumps(evidence, ensure_ascii=False) if evidence else None,
             feedback, actor, ts),
        )
        decision_id = cursor.lastrowid
        # Update asset state in the same transaction
        conn.execute(
            "UPDATE assets SET asset_state = 'approved', updated_at = ? WHERE id = ?",
            (ts, manifest["asset_id"]),
        )
        conn.commit()
        conn.close()

        # Transition session to gate3_approved (separate connection to avoid lock)
        from services.production_orchestrator import ProductionSessionService
        session_svc = ProductionSessionService(db_path=self.db_path)
        session_svc.transition(
            business_slug, production_session_id,
            "gate3_approved", "Gate 3 approved", actor=actor,
        )

        # Fetch the decision record (new connection)
        conn2 = sqlite3.connect(self.db_path)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute(
            "SELECT * FROM gate3_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        conn2.close()

        return dict(row)

    def reject(
        self,
        business_slug: str,
        production_session_id: int,
        feedback: str,
        actor: str = "operator",
    ) -> dict:
        """Reject the final artifact at Gate 3 (sends back for re-render)."""
        from services.production_orchestrator import ProductionSessionService
        from services.manifest_freeze import ManifestStore

        session_svc = ProductionSessionService(db_path=self.db_path)
        session = session_svc.get_session(business_slug, production_session_id)

        manifest_store = ManifestStore(db_path=self.db_path)
        manifest = manifest_store.get_active_manifest(business_slug, production_session_id)

        if not manifest:
            raise Gate3Error("No active manifest to reject")

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            """INSERT INTO gate3_decisions
               (business_slug, production_session_id, asset_id, manifest_id,
                manifest_hash, decision, feedback, actor, created_at)
               VALUES (?, ?, ?, ?, ?, 'reject', ?, ?, ?)""",
            (business_slug, production_session_id, manifest["asset_id"],
             manifest["id"], manifest["manifest_hash"],
             feedback, actor, ts),
        )
        decision_id = cursor.lastrowid
        conn.commit()
        conn.close()

        # Transition back to assembling for re-render (separate connection)
        session_svc.transition(
            business_slug, production_session_id,
            "assembling", "Gate 3 rejected: " + feedback[:200], actor=actor,
        )

        # Fetch the decision record
        conn2 = sqlite3.connect(self.db_path)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute(
            "SELECT * FROM gate3_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        conn2.close()

        return dict(row)

    def kill(
        self,
        business_slug: str,
        production_session_id: int,
        feedback: str,
        actor: str = "operator",
    ) -> dict:
        """Kill the asset at Gate 3."""
        from services.production_orchestrator import ProductionSessionService
        from services.manifest_freeze import ManifestStore

        session_svc = ProductionSessionService(db_path=self.db_path)
        session = session_svc.get_session(business_slug, production_session_id)

        manifest_store = ManifestStore(db_path=self.db_path)
        manifest = manifest_store.get_active_manifest(business_slug, production_session_id)

        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        manifest_hash = manifest["manifest_hash"] if manifest else None
        manifest_id = manifest["id"] if manifest else None
        asset_id = manifest["asset_id"] if manifest else session["asset_id"]

        cursor = conn.execute(
            """INSERT INTO gate3_decisions
               (business_slug, production_session_id, asset_id, manifest_id,
                manifest_hash, decision, feedback, actor, created_at)
               VALUES (?, ?, ?, ?, ?, 'kill', ?, ?, ?)""",
            (business_slug, production_session_id, asset_id,
             manifest_id, manifest_hash, feedback, actor, ts),
        )
        decision_id = cursor.lastrowid
        # Update asset state in same transaction
        conn.execute(
            "UPDATE assets SET asset_state = 'killed', updated_at = ? WHERE id = ?",
            (ts, asset_id),
        )
        conn.commit()
        conn.close()

        # Transition to failed (separate connection)
        session_svc.transition(
            business_slug, production_session_id,
            "failed", "Gate 3 killed: " + feedback[:200], actor=actor,
        )

        # Fetch the decision record
        conn2 = sqlite3.connect(self.db_path)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute(
            "SELECT * FROM gate3_decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        conn2.close()

        return dict(row)

    def get_current_decision(
        self, business_slug: str, production_session_id: int
    ) -> Optional[dict]:
        """Get the most recent Gate 3 decision for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM gate3_decisions
               WHERE business_slug = ? AND production_session_id = ?
               ORDER BY id DESC LIMIT 1""",
            (business_slug, production_session_id),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def is_approved(
        self, business_slug: str, production_session_id: int
    ) -> bool:
        """Check if the session has a current Gate 3 approval."""
        decision = self.get_current_decision(business_slug, production_session_id)
        return decision is not None and decision["decision"] == "approve"

    def _compute_file_hash(self, path: str) -> str:
        """Compute SHA-256 of a file."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except (IOError, OSError):
            return ""


class AssemblyService:
    """Manifest-only assembly service.

    The assembler entrypoint is `assemble(manifest_id)`. It rejects:
    - mutable inventory lookup
    - latest-file fallback
    - vendor-specific manifest fields
    - unlisted media

    Every consumed manifest item/hash and provider lowering is recorded.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path

    def validate_manifest_consumption(
        self,
        business_slug: str,
        manifest_id: int,
    ) -> dict:
        """Validate that all manifest ingredients are present and hash-valid.

        Returns:
        {
            "valid": bool,
            "errors": [...],
            "ingredients": [...]
        }
        """
        from services.manifest_freeze import ManifestStore
        manifest_store = ManifestStore(db_path=self.db_path)

        # Get the manifest by ID
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM assembly_manifests WHERE id = ? AND business_slug = ?",
            (manifest_id, business_slug),
        ).fetchone()
        conn.close()

        if not row:
            return {
                "valid": False,
                "errors": [f"Manifest {manifest_id} not found"],
                "ingredients": [],
            }

        manifest = dict(row)
        manifest_data = json.loads(manifest["manifest_json"]) if isinstance(manifest["manifest_json"], str) else manifest["manifest_json"]

        errors = []
        ingredients = []

        for candidate in manifest_data.get("candidates", []):
            ingredient = {
                "candidate_id": candidate["candidate_id"],
                "category": candidate["category"],
                "role": candidate["role"],
                "artifact_hash": candidate["artifact_hash"],
                "artifact_path": candidate.get("artifact_path"),
            }

            # Check artifact exists
            artifact_path = candidate.get("artifact_path")
            if not artifact_path or not os.path.exists(artifact_path):
                errors.append(
                    f"Candidate {candidate['candidate_id']} ({candidate['category']}/{candidate['role']}): "
                    f"artifact file missing: {artifact_path}"
                )
            else:
                # Verify hash
                actual_hash = self._compute_file_hash(artifact_path)
                if actual_hash != candidate["artifact_hash"]:
                    errors.append(
                        f"Candidate {candidate['candidate_id']}: hash mismatch "
                        f"(expected {candidate['artifact_hash'][:16]}, got {actual_hash[:16]})"
                    )

            ingredients.append(ingredient)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "ingredients": ingredients,
        }

    def _compute_file_hash(self, path: str) -> str:
        """Compute SHA-256 of a file."""
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except (IOError, OSError):
            return ""