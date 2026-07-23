"""Tests for VF-CP-003: Composition ratification surface.

Tests cover:
  - Build ratification view with a plan
  - Ratify a plan (status → ratified, spec hash bound)
  - Reject a plan (status → rejected, transitions back to composition_planning)
  - Stale detection (plan hash mismatch after ratification)
  - Ratify enabled only when previews are generated
  - Ratify enabled only when all elements trace to approved manifest ingredients
  - No false greens (missing previews → not ready)
  - Multiple ratification versions (re-ratify after stale)
"""

import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

import pytest

# Ensure src is importable
src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# ── Fixture helpers (shared with VF-CP-002 tests) ──────────────────────────

import matplotlib

_MPL_FONT_DIR = os.path.join(
    os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"
)
_VALID_BODY = os.path.join(_MPL_FONT_DIR, "DejaVuSans-Bold.ttf")
_VALID_DISPLAY = os.path.join(_MPL_FONT_DIR, "DejaVuSans.ttf")

MODELS_CONFIG = {
    "rendering": {
        "font_path": _VALID_BODY,
        "font_display": _VALID_DISPLAY,
    }
}


def _make_test_image(path: str, w: int = 400, h: int = 600, color=(100, 150, 200)):
    from PIL import Image
    img = Image.new("RGBA", (w, h), color + (255,))
    img.save(path)


def _make_test_wav(path: str, duration_s: float = 1.0, freq: float = 440.0):
    import wave
    import struct
    import math
    sr = 8000
    n = int(sr * duration_s)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", int(32767 * 0.5 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(n)
        )
        wf.writeframes(frames)


def _make_text_element(
    element_id="text_001",
    role="hook",
    text="Hello World",
    style_ref="hook",
    x=0.5,
    y=0.3,
    size=64,
    color="white",
    in_sec=0.0,
    out_sec=2.0,
    text_intent_id="ti_001",
    beat_id="beat_001",
):
    return {
        "element_id": element_id,
        "role": role,
        "text": text,
        "text_intent_id": text_intent_id,
        "beat_id": beat_id,
        "font": {
            "file_hash": "abc123",
            "family": "DejaVu",
            "weight": "Bold",
            "size": size,
            "color": color,
            "border_width": 3,
            "border_color": "black",
            "shadow": None,
        },
        "style_ref": style_ref,
        "position": {"x": x, "y": y, "anchor": "center"},
        "timing": {"in_sec": in_sec, "out_sec": out_sec},
        "word_timing": [],
        "emphasis_marks": [],
    }


def _make_visual_element(
    element_id="vis_001",
    source_hash="hash_001",
    kind="still",
    trim_start=0.0,
    trim_end=2.0,
    scale=1.0,
    crop=None,
):
    return {
        "element_id": element_id,
        "source_hash": source_hash,
        "manifest_candidate_id": "cand_001",
        "kind": kind,
        "trim_start_sec": trim_start,
        "trim_end_sec": trim_end,
        "crop": crop,
        "focal": None,
        "canvas_position": {"x": 0.0, "y": 0.0},
        "scale": scale,
        "motion_keyframes": [],
        "beat_id": "beat_001",
        "event_id": None,
    }


def _make_graphics_element(
    element_id="gfx_text_001",
    gfx_type="overlay",
    x=0.5,
    y=0.7,
    scale=1.0,
    in_sec=0.0,
    out_sec=2.0,
):
    return {
        "element_id": element_id,
        "type": gfx_type,
        "config_hash": "cfg_hash_001",
        "position": {"x": x, "y": y, "anchor": "center"},
        "scale": scale,
        "timing": {"in_sec": in_sec, "out_sec": out_sec},
        "animation": {"type": "fade", "duration_sec": 0.3, "easing": "ease_in_out"},
        "beat_id": "beat_001",
    }


def _make_transition(
    transition_id="trans_001",
    trans_type="crossfade",
    duration=0.5,
    beat_boundary="beat_002",
):
    return {
        "transition_id": transition_id,
        "type": trans_type,
        "duration_sec": duration,
        "easing": "ease_in_out",
        "beat_boundary": beat_boundary,
    }


