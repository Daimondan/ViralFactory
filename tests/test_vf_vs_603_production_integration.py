"""VF-VS-603 — deterministic text-integrity final-review integration."""

from pathlib import Path
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from services.render_review import RenderReviewService


class ExistingFileRenderer:
    def __init__(self, output_path: Path):
        self.output_path = output_path

    def render(self, **_kwargs):
        return {"path": str(self.output_path), "duration": 2.0}


class CompliantReviewer:
    def review_render(self, *_args, **_kwargs):
        return {
            "verdict": "compliant",
            "summary": "Base review passed.",
            "findings": {},
        }


class NonCompliantReviewer:
    def review_render(self, *_args, **_kwargs):
        return {
            "verdict": "needs_operator_decision",
            "summary": "Base review failed.",
            "findings": {"warnings": ["base failure"]},
        }


def _plan(caption_text: str = "Approved voice line.") -> dict:
    return {
        "segments": [],
        "audio": {"vo": {"take_id": "take-1"}},
        "captions": {"burned_in": True, "source": "compiled_cues"},
        "contract_beats": [
            {"beat_id": "b01", "vo_text": "Approved voice line."},
        ],
        "compiled_cues": {
            "captions": [
                {
                    "cue_id": "caption_b01_0",
                    "beat_id": "b01",
                    "text": caption_text,
                    "start_sec": 0.0,
                    "end_sec": 2.0,
                    "position": "bottom",
                }
            ]
        },
    }


def _service(tmp_path: Path) -> RenderReviewService:
    output = tmp_path / "render.mp4"
    output.write_bytes(b"rendered")
    return RenderReviewService(
        db_path=str(tmp_path / "review.db"),
        renderer=ExistingFileRenderer(output),
        reviewer=CompliantReviewer(),
    )


def _review(service: RenderReviewService, plan: dict):
    return service.render_and_review(
        plan=plan,
        asset_id=1,
        draft_id=1,
        business_slug="test-business",
        plan_id=1,
    )


def test_corrupt_compiled_caption_blocks_final_readiness(tmp_path):
    result = _review(
        _service(tmp_path),
        _plan("{'position': 'center', 'style': 'default'}"),
    )

    assert result.review.findings["text_integrity"]["verdict"] == (
        "needs_operator_decision"
    )
    assert result.review.verdict == "needs_operator_decision"
    assert result.ready_for_gate3 is False


def test_exact_compiled_caption_passes_final_text_integrity(tmp_path):
    result = _review(_service(tmp_path), _plan())

    assert result.review.findings["text_integrity"]["verdict"] == "compliant"
    assert result.review.verdict == "compliant"
    assert result.ready_for_gate3 is True


def test_missing_compiled_caption_blocks_vo_plan(tmp_path):
    plan = _plan()
    plan["compiled_cues"]["captions"] = []

    result = _review(_service(tmp_path), plan)

    assert result.review.findings["text_integrity"]["verdict"] == (
        "needs_operator_decision"
    )
    assert result.ready_for_gate3 is False


def test_clean_text_does_not_overwrite_base_noncompliance(tmp_path):
    output = tmp_path / "render.mp4"
    output.write_bytes(b"rendered")
    service = RenderReviewService(
        db_path=str(tmp_path / "review.db"),
        renderer=ExistingFileRenderer(output),
        reviewer=NonCompliantReviewer(),
    )

    result = _review(service, _plan())

    assert result.review.findings["text_integrity"]["verdict"] == "compliant"
    assert result.review.verdict == "needs_operator_decision"
    assert result.ready_for_gate3 is False
