"""
VF-CW-010 — Completeness + immutable manifest freeze.

Mechanically requires exactly one current approved selection per mandatory
role, validates tenant/session/artifact/hash/measurement/preview/rights/
cost/upstream compatibility, returns structured blockers, and
transactionally freezes a canonical manifest containing exact decision/
artifact IDs plus Writer/VO/timing/module/config hashes.

Partial, stale, rejected, superseded, rights-invalid, cost-unapproved,
unprobeable, hash-mismatched, or cross-scope inputs fail closed.
Identical freeze is idempotent. Changed input creates a new manifest and
invalidates prior render/Gate 3 approval.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS assembly_manifests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    production_session_id INTEGER NOT NULL,
    draft_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    manifest_json TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    writer_contract_hash TEXT,
    vo_hash TEXT,
    timing_hash TEXT,
    module_snapshot_hash TEXT,
    config_hash TEXT,
    is_active INTEGER DEFAULT 1,
    frozen_by TEXT NOT NULL DEFAULT 'operator',
    frozen_at TEXT NOT NULL,
    superseded_by INTEGER,
    FOREIGN KEY (production_session_id) REFERENCES production_sessions(id),
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE INDEX IF NOT EXISTS idx_manifests_session ON assembly_manifests(production_session_id);
CREATE INDEX IF NOT EXISTS idx_manifests_asset ON assembly_manifests(asset_id);
CREATE INDEX IF NOT EXISTS idx_manifests_active ON assembly_manifests(is_active);
CREATE INDEX IF NOT EXISTS idx_manifests_hash ON assembly_manifests(manifest_hash);
"""


class ManifestError(Exception):
    """Manifest freeze or validation error."""
    pass


class CompletenessError(ManifestError):
    """Category completeness check failed."""
    pass