def _make_audio(
    vo_source_hash="vo_hash",
    music_source_hash="music_hash",
    total_dur=10.0,
    lufs_target=-14.0,
):
    return {
        "vo_track": {
            "source_hash": vo_source_hash,
            "manifest_candidate_id": "cand_vo",
            "trim_start_sec": 0.0,
            "trim_end_sec": total_dur,
            "gain_curve": [{"time_sec": 0.0, "gain_db": 0.0}],
            "ducking": {"depth": 0.20, "attack_s": 0.3, "release_s": 0.5},
        },
        "music_track": {
            "source_hash": music_source_hash,
            "manifest_candidate_id": "cand_music",
            "start_sec": 0.0,
            "stop_sec": total_dur,
            "gain_db": -3.0,
            "ducking": {"depth": 0.20, "attack_s": 0.3, "release_s": 0.5},
            "fade_in_sec": 0.5,
            "fade_out_sec": 1.0,
        },
        "sfx_events": [
            {
                "sfx_id": "sfx_001",
                "trigger_sec": 2.0,
                "gain_db": -6.0,
                "duration_sec": 0.15,
                "preset": "pop",
                "beat_id": "beat_001",
            },
        ],
        "mix_spec": {"lufs_target": lufs_target, "true_peak_db": -1.0},
    }


def _make_plan(
    text_elements=None,
    visual_elements=None,
    graphics_elements=None,
    transitions=None,
    audio=None,
    total_duration=10.0,
    plan_hash=None,
):
    from services.composition_preview import _plan_hash as _ph
    plan = {
        "schema_version": "1.0",
        "manifest_hash": "man_001",
        "writer_contract_hash": "wc_001",
        "text_hash": "txt_001",
        "canvas": {
            "resolution": {"width": 540, "height": 960},
            "aspect_ratio": "9:16",
            "fps": 30,
            "background": {"color": "#000000"},
            "safe_zones": {"title_safe": 0.9, "action_safe": 0.95},
            "platform_framing": "9:16_vertical",
        },
        "text_elements": text_elements or [],
        "audio": audio or {},
        "visual_elements": visual_elements or [],
        "graphics_elements": graphics_elements or [],
        "transitions": transitions or [],
        "total_duration_sec": total_duration,
    }
    plan["plan_hash"] = plan_hash or _ph(plan)
    return plan


def _make_manifest(candidate_hashes=None):
    """Build a minimal manifest dict for tracing tests."""
    hashes = candidate_hashes or ["vo_hash", "music_hash", "hash_001"]
    return {
        "manifest_hash": "man_001",
        "candidates": [
            {
                "candidate_id": f"cand_{i}",
                "category": "narration" if i == 0 else ("soundtrack" if i == 1 else "visual_media"),
                "role": "full_take" if i == 0 else ("background" if i == 1 else "primary"),
                "artifact_hash": h,
                "artifact_path": f"/tmp/fake_{h}.bin",
            }
            for i, h in enumerate(hashes)
        ],
    }


def _make_writer_contract(text_intents=None, beats=None):
    """Build a minimal writer contract for text tracing tests."""
    ti = text_intents or [
        {"text_intent_id": "ti_001", "beat_id": "beat_001",
         "function": "hook", "text": "Hello World", "required": True},
    ]
    return {
        "writer_contract_hash": "wc_001",
        "text_intents": ti,
        "beats": beats or [
            {"beat_id": "beat_001", "evidence_refs": ["source_1"]},
        ],
    }


# ── Session setup ──────────────────────────────────────────────────────────

