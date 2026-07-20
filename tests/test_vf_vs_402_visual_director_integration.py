"""VF-VS-402 production integration for the registered Visual Director."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from media_adapter import MediaAdapter
from pipeline import PipelineStore
from services.edit_planning import EditPlanningService


def test_visual_director_rejects_invented_audience_copy():
    output = {"beats": [{
        "beat_id": "b01",
        "visual_events": [{
            "event_id": "ev_b01_1",
            "time_range": {"start": 0.0, "end": 1.0},
            "narrative_function": "action",
            "source_policy": "renderer_graphic",
            "required_text": "New words the Writer never approved",
            "capture_policy_ref": None,
        }],
    }]}

    errors = EditPlanningService.validate_visual_director_output(
        output,
        [{"beat_id": "b01", "vo_text": "Approved words", "overlay_text": ""}],
    )

    assert any("invents audience text" in error for error in errors)


def test_visual_director_rejects_cumulative_timestamps_for_later_beats():
    output = {"beats": [
        {
            "beat_id": "b01",
            "visual_events": [{
                "event_id": "ev_b01_1",
                "time_range": {"start": 0.0, "end": 5.24},
                "narrative_function": "action",
                "source_policy": "generated_still",
                "required_text": None,
            }],
        },
        {
            "beat_id": "b02",
            "visual_events": [{
                "event_id": "ev_b02_1",
                "time_range": {"start": 5.24, "end": 11.32},
                "narrative_function": "context",
                "source_policy": "generated_still",
                "required_text": None,
            }],
        },
    ]}

    errors = EditPlanningService.validate_visual_director_output(
        output,
        [
            {"beat_id": "b01", "vo_text": "First approved beat."},
            {"beat_id": "b02", "vo_text": "Second approved beat."},
        ],
        vo_durations_by_beat={"b01": 5.24, "b02": 20.0},
    )

    assert any("ev_b02_1" in error and "beat-local" in error for error in errors)


def test_visual_director_malformed_mixed_start_types_fail_closed_without_crashing():
    output = {"beats": [{
        "beat_id": "b01",
        "visual_events": [
            {
                "event_id": "ev_b01_1",
                "time_range": {"start": "bad", "end": 1.0},
                "narrative_function": "action",
                "source_policy": "generated_still",
                "required_text": None,
            },
            {
                "event_id": "ev_b01_2",
                "time_range": {"start": 1.0, "end": 2.0},
                "narrative_function": "action",
                "source_policy": "generated_still",
                "required_text": None,
            },
        ],
    }]}

    errors = EditPlanningService.validate_visual_director_output(
        output,
        [{"beat_id": "b01", "vo_text": "Approved beat."}],
        vo_durations_by_beat={"b01": 2.0},
    )

    assert errors


def make_visual_reel(
    tmp_path,
    *,
    vo_duration=3.0,
    media_kind="image",
    visual_intent="Show the approved concept as a concrete action.",
):
    """Create one measured-VO Reel with approved visual intent and inventory."""
    db_path = str(tmp_path / "pipeline.db")
    store = PipelineStore(db_path)
    draft_id = store.create_draft(
        "stackpenni", 0, "test", format_name="Instagram Reel Script",
    )
    posts = [{
        "beat_id": "b01",
        "vo_text": "Approved words stay unchanged.",
        "visual_intent": visual_intent,
    }]
    store.save_draft_content(
        draft_id,
        "Approved draft",
        {},
        [],
        platform_content=[{"platform": "Instagram", "posts": posts}],
    )
    asset_id = store.create_asset(
        "stackpenni", draft_id, "Instagram", "reel", "Approved asset", posts=posts,
    )
    image_path = tmp_path / ("source.mp4" if media_kind == "video" else "source.png")
    image_path.write_bytes(b"media")
    media_id = MediaAdapter({"media": {}}, db_path=db_path)._record_media(
        asset_id, media_kind, str(image_path), "fixture", "source", 0,
    )
    vo_path = tmp_path / "vo.wav"
    vo_path.write_bytes(b"audio")
    store.save_vo_segments(asset_id, json.dumps([{
        "frame": 1,
        "beat_id": "b01",
        "text": posts[0]["vo_text"],
        "path": str(vo_path),
        "combined_path": str(vo_path),
        "duration": vo_duration,
        "take_id": "take_visual_001",
    }]))
    return db_path, store, asset_id, media_id


def test_shared_edit_planner_invokes_and_persists_visual_director(
    monkeypatch,
    tmp_path,
):
    db_path, store, asset_id, media_id = make_visual_reel(tmp_path)
    director_calls = []

    def fake_compose(process_name, business_slug, dynamic, **kwargs):
        director_calls.append((process_name, business_slug, dynamic))
        if process_name == "soundtrack_plan_v1":
            contract_id = json.loads(dynamic["content_contract"])["contract_id"]
            return ({
                "contract_id": contract_id,
                "mode": "vo_only",
                "music_bed_ref": None,
                "ducking": None,
                "sfx_cues": [],
                "vo_only_rationale": "The approved voice should stand alone.",
                "source_sound_rationale": None,
                "emotional_register": "direct",
                "search_queries": ["direct restrained pulse"],
                "operator_approval": None,
            }, "soundtrack-context:v1")
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

    monkeypatch.setattr("process_engine.compose_and_run", fake_compose)
    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", fake_complete)

    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 200
    assert director_calls[0][0:2] == ("visual_director_v1", "stackpenni")
    assert director_calls[0][2]["contract_beats"]
    assert json.loads(director_calls[0][2]["vo_timeline"]) == [{
        "beat_id": "b01",
        "duration_sec": 3.0,
        "time_range": {"start": 0.0, "end": 3.0},
    }]
    assert result.payload["plan"]["contract_beats"][0]["visual_events"][0][
        "event_id"
    ] == "ev_b01_1"
    assert result.payload["plan"]["visual_director_provenance"] == {
        "process": "visual_director_v1",
        "module_context": "visual-style:v1",
    }
    saved = store.get_edit_plan(result.payload["plan_id"])
    assert "ev_b01_1" in saved["plan_json"]