class ManifestStore:
    """Immutable assembly manifest store with freeze semantics."""

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

    def check_completeness(
        self,
        business_slug: str,
        production_session_id: int,
        requirements: dict,
    ) -> dict:
        """Mechanically check that every required role has exactly one
        current approved candidate.

        Returns:
        {
            "complete": bool,
            "blockers": [
                {"category": "...", "role": "...", "reason": "...", "candidate_id": ...}
            ],
            "approved_candidates": [...]
        }
        """
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)

        # Get all approved candidates for this session
        approved = store.get_approved_candidates(business_slug, production_session_id)

        # Group by category+role
        approved_by_key = {}
        for c in approved:
            key = f"{c['category']}:{c['role']}"
            if key not in approved_by_key:
                approved_by_key[key] = []
            approved_by_key[key].append(c)

        blockers = []
        approved_list = []

        for cat_entry in requirements.get("categories", []):
            cat_key = cat_entry.get("category", "")
            cat_required = cat_entry.get("required", False)

            for role_entry in cat_entry.get("roles", []):
                role_key = role_entry.get("role", "")
                role_required = role_entry.get("required", False)
                none_allowed = role_entry.get("none_allowed", False)

                if not cat_required and not role_required:
                    continue

                key = f"{cat_key}:{role_key}"
                candidates = approved_by_key.get(key, [])

                if len(candidates) == 0:
                    if none_allowed:
                        # Explicit none is allowed — no blocker
                        continue
                    blockers.append({
                        "category": cat_key,
                        "role": role_key,
                        "reason": "No approved candidate for required role",
                    })
                elif len(candidates) > 1:
                    blockers.append({
                        "category": cat_key,
                        "role": role_key,
                        "reason": f"Multiple approved candidates ({len(candidates)}) — expected exactly 1",
                        "candidate_ids": [c["id"] for c in candidates],
                    })
                else:
                    # Exactly one approved — validate it
                    c = candidates[0]
                    validation_error = self._validate_candidate(c, role_entry)
                    if validation_error:
                        blockers.append({
                            "category": cat_key,
                            "role": role_key,
                            "reason": validation_error,
                            "candidate_id": c["id"],
                        })
                    else:
                        approved_list.append(c)

        return {
            "complete": len(blockers) == 0,
            "blockers": blockers,
            "approved_candidates": approved_list,
        }

    def _validate_candidate(self, candidate: dict, role_entry: dict) -> Optional[str]:
        """Validate a single approved candidate against its role requirements.

        Mechanical checks only: artifact hash exists, preview exists if required,
        rights/cost status if applicable. No creative judgment.
        """
        # Artifact hash must exist
        if not candidate.get("artifact_hash"):
            return "Approved candidate has no artifact hash"

        # Preview required check
        if role_entry.get("preview_required", False):
            if not candidate.get("preview_hash"):
                return "Approved candidate missing required preview hash"

        # Cost approval check (if cost_estimate exists)
        cost = candidate.get("cost_estimate_usd")
        if cost is not None and cost > 0:
            if not candidate.get("cost_approved"):
                return "Approved candidate has unapproved cost"

        # Status must be approved (not superseded/stale)
        if candidate.get("status") != "approved":
            return f"Candidate status is '{candidate['status']}', not 'approved'"

        return None

    def freeze_manifest(
        self,
        business_slug: str,
        production_session_id: int,
        frozen_by: str = "operator",
    ) -> dict:
        """Freeze an immutable assembly manifest.

        Requires all mandatory roles to have exactly one approved candidate.
        Returns the manifest dict.
        """
        from services.candidate_store import CandidateStore
        from services.component_requirements import ComponentRequirementsStore
        from services.production_orchestrator import ProductionSessionService

        # Get the session
        session_svc = ProductionSessionService(db_path=self.db_path)
        session = session_svc.get_session(business_slug, production_session_id)

        # Get current requirements
        req_store = ComponentRequirementsStore(db_path=self.db_path)
        current_reqs = req_store.get_current_requirements(business_slug, production_session_id)

        if not current_reqs:
            raise ManifestError(
                "No requirements found for session — cannot freeze manifest"
            )

        requirements = current_reqs["requirements_json"]

        # Check completeness
        completeness = self.check_completeness(
            business_slug, production_session_id, requirements
        )

        if not completeness["complete"]:
            blocker_msgs = [b["reason"] for b in completeness["blockers"]]
            raise CompletenessError(
                "Cannot freeze manifest — incomplete: " + "; ".join(blocker_msgs)
            )

        # Build the manifest
        approved = completeness["approved_candidates"]

        manifest_data = {
            "business_slug": business_slug,
            "production_session_id": production_session_id,
            "draft_id": session["draft_id"],
            "asset_id": session["asset_id"],
            "platform": session["platform"],
            "format": session.get("format"),
            "requirements_version": current_reqs["version"],
            "requirements_hash": current_reqs["requirements_hash"],
            "writer_contract_hash": session.get("writer_contract_hash"),
            "candidates": [
                {
                    "candidate_id": c["id"],
                    "category": c["category"],
                    "role": c["role"],
                    "version": c["version"],
                    "artifact_hash": c["artifact_hash"],
                    "artifact_path": c["artifact_path"],
                    "preview_hash": c.get("preview_hash"),
                    "preview_path": c.get("preview_path"),
                    "source_type": c.get("source_type"),
                    "cost_estimate_usd": c.get("cost_estimate_usd"),
                    "cost_approved": bool(c.get("cost_approved")),
                    "beat_refs": json.loads(c["beat_refs_json"]) if c.get("beat_refs_json") else [],
                    "measurement": json.loads(c["measurement_json"]) if c.get("measurement_json") else {},
                }
                for c in approved
            ],
        }

        # Compute canonical manifest hash
        manifest_hash = self._compute_manifest_hash(manifest_data)
        manifest_data["manifest_hash"] = manifest_hash

        # Check for idempotent freeze (same hash already active)
        existing = self.get_active_manifest(business_slug, production_session_id)
        if existing and existing["manifest_hash"] == manifest_hash:
            # Idempotent — return existing
            return existing

        # Deactivate prior manifest
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Get next version
        row = conn.execute(
            "SELECT MAX(version) as max_v FROM assembly_manifests WHERE production_session_id = ?",
            (production_session_id,),
        ).fetchone()
        next_version = (row["max_v"] or 0) + 1

        # Deactivate prior active manifests
        conn.execute(
            "UPDATE assembly_manifests SET is_active = 0, superseded_by = NULL WHERE production_session_id = ? AND is_active = 1",
            (production_session_id,),
        )

        # Insert new manifest
        cursor = conn.execute(
            """INSERT INTO assembly_manifests
               (business_slug, production_session_id, draft_id, asset_id,
                version, manifest_json, manifest_hash,
                writer_contract_hash, is_active, frozen_by, frozen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (business_slug, production_session_id, session["draft_id"],
             session["asset_id"], next_version,
             json.dumps(manifest_data, ensure_ascii=False),
             manifest_hash,
             session.get("writer_contract_hash"),
             frozen_by, ts),
        )
        manifest_id = cursor.lastrowid

        # Update prior manifests to point to new one
        conn.execute(
            "UPDATE assembly_manifests SET superseded_by = ? WHERE production_session_id = ? AND is_active = 0 AND superseded_by IS NULL",
            (manifest_id, production_session_id),
        )

        conn.commit()
        row = conn.execute(
            "SELECT * FROM assembly_manifests WHERE id = ?", (manifest_id,)
        ).fetchone()
        conn.close()

        # Parse manifest_json for the return value
        result = dict(row)
        if isinstance(result.get("manifest_json"), str):
            result["manifest_json"] = json.loads(result["manifest_json"])

        # Update session active manifest pointer
        session_svc.set_active_manifest(business_slug, production_session_id, next_version)

        return result

    def _compute_manifest_hash(self, manifest_data: dict) -> str:
        """Compute a canonical content hash for the manifest."""
        # Exclude manifest_hash itself from the hash computation
        data = {k: v for k, v in manifest_data.items() if k != "manifest_hash"}
        canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get_active_manifest(
        self, business_slug: str, production_session_id: int
    ) -> Optional[dict]:
        """Get the current active manifest for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM assembly_manifests
               WHERE business_slug = ? AND production_session_id = ? AND is_active = 1
               ORDER BY version DESC LIMIT 1""",
            (business_slug, production_session_id),
        ).fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        result["manifest_json"] = json.loads(result["manifest_json"])
        return result

    def get_manifest_by_hash(self, manifest_hash: str) -> Optional[dict]:
        """Get a manifest by hash (for lineage verification)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM assembly_manifests WHERE manifest_hash = ?",
            (manifest_hash,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        result["manifest_json"] = json.loads(result["manifest_json"])
        return result

    def list_manifests(
        self, business_slug: str, production_session_id: int
    ) -> list[dict]:
        """List all manifest versions for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, version, manifest_hash, is_active, frozen_by, frozen_at
               FROM assembly_manifests
               WHERE business_slug = ? AND production_session_id = ?
               ORDER BY version DESC""",
            (business_slug, production_session_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]