"""
VF-CP-001 — CompositionPlan schema + generator tests.

Tests:
  - Schema round-trip is canonical and content-hashed
  - Two tenant/format fixtures produce visibly different plans with zero Python edits
  - Every text element traces to approved Writer contract text
  - Every audio/visual/graphics element traces to a manifest ingredient hash
  - Missing ingredients fail closed
  - Plan is serializable and diffable
  - Plan hash is key-order independent
"""

import json
import os
import sys

import pytest

# Ensure src is on the path
src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


# ── Shared fixture data ──────────────────────────────────────────────────

def _overlay_styles():
    return {
        "default": {"fontsize": 48, "fontcolor": "white", "borderw": 3,
                     "bordercolor": "black", "shadowx": 1, "shadowy": 1,
                     "shadowcolor": "black@0.5"},
        "hook": {"fontsize": 72, "fontcolor": "white", "borderw": 4,
                  "bordercolor": "black", "shadowx": 2, "shadowy": 2,
                  "shadowcolor": "black@0.5"},
        "caption": {"fontsize": 42, "fontcolor": "white", "borderw": 2,
                     "bordercolor": "black"},
        "emphasis": {"fontsize": 56, "fontcolor": "white", "borderw": 3,
                      "bordercolor": "black"},
        "proof": {"fontsize": 40, "fontcolor": "white", "borderw": 2,
                   "bordercolor": "black"},
        "reframe": {"fontsize": 56, "fontcolor": "white", "borderw": 3,
                      "bordercolor": "black"},
        "cta": {"fontsize": 52, "fontcolor": "white", "borderw": 3,
                 "bordercolor": "black"},
        "title": {"fontsize": 80, "fontcolor": "white", "borderw": 5,
                    "bordercolor": "black"},
    }


def _sfx_presets():
    return {
        "pop": {"freq": "1200", "duration": 0.15, "volume": 0.5, "type": "sine"},
        "whoosh": {"freq": "800", "duration": 0.3, "volume": 0.4, "type": "sine"},
    }


def _render_styles(styles=None, positions=None):
    base = _overlay_styles()
    if styles:
        base.update(styles)
    rs = {"overlay_styles": base, "sfx_presets": _sfx_presets(),
          "sfx_default_preset": "pop"}
    if positions:
        rs["text_positions"] = positions
    return rs


def _font_config(family="Montserrat", weight="Bold", file_hash="a" * 64):
    return {
        "font_path": "",  # empty so generator uses font_file_hash directly
        "font_display": "",
        "font_family": family,
        "font_weight": weight,
        "font_file_hash": file_hash,
        "font_display_hash": "b" * 64,
        "font_display_family": "Anton",
        "font_display_weight": "Regular",
    }


def _canvas_config(aspect="9:16", res=None, fps=30):
    if res is None:
        res = {"width": 1080, "height": 1920}
    return {
        "resolution": res,
        "aspect_ratio": aspect,
        "fps": fps,
        "background": {"color": "#000000"},
        "safe_zones": {"title_safe": 0.9, "action_safe": 0.95},
        "platform_framing": "9:16_vertical" if aspect == "9:16" else "16:9_horizontal",
    }


def _mix_config():
    return {
        "lufs_target": -14.0,
        "true_peak_db": -1.0,
        "ducking": {"default_depth": 0.20, "attack_s": 0.3, "release_s": 0.5},
    }


def _writer_contract_hash(beats, text_intents=None):
    from production_contract import compute_writer_contract_hash
    wc = {
        "platform_content": [],
        "beats": beats,
        "primary_audience_action": "finish",
        "capture_policy": "generated_allowed",
    }
    return compute_writer_contract_hash(wc)


def _writer_contract(beats, text_intents, edit_segments=None):
    wc_hash = _writer_contract_hash(beats, text_intents)
    return {
        "contract_id": "test_contract_001",
        "version": "2.0",
        "content_contract": {
            "contract_id": "test_contract_001",
            "core_claim": "Test claim",
            "audience_value": "Test value",
            "evidence_refs": [],
            "primary_emotional_job": "curiosity",
            "primary_audience_action": "finish",
            "format_name": "reel",
            "platform": "IG",
            "capture_policy": "generated_allowed",
            "evidence_label": "HYPOTHESIS",
        },
        "beats": beats,
        "text_intents": text_intents,
        "media_recipes": [],
        "edit_segments": edit_segments or [],
        "soundtrack_plan": None,
        "writer_contract_hash": wc_hash,
    }


def _beats():
    return [
        {
            "beat_id": "b01", "platform_variant_id": "pv01", "role": "hook",
            "required": True, "vo_text": "This is the hook",
            "staged_action": "Show product", "capture_policy": "generated_allowed",
            "intended_duration_sec": {"min": 2.0, "max": 3.0},
            "evidence_refs": ["source_1"],
            "visual_intent": {"subject": "product", "action": "display",
                              "meaning": "product reveal"},
            "audio_intent": {"mode": "vo", "music_action": "start",
                             "sfx": [{"type": "pop", "timing": "on_beat"}]},
            "visual_events": [{
                "event_id": "ev_b01_1",
                "time_range": {"start": 0.0, "end": 3.0},
                "narrative_function": "hook_contrast",
                "source_policy": "generated_still",
                "required_text": None,
                "capture_policy_ref": "generated_allowed",
            }],
            "transition_in": "cut",
        },
        {
            "beat_id": "b02", "platform_variant_id": "pv01", "role": "proof",
            "required": True, "vo_text": "Here is the proof",
            "staged_action": "Show chart", "capture_policy": "generated_allowed",
            "intended_duration_sec": {"min": 3.0, "max": 4.0},
            "evidence_refs": [],
            "visual_intent": {"subject": "chart", "action": "zoom",
                              "meaning": "data proof"},
            "audio_intent": {"mode": "vo", "music_action": "continue", "sfx": []},
            "visual_events": [{
                "event_id": "ev_b02_1",
                "time_range": {"start": 0.0, "end": 4.0},
                "narrative_function": "proof",
                "source_policy": "generated_still",
                "required_text": None,
                "capture_policy_ref": "generated_allowed",
            }],
            "transition_in": "crossfade",
        },
    ]


def _text_intents():
    return [
        {"text_intent_id": "ti_01", "beat_id": "b01", "function": "hook",
         "text": "This is the hook", "required": True},
        {"text_intent_id": "ti_02", "beat_id": "b01", "function": "caption",
         "text": "Hook caption text", "required": True},
        {"text_intent_id": "ti_03", "beat_id": "b02", "function": "proof",
         "text": "Proof overlay text", "required": True},
        {"text_intent_id": "ti_04", "beat_id": "b02", "function": "cta",
         "text": "Follow for more", "required": True},
    ]


def _cue_timeline(beats, text_intents):
    from services.cue_compiler import CueCompiler
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "This is the hook"},
        {"beat_id": "b02", "duration": 4.0, "text": "Here is the proof"},
    ]
    return CueCompiler().compile(
        beats, text_intents, vo_segments=vo_segments,
    )


def _manifest(beats, wc_hash, vo_hash="v" * 64, music_hash=None,
              visual_hash="g" * 64):
    candidates = [
        {"candidate_id": 1, "category": "narration", "role": "full_take",
         "version": 1, "artifact_hash": vo_hash, "artifact_path": "/vo.wav",
         "preview_hash": None, "preview_path": None, "source_type": "audio",
         "cost_estimate_usd": None, "cost_approved": True,
         "beat_refs": ["b01", "b02"], "measurement": {"duration": 7.0}},
        {"candidate_id": 2, "category": "visual", "role": "b_roll",
         "version": 1, "artifact_hash": visual_hash,
         "artifact_path": "/visual.mp4", "preview_hash": None,
         "preview_path": None, "source_type": "video",
         "cost_estimate_usd": None, "cost_approved": True,
         "beat_refs": ["b01"], "measurement": {"duration": 5.0,
                   "width": 1080, "height": 1920}},
    ]
    if music_hash:
        candidates.append({
            "candidate_id": 3, "category": "soundtrack", "role": "bed",
            "version": 1, "artifact_hash": music_hash,
            "artifact_path": "/music.mp3", "preview_hash": None,
            "preview_path": None, "source_type": "audio",
            "cost_estimate_usd": None, "cost_approved": True,
            "beat_refs": [], "measurement": {"duration": 30.0},
        })
    return {
        "business_slug": "test_tenant",
        "production_session_id": 1,
        "draft_id": 1,
        "asset_id": 1,
        "platform": "IG",
        "format": "reel",
        "requirements_version": 1,
        "requirements_hash": "r" * 64,
        "writer_contract_hash": wc_hash,
        "candidates": candidates,
        "manifest_hash": "m" * 64,
    }


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def base_components():
    beats = _beats()
    text_intents = _text_intents()
    wc = _writer_contract(beats, text_intents)
    timeline = _cue_timeline(beats, text_intents)
    manifest = _manifest(beats, wc["writer_contract_hash"])
    return beats, text_intents, wc, timeline, manifest


@pytest.fixture
def generator():
    from services.composition_plan import CompositionPlanGenerator
    return CompositionPlanGenerator(
        render_styles=_render_styles(),
        font_config=_font_config(),
        canvas_config=_canvas_config(),
        mix_config=_mix_config(),
    )


# ── Tests ─────────────────────────────────────────────────────────────────

class TestSchemaRoundTrip:
    """Schema round-trip is canonical and content-hashed."""

    def test_plan_has_schema_version(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        assert plan["schema_version"] == "1.0"

    def test_plan_has_hash(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        assert "plan_hash" in plan
        assert len(plan["plan_hash"]) == 64

    def test_round_trip_preserves_hash(self, generator, base_components):
        from services.composition_plan import (
            serialize_plan, deserialize_plan, compute_plan_hash,
        )
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        json_str = serialize_plan(plan)
        restored = deserialize_plan(json_str)
        assert restored["plan_hash"] == plan["plan_hash"]
        assert compute_plan_hash(restored) == plan["plan_hash"]

    def test_hash_is_key_order_independent(self, generator, base_components):
        from services.composition_plan import compute_plan_hash
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)

        # Reorder top-level keys
        reordered = {}
        keys = list(plan.keys())
        keys.reverse()
        for k in keys:
            reordered[k] = plan[k]

        assert compute_plan_hash(reordered) == compute_plan_hash(plan)


class TestTwoTenantFormats:
    """Two tenant/format fixtures produce visibly different plans with
    zero Python edits."""

    def test_different_canvas_produces_diff(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, diff_plans,
        )
        _, _, wc, timeline, manifest = base_components

        gen_a = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(family="Montserrat"),
            canvas_config=_canvas_config(aspect="9:16",
                                          res={"width": 1080, "height": 1920}),
            mix_config=_mix_config(),
        )
        gen_b = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(family="Inter"),
            canvas_config=_canvas_config(aspect="16:9",
                                          res={"width": 1920, "height": 1080}),
            mix_config=_mix_config(),
        )

        plan_a = gen_a.generate(manifest, wc, timeline)
        plan_b = gen_b.generate(manifest, wc, timeline)

        assert plan_a["plan_hash"] != plan_b["plan_hash"]
        diff = diff_plans(plan_a, plan_b)
        assert len(diff) > 0
        assert "1080" in diff
        assert "1920" in diff

    def test_different_font_produces_diff(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, diff_plans,
        )
        _, _, wc, timeline, manifest = base_components

        gen_a = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(family="Montserrat", file_hash="a" * 64),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        gen_b = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(family="Inter", file_hash="c" * 64),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )

        plan_a = gen_a.generate(manifest, wc, timeline)
        plan_b = gen_b.generate(manifest, wc, timeline)

        assert plan_a["plan_hash"] != plan_b["plan_hash"]
        diff = diff_plans(plan_a, plan_b)
        # Font family should appear in the diff
        assert "Montserrat" in diff or "Inter" in diff

    def test_different_style_produces_diff(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, diff_plans,
        )
        _, _, wc, timeline, manifest = base_components

        gen_a = CompositionPlanGenerator(
            render_styles=_render_styles(styles={
                "hook": {"fontsize": 72, "fontcolor": "white", "borderw": 4,
                          "bordercolor": "black"},
            }),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        gen_b = CompositionPlanGenerator(
            render_styles=_render_styles(styles={
                "hook": {"fontsize": 96, "fontcolor": "#F2B705",
                          "borderw": 4, "bordercolor": "black"},
            }),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )

        plan_a = gen_a.generate(manifest, wc, timeline)
        plan_b = gen_b.generate(manifest, wc, timeline)

        assert plan_a["plan_hash"] != plan_b["plan_hash"]
        diff = diff_plans(plan_a, plan_b)
        assert "96" in diff or "F2B705" in diff


class TestTextTracesToWriterContract:
    """Every text element traces to approved Writer contract text."""

    def test_all_text_intents_present(self, generator, base_components):
        _, text_intents, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)

        text_elems = [e for e in plan["text_elements"]
                      if e["role"] != "citation"]
        ti_ids = {ti["text_intent_id"] for ti in text_intents}
        elem_ti_ids = {e["text_intent_id"] for e in text_elems}
        assert elem_ti_ids == ti_ids

    def test_text_matches_writer_contract(self, generator, base_components):
        _, text_intents, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)

        ti_by_id = {ti["text_intent_id"]: ti for ti in text_intents}
        for te in plan["text_elements"]:
            if te["role"] == "citation":
                continue
            ti = ti_by_id[te["text_intent_id"]]
            assert te["text"] == ti["text"], (
                f"Text mismatch for {te['element_id']}: "
                f"plan='{te['text']}' vs contract='{ti['text']}'"
            )

    def test_citations_trace_to_evidence_refs(self, generator, base_components):
        beats, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)

        citations = [e for e in plan["text_elements"]
                     if e["role"] == "citation"]
        all_evidence = []
        for beat in beats:
            all_evidence.extend(beat.get("evidence_refs") or [])

        citation_texts = [c["text"] for c in citations]
        for ref in all_evidence:
            assert ref in citation_texts, (
                f"Evidence ref '{ref}' not found in citation elements"
            )

    def test_validation_passes_for_correct_text(self, generator, base_components):
        from services.composition_plan import validate_plan
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        errors = validate_plan(plan, manifest, wc)
        text_errors = [e for e in errors if "text" in e.lower()
                       or "citation" in e.lower()
                       or "text_intent" in e.lower()]
        assert text_errors == []


class TestAudioVisualTraceToManifest:
    """Every audio/visual element traces to a manifest ingredient hash."""

    def test_vo_track_traces_to_manifest(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        vo = plan["audio"]["vo_track"]
        assert vo is not None
        manifest_hashes = {c["artifact_hash"] for c in manifest["candidates"]}
        assert vo["source_hash"] in manifest_hashes

    def test_visual_elements_trace_to_manifest(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        manifest_hashes = {c["artifact_hash"] for c in manifest["candidates"]}
        for ve in plan["visual_elements"]:
            assert ve["source_hash"] in manifest_hashes, (
                f"Visual element {ve['element_id']} source_hash "
                f"not in manifest"
            )

    def test_validation_passes_for_correct_hashes(
        self, generator, base_components
    ):
        from services.composition_plan import validate_plan
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        errors = validate_plan(plan, manifest, wc)
        hash_errors = [e for e in errors if "hash" in e.lower()
                       and "plan_hash" not in e.lower()]
        assert hash_errors == []

    def test_music_track_traces_to_manifest(self, base_components):
        from services.composition_plan import CompositionPlanGenerator
        _, _, wc, timeline, manifest = base_components
        manifest = dict(manifest)
        manifest["candidates"] = manifest["candidates"] + [{
            "candidate_id": 3, "category": "soundtrack", "role": "bed",
            "version": 1, "artifact_hash": "m" * 64,
            "artifact_path": "/music.mp3", "preview_hash": None,
            "preview_path": None, "source_type": "audio",
            "cost_estimate_usd": None, "cost_approved": True,
            "beat_refs": [], "measurement": {"duration": 30.0},
        }]
        gen = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        plan = gen.generate(manifest, wc, timeline)
        music = plan["audio"]["music_track"]
        assert music is not None
        manifest_hashes = {c["artifact_hash"] for c in manifest["candidates"]}
        assert music["source_hash"] in manifest_hashes


class TestMissingIngredientsFailClosed:
    """Missing ingredients fail closed."""

    def test_missing_vo_fails(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, CompositionPlanError,
        )
        _, _, wc, timeline, manifest = base_components
        manifest = dict(manifest)
        manifest["candidates"] = [
            c for c in manifest["candidates"]
            if c["category"] != "narration"
        ]
        gen = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        with pytest.raises(CompositionPlanError, match="narration"):
            gen.generate(manifest, wc, timeline)

    def test_missing_visual_fails(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, CompositionPlanError,
        )
        _, _, wc, timeline, manifest = base_components
        manifest = dict(manifest)
        manifest["candidates"] = [
            c for c in manifest["candidates"]
            if c["category"] != "visual"
        ]
        gen = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        with pytest.raises(CompositionPlanError, match="visual"):
            gen.generate(manifest, wc, timeline)

    def test_missing_artifact_hash_fails(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, CompositionPlanError,
        )
        _, _, wc, timeline, manifest = base_components
        manifest = dict(manifest)
        manifest["candidates"] = [
            {**c, "artifact_hash": None}
            for c in manifest["candidates"]
        ]
        gen = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        with pytest.raises(CompositionPlanError, match="artifact_hash"):
            gen.generate(manifest, wc, timeline)

    def test_writer_contract_hash_mismatch_fails(self, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, CompositionPlanError,
        )
        _, _, wc, timeline, manifest = base_components
        manifest = dict(manifest)
        manifest["writer_contract_hash"] = "x" * 64
        gen = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(),
            mix_config=_mix_config(),
        )
        with pytest.raises(CompositionPlanError, match="hash mismatch"):
            gen.generate(manifest, wc, timeline)


class TestSerializableDiffable:
    """Plan is serializable and diffable."""

    def test_serialize_deserialize_roundtrip(self, generator, base_components):
        from services.composition_plan import (
            serialize_plan, deserialize_plan,
        )
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        json_str = serialize_plan(plan)
        restored = deserialize_plan(json_str)
        assert restored == plan

    def test_serialized_is_valid_json(self, generator, base_components):
        from services.composition_plan import serialize_plan
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        json_str = serialize_plan(plan)
        parsed = json.loads(json_str)
        assert parsed["plan_hash"] == plan["plan_hash"]

    def test_diff_produces_output(self, generator, base_components):
        from services.composition_plan import (
            CompositionPlanGenerator, diff_plans,
        )
        _, _, wc, timeline, manifest = base_components

        gen_a = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(fps=30),
            mix_config=_mix_config(),
        )
        gen_b = CompositionPlanGenerator(
            render_styles=_render_styles(),
            font_config=_font_config(),
            canvas_config=_canvas_config(fps=60),
            mix_config=_mix_config(),
        )
        plan_a = gen_a.generate(manifest, wc, timeline)
        plan_b = gen_b.generate(manifest, wc, timeline)

        diff = diff_plans(plan_a, plan_b)
        assert isinstance(diff, str)
        assert len(diff) > 0
        assert "30" in diff or "60" in diff

    def test_identical_plans_produce_empty_diff(self, generator, base_components):
        from services.composition_plan import diff_plans
        _, _, wc, timeline, manifest = base_components
        plan_a = generator.generate(manifest, wc, timeline)
        plan_b = generator.generate(manifest, wc, timeline)
        diff = diff_plans(plan_a, plan_b)
        assert diff == ""


class TestPlanStructure:
    """Plan contains all required structural sections."""

    def test_has_all_sections(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        required = [
            "schema_version", "manifest_hash", "writer_contract_hash",
            "text_hash", "canvas", "text_elements", "audio",
            "visual_elements", "graphics_elements", "transitions",
            "total_duration_sec", "plan_hash",
        ]
        for key in required:
            assert key in plan, f"Missing plan section: {key}"

    def test_canvas_has_required_fields(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        canvas = plan["canvas"]
        for key in ["resolution", "aspect_ratio", "fps", "background",
                     "safe_zones", "platform_framing"]:
            assert key in canvas, f"Missing canvas field: {key}"

    def test_audio_has_required_fields(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        audio = plan["audio"]
        for key in ["vo_track", "music_track", "sfx_events", "mix_spec"]:
            assert key in audio, f"Missing audio field: {key}"

    def test_text_elements_have_required_fields(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        for te in plan["text_elements"]:
            for key in ["element_id", "role", "text", "text_intent_id",
                        "beat_id", "font", "style_ref", "position",
                        "timing", "word_timing", "emphasis_marks"]:
                assert key in te, f"Missing text element field: {key}"
            for key in ["file_hash", "family", "weight", "size", "color",
                        "border_width", "border_color", "shadow"]:
                assert key in te["font"], f"Missing font field: {key}"

    def test_visual_elements_have_required_fields(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        for ve in plan["visual_elements"]:
            for key in ["element_id", "source_hash", "manifest_candidate_id",
                        "kind", "trim_start_sec", "trim_end_sec", "crop",
                        "focal", "canvas_position", "scale",
                        "motion_keyframes", "beat_id", "event_id"]:
                assert key in ve, f"Missing visual element field: {key}"

    def test_transitions_have_required_fields(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        # Beats b01 (cut) and b02 (crossfade) → at least 2 transitions
        assert len(plan["transitions"]) >= 2
        for tr in plan["transitions"]:
            for key in ["transition_id", "type", "duration_sec",
                        "easing", "beat_boundary"]:
                assert key in tr, f"Missing transition field: {key}"

    def test_graphics_elements_have_required_fields(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        for ge in plan["graphics_elements"]:
            for key in ["element_id", "type", "config_hash", "position",
                        "scale", "timing", "animation", "beat_id"]:
                assert key in ge, f"Missing graphics element field: {key}"


class TestIdempotentGeneration:
    """Same inputs produce same plan hash."""

    def test_idempotent(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan_a = generator.generate(manifest, wc, timeline)
        plan_b = generator.generate(manifest, wc, timeline)
        assert plan_a["plan_hash"] == plan_b["plan_hash"]


class TestValidationCatchesTampering:
    """validate_plan catches tampering."""

    def test_tampered_text_detected(self, generator, base_components):
        from services.composition_plan import validate_plan
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        plan["text_elements"][0]["text"] = "TAMPERED TEXT"
        errors = validate_plan(plan, manifest, wc)
        assert any("text" in e.lower() for e in errors)

    def test_tampered_hash_detected(self, generator, base_components):
        from services.composition_plan import validate_plan
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        plan["plan_hash"] = "0" * 64
        errors = validate_plan(plan, manifest, wc)
        assert any("plan hash" in e.lower() for e in errors)

    def test_tampered_source_hash_detected(self, generator, base_components):
        from services.composition_plan import validate_plan
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        plan["visual_elements"][0]["source_hash"] = "z" * 64
        errors = validate_plan(plan, manifest, wc)
        assert any("source_hash" in e.lower() for e in errors)


class TestSfxAndMix:
    """SFX events and mix spec are correctly compiled."""

    def test_sfx_events_from_audio_intent(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        sfx = plan["audio"]["sfx_events"]
        # Beat b01 has sfx [{"type": "pop", "timing": "on_beat"}]
        assert len(sfx) >= 1
        assert sfx[0]["preset"] == "pop"

    def test_mix_spec_values(self, generator, base_components):
        _, _, wc, timeline, manifest = base_components
        plan = generator.generate(manifest, wc, timeline)
        mix = plan["audio"]["mix_spec"]
        assert mix["lufs_target"] == -14.0
        assert mix["true_peak_db"] == -1.0