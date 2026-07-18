"""VF-VS-503 production soundtrack preview and approval gate.

Behavioral coverage for the shared render boundary, HTTP operator controls, and
autonomous-chain pause. Decisions bind to the exact immutable soundtrack plan.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline import PipelineStore
from services.render_review import RenderReviewService
from soundtrack_gate import SoundtrackPreviewGate, SoundtrackGateError
from soundtrack_plan import compute_soundtrack_plan_hash


def _vo_only(contract_id: str = "contract-503") -> dict:
    return {
        "contract_id": contract_id,
        "mode": "vo_only",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": "The approved voice carries the intended emotional arc.",
        "source_sound_rationale": None,
        "emotional_register": "direct and grounded",
        "operator_approval": None,
    }


def _music(contract_id: str = "contract-503") -> dict:
    return {
        "contract_id": contract_id,
        "mode": "music_bed",
        "music_bed_ref": {
            "source_id": "/audio/bed.wav",
            "licence": {
                "type": "royalty_free",
                "id": "lic-503",
                "url": "https://example.invalid/licence/503",
            },
            "cost_usd": 0.0,
        },
        "ducking": {"attenuation_db": -12.0, "envelope": []},
        "sfx_cues": [],
        "vo_only_rationale": None,
        "source_sound_rationale": None,
        "emotional_register": "warm forward motion",
        "operator_approval": None,
    }


def _persist_asset_plan(
    tmp_path: Path,
    soundtrack: dict | None = None,
    *,
    include_source_media: bool = False,
):
    store = PipelineStore(str(tmp_path / "gate.db"))
    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)
    vo_path = media_dir / "vo.wav"
    with wave.open(str(vo_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000)
    soundtrack = json.loads(json.dumps(soundtrack or _vo_only()))
    if soundtrack.get("music_bed_ref"):
        bed_path = media_dir / "bed.wav"
        with wave.open(str(bed_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8000)
        soundtrack["music_bed_ref"]["source_id"] = str(bed_path)
    card_id = store.create_idea_card(
        "test-business",
        "Gate test",
        ["Hook"],
        {
            "scope": {"type": "one_off"},
            "format": {"format_name": "reel", "experimental": False},
            "capture_required": [],
            "rationale": "test",
        },
        "ai_originated",
    )
    draft_id = store.create_draft(
        "test-business", card_id, "ai_originated", "reel", "one_off"
    )
    asset_id = store.create_asset(
        "test-business", draft_id, "instagram", "reel", "Approved copy", [], []
    )
    source_segments = []
    if include_source_media:
        from media_adapter import MediaAdapter

        source_path = media_dir / "source.wav"
        with wave.open(str(source_path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\x00\x00" * 8000)
        media_id = MediaAdapter({"media": {}}, db_path=store.db_path)._record_media(
            asset_id,
            "video",
            str(source_path),
            "fixture",
            "source sound fixture",
            0,
        )
        source_segments = [{
            "segment_id": "source-sound-segment",
            "source": f"asset_media:{media_id}",
            "audio_contribution": "source",
        }]
    plan = {
        "canvas": {"duration_target": 3.0},
        "audio": {"vo": {"take_id": "take-503", "path": str(vo_path)}},
        "segments": source_segments,
        "feasibility": {
            "feasible": True,
            "verdict": "feasible",
            "summary": "All required checks passed.",
            "checks": {
                name: {"feasible": True}
                for name in RenderReviewService._REQUIRED_FEASIBILITY_CHECKS
            },
        },
    }
    edit_plan_id = store.save_edit_plan(
        draft_id,
        asset_id,
        plan,
        soundtrack_plan=soundtrack,
    )
    return store, card_id, draft_id, asset_id, edit_plan_id


def test_gate_mints_token_and_decisions_are_append_only(tmp_path):
    gate = SoundtrackPreviewGate(str(tmp_path / "gate.db"))
    plan_hash = compute_soundtrack_plan_hash(_vo_only())

    gate.record_rejection(
        "contract-503", "test-business", plan_hash, "vo_only", "Try music."
    )
    approval = gate.record_approval(
        "contract-503", "test-business", plan_hash, "vo_only"
    )

    assert approval["gate_token"].startswith("soundtrack_gate_")
    with sqlite3.connect(gate.db_path) as conn:
        rows = conn.execute(
            "SELECT verdict, gate_token FROM soundtrack_approvals ORDER BY id"
        ).fetchall()
    assert [row[0] for row in rows] == ["rejected", "approved"]
    assert rows[0][1] is None
    assert rows[1][1] == approval["gate_token"]
    assert gate.require_approval("contract-503", plan_hash)["verdict"] == "approved"


def test_gate_rejects_caller_supplied_token(tmp_path):
    gate = SoundtrackPreviewGate(str(tmp_path / "gate.db"))
    result = gate.record_approval(
        "contract-503",
        "test-business",
        compute_soundtrack_plan_hash(_vo_only()),
        "vo_only",
        reason="caller-token",
    )
    assert result["gate_token"] != "caller-token"
    with pytest.raises(TypeError):
        gate.record_approval(
            "contract-503",
            "test-business",
            compute_soundtrack_plan_hash(_vo_only()),
            "vo_only",
            gate_token="caller-token",
        )


def test_render_blocks_exact_current_soundtrack_before_renderer(tmp_path):
    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path)
    renderer = MagicMock()
    service = RenderReviewService(
        db_path=store.db_path,
        renderer=renderer,
        reviewer=MagicMock(),
        models_config={},
    )

    result = service.render_for_asset(
        asset_id=asset_id,
        plan_id=edit_plan_id,
        business_slug="test-business",
        store=store,
    )

    assert result.status_code == 409
    assert result.payload["status"] == "soundtrack_approval_required"
    renderer.render.assert_not_called()


def test_render_rejects_approval_for_stale_replaced_hash(tmp_path):
    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _vo_only())
    old = store.list_soundtrack_plans(asset_id)[0]
    gate = SoundtrackPreviewGate(store.db_path)
    gate.record_approval(old["contract_id"], "test-business", old["plan_hash"], "vo_only")
    replacement = store.save_soundtrack_plan(asset_id, edit_plan_id, _music())

    renderer = MagicMock()
    result = RenderReviewService(
        db_path=store.db_path,
        renderer=renderer,
        reviewer=MagicMock(),
        models_config={},
    ).render_for_asset(
        asset_id=asset_id,
        plan_id=edit_plan_id,
        business_slug="test-business",
        store=store,
    )

    assert replacement["plan_hash"] != old["plan_hash"]
    assert result.status_code == 409
    assert result.payload["status"] == "soundtrack_approval_required"
    renderer.render.assert_not_called()


def test_explicit_vo_only_creates_and_approves_new_immutable_plan(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _music())
    old = store.list_soundtrack_plans(asset_id)[0]
    service = SoundtrackReviewService(store.db_path)
    service.acknowledge_preview(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        business_slug="test-business",
        store=store,
    )
    result = service.decide(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        action="vo_only",
        business_slug="test-business",
        reason="The voice should carry this piece without a bed.",
        store=store,
    )

    assert result.ok
    assert result.payload["status"] == "approved"
    assert result.payload["mode"] == "vo_only"
    plans = store.list_soundtrack_plans(asset_id)
    assert len(plans) == 2
    assert plans[0]["plan_hash"] != old["plan_hash"]
    assert plans[0]["plan"]["vo_only_rationale"] == (
        "The voice should carry this piece without a bed."
    )
    assert SoundtrackPreviewGate(store.db_path).is_approved(
        plans[0]["contract_id"], plans[0]["plan_hash"]
    )


def test_replace_selects_same_edit_plan_alternative_and_requires_fresh_approval(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _vo_only())
    vo_alternative = store.list_soundtrack_plans(asset_id)[0]
    music_reference = store.save_soundtrack_plan(asset_id, edit_plan_id, _music())
    current_music = store.get_soundtrack_plan(music_reference["soundtrack_plan_id"])

    result = SoundtrackReviewService(store.db_path).decide(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        action="replace",
        business_slug="test-business",
        replacement_plan_id=vo_alternative["id"],
        reason="Use the quieter alternate.",
        store=store,
    )

    assert result.ok
    assert result.payload["status"] == "replacement_selected"
    persisted_edit = json.loads(store.get_edit_plan(edit_plan_id)["plan_json"])
    assert persisted_edit["soundtrack_plan"]["soundtrack_plan_id"] == vo_alternative["id"]
    replaced = SoundtrackPreviewGate(store.db_path).get_approval(
        current_music["contract_id"], current_music["plan_hash"]
    )
    assert replaced["verdict"] == "replaced"
    assert not SoundtrackPreviewGate(store.db_path).is_approved(
        vo_alternative["contract_id"], vo_alternative["plan_hash"]
    )


def test_service_approval_fails_until_exact_plan_preview_is_acknowledged(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _vo_only())
    service = SoundtrackReviewService(store.db_path)
    blocked = service.decide(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        action="approve",
        business_slug="test-business",
        store=store,
    )
    assert blocked.status_code == 409
    assert "listen" in blocked.payload["error"].lower()

    service.acknowledge_preview(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        business_slug="test-business",
        store=store,
    )
    approved = service.decide(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        action="approve",
        business_slug="test-business",
        store=store,
    )
    assert approved.ok
    assert approved.payload["status"] == "approved"


def test_replace_requires_same_asset_persisted_plan(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _vo_only())
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    other_store, _, _, other_asset_id, _ = _persist_asset_plan(other_dir, _music())
    # Copy an unrelated row into this DB to exercise ownership checks.
    unrelated = other_store.list_soundtrack_plans(other_asset_id)[0]
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """INSERT INTO soundtrack_plans
               (contract_id, asset_id, edit_plan_id, plan_version, plan_json,
                plan_hash, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                unrelated["contract_id"],
                asset_id + 999,
                edit_plan_id + 999,
                unrelated["plan_version"],
                json.dumps(unrelated["plan"]),
                unrelated["plan_hash"],
                "proposed",
                unrelated["created_at"],
            ),
        )
        replacement_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()

    result = SoundtrackReviewService(store.db_path).decide(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        action="replace",
        business_slug="test-business",
        replacement_plan_id=replacement_id,
        reason="Use the alternate.",
        store=store,
    )
    assert result.status_code == 409
    assert "does not belong" in result.payload["error"]


