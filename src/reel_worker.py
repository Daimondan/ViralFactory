#!/usr/bin/env python3
"""Systemd worker for long-running reel production jobs."""

from __future__ import annotations

import os
import signal
import time

from config_loader import load_all
from reel_jobs import run_next_reel_job
from reel_production_runner import run_reel_production

_running = True


def _stop(_signum, _frame):
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    root = os.environ.get("VIRALFACTORY_ROOT", os.getcwd())
    db_path = os.environ.get("VIRALFACTORY_DB", os.path.join(root, "data", "viralfactory.db"))
    config_dir = os.environ.get("VIRALFACTORY_CONFIG", os.path.join(root, "config"))
    config = load_all(config_dir)
    business_slug = config["business"]["business"]["slug"]
    worker_config = config["models"].get("media", {}).get("reel_production", {})

    # Ensure WAL mode is set before any DB access (P0-4).
    import sqlite3 as _sqlite3_init
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    _wal_conn = _sqlite3_init.connect(db_path)
    try:
        _wal_conn.execute("PRAGMA journal_mode=WAL")
        _wal_conn.execute("PRAGMA synchronous=NORMAL")
    finally:
        _wal_conn.close()
    poll_seconds = float(worker_config.get("worker_poll_seconds", 2))

    def runner(asset_id: int, approved_cost_usd: float) -> dict:
        print(f"[reel-worker] starting asset {asset_id}", flush=True)
        result = run_reel_production(
            asset_id, approved_cost_usd,
            db_path=db_path,
            config_dir=config_dir,
            business_slug=business_slug,
            modules_dir=os.path.join(root, "modules"),
            prompts_dir=os.path.join(root, "prompts"),
        )
        print(f"[reel-worker] completed asset {asset_id}", flush=True)
        return result

    print("[reel-worker] ready", flush=True)
    while _running:
        worked = run_next_reel_job(db_path, runner)
        if not worked:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    main()
