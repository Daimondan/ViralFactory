"""
Tests for T8.6: Production chain — Writer + Assembler stages.

AC:
- Writer chain: approved → writing → draft_ready (success)
- Writer chain: approved → writing → writer_failed (error, with retry)
- Assembler chain: shipped → assembling → asset_ready (success)
- Retry endpoint restarts the appropriate chain from writer_failed/assembly_failed
- Series parent approval spawns children in state 'new' (each child gates separately)
- No-auto-publish: chain terminates at asset review
"""
import os
import json
import pytest
import sys
import time
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    return PipelineStore(db_path=db_path)


class TestCardStateTransitions:
    """T8.6: New card states exist and transition correctly."""

    def test_writing_state_allowed(self, store):
        """Card can transition to 'writing' state."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(card_id, "writing")
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "writing"

    def test_draft_ready_state_allowed(self, store):
        """Card can transition to 'draft_ready' state."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(card_id, "draft_ready")
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "draft_ready"

    def test_assembling_state_allowed(self, store):
        """Card can transition to 'assembling' state."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(card_id, "assembling")
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "assembling"

    def test_asset_ready_state_allowed(self, store):
        """Card can transition to 'asset_ready' state."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(card_id, "asset_ready")
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "asset_ready"

    def test_writer_failed_state_with_error(self, store):
        """Card can transition to 'writer_failed' with error info."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(
            card_id,
            "writer_failed",
            production_error={"step": "draft_generation", "error": "LLM timeout"},
        )
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "writer_failed"
        error = json.loads(card["production_error"])
        assert error["step"] == "draft_generation"
        assert "LLM timeout" in error["error"]

    def test_assembly_failed_state_with_error(self, store):
        """Card can transition to 'assembly_failed' with error info."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(
            card_id,
            "assembly_failed",
            production_error={"step": "fan_out", "error": "LLM timeout"},
        )
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "assembly_failed"
        error = json.loads(card["production_error"])
        assert error["step"] == "fan_out"

    def test_legacy_production_failed_state_allowed(self, store):
        """Legacy 'production_failed' state still works (backward compat)."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(card_id, "production_failed",
            production_error={"step": "draft_generation", "error": "legacy"})
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "production_failed"


class TestProductionChainModule:
    """T8.6: produce_chain module exists and has correct interface."""

    def test_produce_chain_importable(self):
        """produce_chain module imports without error."""
        from produce_chain import ProductionChain, enqueue_writer_chain, enqueue_assembler_chain
        assert ProductionChain is not None
        assert enqueue_writer_chain is not None
        assert enqueue_assembler_chain is not None

    def test_enqueue_writer_chain_returns_thread(self, db_path):
        """enqueue_writer_chain starts a background thread and returns it."""
        from produce_chain import ProductionChain, enqueue_writer_chain

        store = PipelineStore(db_path=db_path)
        s1 = store.add_source("biz", "rss_item", "Source", content="content", content_hash="h1")
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[s1],
        )
        store.update_card_state(card_id, "approved")

        # Mock the writer chain to just set state
        with patch.object(ProductionChain, 'run_writer_chain', side_effect=lambda cid, bs: store.update_card_state(cid, 'draft_ready')):
            thread = enqueue_writer_chain(
                db_path=db_path,
                config_dir="config",
                modules_dir="modules",
                prompts_dir="prompts",
                card_id=card_id,
                business_slug="biz",
            )
            assert thread is not None
            thread.join(timeout=5)
            card = store.get_idea_card(card_id)
            assert card["card_state"] == "draft_ready"

    def test_writer_chain_failure_sets_writer_failed(self, db_path):
        """Writer chain failure sets card to writer_failed with error info."""
        from produce_chain import ProductionChain, enqueue_writer_chain

        store = PipelineStore(db_path=db_path)
        s1 = store.add_source("biz", "rss_item", "Source", content="content", content_hash="h1")
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[s1],
        )
        store.update_card_state(card_id, "approved")

        # Mock _step_draft to raise — run_writer_chain's try/except will catch it
        with patch.object(ProductionChain, '_step_draft', side_effect=RuntimeError("LLM service unavailable")):
            thread = enqueue_writer_chain(
                db_path=db_path,
                config_dir="config",
                modules_dir="modules",
                prompts_dir="prompts",
                card_id=card_id,
                business_slug="biz",
            )
            thread.join(timeout=5)
            card = store.get_idea_card(card_id)
            assert card["card_state"] == "writer_failed"
            error = json.loads(card["production_error"])
            assert "LLM service unavailable" in error["error"]

    def test_legacy_enqueue_chain_alias(self, db_path):
        """Legacy enqueue_chain alias still works (backward compat)."""
        from produce_chain import ProductionChain, enqueue_chain

        store = PipelineStore(db_path=db_path)
        s1 = store.add_source("biz", "rss_item", "Source", content="content", content_hash="h1")
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[s1],
        )
        store.update_card_state(card_id, "approved")

        with patch.object(ProductionChain, 'run_writer_chain', side_effect=lambda cid, bs: store.update_card_state(cid, 'draft_ready')):
            thread = enqueue_chain(
                db_path=db_path,
                config_dir="config",
                modules_dir="modules",
                prompts_dir="prompts",
                card_id=card_id,
                business_slug="biz",
            )
            assert thread is not None
            thread.join(timeout=5)
            card = store.get_idea_card(card_id)
            assert card["card_state"] == "draft_ready"


class TestRetryEndpoint:
    """T8.6: Retry endpoint exists and works."""

    def test_retry_only_for_failed_states(self, tmp_path):
        """Retry endpoint rejects cards not in writer_failed/assembly_failed state."""
        from app import create_app

        db_path = str(tmp_path / "test.db")
        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)

        # Write minimal config files
        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            f.write("""
