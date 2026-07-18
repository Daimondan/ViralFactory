"""VF-AU-401 production pre-render feasibility boundary."""

from tests.test_vf_vs_402_visual_director_integration import make_visual_reel

from services.render_review import RenderReviewService


class RendererSpy:
    def __init__(self):
        self.called = False

    def render(self, **kwargs):
        self.called = True
        raise AssertionError("renderer must not run without feasible pre-render evidence")


class SuccessfulRenderer:
    def __init__(self, output_path):
        self.output_path = output_path
        self.called = False

    def render(self, **kwargs):
        self.called = True
        self.output_path.write_bytes(b"rendered fixture")
        return {
            "path": str(self.output_path),
            "duration": 3.0,
            "render_time_s": 0.1,
            "version": 1,
            "cut_list": [],
        }


class CompliantReviewer:
    def review_render(self, *args, **kwargs):
        return {
            "verdict": "compliant",
            "summary": "Fixture passed.",
            "findings": {"warnings": []},
        }


def complete_feasibility():
    return {
        "feasible": True,
        "verdict": "feasible",
        "summary": "All pre-render feasibility checks passed.",
        "checks": {
            "vo_timeline": {"feasible": True},
            "beat_mapping": {"feasible": True},
            "visual_event_coverage": {"feasible": True},
            "talking_head_motion": {"feasible": True},
        },
    }


def test_complete_feasibility_evidence_is_render_ready():
    plan = {"feasibility": complete_feasibility()}

    assert RenderReviewService._pre_render_feasibility_error(plan) is None


def test_partial_or_failed_feasibility_evidence_is_blocked():
    partial = complete_feasibility()
    del partial["checks"]["visual_event_coverage"]
    false_green = complete_feasibility()
    false_green["checks"]["talking_head_motion"]["feasible"] = False

    assert "missing feasibility checks" in (
        RenderReviewService._pre_render_feasibility_error({"feasibility": partial})
        or ""
    ).lower()
    assert RenderReviewService._pre_render_feasibility_error(
        {"feasibility": false_green}
    )


def test_voice_led_render_requires_feasible_persisted_plan(tmp_path):
    db_path, store, asset_id, _media_id = make_visual_reel(tmp_path)
    plan_id = store.save_edit_plan(
        store.get_asset(asset_id)["draft_id"],
        asset_id,
        {
            "segments": [],
            "audio": {
                "vo": {
                    "take_id": "take_visual_001",
                    "path": str(tmp_path / "vo.wav"),
                    "duration_sec": 3.0,
                },
            },
            "canvas": {
                "aspect_ratio": "9:16",
                "resolution": "1080x1920",
                "duration_target": 3.0,
            },
        },
        compliance_contract={"beats": []},
    )
    renderer = RendererSpy()

    result = RenderReviewService(
        db_path=db_path,
        renderer=renderer,
    ).render_for_asset(
        asset_id=asset_id,
        plan_id=plan_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 409
    assert result.payload["status"] == "feasibility_required"
    assert "feasibility" in result.payload["error"].lower()
    assert renderer.called is False
    assert store.get_edit_plan(plan_id)["status"] == "needs_operator_decision"


def test_voice_led_render_accepts_complete_feasibility_evidence(tmp_path):
    db_path, store, asset_id, _media_id = make_visual_reel(tmp_path)
    plan_id = store.save_edit_plan(
        store.get_asset(asset_id)["draft_id"],
        asset_id,
        {
            "segments": [],
            "audio": {
                "vo": {
                    "take_id": "take_visual_001",
                    "path": str(tmp_path / "vo.wav"),
                    "duration_sec": 3.0,
                },
            },
            "canvas": {
                "aspect_ratio": "9:16",
                "resolution": "1080x1920",
                "duration_target": 3.0,
            },
            "feasibility": complete_feasibility(),
        },
        compliance_contract={"beats": []},
    )
    renderer = SuccessfulRenderer(tmp_path / "render.mp4")

    result = RenderReviewService(
        db_path=db_path,
        renderer=renderer,
        reviewer=CompliantReviewer(),
    ).render_for_asset(
        asset_id=asset_id,
        plan_id=plan_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.ok
    assert result.payload["status"] == "ok"
    assert renderer.called is True
