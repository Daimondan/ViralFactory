"""
ViralFactory — Provenance Log

Every LLM call is logged to SQLite: input hash, prompt file + version, model,
raw output, validated output, validator verdict. This is the audit trail.

The provenance log is how trust works — you can always see what prompt, what model,
and what module versions produced any piece of content.
"""

import json
import sqlite3
import os
from datetime import datetime, timezone
from typing import Any, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS provenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- ISO 8601 UTC
    input_hash TEXT NOT NULL,          -- SHA-256 of the input variables
    prompt_file TEXT NOT NULL,         -- path to the prompt template
    prompt_version TEXT NOT NULL,     -- version string from the prompt file
    model TEXT NOT NULL,               -- model name from config
    provider TEXT NOT NULL,           -- provider name from config
    raw_output TEXT,                   -- raw LLM response
    validated_output TEXT,             -- validated JSON output (null if validation failed)
    validator_verdict TEXT NOT NULL,   -- 'valid', 'invalid', 'error'
    validator_errors TEXT,             -- error details if invalid
    context TEXT,                      -- human-readable context for the call
    temperature REAL,                  -- temperature used
    latency_ms INTEGER,                -- response time in milliseconds
    cached INTEGER DEFAULT 0           -- 1 if this was served from cache
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_provenance_input_hash ON provenance(input_hash);
CREATE INDEX IF NOT EXISTS idx_provenance_prompt_file ON provenance(prompt_file);
CREATE INDEX IF NOT EXISTS idx_provenance_verdict ON provenance(validator_verdict);
"""


class ProvenanceLog:
    """SQLite-backed provenance log for all LLM calls."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript(SCHEMA)
        self.conn.executescript(INDEX_SQL)
        self.conn.commit()

    def log(
        self,
        input_hash: str,
        prompt_file: str,
        prompt_version: str,
        model: str,
        provider: str,
        raw_output: str,
        validated_output: Optional[dict],
        validator_verdict: str,
        validator_errors: Optional[str] = None,
        context: str = "",
        temperature: float = 0.0,
        latency_ms: Optional[int] = None,
        cached: bool = False,
    ):
        """Write a provenance row for an LLM call."""
        ts = datetime.now(timezone.utc).isoformat()
        validated_json = json.dumps(validated_output) if validated_output else None

        self.conn.execute(
            """INSERT INTO provenance
               (timestamp, input_hash, prompt_file, prompt_version, model, provider,
                raw_output, validated_output, validator_verdict, validator_errors,
                context, temperature, latency_ms, cached)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (ts, input_hash, prompt_file, prompt_version, model, provider,
             raw_output, validated_json, validator_verdict, validator_errors,
             context, temperature, latency_ms, 1 if cached else 0),
        )
        self.conn.commit()

    def get_by_hash(self, input_hash: str) -> list[dict]:
        """Retrieve all provenance entries for a given input hash."""
        rows = self.conn.execute(
            "SELECT * FROM provenance WHERE input_hash = ? ORDER BY timestamp DESC",
            (input_hash,),
        ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        """Total number of provenance entries."""
        return self.conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0]

    def close(self):
        self.conn.close()