business:
  name: "TestBiz"
  slug: "test-biz"
  description: "Test business"
subjects:
  - "test"
platforms:
  - name: "X"
    handle: "@test"
    priority: 1
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

        store = PipelineStore(db_path=db_path)
        s1 = store.add_source("test-biz", "rss_item", "S", content="c", content_hash="h1")
        card_id = store.create_idea_card(
            business_slug="test-biz",
            idea="Test",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[s1],
        )
        store.update_card_state(card_id, "approved")

        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        client = app.test_client()

        # Should reject — card is 'approved', not failed
        resp = client.post(f"/api/ideas/{card_id}/retry-production")
        assert resp.status_code == 400
        assert "writer_failed" in resp.json["error"] or "assembly_failed" in resp.json["error"]


class TestNoAutoPublish:
    """T8.6: No-auto-publish — chain terminates at asset review."""

    def test_chain_does_not_publish(self):
        """produce_chain module does not contain publish logic."""
        produce_chain_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(produce_chain_path) as f:
            content = f.read()
        # Must NOT contain publish API calls (the word in comments is fine)
        assert "buffer_api" not in content.lower()
        assert "postiz_api" not in content.lower()
        assert "schedule_post" not in content.lower()
        assert "publish_to" not in content.lower()
        # Must terminate at asset_ready
        assert "asset_ready" in content

    def test_writer_chain_does_not_ship(self):
        """Writer chain does NOT auto-ship the draft — it stops at draft_ready."""
        produce_chain_path = os.path.join(os.path.dirname(__file__), "..", "src", "produce_chain.py")
        with open(produce_chain_path) as f:
            content = f.read()
        # The run_writer_chain method should set draft_ready, NOT shipped
        assert "draft_ready" in content
        # The _step_draft method must NOT contain update_draft_state shipped
        assert 'update_draft_state(draft_id, "shipped")' not in content


class TestAwaitingCaptureRemoved:
    """Cards with capture tasks no longer block — they go straight to approved."""

    def test_approve_with_capture_tasks_goes_to_approved(self, tmp_path):
        """Gate 1 approval with capture tasks sets state to 'approved' (not awaiting_capture)."""
        from app import create_app

        db_path = str(tmp_path / "test.db")
        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)

        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            f.write("""
business:
  name: "TestBiz"
  slug: "test-biz"
  description: "Test business"
subjects:
  - "test"
platforms:
  - name: "X"
    handle: "@test"
    priority: 1
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

        store = PipelineStore(db_path=db_path)
        s1 = store.add_source("test-biz", "rss_item", "S", content="c", content_hash="h1")
        card_id = store.create_idea_card(
            business_slug="test-biz",
            idea="Test with capture",
            hook_options=["h"],
            treatment={
                "scope": {"type": "one_off"},
                "format": {"format_name": "test", "experimental": False},
                "capture_required": ["Real photo of vendor stall"],
                "rationale": "r"
            },
            origin="ai_originated",
            source_refs=[s1],
        )
        store.update_card_state(card_id, "new")

        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        client = app.test_client()

        resp = client.post(f"/api/ideas/{card_id}/gate",
                           json={"action": "approve"})
        assert resp.status_code == 200
        data = resp.json
        assert data["new_state"] == "approved"
        assert data["new_state"] != "awaiting_capture"