"""Regressions for long reel production running outside HTTP workers."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobs import JobsStore
from reel_jobs import enqueue_reel_job, get_reel_job_status, run_next_reel_job
from reel_production_runner import _find_submitted_video_tasks, _poll_video


def test_enqueue_returns_immediately_and_prevents_duplicate_work(tmp_path):
    db_path = str(tmp_path / "jobs.db")

    first = enqueue_reel_job(db_path, asset_id=6, approved_cost_usd=3.0,
                             source_hash="writer-hash", stale_timeout_s=14400)
    second = enqueue_reel_job(db_path, asset_id=6, approved_cost_usd=3.0,
                              source_hash="writer-hash", stale_timeout_s=14400)

    assert first["status"] == "started"
    assert second == {"status": "running", "job_id": first["job_id"],
                      "started_at": second["started_at"]}
    job = JobsStore(db_path).get_job(first["job_id"])
    assert json.loads(job["result_ref"]) == {
        "approved_cost_usd": 3.0,
        "source_hash": "writer-hash",
    }


def test_worker_completes_job_with_structured_result(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    queued = enqueue_reel_job(db_path, 6, 3.0, "writer-hash", 14400)
    calls = []

    def runner(asset_id, approved_cost_usd):
        calls.append((asset_id, approved_cost_usd))
        return {"status": "ok", "plan_id": 9, "vo_duration_seconds": 72.1}

    assert run_next_reel_job(db_path, runner) is True
    assert calls == [(6, 3.0)]
    status = get_reel_job_status(db_path, queued["job_id"])
    assert status["status"] == "done"
    assert status["result"]["plan_id"] == 9


def test_worker_records_failure_instead_of_leaving_running_job(tmp_path):
    db_path = str(tmp_path / "jobs.db")
    queued = enqueue_reel_job(db_path, 6, 3.0, "writer-hash", 14400)

    def fail_runner(asset_id, approved_cost_usd):
        raise RuntimeError("voice model ran out of memory")

    assert run_next_reel_job(db_path, fail_runner) is True
    status = get_reel_job_status(db_path, queued["job_id"])
    assert status["status"] == "failed"
    assert "voice model ran out of memory" in status["error"]


def test_assets_ui_polls_reel_job_instead_of_parsing_long_request():
    source = (ROOT / "src" / "templates" / "assets.html").read_text()

    assert "pollReelProductionJob(assetId, data.job_id" in source
    assert "'/api/reel-production-jobs/' + jobId" in source
    assert "data.status === 'queued' || data.status === 'running'" in source
    assert "response.text()" in source
    assert "JSON.parse" in source


def test_fal_poll_download_uses_adapter_contract():
    class Adapter:
        def check_video_job(self, external_job_id, provider=None, model=None):
            assert (external_job_id, provider, model) == ("task-1", "fal", "kling-3")
            return {"status": "completed", "download_url": "https://files/clip.mp4", "cost_usd": 0}

        def download_video(self, external_job_id, download_url, asset_id, model,
                           prompt, cost_usd=0, business_slug=None,
                           video_provider=None):
            assert external_job_id == "task-1"
            assert download_url == "https://files/clip.mp4"
            assert video_provider == "fal"
            assert cost_usd == 0.5
            return {"file_path": "clip.mp4", "media_id": 44}

    result = _poll_video(
        Adapter(), "task-1", 6, "kling-3", "move naturally",
        "stackpenni", "fal", 0.5,
    )
    assert result == {"path": "clip.mp4", "media_id": 44}


def test_submitted_provider_tasks_are_recovered_before_retrying_spend(tmp_path):
    import sqlite3
    db_path = str(tmp_path / "tasks.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE provenance (timestamp TEXT, context TEXT, validated_output TEXT)")
    conn.execute(
        "INSERT INTO provenance VALUES (?, ?, ?)",
        ("2026-07-18T01:00:00Z",
         "Approved storyboard animation b01 for asset 6 (submitted, ext_job=task-old)",
         json.dumps({"prompt": "old prompt"})),
    )
    conn.execute(
        "INSERT INTO provenance VALUES (?, ?, ?)",
        ("2026-07-18T02:00:00Z",
         "Approved storyboard animation b01 for asset 6 (submitted, ext_job=task-new)",
         json.dumps({"prompt": "approved motion"})),
    )
    conn.commit()
    conn.close()

    assert _find_submitted_video_tasks(db_path, 6) == {
        "b01": {"external_job_id": "task-new", "prompt": "approved motion"},
    }
