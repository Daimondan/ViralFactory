"""Tests for WAL mode and concurrent read/write safety (P0-4).

Verifies that the database is in WAL mode after create_app() and that
a long write transaction does not block a concurrent read.
"""

import os
import sys
import tempfile
import threading
import time
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))


@pytest.fixture
def fresh_app():
    """Create a fresh app with a temp database and return (app, db_path)."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    import app as app_module
    flask_app = app_module.create_app(db_path=db_path)

    yield flask_app, db_path

    # Cleanup
    for suffix in ["", "-wal", "-shm"]:
        try:
            os.unlink(db_path + suffix)
        except OSError:
            pass


def test_wal_mode_after_create_app(fresh_app):
    """PRAGMA journal_mode reports wal after create_app()."""
    _, db_path = fresh_app
    conn = sqlite3.connect(db_path)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()
    assert mode == "wal", f"Expected journal_mode=wal, got {mode}"


def test_concurrent_read_during_write(fresh_app):
    """A long write transaction must not block a concurrent read (WAL property)."""
    _, db_path = fresh_app

    # Create a test table and insert a row
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS wal_test (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO wal_test (val) VALUES ('initial')")
    conn.commit()
    conn.close()

    read_result = []
    read_error = []

    def do_read():
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            row = conn.execute("SELECT val FROM wal_test WHERE id = 1").fetchone()
            read_result.append(row[0] if row else None)
            conn.close()
        except Exception as e:
            read_error.append(str(e))

    # Start a long write transaction (hold it open for 1 second)
    writer = sqlite3.connect(db_path)
    writer.execute("BEGIN")
    writer.execute("INSERT INTO wal_test (val) VALUES ('writing')")

    # Launch the read thread while the write transaction is open
    thread = threading.Thread(target=do_read)
    thread.start()
    time.sleep(0.3)  # let the reader try while writer holds the transaction

    # Commit the write
    writer.commit()
    writer.close()

    thread.join(timeout=10)

    assert not read_error, f"Read failed: {read_error}"
    assert read_result == ["initial"], f"Read returned: {read_result}"
    # The read should have succeeded without waiting for the write to commit
    # (WAL allows readers to see the last committed state before the open write)