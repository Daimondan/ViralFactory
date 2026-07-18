import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from transcription import TranscriptionWorker


class FailingConnection:
    def __init__(self):
        self.closed = False
        self.row_factory = None

    def execute(self, *_args, **_kwargs):
        raise sqlite3.OperationalError("forced query failure")

    def close(self):
        self.closed = True


def make_worker():
    return TranscriptionWorker(
        db_path="unused.db",
        upload_dir="unused",
        models_config={"transcription": {"enabled": True}},
    )


def test_pending_query_closes_connection_after_database_error(monkeypatch):
    connection = FailingConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda _path: connection)

    with pytest.raises(sqlite3.OperationalError, match="forced query failure"):
        make_worker()._get_pending_audio()

    assert connection.closed


def test_backfill_query_closes_connection_after_database_error(monkeypatch):
    connection = FailingConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda _path: connection)

    with pytest.raises(sqlite3.OperationalError, match="forced query failure"):
        make_worker()._backfill()

    assert connection.closed


def test_material_update_closes_connection_after_database_error(monkeypatch):
    connection = FailingConnection()
    monkeypatch.setattr(sqlite3, "connect", lambda _path: connection)

    with pytest.raises(sqlite3.OperationalError, match="forced query failure"):
        make_worker()._update_material(1, "processing")

    assert connection.closed


def test_app_factory_can_disable_process_background_workers(monkeypatch, tmp_path):
    from app import create_app

    monkeypatch.setenv("VIRALFACTORY_DISABLE_BACKGROUND_WORKERS", "1")
    app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
    worker = app.config.get("TRANSCRIPTION_WORKER")
    if worker is not None:
        worker.stop()

    assert worker is None
