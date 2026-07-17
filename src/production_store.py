"""
Production Contract Store — additive storage and versioning (VF-AU-103).

Persists Production Contract v2 structures without destroying existing
drafts. Uses append-only history for contracts and performance records.

Tables:
  production_contracts — the current version of each contract
  production_contract_revisions — append-only history of contract changes
  performance_records — the latest performance/metrics record per contract
  performance_record_history — append-only metric capture history

Rules:
- Additive migration: new tables added alongside existing pipeline tables.
- No INSERT OR REPLACE on audit/provenance history.
- Repeated revisions preserve history.
- Tenant scoping via business_slug.
- Rollback-safe: failed writes do not corrupt existing data.
"""

import os
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


PRODUCTION_STORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS production_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    business_slug TEXT NOT NULL,
    draft_id INTEGER,
    version TEXT NOT NULL,
    writer_contract_hash TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(contract_id)
);

CREATE TABLE IF NOT EXISTS production_contract_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    business_slug TEXT NOT NULL,
    version TEXT NOT NULL,
    writer_contract_hash TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    revision_number INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS performance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    business_slug TEXT,
    platform_post_id TEXT,
    published_at TEXT,
    record_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(contract_id)
);

CREATE TABLE IF NOT EXISTS performance_record_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contract_id TEXT NOT NULL,
    record_json TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pc_business ON production_contracts(business_slug);
CREATE INDEX IF NOT EXISTS idx_pcr_contract ON production_contract_revisions(contract_id);
CREATE INDEX IF NOT EXISTS idx_pr_contract ON performance_records(contract_id);
CREATE INDEX IF NOT EXISTS idx_prh_contract ON performance_record_history(contract_id);
"""


class ProductionStore:
    """Data access for Production Contract v2 storage."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize tables additively — never destroy existing data."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript(PRODUCTION_STORE_SCHEMA)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ── Contract storage ──────────────────────────────────────────────────────

    def save_contract(self, business_slug: str, draft_id: int | None, contract: dict) -> None:
        """Save a contract, replacing the current version but preserving history.

        Uses INSERT OR REPLACE on the main table (one row per contract_id) but
        appends to production_contract_revisions for audit history.
        """
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        contract_json = json.dumps(contract, ensure_ascii=False, sort_keys=True)
        contract_id = contract.get("contract_id", "")
        version = contract.get("version", "2.0")
        writer_hash = contract.get("writer_contract_hash", "")

        # Get current revision number
        rev_row = conn.execute(
            "SELECT MAX(revision_number) FROM production_contract_revisions WHERE contract_id = ?",
            (contract_id,),
        ).fetchone()
        next_rev = (rev_row[0] or 0) + 1

        # Upsert current version
        conn.execute(
            """INSERT INTO production_contracts
               (contract_id, business_slug, draft_id, version, writer_contract_hash,
                contract_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(contract_id) DO UPDATE SET
                   business_slug = excluded.business_slug,
                   draft_id = excluded.draft_id,
                   version = excluded.version,
                   writer_contract_hash = excluded.writer_contract_hash,
                   contract_json = excluded.contract_json,
                   updated_at = excluded.updated_at""",
            (contract_id, business_slug, draft_id, version, writer_hash,
             contract_json, ts, ts),
        )

        # Append to history (always insert, never replace)
        conn.execute(
            """INSERT INTO production_contract_revisions
               (contract_id, business_slug, version, writer_contract_hash,
                contract_json, revision_number, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (contract_id, business_slug, version, writer_hash,
             contract_json, next_rev, ts),
        )

        conn.commit()
        conn.close()

    def get_contract(self, contract_id: str) -> dict | None:
        """Retrieve the current version of a contract by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM production_contracts WHERE contract_id = ?",
            (contract_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        contract = json.loads(row["contract_json"])
        contract["business_slug"] = row["business_slug"]
        contract["draft_id"] = row["draft_id"]
        return contract

    def get_contract_history(self, contract_id: str) -> list[dict]:
        """Retrieve append-only revision history for a contract."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM production_contract_revisions
               WHERE contract_id = ? ORDER BY revision_number""",
            (contract_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_contracts(self, business_slug: str) -> list[dict]:
        """List all contracts for a tenant."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM production_contracts WHERE business_slug = ? ORDER BY updated_at DESC",
            (business_slug,),
        ).fetchall()
        conn.close()
        return [
            {
                "contract_id": r["contract_id"],
                "business_slug": r["business_slug"],
                "draft_id": r["draft_id"],
                "version": r["version"],
                "updated_at": r["updated_at"],
            }
            for r in rows
        ]

    # ── Performance records ───────────────────────────────────────────────────

    def save_performance_record(self, contract_id: str, record: dict) -> None:
        """Save a performance record, replacing current but appending history."""
        conn = sqlite3.connect(self.db_path)
        ts = self._now()
        record_json = json.dumps(record, ensure_ascii=False, sort_keys=True)
        business_slug = record.get("business_slug", "")
        platform_post_id = record.get("platform_post_id", "")
        published_at = record.get("published_at", "")

        # Upsert current record
        conn.execute(
            """INSERT INTO performance_records
               (contract_id, business_slug, platform_post_id, published_at,
                record_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(contract_id) DO UPDATE SET
                   business_slug = excluded.business_slug,
                   platform_post_id = excluded.platform_post_id,
                   published_at = excluded.published_at,
                   record_json = excluded.record_json,
                   updated_at = excluded.updated_at""",
            (contract_id, business_slug, platform_post_id, published_at,
             record_json, ts, ts),
        )

        # Append to history
        conn.execute(
            """INSERT INTO performance_record_history
               (contract_id, record_json, captured_at)
               VALUES (?, ?, ?)""",
            (contract_id, record_json, ts),
        )

        conn.commit()
        conn.close()

    def get_performance_record(self, contract_id: str) -> dict | None:
        """Retrieve the current performance record for a contract."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM performance_records WHERE contract_id = ?",
            (contract_id,),
        ).fetchone()
        conn.close()

        if not row:
            return None

        return json.loads(row["record_json"])

    def get_performance_history(self, contract_id: str) -> list[dict]:
        """Retrieve append-only metric capture history for a contract."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT * FROM performance_record_history
               WHERE contract_id = ? ORDER BY captured_at""",
            (contract_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]