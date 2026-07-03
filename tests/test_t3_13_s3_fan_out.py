"""
Tests for T3.13 S3: Fan-out fidelity — platform set from Format Guide,
native platform verbatim, override support, fallback warning.

AC:
- Draft with format platforms [X] and business platforms [X, Instagram], no override
  → one asset, platform X, native=1, content byte-identical to draft_text (single-post fixture)
- Thread-format fixture → posts[] whose concatenation (minus numbering tokens) equals draft text
- Override body platforms: ["Instagram"] → IG asset only, adapted path, native=0
- Unresolvable format → configured platforms + warning key in response
"""
import os
import json
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def app_with_format_guide(tmp_path):
    """Flask app with Format Guide module containing platform declarations."""
    from app import create_app
    from module_store import ModuleStore

    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)
    modules_dir_base = str(tmp_path / "modules")
    modules_dir = os.path.join(modules_dir_base, "testbiz")
    os.makedirs(modules_dir)

    # Business config with X + Instagram platforms
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
  ideator: "test_backend"
test_backend:
  provider: "ollama_cloud"
  model: "test-model"
  temperature: 0
  max_tokens: 100
  base_url: "http://localhost:1"
""")

    with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
        f.write("feeds: []\nchannels: []\nqueries: []\n")

    # Format Guide module with platform declarations
    format_guide_md = """# Format Guide — v1.0

## Summary
Test format guide.

## Formats

### X Single Post
- **Platforms:** X
- **Best for:** hot takes
- **Length:** 1 tweet
- **Effort level:** low
- **Requires human capture:** none
- **Status:** proven
- **Reuse pathways:** none
- **Provenance:** test

**Skeleton:**
```
[Bold claim]
```

### X Thread
- **Platforms:** X
- **Best for:** deep explainers
- **Length:** 5-12 tweets
- **Effort level:** medium
- **Requires human capture:** none
- **Status:** proven
- **Reuse pathways:** none
- **Provenance:** test

**Skeleton:**
```
Tweet 1 (hook): [hook]
Tweet 2 (context): [context]
```

### Instagram Carousel
- **Platforms:** Instagram
- **Best for:** guides
- **Length:** 6-10 slides
- **Effort level:** medium
- **Requires human capture:** optional
- **Status:** proven
- **Reuse pathways:** none
- **Provenance:** test

**Skeleton:**
```
Slide 1 (cover): [title]
Slide 2 (context): [context]
```