def test_preview_payload_uses_persisted_current_plan(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _vo_only())
    result = SoundtrackReviewService(store.db_path).get_review(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        store=store,
    )
    assert result.ok
    assert result.payload["mode"] == "vo_only"
    assert result.payload["approval"]["approved"] is False
    assert result.payload["preview"]["tracks"][0]["file"] == "/media/vo.wav"
    assert result.payload["current"] is True


def test_autonomous_chain_pauses_before_render_and_resumes_after_approval(tmp_path, monkeypatch):
    from produce_chain import ProductionChain

    store, card_id, draft_id, asset_id, edit_plan_id = _persist_asset_plan(tmp_path)
    chain = ProductionChain(
        db_path=store.db_path,
        config_dir=str(ROOT / "config"),
        modules_dir=str(ROOT / "modules"),
        prompts_dir=str(ROOT / "prompts"),
    )
    for name in ("_step_fanout", "_step_vo", "_step_media_plan", "_step_media_exec", "_step_edit_plan"):
        monkeypatch.setattr(chain, name, MagicMock())
    render = MagicMock()
    monkeypatch.setattr(chain, "_step_render", render)

    chain.run_assembler_chain(draft_id, card_id, "test-business")
    assert store.get_idea_card(card_id)["card_state"] == "awaiting_soundtrack_approval"
    render.assert_not_called()

    current = store.list_soundtrack_plans(asset_id)[0]
    SoundtrackPreviewGate(store.db_path).record_approval(
        current["contract_id"], "test-business", current["plan_hash"], current["plan"]["mode"]
    )
    chain.run_assembler_chain(draft_id, card_id, "test-business")
    render.assert_called_once()
    assert store.get_idea_card(card_id)["card_state"] == "asset_ready"


