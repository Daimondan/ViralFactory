"""
ViralFactory — Jobs Table

Shared infrastructure for idempotency and async job tracking.

Per CORRECTION-pipeline-ux-and-media-generation-v1.0 F1:
- Every expensive endpoint (draft generate, fan-out, onboarding message, analyze,
  media generation, rendering, VO) is guarded against duplicate concurrent calls.
- A request arriving while a matching job is 'running' returns HTTP 409 with
  the running job's status — no second LLM/media call fires.
- Stale 'running' jobs older than a timeout are treated as dead and may be retried.
- This table is the same substrate the media/VO/render workers use for async jobs.

Job lifecycle:
  running → done | failed | dead

job_key is derived from endpoint + entity id (+ input hash where inputs vary).
"""

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_key TEXT NOT NULL,              -- derived from endpoint + entity_id + input_hash
    job_type TEXT NOT NULL,             -- draft_generate | fan_out | media_image | media_video | assembly_render | vo | analyze
    entity_id INTEGER,                  -- the entity this job operates on (draft_id, asset_id, card_id, etc.)
    status TEXT NOT NULL DEFAULT 'running',  -- running | done | failed | dead
    result_ref TEXT,                    -- reference to the result (file path, JSON string, etc.)
    error TEXT,                          -- error message if failed
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    -- VF-CW-001: Correlation fields for production observability
    business_slug TEXT,                 -- tenant scope for multi-tenant isolation
    production_session_id INTEGER,      -- links to production_sessions table (VF-CW-002)
    draft_id INTEGER,                   -- explicit draft correlation
    asset_id INTEGER,                   -- explicit asset correlation
    state TEXT,                         -- production state at job start
    attempt INTEGER DEFAULT 1,          -- retry attempt number
    upstream_hash TEXT                  -- hash of upstream inputs for lineage
);

