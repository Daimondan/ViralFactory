"""
Tests for T8.5: Sources flow to production.

AC:
- Draft prompt (v2.3) contains {grounding_sources} section
- draft_generate assembles grounding_sources from card's source_refs
- Full content of every cited source included (inspectable via provenance)
- Empty content degrades to summary with (summary only) marker
- Fan-out prompt (v2.2) receives source titles only, not full content
"""
import os
import json
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    return PipelineStore(db_path=db_path)


class TestDraftPromptHasGroundingSources:
    """T8.5: Draft prompt v2.3 has grounding_sources section."""

    def test_prompt_version_23(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "draft", "generate_v2.md")
        with open(prompt_path) as f:
            first_line = f.readline().strip()
        assert "2.3" in first_line

    def test_prompt_has_grounding_sources_variable(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "draft", "generate_v2.md")
        with open(prompt_path) as f:
            content = f.read()
        assert "{grounding_sources}" in content
        assert "Grounding sources" in content
        assert "MUST come from these sources" in content

    def test_prompt_has_no_fabrication_rule(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "draft", "generate_v2.md")
        with open(prompt_path) as f:
            content = f.read().lower()
        assert "do not fabricate specifics" in content


class TestFanOutPromptHasSourceTitles:
    """T8.5: Fan-out prompt v2.2 has source_titles variable."""

    def test_fanout_version_22(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "assets", "fan_out_v2.md")
        with open(prompt_path) as f:
            first_line = f.readline().strip()
        assert "2.2" in first_line

    def test_fanout_has_source_titles_variable(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "assets", "fan_out_v2.md")
        with open(prompt_path) as f:
            content = f.read()
        assert "{source_titles}" in content
        assert "titles only" in content.lower()

    def test_fanout_does_not_have_grounding_sources(self):
        """Fan-out should NOT have full grounding sources — only titles."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "assets", "fan_out_v2.md")
        with open(prompt_path) as f:
            content = f.read()
        assert "{grounding_sources}" not in content


class TestGroundingSourcesAssembly:
    """T8.5: Grounding sources are assembled from source_refs correctly."""

    def test_resolve_with_full_content(self, store):
        """Source with content gets full content in grounding block."""
        s1 = store.add_source("biz", "rss_item", "Breaking AI News",
                              url="https://example.com/1",
                              summary="Short summary",
                              content="Full article text with details and quotes.",
                              content_hash="h1")
        sources = store.resolve_source_refs("biz", [s1])
        assert len(sources) == 1
        assert sources[0]["content"] == "Full article text with details and quotes."
        assert sources[0]["summary"] == "Short summary"

    def test_resolve_empty_content_degrades_to_summary(self, store):
        """Source with empty content but non-empty summary degrades to summary."""
        s1 = store.add_source("biz", "rss_item", "News Item",
                              url="https://example.com/2",
                              summary="Summary only content",
                              content="",
                              content_hash="h2")
        sources = store.resolve_source_refs("biz", [s1])
        assert len(sources) == 1
        # Content is empty, summary is available
        assert sources[0]["content"] == ""
        assert sources[0]["summary"] == "Summary only content"

    def test_multi_source_resolution(self, store):
        """Multiple source_refs resolve to multiple sources."""
        s1 = store.add_source("biz", "rss_item", "Source A", content="Content A", content_hash="h1")
        s2 = store.add_source("biz", "operator_material", "Source B", content="Content B", content_hash="h2")
        sources = store.resolve_source_refs("biz", [s1, s2])
        assert len(sources) == 2
        contents = {s["content"] for s in sources}
        assert contents == {"Content A", "Content B"}

    def test_no_source_refs_returns_empty(self, store):
        """Card with no source_refs resolves to empty list."""
        sources = store.resolve_source_refs("biz", [])
        assert sources == []