"""Operator-reported regressions in the non-blocking capture flow."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import create_app
from pipeline import PipelineStore


BUSINESS_SLUG = "stackpenni"


def test_idea_prompts_exclude_production_outputs_from_required_capture():
    prompts = {
        "prompts/ideas/generate_v1.md": "<!-- version: 2.1 -->",
        "prompts/ideas/treatment_select_v1.md": "<!-- version: 1.1 -->",
    }
    for path, version in prompts.items():
        content = Path(path).read_text()
        assert version in content
        assert "Do not list production outputs as capture_required" in content
        assert "Do not require generic context that downstream production may generate" in content


def _make_card(tmp_path):
    db_path = str(tmp_path / "capture.db")
    app = create_app(config_dir="config", db_path=db_path)
    app.config["TESTING"] = True
    store = PipelineStore(db_path)
    card_id = store.create_idea_card(
        business_slug=BUSINESS_SLUG,
        idea="A test idea that needs real capture",
        hook_options=["A useful hook"],
        treatment={
            "scope": {"type": "one_off"},
            "format": {"format_name": "Instagram Reel Script"},
            "capture_required": [
                "Real footage of a gathering",
                "Real footage of a work session",
            ],
            "rationale": "The real setting is part of the evidence.",
        },
        origin="ai_originated",
    )
    return app, store, card_id


def test_new_card_with_capture_keeps_gate_one_approve_action(tmp_path):
    app, _store, card_id = _make_card(tmp_path)

    response = app.test_client().get("/ideas?tab=queue")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"cardAction({card_id}, 'approve')" in body
    assert f'/ideas/{card_id}/capture' in body
    assert "Add real capture" in body
    assert "Upload capture first" not in body
    assert "approving without it will stall" not in body


def test_approved_capture_card_does_not_offer_duplicate_approval(tmp_path):
    app, store, card_id = _make_card(tmp_path)
    store.update_card_state(card_id, "approved")

    response = app.test_client().get("/ideas?tab=approved")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"cardAction({card_id}, 'approve')" not in body
    assert f'/create/draft/{card_id}' in body
    assert f'/ideas/{card_id}/capture' in body
    assert "Add real capture" in body


def test_capture_page_is_non_blocking_and_has_no_legacy_ai_generator(tmp_path):
    app, _store, card_id = _make_card(tmp_path)

    response = app.test_client().get(f"/ideas/{card_id}/capture")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Continue to idea review" in body
    assert "production can continue before capture is added" in body
    assert "Generate missing capture with AI" not in body
    assert "task-icon done" not in body


def test_legacy_ai_capture_generation_fails_closed_before_media_call(tmp_path, monkeypatch):
    app, _store, card_id = _make_card(tmp_path)
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("paid media generation must not run")

    monkeypatch.setattr("media_adapter.MediaAdapter.generate_image", fail_if_called)

    response = app.test_client().post(
        f"/api/ideas/{card_id}/generate-capture",
        json={},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error": (
            "AI-generated media cannot fulfill required real capture. "
            "Approve the idea to continue production and add real material before final review."
        )
    }
    assert called is False


def test_capture_upload_does_not_bypass_gate_one_state(tmp_path):
    app, store, card_id = _make_card(tmp_path)

    client = app.test_client()
    response = None
    for content in ("Operator-supplied field note", "Operator-supplied video note"):
        response = client.post(
            f"/api/ideas/{card_id}/capture-upload",
            json={"content": content},
        )

    assert response.status_code == 200
    card = store.get_idea_card(card_id)
    assert card["card_state"] == "new"
    assert len(json.loads(card["capture_uploads"])) == 2