CREATE INDEX IF NOT EXISTS idx_jobs_key ON jobs(job_key);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_entity ON jobs(entity_id);
CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(production_session_id);
CREATE INDEX IF NOT EXISTS idx_jobs_business ON jobs(business_slug);
"""


# Stale-job timeout: a running job older than this is considered dead.
# Render/VO jobs can take minutes, so we set a generous default.
# Per-job-type overrides can be passed to is_stale().
DEFAULT_STALE_TIMEOUT_S = 600  # 10 minutes


class JobsStore:
    """SQLite-backed job tracking and idempotency guard."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        # Create table if not exists (original columns only for new DBs)
        # Then run migrations to add correlation columns to existing tables
        # before creating indexes that reference them
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT NOT NULL,
                job_type TEXT NOT NULL,
                entity_id INTEGER,
                status TEXT NOT NULL DEFAULT 'running',
                result_ref TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                created_at TEXT NOT NULL
            );
        """)
        # VF-CW-001: Idempotent migration — add correlation columns
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        migration_cols = {
            "business_slug": "TEXT",
            "production_session_id": "INTEGER",
            "draft_id": "INTEGER",
            "asset_id": "INTEGER",
            "state": "TEXT",
            "attempt": "INTEGER DEFAULT 1",
            "upstream_hash": "TEXT",
        }
        for col, coltype in migration_cols.items():
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {coltype}")
        # Create all indexes (safe now — all columns exist)
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_jobs_key ON jobs(job_key);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
            CREATE INDEX IF NOT EXISTS idx_jobs_entity ON jobs(entity_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_session ON jobs(production_session_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_business ON jobs(business_slug);
        """)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def make_job_key(job_type: str, entity_id: int = None, input_hash: str = None) -> str:
        """Build a job key from type + entity + optional input hash."""
        parts = [job_type]
        if entity_id is not None:
            parts.append(str(entity_id))
        if input_hash:
            parts.append(input_hash[:16])  # truncate hash for key brevity
        return "|".join(parts)

    def start_job(
        self,
        job_type: str,
        entity_id: int = None,
        input_hash: str = None,
        stale_timeout_s: int = DEFAULT_STALE_TIMEOUT_S,
        business_slug: str = None,
        production_session_id: int = None,
        draft_id: int = None,
        asset_id: int = None,
        state: str = None,
        attempt: int = 1,
        upstream_hash: str = None,
    ) -> dict:
        """
        Attempt to start a job. Returns one of:
          - {"status": "started", "job_id": N} — a new job was started; proceed with the work
          - {"status": "running", "job_id": N, "started_at": ...} — a matching job is already
            running; do NOT fire a second call. The caller should return HTTP 409.
          - {"status": "done", "job_id": N, "result_ref": ...} — a matching job already
            completed. The caller can return the cached result.

        Stale 'running' jobs older than stale_timeout_s are marked 'dead' and the
        new job is started.

        VF-CW-001: Correlation fields (business_slug, production_session_id,
        draft_id, asset_id, state, attempt, upstream_hash) are persisted for
        production observability and lineage tracking.
        """
        job_key = self.make_job_key(job_type, entity_id, input_hash)
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # Check for an existing job with this key
        existing = conn.execute(
            "SELECT * FROM jobs WHERE job_key = ? ORDER BY id DESC LIMIT 1",
            (job_key,),
        ).fetchone()

        if existing:
            existing = dict(existing)
            if existing["status"] == "running":
                # Check if stale
                started_at = existing["started_at"]
                if self._is_stale(started_at, stale_timeout_s):
                    # Mark as dead, start a new job
                    conn.execute(
                        "UPDATE jobs SET status = 'dead', completed_at = ? WHERE id = ?",
                        (ts, existing["id"]),
                    )
                    conn.commit()
                else:
                    conn.close()
                    return {
                        "status": "running",
                        "job_id": existing["id"],
                        "started_at": started_at,
                    }
            # 'done', 'failed', 'dead' → allow a new attempt (content-hash cache handles dedup)

        # Start a new job
        cursor = conn.execute(
            """INSERT INTO jobs (job_key, job_type, entity_id, status, started_at, created_at,
                                  business_slug, production_session_id, draft_id, asset_id,
                                  state, attempt, upstream_hash)
               VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_key, job_type, entity_id, ts, ts,
             business_slug, production_session_id, draft_id, asset_id,
             state, attempt, upstream_hash),
        )
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"status": "started", "job_id": job_id}

    def complete_job(self, job_id: int, result_ref: str = None):
        """Mark a job as done with an optional result reference."""
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE jobs SET status = 'done', result_ref = ?, completed_at = ? WHERE id = ?",
            (result_ref, ts, job_id),
        )
        conn.commit()
        conn.close()

    def fail_job(self, job_id: int, error: str = ""):
        """Mark a job as failed with an error message."""
        ts = self._now()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE jobs SET status = 'failed', error = ?, completed_at = ? WHERE id = ?",
            (error, ts, job_id),
        )
        conn.commit()
        conn.close()

    def get_job(self, job_id: int) -> Optional[dict]:
        """Get a single job by ID."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_job_by_key(self, job_key: str) -> Optional[dict]:
        """Get the most recent job with a given key."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_key = ? ORDER BY id DESC LIMIT 1",
            (job_key,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_jobs(
        self,
        job_type: str = None,
        status: str = None,
        entity_id: int = None,
        limit: int = 50,
    ) -> list[dict]:
        """List jobs, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM jobs WHERE 1=1"
        params = []
        if job_type:
            query += " AND job_type = ?"
            params.append(job_type)
        if status:
            query += " AND status = ?"
            params.append(status)
        if entity_id is not None:
            query += " AND entity_id = ?"
            params.append(entity_id)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def cleanup_stale(self, stale_timeout_s: int = DEFAULT_STALE_TIMEOUT_S) -> int:
        """Mark all stale 'running' jobs as 'dead'. Returns count of cleaned jobs."""
        ts = self._now()
        cutoff = datetime.now(timezone.utc).timestamp() - stale_timeout_s
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        running = conn.execute(
            "SELECT * FROM jobs WHERE status = 'running'"
        ).fetchall()
        count = 0
        for row in running:
            row = dict(row)
            if self._is_stale(row["started_at"], stale_timeout_s):
                conn.execute(
                    "UPDATE jobs SET status = 'dead', completed_at = ? WHERE id = ?",
                    (ts, row["id"]),
                )
                count += 1
        conn.commit()
        conn.close()
        return count

    @staticmethod
    def _is_stale(started_at_iso: str, stale_timeout_s: int) -> bool:
        """Check if a job's started_at timestamp is older than the timeout."""
        try:
            started = datetime.fromisoformat(started_at_iso)
            elapsed = (datetime.now(timezone.utc) - started).total_seconds()
            return elapsed > stale_timeout_s
        except (ValueError, TypeError):
            return True  # bad timestamp = treat as stale
