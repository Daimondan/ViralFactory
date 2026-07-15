"""
ViralFactory — Reference Asset Registry

Per CORRECTION-episode-format-and-reference-assets-v1.0 §2:
- Stores character refs, location refs, grade tokens, music beds, card styles
- Proposal → approve → retire lifecycle (no bulk approve — operator gates each)
- Approved payloads are locked; changes create a new version through the same gate
- Every generation call logs which registry IDs + versions it used (provenance)

The registry is the system of record for all recurring visual/audio identity assets.
The harness knows the schema; it never knows any tenant's character names or grade string.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS reference_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    kind TEXT NOT NULL,           -- 'character_ref' | 'location_ref' | 'music_bed' | 'grade_token' | 'card_style' | 'lockup_svg'
    name TEXT NOT NULL,           -- 'fitzroy', 'kitchen_dawn', 'bed_somber'
    status TEXT NOT NULL DEFAULT 'proposed',  -- 'proposed' | 'approved' | 'retired'
    payload_json TEXT NOT NULL,   -- kind-specific: file paths, prompt text, params
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT,
    approved_at TEXT,
    approved_by TEXT,
    notes TEXT                    -- operator notes / rationale
);

-- One asset name per kind per business; versions track changes over time
CREATE UNIQUE INDEX IF NOT EXISTS idx_ref_assets_unique
    ON reference_assets(business_slug, kind, name, version);

CREATE INDEX IF NOT EXISTS idx_ref_assets_business
    ON reference_assets(business_slug);
CREATE INDEX IF NOT EXISTS idx_ref_assets_kind
    ON reference_assets(kind);
CREATE INDEX IF NOT EXISTS idx_ref_assets_status
    ON reference_assets(status);
"""

# Valid asset kinds
VALID_KINDS = {
    "character_ref",   # 3-6 reference images + face/wardrobe canon text
    "location_ref",    # 1-2 establishing plates + prompt text
    "music_bed",       # audio file path, register, duration, source
    "grade_token",     # verbatim grade string injected into every image prompt
    "card_style",      # renderer parameters: font, palette, position, animation
    "lockup_svg",      # vector lockup sheets — brand identity graphics
}

VALID_STATUSES = {"proposed", "approved", "retired"}


