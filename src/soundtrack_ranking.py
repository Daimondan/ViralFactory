"""Soundtrack ranking via LLM (VF-VS-511, DIVERGENCE-015).

The LLM receives filtered candidates + the script's audio intent and returns
a ranked top 3 (1 recommended + 2 alternatives). Ranking weights: mood/fit
80%, popularity/trending 20%. The LLM applies these in context, not as a
mechanical formula.

Provenance is logged like every other LLM call.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


SOUNDTRACK_RANKING_SCHEMA = {
    "type": "object",
    "required": ["recommended", "alternatives", "vo_only_fallback"],
    "properties": {
        "recommended": {
            "type": ["object", "null"],
            "properties": {
                "audio_id": {"type": "string", "minLength": 1},
                "title": {"type": "string"},
                "artist": {"type": "string"},
                "source": {"type": "string"},
                "rationale": {"type": "string"},
                "fit_score": {"type": "number", "minimum": 0, "maximum": 100},
                "popularity_tier": {"type": "string", "enum": ["high", "medium", "low"]},
            },
        },
        "alternatives": {
            "type": "array",
            "minItems": 0,
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "audio_id": {"type": "string", "minLength": 1},
                    "title": {"type": "string"},
                    "artist": {"type": "string"},
                    "source": {"type": "string"},
                    "rationale": {"type": "string"},
                    "trade_off": {"type": "string"},
                    "fit_score": {"type": "number", "minimum": 0, "maximum": 100},
                    "popularity_tier": {"type": "string", "enum": ["high", "medium", "low"]},
                },
            },
        },
        "vo_only_fallback": {"type": "boolean"},
        "vo_only_rationale": {"type": "string"},
    },
}


class SoundtrackRankingError(Exception):
    """Raised when ranking fails critically."""


def _build_candidates_json(candidates: list[dict], max_n: int = 30) -> str:
    """Build a compact JSON representation of candidates for the LLM."""
    compact = []
    for c in candidates[:max_n]:
        compact.append({
            "audio_id": c["audio_id"],
            "title": c["title"],
            "artist": c["artist"],
            "source": c["source"],
            "duration_s": c["duration_s"],
            "preview_url": c.get("preview_url", "")[:80],
            "license_observation": c.get("license_observation", ""),
            "rights_status": c.get("rights_status", "unknown"),
        })
    return json.dumps(compact, indent=2, ensure_ascii=False)


def _validate_ranking(
    result: dict, candidates: list[dict],
) -> list[str]:
    """Validate that the ranking only references real candidates."""
    errors = []
    valid_ids = {c["audio_id"] for c in candidates}

    rec = result.get("recommended")
    if not result.get("vo_only_fallback") and rec:
        if rec.get("audio_id") and rec["audio_id"] not in valid_ids:
            errors.append(f"Recommended audio_id '{rec['audio_id']}' not in candidates")

    for alt in result.get("alternatives", []):
        if alt.get("audio_id") and alt["audio_id"] not in valid_ids:
            errors.append(f"Alternative audio_id '{alt['audio_id']}' not in candidates")

    if not result.get("vo_only_fallback") and not rec:
        errors.append("No recommended track and vo_only_fallback is false")

    if result.get("vo_only_fallback") and not result.get("vo_only_rationale"):
        errors.append("vo_only_fallback is true but no vo_only_rationale provided")

    return errors


def rank_soundtrack_candidates(
    candidates: list[dict],
    audio_intent: dict,
    visual_direction: dict | None,
    vo_duration_s: float,
    emotional_register: str,
    config: dict,
    models_config: dict,
    db_path: str,
    config_dir: str = "config",
    modules_dir: str = "modules",
    prompts_dir: str = "prompts",
    business_slug: str = "",
    business_config: dict | None = None,
) -> dict:
    """Run the LLM ranking on soundtrack candidates.

    Returns the validated ranking result with provenance.
    """
    from llm_adapter import LLMAdapter

    ranking_config = config.get("ranking", {})
    prompt_file = "soundtrack/ranking_v1.md"

    # Build the candidates JSON for the prompt
    candidates_json = _build_candidates_json(candidates)

    # Extract energy curve from visual_direction
    music_block = (visual_direction or {}).get("music", {})
    energy_curve = music_block.get("energy_curve", "intro-build-duck-lift-settle")

    variables = {
        "emotional_register": emotional_register or "neutral",
        "content_summary": audio_intent.get("content_summary", "")[:500],
        "vo_duration_s": f"{vo_duration_s:.1f}",
        "energy_curve": energy_curve,
        "candidates_json": candidates_json,
    }

    adapter = LLMAdapter(
        models_config=models_config,
        db_path=db_path,
        prompts_dir=prompts_dir,
    )

    try:
        result = adapter.complete(
            prompt_file=prompt_file,
            variables=variables,
            schema=SOUNDTRACK_RANKING_SCHEMA,
            backend="drafter",
            context=f"Soundtrack ranking for {len(candidates)} candidates",
            business_slug=business_slug,
            profile="drafter",
        )
    except Exception as exc:
        raise SoundtrackRankingError(f"LLM ranking call failed: {exc}") from exc

    # Validate the result references real candidates
    validation_errors = _validate_ranking(result, candidates)
    if validation_errors:
        raise SoundtrackRankingError(
            f"Ranking validation failed: {'; '.join(validation_errors)}"
        )

    return result