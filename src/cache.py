"""
ViralFactory — Content-Hash Cache

Deterministic caching by content hash. An unchanged input is never re-judged.
If the same prompt + variables + model have been seen before, return the cached result
instead of calling the LLM again.
"""

import hashlib
import json
import os
import sqlite3
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,       -- SHA-256 of (prompt_file + prompt_version + variables_hash + model)
    input_hash TEXT NOT NULL,          -- SHA-256 of the variables
    prompt_file TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    result TEXT NOT NULL,              -- validated JSON output
    created_at TEXT NOT NULL,
    hit_count INTEGER DEFAULT 0
);
"""


class ContentHashCache:
    """SQLite-backed cache for LLM calls, keyed by content hash."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @staticmethod
    def hash_variables(variables: dict) -> str:
        """SHA-256 hash of the input variables."""
        # Sort keys for deterministic hashing
        serialized = json.dumps(variables, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    @staticmethod
    def make_cache_key(
        prompt_file: str,
        prompt_version: str,
        variables_hash: str,
        model: str,
    ) -> str:
        """Build the full cache key from prompt + model + input."""
        key_str = f"{prompt_file}|{prompt_version}|{variables_hash}|{model}"
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(
        self,
        prompt_file: str,
        prompt_version: str,
        variables_hash: str,
        model: str,
    ) -> Optional[dict]:
        """Return cached result if present, else None."""
        key = self.make_cache_key(prompt_file, prompt_version, variables_hash, model)
        row = self.conn.execute(
            "SELECT result FROM llm_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
        if row:
            # Update hit count
            self.conn.execute(
                "UPDATE llm_cache SET hit_count = hit_count + 1 WHERE cache_key = ?",
                (key,),
            )
            self.conn.commit()
            return json.loads(row["result"])
        return None

    def put(
        self,
        prompt_file: str,
        prompt_version: str,
        variables_hash: str,
        model: str,
        result: dict,
    ):
        """Store a result in the cache."""
        from datetime import datetime, timezone
        key = self.make_cache_key(prompt_file, prompt_version, variables_hash, model)
        ts = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO llm_cache
               (cache_key, input_hash, prompt_file, prompt_version, model, result, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (key, variables_hash, prompt_file, prompt_version, model,
             json.dumps(result), ts),
        )
        self.conn.commit()

    def count(self) -> int:
        """Total cached entries."""
        return self.conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0]

    def close(self):
        self.conn.close()