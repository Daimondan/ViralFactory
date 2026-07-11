"""
Tests for T10.3 — Pre-render feasibility checks (AMENDMENT-008).

Key regression test: the 92s VO + 18s plan failure case must be caught
before render — the operator sees the mismatch, not a silently truncated video.
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from feasibility_checks import (
    compute_plan_timeline_duration,
    check_vo_timeline_feasibility,
    check_beat_mapping,
    run_feasibility_checks,
    DEFAULT_DURATION_TOLERANCE_S,
)


# ── compute_plan_timeline_duration ─────────────────────────────────────────

class TestComputePlanTimelineDuration:
    def test_video_segments_summed(self):
        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3.5},
                {"source": "generated:2", "in": 0, "out": 5.0},
                {"source": "upload:3", "in": 2.0, "out": 8.0},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }
        duration = compute_plan_timeline_duration(plan)
        assert duration == pytest.approx(3.5 + 5.0 + 6.0)

    def test_duration_target_overrides_if_longer(self):
        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 5.0},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 30},
        }
        duration = compute_plan_timeline_duration(plan)
        assert duration == 30.0

    def test_duration_target_not_used_if_shorter(self):
        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 15.0},
                {"source": "generated:2", "in": 0, "out": 15.0},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 10},
        }
        duration = compute_plan_timeline_duration(plan)
        assert duration == 30.0  # segment sum (30) > duration_target (10)

    def test_empty_plan(self):
        plan = {"segments": [], "canvas": {}}
        duration = compute_plan_timeline_duration(plan)
        assert duration == 0.0

    def test_image_segments_have_no_duration_from_plan(self):
        """Image segments (in=0, out=0) don't contribute to computed duration."""
        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 0},  # image
                {"source": "generated:2", "in": 0, "out": 5.0},  # video
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 18},
        }
        duration = compute_plan_timeline_duration(plan)
        # Image contributes 0, video contributes 5, duration_target=18 > 5, so 18
        assert duration == 18.0


# ── check_vo_timeline_feasibility ──────────────────────────────────────────

class TestVOTimelineFeasibility:
    def test_vo_fits_timeline(self):
        result = check_vo_timeline_feasibility(vo_duration=15.0, plan_timeline_duration=18.0)
        assert result["feasible"] is True
        assert result["mismatch"] is None

    def test_vo_within_tolerance(self):
        result = check_vo_timeline_feasibility(
            vo_duration=19.5, plan_timeline_duration=18.0, tolerance_s=2.0
        )
        assert result["feasible"] is True

    def test_vo_exceeds_timeline_beyond_tolerance(self):
        result = check_vo_timeline_feasibility(
            vo_duration=92.0, plan_timeline_duration=18.0, tolerance_s=2.0
        )
        assert result["feasible"] is False
        assert "92" in result["mismatch"]
        assert "18" in result["mismatch"]
        assert "74" in result["mismatch"]

    def test_no_vo_always_feasible(self):
        result = check_vo_timeline_feasibility(vo_duration=0, plan_timeline_duration=18.0)
        assert result["feasible"] is True

    def test_no_timeline_duration_feasible(self):
        result = check_vo_timeline_feasibility(vo_duration=30.0, plan_timeline_duration=0)
        assert result["feasible"] is True


# ── check_beat_mapping ──────────────────────────────────────────────────────

class TestBeatMapping:
    def _contract(self, beats):
        return {"beats": beats, "summary": "test"}

    def test_all_beats_mapped(self):
        contract = self._contract([
            {"beat_id": "b1", "required": True, "planned_segment_ids": ["seg_0"]},
            {"beat_id": "b2", "required": True, "planned_segment_ids": ["seg_1", "seg_2"]},
        ])
        plan = {"segments": [{"source": "generated:1", "in": 0, "out": 5}]}
        result = check_beat_mapping(contract, plan)
        assert result["feasible"] is True
        assert result["unmapped_beats"] == []

    def test_required_beat_with_no_mapping(self):
        contract = self._contract([
            {"beat_id": "b1", "required": True, "planned_segment_ids": ["seg_0"]},
            {"beat_id": "b2", "required": True, "planned_segment_ids": [],
             "source_excerpt": "The secret is in the process",
             "requirement_type": "spoken_dialogue"},
        ])
        plan = {"segments": [{"source": "generated:1", "in": 0, "out": 5}]}
        result = check_beat_mapping(contract, plan)
        assert result["feasible"] is False
        assert len(result["unmapped_beats"]) == 1
        assert result["unmapped_beats"][0]["beat_id"] == "b2"

    def test_optional_beat_without_mapping_ok(self):
        contract = self._contract([
            {"beat_id": "b1", "required": True, "planned_segment_ids": ["seg_0"]},
            {"beat_id": "b2", "required": False, "planned_segment_ids": []},
        ])
        plan = {"segments": [{"source": "generated:1", "in": 0, "out": 5}]}
        result = check_beat_mapping(contract, plan)
        assert result["feasible"] is True

    def test_no_contract(self):
        """No compliance contract — beat mapping is feasible (no constraints)."""
        result = check_beat_mapping(None, {"segments": []})
        assert result["feasible"] is True


