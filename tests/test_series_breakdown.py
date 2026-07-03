"""
Tests for F3 (CORRECTION-feedback-plumbing): Series breakdown.
- Approving a series parent yields children in state 'new' with distinct ideas
- Breakdown failure still yields children (clones, state 'new') and a warning
- Bulk approve transitions all 'new' children of a parent
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    from pipeline import PipelineStore
    return PipelineStore(db_path=db_path)


@pytest.fixture
def series_treatment():
    return {
        "scope": {"type": "series_of_n", "n": 3, "cadence": "weekly"},
        "format": {"format_name": "X Thread", "experimental": False},
        "capture_required": [],
        "reuse": {},
        "rationale": "Test series",
    }


@pytest.fixture
def app(tmp_path):
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


class TestF3SeriesBreakdown:
    """F3: Series children spawn via LLM breakdown, enter state 'new'."""

    def test_series_children_spawn_in_state_new(self, app, store, series_treatment):
        """Approving a series_of_3 parent yields 2 children in state 'new' with distinct ideas."""
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Parent idea about wealth building",
            hook_options=["Hook 1", "Hook 2"],
            treatment=series_treatment, origin="ai_originated",
        )

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            if "series_breakdown" in prompt_file:
                return {
                    "parts": [
                        {"part_number": 2, "idea": "PART2_SENTINEL about investing", "hook_options": ["h2a", "h2b"], "capture_required": []},
                        {"part_number": 3, "idea": "PART3_SENTINEL about compound growth", "hook_options": ["h3a", "h3b"], "capture_required": []},
                    ]
                }
            return {"cards": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app.test_client()
            resp = client.post(f"/api/ideas/{card_id}/gate",
                               json={"action": "approve"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["new_state"] == "approved"

        # Find children
        all_cards = [c for c in store.list_idea_cards("testbiz") if c.get("parent_id") == card_id]
        assert len(all_cards) == 2
        for child in all_cards:
            assert child["card_state"] == "new"
            assert child["idea"] != "Parent idea about wealth building"
            assert "SENTINEL" in child["idea"]

    def test_series_children_distinct_from_each_other(self, app, store, series_treatment):
        """Children ideas differ from the parent and from each other."""
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Parent idea",
            hook_options=["Hook 1"],
            treatment=series_treatment, origin="ai_originated",
        )

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            if "series_breakdown" in prompt_file:
                return {
                    "parts": [
                        {"part_number": 2, "idea": "Unique idea A", "hook_options": ["a"], "capture_required": []},
                        {"part_number": 3, "idea": "Unique idea B", "hook_options": ["b"], "capture_required": []},
                    ]
                }
            return {"cards": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app.test_client()
            client.post(f"/api/ideas/{card_id}/gate", json={"action": "approve"})

        children = [c for c in store.list_idea_cards("testbiz") if c.get("parent_id") == card_id]
        ideas = [c["idea"] for c in children]
        assert "Unique idea A" in ideas
        assert "Unique idea B" in ideas
        assert "Parent idea" not in ideas

    def test_breakdown_failure_falls_back_to_clones_in_new(self, app, store, series_treatment):
        """Breakdown failure still yields children (clones, state 'new') and a warning."""
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Parent idea",
            hook_options=["Hook 1"],
            treatment=series_treatment, origin="ai_originated",
        )

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            raise Exception("LLM failed")

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app.test_client()
            resp = client.post(f"/api/ideas/{card_id}/gate", json={"action": "approve"})

        assert resp.status_code == 200
        data = resp.get_json()
        assert "warning" in data

        children = [c for c in store.list_idea_cards("testbiz") if c.get("parent_id") == card_id]
        assert len(children) == 2  # n-1 = 2 clones
        for child in children:
            assert child["card_state"] == "new"

    def test_bulk_approve_children(self, app, store, series_treatment):
        """Bulk approve transitions all 'new' children of a parent."""
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Parent idea",
            hook_options=["Hook 1"],
            treatment=series_treatment, origin="ai_originated",
        )

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            if "series_breakdown" in prompt_file:
                return {
                    "parts": [
                        {"part_number": 2, "idea": "Part 2 idea", "hook_options": ["h2"], "capture_required": []},
                        {"part_number": 3, "idea": "Part 3 idea", "hook_options": ["h3"], "capture_required": []},
                    ]
                }
            return {"cards": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app.test_client()
            client.post(f"/api/ideas/{card_id}/gate", json={"action": "approve"})

        children = [c for c in store.list_idea_cards("testbiz") if c.get("parent_id") == card_id]
        assert len(children) == 2
        assert all(c["card_state"] == "new" for c in children)

        # Bulk approve via the new endpoint
        resp = client.post(f"/api/ideas/{card_id}/bulk-approve-children")
        assert resp.status_code == 200

        children_after = [c for c in store.list_idea_cards("testbiz") if c.get("parent_id") == card_id]
        assert all(c["card_state"] == "approved" for c in children_after)