"""Tests for thread publish path bug fix (DIVERGENCE-022 related).

The thread publish path at buffer_adapter.py:232-237 was sending `content`
(the internal summary line) to Buffer instead of the actual thread `posts`
array. This test verifies the fix: thread posts are sent as a Buffer thread
via metadata.{service}.thread, and the top-level text is the first post.
"""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from buffer_adapter import BufferAdapter, BufferError


class TestGetServiceKey:
    """Test the _get_service_key platform → Buffer metadata key mapping."""

    def test_x_maps_to_twitter(self):
        assert BufferAdapter._get_service_key("x") == "twitter"

    def test_twitter_maps_to_twitter(self):
        assert BufferAdapter._get_service_key("twitter") == "twitter"

    def test_instagram_maps_to_instagram(self):
        assert BufferAdapter._get_service_key("instagram") == "instagram"

    def test_ig_maps_to_instagram(self):
        assert BufferAdapter._get_service_key("ig") == "instagram"

    def test_bluesky_maps_to_bluesky(self):
        assert BufferAdapter._get_service_key("bluesky") == "bluesky"

    def test_threads_maps_to_threads(self):
        assert BufferAdapter._get_service_key("threads") == "threads"

    def test_mastodon_maps_to_mastodon(self):
        assert BufferAdapter._get_service_key("mastodon") == "mastodon"

    def test_unknown_returns_none(self):
        assert BufferAdapter._get_service_key("unknown") is None

    def test_case_insensitive(self):
        assert BufferAdapter._get_service_key("X") == "twitter"
        assert BufferAdapter._get_service_key("Instagram") == "instagram"


class TestThreadPublish:
    """Test that thread publish sends actual posts, not the summary line."""

    def _make_adapter(self, tmp_path):
        """Create a BufferAdapter with mocked config."""
        db = str(tmp_path / "test.db")
        models_config = {
            "active": {"default": "buffer"},
            "buffer": {
                "provider": "buffer",
                "model": "n/a",
                "temperature": 0,
                "max_tokens": 0,
            },
        }
        adapter = BufferAdapter(models_config, db_path=db)
        return adapter

    def test_thread_uses_posts_not_content(self, tmp_path):
        """When publishing a thread, the text should be posts[0], not content."""
        adapter = self._make_adapter(tmp_path)

        # Mock the GraphQL call to capture the input_obj
        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_123", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_123")

        posts = ["First tweet in the thread", "Second tweet", "Third tweet"]
        content = "Thread about Caribbean wealth"  # the summary line

        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="x",
            content=content,
            posts=posts,
            asset_state="approved",
        )

        # The top-level text should be the first post, not the summary
        assert captured_input["text"] == "First tweet in the thread"
        assert captured_input["text"] != content

        # Thread metadata should contain all posts
        assert "metadata" in captured_input
        meta = captured_input["metadata"]
        assert "twitter" in meta
        thread = meta["twitter"]["thread"]
        assert len(thread) == 3
        assert thread[0]["text"] == "First tweet in the thread"
        assert thread[1]["text"] == "Second tweet"
        assert thread[2]["text"] == "Third tweet"

    def test_single_post_uses_content(self, tmp_path):
        """Single posts (no thread) should still use content as text."""
        adapter = self._make_adapter(tmp_path)

        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_456", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_123")

        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="x",
            content="Single post text",
            posts=None,
            asset_state="approved",
        )

        assert captured_input["text"] == "Single post text"
        assert "metadata" not in captured_input

    def test_single_post_with_one_item_not_thread(self, tmp_path):
        """Posts with only one item should not use thread metadata."""
        adapter = self._make_adapter(tmp_path)

        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_789", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_123")

        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="x",
            content="summary",
            posts=["one post"],
            asset_state="approved",
        )

        # Single post — no thread metadata
        assert "metadata" not in captured_input
        assert captured_input["text"] == "summary"

    def test_thread_with_frame_objects_not_treated_as_thread(self, tmp_path):
        """Reel/story_series posts are frame objects (dicts), not strings.
        They should NOT be treated as a text thread."""
        adapter = self._make_adapter(tmp_path)

        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_000", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_123")

        posts = [
            {"label": "HOOK", "vo_text": "frame 1"},
            {"label": "SETUP", "vo_text": "frame 2"},
        ]

        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="instagram",
            content="reel summary",
            posts=posts,
            asset_state="approved",
        )

        # Frame objects → not a text thread, no thread metadata
        assert "metadata" not in captured_input
        # Falls back to content (or post_caption.text — handled by caller)
        assert captured_input["text"] == "reel summary"

    def test_thread_filters_empty_posts(self, tmp_path):
        """Empty strings in the thread posts should be filtered out."""
        adapter = self._make_adapter(tmp_path)

        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_001", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_123")

        posts = ["real first tweet", "", "  ", "real second tweet"]
        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="x",
            content="summary",
            posts=posts,
            asset_state="approved",
        )

        meta = captured_input.get("metadata", {})
        thread = meta.get("twitter", {}).get("thread", [])
        # Only non-empty posts should be in the thread
        assert len(thread) == 2
        assert thread[0]["text"] == "real first tweet"
        assert thread[1]["text"] == "real second tweet"

    def test_thread_instagram_uses_instagram_key(self, tmp_path):
        """Instagram threads (e.g. carousel text) use 'instagram' metadata key."""
        adapter = self._make_adapter(tmp_path)

        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_002", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_456")

        posts = ["slide 1 text", "slide 2 text", "slide 3 text"]
        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="instagram",
            content="carousel summary",
            posts=posts,
            asset_state="approved",
        )

        meta = captured_input.get("metadata", {})
        assert "instagram" in meta
        thread = meta["instagram"]["thread"]
        assert len(thread) == 3

    def test_thread_unknown_platform_no_metadata(self, tmp_path):
        """Unknown platform: no thread metadata, but text still uses posts[0]."""
        adapter = self._make_adapter(tmp_path)

        captured_input = {}

        def mock_gql(query, variables):
            captured_input.update(variables.get("input", {}))
            return {"createPost": {"post": {"id": "buf_003", "status": "posted"}}}

        adapter._gql = mock_gql
        adapter.get_integration_for_platform = MagicMock(return_value="channel_789")

        posts = ["first", "second"]
        adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="unknown_platform",
            content="summary",
            posts=posts,
            asset_state="approved",
        )

        # Unknown platform → no thread metadata, but text is still posts[0]
        assert "metadata" not in captured_input
        assert captured_input["text"] == "first"