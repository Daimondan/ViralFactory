"""VF-VS-502 production invocation and persistence for soundtrack planning."""

import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline import PipelineStore
from process_engine import compose_and_run
from services.edit_planning import EditPlanningService
from soundtrack_plan import make_vo_only_plan
from test_vf_vs_402_visual_director_integration import make_visual_reel


def _visual_output():
    return {"beats": [{
        "beat_id": "b01",
        "visual_events": [{
            "event_id": "ev_b01_1",
            "time_range": {"start": 0.0, "end": 3.0},
            "narrative_function": "action",
            "source_policy": "approved_reference",
            "required_text": None,
            "capture_policy_ref": None,
        }],
    }]}


def _soundtrack_output(contract_id, **overrides):
    output = make_vo_only_plan(
        contract_id,
        "The approved voice carries the intended emotional weight on its own.",
    )
    output["emotional_register"] = "direct"
    output.update(overrides)
    return output


def _edit_output(media_id):
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


def _run_planner(monkeypatch, tmp_path, soundtrack_factory):
    db_path, store, asset_id, media_id = make_visual_reel(tmp_path)
    process_calls = []

    def fake_compose(process_name, business_slug, dynamic, **kwargs):
        process_calls.append((process_name, business_slug, dynamic))
        if process_name == "visual_director_v1":
            return _visual_output(), "visual-style:v1"
        assert process_name == "soundtrack_plan_v1"
        contract_id = json.loads(dynamic["content_contract"])["contract_id"]
        return soundtrack_factory(contract_id), "soundtrack-context:v1"

    def fake_complete(self, prompt_file, variables, schema, **kwargs):
        return _edit_output(media_id)

    monkeypatch.setattr("process_engine.compose_and_run", fake_compose)
    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", fake_complete)
    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )
    return result, store, asset_id, process_calls


def test_shared_planner_invokes_validates_and_persists_soundtrack(monkeypatch, tmp_path):
    result, store, asset_id, calls = _run_planner(
        monkeypatch,
        tmp_path,
        lambda contract_id: _soundtrack_output(contract_id),
    )

    assert result.status_code == 200
    assert [call[0] for call in calls] == [
        "visual_director_v1", "soundtrack_plan_v1",
    ]
    soundtrack_call = calls[1]
    assert soundtrack_call[1] == "stackpenni"
    content_contract = json.loads(soundtrack_call[2]["content_contract"])
    assert content_contract["contract_id"] == f"asset:{asset_id}"
    assert content_contract["beats"][0]["vo_text"] == "Approved words stay unchanged."
    assert json.loads(soundtrack_call[2]["vo_timeline"])[0]["beat_id"] == "b01"
    assert json.loads(soundtrack_call[2]["audio_intents"])[0]["beat_id"] == "b01"

    stored_soundtracks = store.list_soundtrack_plans(asset_id)
    assert len(stored_soundtracks) == 1
    assert stored_soundtracks[0]["plan"]["mode"] == "vo_only"
    assert stored_soundtracks[0]["plan"]["emotional_register"] == "direct"
    assert stored_soundtracks[0]["plan"]["operator_approval"] is None

    reference = result.payload["plan"]["soundtrack_plan"]
    assert reference["soundtrack_plan_id"] == stored_soundtracks[0]["id"]
    assert result.payload["plan"]["soundtrack_planner_provenance"] == {
        "process": "soundtrack_plan_v1",
        "module_context": "soundtrack-context:v1",
    }
    saved_plan = json.loads(store.get_edit_plan(result.payload["plan_id"])["plan_json"])
    assert saved_plan["soundtrack_plan"] == reference
    assert saved_plan["soundtrack_planner_provenance"] == {
        "process": "soundtrack_plan_v1",
        "module_context": "soundtrack-context:v1",
    }


