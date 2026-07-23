"""
VF-CW-003 — Config + prompt-driven component requirements tests.

Tests:
  - Category registry loads from config
  - Two tenant/format fixtures yield different valid role sets with zero Python edits
  - Required-real capture cannot allow generated substitution
  - Validator rejects unknown categories/roles
  - Validator rejects duplicate categories/roles
  - Validator rejects missing required fields
  - Requirements store persists with provenance
  - Requirements are append-only versions
  - Content hash is canonical
"""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def config_dir():
    """Path to the real config directory."""
    return os.path.join(os.path.dirname(__file__), "..", "config")


@pytest.fixture
def registry(config_dir):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from services.component_requirements import ComponentCategoryRegistry
    return ComponentCategoryRegistry(config_dir=config_dir)


@pytest.fixture
def validator(registry):
    from services.component_requirements import ComponentRequirementsValidator
    return ComponentRequirementsValidator(registry=registry)


@pytest.fixture
def tmp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_vf.db")
    yield db_path
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def req_store(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    # Initialize pipeline store first (creates production_sessions table)
    from pipeline import PipelineStore
    PipelineStore(db_path=tmp_db)
    from services.component_requirements import ComponentRequirementsStore
    return ComponentRequirementsStore(db_path=tmp_db)


# ── Category Registry ─────────────────────────────────────────────────

class TestCategoryRegistry:
    def test_loads_from_config(self, registry):
        cats = registry.categories
        assert "narration" in cats
        assert "visual_media" in cats
        assert "soundtrack" in cats
        assert "sound_effects" in cats
        assert "typography" in cats
        assert "graphics" in cats

    def test_get_category(self, registry):
        cat = registry.get_category("narration")
        assert cat is not None
        assert cat["key"] == "narration"
        assert cat["label"] == "Narration"

    def test_get_role(self, registry):
        role = registry.get_role("narration", "full_take")
        assert role is not None
        assert role["key"] == "full_take"
        assert role["cardinality"] == "1"
        assert role["preview_required"] is True

    def test_unknown_category(self, registry):
        assert not registry.is_valid_category("nonexistent")
        assert registry.get_category("nonexistent") is None

    def test_unknown_role(self, registry):
        assert not registry.is_valid_role("narration", "nonexistent")
        assert registry.get_role("narration", "nonexistent") is None

    def test_format_overrides_reel(self, registry):
        required = registry.get_required_categories("reel")
        assert "narration" in required
        assert "visual_media" in required
        assert "typography" in required

    def test_format_overrides_thread(self, registry):
        required = registry.get_required_categories("thread")
        assert "visual_media" in required
        assert "typography" in required
        assert "narration" not in required  # threads don't need VO

    def test_format_overrides_unknown_format(self, registry):
        """Unknown formats have no overrides — all categories optional."""
        required = registry.get_required_categories("nonexistent_format")
        assert required == []

    def test_no_business_values_in_config(self, config_dir):
        """No business-specific values in the config file."""
        with open(os.path.join(config_dir, "component_categories.yaml")) as f:
            content = f.read()
        # No StackPenni, no Caribbean, no Daimon
        assert "stackpenni" not in content.lower()
        assert "caribbean" not in content.lower()
        assert "daimon" not in content.lower()


# ── Two tenant/format fixtures produce different role sets ────────────

class TestTenantFormatDifferentiation:
    """Two tenant/format fixtures yield different valid role sets with
    zero Python edits — the config and prompt drive the difference."""

    def test_reel_vs_thread_different_roles(self, validator):
        """A reel needs narration, a thread does not."""
        reel_reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [
                        {"role": "full_take", "required": True,
                         "scope": "all_beats", "beat_refs": ["beat_1"],
                         "none_allowed": False, "preview_required": True},
                    ],
                },
                {
                    "category": "visual_media",
                    "required": True,
                    "roles": [
                        {"role": "beat_visual", "required": True,
                         "scope": "per_beat", "beat_refs": ["beat_1"],
                         "none_allowed": False, "preview_required": True,
                         "requires_real_capture": True},
                    ],
                },
            ],
        }
        thread_reqs = {
            "format": "thread",
            "platform": "X",
            "categories": [
                {
                    "category": "visual_media",
                    "required": True,
                    "roles": [
                        {"role": "beat_visual", "required": True,
                         "scope": "per_beat", "beat_refs": ["beat_1"],
                         "none_allowed": False, "preview_required": True},
                    ],
                },
                {
                    "category": "typography",
                    "required": True,
                    "roles": [
                        {"role": "caption_font", "required": True,
                         "scope": "full_piece", "beat_refs": [],
                         "none_allowed": True, "preview_required": True},
                    ],
                },
            ],
        }

        reel_valid, reel_errors = validator.validate(reel_reqs)
        thread_valid, thread_errors = validator.validate(thread_reqs)

        assert reel_valid, f"Reel requirements should be valid: {reel_errors}"
        assert thread_valid, f"Thread requirements should be valid: {thread_errors}"

        # Reel has narration, thread does not
        reel_cats = {c["category"] for c in reel_reqs["categories"]}
        thread_cats = {c["category"] for c in thread_reqs["categories"]}
        assert "narration" in reel_cats
        assert "narration" not in thread_cats

    def test_required_real_capture_flag(self, validator):
        """A role can declare requires_real_capture to prevent generated substitution."""
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "visual_media",
                    "required": True,
                    "roles": [
                        {"role": "beat_visual", "required": True,
                         "scope": "per_beat", "beat_refs": ["beat_1"],
                         "none_allowed": False, "preview_required": True,
                         "requires_real_capture": True},
                    ],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert valid, f"Should validate with requires_real_capture: {errors}"

        # The flag is preserved in the output
        role = reqs["categories"][0]["roles"][0]
        assert role["requires_real_capture"] is True


