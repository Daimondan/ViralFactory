"""Regressions for VO-first, motion-capable reel production."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from reel_production import (
    ReelProductionError,
    build_reel_plan,
    estimate_motion,
    extract_reel_beats,
    validate_cost_approval,
    validate_motion_plan,
    validate_vo_segments,
)


POSTS = [
    {
        "vo_text": "Alex Karp said discipline beats talent when timing gets rough.",
        "text_on_screen": "Alex Karp · Discipline > talent",
        "visual": "A founder closes distractions and returns to focused work.",
    },
    {
        "vo_text": "Scott Galloway calls it the Algebra of Wealth.",
        "text_on_screen": "Discipline. Resilience. Timing.",
        "visual": "Three ideas resolve as bold graphic cards.",
    },
]
RENDER_CONFIG = {
    "aspect_ratio": "9:16", "resolution": "1080x1920",
    "caption_style_ref": "caption", "overlay_style_ref": "emphasis",
}


@pytest.fixture
def beats():
    return extract_reel_beats(POSTS)


def test_extracts_exact_structured_vo_and_renderer_text(beats):
    assert [b["beat_id"] for b in beats] == ["b01", "b02"]
    assert beats[0]["vo_text"] == POSTS[0]["vo_text"]
    assert beats[0]["overlay_text"] == POSTS[0]["text_on_screen"]
    assert beats[1]["overlay_text"] == "Discipline. Resilience. Timing."


def test_vo_validation_rejects_partial_generation(beats, tmp_path):
    wav = tmp_path / "one.wav"
    wav.write_bytes(b"RIFF")
    with pytest.raises(ReelProductionError, match="2 spoken beats.*1 VO segment"):
        validate_vo_segments(beats, [{
            "beat_id": "b01", "frame": 1, "text": POSTS[0]["vo_text"],
            "duration": 8.0, "path": str(wav), "take_id": "take_x",
            "combined_path": str(wav),
        }])


def test_vo_validation_rejects_rewritten_text(beats, tmp_path):
    files = []
    for i in range(3):
        p = tmp_path / f"{i}.wav"; p.write_bytes(b"RIFF"); files.append(str(p))
    segments = [
        {"beat_id": "b01", "frame": 1, "text": "Paraphrased", "duration": 8.0,
         "path": files[0], "take_id": "take_x", "combined_path": files[2]},
        {"beat_id": "b02", "frame": 2, "text": POSTS[1]["vo_text"], "duration": 7.0,
         "path": files[1], "take_id": "take_x", "combined_path": files[2]},
    ]
    with pytest.raises(ReelProductionError, match="does not match approved text"):
        validate_vo_segments(beats, segments)


def test_motion_estimate_uses_config_rate_and_only_missing_beats(beats):
    config = {
        "video_default": "kling-3-standard",
        "video_generators": [{
            "name": "kling-3-standard", "provider": "fal",
            "cost_per_second_usd": 0.10, "clip_duration_seconds": 5,
        }],
    }
    estimate = estimate_motion(beats, config, existing_motion_beat_ids={"b01"})
    assert estimate == {
        "generator": "kling-3-standard",
        "provider": "fal",
        "clip_duration_seconds": 5,
        "missing_beat_ids": ["b02"],
        "clip_count": 1,
        "estimated_cost_usd": 0.5,
    }


def test_cost_approval_must_match_current_estimate():
    validate_cost_approval(3.0, 3.0)
    with pytest.raises(ReelProductionError, match="changed"):
        validate_cost_approval(2.0, 3.0)


def test_motion_plan_requires_one_prompt_per_exact_beat(beats):
    valid = {"shots": [
        {"beat_id": "b01", "motion_prompt": "Slow push-in as the founder closes distractions."},
        {"beat_id": "b02", "motion_prompt": "Cards resolve in sequence with restrained camera drift."},
    ]}
    assert set(validate_motion_plan(beats, valid)) == {"b01", "b02"}
    with pytest.raises(ReelProductionError, match="missing"):
        validate_motion_plan(beats, {"shots": valid["shots"][:1]})


def test_plan_uses_vo_as_master_clock_and_exact_overlays(beats, tmp_path):
    combined = tmp_path / "combined.wav"; combined.write_bytes(b"RIFF")
    segments = []
    for i, (beat, duration) in enumerate(zip(beats, [8.0, 7.0]), 1):
        p = tmp_path / f"frame{i}.wav"; p.write_bytes(b"RIFF")
        segments.append({
            "beat_id": beat["beat_id"], "frame": i, "text": beat["vo_text"],
            "duration": duration, "path": str(p), "take_id": "take_exact",
            "combined_path": str(combined),
        })

    visuals = {
        "b01": {"video": {"ingredient_id": "generated:21", "duration": 5.0},
                "image": {"ingredient_id": "generated:11"}},
        "b02": {"video": {"ingredient_id": "generated:22", "duration": 5.0},
                "image": {"ingredient_id": "generated:12"}},
    }
    plan, contract = build_reel_plan(beats, segments, visuals, RENDER_CONFIG)

    assert plan["canvas"]["duration_target"] == 15.0
    assert sum(s["out"] - s["in"] for s in plan["segments"]) == 15.0
    assert plan["audio"]["vo"]["take_id"] == "take_exact"
    assert plan["audio"]["original_audio"] is False
    assert plan["captions"]["burned_in"] is True
    overlays = [o["text"] for s in plan["segments"] for o in s.get("overlays", [])]
    assert POSTS[0]["vo_text"] in overlays
    assert POSTS[1]["vo_text"] in overlays
    assert POSTS[0]["text_on_screen"] in overlays
    assert POSTS[1]["text_on_screen"] in overlays
    assert [b["source_excerpt"] for b in contract["beats"]] == [p["vo_text"] for p in POSTS]
    assert [b["expected_duration"] for b in contract["beats"]] == [8.0, 7.0]
    assert all(b["verification_method"] == "audio_transcript_match" for b in contract["beats"])


def test_plan_refuses_silent_vo_led_reel(beats, tmp_path):
    with pytest.raises(ReelProductionError, match="VO segment"):
        build_reel_plan(beats, [], {}, RENDER_CONFIG)


def test_asset_media_records_stable_beat_links(tmp_path):
    from media_adapter import MediaAdapter
    db = tmp_path / "media.db"
    adapter = MediaAdapter({"media": {}}, db_path=str(db))
    media_id = adapter._record_media(
        7, "image", "/tmp/frame.png", "fixture", "prompt", 0,
        beat_id="b02", source_media_id=11,
    )
    import sqlite3
    conn = sqlite3.connect(db)
    row = conn.execute(
        "SELECT beat_id, source_media_id FROM asset_media WHERE id = ?", (media_id,)
    ).fetchone()
    conn.close()
    assert row == ("b02", 11)
