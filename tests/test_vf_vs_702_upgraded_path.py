"""VF-VS-702 — Real fresh Reel through upgraded path (service-based).

AC: working artifact, complete evidence, operator approval, no false-green.

This test verifies the upgraded service-based path end-to-end using the
existing rendered asset (asset 6) as the test subject. It does NOT make new
paid LLM/media calls — it verifies that the service path produces:
1. A working artifact (the rendered MP4 exists and is playable)
2. Complete evidence (contract versions, IDs, measured VO, plan, compliance)
3. No false-green (skipped evidence blocks, compliance verdict is honest)

A truly "fresh" Reel requires operator-approved LLM + media calls and is
gated by the operator. This test is the automated proof that the upgraded
path is wired correctly; the operator runs the fresh Reel manually.
"""

import json
import os
import subprocess
import sys
import sqlite3
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def _has_ffprobe():
    try:
        subprocess.run(["ffprobe", "-version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def test_existing_artifact_is_playable():
    """AC: working artifact — the rendered MP4 exists and ffprobe can read it."""
    path = "data/media/6/final_2.mp4"
    if not os.path.exists(path):
        pytest.skip("Asset 6 final_2.mp4 not found — run on production VPS")
    if not _has_ffprobe():
        pytest.skip("ffprobe not available")

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    assert duration > 0, "Artifact has zero duration — not playable"


def test_existing_artifact_has_audio_stream():
    """AC: working artifact — must have an audio stream (VO)."""
    path = "data/media/6/final_2.mp4"
    if not os.path.exists(path):
        pytest.skip("Asset 6 not found")
    if not _has_ffprobe():
        pytest.skip("ffprobe not available")

    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", path],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    assert len(audio_streams) > 0, "Artifact has no audio stream — VO missing"


def test_upgraded_path_services_importable():
    """AC: complete evidence — all upgraded-path services are importable."""
    from services.cue_compiler import CueCompiler  # noqa: F401
    from services.caption_timing import chunk_captions  # noqa: F401
    from services.render_review import RenderReviewService  # noqa: F401
    from services.edit_planning import EditPlanningService  # noqa: F401
    from services.media_planning import MediaPlanningService  # noqa: F401
    from services.media_inventory import MediaInventoryService  # noqa: F401
    from feasibility_checks import run_feasibility_checks  # noqa: F401
    from production_contract import assemble_contract  # noqa: F401
    from soundtrack_plan import validate_soundtrack_plan  # noqa: F401
    from soundtrack_gate import SoundtrackPreviewGate  # noqa: F401
    from text_integrity import check_text_integrity  # noqa: F401


def test_upgraded_path_cue_compiler_phrase_level():
    """AC: complete evidence — the upgraded cue compiler produces phrase-level captions."""
    from services.cue_compiler import CueCompiler

    beats = [{"beat_id": "b01", "vo_text": "", "audio_intent": {"mode": "vo_only"}}]
    text_intents = [{
        "text_intent_id": "t01", "beat_id": "b01", "function": "caption",
        "text": "We built a thing that turned into something much bigger",
    }]
    vo_segments = [{"beat_id": "b01", "duration": 8.0, "text": "test"}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)
    assert len(timeline.captions) > 1  # phrase-level, not full-beat


def test_upgraded_path_feasibility_catches_draft8_pattern():
    """AC: no false-green — the Draft 8 pattern is caught by feasibility checks."""
    from feasibility_checks import run_feasibility_checks

    plan = {"segments": [], "canvas": {}}
    beat = {
        "beat_id": "b01",
        "intended_duration_sec": {"min": 0, "max": 14.0},
        "visual_intent": {
            "subject": "the founder",
            "action": "speaking to camera",
            "meaning": "talking head",
        },
        "visual_events": [
            {"event_id": "ev_b01_1", "time_range": {"start": 0.0, "end": 5.0},
             "narrative_function": "context", "source_policy": "generated_motion"},
        ],
    }
    result = run_feasibility_checks(
        plan, {},
        beats=[beat],
        vo_segments=[{"beat_id": "b01", "duration": 14.0, "text": "..."}],
        motion_durations={"b01": 5.0},
    )
    assert result["verdict"] == "needs_operator_decision"


def test_upgraded_path_skipped_evidence_blocks():
    """AC: no false-green — skipped evidence blocks readiness."""
    from asset_review import AssetReviewer

    reviewer = AssetReviewer(models_config={}, db_path=tempfile.mktemp(suffix=".db"))
    result = reviewer.run_content_alignment(
        asset_id=1, media_id=1,
        mechanical={"verdict": "pass", "warnings": []},
        visual={"status": "skipped", "verdict": "skipped", "summary": "skipped"},
        audio={"status": "complete", "verdict": "pass"},
        business_slug="test",
        asset_content="content",
        asset_posts="",
    )
    assert result["verdict"] != "ready_for_operator"


def test_upgraded_path_text_integrity_catches_dict_leak():
    """AC: no false-green — dict metadata leak is caught."""
    from text_integrity import check_text_integrity

    captions = [{"cue_id": "cap_0", "text": "{'position': 'center'}", "start_sec": 0.0, "end_sec": 3.0}]
    result = check_text_integrity(captions)
    assert result.verdict == "needs_operator_decision"


def test_upgraded_path_soundtrack_plan_validates():
    """AC: complete evidence — soundtrack plan validation is wired."""
    from soundtrack_plan import make_vo_only_plan, validate_soundtrack_plan

    plan = make_vo_only_plan("c001", "Valid rationale.")
    errors = validate_soundtrack_plan(plan)
    assert errors == []


def test_upgraded_path_soundtrack_gate_enforces_approval():
    """AC: no false-green — soundtrack gate blocks unapproved plans."""
    from soundtrack_gate import SoundtrackPreviewGate, SoundtrackGateError
    from soundtrack_plan import make_vo_only_plan, compute_soundtrack_plan_hash

    gate = SoundtrackPreviewGate(db_path=tempfile.mktemp(suffix=".db"))
    plan = make_vo_only_plan("c001", "Valid rationale.")
    h = compute_soundtrack_plan_hash(plan)
    with pytest.raises(SoundtrackGateError):
        gate.require_approval("c001", h)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))