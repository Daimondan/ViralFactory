"""
VF-CW-008 — Typography and graphics specimens service tests.

Tests:
  - Register font specimen with exact hash
  - Missing font file blocks instead of silent fallback
  - Two tenants resolve different fonts with zero Python edits
  - Typography roles (hook, caption, emphasis, etc.) each produce separate candidates
  - Graphics overlay candidate registration
  - Transition candidate registration
  - Missing specimen blocks (missing overlay style)
  - Missing models.yaml rendering config blocks
  - check_font_exists fails closed
  - Explicit font_key / style_ref override replaces default
  - Approved typography candidates retrieval
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest
import yaml


# ── Fixtures ──

@pytest.fixture
def tmp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_vf.db")
    yield db_path, tmpdir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


def _make_font_file(tmpdir, name="test_font.ttf", seed=b"A"):
    """Create a fake font file (just bytes — we only hash it).

    The seed parameter makes each font unique so hashes differ.
    """
    path = os.path.join(tmpdir, name)
    with open(path, "wb") as f:
        f.write(b"\x00\x01\x00\x00FakeTrueTypeFontData" + seed * 128)
    return path


def _make_models_yaml(config_dir, font_path, font_display_path=None):
    """Write a minimal models.yaml with a rendering section."""
    rendering = {"font_path": font_path}
    if font_display_path:
        rendering["font_display"] = font_display_path
    data = {
        "active": {
            "default": "dummy",
            "drafter": "dummy",
        },
        "dummy": {
            "provider": "ollama_cloud",
            "model": "dummy",
            "temperature": 0,
            "max_tokens": 4096,
            "base_url": "https://ollama.com",
        },
        "rendering": rendering,
    }
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "models.yaml"), "w") as f:
        yaml.safe_dump(data, f)


def _make_render_styles_yaml(config_dir, extra_styles=None):
    """Write a minimal render_styles.yaml."""
    overlay_styles = {
        "default": {
            "fontsize": 48,
            "fontcolor": "white",
            "borderw": 3,
            "bordercolor": "black",
        },
        "hook": {
            "fontsize": 72,
            "fontcolor": "white",
            "borderw": 4,
            "bordercolor": "black",
        },
        "emphasis": {
            "fontsize": 56,
            "fontcolor": "white",
            "borderw": 3,
            "bordercolor": "black",
        },
        "caption": {
            "fontsize": 42,
            "fontcolor": "white",
            "borderw": 2,
            "bordercolor": "black",
        },
        "cta": {
            "fontsize": 52,
            "fontcolor": "white",
            "borderw": 3,
            "bordercolor": "black",
        },
    }
    if extra_styles:
        overlay_styles.update(extra_styles)
    data = {
        "overlay_styles": overlay_styles,
        "sfx_presets": {
            "pop": {"freq": "1200", "duration": 0.15, "volume": 0.5, "type": "sine"},
        },
        "sfx_default_preset": "pop",
    }
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "render_styles.yaml"), "w") as f:
        yaml.safe_dump(data, f)


def _setup_session(db_path, business_slug="test_tenant"):
    """Create a production session + asset in the DB."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService

    store = PipelineStore(db_path=db_path)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug=business_slug, idea="Test", hook_options=["Hook"],
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
        (business_slug, card["id"], now, now))
    conn.commit()
    draft = dict(conn.execute(
        "SELECT * FROM drafts ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, asset_state, created_at, updated_at) "
        "VALUES (?, ?, 'IG', 'reel', 'Test', 'pending', ?, ?)",
        (business_slug, draft["id"], now, now))
    conn.commit()
    asset = dict(conn.execute(
        "SELECT * FROM assets ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()

    svc = ProductionSessionService(db_path=db_path)
    session = svc.create_session(
        business_slug, draft["id"], asset["id"], "IG", "reel")
    return session, asset


@pytest.fixture
def typo_service(tmp_db):
    """A TypographyCandidateService with a valid config dir and font file."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    db_path, tmpdir = tmp_db
    config_dir = os.path.join(tmpdir, "config")
    modules_dir = os.path.join(tmpdir, "modules")
    font_path = _make_font_file(tmpdir, seed=b"X")
    font_display_path = _make_font_file(tmpdir, "display_font.ttf", seed=b"Y")

    _make_models_yaml(config_dir, font_path, font_display_path)
    _make_render_styles_yaml(config_dir)

    from pipeline import PipelineStore
    PipelineStore(db_path=db_path)

    from services.typography_candidates import TypographyCandidateService
    return TypographyCandidateService(
        db_path=db_path,
        config_dir=config_dir,
        modules_dir=modules_dir,
    ), db_path


# ── Tests ──

class TestRegisterFontSpecimen:
    def test_register_with_exact_hash(self, typo_service, tmp_db):
        """Register a font specimen and verify exact hash is present and bindable."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        candidate = svc.register_typography_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "hook_font",
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "typography"
        assert candidate["role"] == "hook_font"
        assert candidate["status"] == "available"

        # Exact hashes visible and bindable
        measurement = json.loads(candidate["measurement_json"])
        assert "font_hash" in measurement
        assert len(measurement["font_hash"]) == 64  # SHA-256 hex
        assert "style_hash" in measurement
        assert len(measurement["style_hash"]) == 64
        assert "specimen_hash" in measurement
        assert len(measurement["specimen_hash"]) == 64

        # artifact_hash is the specimen_hash — bindable
        assert candidate["artifact_hash"] == measurement["specimen_hash"]

        # Font path is recorded
        assert measurement["font_path"].endswith("test_font.ttf")
        assert candidate["artifact_path"] == measurement["font_path"]

        # Style ref resolved to 'hook' (the default for hook_font)
        assert measurement["style_ref"] == "hook"

    def test_register_caption_uses_default_style(self, typo_service, tmp_db):
        """caption_font role defaults to the 'caption' overlay style."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        candidate = svc.register_typography_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "caption_font",
        )
        measurement = json.loads(candidate["measurement_json"])
        assert measurement["style_ref"] == "caption"
        # caption_font defaults to font_path (not font_display)
        assert measurement["font_key"] == "font_path"


class TestMissingFontBlocks:
    def test_missing_font_file_raises(self, tmp_db):
        """Missing font file blocks instead of silently falling back."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        db_path, tmpdir = tmp_db
        config_dir = os.path.join(tmpdir, "config")
        modules_dir = os.path.join(tmpdir, "modules")

        # models.yaml points to a nonexistent font
        _make_models_yaml(config_dir, "/nonexistent/font.ttf")
        _make_render_styles_yaml(config_dir)

        from pipeline import PipelineStore
        PipelineStore(db_path=db_path)

        from services.typography_candidates import (
            TypographyCandidateService, TypographyCandidateError,
        )
        svc = TypographyCandidateService(
            db_path=db_path, config_dir=config_dir, modules_dir=modules_dir)

        session, asset = _setup_session(db_path)

        with pytest.raises(TypographyCandidateError, match="Font file does not exist"):
            svc.register_typography_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "hook_font",
            )

    def test_missing_rendering_config_blocks(self, tmp_db):
        """models.yaml without rendering.font_path blocks."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        db_path, tmpdir = tmp_db
        config_dir = os.path.join(tmpdir, "config")
        modules_dir = os.path.join(tmpdir, "modules")

        # models.yaml with no rendering section
        data = {
            "active": {"default": "dummy", "drafter": "dummy"},
            "dummy": {
                "provider": "ollama_cloud", "model": "dummy",
                "temperature": 0, "max_tokens": 4096,
                "base_url": "https://ollama.com",
            },
        }
        os.makedirs(config_dir, exist_ok=True)
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            yaml.safe_dump(data, f)
        _make_render_styles_yaml(config_dir)

        from pipeline import PipelineStore
        PipelineStore(db_path=db_path)

        from services.typography_candidates import (
            TypographyCandidateService, TypographyCandidateError,
        )
        svc = TypographyCandidateService(
            db_path=db_path, config_dir=config_dir, modules_dir=modules_dir)

        session, asset = _setup_session(db_path)

        with pytest.raises(TypographyCandidateError, match="not configured"):
            svc.register_typography_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "hook_font",
            )

    def test_check_font_exists_empty_path(self, typo_service):
        """check_font_exists fails closed on empty path."""
        from services.typography_candidates import TypographyCandidateError
        svc, _ = typo_service
        with pytest.raises(TypographyCandidateError, match="empty"):
            svc.check_font_exists("")

    def test_check_font_exists_missing_file(self, typo_service):
        """check_font_exists fails closed on missing file."""
        from services.typography_candidates import TypographyCandidateError
        svc, _ = typo_service
        with pytest.raises(TypographyCandidateError, match="does not exist"):
            svc.check_font_exists("/nonexistent/path.ttf")


class TestTwoTenantsDifferentFonts:
    def test_two_tenants_resolve_different_fonts(self, tmp_db):
        """Two tenants with different config dirs resolve different fonts with
        zero Python edits — pure config-driven variation."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        db_path, tmpdir = tmp_db

        # Tenant A: uses font_a.ttf
        config_a = os.path.join(tmpdir, "config_a")
        modules_a = os.path.join(tmpdir, "modules_a")
        font_a = _make_font_file(tmpdir, "font_a.ttf", seed=b"A")
        _make_models_yaml(config_a, font_a)
        _make_render_styles_yaml(config_a, extra_styles={
            "hook": {"fontsize": 100, "fontcolor": "red", "borderw": 5, "bordercolor": "black"},
        })

        # Tenant B: uses font_b.ttf + different hook style
        config_b = os.path.join(tmpdir, "config_b")
        modules_b = os.path.join(tmpdir, "modules_b")
        font_b = _make_font_file(tmpdir, "font_b.ttf", seed=b"B")
        _make_models_yaml(config_b, font_b)
        _make_render_styles_yaml(config_b, extra_styles={
            "hook": {"fontsize": 50, "fontcolor": "blue", "borderw": 1, "bordercolor": "white"},
        })

        from pipeline import PipelineStore
        PipelineStore(db_path=db_path)

        from services.typography_candidates import TypographyCandidateService

        svc_a = TypographyCandidateService(
            db_path=db_path, config_dir=config_a, modules_dir=modules_a)
        svc_b = TypographyCandidateService(
            db_path=db_path, config_dir=config_b, modules_dir=modules_b)

        session_a, asset_a = _setup_session(db_path, business_slug="tenant_a")
        session_b, asset_b = _setup_session(db_path, business_slug="tenant_b")

        cand_a = svc_a.register_typography_candidate(
            "tenant_a", session_a["id"], session_a["draft_id"],
            asset_a["id"], "hook_font")
        cand_b = svc_b.register_typography_candidate(
            "tenant_b", session_b["id"], session_b["draft_id"],
            asset_b["id"], "hook_font")

        meas_a = json.loads(cand_a["measurement_json"])
        meas_b = json.loads(cand_b["measurement_json"])

        # Different font files → different font hashes
        assert meas_a["font_hash"] != meas_b["font_hash"]
        assert meas_a["font_path"] != meas_b["font_path"]

        # Different hook styles → different style hashes
        assert meas_a["style_hash"] != meas_b["style_hash"]

        # Different specimen hashes (combined)
        assert meas_a["specimen_hash"] != meas_b["specimen_hash"]

        # Both are valid candidates
        assert cand_a["category"] == "typography"
        assert cand_b["category"] == "typography"
        assert cand_a["business_slug"] == "tenant_a"
        assert cand_b["business_slug"] == "tenant_b"


class TestTypographyRolesSeparate:
    @pytest.mark.parametrize("role", [
        "hook_font", "caption_font", "emphasis_font",
        "lower_third_font", "cta_font",
    ])
    def test_each_role_produces_separate_candidate(self, typo_service, tmp_db, role):
        """Each typography role produces a separate candidate with its own lineage."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        candidate = svc.register_typography_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], role,
        )

        assert candidate["role"] == role
        assert candidate["category"] == "typography"
        assert candidate["status"] == "available"

        measurement = json.loads(candidate["measurement_json"])
        assert measurement["role"] == role
        assert measurement["font_hash"] is not None
        assert measurement["style_hash"] is not None

    def test_all_roles_listed_together(self, typo_service, tmp_db):
        """All five typography roles produce five separate candidates."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        roles = ["hook_font", "caption_font", "emphasis_font",
                 "lower_third_font", "cta_font"]
        for role in roles:
            svc.register_typography_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], role,
            )

        candidates = svc.list_typography_candidates("test_tenant", session["id"])
        assert len(candidates) == 5
        listed_roles = {c["role"] for c in candidates}
        assert listed_roles == set(roles)

    def test_invalid_role_raises(self, typo_service, tmp_db):
        """Invalid role raises an error."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        from services.typography_candidates import TypographyCandidateError
        with pytest.raises(TypographyCandidateError, match="Invalid typography role"):
            svc.register_typography_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "invalid_role",
            )


class TestGraphicsOverlayCandidate:
    def test_register_overlay_graphic(self, typo_service, tmp_db):
        """Register a graphics overlay candidate."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        candidate = svc.register_graphics_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "overlay_graphic",
            beat_refs=["b01", "b02"],
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "graphics"
        assert candidate["role"] == "overlay_graphic"
        assert candidate["status"] == "available"

        measurement = json.loads(candidate["measurement_json"])
        assert measurement["style_ref"] == "default"
        assert len(measurement["style_hash"]) == 64
        assert len(measurement["specimen_hash"]) == 64

        # Graphics candidates have no font
        assert "font_hash" not in measurement

        # artifact_hash is the specimen hash
        assert candidate["artifact_hash"] == measurement["specimen_hash"]

    def test_overlay_with_explicit_style(self, typo_service, tmp_db):
        """Register overlay graphic with an explicit style_ref override."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        candidate = svc.register_graphics_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "overlay_graphic",
            style_ref="hook",
        )
        measurement = json.loads(candidate["measurement_json"])
        assert measurement["style_ref"] == "hook"


class TestTransitionCandidate:
    def test_register_transition(self, typo_service, tmp_db):
        """Register a transition candidate."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        candidate = svc.register_graphics_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "transition",
            beat_refs=["b01->b02"],
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "graphics"
        assert candidate["role"] == "transition"
        assert candidate["status"] == "available"

        measurement = json.loads(candidate["measurement_json"])
        assert measurement["style_ref"] == "default"
        assert len(measurement["specimen_hash"]) == 64

    def test_transition_and_overlay_are_separate(self, typo_service, tmp_db):
        """Transition and overlay_graphic are separate candidates."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        svc.register_graphics_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "overlay_graphic",
        )
        svc.register_graphics_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "transition",
        )

        graphics = svc.list_graphics_candidates("test_tenant", session["id"])
        assert len(graphics) == 2
        roles = {c["role"] for c in graphics}
        assert roles == {"overlay_graphic", "transition"}

    def test_invalid_graphics_role_raises(self, typo_service, tmp_db):
        """Invalid graphics role raises an error."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        from services.typography_candidates import TypographyCandidateError
        with pytest.raises(TypographyCandidateError, match="Invalid graphics role"):
            svc.register_graphics_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "invalid_graphics",
            )


class TestMissingSpecimenBlocks:
    def test_missing_overlay_style_blocks(self, tmp_db):
        """Missing overlay style blocks instead of silent fallback."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        db_path, tmpdir = tmp_db
        config_dir = os.path.join(tmpdir, "config")
        modules_dir = os.path.join(tmpdir, "modules")
        font_path = _make_font_file(tmpdir)
        _make_models_yaml(config_dir, font_path)

        # render_styles.yaml with NO 'hook' style
        _make_render_styles_yaml(config_dir, extra_styles={})
        # Remove hook from the base styles
        rs_path = os.path.join(config_dir, "render_styles.yaml")
        with open(rs_path) as f:
            data = yaml.safe_load(f)
        del data["overlay_styles"]["hook"]
        del data["overlay_styles"]["emphasis"]
        del data["overlay_styles"]["caption"]
        del data["overlay_styles"]["cta"]
        with open(rs_path, "w") as f:
            yaml.safe_dump(data, f)

        from pipeline import PipelineStore
        PipelineStore(db_path=db_path)

        from services.typography_candidates import (
            TypographyCandidateService, TypographyCandidateError,
        )
        svc = TypographyCandidateService(
            db_path=db_path, config_dir=config_dir, modules_dir=modules_dir)

        session, asset = _setup_session(db_path)

        # hook_font defaults to style_ref='hook' which doesn't exist
        with pytest.raises(TypographyCandidateError, match="not found"):
            svc.register_typography_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "hook_font",
            )

    def test_missing_graphics_style_blocks(self, tmp_db):
        """Missing graphics overlay style blocks instead of silent fallback."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        db_path, tmpdir = tmp_db
        config_dir = os.path.join(tmpdir, "config")
        modules_dir = os.path.join(tmpdir, "modules")
        font_path = _make_font_file(tmpdir)
        _make_models_yaml(config_dir, font_path)

        # render_styles.yaml with only 'default' — no extra styles
        with open(os.path.join(config_dir, "render_styles.yaml"), "w") as f:
            yaml.safe_dump({
                "overlay_styles": {
                    "default": {"fontsize": 48, "fontcolor": "white"},
                },
                "sfx_presets": {
                    "pop": {"freq": "1200", "duration": 0.15, "volume": 0.5, "type": "sine"},
                },
                "sfx_default_preset": "pop",
            }, f)

        from pipeline import PipelineStore
        PipelineStore(db_path=db_path)

        from services.typography_candidates import (
            TypographyCandidateService, TypographyCandidateError,
        )
        svc = TypographyCandidateService(
            db_path=db_path, config_dir=config_dir, modules_dir=modules_dir)

        session, asset = _setup_session(db_path)

        # Explicit style_ref that doesn't exist
        with pytest.raises(TypographyCandidateError, match="not found"):
            svc.register_graphics_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "overlay_graphic",
                style_ref="nonexistent_style",
            )

    def test_missing_models_yaml_blocks(self, tmp_db):
        """Missing models.yaml blocks entirely."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        db_path, tmpdir = tmp_db
        config_dir = os.path.join(tmpdir, "empty_config")
        modules_dir = os.path.join(tmpdir, "modules")
        os.makedirs(config_dir, exist_ok=True)
        _make_render_styles_yaml(config_dir)

        from pipeline import PipelineStore
        PipelineStore(db_path=db_path)

        from services.typography_candidates import (
            TypographyCandidateService, TypographyCandidateError,
        )
        svc = TypographyCandidateService(
            db_path=db_path, config_dir=config_dir, modules_dir=modules_dir)

        session, asset = _setup_session(db_path)

        with pytest.raises(TypographyCandidateError, match="models.yaml not found"):
            svc.register_typography_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "hook_font",
            )


class TestExplicitOverrides:
    def test_explicit_font_key_overrides_default(self, typo_service, tmp_db):
        """Explicit font_key replaces the default — requires an exact decision."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        # hook_font defaults to font_path; explicitly use font_display
        candidate = svc.register_typography_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "hook_font",
            font_key="font_display",
        )
        measurement = json.loads(candidate["measurement_json"])
        assert measurement["font_key"] == "font_display"
        assert measurement["font_path"].endswith("display_font.ttf")

    def test_explicit_style_ref_overrides_default(self, typo_service, tmp_db):
        """Explicit style_ref replaces the default — requires an exact decision."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        # hook_font defaults to style_ref='hook'; explicitly use 'cta'
        candidate = svc.register_typography_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "hook_font",
            style_ref="cta",
        )
        measurement = json.loads(candidate["measurement_json"])
        assert measurement["style_ref"] == "cta"


class TestApprovedTypography:
    def test_get_approved_typography(self, typo_service, tmp_db):
        """Approved typography candidates are retrievable."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        c = svc.register_typography_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "hook_font",
        )

        # No approved yet
        approved = svc.get_approved_typography("test_tenant", session["id"])
        assert approved == []

        # Approve it
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=db_path)
        store.record_decision("test_tenant", session["id"], c["id"], "approve")

        approved = svc.get_approved_typography("test_tenant", session["id"])
        assert len(approved) == 1
        assert approved[0]["id"] == c["id"]
        assert approved[0]["status"] == "approved"

    def test_get_approved_graphics(self, typo_service, tmp_db):
        """Approved graphics candidates are retrievable."""
        svc, db_path = typo_service
        session, asset = _setup_session(db_path)

        c = svc.register_graphics_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "transition",
        )

        assert svc.get_approved_graphics("test_tenant", session["id"]) == []

        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=db_path)
        store.record_decision("test_tenant", session["id"], c["id"], "approve")

        approved = svc.get_approved_graphics("test_tenant", session["id"])
        assert len(approved) == 1
        assert approved[0]["id"] == c["id"]


class TestResolveFontFile:
    def test_resolve_returns_hash(self, typo_service):
        """resolve_font_file returns path and hash."""
        svc, _ = typo_service
        info = svc.resolve_font_file("font_path")
        assert "font_path" in info
        assert "font_hash" in info
        assert len(info["font_hash"]) == 64
        assert os.path.isfile(info["font_path"])

    def test_resolve_unknown_key_raises(self, typo_service):
        """Resolving an unknown font key raises."""
        from services.typography_candidates import TypographyCandidateError
        svc, _ = typo_service
        with pytest.raises(TypographyCandidateError, match="not configured"):
            svc.resolve_font_file("nonexistent_font_key")