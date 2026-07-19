"""VF-VS-504 — production soundtrack-mix review integration."""

from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from services.render_review import RenderReviewService
from soundtrack_gate import SoundtrackPreviewGate
from soundtrack_plan import make_music_bed_plan, make_vo_only_plan
from tests.test_vf_vs_503_production_gate import _persist_asset_plan, _vo_only


class ExistingFileRenderer:
    def __init__(self, path: Path, audio_evidence: dict | None = None):
        self.path = path
        self.audio_evidence = audio_evidence or {}

    def render(self, **_kwargs):
        return {
            "path": str(self.path),
            "duration": 2.0,
            "render_time_s": 0.1,
            "version": 1,
            "cut_list": [],
            "audio_evidence": self.audio_evidence,
        }


class CompliantReviewer:
    def review_render(self, *_args, **_kwargs):
        return {
            "verdict": "compliant",
            "summary": "Base compliance passed.",
            "findings": {"warnings": []},
        }


@pytest.fixture
def audible_render(tmp_path: Path) -> Path:
    path = tmp_path / "audible.mp4"
    completed = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=black:s=320x240:d=2", "-f", "lavfi", "-i",
            "sine=frequency=440:duration=2", "-c:v", "libx264", "-c:a", "aac",
            "-shortest", str(path),
        ],
        capture_output=True,
        timeout=20,
    )
    assert completed.returncode == 0
    return path


def _music_plan() -> dict:
    return make_music_bed_plan(
        "asset:1",
        "bed-1",
        {
            "type": "royalty_free",
            "id": "licence-1",
            "url": "https://licence.example/1",
        },
        0.0,
        ducking={"attenuation_db": -12, "envelope": []},
    )


def _vo_evidence() -> dict:
    return {
        "strategy": "vo",
        "applied": True,
        "source_ids": [],
        "audible_windows": {},
        "vo_source_id": "take-1",
    }


def test_embedded_plan_token_is_not_trusted(audible_render: Path):
    plan = make_vo_only_plan("asset:1", "The approved VO carries the piece.")
    plan["operator_approval"] = "caller-controlled"

    result = RenderReviewService().check_soundtrack_mix(
        str(audible_render),
        plan,
        rendered_audio_evidence=_vo_evidence(),
    )

    assert result["verdict"] == "needs_operator_decision"
    assert any("approval" in issue.lower() for issue in result["issues"])


def test_vo_only_reports_measured_loudness_and_true_peak(audible_render: Path):
    plan = make_vo_only_plan("asset:1", "The approved VO carries the piece.")

    result = RenderReviewService().check_soundtrack_mix(
        str(audible_render),
        plan,
        operator_approval={"gate_token": "server-minted"},
        rendered_audio_evidence=_vo_evidence(),
        vo_duration=2.0,
    )

    assert result["verdict"] == "compliant"
    assert isinstance(result["checks"]["integrated_loudness_lufs"], float)
    assert isinstance(result["checks"]["true_peak_dbtp"], float)
    assert result["checks"]["audible_windows"]["vo"]
    assert result["checks"]["expected_source_ids"] == []
    assert result["checks"]["rendered_source_ids"] == []


def test_approved_music_fails_without_source_bound_render_evidence(
    audible_render: Path,
):
    result = RenderReviewService().check_soundtrack_mix(
        str(audible_render),
        _music_plan(),
        operator_approval={"gate_token": "server-minted"},
        rendered_audio_evidence={},
        vo_duration=2.0,
    )

    assert result["verdict"] == "needs_operator_decision"
    assert result["checks"]["expected_source_ids"] == ["bed-1"]
    assert result["checks"]["rendered_source_ids"] == []
    assert any("bed-1" in issue for issue in result["issues"])


def test_render_and_review_invokes_mix_review_and_blocks_gate3(
    audible_render: Path,
):
    service = RenderReviewService(
        renderer=ExistingFileRenderer(audible_render),
        reviewer=CompliantReviewer(),
    )

    result = service.render_and_review(
        plan={},
        asset_id=1,
        draft_id=1,
        business_slug="test",
        plan_id=1,
        soundtrack_plan=_music_plan(),
        soundtrack_approval={"gate_token": "server-minted"},
        vo_duration=2.0,
    )

    mix = result.review.findings["soundtrack_mix"]
    assert mix["verdict"] == "needs_operator_decision"
    assert result.review.verdict == "needs_operator_decision"
    assert not result.ready_for_gate3


def test_render_and_review_can_pass_explicit_approved_vo_only(
    audible_render: Path,
):
    service = RenderReviewService(
        renderer=ExistingFileRenderer(audible_render, _vo_evidence()),
        reviewer=CompliantReviewer(),
    )
    plan = make_vo_only_plan("asset:1", "The approved VO carries the piece.")

    result = service.render_and_review(
        plan={},
        asset_id=1,
        draft_id=1,
        business_slug="test",
        plan_id=1,
        soundtrack_plan=plan,
        soundtrack_approval={"gate_token": "server-minted"},
        vo_duration=2.0,
    )

    assert result.review.findings["soundtrack_mix"]["verdict"] == "compliant"
    assert result.review.verdict == "compliant"
    assert result.ready_for_gate3


def test_render_for_asset_passes_exact_gate_decision_into_final_mix_review(
    tmp_path: Path,
    audible_render: Path,
):
    store, _, _, asset_id, edit_plan_id = _persist_asset_plan(
        tmp_path,
        _vo_only(),
    )
    edit_plan = store.get_edit_plan(edit_plan_id)
    plan = json.loads(edit_plan["plan_json"])
    plan.update({
        "captions": {"burned_in": True, "source": "compiled_cues"},
        "contract_beats": [{"beat_id": "b01", "vo_text": "Approved copy"}],
        "compiled_cues": {"captions": [{
            "cue_id": "caption_b01_0",
            "beat_id": "b01",
            "text": "Approved copy",
            "start_sec": 0.0,
            "end_sec": 1.0,
            "position": "bottom",
        }]},
    })
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE edit_plans SET plan_json = ? WHERE id = ?",
            (json.dumps(plan), edit_plan_id),
        )
    soundtrack = store.list_soundtrack_plans(asset_id)[0]
    SoundtrackPreviewGate(store.db_path).record_approval(
        soundtrack["contract_id"],
        "test-business",
        soundtrack["plan_hash"],
        "vo_only",
    )
    service = RenderReviewService(
        db_path=store.db_path,
        renderer=ExistingFileRenderer(audible_render, _vo_evidence()),
        reviewer=CompliantReviewer(),
        models_config={},
    )
    service._extended_review_summary = lambda **_kwargs: {}

    response = service.render_for_asset(
        asset_id=asset_id,
        plan_id=edit_plan_id,
        business_slug="test-business",
        store=store,
    )

    assert response.status_code == 200
    assert response.payload["status"] == "ok"
    assert response.payload["ready_for_gate3"] is True
    assert response.payload["review"]["verdict"] == "compliant"