def _setup_session(db_path: str, state: str = "composition_review_required"):
    """Create a minimal production session in the given state."""
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService

    store = PipelineStore(db_path=db_path)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug="test_tenant",
        idea="Test idea",
        hook_options=["Hook"],
        treatment={"format": "reel", "scope": "test", "capture_required": False},
        origin="human_seeded",
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    card = dict(conn.execute(
        "SELECT * FROM idea_cards ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
        "draft_text, draft_version, draft_state, created_at, updated_at) "
        "VALUES (?, ?, 'human_seeded', 'reel', 'test', '', 1, 'shipped', ?, ?)",
        ("test_tenant", card["id"], now, now))
    conn.commit()
    draft = dict(conn.execute(
        "SELECT * FROM drafts ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, asset_state, created_at, updated_at) "
        "VALUES (?, ?, 'IG', 'reel', 'Test', 'pending', ?, ?)",
        ("test_tenant", draft["id"], now, now))
    conn.commit()
    asset = dict(conn.execute(
        "SELECT * FROM assets ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()

    svc = ProductionSessionService(db_path=db_path)
    session = svc.create_session(
        "test_tenant", draft["id"], asset["id"], "IG", "reel")

    # Transition to the target state
    transitions = [
        ("generating_components", "requirements planned"),
        ("component_review_required", "candidates generated"),
        ("manifest_ready", "manifest frozen"),
        ("composition_planning", "plan started"),
        ("composition_review_required", "plan ready"),
    ]
    for to_state, reason in transitions:
        svc.transition("test_tenant", session["id"], to_state, reason)
        if to_state == state:
            break

    # If we need composition_ratified, continue from review
    if state == "composition_ratified":
        svc.transition(
            "test_tenant", session["id"],
            "composition_ratified", "ratified for test")

    return session, svc


# ── Pytest fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def tmp_env():
    """Create a temporary DB and preview cache."""
    tmpdir = tempfile.mkdtemp(prefix="vf_cp003_")
    db_path = os.path.join(tmpdir, "test_vf.db")
    cache_dir = os.path.join(tmpdir, "previews")
    os.makedirs(cache_dir, exist_ok=True)

    # Test fixture files
    bg_image = os.path.join(tmpdir, "bg.png")
    _make_test_image(bg_image, 800, 1200, (80, 100, 140))
    clip_image = os.path.join(tmpdir, "clip.png")
    _make_test_image(clip_image, 720, 1280, (120, 80, 160))
    audio_wav = os.path.join(tmpdir, "tone.wav")
    _make_test_wav(audio_wav, 1.5, 440)

    source_map = {
        "hash_001": clip_image,
        "vo_hash": audio_wav,
        "music_hash": audio_wav,
    }

    yield {
        "db_path": db_path,
        "cache_dir": cache_dir,
        "tmpdir": tmpdir,
        "bg_image": bg_image,
        "source_map": source_map,
    }

    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def ratification_service(tmp_env):
    from services.ratification_service import RatificationService
    return RatificationService(
        db_path=tmp_env["db_path"],
        config_dir=os.path.join(os.path.dirname(__file__), "..", "config"),
    )


@pytest.fixture
def preview_generator(tmp_env):
    from services.composition_preview import CompositionPreviewGenerator
    return CompositionPreviewGenerator(
        cache_dir=tmp_env["cache_dir"],
        models_config=MODELS_CONFIG,
        config_dir=os.path.join(os.path.dirname(__file__), "..", "config"),
        source_resolver=lambda h: tmp_env["source_map"].get(h, ""),
    )


def _generate_all_previews(gen, plan, bg_path=""):
    """Generate all previews and return the dict.

    If generation fails for some categories (e.g., missing audio),
    return partial previews instead of raising.
    """
    try:
        return gen.generate_all(plan, graphics_background=bg_path)
    except Exception:
        # Return partial previews — generate what we can individually
        previews = {}
        for te in plan.get("text_elements", []):
            try:
                previews.setdefault("text", []).append(gen.preview_text(plan, te))
            except Exception:
                pass
        for ve in plan.get("visual_elements", []):
            try:
                previews.setdefault("visual", []).append(gen.preview_visual(plan, ve))
            except Exception:
                pass
        try:
            previews.setdefault("timeline", []).append(gen.preview_timeline(plan))
        except Exception:
            pass
        return previews


# ── Tests ─────────────────────────────────────────────────────────────────


class TestBuildRatificationView:
    """Build ratification view with a plan."""

    def test_build_view_with_plan_and_previews(self, ratification_service, tmp_env):
        """Build view returns plan, previews, status, and ratify_enabled."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        plan = _make_plan(text_elements=[te])
        previews = {"text": ["text_text_001.png"], "timeline": ["timeline_full.png"]}

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews
        )

        assert view["plan"] == plan
        assert view["plan_hash"] == plan["plan_hash"]
        assert view["session"]["id"] == session["id"]
        assert view["previews"] == previews
        assert "status" in view
        assert "ratify_enabled" in view
        assert view["stale"] is False
        assert view["previous_ratification"] is None

    def test_build_view_status_plan_generated_when_no_previews(
        self, ratification_service, tmp_env
    ):
        """No previews → status is plan_generated, ratify disabled."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        plan = _make_plan(text_elements=[te])

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, {}
        )

        assert view["status"] == "plan_generated"
        assert view["ratify_enabled"] is False

    def test_build_view_includes_preview_gaps(self, ratification_service, tmp_env):
        """Missing previews are listed in preview_gaps."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        plan = _make_plan(text_elements=[te])

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, {}
        )

        assert len(view["preview_gaps"]) > 0
        assert any("text" in g for g in view["preview_gaps"])


class TestRatify:
    """Ratify a plan — status → ratified, spec hash bound."""

    def test_ratify_transitions_to_ratified(self, ratification_service, tmp_env,
                                             preview_generator):
        """Ratify transitions session to composition_ratified."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        ve = _make_visual_element()
        ge = _make_graphics_element()
        tr = _make_transition()
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te],
            visual_elements=[ve],
            graphics_elements=[ge],
            transitions=[tr],
            audio=audio,
            total_duration=5.0,
        )
        previews = _generate_all_previews(
            preview_generator, plan, bg_path=tmp_env["bg_image"]
        )

        decision = ratification_service.ratify(
            "test_tenant", session["id"], plan, previews,
            actor="operator", feedback="Looks good",
        )

        assert decision["decision"] == "ratify"
        assert decision["plan_hash"] == plan["plan_hash"]

        # Session is now composition_ratified
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])
        refreshed = svc.get_session("test_tenant", session["id"])
        assert refreshed["current_state"] == "composition_ratified"
        assert refreshed["active_composition_plan_hash"] == plan["plan_hash"]

    def test_ratify_binds_spec_hash(self, ratification_service, tmp_env,
                                     preview_generator):
        """Ratify binds the plan hash as the active composition plan hash."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        audio = _make_audio()
        plan = _make_plan(text_elements=[te], audio=audio, total_duration=5.0)
        previews = _generate_all_previews(preview_generator, plan)

        ratification_service.ratify(
            "test_tenant", session["id"], plan, previews)

        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])
        refreshed = svc.get_session("test_tenant", session["id"])
        assert refreshed["active_composition_plan_hash"] == plan["plan_hash"]

    def test_ratify_fails_when_previews_missing(self, ratification_service,
                                                 tmp_env):
        """Ratify fails closed when previews are incomplete."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        plan = _make_plan(text_elements=[te])

        with pytest.raises(Exception, match="not ready"):
            ratification_service.ratify(
                "test_tenant", session["id"], plan, {})

    def test_ratify_fails_from_wrong_state(self, ratification_service, tmp_env,
                                            preview_generator):
        """Ratify fails if session is not in composition_review_required."""
        session, _ = _setup_session(tmp_env["db_path"], state="composition_planning")
        te = _make_text_element()
        audio = _make_audio()
        plan = _make_plan(text_elements=[te], audio=audio, total_duration=5.0)
        previews = _generate_all_previews(preview_generator, plan)

        with pytest.raises(Exception, match="state"):
            ratification_service.ratify(
                "test_tenant", session["id"], plan, previews)


