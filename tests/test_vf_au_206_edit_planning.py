"""Tests for VF-AU-206: Edit-planning service v2."""

import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from services.edit_planning import EditPlanningService


class TestSegmentValidation:
    def test_invented_source_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "fake:999"}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("fake:999" in e or "not in inventory" in e for e in errors)

    def test_valid_source_passes(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert errors == []

    def test_out_of_bounds_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1",
                      "source_in": 5.0, "source_out": 2.0}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("bounds" in e.lower() for e in errors)

    def test_missing_required_beat_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"}]
        beats = [{"beat_id": "b01", "required": True}, {"beat_id": "b02", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("b02" in e for e in errors)

    def test_unknown_beat_in_segment_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b99"], "source": "asset_media:1"}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("b99" in e for e in errors)

    def test_duplicate_segment_id_rejected(self):
        svc = EditPlanningService()
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"},
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:2"},
        ]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1", "asset_media:2"}, set())
        assert any("duplicate" in e.lower() for e in errors)

    def test_text_intent_reference_resolves(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1",
                      "text_intent_ids": ["t01"]}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, {"t01"})
        assert errors == []

    def test_unknown_text_intent_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1",
                      "text_intent_ids": ["t99"]}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, {"t01"})
        assert any("t99" in e for e in errors)

    def test_mixed_valid_invalid_sources(self):
        """In a plan with mixed valid and invalid sources, only invalid ones are flagged."""
        svc = EditPlanningService()
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"},  # valid
            {"segment_id": "s02", "beat_ids": ["b02"], "source": "fake:999"},       # invalid
        ]
        beats = [{"beat_id": "b01", "required": True}, {"beat_id": "b02", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        # Should flag the invalid source but not the valid one
        assert any("fake:999" in e for e in errors)
        assert not any("asset_media:1" in e for e in errors if "not in inventory" in e)