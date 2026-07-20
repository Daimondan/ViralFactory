"""VF-VS-103 behavioral equivalence for operator and autonomous edit planning."""

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import create_app
from media_adapter import MediaAdapter
from pipeline import PipelineStore
from produce_chain import ProductionChain


def test_operator_and_autonomous_paths_produce_equivalent_edit_plans(monkeypatch, tmp_path):
    db_path = str(tmp_path / "pipeline.db")
    app = create_app(config_dir=str(ROOT / "config"), db_path=db_path)
    store = PipelineStore(db_path=db_path)
    draft_id = store.create_draft(
        "stackpenni",
        0,
        "test",
        format_name="Instagram Reel Script",
    )
    store.save_draft_content(draft_id, "Approved draft", {}, [], platform_content=[])
    asset_id = store.create_asset(
        "stackpenni",
        draft_id,
        "Instagram",
        "reel",
        "Approved voice-led asset",
        posts=[{"beat_id": "b01", "vo_text": "Approved voice-over."}],
    )
    image_path = tmp_path / "approved-source.png"
    image_path.write_bytes(b"fixture image")
    media_id = MediaAdapter({"media": {}}, db_path=db_path)._record_media(
        asset_id,
        "image",
        str(image_path),
        "fixture",
        "approved visual source",
        0,
    )
    ingredient_id = f"asset_media:{media_id}"
    combined_path = tmp_path / "complete-take.wav"
    segment_path = tmp_path / "vo-b01.wav"
    combined_path.write_bytes(b"combined audio fixture")
    segment_path.write_bytes(b"audio fixture")
    store.save_vo_segments(asset_id, json.dumps([{
        "frame": 1,
        "beat_id": "b01",
        "text": "Approved voice-over.",
        "path": str(segment_path),
        "combined_path": str(combined_path),
        "duration": 3.0,
        "take_id": "take_equivalence_001",
    }]))
    deterministic_plan = {
        "canvas": {
            "aspect_ratio": "9:16",
            "resolution": "1080x1920",
        },
        "segments": [{
            "segment_id": "seg_b01_1",
            "beat_ids": ["b01"],
            "source": ingredient_id,
            "source_in": 0,
            "source_out": 3,
            "timeline_duration": 3,
            "cue_ids": ["vo_b01"],
            "transition": "cut",
            "transition_reason": "opens the piece",
            "audio_contribution": "vo",
        }],
    }
    llm_calls = []
    premature_discovery_calls = []

    def premature_discovery(*args, **kwargs):
        premature_discovery_calls.append((args, kwargs))
        return {"candidates": [], "queries": [], "errors": ["fixture failure"]}

    def deterministic_complete(self, prompt_file, variables, schema, **kwargs):
        llm_calls.append({
            "prompt_file": prompt_file,
            "variables": variables,
            "schema": schema,
            "business_slug": kwargs.get("business_slug"),
        })
        if prompt_file == "assembly/soundtrack_plan_v1.md":
            contract_id = json.loads(variables["content_contract"])["contract_id"]
            return {
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
            }
        return deterministic_plan

    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", deterministic_complete)
    monkeypatch.setattr(
        "soundtrack_discovery.discover_soundtrack_candidates",
        premature_discovery,
    )

    route_response = app.test_client().post(
        f"/api/assets/{asset_id}/edit-plan",
        json={},
    )
    assert route_response.status_code == 200
    route_result = route_response.get_json()

    chain = ProductionChain(
        db_path=db_path,
        config_dir=str(ROOT / "config"),
        modules_dir=str(ROOT / "modules"),
        prompts_dir=str(ROOT / "prompts"),
    )
    chain._step_edit_plan(draft_id, 0, "stackpenni", store)
    chain_result = store._get_step_data(draft_id, "edit_plan_result")

    assert route_result["status"] == chain_result["status"] == "ok"
    assert premature_discovery_calls == []
    assert "soundtrack_auto_processed" not in route_result["plan"]
    assert "soundtrack_ranking" not in route_result["plan"]
    route_plan = json.loads(json.dumps(route_result["plan"]))
    chain_plan = json.loads(json.dumps(chain_result["plan"]))
    route_plan["soundtrack_plan"].pop("soundtrack_plan_id")
    chain_plan["soundtrack_plan"].pop("soundtrack_plan_id")
    assert route_plan == chain_plan
    assert route_result["plan"]["audio"]["vo"]["take_id"] == "take_equivalence_001"
    assert route_result["plan"]["canvas"]["duration_target"] == 3.0
    assert route_result["plan"]["segments"][0]["ingredient_id"] == ingredient_id
    assert route_result["cut_list"] == chain_result["cut_list"]
    assert route_result["plan_id"] != chain_result["plan_id"]
    assert len(llm_calls) == 4
    assert llm_calls[:2] == llm_calls[2:]

    route_saved = store.get_edit_plan(route_result["plan_id"])
    chain_saved = store.get_edit_plan(chain_result["plan_id"])
    for field in ("compliance_contract_json", "source_draft_hash"):
        assert route_saved[field] == chain_saved[field]

    route_saved_plan = json.loads(route_saved["plan_json"])
    chain_saved_plan = json.loads(chain_saved["plan_json"])
    route_saved_plan["soundtrack_plan"].pop("soundtrack_plan_id")
    chain_saved_plan["soundtrack_plan"].pop("soundtrack_plan_id")
    assert route_saved_plan == chain_saved_plan