class TestReject:
    """Reject a plan — status → rejected, transitions back to composition_planning."""

    def test_reject_transitions_back_to_planning(self, ratification_service,
                                                  tmp_env):
        """Reject sends the session back to composition_planning."""
        session, _ = _setup_session(tmp_env["db_path"])
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])

        decision = ratification_service.reject(
            "test_tenant", session["id"],
            feedback="Text overlay is too small",
            actor="operator",
        )

        assert decision["decision"] == "reject"
        assert "too small" in decision["feedback"]

        refreshed = svc.get_session("test_tenant", session["id"])
        assert refreshed["current_state"] == "composition_planning"

    def test_reject_records_feedback(self, ratification_service, tmp_env):
        """Reject stores structured feedback in the decision record."""
        session, _ = _setup_session(tmp_env["db_path"])

        decision = ratification_service.reject(
            "test_tenant", session["id"],
            feedback="Audio mix needs ducking adjustment",
        )

        assert decision["feedback"] == "Audio mix needs ducking adjustment"
        assert decision["decision"] == "reject"

    def test_status_is_rejected_after_reject(self, ratification_service, tmp_env):
        """get_ratification_status returns 'rejected' after a reject."""
        session, _ = _setup_session(tmp_env["db_path"])
        ratification_service.reject(
            "test_tenant", session["id"], feedback="Bad")

        status = ratification_service.get_ratification_status(
            "test_tenant", session["id"])
        assert status == "rejected"


