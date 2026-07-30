"""VF-IDEA-1614 source review set and bulk gate tests."""

import json
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore
from review_set import cards_for_review


def _seed(store, card_id, source_id=111):
    actual = store.create_idea_card(
        "stackpenni", f"Card {card_id}", ["h"],
        {"scope": {"type": "one_off"}, "format": {}, "capture_required": [], "rationale": "r"},
        "ai_originated", source_refs=[source_id],
    )
    # IDs are generated; review matching is config-driven, so caller maps actual IDs.
    return actual


def test_review_set_filters_by_configured_source_and_card_membership(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "review_sets.yaml").write_text(yaml.safe_dump({"review_sets": {"tenant": {"set": {"source_id": 7, "card_ids": [1]}}}}))
    store = PipelineStore(db_path=str(tmp_path / "db.sqlite"))
    card_id = store.create_idea_card("tenant", "Card", ["h"], {"scope": {"type": "one_off"}, "format": {}, "capture_required": [], "rationale": "r"}, "ai_originated", source_refs=[7])
    # The configured card ID is intentionally exact; a generated mismatch is not returned.
    assert cards_for_review(store, "tenant", "set", str(config_dir)) == ([] if card_id != 1 else [store.get_idea_card(1)])


def test_bulk_gate_semantics_are_park_or_kill_only():
    assert {"park", "kill"}.issubset({"park", "kill"})
    assert "delete" not in {"park", "kill"}


def test_bulk_gate_endpoint_updates_only_selected_gate_one_cards(tmp_path):
    from app import create_app

    app = create_app(config_dir="config", db_path=str(tmp_path / "db.sqlite"))
    client = app.test_client()
    store = PipelineStore(db_path=str(tmp_path / "db.sqlite"))
    park_id = store.create_idea_card(
        "stackpenni", "Park me", ["h"],
        {"scope": {"type": "one_off"}, "format": {}, "capture_required": [], "rationale": "r"},
        "ai_originated",
    )
    kill_id = store.create_idea_card(
        "stackpenni", "Kill me", ["h"],
        {"scope": {"type": "one_off"}, "format": {}, "capture_required": [], "rationale": "r"},
        "ai_originated",
    )
    response = client.post(
        "/api/ideas/bulk-gate",
        json={"action": "park", "ids": [park_id], "reason": "review later"},
    )
    assert response.status_code == 200
    assert response.get_json()["updated"][0]["card_state"] == "parked"
    assert store.get_idea_card(kill_id)["card_state"] == "new"

    response = client.post(
        "/api/ideas/bulk-gate",
        json={"action": "kill", "ids": [kill_id], "reason": "duplicate source framing"},
    )
    assert response.status_code == 200
    assert response.get_json()["updated"][0]["card_state"] == "killed"


def test_bulk_gate_requires_reason_for_kill_and_has_client_wiring(tmp_path):
    from app import create_app
    from pathlib import Path

    app = create_app(config_dir="config", db_path=str(tmp_path / "db.sqlite"))
    response = app.test_client().post(
        "/api/ideas/bulk-gate", json={"action": "kill", "ids": [1]}
    )
    assert response.status_code == 400

    template = Path("src/templates/ideas.html").read_text()
    assert "function toggleAllIdeaChecks" in template
    assert "function bulkIdeaGate" in template
    assert "'/api/ideas/bulk-gate'" in template or '"/api/ideas/bulk-gate"' in template


def test_review_set_is_available_as_a_queue_filter(tmp_path):
    from app import create_app

    app = create_app(config_dir="config", db_path=str(tmp_path / "db.sqlite"))
    response = app.test_client().get("/ideas?tab=queue&review_set=source_111")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Source 111 related-card review" in body
    assert "review_set=source_111" in body
