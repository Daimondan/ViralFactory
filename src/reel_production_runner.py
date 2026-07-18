"""Long-running VO-first reel production, executed by the systemd worker."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time

from config_loader import load_all
from media_adapter import MediaAdapter
from pipeline import PipelineStore
from reel_production import (
    MOTION_PLAN_SCHEMA,
    ReelProductionError,
    build_reel_plan,
    estimate_motion,
    extract_reel_beats,
    validate_cost_approval,
    validate_motion_plan,
    validate_vo_segments,
)


def _state(asset_id: int, db_path: str, config_dir: str):
    store = PipelineStore(db_path=db_path)
    asset = store.get_asset(asset_id)
    if not asset:
        raise ReelProductionError("Asset not found")
    beats = extract_reel_beats(json.loads(asset.get("posts") or "[]"))
    if not beats or not any(beat.get("vo_text") for beat in beats):
        raise ReelProductionError("This asset has no structured spoken reel beats.")

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
    """Produce complete VO, motion clips, and an exact edit plan."""
    store, asset, beats, models_config, adapter, images, videos, estimate = _state(
        asset_id, db_path, config_dir,
    )
    validate_cost_approval(approved_cost_usd, estimate["estimated_cost_usd"])
    missing_images = [beat["beat_id"] for beat in beats if beat["beat_id"] not in images]
    if missing_images:
        raise ReelProductionError(
            f"Storyboard stills are missing for: {', '.join(missing_images)}. Generate images first."
        )

    from vo_generator import VOGenerator
    vo_segments = json.loads(store.get_vo_segments(asset_id) or "[]")
    try:
        validate_vo_segments(beats, vo_segments)
    except ReelProductionError:
        vo_result = VOGenerator(
            db_path=db_path, models_config=models_config,
        ).generate_vo_per_frame(
            asset_id=asset_id,
            posts=[{"beat_id": beat["beat_id"], "vo_text": beat["vo_text"]}
                   for beat in beats if beat.get("vo_text")],
            business_slug=business_slug,
        )
        vo_segments = vo_result["segments"]
        store.save_vo_segments(asset_id, json.dumps(vo_segments))
        validate_vo_segments(beats, vo_segments)

    # A worker may die after paid submission but before download. Recover those
    # provider tasks from provenance before considering any new spend.
    latest_source_time = max((row.get("created_at") or "" for row in images.values()), default="")
    submitted_tasks = _find_submitted_video_tasks(db_path, asset_id, latest_source_time)
    missing_before_recovery = list(estimate["missing_beat_ids"])
    clip_cost = (
        estimate["estimated_cost_usd"] / len(missing_before_recovery)
        if missing_before_recovery else 0
    )
    recovered_any = False
    for beat_id in missing_before_recovery:
        task = submitted_tasks.get(beat_id)
        if not task:
            continue
        generated = _poll_video(
            adapter, task["external_job_id"], asset_id,
            estimate["generator"], task["prompt"], business_slug,
            estimate["provider"], clip_cost,
        )
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE asset_media SET beat_id = ?, source_media_id = ? WHERE id = ?",
            (beat_id, images[beat_id]["id"], generated["media_id"]),
        )
        conn.commit()
        conn.close()
        recovered_any = True
    if recovered_any:
        store, asset, beats, models_config, adapter, images, videos, estimate = _state(
            asset_id, db_path, config_dir,
        )

    from context_assembly import assemble_module_context
    from llm_adapter import LLMAdapter
    module_vars, module_prov = assemble_module_context(
        "assembly/motion_plan_v1.md", business_slug,
        db_path=db_path, modules_dir=modules_dir,
    )
    vo_by_beat = {segment["beat_id"]: segment for segment in vo_segments}
    storyboard = [{
        "beat_id": beat["beat_id"],
        "semantic_visual_intent": beat["visual"],
        "measured_vo_duration_seconds": vo_by_beat[beat["beat_id"]]["duration"],
        "approved_source_still": images[beat["beat_id"]]["path"],
    } for beat in beats]
    motion_result = LLMAdapter(
        models_config, db_path=db_path, prompts_dir=prompts_dir,
    ).complete(
        prompt_file="assembly/motion_plan_v1.md",
        variables={
            "storyboard_beats": json.dumps(storyboard, ensure_ascii=False, indent=2),
            "generator_constraints": json.dumps({
                "generator": estimate["generator"],
                "clip_duration_seconds": estimate["clip_duration_seconds"],
                "mode": "image_to_video",
            }),
            "visual_style": module_vars.get("visual_style", ""),
        },
        schema=MOTION_PLAN_SCHEMA,
        backend="drafter",
        context=f"Motion plan for asset {asset_id} | module_ctx: {module_prov}",
        business_slug=business_slug,
        profile="drafter",
    )
    motion_prompts = validate_motion_plan(beats, motion_result)

    render_config = models_config.get("media", {}).get("reel_production", {})
    submissions = []
    for beat_id in estimate["missing_beat_ids"]:
        source = images[beat_id]
        submit = adapter.submit_video(
            prompt=motion_prompts[beat_id],
            asset_id=asset_id,
            model=estimate["generator"],
            provider=estimate["provider"],
            aspect_ratio=render_config.get("aspect_ratio", ""),
            duration=estimate["clip_duration_seconds"],
            source_image=source["path"],
            mode="image_to_video",
            context=f"Approved storyboard animation {beat_id} for asset {asset_id}",
            business_slug=business_slug,
        )
        submissions.append((beat_id, source, submit))

    for beat_id, source, submit in submissions:
        generated = _poll_video(
            adapter, submit["external_job_id"], asset_id,
            submit.get("model", estimate["generator"]), motion_prompts[beat_id],
            business_slug, estimate["provider"], submit.get("cost_usd", 0),
        )
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE asset_media SET beat_id = ?, source_media_id = ? WHERE id = ?",
            (beat_id, source["id"], generated["media_id"]),
        )
        conn.commit()
        conn.close()

    media = adapter.list_asset_media(asset_id, owner_type="asset")
    images = {row["beat_id"]: row for row in media if row.get("kind") == "image" and row.get("beat_id")}
    videos = {row["beat_id"]: row for row in media if row.get("kind") == "video" and row.get("beat_id")}
    from assembly import probe_duration
    visuals = {}
    for beat in beats:
        beat_id = beat["beat_id"]
        image = images[beat_id]
        video = videos.get(beat_id)
        visuals[beat_id] = {"image": {"ingredient_id": f"generated:{image['id']}"}}
        if video:
            visuals[beat_id]["video"] = {
                "ingredient_id": f"generated:{video['id']}",
                "duration": probe_duration(video["path"]) or estimate["clip_duration_seconds"],
            }

    plan, contract = build_reel_plan(beats, vo_segments, visuals, render_config)
    source_hash = hashlib.sha256(
        json.dumps(json.loads(asset.get("posts") or "[]"), sort_keys=True,
                   ensure_ascii=False).encode()
    ).hexdigest()
    plan_id = store.save_edit_plan(
        asset["draft_id"], asset_id, plan,
        compliance_contract=contract, source_draft_hash=source_hash,
    )
    return {
        "status": "ok",
        "plan_id": plan_id,
        "vo_duration_seconds": plan["canvas"]["duration_target"],
        "motion_clips": len(videos),
        "estimated_cost_usd": estimate["estimated_cost_usd"],
    }
