"""Tests for the transcription worker's atomic claim mechanism (P0-3).

Verifies that two workers against one database with one pending material
invoke _transcribe exactly once — the second worker's claim returns False
and it skips the row.
"""

import os
import sys
import tempfile
import threading
import time
from unittest.mock import patch, MagicMock

import sqlite3
import pytest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))


@pytest.fixture
def temp_db():
    """Create a temporary database with a materials table and one pending audio row."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    upload_dir = tempfile.mkdtemp()

    # Create the materials table the same way MaterialStore does
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            material_type TEXT,
            normalized_content TEXT,
            transcription_status TEXT,
            word_count INTEGER,
            word_timestamps TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.execute(
        """INSERT INTO materials (filename, material_type, normalized_content, transcription_status)
           VALUES ('test_audio.mp3', 'audio', '[transcription pending]', 'pending')"""
    )
    conn.commit()
    conn.close()

    yield db_path, upload_dir

    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass
    import shutil
    shutil.rmtree(upload_dir, ignore_errors=True)


def test_claim_returns_true_on_first_call(temp_db):
    """_claim returns True the first time and False on every subsequent call for the same row."""
    from transcription import TranscriptionWorker

    db_path, upload_dir = temp_db
    worker = TranscriptionWorker(
        db_path=db_path,
        upload_dir=upload_dir,
        models_config={},
    )

    assert worker._claim(1) is True
    assert worker._claim(1) is False
    assert worker._claim(1) is False


def test_two_workers_transcribe_once(temp_db):
    """Two workers against one pending material invoke _transcribe exactly once."""
    from transcription import TranscriptionWorker

    db_path, upload_dir = temp_db
    # Place a dummy audio file so _find_audio_file succeeds
    audio_path = os.path.join(upload_dir, "material_1.mp3")
    with open(audio_path, "wb") as f:
        f.write(b"\x00" * 128)

    transcribe_calls = []
    call_lock = threading.Lock()

    def mock_transcribe(self, audio_path):
        with call_lock:
            transcribe_calls.append(audio_path)
        # Simulate some processing time so the race window is real
        time.sleep(0.2)
        return ("transcript text", 2, None)

    worker1 = TranscriptionWorker(db_path=db_path, upload_dir=upload_dir, models_config={})
    worker2 = TranscriptionWorker(db_path=db_path, upload_dir=upload_dir, models_config={})

    # Both workers see the pending row, then try to claim it
    pending1 = worker1._get_pending_audio()
    pending2 = worker2._get_pending_audio()

    assert len(pending1) == 1
    assert len(pending2) == 1
    assert pending1[0]["id"] == pending2[0]["id"]  # same row

    # Process concurrently with mocked _transcribe
    results = []
    threads = []

    def run_process(worker, material):
        with patch.object(TranscriptionWorker, "_transcribe", mock_transcribe):
            results.append(worker._process_one(material))

    t1 = threading.Thread(target=run_process, args=(worker1, pending1[0]))
    t2 = threading.Thread(target=run_process, args=(worker2, pending2[0]))

    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one worker should have transcribed
    assert len(transcribe_calls) == 1, f"Expected 1 transcribe call, got {len(transcribe_calls)}"
    # One worker returns True, the other False
    assert results.count(True) == 1
    assert results.count(False) == 1


def test_claim_returns_false_for_nonexistent_row(temp_db):
    """_claim returns False for a row that doesn't exist."""
    from transcription import TranscriptionWorker

    db_path, upload_dir = temp_db
    worker = TranscriptionWorker(db_path=db_path, upload_dir=upload_dir, models_config={})

    assert worker._claim(99999) is False