"""
Tests for M3 T3.5–T3.12: Drafter, human pass, assets, publish, origin threading.

Tests cover:
- PipelineStore: draft CRUD, asset CRUD, feedback log, state transitions
- DRAFT_SCHEMA validation
- Flask API endpoints for draft generation (mocked LLM), feedback, gate decisions
- Assets fan-out (mocked), gate 3 decisions, publish scheduling
- Origin/format/scope threading (T3.9)
- Create surface loads
"""

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    from pipeline import PipelineStore
    return PipelineStore(db_path=db_path)


@pytest.fixture
def sample_treatment():
    return {
        "scope": {"type": "one_off"},
        "format": {"format_name": "X Thread", "experimental": False},
        "capture_required": [],
        "reuse": {},
        "rationale": "Test rationale",
    }


@pytest.fixture
def app(tmp_path):
    """Flask app with temp config and DB."""
    from app import create_app

    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)

    with open(os.path.join(config_dir, "business.yaml"), "w") as f:
        f.write("""
business:
  name: "TestBiz"
  slug: "testbiz"
  description: "Test business"
subjects:
  - "test"
platforms:
  - name: "X"
    handle: "@test"
    priority: 1
  - name: "Instagram"
    handle: "@test"
    priority: 2
audience_description: "Test audience"
""")

    with open(os.path.join(config_dir, "models.yaml"), "w") as f:
        f.write("""
active:
  default: "test_backend"
  drafter: "test_backend"
test_backend:
  provider: "ollama_cloud"
  model: "test-model"
  temperature: 0
  max_tokens: 100
  base_url: "http://localhost:1"
""")

    with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
        f.write("feeds: []\nchannels: []\nqueries: []\n")

    db_path = str(tmp_path / "test.db")
    app = create_app(config_dir=config_dir, db_path=db_path)
    app.config["TESTING"] = True
    return app


