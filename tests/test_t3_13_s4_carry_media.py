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
- **Variant type:** single_post
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
- **Variant type:** thread
- **Best for:** analysis, storytelling
- **Length:** 5-10 tweets
- **Effort level:** medium
- **Requires human capture:** none
- **Status:** proven
- **Reuse pathways:** none
- **Provenance:** test

**Skeleton:**
```
1/ [Hook tweet]
2/ [Supporting detail]
...
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
        # Draft media prompts must match the draft's visual_direction prompts
        # so _carry_draft_media validates them as current (not stale).
        prompts = ["prompt 1", "prompt 2"]
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=prompts)

        # Create 2 draft preview images with matching prompts
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
        # Media prompts must match visual_direction prompts for carry validation
        prompts = ["prompt 1", "prompt 2", "prompt 3"]
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=prompts)

        # Create 2 draft preview images with matching prompts
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
        # Media prompts must match visual_direction prompts for carry validation
        prompts = ["prompt 1", "prompt 2"]
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=prompts)

        # Create 2 draft preview images with matching prompts
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


class TestStaleMediaSuppression:
    """Stale draft media from a previous generation must not be carried into
    assets, and posts with image_prompt='none' must not show images."""

    def test_stale_media_not_carried(self, app_with_format_guide, sample_treatment):
        """Draft media whose prompt doesn't match the draft's current
        visual_direction prompts is NOT carried into the spawned asset."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        # Current prompts are about tourism
        current_prompts = ["tourism image 1", "tourism image 2"]
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=current_prompts)

        # Create 2 draft preview images with STALE prompts (different topic)
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/stale_1.png", "test-model",
                         "compound interest chart", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/stale_2.png", "test-model",
                         "spend vs invest bar chart", owner_type="draft")

        # Fan out
        with patch.object(LLMAdapter, "complete", return_value={
            "content": "test", "variant_type": "single_post", "posts": [], "image_prompts": []
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        asset_id = resp.get_json()["assets"][0]["id"]

        # Stale media should NOT be carried
        carried = ma.list_asset_media(asset_id, kind="image", owner_type="asset")
        assert len(carried) == 0, f"Expected 0 stale images carried, got {len(carried)}"

    def test_matching_media_carried_stale_skipped(self, app_with_format_guide, sample_treatment):
        """When draft has 3 media rows but only 2 match current prompts,
        only the 2 matching ones are carried."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        current_prompts = ["prompt A", "prompt B"]
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=current_prompts)

        # 2 matching + 1 stale
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/match_1.png", "test-model",
                         "prompt A", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/stale.png", "test-model",
                         "old stale prompt", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/match_2.png", "test-model",
                         "prompt B", owner_type="draft")

        with patch.object(LLMAdapter, "complete", return_value={
            "content": "test", "variant_type": "single_post", "posts": [], "image_prompts": []
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        asset_id = resp.get_json()["assets"][0]["id"]
        carried = ma.list_asset_media(asset_id, kind="image", owner_type="asset")
        assert len(carried) == 2
        carried_prompts = [c["prompt"] for c in carried]
        assert "prompt A" in carried_prompts
        assert "prompt B" in carried_prompts
        assert "old stale prompt" not in carried_prompts

    def test_clear_draft_media(self, app_with_format_guide, sample_treatment):
        """clear_draft_media deletes all draft preview media for a draft."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=["p1", "p2"])

        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/old_1.png", "test-model",
                         "p1", owner_type="draft")
        ma._record_media(draft_id, "image", "/data/media/old_2.png", "test-model",
                         "p2", owner_type="draft")

        # Verify 2 rows exist
        assert len(ma.list_asset_media(draft_id, kind="image", owner_type="draft")) == 2

        # Clear
        deleted = ma.clear_draft_media(draft_id)
        assert deleted == 2

        # Verify 0 rows remain
        assert len(ma.list_asset_media(draft_id, kind="image", owner_type="draft")) == 0

    def test_clear_draft_media_only_deletes_draft_type(self, app_with_format_guide, sample_treatment):
        """clear_draft_media only deletes owner_type='draft', not 'asset' media."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  image_prompts=["p1"])

        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(draft_id, "image", "/data/media/draft_img.png", "test-model",
                         "p1", owner_type="draft")
        ma._record_media(999, "image", "/data/media/asset_img.png", "test-model",
                         "p1", owner_type="asset")

        # Clear draft media
        deleted = ma.clear_draft_media(draft_id)
        assert deleted == 1

        # Asset media should still exist
        asset_media = ma.list_asset_media(999, kind="image", owner_type="asset")
        assert len(asset_media) == 1


class TestPostImagesMapping:
    """The assets page must build a post_images mapping that only shows images
    for posts whose image_prompt is not 'none'."""

    def test_none_prompt_no_image(self, app_with_format_guide, sample_treatment):
        """A post with image_prompt='none' must not get an image shown,
        even if images exist in the asset media list."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  format_name="X Thread")

        # Fan out with mocked LLM that returns a thread with 3 posts,
        # image_prompts = ["img prompt 1", "none", "img prompt 3"]
        with patch.object(LLMAdapter, "complete", return_value={
            "content": "thread test",
            "variant_type": "thread",
            "posts": ["tweet 1 text", "tweet 2 text", "tweet 3 text"],
            "image_prompts": ["img prompt 1", "none", "img prompt 3"],
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        assert resp.status_code == 200
        asset_id = resp.get_json()["assets"][0]["id"]

        # Add 2 images to the asset (for prompts 1 and 3, skipping "none")
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(asset_id, "image", "/data/media/img1.png", "test-model",
                         "img prompt 1", owner_type="asset")
        ma._record_media(asset_id, "image", "/data/media/img3.png", "test-model",
                         "img prompt 3", owner_type="asset")

        # Load the assets page
        resp = client.get(f"/create/assets/{draft_id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # Tweet 1 should have its image, tweet 2 should NOT have an image,
        # tweet 3 should have its image
        assert "/data/media/img1.png" in html, "Tweet 1 image missing"
        assert "/data/media/img3.png" in html, "Tweet 3 image missing"
        assert "img2" not in html, "No img2 should exist"

        # Tweet 2's position should show a text-only placeholder, not an image
        # (the elif branch shows post-image-placeholder only if prompt != 'none')
        # Since prompt IS 'none', neither image nor placeholder should appear for tweet 2

    def test_all_none_no_images_shown(self, app_with_format_guide, sample_treatment):
        """If all image_prompts are 'none', no images should be shown on any post."""
        from pipeline import PipelineStore
        from media_adapter import MediaAdapter
        from unittest.mock import patch
        from llm_adapter import LLMAdapter

        store = PipelineStore(db_path=app_with_format_guide.config["DB_PATH"])
        draft_text = "Test draft text"
        card_id, draft_id = _make_shipped_draft(store, sample_treatment, draft_text,
                                                  format_name="X Thread")

        with patch.object(LLMAdapter, "complete", return_value={
            "content": "thread test",
            "variant_type": "thread",
            "posts": ["tweet 1", "tweet 2", "tweet 3"],
            "image_prompts": ["none", "none", "none"],
        }):
            client = app_with_format_guide.test_client()
            resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})

        asset_id = resp.get_json()["assets"][0]["id"]

        # Even if stale images somehow exist on the asset, they shouldn't show
        ma = MediaAdapter({"models": {}}, db_path=app_with_format_guide.config["DB_PATH"])
        ma._record_media(asset_id, "image", "/data/media/stale.png", "test-model",
                         "stale prompt", owner_type="asset")

        resp = client.get(f"/create/assets/{draft_id}")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # No images should be rendered for any tweet
        assert "/data/media/stale.png" not in html, "Stale image should not be shown for none-prompt post"
        # No actual <img> tags with class post-image should be present
        # (post-image and post-image-placeholder appear in CSS <style> block,
        # so we check for the actual img tag instead)
        assert "<img class=\"post-image\"" not in html, "No post-image img tags should be present for all-none prompts"
        assert "post-image-placeholder\">img" not in html and "post-image-placeholder\">slide" not in html, \
            "No image placeholders should be shown for all-none prompts"