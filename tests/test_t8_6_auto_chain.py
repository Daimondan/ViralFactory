"""
Tests for T8.6: Auto-production chain.

AC:
- Card state transitions: approved → producing → asset_ready (success)
- Card state transitions: approved → producing → production_failed (error, with retry)
- Retry endpoint restarts the chain from production_failed
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

    def test_producing_state_allowed(self, store):
        """Card can transition to 'producing' state."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["h"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "r"},
            origin="ai_originated",
            source_refs=[1],
        )
        store.update_card_state(card_id, "producing")
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "producing"

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

    def test_production_failed_state_with_error(self, store):
        """Card can transition to 'production_failed' with error info."""
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
            "production_failed",
            production_error={"step": "draft_generation", "error": "LLM timeout"},
        )
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "production_failed"
        error = json.loads(card["production_error"])
        assert error["step"] == "draft_generation"
        assert "LLM timeout" in error["error"]


class TestProductionChainModule:
    """T8.6: produce_chain module exists and has correct interface."""

    def test_produce_chain_importable(self):
        """produce_chain module imports without error."""
        from produce_chain import ProductionChain, enqueue_chain
        assert ProductionChain is not None
        assert enqueue_chain is not None

    def test_enqueue_chain_returns_thread(self, db_path):
        """enqueue_chain starts a background thread and returns it."""
        from produce_chain import ProductionChain, enqueue_chain

        # Create a card to work with
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

        # Mock the chain to just set state without LLM calls
        with patch.object(ProductionChain, 'run_chain', side_effect=lambda cid, bs: store.update_card_state(cid, 'asset_ready')):
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
            assert card["card_state"] == "asset_ready"

    def test_chain_failure_sets_production_failed(self, db_path):
        """Chain failure sets card to production_failed with error info."""
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

        # Mock _step_draft to raise — run_chain's try/except will catch it
        with patch.object(ProductionChain, '_step_draft', side_effect=RuntimeError("LLM service unavailable")):
            thread = enqueue_chain(
                db_path=db_path,
                config_dir="config",
                modules_dir="modules",
                prompts_dir="prompts",
                card_id=card_id,
                business_slug="biz",
            )
            thread.join(timeout=5)
            card = store.get_idea_card(card_id)
            assert card["card_state"] == "production_failed"
            error = json.loads(card["production_error"])
            assert "LLM service unavailable" in error["error"]


class TestRetryEndpoint:
    """T8.6: Retry endpoint exists and works."""

    def test_retry_only_for_production_failed(self, tmp_path):
        """Retry endpoint rejects cards not in production_failed state."""
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

        # Should reject — card is 'approved', not 'production_failed'
        resp = client.post(f"/api/ideas/{card_id}/retry-production")
        assert resp.status_code == 400
        assert "production_failed" in resp.json["error"]


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