def test_missing_source_sound_media_cannot_be_acknowledged(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    source_sound = {
        "contract_id": "contract-503",
        "mode": "source_sound",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": None,
        "source_sound_rationale": "The selected footage carries the intended scene audio.",
        "emotional_register": "grounded",
        "operator_approval": None,
    }
    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, source_sound)
    service = SoundtrackReviewService(store.db_path)
    review = service.get_review(
        asset_id=asset_id, edit_plan_id=edit_plan_id, store=store
    )
    assert review.payload["preview_ready"] is False
    blocked = service.acknowledge_preview(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        business_slug="test-business",
        store=store,
    )
    assert blocked.status_code == 409
    assert "playable" in blocked.payload["error"]


def test_source_sound_preview_uses_selected_asset_media(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    source_sound = {
        "contract_id": "contract-503",
        "mode": "source_sound",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": [],
        "vo_only_rationale": None,
        "source_sound_rationale": "The selected footage carries the intended scene audio.",
        "emotional_register": "grounded",
        "operator_approval": None,
    }
    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(
        tmp_path, source_sound, include_source_media=True
    )
    result = SoundtrackReviewService(store.db_path).get_review(
        asset_id=asset_id, edit_plan_id=edit_plan_id, store=store
    )
    assert result.ok
    assert result.payload["preview_ready"] is True
    assert result.payload["preview"]["tracks"] == [{
        "name": "source_sound",
        "file": "/media/source.wav",
        "description": "Selected source footage audio on its own.",
    }]


def test_music_preview_renders_real_bed_under_vo_file(tmp_path):
    from services.soundtrack_review import SoundtrackReviewService

    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(tmp_path, _music())
    result = SoundtrackReviewService(store.db_path).get_review(
        asset_id=asset_id,
        edit_plan_id=edit_plan_id,
        store=store,
    )
    assert result.ok
    tracks = {track["name"]: track for track in result.payload["preview"]["tracks"]}
    assert tracks["bed_alone"]["file"] == "/media/bed.wav"
    assert tracks["bed_under_vo"]["file"].startswith(
        f"/media/{asset_id}/soundtrack-preview-"
    )
    mixed_name = tracks["bed_under_vo"]["file"].rsplit("/", 1)[-1]
    mixed_path = tmp_path / "media" / str(asset_id) / mixed_name
    assert mixed_path.is_file()
    assert mixed_path.stat().st_size > 0
    assert result.payload["preview_ready"] is True


def test_assets_template_exposes_all_soundtrack_decisions():
    template = (ROOT / "src" / "templates" / "assets.html").read_text()
    assert "Prepare audio preview" in template
    assert "Approve soundtrack" in template
    assert "Reject soundtrack" in template
    assert "Replace soundtrack" in template
    assert "Use VO only" in template
    assert "soundtrack_approval_required" in template


def test_operator_routes_preview_then_approve_exact_persisted_plan(tmp_path):
    from app import create_app

    store, _, draft_id, asset_id, _edit_plan_id = _persist_asset_plan(
        tmp_path, _vo_only()
    )
    app = create_app(config_dir=str(ROOT / "config"), db_path=store.db_path)
    app.config.update(TESTING=True, START_BACKGROUND_WORKERS=False)
    client = app.test_client()

    page = client.get(f"/create/assets/{draft_id}")
    assert page.status_code == 200
    assert b"Prepare audio preview" in page.data
    assert b"Approve soundtrack" in page.data

    review = client.get(f"/api/assets/{asset_id}/soundtrack-review")
    assert review.status_code == 200
    assert review.get_json()["mode"] == "vo_only"
    assert review.get_json()["preview_acknowledged"] is False

    blocked = client.post(
        f"/api/assets/{asset_id}/soundtrack-decision",
        json={"action": "approve"},
    )
    assert blocked.status_code == 409
    assert "listen" in blocked.get_json()["error"].lower()

    previewed = client.post(f"/api/assets/{asset_id}/soundtrack-previewed", json={})
    assert previewed.status_code == 200
    assert previewed.get_json()["status"] == "preview_acknowledged"

    approved = client.post(
        f"/api/assets/{asset_id}/soundtrack-decision",
        json={"action": "approve"},
    )
    assert approved.status_code == 200
    assert approved.get_json()["status"] == "approved"

    readback = client.get(f"/api/assets/{asset_id}/soundtrack-review").get_json()
    assert readback["approval"]["approved"] is True
