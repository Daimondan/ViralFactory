"""
Tests for M3 T3.1–T3.3: Idea card generation, Ideas gate, awaiting-capture state.

Tests cover:
- PipelineStore: create/get/list idea cards, state transitions, capture uploads
- IDEA_CARD_SCHEMA validation
- Series spawning (T3.10)
- Awaiting-capture state + fulfillment check
- Feedback log for kill reasons
- Flask API endpoints (mocked LLM)
"""

import os
import json
import tempfile
import pytest
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def db_path(tmp_path):
    """Temporary DB path for each test."""
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    """PipelineStore with a temp DB."""
    from pipeline import PipelineStore
    return PipelineStore(db_path=db_path)


@pytest.fixture
def sample_treatment():
    """A valid treatment block for testing."""
    return {
        "scope": {"type": "one_off"},
        "format": {"format_name": "X Thread", "experimental": False},
        "capture_required": [],
        "reuse": {},
        "rationale": "A single X thread fits this timely take.",
    }


@pytest.fixture
def sample_treatment_with_capture():
    """Treatment that requires human capture."""
    return {
        "scope": {"type": "one_off"},
        "format": {"format_name": "IG Reel", "experimental": False},
        "capture_required": [
            "Record 15s of street footage in Bridgetown",
            "Photograph a receipt close-up",
        ],
        "reuse": {},
        "rationale": "Reel format needs real footage per the Visual Style Guide.",
    }


@pytest.fixture
def sample_treatment_series():
    """Treatment for a series_of_n."""
    return {
        "scope": {"type": "series_of_n", "n": 3, "cadence": "weekly"},
        "format": {"format_name": "X Thread", "experimental": False},
        "capture_required": [],
        "reuse": {},
        "rationale": "A 3-part weekly series to build anticipation.",
    }


@pytest.fixture
def sample_treatment_experimental():
    """Treatment with an experimental format debut."""
    return {
        "scope": {"type": "one_off"},
        "format": {
            "format_name": "Split-screen POV",
            "experimental": True,
            "format_spec": "Two vertical halves showing two perspectives simultaneously",
        },
        "capture_required": [],
        "reuse": {},
        "rationale": "Testing a new format for engagement.",
    }


