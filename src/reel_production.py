"""VO-first production mechanics for structured reel assets.

The Writer owns words and semantic intent. This module only preserves that
contract while turning measured VO and beat-scoped media into a render plan.
It contains no creative judgment and makes no provider calls.
"""

from __future__ import annotations

import math
import os
from typing import Iterable


class ReelProductionError(ValueError):
    """Raised when a reel cannot be produced without violating its contract."""


MOTION_PLAN_SCHEMA = {
    "type": "object",
    "required": ["shots"],
    "properties": {
        "shots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["beat_id", "motion_prompt"],
                "properties": {
                    "beat_id": {"type": "string"},
                    "motion_prompt": {"type": "string"},
                },
            },
        },
    },
}


def extract_reel_beats(posts: Iterable[object]) -> list[dict]:
    """Normalize structured Writer frames without rewriting approved text."""
    beats = []
    for index, post in enumerate(posts or [], 1):
        if isinstance(post, dict):
            vo_text = str(post.get("vo_text") or "").strip()
            overlay = str(post.get("text_on_screen") or "").strip()
            visual = str(post.get("visual") or post.get("visual_intent") or "").strip()
            beat_id = str(post.get("beat_id") or f"b{index:02d}")
        else:
            vo_text = str(post or "").strip()
            overlay = ""
            visual = ""
            beat_id = f"b{index:02d}"
        if not vo_text and not overlay and not visual:
            continue
        beats.append({
            "beat_id": beat_id,
            "frame": index,
            "vo_text": vo_text,
            "overlay_text": overlay,
            "visual": visual,
        })
    return beats


def validate_vo_segments(beats: list[dict], segments: list[dict]) -> dict:
    """Require a complete, exact, measured VO take for every spoken beat."""
    spoken = [beat for beat in beats if beat.get("vo_text")]
    if not spoken:
        return {"take_id": "", "combined_path": "", "duration": 0.0}
    if len(segments or []) != len(spoken):
        raise ReelProductionError(
            f"Reel has {len(spoken)} spoken beats but only {len(segments or [])} VO segment(s). "
            "Generate the complete voice-over before rendering."
        )

    take_ids = set()
    combined_paths = set()
    total = 0.0
    by_beat = {str(seg.get("beat_id") or f"b{int(seg.get('frame', 0)):02d}"): seg for seg in segments}
    for beat in spoken:
        seg = by_beat.get(beat["beat_id"])
        if not seg:
            raise ReelProductionError(f"Missing VO segment for beat {beat['beat_id']}.")
        if str(seg.get("text") or "") != beat["vo_text"]:
            raise ReelProductionError(
                f"VO segment {beat['beat_id']} does not match approved text. Regenerate the complete take."
            )
        path = str(seg.get("path") or "")
        duration = float(seg.get("duration") or 0)
        if not path or not os.path.exists(path) or duration <= 0:
            raise ReelProductionError(f"VO segment {beat['beat_id']} has no valid measured audio file.")
        take_ids.add(str(seg.get("take_id") or ""))
        combined_paths.add(str(seg.get("combined_path") or ""))
        total += duration

    take_ids.discard("")
    combined_paths.discard("")
    if len(take_ids) != 1 or len(combined_paths) != 1:
        raise ReelProductionError("VO segments do not identify one complete combined take.")
    combined_path = next(iter(combined_paths))
    if not os.path.exists(combined_path):
        raise ReelProductionError("The combined VO file is missing; rendering would be silent.")
    return {
        "take_id": next(iter(take_ids)),
        "combined_path": combined_path,
        "duration": round(total, 3),
    }


def _video_generator(media_config: dict) -> dict:
    default = media_config.get("video_default", "")
    generators = media_config.get("video_generators", []) or []
    selected = next((g for g in generators if g.get("name") == default), None)
    if not selected and generators:
        selected = generators[0]
    if not selected:
        raise ReelProductionError("No video generator is configured.")
    return selected


def estimate_motion(beats: list[dict], media_config: dict,
                    existing_motion_beat_ids: set[str] | None = None) -> dict:
    """Compute the exact animation spend before any provider call."""
    generator = _video_generator(media_config)
    existing = existing_motion_beat_ids or set()
    missing = [b["beat_id"] for b in beats if b["beat_id"] not in existing]
    clip_duration = int(generator.get("clip_duration_seconds", 5))
    rate = float(generator.get("cost_per_second_usd", 0))
    return {
        "generator": generator.get("name", ""),
        "provider": generator.get("provider", ""),
        "clip_duration_seconds": clip_duration,
        "missing_beat_ids": missing,
        "clip_count": len(missing),
        "estimated_cost_usd": round(len(missing) * clip_duration * rate, 2),
    }


def validate_cost_approval(approved_cost_usd: float, current_cost_usd: float) -> None:
    """Fail closed if the operator approved a stale or different spend."""
    if abs(float(approved_cost_usd) - float(current_cost_usd)) > 0.005:
        raise ReelProductionError(
            f"The animation estimate changed from ${float(approved_cost_usd):.2f} "
            f"to ${float(current_cost_usd):.2f}. Review and approve the new estimate."
        )