## Provenance
- Version: 1.0
- Schema: format_guide_v1
"""
    db_path = str(tmp_path / "test.db")

    # Write Format Guide module directly to filesystem (bypasses gate for test setup)
    format_guide_path = os.path.join(modules_dir, "format-guide.md")
    with open(format_guide_path, "w") as f:
        f.write(format_guide_md)

    app = create_app(config_dir=config_dir, db_path=db_path)
    app.config["TESTING"] = True
    app.config["MODULES_DIR"] = modules_dir_base  # so ModuleStore finds the test modules
    return app


@pytest.fixture
def sample_treatment():
    return {
        "scope": {"type": "one_off"},
        "format": {"format_name": "X Single Post", "experimental": False},
        "capture_required": [],
        "reuse": {},
        "rationale": "Test rationale",
    }


def _make_shipped_draft(store, sample_treatment, draft_text, format_name="X Single Post"):
    """Helper: create a card + shipped draft for fan-out tests."""
    treatment = dict(sample_treatment)
    treatment["format"] = {"format_name": format_name, "experimental": False}
    card_id = store.create_idea_card(
        business_slug="testbiz", idea="Test idea",
        hook_options=["h"], treatment=treatment, origin="ai_originated",
    )
    draft_id = store.create_draft("testbiz", card_id, "ai_originated", format_name, "one_off")
    store.save_draft_content(draft_id, draft_text, {"image_prompts": [], "reference_notes": [], "shot_format_choices": []}, [])
    store.update_draft_state(draft_id, "shipped")
    return card_id, draft_id


class TestS3FanOutFidelity:
    """S3: Fan-out respects treatment format, native platform verbatim."""

    def test_native_single_post_content_byte_identical(self, app_with_format_guide, sample_treatment):
        """AC: Draft with format platforms [X] and business platforms [X, Instagram],
        no override → one asset, platform X, native=1, content byte-identical to draft_text."""
        from pipeline import PipelineStore
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "This is the approved draft text. It must ship verbatim."
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text, "X Single Post")

        # Mock the LLM — for native single post, it should NOT be called
        call_count = [0]
        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            call_count[0] += 1
            return {"content": "should not use this", "variant_type": "single_post", "posts": [], "image_prompts": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        # Only X (the native platform) should be produced
        assert len(data["assets"]) == 1
        assert data["assets"][0]["platform"] == "X"
        assert data["assets"][0]["native"] is True
        # No LLM call for native single post
        assert call_count[0] == 0

        # Content byte-identical to draft_text
        asset = store.get_asset(data["assets"][0]["id"])
        assert asset["content"] == draft_text
        assert asset["native"] == 1

    def test_native_thread_structured_via_llm(self, app_with_format_guide, sample_treatment):
        """AC: Thread-format fixture → posts[] from structure_v1.md prompt, not fan_out."""
        from pipeline import PipelineStore
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "This is the approved thread text. It has multiple sentences. Each should become a tweet."
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text, "X Thread")

        captured_prompts = []
        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            captured_prompts.append(prompt_file)
            if "structure_v1" in prompt_file:
                return {
                    "content": "Thread summary",
                    "variant_type": "thread",
                    "posts": ["1/3 This is the approved thread text.", "2/3 It has multiple sentences.", "3/3 Each should become a tweet."],
                    "image_prompts": ["none", "none", "none"],
                }
            return {"content": "adapted", "variant_type": "thread", "posts": ["adapted"], "image_prompts": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["assets"][0]["platform"] == "X"
        assert data["assets"][0]["native"] is True
        # Should have used structure_v1.md, not fan_out_v2.md
        assert any("structure_v1" in p for p in captured_prompts)
        assert not any("fan_out" in p for p in captured_prompts)

    def test_override_to_instagram_only(self, app_with_format_guide, sample_treatment):
        """AC: Override body platforms: ["Instagram"] → IG asset only, adapted path, native=0."""
        from pipeline import PipelineStore
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "This is the approved draft text for override test."
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text, "X Single Post")

        captured_prompts = []
        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            captured_prompts.append(prompt_file)
            return {"content": "IG adapted content", "variant_type": "single_post", "posts": ["IG adapted content"], "image_prompts": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={"platforms": ["Instagram"]})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        assert data["assets"][0]["platform"] == "Instagram"
        assert data["assets"][0]["native"] is False
        # Should have used fan_out prompt (adaptation path)
        assert any("fan_out" in p for p in captured_prompts)

        asset = store.get_asset(data["assets"][0]["id"])
        assert asset["native"] == 0
        # Content should NOT be byte-identical (it was adapted)
        assert asset["content"] != draft_text

    def test_unresolvable_format_falls_back_with_warning(self, app_with_format_guide, sample_treatment):
        """AC: Unresolvable format → configured platforms + warning key in response."""
        from pipeline import PipelineStore
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Draft with unknown format."
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text, "Unknown Format")

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            return {"content": "adapted", "variant_type": "single_post", "posts": ["adapted"], "image_prompts": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        # Should fall back to all configured platforms (X + Instagram)
        assert data["count"] == 2
        # Warning key present
        assert "warning" in data
        assert "Unknown Format" in data["warning"]
        # None should be native (format not found)
        for asset_info in data["assets"]:
            assert asset_info["native"] is False

    def test_native_column_migration_idempotent(self, app_with_format_guide, sample_treatment):
        """The native column migration is idempotent — creating assets after migration works."""
        from pipeline import PipelineStore

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        # Create asset with native=True
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, "test", "X Single Post")
        asset_id = store.create_asset(
            business_slug="testbiz", draft_id=draft_id,
            platform="X", variant_type="single_post",
            content="test content", native=True,
        )
        asset = store.get_asset(asset_id)
        assert asset["native"] == 1

        # Create another with native=False
        asset_id2 = store.create_asset(
            business_slug="testbiz", draft_id=draft_id,
            platform="Instagram", variant_type="single_post",
            content="adapted content", native=False,
        )
        asset2 = store.get_asset(asset_id2)
        assert asset2["native"] == 0

    def test_carousel_format_produces_native_carousel(self, app_with_format_guide, sample_treatment):
        """Carousel format on Instagram → native, structured via structure_v1.md."""
        from pipeline import PipelineStore
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Carousel content with multiple points to make across slides."
        treatment = dict(sample_treatment)
        treatment["format"] = {"format_name": "Instagram Carousel", "experimental": False}
        card_id = store.create_idea_card(
            business_slug="testbiz", idea="Carousel idea",
            hook_options=["h"], treatment=treatment, origin="ai_originated",
        )
        draft_id = store.create_draft("testbiz", card_id, "ai_originated", "Instagram Carousel", "one_off")
        store.save_draft_content(draft_id, draft_text, {"image_prompts": [], "reference_notes": [], "shot_format_choices": []}, [])
        store.update_draft_state(draft_id, "shipped")

        captured_prompts = []
        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            captured_prompts.append(prompt_file)
            if "structure_v1" in prompt_file:
                return {
                    "content": "Carousel summary",
                    "variant_type": "carousel",
                    "posts": ["Slide 1 (cover): Carousel content", "Slide 2: with multiple points", "Slide 3: to make across slides."],
                    "image_prompts": ["cover prompt", "prompt2", "prompt3"],
                }
            return {"content": "adapted", "variant_type": "carousel", "posts": ["adapted"], "image_prompts": []}

        with patch.object(LLMAdapter, "complete", mock_complete):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        # Only Instagram (native platform for carousel)
        assert data["count"] == 1
        assert data["assets"][0]["platform"] == "Instagram"
        assert data["assets"][0]["native"] is True
        assert any("structure_v1" in p for p in captured_prompts)