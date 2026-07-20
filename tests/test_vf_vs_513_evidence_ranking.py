"""VF-VS-513 evidence-honest, rights-valid soundtrack ranking."""

from pathlib import Path
import json
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from soundtrack_ranking import (
    SoundtrackRankingError,
    _build_candidates_json,
    _validate_ranking,
    rank_soundtrack_candidates,
)


def _candidate(candidate_id="track-1", **overrides):
    candidate = {
        "candidate_id": candidate_id,
        "title": "Track",
        "artist": "Artist",
        "provider": "catalog-a",
        "region": "global",
        "duration_s": 45.0,
        "rights_record_id": 11,
        "rights_version": 2,
        "rights_hash": "a" * 64,
        "rights_status": "verified",
        "artifact_id": 21,
        "artifact_hash": "b" * 64,
        "preview_artifact_id": 31,
        "metric": {
            "name": "provider_rank",
            "value": 7,
            "rank": 7,
            "provider": "catalog-a",
            "region": "global",
            "collected_at": "2026-07-20T00:00:00+00:00",
        },
        "fit_observations": {
            "mood": "warm",
            "energy": "restrained",
            "vocals": "none observed",
        },
    }
    candidate.update(overrides)
    return candidate


def _selection(candidate_id="track-1", **overrides):
    selection = {
        "candidate_id": candidate_id,
        "rationale": "The observed mood and energy fit the requested register.",
        "fit_evidence": [
            {"claim": "Warm mood", "evidence_field": "fit_observations.mood"},
            {"claim": "Restrained energy", "evidence_field": "fit_observations.energy"},
        ],
        "popularity_tie_breaker": {
            "used": False,
            "reason": "Fit evidence was decisive.",
            "metric_name": None,
        },
    }
    selection.update(overrides)
    return selection


def _result(recommended=None, alternatives=None):
    return {
        "recommended": recommended or _selection(),
        "alternatives": alternatives or [],
        "vo_only_fallback": False,
        "vo_only_rationale": None,
    }


@pytest.mark.parametrize("field,value", [
    ("rights_status", "unknown"),
    ("rights_record_id", None),
    ("artifact_id", None),
    ("artifact_hash", "bad"),
    ("preview_artifact_id", None),
])
def test_ranking_rejects_candidate_without_rights_valid_local_artifacts(field, value):
    with pytest.raises(SoundtrackRankingError):
        _build_candidates_json([_candidate(**{field: value})])


def test_candidate_payload_preserves_exact_evidence_fields():
    payload = _build_candidates_json([_candidate()])
    assert '"rights_version": 2' in payload
    assert '"artifact_hash"' in payload
    assert '"collected_at"' in payload
    assert '"provider_rank"' in payload


def test_candidate_metric_scope_must_match_candidate_scope():
    candidate = _candidate()
    candidate["metric"]["provider"] = "another-provider"
    with pytest.raises(SoundtrackRankingError, match="must match provider"):
        _build_candidates_json([candidate])


def test_validator_rejects_invented_and_duplicate_selection_ids():
    candidates = [_candidate("track-1"), _candidate("track-2")]
    result = _result(
        recommended=_selection("track-1"),
        alternatives=[_selection("track-1"), _selection("invented")],
    )
    errors = _validate_ranking(result, candidates)
    assert any("unique" in error for error in errors)
    assert any("invented" in error for error in errors)


def test_validator_rejects_rationale_evidence_field_absent_from_candidate():
    result = _result(recommended=_selection(
        fit_evidence=[{"claim": "Viral", "evidence_field": "invented.virality"}]
    ))
    errors = _validate_ranking(result, [_candidate()])
    assert any("invented.virality" in error for error in errors)


def test_incomparable_cross_provider_metrics_cannot_be_used_as_tie_breaker():
    candidates = [
        _candidate("track-1"),
        _candidate(
            "track-2",
            provider="catalog-b",
            metric={
                "name": "usage_count",
                "value": 1000,
                "rank": None,
                "provider": "catalog-b",
                "region": "us",
                "collected_at": "2026-07-20T00:00:00+00:00",
            },
        ),
    ]
    result = _result(
        recommended=_selection(
            "track-1",
            popularity_tie_breaker={
                "used": True,
                "reason": "Higher popularity.",
                "metric_name": "provider_rank",
            },
        ),
        alternatives=[_selection("track-2")],
    )
    errors = _validate_ranking(result, candidates)
    assert any("incomparable" in error for error in errors)


def test_comparable_metric_may_be_a_bounded_tie_breaker():
    candidates = [
        _candidate("track-1"),
        _candidate(
            "track-2",
            metric={
                "name": "provider_rank",
                "value": 9,
                "rank": 9,
                "provider": "catalog-a",
                "region": "global",
                "collected_at": "2026-07-20T00:10:00+00:00",
            },
        ),
    ]
    result = _result(
        recommended=_selection(
            popularity_tie_breaker={
                "used": True,
                "reason": "Comparable provider rank broke a fit tie.",
                "metric_name": "provider_rank",
            },
        ),
        alternatives=[_selection("track-2")],
    )
    assert _validate_ranking(result, candidates) == []


def test_vo_only_requires_reason_and_no_selected_tracks():
    result = {
        "recommended": _selection(),
        "alternatives": [],
        "vo_only_fallback": True,
        "vo_only_rationale": "",
    }
    errors = _validate_ranking(result, [_candidate()])
    assert any("recommended" in error for error in errors)
    assert any("vo_only_rationale" in error for error in errors)


def test_ranking_call_logs_processing_profile_prompt_version_and_cache(
    monkeypatch, tmp_path
):
    proposal = _result()
    network_calls = []

    def fake_network(self, prompt, model, base_url, temperature, max_tokens):
        network_calls.append(prompt)
        return json.dumps(proposal), 9

    monkeypatch.setattr(
        "llm_adapter.LLMAdapter._call_openai_compatible", fake_network
    )
    db_path = str(tmp_path / "ranking.db")
    models = {
        "active": {"default": "test_backend"},
        "test_backend": {
            "provider": "openai_compatible",
            "model": "test-ranking-model",
            "temperature": 0,
            "max_tokens": 1000,
            "base_url": "http://127.0.0.1:1",
        },
    }
    kwargs = {
        "candidates": [_candidate()],
        "audio_intent": {"content_summary": "Approved summary"},
        "visual_direction": {"music": {"energy_curve": "restrained"}},
        "vo_duration_s": 30.0,
        "emotional_register": "warm",
        "config": {"ranking": {
            "prompt_file": "soundtrack/ranking_v1.md",
            "backend": "default",
            "profile": "processing",
            "max_candidates_to_llm": 10,
        }},
        "models_config": models,
        "db_path": db_path,
        "prompts_dir": str(ROOT / "prompts"),
        "business_slug": "test-business",
    }

    assert rank_soundtrack_candidates(**kwargs) == proposal
    assert rank_soundtrack_candidates(**kwargs) == proposal
    assert len(network_calls) == 1
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """SELECT prompt_file, prompt_version, model, provider, profile,
                      raw_output, validator_verdict, business_slug
               FROM provenance ORDER BY id"""
        ).fetchall()
    assert rows[0] == (
        "soundtrack/ranking_v1.md", "2.0", "test-ranking-model",
        "openai_compatible", "processing", json.dumps(proposal), "valid",
        "test-business",
    )
    assert rows[1][5] == "(cached)"
    assert rows[1][6] == "valid"