def validate_motion_plan(beats: list[dict], plan: dict) -> dict[str, str]:
    """Require one provider prompt for every exact Writer beat, no inventions."""
    required = {beat["beat_id"] for beat in beats}
    prompts = {}
    for shot in plan.get("shots", []) or []:
        beat_id = str(shot.get("beat_id") or "")
        prompt = str(shot.get("motion_prompt") or "").strip()
        if beat_id not in required:
            raise ReelProductionError(f"Motion plan invented unknown beat {beat_id}.")
        if not prompt:
            raise ReelProductionError(f"Motion plan has an empty prompt for beat {beat_id}.")
        if beat_id in prompts:
            raise ReelProductionError(f"Motion plan duplicated beat {beat_id}.")
        prompts[beat_id] = prompt
    missing = sorted(required - set(prompts))
    if missing:
        raise ReelProductionError(f"Motion plan is missing beat(s): {', '.join(missing)}.")
    return prompts


def build_reel_plan(beats: list[dict], vo_segments: list[dict],
                    visuals_by_beat: dict[str, dict],
                    render_config: dict) -> tuple[dict, dict]:
    """Build a source-resolved beat plan from measured VO and scoped media.

    A generated motion clip opens each beat; its approved source still holds the
    remainder when the spoken beat is longer. This is deterministic coverage,
    not a creative rewrite.
    """
    vo = validate_vo_segments(beats, vo_segments)
    required_config = ("aspect_ratio", "resolution", "caption_style_ref", "overlay_style_ref")
    missing_config = [key for key in required_config if not render_config.get(key)]
    if missing_config:
        raise ReelProductionError(
            f"Reel render config is missing: {', '.join(missing_config)}."
        )
    segments = []
    contract_beats = []
    by_beat = {str(seg.get("beat_id") or f"b{int(seg.get('frame', 0)):02d}"): seg for seg in vo_segments}
    timeline = 0.0

    for beat in beats:
        if not beat.get("vo_text"):
            continue
        beat_id = beat["beat_id"]
        duration = round(float(by_beat[beat_id]["duration"]), 3)
        media = visuals_by_beat.get(beat_id, {}) or {}
        video = media.get("video") or {}
        image = media.get("image") or {}
        if not video and not image:
            raise ReelProductionError(f"Beat {beat_id} has no beat-scoped visual media.")

        beat_segment_ids = []
        remaining = duration
        sources = []
        if video:
            video_duration = min(float(video.get("duration") or 0), remaining)
            if video_duration > 0:
                sources.append((video["ingredient_id"], video_duration))
                remaining = round(remaining - video_duration, 3)
        if remaining > 0:
            fallback = image or video
            if not fallback:
                raise ReelProductionError(f"Beat {beat_id} lacks media for {remaining:.1f}s of VO.")
            sources.append((fallback["ingredient_id"], remaining))

        for source_index, (source, source_duration) in enumerate(sources, 1):
            segment_id = f"seg_{beat_id}_{source_index}"
            beat_segment_ids.append(segment_id)
            overlays = [{
                "type": "caption",
                "text": beat["vo_text"],
                "start": 0.0,
                "end": source_duration,
                "style_ref": render_config["caption_style_ref"],
                "position": "bottom",
            }]
            if beat.get("overlay_text"):
                overlays.append({
                    "type": "text_card",
                    "text": beat["overlay_text"],
                    "start": 0.0,
                    "end": source_duration,
                    "style_ref": render_config["overlay_style_ref"],
                    "position": "center",
                })
            segments.append({
                "segment_id": segment_id,
                "beat_id": beat_id,
                "source": source,
                "in": 0.0,
                "out": source_duration,
                # Cuts preserve the measured VO clock exactly. Crossfades shorten
                # the assembled timeline unless their overlap is budgeted.
                "transition_in": "cut",
                "overlays": overlays,
            })

        contract_beats.append({
            "beat_id": beat_id,
            "source_excerpt": beat["vo_text"],
            "requirement_type": "spoken_dialogue",
            "required": True,
            "planned_segment_ids": beat_segment_ids,
            "planned_time_range": {"start": timeline, "end": round(timeline + duration, 3)},
            "expected_duration": duration,
            "verification_method": "audio_transcript_match",
        })
        timeline = round(timeline + duration, 3)

    plan = {
        "segments": segments,
        "audio": {
            "vo": {"take_id": vo["take_id"], "ducking": True},
            "music": {},
            "original_audio": False,
        },
        "captions": {
            "burned_in": True,
            "source": "vo_script",
            "style_ref": render_config["caption_style_ref"],
        },
        "canvas": {
            "aspect_ratio": render_config["aspect_ratio"],
            "resolution": render_config["resolution"],
            "duration_target": vo["duration"],
        },
    }
    contract = {
        "beats": contract_beats,
        "summary": f"{len(contract_beats)} exact spoken beats mapped to measured VO and beat-scoped media.",
    }
    return plan, contract
