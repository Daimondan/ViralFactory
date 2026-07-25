"""Single connection factory for the ViralFactory SQLite database.

Every connection in the system should come from here. Direct sqlite3.connect
calls bypass busy_timeout and row_factory and are a defect.

Migration is one module per commit (P1-5). The ``migrated`` list in
``tests/test_db_factory_guard.py`` is the migration ledger — extend it in
the same commit that migrates each module.
"""

import sqlite3

BUSY_TIMEOUT_MS = 30_000


def connect(db_path: str, row_factory: bool = True) -> sqlite3.Connection:
    """Create a connection with busy_timeout, foreign_keys, and row_factory.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database file.
    row_factory : bool
        When True (default), sets ``conn.row_factory = sqlite3.Row`` so rows
        can be accessed by column name. Pass False only when a caller
        genuinely depends on tuple-style positional indexing — and leave a
        comment saying why.

    Returns
    -------
    sqlite3.Connection
    """
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys=ON")
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn