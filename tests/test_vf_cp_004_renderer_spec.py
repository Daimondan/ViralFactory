"""
VF-CP-004 — RendererSpec compilation from ratified CompositionPlan.

Tests:
  - Compile a ratified plan → RendererSpec v1
  - Unratified plan cannot compile
  - Stale plan (hash mismatch) cannot compile
  - Rejected plan (state != composition_ratified) cannot compile
  - RendererSpec round-trip preserves all element hashes
  - Two different plans produce different specs
  - Spec hash is canonical (key-order independent)
  - Spec inherits composition plan hash as identity
  - Unsupported mandatory features return structured blockers
"""

import json
import os
import sys
import tempfile

import pytest

# Ensure src is on the path
src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)


# ── Shared fixture helpers (mirror test_vf_cp_001) ───────────────────────

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
        "font_path": "",
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


def _generate_plan(render_styles=None, font_config=None, canvas_config=None,
                   mix_config=None):
    """Generate a CompositionPlan dict from the default fixtures."""
    from services.composition_plan import CompositionPlanGenerator
    beats = _beats()
    text_intents = _text_intents()
    wc = _writer_contract(beats, text_intents)
    timeline = _cue_timeline(beats, text_intents)
    manifest = _manifest(beats, wc["writer_contract_hash"])
    gen = CompositionPlanGenerator(
        render_styles=render_styles or _render_styles(),
        font_config=font_config or _font_config(),
        canvas_config=canvas_config or _canvas_config(),
        mix_config=mix_config or _mix_config(),
    )
    return gen.generate(manifest, wc, timeline)


# ── DB / session setup fixture ──────────────────────────────────────────

@pytest.fixture
def db_env(tmp_path):
    """Create a temp DB with a production session transitioned to
    composition_ratified, and return (db_path, business_slug, session_id,
    plan)."""
    from services.production_orchestrator import ProductionSessionService

    db_path = str(tmp_path / "test_vf.db")
    business_slug = "test_tenant"

    plan = _generate_plan()

    svc = ProductionSessionService(db_path=db_path)
    session = svc.create_session(
        business_slug=business_slug,
        draft_id=1,
        asset_id=1,
        platform="IG",
        format="reel",
        writer_contract_hash="w" * 64,
    )
    session_id = session["id"]

    # Transition: planning → generating → component_review → manifest_ready
    #   → composition_planning → composition_review_required → composition_ratified
    svc.transition(business_slug, session_id, "generating_components")
    svc.transition(business_slug, session_id, "component_review_required")
    svc.transition(business_slug, session_id, "manifest_ready")
    svc.transition(business_slug, session_id, "composition_planning")
    svc.transition(business_slug, session_id, "composition_review_required")
    svc.transition(business_slug, session_id, "composition_ratified")

    # Set the active composition plan hash
    svc.set_composition_plan_hash(business_slug, session_id, plan["plan_hash"])

    return db_path, business_slug, session_id, plan


# ── Tests ────────────────────────────────────────────────────────────────

