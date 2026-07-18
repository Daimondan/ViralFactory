"""Legacy VO-first Reel helpers retained for safe recovery and compatibility."""

from __future__ import annotations

import json
import re
import sqlite3
import time

from config_loader import load_all
from media_adapter import MediaAdapter
from pipeline import PipelineStore
from reel_production import (
    ReelProductionError,
    estimate_motion,
    extract_reel_beats,
)


def _state(asset_id: int, db_path: str, config_dir: str):
    store = PipelineStore(db_path=db_path)
    asset = store.get_asset(asset_id)
    if not asset:
        raise ReelProductionError("Asset not found")
    beats = extract_reel_beats(json.loads(asset.get("posts") or "[]"))
    if not beats or not any(beat.get("vo_text") for beat in beats):
        raise ReelProductionError("This asset has no structured spoken Reel beats.")

    models_config = load_all(config_dir)["models"]
    adapter = MediaAdapter(models_config, db_path=db_path)
    media = adapter.list_asset_media(asset_id, owner_type="asset")

    generated_paths = json.loads(asset.get("generated_images") or "[]")
    images_by_path = {row.get("path"): row for row in media if row.get("kind") == "image"}
    conn = sqlite3.connect(db_path)
    for beat, path in zip(beats, generated_paths):
        row = images_by_path.get(path)
        if row and not row.get("beat_id"):
            conn.execute("UPDATE asset_media SET beat_id = ? WHERE id = ?", (beat["beat_id"], row["id"]))
    conn.commit()
    conn.close()

    media = adapter.list_asset_media(asset_id, owner_type="asset")
    images = {row["beat_id"]: row for row in media if row.get("kind") == "image" and row.get("beat_id")}
    videos = {row["beat_id"]: row for row in media if row.get("kind") == "video" and row.get("beat_id")}
    estimate = estimate_motion(beats, models_config.get("media", {}), set(videos))
    return store, asset, beats, models_config, adapter, images, videos, estimate


def _poll_video(adapter: MediaAdapter, external_job_id: str, asset_id: int,
                model: str, prompt: str, business_slug: str, provider: str,
                estimated_cost_usd: float) -> dict:
    """Poll one already-submitted provider task and register its local file."""
    max_attempts = 60
    for _ in range(max_attempts):
        if provider == "fal":
            poll = adapter.check_video_job(external_job_id, provider=provider, model=model)
        else:
            poll = adapter.check_video_job(external_job_id, provider=provider)
        if poll.get("status") == "completed" and poll.get("download_url"):
            result = adapter.download_video(
                external_job_id, poll["download_url"], asset_id, model, prompt,
                poll.get("cost_usd", 0) or estimated_cost_usd,
                business_slug, video_provider=provider,
            )
            return {
                "path": result["file_path"],
                "media_id": result["media_id"],
            }
        if poll.get("status") == "failed":
            raise RuntimeError(poll.get("error") or "Video provider reported failure")
        time.sleep(5)
    raise RuntimeError("Video provider did not finish within five minutes")


def _find_submitted_video_tasks(db_path: str, asset_id: int,
                                not_before: str = "") -> dict[str, dict]:
    """Recover latest paid provider tasks from durable provenance."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT context, validated_output FROM provenance "
        "WHERE context LIKE ? AND timestamp >= ? ORDER BY timestamp DESC",
        (f"Approved storyboard animation % for asset {asset_id} (submitted, ext_job=%",
         not_before),
    ).fetchall()
    conn.close()
    tasks = {}
    pattern = re.compile(
        rf"Approved storyboard animation (b\d+) for asset {asset_id} "
        r"\(submitted, ext_job=([^\)]+)\)"
    )
    for context, validated_output in rows:
        match = pattern.fullmatch(context or "")
        if not match or match.group(1) in tasks:
            continue
        try:
            payload = json.loads(validated_output or "{}")
        except (TypeError, ValueError):
            payload = {}
        tasks[match.group(1)] = {
            "external_job_id": match.group(2),
            "prompt": payload.get("prompt", ""),
        }
    return tasks


def run_reel_production(asset_id: int, approved_cost_usd: float, *,
                        db_path: str, config_dir: str,
                        business_slug: str, modules_dir: str = "modules",
                        prompts_dir: str = "prompts") -> dict:
    """Fail closed: the superseded VO-led production path is retired."""
    raise ReelProductionError(
        "The legacy VO-led Reel production path is retired. "
        "Use the shared Media Planning, Edit Planning, and Render Review services."
    )
