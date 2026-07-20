"""VF-VS-510..515: Soundtrack discovery + ranking + auto-mix tests."""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Discovery ────────────────────────────────────────────────────────────────

def test_discovery_filter_min_duration():
    """Candidates shorter than min_duration_s are filtered out."""
    from soundtrack_discovery import _filter_candidates
    candidates = [
        {"duration_s": 15, "preview_url": "http://x"},
        {"duration_s": 45, "preview_url": "http://y"},
        {"duration_s": 0, "preview_url": "http://z"},  # unknown duration = kept
    ]
    filtered = _filter_candidates(candidates, min_duration_s=30, require_preview_url=True)
    # The 15s track is filtered, the 45s and unknown-duration (0) are kept
    assert len(filtered) == 2
    assert all(c["duration_s"] >= 30 or c["duration_s"] == 0 for c in filtered)


def test_discovery_filter_no_preview():
    """Candidates without a preview URL are filtered when require_preview_url is True."""
    from soundtrack_discovery import _filter_candidates
    candidates = [
        {"duration_s": 60, "preview_url": ""},
        {"duration_s": 60, "preview_url": "http://x"},
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
    assert SOUNDTRACK_RANKING_SCHEMA["additionalProperties"] is False
    selection = SOUNDTRACK_RANKING_SCHEMA["properties"]["recommended"]
    assert "fit_evidence" in selection["required"]
    assert "popularity_tie_breaker" in selection["required"]


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
    ranking = config["soundtrack"]["ranking"]
    assert ranking["prompt_file"] == "soundtrack/ranking_v1.md"
    assert ranking["profile"] == "processing"
    assert "mood_fit_weight" not in ranking
    assert "popularity_weight" not in ranking