class TestStaleDetection:
    """Stale detection — plan hash mismatch after ratification."""

    def test_stale_after_plan_change(self, ratification_service, tmp_env,
                                      preview_generator):
        """Plan hash mismatch after ratification → stale."""
        session, _ = _setup_session(tmp_env["db_path"])

        # Ratify the original plan
        te = _make_text_element(text="Original hook")
        audio = _make_audio()
        plan_a = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0,
            plan_hash="plan_a_001")
        previews = _generate_all_previews(preview_generator, plan_a)

        ratification_service.ratify(
            "test_tenant", session["id"], plan_a, previews)

        # Now a new plan is generated with a different hash
        te_b = _make_text_element(text="Changed hook text")
        plan_b = _make_plan(
            text_elements=[te_b], audio=audio, total_duration=5.0,
            plan_hash="plan_b_002")

        stale = ratification_service.check_stale(
            "test_tenant", session["id"], plan_b["plan_hash"])
        assert stale is True

    def test_not_stale_when_hash_matches(self, ratification_service, tmp_env,
                                          preview_generator):
        """Same plan hash after ratification → not stale."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0,
            plan_hash="plan_stable_001")
        previews = _generate_all_previews(preview_generator, plan)

        ratification_service.ratify(
            "test_tenant", session["id"], plan, previews)

        stale = ratification_service.check_stale(
            "test_tenant", session["id"], plan["plan_hash"])
        assert stale is False

    def test_stale_status_in_view(self, ratification_service, tmp_env,
                                   preview_generator):
        """build_ratification_view reports stale=True after plan change."""
        session, _ = _setup_session(tmp_env["db_path"])

        te = _make_text_element(text="Original")
        audio = _make_audio()
        plan_a = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0,
            plan_hash="plan_v1_001")
        previews = _generate_all_previews(preview_generator, plan_a)

        ratification_service.ratify(
            "test_tenant", session["id"], plan_a, previews)

        # New plan with different hash
        te_b = _make_text_element(text="Changed")
        plan_b = _make_plan(
            text_elements=[te_b], audio=audio, total_duration=5.0,
            plan_hash="plan_v2_002")

        # Transition session back to composition_review_required for the
        # new plan (simulating re-review after plan change)
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])
        svc.transition("test_tenant", session["id"],
                       "composition_planning", "plan changed")
        svc.transition("test_tenant", session["id"],
                       "composition_review_required", "new plan ready")

        previews_b = _generate_all_previews(preview_generator, plan_b)

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan_b, previews_b)

        assert view["stale"] is True
        assert view["status"] == "stale"
        assert view["previous_ratification"] is not None
        assert view["previous_ratification"]["plan_hash"] == "plan_v1_001"


class TestRatifyEnabledPreviews:
    """Ratify enabled only when previews are generated."""

    def test_ratify_disabled_when_previews_missing(self, ratification_service,
                                                    tmp_env):
        """Missing previews → ratify_enabled=False."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        ve = _make_visual_element()
        plan = _make_plan(text_elements=[te], visual_elements=[ve])

        # Only text preview, missing visual, timeline, etc.
        previews = {"text": ["text_text_001.png"]}

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews)

        assert view["ratify_enabled"] is False
        assert view["status"] != "ready_for_review"

    def test_ratify_enabled_when_all_previews_generated(
        self, ratification_service, tmp_env, preview_generator
    ):
        """All previews generated → ratify_enabled=True."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        ve = _make_visual_element()
        ge = _make_graphics_element()
        tr = _make_transition()
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te],
            visual_elements=[ve],
            graphics_elements=[ge],
            transitions=[tr],
            audio=audio,
            total_duration=5.0,
        )
        previews = _generate_all_previews(
            preview_generator, plan, bg_path=tmp_env["bg_image"]
        )

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews)

        assert view["ratify_enabled"] is True
        assert view["status"] == "ready_for_review"


class TestRatifyEnabledManifestTracing:
    """Ratify enabled only when all elements trace to approved manifest."""

    def test_ratify_disabled_when_visual_hash_not_in_manifest(
        self, ratification_service, tmp_env, preview_generator
    ):
        """Visual element with source_hash not in manifest → disabled."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        # Use a hash that can be resolved for preview but is NOT in the manifest
        ve = _make_visual_element(source_hash="hash_001")
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te], visual_elements=[ve],
            audio=audio, total_duration=5.0)
        previews = _generate_all_previews(
            preview_generator, plan, bg_path=tmp_env["bg_image"])

        # Manifest contains vo_hash and music_hash but NOT hash_001
        manifest = _make_manifest(
            candidate_hashes=["vo_hash", "music_hash"])

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews, manifest=manifest)

        assert view["ratify_enabled"] is False
        assert any("not in manifest" in g for g in view["manifest_gaps"])

    def test_ratify_disabled_when_audio_hash_not_in_manifest(
        self, ratification_service, tmp_env, preview_generator
    ):
        """Audio VO source_hash not in manifest → disabled."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        audio = _make_audio(vo_source_hash="UNAPPROVED_VO")
        plan = _make_plan(text_elements=[te], audio=audio)
        previews = _generate_all_previews(preview_generator, plan)

        manifest = _make_manifest(candidate_hashes=["other_hash"])

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews, manifest=manifest)

        assert view["ratify_enabled"] is False
        assert any("VO" in g or "vo" in g.lower() for g in view["manifest_gaps"])

    def test_ratify_enabled_when_all_hashes_in_manifest(
        self, ratification_service, tmp_env, preview_generator
    ):
        """All source hashes in manifest → enabled."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        ve = _make_visual_element(source_hash="hash_001")
        audio = _make_audio()
        plan = _make_plan(text_elements=[te], visual_elements=[ve],
                          audio=audio, total_duration=5.0)
        previews = _generate_all_previews(preview_generator, plan)

        manifest = _make_manifest(
            candidate_hashes=["vo_hash", "music_hash", "hash_001"]
        )

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews, manifest=manifest)

        assert view["ratify_enabled"] is True

    def test_text_tracing_fails_for_mismatched_text(
        self, ratification_service, tmp_env, preview_generator
    ):
        """Text element that doesn't match writer contract → disabled."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element(text="WRONG TEXT", text_intent_id="ti_001")
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0)
        previews = _generate_all_previews(preview_generator, plan)

        wc = _make_writer_contract(text_intents=[
            {"text_intent_id": "ti_001", "beat_id": "beat_001",
             "function": "hook", "text": "Hello World", "required": True},
        ])

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews,
            writer_contract=wc)

        assert view["ratify_enabled"] is False
        assert any("text_intent" in g for g in view["manifest_gaps"])


class TestNoFalseGreens:
    """No false greens — missing previews must never show ready."""

    def test_empty_previews_not_ready(self, ratification_service, tmp_env):
        """Empty previews dict → never ready_for_review."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        ve = _make_visual_element()
        plan = _make_plan(text_elements=[te], visual_elements=[ve])

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, {})

        assert view["status"] != "ready_for_review"
        assert view["ratify_enabled"] is False

    def test_partial_previews_not_ready(self, ratification_service, tmp_env,
                                         preview_generator):
        """Some but not all previews → not ready_for_review."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        ve = _make_visual_element()
        ge = _make_graphics_element()
        tr = _make_transition()
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te],
            visual_elements=[ve],
            graphics_elements=[ge],
            transitions=[tr],
            audio=audio,
            total_duration=5.0,
        )

        # Generate text and timeline only — missing visual, graphics, etc.
        previews = {
            "text": [preview_generator.preview_text(plan, te)],
            "timeline": [preview_generator.preview_timeline(plan)],
        }

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews)

        assert view["ratify_enabled"] is False
        assert view["status"] != "ready_for_review"
        assert len(view["preview_gaps"]) > 0

    def test_previews_exist_but_files_missing(self, ratification_service,
                                               tmp_env):
        """Preview paths that don't exist on disk → not ready.

        The _has_preview helper checks file existence via the path,
        so phantom paths are detected.
        """
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        plan = _make_plan(text_elements=[te])

        # Pass paths that don't exist
        previews = {
            "text": ["/nonexistent/text_text_001.png"],
            "timeline": ["/nonexistent/timeline_full.png"],
        }

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews)

        assert view["ratify_enabled"] is False


class TestMultipleRatificationVersions:
    """Multiple ratification versions — re-ratify after stale."""

    def test_re_ratify_after_stale(self, ratification_service, tmp_env,
                                    preview_generator):
        """After stale, operator can re-ratify the new plan."""
        session, _ = _setup_session(tmp_env["db_path"])

        # Ratify plan v1
        te_a = _make_text_element(text="Version 1")
        audio = _make_audio()
        plan_a = _make_plan(
            text_elements=[te_a], audio=audio, total_duration=5.0,
            plan_hash="v1_001")
        previews_a = _generate_all_previews(preview_generator, plan_a)

        ratification_service.ratify(
            "test_tenant", session["id"], plan_a, previews_a)

        # Plan changes → stale
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])

        # Transition: ratified → planning → review
        svc.transition("test_tenant", session["id"],
                       "composition_planning", "post-ratification change")
        svc.transition("test_tenant", session["id"],
                       "composition_review_required", "new plan ready")

        te_b = _make_text_element(text="Version 2")
        plan_b = _make_plan(
            text_elements=[te_b], audio=audio, total_duration=5.0,
            plan_hash="v2_002")
        previews_b = _generate_all_previews(preview_generator, plan_b)

        # Check stale is detected via the view (check_stale only
        # returns True when session is still in composition_ratified;
        # after transitioning back to review, the view detects stale
        # by comparing against the previous ratification hash)
        view_b = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan_b, previews_b)
        assert view_b["stale"] is True
        assert view_b["status"] == "stale"

        # Re-ratify with the new plan
        decision_b = ratification_service.ratify(
            "test_tenant", session["id"], plan_b, previews_b)

        assert decision_b["decision"] == "ratify"
        assert decision_b["plan_hash"] == "v2_002"

        # Session is back to composition_ratified
        refreshed = svc.get_session("test_tenant", session["id"])
        assert refreshed["current_state"] == "composition_ratified"
        assert refreshed["active_composition_plan_hash"] == "v2_002"

    def test_ratification_history_preserved(self, ratification_service, tmp_env):
        """All ratification decisions are preserved in history."""
        session, _ = _setup_session(tmp_env["db_path"])

        # Reject first
        ratification_service.reject(
            "test_tenant", session["id"], feedback="First attempt no good")

        # Transition back to review
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])
        svc.transition("test_tenant", session["id"],
                       "composition_review_required", "plan ready again")

        # Get history
        history = ratification_service.get_ratification_history(
            "test_tenant", session["id"])

        assert len(history) >= 1
        assert history[0]["decision"] == "reject"

    def test_previous_ratification_shown_in_view(self, ratification_service,
                                                  tmp_env, preview_generator):
        """build_ratification_view shows previous ratification."""
        session, _ = _setup_session(tmp_env["db_path"])

        te = _make_text_element()
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0)
        previews = _generate_all_previews(preview_generator, plan)

        ratification_service.ratify(
            "test_tenant", session["id"], plan, previews)

        # Build view — should show the prior ratification
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_env["db_path"])
        svc.transition("test_tenant", session["id"],
                       "composition_planning", "plan changed")
        svc.transition("test_tenant", session["id"],
                       "composition_review_required", "new plan ready")

        view = ratification_service.build_ratification_view(
            "test_tenant", session["id"], plan, previews)

        assert view["previous_ratification"] is not None
        assert view["previous_ratification"]["decision"] == "ratify"


class TestGetRatificationStatus:
    """get_ratification_status returns the correct status."""

    def test_status_plan_generated_no_plan(self, ratification_service, tmp_env):
        """No plan provided → plan_generated."""
        session, _ = _setup_session(tmp_env["db_path"])

        status = ratification_service.get_ratification_status(
            "test_tenant", session["id"])

        assert status == "plan_generated"

    def test_status_ratified(self, ratification_service, tmp_env,
                              preview_generator):
        """Ratified session → ratified."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element()
        audio = _make_audio()
        plan = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0)
        previews = _generate_all_previews(preview_generator, plan)

        ratification_service.ratify(
            "test_tenant", session["id"], plan, previews)

        status = ratification_service.get_ratification_status(
            "test_tenant", session["id"], plan)
        assert status == "ratified"

    def test_status_stale_after_change(self, ratification_service, tmp_env,
                                        preview_generator):
        """Stale plan → stale status."""
        session, _ = _setup_session(tmp_env["db_path"])
        te = _make_text_element(text="v1")
        audio = _make_audio()
        plan_a = _make_plan(
            text_elements=[te], audio=audio, total_duration=5.0,
            plan_hash="stable_v1")
        previews = _generate_all_previews(preview_generator, plan_a)

        ratification_service.ratify(
            "test_tenant", session["id"], plan_a, previews)

        # New plan with different hash
        te_b = _make_text_element(text="v2")
        plan_b = _make_plan(
            text_elements=[te_b], audio=audio, total_duration=5.0,
            plan_hash="stable_v2")

        status = ratification_service.get_ratification_status(
            "test_tenant", session["id"], plan_b)
        assert status == "stale"