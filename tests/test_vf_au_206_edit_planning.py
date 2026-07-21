"""Tests for VF-AU-206: Edit-planning service v2."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from media_adapter import MediaAdapter
from pipeline import PipelineStore
from services.edit_planning import EditPlanningService


def _make_voice_led_reel(tmp_path):
    db_path = str(tmp_path / "pipeline.db")
    store = PipelineStore(db_path)
    draft_id = store.create_draft(
        "stackpenni",
        0,
        "test",
        format_name="Instagram Reel Script",
    )
    posts = [
        {
            "beat_id": "b01",
            "label": "HOOK",
            "vo_text": "Money habits start long before the first paycheque arrives.",
            "text_on_screen": {"text": "Start before payday"},
            "transition_in": "cut",
        },
        {
            "beat_id": "b02",
            "label": "PAYOFF",
            "vo_text": "Practice the habit while the amounts are still small.",
            "text_on_screen": {"text": "Practice with small amounts"},
            "transition_in": "crossfade",
        },
    ]
    store.save_draft_content(
        draft_id,
        "Approved draft",
        {},
        [],
        platform_content=[{
            "platform": "Instagram",
            "variant_type": "reel",
            "content": "Approved voice-led asset",
            "posts": posts,
        }],
    )
    asset_id = store.create_asset(
        "stackpenni",
        draft_id,
        "Instagram",
        "reel",
        "Approved voice-led asset",
        posts=posts,
    )

    image_path = tmp_path / "approved-source.png"
    image_path.write_bytes(b"fixture image")
    media_id = MediaAdapter({"media": {}}, db_path=db_path)._record_media(
        asset_id,
        "image",
        str(image_path),
        "fixture",
        "approved visual source",
        0,
    )

    combined_path = tmp_path / "complete-take.wav"
    combined_path.write_bytes(b"combined audio fixture")
    vo_segments = []
    for index, (post, duration) in enumerate(zip(posts, (3.25, 2.75)), 1):
        segment_path = tmp_path / f"vo-{index}.wav"
        segment_path.write_bytes(b"audio fixture")
        vo_segments.append({
            "frame": index,
            "beat_id": post["beat_id"],
            "text": post["vo_text"],
            "path": str(segment_path),
            "combined_path": str(combined_path),
            "duration": duration,
            "take_id": "take_exact_001",
        })
    store.save_vo_segments(asset_id, json.dumps(vo_segments))
    return db_path, store, draft_id, asset_id, media_id


def test_generate_for_asset_compiles_exact_measured_vo_and_persists_contract(
    monkeypatch,
    tmp_path,
):
    db_path, store, _draft_id, asset_id, media_id = _make_voice_led_reel(tmp_path)
    captured = {}

    def complete(self, prompt_file, variables, schema, **kwargs):
        if prompt_file == "assembly/soundtrack_plan_v1.md":
            contract_id = json.loads(variables["content_contract"])["contract_id"]
            return {
                "contract_id": contract_id,
                "mode": "vo_only",
                "music_bed_ref": None,
                "ducking": None,
                "sfx_cues": [],
                "vo_only_rationale": "The approved voice should stand alone.",
                "source_sound_rationale": None,
                "emotional_register": "direct",
                "search_queries": ["direct restrained pulse"],
                "operator_approval": None,
            }
        captured.update({
            "prompt_file": prompt_file,
            "variables": variables,
            "schema": schema,
        })
        return {
            "segments": [
                {
                    "segment_id": "seg_b01_1",
                    "beat_ids": ["b01"],
                    "source": f"asset_media:{media_id}",
                    "source_in": 0,
                    "source_out": 3.25,
                    "timeline_duration": 3.25,
                    "cue_ids": ["vo_b01"],
                    "transition": "cut",
                    "transition_reason": "opens the piece",
                    "audio_contribution": "vo",
                },
                {
                    "segment_id": "seg_b02_1",
                    "beat_ids": ["b02"],
                    "source": f"asset_media:{media_id}",
                    "source_in": 0,
                    "source_out": 2.75,
                    "timeline_duration": 2.75,
                    "cue_ids": ["vo_b02"],
                    "transition": "cut",
                    "transition_reason": "LLM incorrectly requested a cut",
                    "audio_contribution": "vo",
                },
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", complete)

    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 200
    assert captured["prompt_file"] == "assembly/edit_plan_v2.md"
    vo_take = json.loads(captured["variables"]["vo_take_json"])
    assert vo_take == {"take_id": "take_exact_001", "duration_sec": 6.0}
    compiled = json.loads(captured["variables"]["compiled_cues_json"])
    assert compiled["total_duration_sec"] == 6.0
    assert {cue["beat_id"] for cue in compiled["vo_timings"]} == {"b01", "b02"}
    assert all(cue["metadata"]["measured"] for cue in compiled["vo_timings"])
    caption_words = {
        beat_id: " ".join(
            cue["text"]
            for cue in compiled["captions"]
            if cue["beat_id"] == beat_id
        ).split()
        for beat_id in ("b01", "b02")
    }
    assert caption_words["b01"] == (
        "Money habits start long before the first paycheque arrives."
    ).split()
    assert caption_words["b02"] == (
        "Practice the habit while the amounts are still small."
    ).split()

    plan = result.payload["plan"]
    assert plan["audio"]["vo"]["take_id"] == "take_exact_001"
    assert plan["audio"]["vo"]["path"] == str(tmp_path / "complete-take.wav")
    assert plan["audio"]["vo"]["duration_sec"] == 6.0
    assert plan["canvas"]["duration_target"] == 6.0
    assert plan["compiled_cues"]["text_hash"] == compiled["text_hash"]
    transition_cues = {
        cue["beat_id"]: cue["metadata"]["transition_in"]
        for cue in plan["compiled_cues"]["overlays"]
        if cue["cue_type"] == "transition"
    }
    assert transition_cues == {"b01": "cut", "b02": "crossfade"}
    assert [segment["beat_ids"] for segment in plan["segments"]] == [["b01"], ["b02"]]
    assert plan["segments"][1]["transition_in"] == "crossfade"
    assert all(segment["source"].startswith("generated:") for segment in plan["segments"])
    assert plan["captions"]["style_ref"] == "caption"
    caption_overlays = [
        overlay
        for segment in plan["segments"]
        for overlay in segment["overlays"]
        if overlay["type"] == "caption"
    ]
    assert caption_overlays
    assert all(overlay["style_ref"] == "caption" for overlay in caption_overlays)

    saved = store.get_edit_plan(result.payload["plan_id"])
    assert saved["compliance_contract_json"]
    assert saved["source_draft_hash"]
    saved_plan = json.loads(saved["plan_json"])
    assert saved_plan["audio"]["vo"]["take_id"] == "take_exact_001"
    assert saved_plan["canvas"]["duration_target"] == 6.0
    assert saved_plan["segments"][1]["transition_in"] == "crossfade"


def test_generate_for_asset_stops_before_llm_when_complete_vo_is_missing(
    monkeypatch,
    tmp_path,
):
    db_path, store, _draft_id, asset_id, _media_id = _make_voice_led_reel(tmp_path)
    store.save_vo_segments(asset_id, "[]")

    def unexpected_complete(*args, **kwargs):
        raise AssertionError("LLM must not run without a complete approved VO take")

    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", unexpected_complete)

    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 409
    assert result.payload["status"] == "vo_required"
    assert store.list_edit_plans(asset_id) == []


def test_generate_for_asset_rejects_timeline_that_differs_from_measured_vo(
    monkeypatch,
    tmp_path,
):
    db_path, store, _draft_id, asset_id, media_id = _make_voice_led_reel(tmp_path)

    def complete(self, prompt_file, variables, schema, **kwargs):
        return {
            "segments": [{
                "segment_id": "seg_all",
                "beat_ids": ["b01", "b02"],
                "source": f"asset_media:{media_id}",
                "source_in": 0,
                "source_out": 5.5,
                "timeline_duration": 5.5,
                "cue_ids": ["vo_b01", "vo_b02"],
                "transition": "cut",
                "transition_reason": "single visual hold",
                "audio_contribution": "vo",
            }],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

    monkeypatch.setattr("llm_adapter.LLMAdapter.complete", complete)

    result = EditPlanningService(db_path=db_path).generate_for_asset(
        asset_id=asset_id,
        business_slug="stackpenni",
        store=store,
    )

    assert result.status_code == 422
    assert result.payload["status"] == "invalid_plan"
    assert any("measured VO" in error for error in result.payload["errors"])
    assert store.list_edit_plans(asset_id) == []


def test_compliance_uses_compiled_per_beat_vo_ranges_for_shared_segment():
    beats = [
        {"beat_id": "b01", "vo_text": "First beat.", "required": True},
        {"beat_id": "b02", "vo_text": "Second beat.", "required": True},
    ]
    segments = [{
        "segment_id": "seg_all",
        "beat_ids": ["b01", "b02"],
        "timeline_duration": 6.0,
    }]
    compiled = {"vo_timings": [
        {"beat_id": "b01", "start_sec": 0.0, "end_sec": 3.25},
        {"beat_id": "b02", "start_sec": 3.25, "end_sec": 6.0},
    ]}

    contract = EditPlanningService._build_compliance_contract(
        beats,
        segments,
        compiled,
    )

    ranges = {
        beat["beat_id"]: beat["planned_time_range"]
        for beat in contract["beats"]
    }
    assert ranges == {
        "b01": {"start": 0.0, "end": 3.25},
        "b02": {"start": 3.25, "end": 6.0},
    }


def test_source_draft_hash_tracks_exact_available_writer_source():
    platform_content = [{
        "platform": "Instagram",
        "variant_type": "reel",
        "content": "Approved voice-led asset",
        "posts": [{"beat_id": "b01", "vo_text": "Approved words."}],
    }]
    beats = [{"beat_id": "b01", "vo_text": "Approved words."}]

    original = EditPlanningService._compute_source_draft_hash(
        platform_content,
        beats,
    )
    changed = EditPlanningService._compute_source_draft_hash(
        [{**platform_content[0], "content": "Changed words"}],
        beats,
    )

    assert len(original) == 64
    assert original != changed


class TestSegmentValidation:
    def test_render_source_aliases_stock_inventory_namespaces(self):
        assert EditPlanningService._render_source("stock_cache:7") == "stock:7"
        assert EditPlanningService._render_source("stock_media:8") == "stock:8"

    def test_v2_missing_source_out_is_rejected(self):
        svc = EditPlanningService()
        segments = [{
            "segment_id": "s01",
            "beat_ids": ["b01"],
            "source": "asset_media:1",
            "source_in": 0,
        }]
        beats = [{"beat_id": "b01", "required": True}]

        errors = svc.validate_segments(
            segments,
            beats,
            {"asset_media:1"},
            set(),
            require_source_out=True,
        )

        assert any("missing source_out" in error.lower() for error in errors)

    def test_supplied_zero_source_out_is_rejected(self):
        svc = EditPlanningService()
        segments = [{
            "segment_id": "s01",
            "beat_ids": ["b01"],
            "source": "asset_media:1",
            "source_in": 0,
            "source_out": 0,
        }]
        beats = [{"beat_id": "b01", "required": True}]

        errors = svc.validate_segments(
            segments,
            beats,
            {"asset_media:1"},
            set(),
        )

        assert any("invalid bounds" in error.lower() for error in errors)

    def test_video_source_out_cannot_exceed_inventory_duration(self):
        """Small overshoots are clamped to the video duration; large overshoots (>2s) are rejected."""
        svc = EditPlanningService()
        # Small overshoot: 5.0s source_out on a 4.0s video → clamped, no error
        segments = [{
            "segment_id": "s01",
            "beat_ids": ["b01"],
            "source": "asset_media:1",
            "source_in": 0,
            "source_out": 5.0,
        }]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(
            segments,
            beats,
            {"asset_media:1"},
            set(),
            inventory_items={
                "asset_media:1": {"kind": "video", "duration": 4.0},
            },
        )
        # Small overshoot should be clamped, not rejected
        assert not any("exceeds" in error.lower() for error in errors), f"Small overshoot should be clamped, not rejected: {errors}"
        assert segments[0]["source_out"] == 4.0, f"source_out should be clamped to 4.0, got {segments[0]['source_out']}"

        # Large overshoot: 10.0s source_out on a 4.0s video → rejected
        segments_large = [{
            "segment_id": "s02",
            "beat_ids": ["b01"],
            "source": "asset_media:1",
            "source_in": 0,
            "source_out": 10.0,
        }]
        errors_large = svc.validate_segments(
            segments_large,
            beats,
            {"asset_media:1"},
            set(),
            inventory_items={
                "asset_media:1": {"kind": "video", "duration": 4.0},
            },
        )
        assert any("exceeds" in error.lower() for error in errors_large), "Large overshoot (>2s) should be rejected"

    def test_invented_source_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "fake:999"}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("fake:999" in e or "not in inventory" in e for e in errors)

    def test_valid_source_passes(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert errors == []

    def test_out_of_bounds_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1",
                      "source_in": 5.0, "source_out": 2.0}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("bounds" in e.lower() for e in errors)

    def test_missing_required_beat_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"}]
        beats = [{"beat_id": "b01", "required": True}, {"beat_id": "b02", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("b02" in e for e in errors)

    def test_unknown_beat_in_segment_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b99"], "source": "asset_media:1"}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        assert any("b99" in e for e in errors)

    def test_duplicate_segment_id_rejected(self):
        svc = EditPlanningService()
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"},
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:2"},
        ]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1", "asset_media:2"}, set())
        assert any("duplicate" in e.lower() for e in errors)

    def test_text_intent_reference_resolves(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1",
                      "text_intent_ids": ["t01"]}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, {"t01"})
        assert errors == []

    def test_unknown_text_intent_rejected(self):
        svc = EditPlanningService()
        segments = [{"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1",
                      "text_intent_ids": ["t99"]}]
        beats = [{"beat_id": "b01", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, {"t01"})
        assert any("t99" in e for e in errors)

    def test_mixed_valid_invalid_sources(self):
        """In a plan with mixed valid and invalid sources, only invalid ones are flagged."""
        svc = EditPlanningService()
        segments = [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "asset_media:1"},  # valid
            {"segment_id": "s02", "beat_ids": ["b02"], "source": "fake:999"},       # invalid
        ]
        beats = [{"beat_id": "b01", "required": True}, {"beat_id": "b02", "required": True}]
        errors = svc.validate_segments(segments, beats, {"asset_media:1"}, set())
        # Should flag the invalid source but not the valid one
        assert any("fake:999" in e for e in errors)
        assert not any("asset_media:1" in e for e in errors if "not in inventory" in e)