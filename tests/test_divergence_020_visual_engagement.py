"""Tests for DIVERGENCE-020: visual engagement criteria — 4-second segment max."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.edit_planning import EditPlanningService


def _make_service(tmp_path):
    """Create an EditPlanningService with minimal deps."""
    return EditPlanningService(db_path=str(tmp_path / "test.db"))


def _make_beats(beat_ids=("b01",)):
    return [{"beat_id": bid, "required": True} for bid in beat_ids]


def test_segment_under_4s_passes(tmp_path):
    """Segments ≤4s with no overlay should pass."""
    svc = _make_service(tmp_path)
    segments = [
        {"segment_id": "s1", "source": "generated:1", "in": 0, "out": 3.5,
         "timeline_duration": 3.5, "beat_ids": ["b01"], "overlays": []},
    ]
    beats = _make_beats()
    errors = svc.validate_segments(segments, beats, {"generated:1"}, set())
    assert not any("exceeds" in e for e in errors), f"Should not have duration errors: {errors}"


def test_segment_over_4s_without_overlay_fails(tmp_path):
    """Segments >4s without an overlay should fail (DIVERGENCE-020)."""
    svc = _make_service(tmp_path)
    segments = [
        {"segment_id": "s1", "source": "generated:1", "in": 0, "out": 7.0,
         "timeline_duration": 7.0, "beat_ids": ["b01"], "overlays": []},
    ]
    beats = _make_beats()
    errors = svc.validate_segments(segments, beats, {"generated:1"}, set())
    assert any("exceeds" in e for e in errors), f"Should have duration error: {errors}"


def test_segment_over_4s_with_early_overlay_passes(tmp_path):
    """Segments >4s WITH an overlay at ≤4s should pass — the overlay IS the visual change."""
    svc = _make_service(tmp_path)
    segments = [
        {"segment_id": "s1", "source": "generated:1", "in": 0, "out": 7.0,
         "timeline_duration": 7.0, "beat_ids": ["b01"],
         "overlays": [{"type": "caption", "text": "key point", "start": 2.0, "end": 5.0}]},
    ]
    beats = _make_beats()
    errors = svc.validate_segments(segments, beats, {"generated:1"}, set())
    assert not any("exceeds" in e for e in errors), f"Should not have duration error with early overlay: {errors}"


def test_segment_over_4s_with_late_overlay_fails(tmp_path):
    """Segments >4s with an overlay only AFTER the 4s mark should still fail."""
    svc = _make_service(tmp_path)
    segments = [
        {"segment_id": "s1", "source": "generated:1", "in": 0, "out": 8.0,
         "timeline_duration": 8.0, "beat_ids": ["b01"],
         "overlays": [{"type": "caption", "text": "late", "start": 5.0, "end": 7.0}]},
    ]
    beats = _make_beats()
    errors = svc.validate_segments(segments, beats, {"generated:1"}, set())
    assert any("exceeds" in e for e in errors), f"Should have duration error (overlay too late): {errors}"


def test_segment_exactly_4s_passes(tmp_path):
    """Segment exactly at 4s boundary should pass."""
    svc = _make_service(tmp_path)
    segments = [
        {"segment_id": "s1", "source": "generated:1", "in": 0, "out": 4.0,
         "timeline_duration": 4.0, "beat_ids": ["b01"], "overlays": []},
    ]
    beats = _make_beats()
    errors = svc.validate_segments(segments, beats, {"generated:1"}, set())
    assert not any("exceeds" in e for e in errors), f"4.0s exactly should pass: {errors}"