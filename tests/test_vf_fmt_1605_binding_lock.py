"""VF-FMT-1605: Gate-1 production-binding lock and writer hash boundary."""

import copy
import json
import os
import sys
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore, lock_approved_production_binding
from production_contract import assemble_contract, compute_writer_contract_hash


BINDING = {
    "mode": "episode",
    "process_ref": "episode-format",
    "governance_module_ref": "episode-format-parable",
    "governance_module_version": "1.0",
}


def _content(binding=None):
    result = {
        "contract_id": "c1605",
        "core_claim": "claim",
        "audience_value": "value",
        "evidence_refs": ["source:1"],
        "primary_emotional_job": "conviction",
        "primary_audience_action": "save",
        "format_name": "reel",
        "platform": "instagram",
        "capture_policy": "generated_allowed",
        "evidence_label": "HYPOTHESIS",
    }
    if binding is not None:
        result["production_binding"] = binding
    return result


def _treatment(binding=None):
    fmt = {"format_name": "Reel", "experimental": False}
    if binding is not None:
        fmt["production_binding"] = binding
    return {
        "scope": {"type": "one_off"},
        "format": fmt,
        "capture_required": [],
        "reuse": {},
        "rationale": "fixture",
    }


def _app(tmp_path):
    from app import create_app

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "business.yaml").write_text(
        yaml.safe_dump(
            {
                "business": {"name": "TestBiz", "slug": "testbiz", "description": "test business"},
                "subjects": ["test"],
                "platforms": [{"name": "Instagram", "handle": "@test"}],
                "audience_description": "test audience",
            }
        )
    )
    (config_dir / "models.yaml").write_text(
        yaml.safe_dump(
            {
                "active": {"default": "test", "drafter": "test", "ideator": "test"},
                "test": {"provider": "test", "model": "test", "temperature": 0, "max_tokens": 100},
            }
        )
    )
    (config_dir / "sources.yaml").write_text(yaml.safe_dump({"feeds": [], "channels": [], "queries": []}))
    app = create_app(config_dir=str(config_dir), db_path=str(tmp_path / "vf.db"))
    app.config["TESTING"] = True
    return app


def test_lock_copies_selected_binding_without_aliasing():
    treatment = _treatment(BINDING)
    locked = lock_approved_production_binding(treatment)
    assert locked["production_binding"] == BINDING
    assert locked["production_binding"] is not treatment["format"]["production_binding"]

    treatment["format"]["production_binding"]["mode"] = "standard"
    assert locked["production_binding"]["mode"] == "episode"


def test_lock_does_not_infer_episode_when_binding_is_missing():
    locked = lock_approved_production_binding(_treatment())
    assert locked["production_binding"] is None


def test_gate_approval_persists_locked_binding_before_writer_chain(tmp_path):
    app = _app(tmp_path)
    store = PipelineStore(app.config["DB_PATH"])
    card_id = store.create_idea_card(
        business_slug="testbiz",
        idea="Episode-bound idea",
        hook_options=["hook"],
        treatment=_treatment(BINDING),
        origin="ai_originated",
    )

    with patch("produce_chain.enqueue_writer_chain") as enqueue:
        response = app.test_client().post(
            f"/api/ideas/{card_id}/gate", json={"action": "approve"}
        )

    assert response.status_code == 200
    stored = store.get_idea_card(card_id)
    stored_treatment = json.loads(stored["treatment"])
    assert stored_treatment["production_binding"] == BINDING
    enqueue.assert_called_once()


def test_writer_contract_hash_changes_when_approved_binding_changes():
    base = {
        "platform_content": [{"platform": "Instagram", "content": "text"}],
        "beats": [],
        "primary_audience_action": "save",
        "capture_policy": "generated_allowed",
    }
    standard = dict(base, production_binding={"mode": "standard"})
    episode = dict(base, production_binding=BINDING)
    assert compute_writer_contract_hash(standard) != compute_writer_contract_hash(episode)


def test_assembled_contract_hash_includes_approved_binding():
    standard = assemble_contract(_content({"mode": "standard"}), [])
    episode = assemble_contract(_content(BINDING), [])
    assert standard["writer_contract_hash"] != episode["writer_contract_hash"]