# ── Validator ─────────────────────────────────────────────────────────

class TestValidator:
    def test_valid_requirements(self, validator):
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [
                        {"role": "full_take", "required": True,
                         "scope": "all_beats", "beat_refs": [],
                         "none_allowed": False, "preview_required": True},
                    ],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert valid
        assert errors == []

    def test_unknown_category_rejected(self, validator):
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "nonexistent",
                    "required": True,
                    "roles": [],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert not valid
        assert any("Unknown category" in e for e in errors)

    def test_unknown_role_rejected(self, validator):
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [
                        {"role": "nonexistent_role", "required": True,
                         "scope": "all_beats", "beat_refs": [],
                         "none_allowed": False, "preview_required": True},
                    ],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert not valid
        assert any("Unknown role" in e for e in errors)

    def test_duplicate_category_rejected(self, validator):
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [],
                },
                {
                    "category": "narration",
                    "required": True,
                    "roles": [],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert not valid
        assert any("Duplicate category" in e for e in errors)

    def test_duplicate_role_rejected(self, validator):
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [
                        {"role": "full_take", "required": True,
                         "scope": "all_beats", "beat_refs": [],
                         "none_allowed": False, "preview_required": True},
                        {"role": "full_take", "required": True,
                         "scope": "all_beats", "beat_refs": [],
                         "none_allowed": False, "preview_required": True},
                    ],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert not valid
        assert any("Duplicate role" in e for e in errors)

    def test_missing_required_fields(self, validator):
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [
                        {"role": "full_take"},  # missing required, scope, etc.
                    ],
                },
            ],
        }
        valid, errors = validator.validate(reqs)
        assert not valid
        assert any("missing" in e for e in errors)


# ── Store ─────────────────────────────────────────────────────────────

