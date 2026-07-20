"""Evidence-honest ranking of rights-valid soundtrack artifacts (VF-VS-513)."""

from __future__ import annotations

import json
from datetime import datetime


_EVIDENCE_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["claim", "evidence_field"],
    "properties": {
        "claim": {"type": "string", "minLength": 1},
        "evidence_field": {"type": "string", "minLength": 1},
    },
}
_TIE_BREAKER = {
    "type": "object",
    "additionalProperties": False,
    "required": ["used", "reason", "metric_name"],
    "properties": {
        "used": {"type": "boolean"},
        "reason": {"type": "string", "minLength": 1},
        "metric_name": {"type": ["string", "null"]},
    },
}
_SELECTION_PROPERTIES = {
    "candidate_id": {"type": "string", "minLength": 1},
    "rationale": {"type": "string", "minLength": 1},
    "fit_evidence": {
        "type": "array", "minItems": 1, "items": _EVIDENCE_ITEM,
    },
    "popularity_tie_breaker": _TIE_BREAKER,
}
_SELECTION_REQUIRED = list(_SELECTION_PROPERTIES)

SOUNDTRACK_RANKING_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "recommended", "alternatives", "vo_only_fallback", "vo_only_rationale",
    ],
    "properties": {
        "recommended": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "required": _SELECTION_REQUIRED,
            "properties": _SELECTION_PROPERTIES,
        },
        "alternatives": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": _SELECTION_REQUIRED,
                "properties": _SELECTION_PROPERTIES,
            },
        },
        "vo_only_fallback": {"type": "boolean"},
        "vo_only_rationale": {"type": ["string", "null"]},
    },
}


class SoundtrackRankingError(ValueError):
    """Raised when candidate evidence or ranking output fails closed."""


def _is_sha256(value) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def _validate_candidate(candidate: dict, index: int) -> list[str]:
    errors = []
    prefix = f"candidates[{index}]"
    for field in ("candidate_id", "title", "provider", "region"):
        if not isinstance(candidate.get(field), str) or not candidate[field].strip():
            errors.append(f"{prefix}.{field} is required")
    if candidate.get("rights_status") != "verified":
        errors.append(f"{prefix}.rights_status must be verified")
    for field in ("rights_record_id", "rights_version", "artifact_id", "preview_artifact_id"):
        value = candidate.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"{prefix}.{field} must be a positive integer")
    for field in ("rights_hash", "artifact_hash"):
        if not _is_sha256(candidate.get(field)):
            errors.append(f"{prefix}.{field} must be a SHA-256 digest")
    duration = candidate.get("duration_s")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
        errors.append(f"{prefix}.duration_s must be positive")
    observations = candidate.get("fit_observations")
    if not isinstance(observations, dict) or not observations:
        errors.append(f"{prefix}.fit_observations must contain observed facts")
    elif any(not isinstance(value, (str, int, float, bool)) for value in observations.values()):
        errors.append(f"{prefix}.fit_observations values must be scalar evidence")

    metric = candidate.get("metric")
    if not isinstance(metric, dict):
        errors.append(f"{prefix}.metric is required")
    else:
        for field in ("name", "provider", "region", "collected_at"):
            if not isinstance(metric.get(field), str) or not metric[field].strip():
                errors.append(f"{prefix}.metric.{field} is required")
        if metric.get("provider") != candidate.get("provider"):
            errors.append(f"{prefix}.metric.provider must match provider")
        if metric.get("region") != candidate.get("region"):
            errors.append(f"{prefix}.metric.region must match region")
        value = metric.get("value")
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            errors.append(f"{prefix}.metric.value must be numeric or null")
        rank = metric.get("rank")
        if rank is not None and (
            isinstance(rank, bool) or not isinstance(rank, int) or rank < 1
        ):
            errors.append(f"{prefix}.metric.rank must be a positive integer or null")
        try:
            datetime.fromisoformat(str(metric.get("collected_at", "")).replace("Z", "+00:00"))
        except ValueError:
            errors.append(f"{prefix}.metric.collected_at must be an ISO timestamp")
    return errors


def _build_candidates_json(candidates: list[dict], max_n: int = 30) -> str:
    """Validate and serialize exact evidence supplied to the ranking LLM."""
    if not candidates:
        raise SoundtrackRankingError("No rights-valid candidates available for ranking")
    selected = candidates[:max_n]
    errors = [
        error
        for index, candidate in enumerate(selected)
        for error in _validate_candidate(candidate, index)
    ]
    ids = [candidate.get("candidate_id") for candidate in selected]
    if len(ids) != len(set(ids)):
        errors.append("candidate_id values must be unique")
    if errors:
        raise SoundtrackRankingError("Candidate validation failed: " + "; ".join(errors))
    allowed_fields = (
        "candidate_id", "title", "artist", "provider", "region", "duration_s",
        "rights_record_id", "rights_version", "rights_hash", "rights_status",
        "artifact_id", "artifact_hash", "preview_artifact_id", "metric",
        "fit_observations",
    )
    payload = [
        {field: candidate.get(field) for field in allowed_fields}
        for candidate in selected
    ]
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _field_exists(candidate: dict, path: str) -> bool:
    current = candidate
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return current is not None and current != ""