class TestDraftStore:
    """Test PipelineStore draft operations (T3.5)."""

    def test_create_and_get_draft(self, store, sample_treatment):
        """Can create a draft and retrieve it."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test idea",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id,
            origin="ai_originated", format_name="X Thread", scope="one_off",
        )
        assert draft_id > 0

        draft = store.get_draft(draft_id)
        assert draft is not None
        assert draft["idea_card_id"] == card_id
        assert draft["origin"] == "ai_originated"
        assert draft["format"] == "X Thread"
        assert draft["scope"] == "one_off"
        assert draft["draft_state"] == "drafting"
        assert draft["draft_version"] == 1

    def test_save_draft_content(self, store, sample_treatment):
        """Saving draft content transitions to draft_ready."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id,
            origin="ai_originated", format_name="X Thread", scope="one_off",
        )
        store.save_draft_content(
            draft_id,
            draft_text="This is the full draft text.",
            visual_direction={"image_prompts": ["prompt 1"], "reference_notes": ["ref"], "shot_format_choices": ["shot"]},
            self_audit_flags=[{"line": "line 1", "rule": "too generic", "suggestion": "make specific"}],
        )
        draft = store.get_draft(draft_id)
        assert draft["draft_state"] == "draft_ready"
        assert draft["draft_text"] == "This is the full draft text."
        flags = json.loads(draft["self_audit_flags"])
        assert len(flags) == 1
        assert flags[0]["rule"] == "too generic"

    def test_draft_state_transitions(self, store, sample_treatment):
        """Draft goes through the right state transitions."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id,
            origin="ai_originated",
        )
        assert store.get_draft(draft_id)["draft_state"] == "drafting"

        store.update_draft_state(draft_id, "shipped")
        assert store.get_draft(draft_id)["draft_state"] == "shipped"

        store.update_draft_state(draft_id, "killed")
        assert store.get_draft(draft_id)["draft_state"] == "killed"

    def test_draft_version_increment(self, store, sample_treatment):
        """Revision increments the draft version."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id,
            origin="ai_originated",
        )
        assert store.get_draft(draft_id)["draft_version"] == 1

        v2 = store.increment_draft_version(draft_id)
        assert v2 == 2
        assert store.get_draft(draft_id)["draft_state"] == "revised"

    def test_human_edits_saved(self, store, sample_treatment):
        """Direct edits are saved to the draft."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id,
            origin="ai_originated",
        )
        store.save_human_edits(draft_id, {"opening": "Rewritten opening line"})
        draft = store.get_draft(draft_id)
        edits = json.loads(draft["human_edits"])
        assert edits["opening"] == "Rewritten opening line"


class TestAssetStore:
    """Test PipelineStore asset operations (T3.7/T3.8)."""

    def test_create_and_get_asset(self, store, sample_treatment):
        """Can create an asset and retrieve it."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id, origin="ai_originated",
        )
        asset_id = store.create_asset(
            business_slug="testbiz", draft_id=draft_id,
            platform="X", variant_type="thread",
            content="Thread content here",
            image_prompts=["prompt 1"],
        )
        assert asset_id > 0

        asset = store.get_asset(asset_id)
        assert asset["platform"] == "X"
        assert asset["variant_type"] == "thread"
        assert asset["asset_state"] == "pending"

    def test_list_assets_by_draft(self, store, sample_treatment):
        """Can list all assets for a draft."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id, origin="ai_originated",
        )
        store.create_asset("testbiz", draft_id, "X", "thread", "content 1")
        store.create_asset("testbiz", draft_id, "Instagram", "carousel", "content 2")

        assets = store.list_assets(draft_id)
        assert len(assets) == 2

    def test_asset_state_transitions(self, store, sample_treatment):
        """Assets transition through approve/fix/kill/publish."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id, origin="ai_originated",
        )
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")

        store.update_asset_state(asset_id, "approved")
        assert store.get_asset(asset_id)["asset_state"] == "approved"

        store.update_asset_state(asset_id, "published")
        assert store.get_asset(asset_id)["asset_state"] == "published"

    def test_asset_schedule(self, store, sample_treatment):
        """Can set a publish schedule on an asset."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id, origin="ai_originated",
        )
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")
        store.set_asset_schedule(asset_id, "2026-07-05T10:00:00Z")
        asset = store.get_asset(asset_id)
        assert asset["publish_scheduled_at"] == "2026-07-05T10:00:00Z"


class TestOriginThreading:
    """Test T3.9: origin + format + scope threaded through pipeline."""

    def test_origin_carried_to_draft(self, store, sample_treatment):
        """Origin from idea card is carried to draft."""
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment,
            origin="human_seeded_ai_developed",
        )
        draft_id = store.create_draft(
            business_slug="testbiz", idea_card_id=card_id,
            origin="human_seeded_ai_developed",
            format_name="X Thread", scope="one_off",
        )
        draft = store.get_draft(draft_id)
        assert draft["origin"] == "human_seeded_ai_developed"
        assert draft["format"] == "X Thread"
        assert draft["scope"] == "one_off"

    def test_stats_breakdown_by_origin_format_scope(self, store, sample_treatment):
        """Nightly stats include origin/format/scope breakdown."""
        # Create cards + drafts with different origins
        for origin in ["ai_originated", "human_seeded", "human_seeded_ai_developed"]:
            card_id = store.create_idea_card(
                business_slug="testbiz", idea=f"Test {origin}",
                hook_options=["h"], treatment=sample_treatment, origin=origin,
            )
            draft_id = store.create_draft(
                business_slug="testbiz", idea_card_id=card_id,
                origin=origin, format_name="X Thread", scope="one_off",
            )
            store.update_draft_state(draft_id, "shipped")

        stats = store.get_pipeline_stats("testbiz")
        assert stats["shipped_drafts"] == 3
        assert stats["origin_breakdown"]["ai_originated"] == 1
        assert stats["origin_breakdown"]["human_seeded"] == 1
        assert stats["origin_breakdown"]["human_seeded_ai_developed"] == 1
        assert stats["format_breakdown"]["X Thread"] == 3
        assert stats["scope_breakdown"]["one_off"] == 3


class TestDraftSchema:
    """Test DRAFT_SCHEMA validation."""

    def test_valid_draft_passes(self):
        from pipeline import DRAFT_SCHEMA
        from validator import validate_llm_output

        raw = json.dumps({
            "draft_text": "This is the full draft.",
            "visual_direction": {
                "image_prompts": ["prompt"],
                "reference_notes": ["ref"],
                "shot_format_choices": ["shot"],
            },
            "self_audit_flags": [],
        })
        result = validate_llm_output(raw, DRAFT_SCHEMA)
        assert result["draft_text"] == "This is the full draft."

    def test_missing_visual_direction_fails(self):
        from pipeline import DRAFT_SCHEMA
        from validator import validate_llm_output, ValidationError

        raw = json.dumps({
            "draft_text": "Draft text",
            "self_audit_flags": [],
        })
        with pytest.raises(ValidationError):
            validate_llm_output(raw, DRAFT_SCHEMA)


class TestFlaskDraftEndpoints:
    """Test Flask draft/feedback/assets/publish endpoints."""

    def test_draft_page_loads_no_draft(self, app, sample_treatment):
        """Draft page loads for an approved card with no draft yet."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test idea",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        store.update_card_state(card_id, "approved")

        client = app.test_client()
        resp = client.get(f"/create/draft/{card_id}")
        assert resp.status_code == 200
        assert b"Generate draft" in resp.data

    def test_draft_page_loads_with_draft(self, app, sample_treatment):
        """Draft page loads when a draft exists."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test idea",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated", "X Thread", "one_off")
        store.save_draft_content(draft_id, "Draft text", {
            "image_prompts": [], "reference_notes": [], "shot_format_choices": []
        }, [])

        client = app.test_client()
        resp = client.get(f"/create/draft/{card_id}")
        assert resp.status_code == 200
        assert b"Draft text" in resp.data

    def test_feedback_chip(self, app, sample_treatment):
        """Chip feedback is logged."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")

        client = app.test_client()
        resp = client.post(f"/api/draft/{draft_id}/feedback",
                           json={"feedback_type": "chip", "feedback_text": "too long"})
        assert resp.status_code == 200

        entries = store.list_feedback("testbiz")
        assert len(entries) == 1
        assert entries[0]["feedback_type"] == "chip"
        assert entries[0]["weight"] == 1

    def test_feedback_direct_edit(self, app, sample_treatment):
        """Direct edit feedback is saved with highest weight."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")

        client = app.test_client()
        resp = client.post(f"/api/draft/{draft_id}/feedback",
                           json={"feedback_type": "direct_edit", "feedback_text": "Rewritten line", "line_reference": "line_5"})
        assert resp.status_code == 200

        entries = store.list_feedback("testbiz")
        assert entries[0]["weight"] == 3

        # Check edits were saved
        draft = store.get_draft(draft_id)
        edits = json.loads(draft["human_edits"])
        assert "line_5" in edits
        assert edits["line_5"] == "Rewritten line"

    def test_draft_gate_ship(self, app, sample_treatment):
        """Shipping a draft works."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        store.save_draft_content(draft_id, "text", {
            "image_prompts": [], "reference_notes": [], "shot_format_choices": []
        }, [])

        client = app.test_client()
        resp = client.post(f"/api/draft/{draft_id}/gate", json={"action": "ship"})
        assert resp.status_code == 200
        assert resp.get_json()["new_state"] == "shipped"

    def test_draft_gate_kill_with_reason(self, app, sample_treatment):
        """Killing a draft logs reason to feedback."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")

        client = app.test_client()
        resp = client.post(f"/api/draft/{draft_id}/gate",
                           json={"action": "kill", "kill_reason": "voice is off"})
        assert resp.status_code == 200

        entries = store.list_feedback("testbiz")
        kill_entries = [e for e in entries if e["feedback_type"] == "kill_reason"]
        assert len(kill_entries) == 1
        assert kill_entries[0]["feedback_text"] == "voice is off"

    def test_draft_gate_revise(self, app, sample_treatment):
        """Revising increments version."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")

        client = app.test_client()
        resp = client.post(f"/api/draft/{draft_id}/gate", json={"action": "revise"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["new_state"] == "revised"
        assert data["new_version"] == 2

    def test_assets_page_loads(self, app, sample_treatment):
        """Assets page loads for a shipped draft."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        store.update_draft_state(draft_id, "shipped")

        client = app.test_client()
        resp = client.get(f"/create/assets/{draft_id}")
        assert resp.status_code == 200
        assert b"Generate per-platform" in resp.data

    def test_asset_gate_approve(self, app, sample_treatment):
        """Approving an asset works."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")

        client = app.test_client()
        resp = client.post(f"/api/assets/{asset_id}/gate", json={"action": "approve"})
        assert resp.status_code == 200
        assert resp.get_json()["new_state"] == "approved"

    def test_asset_gate_fix(self, app, sample_treatment):
        """Fixing an asset works."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")

        client = app.test_client()
        resp = client.post(f"/api/assets/{asset_id}/gate", json={"action": "fix"})
        assert resp.status_code == 200
        assert resp.get_json()["new_state"] == "fix"

    def test_publish_page_loads(self, app, sample_treatment):
        """Publish page loads with approved assets."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")
        store.update_asset_state(asset_id, "approved")

        client = app.test_client()
        resp = client.get(f"/create/publish/{draft_id}")
        assert resp.status_code == 200
        assert b"Publish" in resp.data

    def test_schedule_publish(self, app, sample_treatment):
        """Scheduling an approved asset for publish works."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")
        store.update_asset_state(asset_id, "approved")

        client = app.test_client()
        resp = client.post(f"/api/assets/{asset_id}/schedule",
                           json={"scheduled_at": "2026-07-05T10:00:00Z"})
        assert resp.status_code == 200
        assert store.get_asset(asset_id)["asset_state"] == "published"
        assert store.get_asset(asset_id)["publish_scheduled_at"] == "2026-07-05T10:00:00Z"

    def test_schedule_not_approved_fails(self, app, sample_treatment):
        """Can't schedule a non-approved asset."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")
        asset_id = store.create_asset("testbiz", draft_id, "X", "thread", "content")

        client = app.test_client()
        resp = client.post(f"/api/assets/{asset_id}/schedule",
                           json={"scheduled_at": "2026-07-05T10:00:00Z"})
        assert resp.status_code == 400

    def test_create_surface_loads(self, app):
        """Create surface dashboard loads."""
        client = app.test_client()
        resp = client.get("/create")
        assert resp.status_code == 200
        assert b"Create" in resp.data

    def test_fan_out_requires_shipped(self, app, sample_treatment):
        """Fan-out only works on shipped drafts."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Test",
            hook_options=["h"], treatment=sample_treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated")

        client = app.test_client()
        resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})
        assert resp.status_code == 400