class TestPipelineStoreIdeaCards:
    """Test the PipelineStore idea card operations."""

    def test_create_and_get_idea_card(self, store, sample_treatment):
        """Can create an idea card and retrieve it."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="BiMPay is changing the game for small vendors",
            hook_options=["Why BiMPay is a game changer", "Small vendors, big rails"],
            treatment=sample_treatment,
            origin="ai_originated",
            evidence_links=[{"url": "https://example.com", "note": "Source"}],
        )
        assert card_id > 0

        card = store.get_idea_card(card_id)
        assert card is not None
        assert card["business_slug"] == "testbiz"
        assert card["idea"] == "BiMPay is changing the game for small vendors"
        assert card["origin"] == "ai_originated"
        assert card["card_state"] == "new"
        assert json.loads(card["hook_options"]) == ["Why BiMPay is a game changer", "Small vendors, big rails"]
        assert json.loads(card["treatment"])["scope"]["type"] == "one_off"

    def test_list_idea_cards_by_state(self, store, sample_treatment):
        """Can list cards filtered by state."""
        # Create 3 cards
        for i in range(3):
            store.create_idea_card(
                business_slug="testbiz",
                idea=f"Idea {i}",
                hook_options=["hook"],
                treatment=sample_treatment,
                origin="ai_originated",
            )

        # All should be 'new'
        new_cards = store.list_idea_cards_by_states("testbiz", ["new"])
        assert len(new_cards) == 3

        # Kill one
        store.update_card_state(new_cards[0]["id"], "killed", kill_reason="weak")
        new_cards = store.list_idea_cards_by_states("testbiz", ["new"])
        assert len(new_cards) == 2
        killed = store.list_idea_cards_by_states("testbiz", ["killed"])
        assert len(killed) == 1

    def test_list_idea_cards_wrong_business(self, store, sample_treatment):
        """Cards from other businesses don't leak."""
        store.create_idea_card(
            business_slug="biz_a",
            idea="Idea A",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        store.create_idea_card(
            business_slug="biz_b",
            idea="Idea B",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )

        a_cards = store.list_idea_cards("biz_a")
        b_cards = store.list_idea_cards("biz_b")
        assert len(a_cards) == 1
        assert len(b_cards) == 1
        assert a_cards[0]["idea"] == "Idea A"
        assert b_cards[0]["idea"] == "Idea B"

    def test_update_card_state_kill_with_reason(self, store, sample_treatment):
        """Killing a card stores the kill reason."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Weak idea",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        store.update_card_state(card_id, "killed", kill_reason="too generic")
        card = store.get_idea_card(card_id)
        assert card["card_state"] == "killed"
        assert card["kill_reason"] == "too generic"

    def test_park_and_reactivate(self, store, sample_treatment):
        """Can park a card and later reactivate (approve) it."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Maybe later",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        store.update_card_state(card_id, "parked")
        assert store.get_idea_card(card_id)["card_state"] == "parked"

        # Reactivate
        store.update_card_state(card_id, "approved")
        assert store.get_idea_card(card_id)["card_state"] == "approved"

    def test_update_card_treatment(self, store, sample_treatment):
        """Can update treatment (direct-edit at Gate 1)."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Idea",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        new_treatment = dict(sample_treatment)
        new_treatment["scope"] = {"type": "series_of_n", "n": 5, "cadence": "daily"}
        store.update_card_treatment(card_id, new_treatment)

        card = store.get_idea_card(card_id)
        treatment = json.loads(card["treatment"])
        assert treatment["scope"]["type"] == "series_of_n"
        assert treatment["scope"]["n"] == 5


class TestAwaitingCapture:
    """Test the awaiting-capture state (T3.3)."""

    def test_capture_fulfilled_empty(self, store, sample_treatment):
        """Card with no capture_required is automatically fulfilled."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="No capture needed",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        assert store.check_capture_fulfilled(card_id) is True

    def test_capture_not_fulfilled(self, store, sample_treatment_with_capture):
        """Card with capture_required and no uploads is not fulfilled."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Needs footage",
            hook_options=["h"],
            treatment=sample_treatment_with_capture,
            origin="ai_originated",
        )
        assert store.check_capture_fulfilled(card_id) is False

    def test_capture_fulfilled_after_uploads(self, store, sample_treatment_with_capture):
        """Card with enough uploads is fulfilled."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Needs footage",
            hook_options=["h"],
            treatment=sample_treatment_with_capture,
            origin="ai_originated",
        )
        # Upload 2 materials (2 capture tasks)
        store.add_capture_upload(card_id, material_id=101)
        assert store.check_capture_fulfilled(card_id) is False  # only 1 of 2

        store.add_capture_upload(card_id, material_id=102)
        assert store.check_capture_fulfilled(card_id) is True  # 2 of 2

    def test_capture_uploads_stored(self, store, sample_treatment_with_capture):
        """Capture uploads are stored in the card record."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Needs footage",
            hook_options=["h"],
            treatment=sample_treatment_with_capture,
            origin="ai_originated",
        )
        store.add_capture_upload(card_id, material_id=201)
        store.add_capture_upload(card_id, material_id=202)

        card = store.get_idea_card(card_id)
        uploads = json.loads(card["capture_uploads"])
        assert uploads == [201, 202]


class TestSeriesSpawning:
    """Test T3.10: series spawning creates child cards."""

    def test_list_series_children(self, store, sample_treatment_series):
        """Can list child cards spawned from a parent."""
        parent_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Series parent",
            hook_options=["h"],
            treatment=sample_treatment_series,
            origin="ai_originated",
        )
        # Spawn children
        for i in range(2):  # 2 children (parent is part 1)
            store.create_idea_card(
                business_slug="testbiz",
                idea=f"Series parent (Part {i+2}/3)",
                hook_options=["h"],
                treatment=sample_treatment_series,
                origin="ai_originated",
                parent_id=parent_id,
            )

        children = store.list_series_children(parent_id)
        assert len(children) == 2
        assert all(c["parent_id"] == parent_id for c in children)


class TestFeedbackLog:
    """Test the feedback log."""

    def test_add_kill_reason_feedback(self, store, sample_treatment):
        """Kill reason is logged to feedback log."""
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Bad idea",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        store.add_feedback(
            business_slug="testbiz",
            feedback_type="kill_reason",
            feedback_text="Too generic, no lived detail",
            idea_card_id=card_id,
        )
        entries = store.list_feedback("testbiz")
        assert len(entries) == 1
        assert entries[0]["feedback_type"] == "kill_reason"
        assert entries[0]["weight"] == 1

    def test_direct_edit_high_weight(self, store, sample_treatment):
        """Direct edit feedback has weight 3 (highest)."""
        store.add_feedback(
            business_slug="testbiz",
            feedback_type="direct_edit",
            feedback_text="Rewrote the opening line",
        )
        entries = store.list_feedback("testbiz")
        assert entries[0]["weight"] == 3

    def test_chip_text_weights(self, store):
        """Chip=1, text=2, direct_edit=3."""
        store.add_feedback("testbiz", "chip", "too long")
        store.add_feedback("testbiz", "text", "the ending is weak, needs more punch")
        store.add_feedback("testbiz", "direct_edit", "rewrote paragraph 2")

        entries = store.list_feedback("testbiz")
        weights = {e["feedback_type"]: e["weight"] for e in entries}
        assert weights["chip"] == 1
        assert weights["text"] == 2
        assert weights["direct_edit"] == 3


class TestPipelineStats:
    """Test the nightly performance note stats (T3.9)."""

    def test_stats_empty(self, store):
        """Stats on empty pipeline return zeros."""
        stats = store.get_pipeline_stats("testbiz")
        assert stats["shipped_drafts"] == 0
        assert stats["published_assets"] == 0
        assert stats["origin_breakdown"] == {}

    def test_stats_with_data(self, store, sample_treatment):
        """Stats count shipped drafts by origin/format/scope."""
        # Create card + draft
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Test",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )
        draft_id = store.create_draft(
            business_slug="testbiz",
            idea_card_id=card_id,
            origin="ai_originated",
            format_name="X Thread",
            scope="one_off",
        )
        store.update_draft_state(draft_id, "shipped")

        stats = store.get_pipeline_stats("testbiz")
        assert stats["shipped_drafts"] == 1
        assert stats["origin_breakdown"]["ai_originated"] == 1
        assert stats["format_breakdown"]["X Thread"] == 1
        assert stats["scope_breakdown"]["one_off"] == 1


class TestIdeaCardSchema:
    """Test the IDEA_CARD_SCHEMA validation."""

    def test_valid_card_passes(self):
        """A valid idea card passes validation."""
        from pipeline import IDEA_CARD_SCHEMA
        from validator import validate_llm_output

        raw = json.dumps({
            "cards": [{
                "idea": "Test idea",
                "hook_options": ["Hook 1", "Hook 2"],
                "treatment": {
                    "scope": {"type": "one_off"},
                    "format": {"format_name": "X Thread", "experimental": False},
                    "capture_required": [],
                    "rationale": "Fits the timely take.",
                },
                "origin": "ai_originated",
                "evidence_links": [{"url": "https://example.com", "note": "test"}],
            }]
        })
        result = validate_llm_output(raw, IDEA_CARD_SCHEMA)
        assert "cards" in result
        assert len(result["cards"]) == 1

    def test_missing_treatment_fails(self):
        """Missing treatment field fails validation."""
        from pipeline import IDEA_CARD_SCHEMA
        from validator import validate_llm_output, ValidationError

        raw = json.dumps({
            "cards": [{
                "idea": "Test",
                "hook_options": ["h"],
                "origin": "ai_originated",
                "evidence_links": [],
            }]
        })
        with pytest.raises(ValidationError):
            validate_llm_output(raw, IDEA_CARD_SCHEMA)

    def test_missing_cards_array_fails(self):
        """Missing cards array fails validation."""
        from pipeline import IDEA_CARD_SCHEMA
        from validator import validate_llm_output, ValidationError

        raw = json.dumps({"ideas": []})
        with pytest.raises(ValidationError):
            validate_llm_output(raw, IDEA_CARD_SCHEMA)


class TestFlaskIdeaEndpoints:
    """Test the Flask API endpoints for idea cards (mocked LLM)."""

    @pytest.fixture
    def app(self, tmp_path):
        """Flask app with temp config and DB."""
        from app import create_app

        # Create temp config
        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)

        business_yaml = """
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
"""
        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            f.write(business_yaml)

        models_yaml = """