def _metrics_comparable(candidates: list[dict]) -> bool:
    signatures = {
        (
            candidate["metric"]["name"],
            candidate["metric"]["provider"],
            candidate["metric"]["region"],
        )
        for candidate in candidates
    }
    return len(signatures) == 1


def _validate_ranking(result: dict, candidates: list[dict]) -> list[str]:
    """Validate membership, evidence grounding, uniqueness, and comparability."""
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["ranking result must be an object"]
    candidate_by_id = {candidate["candidate_id"]: candidate for candidate in candidates}
    vo_only = result.get("vo_only_fallback") is True
    recommended = result.get("recommended")
    alternatives = result.get("alternatives")
    if not isinstance(alternatives, list):
        alternatives = []
        errors.append("alternatives must be an array")

    if vo_only:
        if recommended is not None:
            errors.append("recommended must be null for vo_only_fallback")
        if alternatives:
            errors.append("alternatives must be empty for vo_only_fallback")
        rationale = result.get("vo_only_rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append("vo_only_rationale is required for vo_only_fallback")
        return errors
    if not isinstance(recommended, dict):
        errors.append("recommended is required when vo_only_fallback is false")
        return errors

    selections = [recommended, *alternatives]
    selected_ids = [selection.get("candidate_id") for selection in selections]
    if len(selected_ids) != len(set(selected_ids)):
        errors.append("selected candidate_id values must be unique")
    selected_candidates = []
    tie_breaker_used = False
    for index, selection in enumerate(selections):
        label = "recommended" if index == 0 else f"alternatives[{index - 1}]"
        candidate_id = selection.get("candidate_id")
        candidate = candidate_by_id.get(candidate_id)
        if not candidate:
            errors.append(f"{label} candidate_id '{candidate_id}' not in candidates")
            continue
        selected_candidates.append(candidate)
        evidence = selection.get("fit_evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{label}.fit_evidence must not be empty")
        else:
            for evidence_index, item in enumerate(evidence):
                path = item.get("evidence_field") if isinstance(item, dict) else None
                if not isinstance(path, str) or not _field_exists(candidate, path):
                    errors.append(
                        f"{label}.fit_evidence[{evidence_index}] references absent field '{path}'"
                    )
        tie_breaker = selection.get("popularity_tie_breaker")
        if not isinstance(tie_breaker, dict):
            errors.append(f"{label}.popularity_tie_breaker is required")
        elif tie_breaker.get("used") is True:
            tie_breaker_used = True
            metric_name = tie_breaker.get("metric_name")
            if metric_name != candidate["metric"]["name"]:
                errors.append(f"{label} tie-breaker metric_name does not match evidence")
    if tie_breaker_used:
        if len(selected_candidates) < 2:
            errors.append("popularity tie-breaker requires at least two selected candidates")
        elif not _metrics_comparable(selected_candidates):
            errors.append("popularity metrics are incomparable across selected candidates")
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
    """Rank only validated rights-valid artifacts through the configured LLM."""
    from llm_adapter import LLMAdapter

    ranking_config = config.get("ranking") or {}
    max_candidates = int(ranking_config.get("max_candidates_to_llm", 1))
    candidates_json = _build_candidates_json(candidates, max_n=max_candidates)
    music = (visual_direction or {}).get("music") or {}
    variables = {
        "emotional_register": emotional_register,
        "content_summary": str(audio_intent.get("content_summary") or "")[:500],
        "vo_duration_s": f"{vo_duration_s:.1f}",
        "energy_curve": str(music.get("energy_curve") or "not observed"),
        "candidates_json": candidates_json,
    }
    adapter = LLMAdapter(
        models_config=models_config,
        db_path=db_path,
        prompts_dir=prompts_dir,
    )
    try:
        result = adapter.complete(
            prompt_file=ranking_config.get("prompt_file", "soundtrack/ranking_v1.md"),
            variables=variables,
            schema=SOUNDTRACK_RANKING_SCHEMA,
            backend=ranking_config.get("backend", "default"),
            context=f"Soundtrack ranking for {min(len(candidates), max_candidates)} candidates",
            business_slug=business_slug,
            profile=ranking_config.get("profile", "processing"),
        )
    except Exception as exc:
        raise SoundtrackRankingError(f"LLM ranking call failed: {exc}") from exc
    errors = _validate_ranking(result, candidates[:max_candidates])
    if errors:
        raise SoundtrackRankingError("Ranking validation failed: " + "; ".join(errors))
    return result