class TestCompileRatifiedPlan:
    """Compile a ratified plan into a RendererSpec v1."""

    def test_compiles_ratifed_plan(self, db_env):
        from services.renderer_spec import RendererSpecCompiler, RENDERER_SPEC_VERSION

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        assert spec["spec_version"] == RENDERER_SPEC_VERSION
        assert "spec_hash" in spec
        assert len(spec["spec_hash"]) == 64

    def test_spec_has_identity(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        identity = spec["identity"]
        assert identity["composition_plan_hash"] == plan["plan_hash"]
        assert identity["session_id"] == sid
        assert identity["asset_id"] == 1
        assert identity["business_slug"] == slug

    def test_spec_has_canvas(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        canvas = spec["canvas"]
        assert canvas["width"] == 1080
        assert canvas["height"] == 1920
        assert canvas["fps"] == 30
        assert canvas["aspect_ratio"] == "9:16"

    def test_spec_has_timeline(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        timeline = spec["timeline"]
        assert len(timeline) > 0
        types = {el["type"] for el in timeline}
        # Should have text, visual, audio, graphics, and/or transition
        assert "text" in types

    def test_spec_has_audio_automation(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        aa = spec["audio_automation"]
        assert "lufs_target" in aa
        assert "tracks" in aa
        assert isinstance(aa["tracks"], list)


class TestUnratifiedPlanCannotCompile:
    """Unratified plans cannot compile."""

    def test_wrong_state_rejected(self, tmp_path):
        from services.production_orchestrator import ProductionSessionService
        from services.renderer_spec import RendererSpecCompiler, RendererSpecError

        db_path = str(tmp_path / "test_vf.db")
        slug = "test_tenant"
        plan = _generate_plan()

        svc = ProductionSessionService(db_path=db_path)
        session = svc.create_session(
            business_slug=slug, draft_id=1, asset_id=1,
            platform="IG", format="reel",
        )
        sid = session["id"]
        # Transition only to manifest_ready — NOT ratified
        svc.transition(slug, sid, "generating_components")
        svc.transition(slug, sid, "component_review_required")
        svc.transition(slug, sid, "manifest_ready")

        compiler = RendererSpecCompiler(db_path=db_path)
        with pytest.raises(RendererSpecError, match="composition_ratified"):
            compiler.compile(slug, sid, plan)

    def test_no_active_plan_hash_rejected(self, tmp_path):
        from services.production_orchestrator import ProductionSessionService
        from services.renderer_spec import RendererSpecCompiler, RendererSpecError

        db_path = str(tmp_path / "test_vf.db")
        slug = "test_tenant"
        plan = _generate_plan()

        svc = ProductionSessionService(db_path=db_path)
        session = svc.create_session(
            business_slug=slug, draft_id=1, asset_id=1,
            platform="IG", format="reel",
        )
        sid = session["id"]
        # Transition to ratified state but don't set the plan hash
        svc.transition(slug, sid, "generating_components")
        svc.transition(slug, sid, "component_review_required")
        svc.transition(slug, sid, "manifest_ready")
        svc.transition(slug, sid, "composition_planning")
        svc.transition(slug, sid, "composition_review_required")
        svc.transition(slug, sid, "composition_ratified")

        compiler = RendererSpecCompiler(db_path=db_path)
        with pytest.raises(RendererSpecError, match="active composition plan hash"):
            compiler.compile(slug, sid, plan)


class TestStalePlanCannotCompile:
    """Stale plans (hash mismatch with session's ratified hash) cannot compile."""

    def test_stale_plan_hash_mismatch(self, db_env):
        from services.renderer_spec import RendererSpecCompiler, RendererSpecError

        db_path, slug, sid, plan = db_env

        # Generate a different plan with a different hash
        stale_plan = _generate_plan(
            canvas_config=_canvas_config(aspect="16:9",
                                         res={"width": 1920, "height": 1080}),
        )
        assert stale_plan["plan_hash"] != plan["plan_hash"]

        compiler = RendererSpecCompiler(db_path=db_path)
        with pytest.raises(RendererSpecError, match="Stale plan"):
            compiler.compile(slug, sid, stale_plan)

    def test_tampered_plan_hash_rejected(self, db_env):
        """Plan whose declared hash doesn't match computed hash."""
        from services.renderer_spec import RendererSpecCompiler, RendererSpecError

        db_path, slug, sid, plan = db_env

        # Tamper: change text but keep old hash
        tampered = json.loads(json.dumps(plan))
        tampered["text_elements"][0]["text"] = "TAMPERED TEXT"
        # Keep the original (now-stale) plan_hash
        # The compiler checks both session hash match AND internal integrity

        compiler = RendererSpecCompiler(db_path=db_path)
        with pytest.raises(RendererSpecError):
            compiler.compile(slug, sid, tampered)


class TestRoundTripPreservesHashes:
    """RendererSpec round-trip preserves all element hashes."""

    def test_text_source_hashes_preserved(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        plan_text_hashes = {
            te["font"]["file_hash"] for te in plan["text_elements"]
            if te.get("font", {}).get("file_hash")
        }
        spec_text_hashes = {
            el["source_hash"] for el in spec["timeline"]
            if el["type"] == "text" and el.get("source_hash")
        }
        assert plan_text_hashes <= spec_text_hashes

    def test_visual_source_hashes_preserved(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        plan_visual_hashes = {
            ve["source_hash"] for ve in plan["visual_elements"]
        }
        spec_visual_hashes = {
            el["source_hash"] for el in spec["timeline"]
            if el["type"] == "visual"
        }
        assert plan_visual_hashes <= spec_visual_hashes

    def test_audio_source_hashes_preserved(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        plan_audio_hashes = set()
        vo = plan["audio"].get("vo_track")
        if vo:
            plan_audio_hashes.add(vo["source_hash"])
        music = plan["audio"].get("music_track")
        if music:
            plan_audio_hashes.add(music["source_hash"])

        spec_audio_hashes = {
            el.get("source_hash") for el in spec["timeline"]
            if el["type"] == "audio" and el.get("source_hash")
        }
        assert plan_audio_hashes <= spec_audio_hashes

    def test_graphics_config_hashes_preserved(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        plan_gfx_hashes = {
            gfx["config_hash"] for gfx in plan["graphics_elements"]
        }
        spec_gfx_hashes = {
            el["config_hash"] for el in spec["timeline"]
            if el["type"] == "graphics" and el.get("config_hash")
        }
        assert plan_gfx_hashes <= spec_gfx_hashes

    def test_json_round_trip_preserves_spec(self, db_env):
        from services.renderer_spec import RendererSpecCompiler, compute_spec_hash

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        serialized = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        restored = json.loads(serialized)
        assert restored["spec_hash"] == spec["spec_hash"]
        assert compute_spec_hash(restored) == spec["spec_hash"]


class TestTwoPlansProduceDifferentSpecs:
    """Two tenant/style fixtures produce visibly different specs."""

    def test_different_canvas_produces_different_spec(self, tmp_path):
        from services.production_orchestrator import ProductionSessionService
        from services.renderer_spec import RendererSpecCompiler

        db_path = str(tmp_path / "test_vf.db")
        slug = "test_tenant"

        plan_a = _generate_plan(
            canvas_config=_canvas_config(aspect="9:16",
                                         res={"width": 1080, "height": 1920}),
        )
        plan_b = _generate_plan(
            canvas_config=_canvas_config(aspect="16:9",
                                         res={"width": 1920, "height": 1080}),
        )

        svc = ProductionSessionService(db_path=db_path)

        # Session A
        sa = svc.create_session(business_slug=slug, draft_id=1, asset_id=1,
                                platform="IG", format="reel")
        sid_a = sa["id"]
        for target in ["generating_components", "component_review_required",
                       "manifest_ready", "composition_planning",
                       "composition_review_required", "composition_ratified"]:
            svc.transition(slug, sid_a, target)
        svc.set_composition_plan_hash(slug, sid_a, plan_a["plan_hash"])

        # Session B
        sb = svc.create_session(business_slug=slug, draft_id=2, asset_id=2,
                                platform="IG", format="reel")
        sid_b = sb["id"]
        for target in ["generating_components", "component_review_required",
                       "manifest_ready", "composition_planning",
                       "composition_review_required", "composition_ratified"]:
            svc.transition(slug, sid_b, target)
        svc.set_composition_plan_hash(slug, sid_b, plan_b["plan_hash"])

        compiler = RendererSpecCompiler(db_path=db_path)
        spec_a = compiler.compile(slug, sid_a, plan_a)
        spec_b = compiler.compile(slug, sid_b, plan_b)

        assert spec_a["spec_hash"] != spec_b["spec_hash"]
        assert spec_a["canvas"]["width"] == 1080
        assert spec_b["canvas"]["width"] == 1920
        assert spec_a["canvas"]["aspect_ratio"] == "9:16"
        assert spec_b["canvas"]["aspect_ratio"] == "16:9"

    def test_different_style_produces_different_spec(self, tmp_path):
        from services.production_orchestrator import ProductionSessionService
        from services.renderer_spec import RendererSpecCompiler

        db_path = str(tmp_path / "test_vf.db")
        slug = "test_tenant"

        plan_a = _generate_plan(
            render_styles=_render_styles(styles={
                "hook": {"fontsize": 72, "fontcolor": "white", "borderw": 4,
                          "bordercolor": "black"},
            }),
        )
        plan_b = _generate_plan(
            render_styles=_render_styles(styles={
                "hook": {"fontsize": 96, "fontcolor": "#F2B705", "borderw": 4,
                          "bordercolor": "black"},
            }),
        )
        assert plan_a["plan_hash"] != plan_b["plan_hash"]

        svc = ProductionSessionService(db_path=db_path)

        sa = svc.create_session(business_slug=slug, draft_id=1, asset_id=1,
                                platform="IG", format="reel")
        sid_a = sa["id"]
        for target in ["generating_components", "component_review_required",
                       "manifest_ready", "composition_planning",
                       "composition_review_required", "composition_ratified"]:
            svc.transition(slug, sid_a, target)
        svc.set_composition_plan_hash(slug, sid_a, plan_a["plan_hash"])

        sb = svc.create_session(business_slug=slug, draft_id=2, asset_id=2,
                                platform="IG", format="reel")
        sid_b = sb["id"]
        for target in ["generating_components", "component_review_required",
                       "manifest_ready", "composition_planning",
                       "composition_review_required", "composition_ratified"]:
            svc.transition(slug, sid_b, target)
        svc.set_composition_plan_hash(slug, sid_b, plan_b["plan_hash"])

        compiler = RendererSpecCompiler(db_path=db_path)
        spec_a = compiler.compile(slug, sid_a, plan_a)
        spec_b = compiler.compile(slug, sid_b, plan_b)

        assert spec_a["spec_hash"] != spec_b["spec_hash"]


class TestSpecHashCanonical:
    """Spec hash is canonical (key-order independent)."""

    def test_key_order_independent(self, db_env):
        from services.renderer_spec import RendererSpecCompiler, compute_spec_hash

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        # Reorder top-level keys
        reordered = {}
        keys = list(spec.keys())
        keys.reverse()
        for k in keys:
            reordered[k] = spec[k]

        assert compute_spec_hash(reordered) == compute_spec_hash(spec)

    def test_nested_key_order_independent(self, db_env):
        from services.renderer_spec import RendererSpecCompiler, compute_spec_hash

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        # Reorder identity keys
        identity = spec["identity"]
        reordered_identity = {}
        for k in reversed(list(identity.keys())):
            reordered_identity[k] = identity[k]
        spec_copy = json.loads(json.dumps(spec))
        spec_copy["identity"] = reordered_identity

        assert compute_spec_hash(spec_copy) == compute_spec_hash(spec)

    def test_compiler_compute_spec_hash_matches_module(self, db_env):
        from services.renderer_spec import RendererSpecCompiler, compute_spec_hash

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        assert compiler.compute_spec_hash(spec) == compute_spec_hash(spec)
        assert compiler.compute_spec_hash(spec) == spec["spec_hash"]


class TestSpecInheritsCompositionPlanHash:
    """Spec inherits the composition plan hash as an input hash."""

    def test_identity_contains_plan_hash(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        assert spec["identity"]["composition_plan_hash"] == plan["plan_hash"]

    def test_plan_hash_in_spec_hash(self, db_env):
        """The spec hash is derived from the spec content which includes
        the composition plan hash — so changing the plan hash changes the
        spec hash."""
        from services.renderer_spec import RendererSpecCompiler, compute_spec_hash

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        # If we change the plan hash, the spec hash should change
        spec_modified = json.loads(json.dumps(spec))
        spec_modified["identity"]["composition_plan_hash"] = "x" * 64
        assert compute_spec_hash(spec_modified) != spec["spec_hash"]


class TestValidateSpec:
    """validate_spec round-trip."""

    def test_valid_spec_passes(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        ok, errors = compiler.validate_spec(spec)
        assert ok, f"Validation errors: {errors}"
        assert errors == []

    def test_missing_field_fails(self):
        from services.renderer_spec import RendererSpecCompiler

        compiler = RendererSpecCompiler()
        ok, errors = compiler.validate_spec({"spec_version": "1.0"})
        assert not ok
        assert any("identity" in e for e in errors)

    def test_spec_hash_mismatch_fails(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        # Corrupt the spec hash
        spec["spec_hash"] = "0" * 64
        ok, errors = compiler.validate_spec(spec)
        assert not ok
        assert any("hash mismatch" in e.lower() for e in errors)


class TestUnsupportedFeatures:
    """Unsupported mandatory features return structured blockers."""

    def test_check_capabilities_returns_structure(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        result = compiler.check_capabilities(spec)
        assert "supported" in result
        assert "missing" in result
        assert "required" in result
        assert isinstance(result["required"], list)
        assert result["supported"] is True  # local adapter supports all

    def test_missing_capability_returns_blockers(self, db_env):
        from services.renderer_spec import (
            RendererSpecCompiler, check_adapter_capabilities,
        )

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        # Adapter that supports nothing
        result = check_adapter_capabilities([], compiler.check_capabilities(spec)["required"])
        assert result["supported"] is False
        assert len(result["missing"]) > 0


class TestSerializable:
    """RendererSpec is serializable."""

    def test_serializable_to_json(self, db_env):
        from services.renderer_spec import RendererSpecCompiler

        db_path, slug, sid, plan = db_env
        compiler = RendererSpecCompiler(db_path=db_path)
        spec = compiler.compile(slug, sid, plan)

        # Must be JSON-serializable
        json_str = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        restored = json.loads(json_str)
        assert restored == spec