"""VF-VS-403 production invocation of visual-event feasibility checks."""

import sqlite3

from tests.test_vf_vs_402_visual_director_integration import make_visual_reel

from services.edit_planning import EditPlanningService


def test_five_second_motion_cannot_cover_fourteen_second_talking_head(
    monkeypatch,
    tmp_path,
):
    db_path, store, asset_id, media_id = make_visual_reel(
        tmp_path,
        vo_duration=14.0,
        media_kind="video",
        visual_intent="A person speaking on camera.",
    )

    def fake_compose(*args, **kwargs):
        return ({"beats": [{
            "beat_id": "b01",
            "visual_events": [{
                "event_id": "ev_b01_1",
                "time_range": {"start": 0.0, "end": 14.0},
                "narrative_function": "context",
                "source_policy": "generated_motion",
                "required_text": None,
                "capture_policy_ref": None,
            }],
        }]}, "visual-style:v1")

    def fake_complete(self, prompt_file, variables, schema, **kwargs):
        return {
            "segments": [{
                "segment_id": "seg_b01_1",
                "beat_ids": ["b01"],
                "source": f"asset_media:{media_id}",
                "source_in": 0,
                "source_out": 5,
                "timeline_duration": 14,
                "cue_ids": ["vo_b01"],
                "transition": "cut",
                "transition_reason": "opens the piece",
                "audio_contribution": "vo",
            }],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

    monkeypatch.setattr("process_engine.compose_and_run", fake_compose)
    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", fake_complete)

    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 422
    # DIVERGENCE-020: 14s segment with no overlay is now rejected by the
    # 4-second max validator before reaching feasibility checks.
    # This is the correct behavior — the segment must be split or have
    # a visual change at or before the 4-second mark.
    assert result.payload["status"] in ("invalid_plan", "needs_operator_decision")
    if result.payload["status"] == "invalid_plan":
        assert any("exceeds" in e.lower() for e in result.payload["errors"])
    else:
        assert any("motion" in issue.lower() for issue in result.payload["feasibility"]["issues"])


def test_infeasible_visual_events_block_plan_persistence(monkeypatch, tmp_path):
    db_path, store, asset_id, media_id = make_visual_reel(tmp_path)
    feasibility_calls = []

    def fake_compose(*args, **kwargs):
        return ({"beats": [{
            "beat_id": "b01",
            "visual_events": [{
                "event_id": "ev_b01_1",
                "time_range": {"start": 0.0, "end": 3.0},
                "narrative_function": "action",
                "source_policy": "approved_reference",
                "required_text": None,
                "capture_policy_ref": None,
            }],
        }]}, "visual-style:v1")

    def fake_complete(self, prompt_file, variables, schema, **kwargs):
        return {
            "segments": [{
                "segment_id": "seg_b01_1",
                "beat_ids": ["b01"],
                "source": f"asset_media:{media_id}",
                "source_in": 0,
                "source_out": 3,
                "timeline_duration": 3,
                "cue_ids": ["vo_b01"],
                "transition": "cut",
                "transition_reason": "opens the piece",
                "audio_contribution": "vo",
            }],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

    def fake_feasibility(**kwargs):
        feasibility_calls.append(kwargs)
        return {
            "feasible": False,
            "verdict": "needs_operator_decision",
            "checks": {
                "visual_event_coverage": {"feasible": False},
                "talking_head_motion": {"feasible": True},
            },
            "issues": ["Beat 'b01' has incomplete visual-event coverage"],
            "summary": "1 feasibility issue",
        }

    monkeypatch.setattr("process_engine.compose_and_run", fake_compose)
    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", fake_complete)
    monkeypatch.setattr("feasibility_checks.run_feasibility_checks", fake_feasibility)

    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 422
    assert result.payload["status"] == "needs_operator_decision"
    assert feasibility_calls[0]["beats"][0]["visual_events"][0]["event_id"] == "ev_b01_1"
    assert feasibility_calls[0]["vo_segments"][0]["take_id"] == "take_visual_001"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'edit_plans'"
        ).fetchone()[0] == 0