active:
  default: "test_backend"
  drafter: "test_backend"
test_backend:
  provider: "ollama_cloud"
  model: "test-model"
  temperature: 0
  max_tokens: 100
  base_url: "http://localhost:1"
"""
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            f.write(models_yaml)

        sources_yaml = """
feeds: []
channels: []
queries: []
"""
        with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
            f.write(sources_yaml)

        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def app_with_ideator(self, tmp_path):
        """Flask app with ideator backend configured (S1a)."""
        from app import create_app

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)

        business_yaml = """
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
"""
        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            f.write(business_yaml)

        models_yaml = """
active:
  default: "test_processing"
  drafter: "test_creative"
  ideator: "test_creative"
test_processing:
  provider: "ollama_cloud"
  model: "test-model"
  temperature: 0
  max_tokens: 100
  base_url: "http://localhost:1"
test_creative:
  provider: "ollama_cloud"
  model: "test-model"
  temperature: 0.9
  max_tokens: 100
  base_url: "http://localhost:1"
"""
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            f.write(models_yaml)

        sources_yaml = """
feeds: []
channels: []
queries: []
"""
        with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
            f.write(sources_yaml)

        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        return app

    def test_ideas_generate_uses_ideator_backend(self, app_with_ideator):
        """S1a: ideas_generate route calls the LLM with backend='ideator'."""
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        captured_backend = []

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            captured_backend.append(kwargs.get("backend"))
            return {"cards": [
                {"idea": "Test idea", "hook_options": ["h"], "treatment": {"scope": "one_off", "format": "X Thread", "capture_required": [], "rationale": "r"}, "origin": "ai_originated", "evidence_links": []}
            ]}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_ideator.test_client()
            resp = client.post("/api/ideas/generate", json={"count": 1})

        assert resp.status_code == 200
        assert captured_backend == ["ideator"]

    def test_seed_uses_ideator_backend(self, app_with_ideator):
        """S1a: seed-based card generation uses backend='ideator'."""
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        captured_backend = []

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            captured_backend.append(kwargs.get("backend"))
            return {"cards": [
                {"idea": "Seed idea", "hook_options": ["h"], "treatment": {"scope": "one_off", "format": "X Thread", "capture_required": [], "rationale": "r"}, "origin": "human_seeded", "evidence_links": []}
            ]}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_ideator.test_client()
            resp = client.post("/api/ideas/seed", json={"seed": "My seed idea"})

        assert resp.status_code == 200
        assert captured_backend == ["ideator"]

    def test_ideator_resolves_to_nonzero_temperature(self, tmp_path):
        """S1a: ideator active role resolves to a backend with temperature > 0."""
        from config_loader import load_models

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)
        models_yaml = """