# ── run_feasibility_checks (integration) ───────────────────────────────────

class TestRunFeasibilityChecks:
    def _plan_18s(self):
        """An 18-second plan (the failure case)."""
        return {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 6.0},
                {"source": "generated:2", "in": 0, "out": 6.0},
                {"source": "generated:3", "in": 0, "out": 6.0},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 18},
        }

    def _contract_with_vo_beats(self):
        """A contract with VO beats — the 92s VO case."""
        return {
            "beats": [
                {"beat_id": "b1", "source_excerpt": "Hook line",
                 "requirement_type": "hook", "required": True,
                 "planned_segment_ids": ["seg_0"], "verification_method": "keyframe_visual_match"},
                {"beat_id": "b2", "source_excerpt": "Main dialogue part 1",
                 "requirement_type": "spoken_dialogue", "required": True,
                 "planned_segment_ids": [], "verification_method": "audio_transcript_match"},
            ],
            "summary": "2 beats",
        }

    def test_92s_vo_18s_plan_regression(self):
        """THE key regression test: 92s VO + 18s plan must be caught."""
        result = run_feasibility_checks(
            plan=self._plan_18s(),
            compliance_contract=self._contract_with_vo_beats(),
            vo_duration=92.0,
        )
        assert result["feasible"] is False
        assert result["verdict"] == "needs_operator_decision"
        # Must mention the duration mismatch
        assert any("92" in issue for issue in result["issues"])
        # Must mention the unmapped beat
        assert any("b2" in issue for issue in result["issues"])

    def test_feasible_plan_passes(self):
        """A plan that fits VO and maps all beats passes."""
        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 30.0},
                {"source": "generated:2", "in": 0, "out": 30.0},
                {"source": "generated:3", "in": 0, "out": 35.0},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 95},
        }
        contract = {
            "beats": [
                {"beat_id": "b1", "source_excerpt": "Hook",
                 "requirement_type": "hook", "required": True,
                 "planned_segment_ids": ["0"], "verification_method": "keyframe_visual_match"},
                {"beat_id": "b2", "source_excerpt": "Dialogue",
                 "requirement_type": "spoken_dialogue", "required": True,
                 "planned_segment_ids": ["1", "2"], "verification_method": "audio_transcript_match"},
            ],
            "summary": "2 beats",
        }
        result = run_feasibility_checks(
            plan=plan,
            compliance_contract=contract,
            vo_duration=90.0,
        )
        assert result["feasible"] is True
        assert result["verdict"] == "feasible"

    def test_no_vo_no_contract_passes(self):
        """Silent visual piece with no VO and no contract passes."""
        plan = {
            "segments": [{"source": "generated:1", "in": 0, "out": 10.0}],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 10},
        }
        result = run_feasibility_checks(plan=plan, compliance_contract=None)
        assert result["feasible"] is True

    def test_vo_duration_only_no_contract(self):
        """VO duration check runs even without a contract."""
        result = run_feasibility_checks(
            plan=self._plan_18s(),
            compliance_contract=None,
            vo_duration=50.0,
        )
        assert result["feasible"] is False
        assert result["verdict"] == "needs_operator_decision"
        assert any("50" in issue for issue in result["issues"])

    def test_beat_mapping_only_no_vo(self):
        """Beat mapping check runs even without VO."""
        result = run_feasibility_checks(
            plan=self._plan_18s(),
            compliance_contract=self._contract_with_vo_beats(),
            vo_duration=None,
        )
        assert result["feasible"] is False
        assert any("b2" in issue for issue in result["issues"])