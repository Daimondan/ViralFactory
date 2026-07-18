"""Behavioral route wiring regressions for VF-VS-101.

The HTTP handlers must delegate production work to the same service classes used
by the autonomous assembler chain. A patched service result therefore controls
the route response without requiring route-local asset, LLM, or renderer logic.
"""

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app import create_app
from services import ServiceResponse
from services.edit_planning import EditPlanningService
from services.media_planning import MediaPlanningService
from services.render_review import RenderReviewService


def _make_app(tmp_path):
    return create_app(
        config_dir=str(ROOT / "config"),
        db_path=str(tmp_path / "test.db"),
    )


def _function_source(path, function_name):
    source = path.read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"Function not found: {function_name}")


def test_operator_routes_are_http_only_and_chain_uses_same_service_entrypoints():
    app_path = ROOT / "src" / "app.py"
    forbidden = (
        "LLMAdapter",
        "AssemblyRenderer",
        "MediaAdapter",
        "StockAdapter",
        "probe_duration",
    )
    for function_name in (
        "generate_edit_plan",
        "render_final_cut",
        "generate_missing_media",
    ):
        route_source = _function_source(app_path, function_name)
        assert all(name not in route_source for name in forbidden)

    chain_source = (ROOT / "src" / "produce_chain.py").read_text()
    assert "MediaPlanningService" in chain_source
    assert "EditPlanningService" in chain_source
    assert "RenderReviewService" in chain_source
    assert chain_source.count(".generate_for_asset(") >= 2
    assert ".render_for_asset(" in chain_source


def test_uploaded_binary_path_is_available_to_shared_inventory(tmp_path):
    from materials import MaterialsIntake
    from services.media_inventory import MediaInventoryService

    db_path = str(tmp_path / "test.db")
    upload = tmp_path / "capture.mp4"
    upload.write_bytes(b"capture fixture")
    intake = MaterialsIntake(db_path, upload_dir=str(tmp_path / "uploads"))
    material_id = intake.ingest_file(
        str(upload),
        business_slug="stackpenni",
        channel="capture_upload",
    )

    inventory = MediaInventoryService(db_path).build_inventory(
        asset_id=1,
        business_slug="stackpenni",
        capture_upload_ids=[material_id],
    )

    assert len(inventory.render_ready_items) == 1
    assert inventory.render_ready_items[0].ingredient_id == f"capture_upload:{material_id}"
    assert inventory.render_ready_items[0].kind == "video"


def test_render_review_uses_the_registered_final_cut_media_id(tmp_path):
    import sqlite3

    db_path = str(tmp_path / "test.db")
    output_path = tmp_path / "final.mp4"
    reviewed_media_ids = []

    class RecordingRenderer:
        def render(self, **kwargs):
            output_path.write_bytes(b"rendered video")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE asset_media (id INTEGER PRIMARY KEY, asset_id INTEGER, kind TEXT, path TEXT)"
            )
            conn.execute(
                "INSERT INTO asset_media (id, asset_id, kind, path) VALUES (41, ?, 'final_cut', ?)",
                (kwargs["asset_id"], str(output_path)),
            )
            conn.commit()
            conn.close()
            return {"path": str(output_path)}

    class RecordingReviewer:
        def review_render(self, path, plan, asset_id, media_id, business_slug):
            reviewed_media_ids.append(media_id)
            return {"verdict": "compliant", "summary": "ok", "findings": {}}

    result = RenderReviewService(
        db_path=db_path,
        renderer=RecordingRenderer(),
        reviewer=RecordingReviewer(),
    ).render_and_review(
        plan={},
        asset_id=7,
        draft_id=3,
        business_slug="stackpenni",
        plan_id=9,
    )

    assert result.render.success is True
    assert reviewed_media_ids == [41]


def test_shared_render_service_preserves_extended_operator_reviews(tmp_path):
    calls = []

    class ExtendedReviewer:
        def run_visual_inspection(self, path, plan, content, asset_id, media_id, slug):
            calls.append(("visual", media_id))
            return {"status": "complete", "verdict": "pass", "summary": "visual ok"}

        def run_audio_inspection(self, path, plan, asset_id, media_id, slug, **kwargs):
            calls.append(("audio", media_id))
            return {"status": "complete", "verdict": "pass", "summary": "audio ok"}

        def run_content_alignment(self, asset_id, media_id, **kwargs):
            calls.append(("alignment", media_id))
            return {"verdict": "pass", "summary": "aligned"}

    service = RenderReviewService(db_path=str(tmp_path / "test.db"))
    service._latest_final_cut_media_id = lambda asset_id: 41
    summary = service._extended_review_summary(
        reviewer=ExtendedReviewer(),
        render_path=str(tmp_path / "final.mp4"),
        plan={},
        asset={"content": "approved", "posts": "[]"},
        asset_id=7,
        business_slug="stackpenni",
        mechanical_findings={"warnings": []},
    )

    assert calls == [("visual", 41), ("audio", 41), ("alignment", 41)]
    assert set(summary) == {"visual", "audio", "alignment"}


def test_edit_plan_route_delegates_to_edit_planning_service(monkeypatch, tmp_path):
    calls = []

    def fake_generate(self, *, asset_id, business_slug, feedback="", store=None):
        calls.append((asset_id, business_slug, feedback, store is not None))
        return ServiceResponse({
            "status": "ok",
            "plan_id": 91,
            "cut_list": ["service plan"],
            "plan": {"segments": []},
        })

    monkeypatch.setattr(
        EditPlanningService, "generate_for_asset", fake_generate, raising=False,
    )

    response = _make_app(tmp_path).test_client().post(
        "/api/assets/17/edit-plan", json={"feedback": "hold the proof shot"},
    )

    assert response.status_code == 200
    assert response.get_json()["plan_id"] == 91
    assert calls == [(17, "stackpenni", "hold the proof shot", True)]


def test_render_route_delegates_to_render_review_service(monkeypatch, tmp_path):
    calls = []

    def fake_render(self, *, asset_id, plan_id, business_slug, store=None):
        calls.append((asset_id, plan_id, business_slug, store is not None))
        return ServiceResponse({
            "status": "ok",
            "path": "data/media/23/final_1.mp4",
            "review": {"verdict": "compliant"},
        })

    monkeypatch.setattr(
        RenderReviewService, "render_for_asset", fake_render, raising=False,
    )

    response = _make_app(tmp_path).test_client().post(
        "/api/assets/23/render", json={"plan_id": 52},
    )

    assert response.status_code == 200
    assert response.get_json()["path"].endswith("final_1.mp4")
    assert calls == [(23, 52, "stackpenni", True)]


def test_generate_media_route_delegates_to_media_planning_service(monkeypatch, tmp_path):
    calls = []

    def fake_generate(self, *, asset_id, business_slug, store=None):
        calls.append((asset_id, business_slug, store is not None))
        return ServiceResponse({
            "status": "ok",
            "results": [{"ingredient_id": "asset_media:7", "status": "render_ready"}],
        })

    monkeypatch.setattr(
        MediaPlanningService, "generate_for_asset", fake_generate, raising=False,
    )

    response = _make_app(tmp_path).test_client().post(
        "/api/assets/31/generate-media", json={},
    )

    assert response.status_code == 200
    assert response.get_json()["results"][0]["ingredient_id"] == "asset_media:7"
    assert calls == [(31, "stackpenni", True)]