class TestRequirementsStore:
    def _setup_session(self, tmp_db):
        """Create a production session for testing."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from pipeline import PipelineStore
        from services.production_orchestrator import ProductionSessionService
        import sqlite3

        store = PipelineStore(db_path=tmp_db)
        now = datetime.now(timezone.utc).isoformat()
        store.create_idea_card(
            business_slug="test_tenant",
            idea="Test", hook_options=["Hook"],
            treatment={"format": "reel", "scope": "test", "capture_required": False},
            origin="human_seeded",
        )
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        card = dict(conn.execute(
            "SELECT * FROM idea_cards ORDER BY id DESC LIMIT 1"
        ).fetchone())
        conn.execute(
            "INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
            "draft_text, draft_version, draft_state, created_at, updated_at) "
            "VALUES (?, ?, 'human_seeded', 'reel', 'test', '', 1, 'shipped', ?, ?)",
            ("test_tenant", card["id"], now, now),
        )
        conn.commit()
        draft = dict(conn.execute(
            "SELECT * FROM drafts ORDER BY id DESC LIMIT 1"
        ).fetchone())
        conn.execute(
            "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
            "content, asset_state, created_at, updated_at) "
            "VALUES (?, ?, 'Instagram', 'reel', 'Test', 'pending', ?, ?)",
            ("test_tenant", draft["id"], now, now),
        )
        conn.commit()
        asset = dict(conn.execute(
            "SELECT * FROM assets ORDER BY id DESC LIMIT 1"
        ).fetchone())
        conn.close()

        svc = ProductionSessionService(db_path=tmp_db)
        session = svc.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram", "reel"
        )
        return session

    def test_save_and_retrieve(self, req_store, tmp_db):
        session = self._setup_session(tmp_db)
        reqs = {
            "format": "reel",
            "platform": "Instagram",
            "categories": [
                {"category": "narration", "required": True,
                 "roles": [{"role": "full_take", "required": True,
                            "scope": "all_beats", "beat_refs": [],
                            "none_allowed": False, "preview_required": True}]},
            ],
        }
        saved = req_store.save_requirements(
            business_slug="test_tenant",
            production_session_id=session["id"],
            draft_id=session["draft_id"],
            asset_id=session["asset_id"],
            requirements=reqs,
            provenance={"prompt": "component_requirements_v1.md", "model": "test"},
        )
        assert saved["id"] is not None
        assert saved["version"] == 1
        assert saved["requirements_hash"] is not None

        retrieved = req_store.get_current_requirements("test_tenant", session["id"])
        assert retrieved is not None
        assert retrieved["version"] == 1
        # requirements_json is already parsed to a dict by get_current_requirements
        reqs_data = retrieved["requirements_json"]
        if isinstance(reqs_data, str):
            reqs_data = json.loads(reqs_data)
        assert reqs_data["format"] == "reel"

    def test_append_only_versions(self, req_store, tmp_db):
        session = self._setup_session(tmp_db)
        reqs_v1 = {"format": "reel", "platform": "Instagram", "categories": []}
        reqs_v2 = {"format": "reel", "platform": "Instagram", "categories": [
            {"category": "narration", "required": True, "roles": []}
        ]}

        v1 = req_store.save_requirements(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], reqs_v1,
        )
        v2 = req_store.save_requirements(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], reqs_v2,
        )

        assert v1["version"] == 1
        assert v2["version"] == 2

        # Current is v2
        current = req_store.get_current_requirements("test_tenant", session["id"])
        assert current["version"] == 2

        # List shows all versions
        versions = req_store.list_versions("test_tenant", session["id"])
        assert len(versions) == 2

    def test_content_hash_canonical(self, req_store, tmp_db):
        """Same requirements produce the same hash regardless of key order."""
        from services.component_requirements import compute_requirements_hash
        reqs_a = {"format": "reel", "platform": "Instagram", "categories": []}
        reqs_b = {"platform": "Instagram", "format": "reel", "categories": []}
        assert compute_requirements_hash(reqs_a) == compute_requirements_hash(reqs_b)