class ReferenceAssetStore:
    """SQLite-backed reference asset registry with gate-disciplined lifecycle."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Query methods ──────────────────────────────────────────────

    def list_assets(
        self,
        business_slug: str,
        kind: Optional[str] = None,
        status: Optional[str] = None,
    ) -> list[dict]:
        """List reference assets, optionally filtered by kind and/or status."""
        sql = "SELECT * FROM reference_assets WHERE business_slug = ?"
        params: list = [business_slug]
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY kind ASC, name ASC, version DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_asset(self, asset_id: int) -> Optional[dict]:
        """Get a single asset by ID."""
        row = self.conn.execute(
            "SELECT * FROM reference_assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_approved(
        self, business_slug: str, kind: str, name: str
    ) -> Optional[dict]:
        """Get the latest approved version of a specific asset by kind + name."""
        row = self.conn.execute(
            """SELECT * FROM reference_assets
               WHERE business_slug = ? AND kind = ? AND name = ? AND status = 'approved'
               ORDER BY version DESC LIMIT 1""",
            (business_slug, kind, name),
        ).fetchone()
        return dict(row) if row else None

    def get_latest_version(
        self, business_slug: str, kind: str, name: str
    ) -> Optional[dict]:
        """Get the latest version of a specific asset regardless of status."""
        row = self.conn.execute(
            """SELECT * FROM reference_assets
               WHERE business_slug = ? AND kind = ? AND name = ?
               ORDER BY version DESC LIMIT 1""",
            (business_slug, kind, name),
        ).fetchone()
        return dict(row) if row else None

    def resolve_ref(self, business_slug: str, kind: str, name: str) -> Optional[dict]:
        """Resolve a reference (e.g. 'character_ref:fitzroy') to an approved asset.
        Returns None if no approved version exists — callers must handle this."""
        return self.get_approved(business_slug, kind, name)

    def get_grade_token(self, business_slug: str) -> Optional[str]:
        """Convenience: get the verbatim grade string for a business."""
        asset = self.get_approved(business_slug, "grade_token", "default")
        if not asset:
            return None
        payload = json.loads(asset["payload_json"])
        return payload.get("grade_string")

    # ── Mutation methods (all gated) ───────────────────────────────

    def propose(
        self,
        business_slug: str,
        kind: str,
        name: str,
        payload: dict,
        notes: str = "",
    ) -> dict:
        """Propose a new reference asset (status = 'proposed').
        If an approved version exists, the new proposal gets version = latest + 1."""
        if kind not in VALID_KINDS:
            raise ValueError(f"Invalid kind: {kind}. Must be one of {VALID_KINDS}")

        # Determine next version
        latest = self.get_latest_version(business_slug, kind, name)
        version = (latest["version"] + 1) if latest else 1

        now = self._now()
        cursor = self.conn.execute(
            """INSERT INTO reference_assets
               (business_slug, kind, name, status, payload_json, version,
                created_at, approved_at, approved_by, notes)
               VALUES (?, ?, ?, 'proposed', ?, ?, ?, NULL, NULL, ?)""",
            (
                business_slug,
                kind,
                name,
                json.dumps(payload, ensure_ascii=False),
                version,
                now,
                notes,
            ),
        )
        self.conn.commit()
        return self.get_asset(cursor.lastrowid)

    def approve(self, asset_id: int, approved_by: str = "operator") -> dict:
        """Approve a proposed asset. Locks the payload.
        Any previous approved version of the same kind+name is retired."""
        asset = self.get_asset(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        if asset["status"] != "proposed":
            raise ValueError(
                f"Asset {asset_id} is '{asset['status']}', can only approve 'proposed'"
            )

        now = self._now()

        # Retire any previously approved version of the same kind+name
        self.conn.execute(
            """UPDATE reference_assets SET status = 'retired'
               WHERE business_slug = ? AND kind = ? AND name = ?
               AND status = 'approved' AND id != ?""",
            (asset["business_slug"], asset["kind"], asset["name"], asset_id),
        )

        # Approve this version
        self.conn.execute(
            """UPDATE reference_assets
               SET status = 'approved', approved_at = ?, approved_by = ?
               WHERE id = ?""",
            (now, approved_by, asset_id),
        )
        self.conn.commit()
        return self.get_asset(asset_id)

    def retire(self, asset_id: int) -> dict:
        """Retire an approved asset. Does not delete — retired assets remain for provenance."""
        asset = self.get_asset(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        if asset["status"] != "approved":
            raise ValueError(
                f"Asset {asset_id} is '{asset['status']}', can only retire 'approved'"
            )

        self.conn.execute(
            "UPDATE reference_assets SET status = 'retired' WHERE id = ?",
            (asset_id,),
        )
        self.conn.commit()
        return self.get_asset(asset_id)

    def update_payload(self, asset_id: int, payload: dict, notes: str = "") -> dict:
        """Update the payload of a PROPOSED asset only.
        Approved assets are locked — must propose a new version to change."""
        asset = self.get_asset(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        if asset["status"] != "proposed":
            raise ValueError(
                f"Asset {asset_id} is '{asset['status']}' — approved assets are locked. "
                "Propose a new version to make changes."
            )

        self.conn.execute(
            "UPDATE reference_assets SET payload_json = ?, notes = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), notes, asset_id),
        )
        self.conn.commit()
        return self.get_asset(asset_id)

    def update_notes(self, asset_id: int, notes: str) -> dict:
        """Update notes on any asset (proposed or approved). Notes are not payload."""
        asset = self.get_asset(asset_id)
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")
        self.conn.execute(
            "UPDATE reference_assets SET notes = ? WHERE id = ?",
            (notes, asset_id),
        )
        self.conn.commit()
        return self.get_asset(asset_id)

    # ── File management ────────────────────────────────────────────

    @staticmethod
    def asset_dir(business_slug: str, kind: str, name: str, base: str = "data/media/reference") -> str:
        """Get the directory path for asset files."""
        return os.path.join(base, business_slug, kind, name)

    def list_asset_files(
        self, business_slug: str, kind: str, name: str, base: str = "data/media/reference"
    ) -> list[str]:
        """List files in an asset's directory."""
        d = self.asset_dir(business_slug, kind, name, base)
        if not os.path.isdir(d):
            return []
        return sorted(
            f for f in os.listdir(d)
            if not f.startswith(".") and os.path.isfile(os.path.join(d, f))
        )

    # ── Stats ──────────────────────────────────────────────────────

    def stats(self, business_slug: str) -> dict:
        """Get counts by kind and status for dashboard display."""
        rows = self.conn.execute(
            """SELECT kind, status, COUNT(*) as cnt
               FROM reference_assets WHERE business_slug = ?
               GROUP BY kind, status""",
            (business_slug,),
        ).fetchall()
        stats: dict[str, dict[str, int]] = {}
        for r in rows:
            kind = r["kind"]
            status = r["status"]
            if kind not in stats:
                stats[kind] = {}
            stats[kind][status] = r["cnt"]
        return stats

    def get_generation_context(self, business_slug: str) -> dict:
        """Get all approved reference assets formatted for content generation.

        Returns a dict with:
        - grade_string: the verbatim grade token (or None)
        - characters: {name: {face_canon, wardrobe_canon, files, ...}}
        - locations: {name: {prompt_text, files, ...}}
        - music_beds: {name: {file, register, duration, ...}}
        - card_styles: {name: {renderer params, ...}}
        - lockup_svgs: {name: {files, description, ...}}

        Only approved assets are included — proposed/retired assets are never
        used in content generation. This is the hard business rule: an unapproved
        asset is unusable by any generation path.
        """
        approved = self.list_assets(business_slug, status="approved")
        ctx: dict = {
            "grade_string": None,
            "characters": {},
            "locations": {},
            "music_beds": {},
            "card_styles": {},
            "lockup_svgs": {},
        }

        for asset in approved:
            payload = json.loads(asset["payload_json"])
            name = asset["name"]
            kind = asset["kind"]

            if kind == "grade_token":
                ctx["grade_string"] = payload.get("grade_string")
                ctx["grade_palette"] = payload.get("palette", {})
                ctx["tagline"] = payload.get("tagline", "")
            elif kind == "character_ref":
                ctx["characters"][name] = {
                    "name": payload.get("name", name),
                    "age": payload.get("age"),
                    "role": payload.get("role"),
                    "face_canon": payload.get("face_canon", ""),
                    "wardrobe_canon": payload.get("wardrobe_canon", ""),
                    "voice_register": payload.get("voice_register", ""),
                    "signature_props": payload.get("signature_props", []),
                    "files": payload.get("files", []),
                    "version": asset["version"],
                    "asset_id": asset["id"],
                }
            elif kind == "location_ref":
                ctx["locations"][name] = {
                    "prompt_text": payload.get("prompt_text", ""),
                    "files": payload.get("files", []),
                    "version": asset["version"],
                    "asset_id": asset["id"],
                }
            elif kind == "music_bed":
                ctx["music_beds"][name] = {
                    "file": payload.get("file", ""),
                    "register": payload.get("register", ""),
                    "duration": payload.get("duration", 0),
                    "source": payload.get("source", ""),
                    "version": asset["version"],
                    "asset_id": asset["id"],
                }
            elif kind == "card_style":
                ctx["card_styles"][name] = {
                    **payload,
                    "version": asset["version"],
                    "asset_id": asset["id"],
                }
            elif kind == "lockup_svg":
                ctx["lockup_svgs"][name] = {
                    "description": payload.get("description", ""),
                    "files": payload.get("files", []),
                    "usage": payload.get("usage", ""),
                    "version": asset["version"],
                    "asset_id": asset["id"],
                }

        return ctx

    def close(self):
        self.conn.close()