@pytest.mark.parametrize(
    ("factory", "expected_error"),
    [
        (
            lambda contract_id: _soundtrack_output(
                contract_id,
                operator_approval="invented-gate-token",
            ),
            "operator_approval",
        ),
        (
            lambda contract_id: _soundtrack_output("wrong-contract"),
            "contract_id",
        ),
        (
            lambda contract_id: _soundtrack_output(
                contract_id,
                emotional_register="",
            ),
            "emotional_register",
        ),
        (
            lambda contract_id: _soundtrack_output(
                contract_id,
                sfx_cues=[{
                    "event_id": "sfx_1",
                    "source": "",
                    "timestamp": 4.0,
                    "gain": 0.5,
                    "purpose": "",
                }],
            ),
            "sfx_cues",
        ),
    ],
)
def test_invalid_soundtrack_output_fails_before_any_plan_persists(
    monkeypatch,
    tmp_path,
    factory,
    expected_error,
):
    result, store, asset_id, _calls = _run_planner(
        monkeypatch,
        tmp_path,
        factory,
    )

    assert result.status_code == 422
    assert result.payload["status"] == "invalid_soundtrack_plan"
    assert any(expected_error in error for error in result.payload["errors"])
    assert store.list_edit_plans(asset_id) == []
    assert store.list_soundtrack_plans(asset_id) == []


def test_edit_and_soundtrack_plan_rollback_together_on_soundtrack_insert_failure(
    monkeypatch,
    tmp_path,
):
    db_path = str(tmp_path / "pipeline.db")
    store = PipelineStore(db_path)
    card_id = store.create_idea_card(
        "test-business", "Idea", ["Hook"], {}, "ai_originated",
    )
    draft_id = store.create_draft(
        "test-business", card_id, "ai_originated", "reel", "one_off",
    )
    asset_id = store.create_asset(
        "test-business", draft_id, "instagram", "reel", "Approved asset",
    )
    soundtrack = make_vo_only_plan(
        f"asset:{asset_id}",
        "The approved voice carries the intended emotional weight on its own.",
    )

    def fail_insert(*args, **kwargs):
        raise sqlite3.IntegrityError("forced soundtrack insert failure")

    monkeypatch.setattr(store, "_insert_soundtrack_plan", fail_insert)

    with pytest.raises(sqlite3.IntegrityError, match="forced"):
        store.save_edit_plan(
            draft_id,
            asset_id,
            {"segments": []},
            soundtrack_plan=soundtrack,
        )

    assert store.list_edit_plans(asset_id) == []
    assert store.list_soundtrack_plans(asset_id) == []


def test_registered_soundtrack_process_logs_real_adapter_provenance(
    monkeypatch,
    tmp_path,
):
    db_path = str(tmp_path / "provenance.db")
    contract_id = "asset:provenance"
    proposal = _soundtrack_output(contract_id)

    def fake_network_call(self, prompt, model, base_url, temperature, max_tokens):
        return json.dumps(proposal), 7

    monkeypatch.setattr(
        "llm_adapter.LLMAdapter._call_openai_compatible",
        fake_network_call,
    )
    models_config = {
        "active": {"default": "test_backend"},
        "test_backend": {
            "provider": "openai_compatible",
            "model": "test-soundtrack-model",
            "temperature": 0,
            "max_tokens": 1000,
            "base_url": "http://127.0.0.1:1",
        },
    }

    result, _module_provenance = compose_and_run(
        "soundtrack_plan_v1",
        "stackpenni",
        {
            "asset_id": 9,
            "content_contract": json.dumps({
                "contract_id": contract_id,
                "content": "Approved content.",
                "beats": [],
            }),
            "vo_timeline": json.dumps([{
                "beat_id": "b01",
                "start": 0.0,
                "end": 3.0,
            }]),
            "audio_intents": "[]",
        },
        models_config=models_config,
        db_path=db_path,
        config_dir=str(ROOT / "config"),
        modules_dir=str(ROOT / "modules"),
        prompts_dir=str(ROOT / "prompts"),
    )

    assert result == proposal
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT input_hash, prompt_file, prompt_version, model, provider,
                      raw_output, validated_output, validator_verdict, temperature,
                      business_slug
               FROM provenance ORDER BY id DESC LIMIT 1"""
        ).fetchone()

    assert len(row["input_hash"]) == 64
    assert row["prompt_file"] == "assembly/soundtrack_plan_v1.md"
    assert row["prompt_version"] == "1.0"
    assert row["model"] == "test-soundtrack-model"
    assert row["provider"] == "openai_compatible"
    assert json.loads(row["raw_output"]) == proposal
    assert json.loads(row["validated_output"]) == proposal
    assert row["validator_verdict"] == "valid"
    assert row["temperature"] == 0
    assert row["business_slug"] == "stackpenni"
