"""Durable job handoff for reel production.

HTTP handlers enqueue only. A systemd-managed worker performs the long VO,
provider polling, planning, and rendering preparation outside Gunicorn.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Callable

from jobs import JobsStore

JOB_TYPE = "reel_production"


def _set_result_ref(db_path: str, job_id: int, value: dict) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE jobs SET result_ref = ? WHERE id = ?",
        (json.dumps(value, ensure_ascii=False), job_id),
    )
    conn.commit()
    conn.close()


def enqueue_reel_job(db_path: str, asset_id: int, approved_cost_usd: float,
                     source_hash: str, stale_timeout_s: int) -> dict:
    """Create one idempotent long-running job for the approved Writer contract."""
    jobs = JobsStore(db_path)
    result = jobs.start_job(
        JOB_TYPE, asset_id, source_hash, stale_timeout_s=stale_timeout_s,
    )
    if result["status"] == "started":
        _set_result_ref(db_path, result["job_id"], {
            "approved_cost_usd": float(approved_cost_usd),
            "source_hash": source_hash,
        })
    return result


def get_reel_job_status(db_path: str, job_id: int) -> dict | None:
    """Return an operator-safe job status with parsed completion output."""
    job = JobsStore(db_path).get_job(job_id)
    if not job or job.get("job_type") != JOB_TYPE:
        return None
    response = {
        "job_id": job["id"],
        "asset_id": job["entity_id"],
        "status": job["status"],
        "error": job.get("error"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
    }
    if job["status"] == "done" and job.get("result_ref"):
        try:
            response["result"] = json.loads(job["result_ref"])
        except (TypeError, ValueError):
            response["result"] = {"status": "ok", "result_ref": job["result_ref"]}
    return response


def run_next_reel_job(db_path: str, runner: Callable[[int, float], dict]) -> bool:
    """Run the oldest queued reel job. Returns False when the queue is empty."""
    jobs = JobsStore(db_path)
    queued = list(reversed(jobs.list_jobs(job_type=JOB_TYPE, status="running", limit=50)))
    if not queued:
        return False
    job = queued[0]
    try:
        payload = json.loads(job.get("result_ref") or "{}")
        if "approved_cost_usd" not in payload:
            raise ValueError("Reel job is missing its approved cost payload")
        result = runner(job["entity_id"], float(payload["approved_cost_usd"]))
        jobs.complete_job(job["id"], json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        jobs.fail_job(job["id"], str(exc)[:2000])
    return True
