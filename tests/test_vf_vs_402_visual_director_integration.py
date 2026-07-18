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
    assert director_calls[0][2]["vo_timeline"]
    assert result.payload["plan"]["contract_beats"][0]["visual_events"][0][
        "event_id"
    ] == "ev_b01_1"
    assert result.payload["plan"]["visual_director_provenance"] == {
        "process": "visual_director_v1",
        "module_context": "visual-style:v1",
    }
    saved = store.get_edit_plan(result.payload["plan_id"])
    assert "ev_b01_1" in saved["plan_json"]
