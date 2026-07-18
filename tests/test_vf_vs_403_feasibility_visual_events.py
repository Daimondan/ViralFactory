"""VF-VS-403 — Extend feasibility checks: multi-event coverage + talking-head motion.

AC: Draft 8 Artifact A's 5s-motion + still fallback is caught and blocked.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from feasibility_checks import (
    check_visual_event_coverage as _check_visual_event_coverage,
    check_talking_head_motion_coverage as _check_talking_head_motion_coverage,
    run_feasibility_checks as _run_feasibility_checks,
)

TEST_EVENT_TOLERANCE_S = 0.25
TEST_MOTION_SHORTFALL_RATIO = 0.5


def check_visual_event_coverage(*args, **kwargs):
    kwargs.setdefault("tolerance_s", TEST_EVENT_TOLERANCE_S)
    return _check_visual_event_coverage(*args, **kwargs)


def check_talking_head_motion_coverage(*args, **kwargs):
    kwargs.setdefault("shortfall_ratio", TEST_MOTION_SHORTFALL_RATIO)
    return _check_talking_head_motion_coverage(*args, **kwargs)


def run_feasibility_checks(*args, **kwargs):
    if kwargs.get("beats") is not None:
        kwargs.setdefault("event_coverage_tolerance_s", TEST_EVENT_TOLERANCE_S)
        kwargs.setdefault("motion_shortfall_ratio", TEST_MOTION_SHORTFALL_RATIO)
    return _run_feasibility_checks(*args, **kwargs)


# ── Multi-event coverage ─────────────────────────────────────────────────────


def _make_event(start, end, event_id="ev_b01_1", source_policy="generated_still"):
    return {
        "event_id": event_id,
        "time_range": {"start": start, "end": end},
        "narrative_function": "context",
        "source_policy": source_policy,
    }


def test_full_coverage_passes():
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 14.0},
        "visual_events": [
            _make_event(0.0, 5.0, "ev_b01_1"),
            _make_event(5.0, 10.0, "ev_b01_2"),
            _make_event(10.0, 14.0, "ev_b01_3"),
        ],
    }]
    result = check_visual_event_coverage(beats)
    assert result["feasible"]


def test_gap_detected():
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 14.0},
        "visual_events": [
            _make_event(0.0, 5.0, "ev_b01_1"),
            _make_event(8.0, 14.0, "ev_b01_2"),  # 3s gap
        ],
    }]
    result = check_visual_event_coverage(beats)
    assert not result["feasible"]
    assert any(iss["type"] == "gap" for iss in result["issues"])


def test_overlap_detected():
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 14.0},
        "visual_events": [
            _make_event(0.0, 7.0, "ev_b01_1"),
            _make_event(5.0, 14.0, "ev_b01_2"),  # 2s overlap
        ],
    }]
    result = check_visual_event_coverage(beats)
    assert not result["feasible"]
    assert any(iss["type"] == "overlap" for iss in result["issues"])


def test_incomplete_coverage_detected():
    """Events end early — beat span not fully covered."""
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 14.0},
        "visual_events": [
            _make_event(0.0, 5.0, "ev_b01_1"),
            _make_event(5.0, 8.0, "ev_b01_2"),  # ends at 8, span is 14
        ],
    }]
    result = check_visual_event_coverage(beats)
    assert not result["feasible"]
    assert any(iss["type"] == "incomplete_coverage" for iss in result["issues"])


def test_out_of_bounds_event_detected():
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 10.0},
        "visual_events": [
            _make_event(0.0, 5.0, "ev_b01_1"),
            _make_event(5.0, 12.0, "ev_b01_2"),  # extends beyond span
        ],
    }]
    result = check_visual_event_coverage(beats)
    assert not result["feasible"]
    assert any(iss["type"] == "out_of_bounds" for iss in result["issues"])


def test_no_events_skipped():
    """Beats without visual_events are not coverage failures."""
    beats = [{"beat_id": "b01", "intended_duration_sec": {"min": 0, "max": 5.0}}]
    result = check_visual_event_coverage(beats)
    assert result["feasible"]


def test_measured_vo_segments_used_for_span():
    """When vo_segments are provided, measured duration overrides intended."""
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 20.0},  # intended is longer
        "visual_events": [
            _make_event(0.0, 7.0, "ev_b01_1"),
            _make_event(7.0, 14.0, "ev_b01_2"),
        ],
    }]
    vo_segments = [{"beat_id": "b01", "duration": 14.0, "text": "..."}]
    result = check_visual_event_coverage(beats, vo_segments=vo_segments)
    assert result["feasible"]  # events cover 14s measured span


def test_tolerance_allows_small_gaps():
    """Gaps within the configured event tolerance are not flagged."""
    beats = [{
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 10.0},
        "visual_events": [
            _make_event(0.0, 5.0, "ev_b01_1"),
            _make_event(5.1, 10.0, "ev_b01_2"),  # 0.1s gap — within tolerance
        ],
    }]
    result = check_visual_event_coverage(beats)
    assert result["feasible"]


# ── Talking-head motion coverage ─────────────────────────────────────────────


def _make_talking_head_beat(span=14.0):
    return {
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": span},
        "visual_intent": {
            "subject": "the founder",
            "action": "speaking directly to camera",
            "meaning": "talking head addressing the viewer",
        },
        "visual_events": [
            _make_event(0.0, span, "ev_b01_1", "generated_motion"),
        ],
    }


def test_talking_head_with_short_motion_blocked():
    """Draft 8 Artifact A: 14s beat, 5s motion, no cutaway → blocked."""
    beat = _make_talking_head_beat(14.0)
    result = check_talking_head_motion_coverage(
        [beat],
        motion_durations={"b01": 5.0},
    )
    assert not result["feasible"]
    assert any(iss["type"] == "generated_motion_shortfall" for iss in result["issues"])


def test_talking_head_with_enough_motion_passes():
    beat = _make_talking_head_beat(14.0)
    result = check_talking_head_motion_coverage(
        [beat],
        motion_durations={"b01": 14.0},
    )
    assert result["feasible"]


def test_talking_head_with_explicit_cutaway_passes():
    """A second event with a non-generated source policy counts as a cutaway."""
    beat = _make_talking_head_beat(14.0)
    beat["visual_events"] = [
        _make_event(0.0, 5.0, "ev_b01_1", "generated_motion"),
        _make_event(5.0, 14.0, "ev_b01_2", "operator_capture"),  # cutaway
    ]
    result = check_talking_head_motion_coverage(
        [beat],
        motion_durations={"b01": 5.0},
    )
    assert result["feasible"]


def test_motion_event_with_sufficient_source_passes():
    """Judgment stays in events; Python checks only requested motion duration."""
    beat = {
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 14.0},
        "visual_intent": {"subject": "a landscape", "meaning": "scenic context"},
        "visual_events": [_make_event(0.0, 5.0, "ev_b01_1", "generated_motion")],
    }
    result = check_talking_head_motion_coverage(
        [beat],
        motion_durations={"b01": 5.0},
    )
    assert result["feasible"]


def test_small_shortfall_within_tolerance():
    """Shortfall below the configured motion ratio is not flagged."""
    beat = _make_talking_head_beat(10.0)
    # 6s motion for 10s beat = 40% shortfall, below 50% threshold
    result = check_talking_head_motion_coverage(
        [beat],
        motion_durations={"b01": 6.0},
    )
    assert result["feasible"]


def test_measured_vo_used_for_talking_head_span():
    beat = _make_talking_head_beat(20.0)
    vo_segments = [{"beat_id": "b01", "duration": 14.0, "text": "..."}]
    result = check_talking_head_motion_coverage(
        [beat],
        vo_segments=vo_segments,
        motion_durations={"b01": 5.0},
    )
    assert not result["feasible"]  # 5s motion for 14s measured VO


# ── Integration with run_feasibility_checks ──────────────────────────────────


def test_run_feasibility_checks_includes_new_checks():
    """The runner includes visual_event_coverage and talking_head_motion."""
    plan = {"segments": [], "canvas": {}}
    result = run_feasibility_checks(plan, {}, beats=[], vo_segments=[])
    assert "visual_event_coverage" in result["checks"]
    assert "talking_head_motion" in result["checks"]


def test_run_feasibility_checks_blocks_draft8_pattern():
    """The Draft 8 Artifact A pattern is caught by the full runner."""
    plan = {"segments": [], "canvas": {}}
    beat = _make_talking_head_beat(14.0)
    result = run_feasibility_checks(
        plan,
        {},
        beats=[beat],
        vo_segments=[{"beat_id": "b01", "duration": 14.0, "text": "..."}],
        motion_durations={"b01": 5.0},
    )
    assert result["verdict"] == "needs_operator_decision"
    assert any("talking_head_motion_shortfall" in iss or "motion" in iss.lower() for iss in result["issues"])


def test_run_feasibility_checks_skips_new_checks_when_beats_none():
    """When beats=None, the new checks are skipped (backward compat)."""
    plan = {"segments": [], "canvas": {}}
    result = run_feasibility_checks(plan, {})
    assert result["checks"]["visual_event_coverage"]["feasible"] is True
    assert result["checks"]["talking_head_motion"]["feasible"] is True


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))