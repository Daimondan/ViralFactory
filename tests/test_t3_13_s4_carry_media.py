"""
Tests for T3.13 S4: Carry draft preview media into spawned assets.

AC:
- Fan-out on a draft with 2 preview images → each spawned asset lists 2 carried
  media rows pointing at the existing files; no new generation calls.
- generate-images afterward generates only uncovered prompts;
  regenerate: true forces fresh ones without deleting carried rows.
"""
import os
import json
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def app_with_format_guide(tmp_path):
    """Flask app with Format Guide module for fan-out tests."""
    from app import create_app

    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)
    modules_dir_base = str(tmp_path / "modules")
    modules_dir = os.path.join(modules_dir_base, "testbiz")
    os.makedirs(modules_dir)

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

## Provenance
- Version: 1.0
- Schema: format_guide_v1
"""
    with open(os.path.join(modules_dir, "format-guide.md"), "w") as f:
        f.write(format_guide_md)

    db_path = str(tmp_path / "test.db")
    app = create_app(config_dir=config_dir, db_path=db_path)
    app.config["TESTING"] = True
    app.config["MODULES_DIR"] = modules_dir_base
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


def _make_shipped_draft(store, treatment, draft_text, format_name="X Single Post", image_prompts=None):
    """Helper: create a card + shipped draft."""
    t = dict(treatment)
    t["format"] = {"format_name": format_name, "experimental": False}
    card_id = store.create_idea_card(
        business_slug="testbiz", idea="Test idea",
        hook_options=["h"], treatment=t, origin="ai_originated",
    )
    draft_id = store.create_draft("testbiz", card_id, "ai_originated", format_name, "one_off")
    vd = {"image_prompts": image_prompts or [], "reference_notes": [], "shot_format_choices": []}
    store.save_draft_content(draft_id, draft_text, vd, [])
    store.update_draft_state(draft_id, "shipped")
    return card_id, draft_id


class TestS4CarryDraftMedia:
    """S4: Draft preview media carried into spawned assets."""

    def test_fan_out_carries_draft_media(self, app_with_format_guide, sample_treatment):
        """AC: Fan-out on a draft with 2 preview images → each spawned asset
        lists 2 carried media rows pointing at the existing files."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text)

        # Create 2 draft preview images
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/draft_1.png", "test-model", "prompt 1", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/draft_2.png", "test-model", "prompt 2", owner_type="draft")

        # Fan out (native X — no LLM call for single post)
        with patch.object(LLMAdapter, "complete", return_value={
            "content": "test", "variant_type": "single_post", "posts": [], "image_prompts": []
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["count"] == 1
        asset_id = data["assets"][0]["id"]

        # Check carried media on the asset
        asset_media = ma.list_asset_media(asset_id, kind="image", owner_type="asset")
        assert len(asset_media) == 2
        assert asset_media[0]["path"] == "/data/media/draft_1.png"
        assert asset_media[1]["path"] == "/data/media/draft_2.png"

    def test_generate_images_skips_carried(self, app_with_format_guide, sample_treatment):
        """AC: generate-images afterward generates only uncovered prompts."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=["prompt1", "prompt2", "prompt3"])

        # Create 2 draft preview images
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/draft_1.png", "test-model", "prompt 1", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/draft_2.png", "test-model", "prompt 2", owner_type="draft")

        # Fan out (native X — no LLM for single post, uses visual_direction)
        with patch.object(LLMAdapter, "complete", return_value={
            "content": "test", "variant_type": "single_post", "posts": [], "image_prompts": []
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})
        assert resp.status_code == 200
        asset_id = resp.get_json()["assets"][0]["id"]

        # Generate images — should report 2 carried, generate only 1 (prompt3)
        with patch.object(MediaAdapter, "generate_image", return_value={"path": "/data/media/new.png"}):
            resp = client.post(f"/api/assets/{asset_id}/generate-images", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["carried"] == 2
        assert data["images_generated"] == 1  # only the uncovered prompt

    def test_regenerate_forces_all(self, app_with_format_guide, sample_treatment):
        """AC: regenerate: true forces fresh ones without deleting carried rows."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=["prompt1", "prompt2"])

        # Create 2 draft preview images
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/draft_1.png", "test-model", "prompt 1", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/draft_2.png", "test-model", "prompt 2", owner_type="draft")

        # Fan out
        with patch.object(LLMAdapter, "complete", return_value={
            "content": "test", "variant_type": "single_post", "posts": [], "image_prompts": []
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})
        asset_id = resp.get_json()["assets"][0]["id"]

        # Generate with regenerate=true — should generate all 2
        with patch.object(MediaAdapter, "generate_image", return_value={"path": "/data/media/new.png"}):
            resp = client.post(f"/api/assets/{asset_id}/generate-images", json={"regenerate": True})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["regenerate"] is True
        assert data["images_generated"] == 2  # all prompts generated

        # Carried rows should still exist
        carried = ma.list_asset_media(asset_id, kind="image", owner_type="asset")
        assert len(carried) == 2  # not deleted