active:
  default: "proc"
  drafter: "creative"
  ideator: "creative"
proc:
  provider: "ollama_cloud"
  model: "m"
  temperature: 0
  max_tokens: 100
  base_url: ""
creative:
  provider: "ollama_cloud"
  model: "m"
  temperature: 0.9
  max_tokens: 100
  base_url: ""
"""
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            f.write(models_yaml)

        models = load_models(config_dir)
        ideator_name = models["active"]["ideator"]
        assert ideator_name == "creative"
        assert models[ideator_name]["temperature"] > 0

    def test_config_loader_accepts_ideator_in_active(self, tmp_path):
        """S1a: config_loader validates ideator in active block."""
        from config_loader import load_models

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)
        models_yaml = """
active:
  default: "proc"
  drafter: "creative"
  ideator: "creative"
proc:
  provider: "ollama_cloud"
  model: "m"
  temperature: 0
  max_tokens: 100
  base_url: ""
creative:
  provider: "ollama_cloud"
  model: "m"
  temperature: 0.9
  max_tokens: 100
  base_url: ""
"""
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            f.write(models_yaml)

        # Should not raise
        models = load_models(config_dir)
        assert "ideator" in models["active"]

    def test_ideas_page_loads(self, app):
        """The ideas queue page loads."""
        client = app.test_client()
        resp = client.get("/ideas")
        assert resp.status_code == 200
        assert b"Ideas" in resp.data

    def test_gate_approve_no_capture(self, app, sample_treatment):
        """Approving a card with no capture_required → 'approved'."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Test idea",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )

        client = app.test_client()
        resp = client.post(f"/api/ideas/{card_id}/gate",
                           json={"action": "approve"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["new_state"] == "approved"

    def test_gate_approve_with_capture(self, app, sample_treatment_with_capture):
        """Approving a card with capture_required → 'awaiting_capture'."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Needs footage",
            hook_options=["h"],
            treatment=sample_treatment_with_capture,
            origin="ai_originated",
        )

        client = app.test_client()
        resp = client.post(f"/api/ideas/{card_id}/gate",
                           json={"action": "approve"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["new_state"] == "awaiting_capture"

    def test_gate_kill_logs_reason(self, app, sample_treatment):
        """Killing a card logs the reason to feedback log."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Bad idea",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )

        client = app.test_client()
        resp = client.post(f"/api/ideas/{card_id}/gate",
                           json={"action": "kill", "kill_reason": "too generic"})
        assert resp.status_code == 200

        # Check feedback log
        entries = store.list_feedback("testbiz")
        assert len(entries) == 1
        assert entries[0]["feedback_type"] == "kill_reason"
        assert entries[0]["feedback_text"] == "too generic"

    def test_gate_park(self, app, sample_treatment):
        """Parking a card works."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Maybe later",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )

        client = app.test_client()
        resp = client.post(f"/api/ideas/{card_id}/gate",
                           json={"action": "park"})
        assert resp.status_code == 200
        assert resp.get_json()["new_state"] == "parked"

    def test_gate_invalid_action(self, app, sample_treatment):
        """Invalid action returns 400."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Test",
            hook_options=["h"],
            treatment=sample_treatment,
            origin="ai_originated",
        )

        client = app.test_client()
        resp = client.post(f"/api/ideas/{card_id}/gate",
                           json={"action": "frobnicate"})
        assert resp.status_code == 400

    def test_series_spawning_on_approve(self, app, sample_treatment_series):
        """F3: Approving a series_of_n card spawns child cards via LLM breakdown.

        Children enter state 'new' — operator must gate each part.
        """
        from pipeline import PipelineStore
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Series idea",
            hook_options=["h"],
            treatment=sample_treatment_series,
            origin="ai_originated",
        )

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            if "series_breakdown" in prompt_file:
                return {
                    "parts": [
                        {"part_number": 2, "idea": "Part 2", "hook_options": ["h2"], "capture_required": []},
                        {"part_number": 3, "idea": "Part 3", "hook_options": ["h3"], "capture_required": []},
                    ]
                }
            return {"cards": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app.test_client()
            resp = client.post(f"/api/ideas/{card_id}/gate",
                               json={"action": "approve"})
        assert resp.status_code == 200

        # Check children were spawned
        children = store.list_series_children(card_id)
        assert len(children) == 2  # n=3, parent is 1, children = 2
        # F3: children enter state 'new', not 'approved'
        for child in children:
            assert child["card_state"] == "new"

    def test_capture_page_loads(self, app, sample_treatment_with_capture):
        """The capture page loads for an awaiting-capture card."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Needs footage",
            hook_options=["h"],
            treatment=sample_treatment_with_capture,
            origin="ai_originated",
        )
        store.update_card_state(card_id, "awaiting_capture")

        client = app.test_client()
        resp = client.get(f"/ideas/{card_id}/capture")
        assert resp.status_code == 200
        assert b"Capture tasks" in resp.data

    def test_capture_upload_text(self, app, sample_treatment_with_capture):
        """Uploading capture text via API works."""
        from pipeline import PipelineStore
        store = PipelineStore(db_path=app.config["DB_PATH"])
        card_id = store.create_idea_card(
            business_slug="testbiz",
            idea="Needs footage",
            hook_options=["h"],
            treatment=sample_treatment_with_capture,
            origin="ai_originated",
        )

        client = app.test_client()
        resp = client.post(f"/api/ideas/{card_id}/capture-upload",
                           json={"content": "This is captured footage notes."})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["material_id"] > 0