"""VF-VS-510..515: Soundtrack discovery + ranking + auto-mix tests."""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Discovery ────────────────────────────────────────────────────────────────

def test_discovery_query_derivation():
    """Search queries are derived from the Writer's audio/visual intent."""
    from soundtrack_discovery import _derive_search_queries
    queries = _derive_search_queries(
        {"audio_intents": [{"beat_id": "b01", "audio_intent": {"mood": "motivational"}}]},
        {"music": {"mood": "reflective", "genre": "minimal"}},
    )
    assert "reflective minimal" in queries
    assert "reflective" in queries
    assert "minimal" in queries


def test_discovery_query_fallback():
    """When no mood/genre is provided, falls back to 'instrumental'."""
    from soundtrack_discovery import _derive_search_queries
    queries = _derive_search_queries({"audio_intents": []}, None)
    assert "instrumental" in queries


def test_discovery_filter_min_duration():
    """Candidates shorter than min_duration_s are filtered out."""
    from soundtrack_discovery import _filter_candidates
    candidates = [
        {"duration_s": 15, "preview_url": "http://x", "commercial_safe": True},
        {"duration_s": 45, "preview_url": "http://y", "commercial_safe": True},
        {"duration_s": 0, "preview_url": "http://z", "commercial_safe": True},  # unknown duration = kept
    ]
    filtered = _filter_candidates(candidates, min_duration_s=30, require_preview_url=True)
    # The 15s track is filtered, the 45s and unknown-duration (0) are kept
    assert len(filtered) == 2
    assert all(c["duration_s"] >= 30 or c["duration_s"] == 0 for c in filtered)


def test_discovery_filter_no_preview():
    """Candidates without a preview URL are filtered when require_preview_url is True."""
    from soundtrack_discovery import _filter_candidates
    candidates = [
        {"duration_s": 60, "preview_url": "", "commercial_safe": True},
        {"duration_s": 60, "preview_url": "http://x", "commercial_safe": True},
    ]
    filtered = _filter_candidates(candidates, min_duration_s=30, require_preview_url=True)
    assert len(filtered) == 1
    assert filtered[0]["preview_url"] == "http://x"


# ── Ranking schema ───────────────────────────────────────────────────────────

def test_ranking_schema_structure():
    """The ranking schema validates the expected shape."""
    from soundtrack_ranking import SOUNDTRACK_RANKING_SCHEMA
    assert SOUNDTRACK_RANKING_SCHEMA["type"] == "object"
    assert "recommended" in SOUNDTRACK_RANKING_SCHEMA["required"]
    assert "alternatives" in SOUNDTRACK_RANKING_SCHEMA["required"]
    assert "vo_only_fallback" in SOUNDTRACK_RANKING_SCHEMA["required"]


def test_ranking_validation_rejects_invented_tracks():
    """The ranking validator rejects recommended tracks not in the candidate list."""
    from soundtrack_ranking import _validate_ranking
    candidates = [{"audio_id": "A1"}, {"audio_id": "A2"}]
    result = {
        "recommended": {"audio_id": "FAKE", "title": "Fake", "artist": "", "source": "x",
                        "rationale": "x", "fit_score": 90, "popularity_tier": "high"},
        "alternatives": [],
        "vo_only_fallback": False,
    }
    errors = _validate_ranking(result, candidates)
    assert any("FAKE" in e for e in errors)


def test_ranking_validation_accepts_real_tracks():
    """The ranking validator passes when tracks are in the candidate list."""
    from soundtrack_ranking import _validate_ranking
    candidates = [{"audio_id": "A1"}, {"audio_id": "A2"}, {"audio_id": "A3"}]
    result = {
        "recommended": {"audio_id": "A1", "title": "Track 1", "artist": "Artist",
                        "source": "bundle", "rationale": "Best fit",
                        "fit_score": 92, "popularity_tier": "high"},
        "alternatives": [
            {"audio_id": "A2", "title": "Track 2", "artist": "Artist2",
             "source": "bundle", "rationale": "Second", "trade_off": "Less fit",
             "fit_score": 85, "popularity_tier": "medium"},
        ],
        "vo_only_fallback": False,
    }
    errors = _validate_ranking(result, candidates)
    assert len(errors) == 0


def test_ranking_validation_vo_only_requires_rationale():
    """vo_only_fallback=True requires a vo_only_rationale."""
    from soundtrack_ranking import _validate_ranking
    candidates = [{"audio_id": "A1"}]
    result = {"recommended": None, "alternatives": [], "vo_only_fallback": True}
    errors = _validate_ranking(result, candidates)
    assert any("vo_only_rationale" in e for e in errors)


# ── Mix engineering ──────────────────────────────────────────────────────────

def test_mix_volume_filter_builds_segments():
    """The volume filter builds per-beat segments from the VO timeline."""
    from soundtrack_mix import _build_volume_filter
    config = {
        "mixing": {
            "energy_curve_mapping": {"intro": 0.25, "build": 0.35, "duck": 0.18},
            "ducking": {"default_depth": 0.20},
        }
    }
    timeline = [
        {"start_sec": 0, "end_sec": 8, "energy_phase": "intro"},
        {"start_sec": 8, "end_sec": 15, "energy_phase": "build"},
        {"start_sec": 15, "end_sec": 20, "energy_phase": "duck"},
    ]
    filt = _build_volume_filter([], timeline, config)
    assert "volume=0.25" in filt
    assert "volume=0.35" in filt
    assert "volume=0.18" in filt
    assert "between(t,0.00,8.00)" in filt


def test_mix_phase_from_index():
    """Beat index maps to energy phases."""
    from soundtrack_mix import _phase_from_index
    # Test the function directly
    from services.edit_planning import _phase_from_beat_index
    assert _phase_from_beat_index(0) == "intro"
    assert _phase_from_beat_index(1) == "build"
    assert _phase_from_beat_index(2) == "duck"
    assert _phase_from_beat_index(3) == "lift"
    assert _phase_from_beat_index(4) == "settle"
    assert _phase_from_beat_index(10) == "settle"  # clamped


# ── Config ───────────────────────────────────────────────────────────────────

def test_config_has_soundtrack_block():
    """models.yaml has the soundtrack config block."""
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")) as f:
        config = yaml.safe_load(f)
    assert "soundtrack" in config
    assert "discovery" in config["soundtrack"]
    assert "ranking" in config["soundtrack"]
    assert "mixing" in config["soundtrack"]
    assert config["soundtrack"]["ranking"]["mood_fit_weight"] == 0.80
    assert config["soundtrack"]["ranking"]["popularity_weight"] == 0.20