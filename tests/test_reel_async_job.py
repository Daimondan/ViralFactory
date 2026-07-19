"""Regressions for long reel production running outside HTTP workers."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jobs import JobsStore
from reel_jobs import enqueue_reel_job, get_reel_job_status, run_next_reel_job
from reel_production import ReelProductionError
from reel_production_runner import (
    _find_submitted_video_tasks,
    _poll_video,
    run_reel_production,
)


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


def test_assets_ui_has_no_retired_reel_job_polling():
    source = (ROOT / "src" / "templates" / "assets.html").read_text()

    assert "pollReelProductionJob" not in source
    assert "'/api/reel-production-jobs/' + jobId" not in source
    assert "pollRenderStatus(assetId, btn, statusElem)" in source


def test_legacy_vo_led_runner_is_retired_before_any_pipeline_work(monkeypatch, tmp_path):
    import reel_production_runner

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("legacy state and provider setup must not run")

    monkeypatch.setattr(reel_production_runner, "_state", fail_if_called)

    with pytest.raises(ReelProductionError, match="retired"):
        run_reel_production(
            6,
            0,
            db_path=str(tmp_path / "pipeline.db"),
            config_dir="config",
            business_slug="fixture",
        )


def test_operator_route_does_not_enqueue_the_retired_vo_led_path(tmp_path):
    from app import create_app
    from pipeline import PipelineStore

    db_path = str(tmp_path / "pipeline.db")
    app = create_app(config_dir=str(ROOT / "config"), db_path=db_path)
    store = PipelineStore(db_path=db_path)
    asset_id = store.create_asset(
        "fixture",
        1,
        "Instagram",
        "reel",
        "Approved content",
        posts=[{
            "beat_id": "b01",
            "vo_text": "Approved voice-over.",
            "text_on_screen": {"text": "Approved overlay"},
            "visual_intent": "A renderer-owned card.",
        }],
    )

    response = app.test_client().post(
        f"/api/assets/{asset_id}/produce-reel",
        json={"approved_cost_usd": 0},
    )

    assert response.status_code == 409
    assert "retired" in response.get_json()["error"].lower()
    assert JobsStore(db_path).list_jobs(job_type="reel_production") == []


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
