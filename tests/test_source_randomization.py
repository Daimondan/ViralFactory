"""
Tests for source randomization and existing-ideas summarization.

Two fixes for idea diversity:
1. list_sources_sampled — randomized source selection prevents the same 50
   sources from dominating every generation run.
2. _summarize_idea — sentence-complete extraction instead of mid-word
   truncation at 120 chars, so the LLM can actually assess overlap.
"""
import os
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore
from idea_diversity import summarize_idea


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    return PipelineStore(db_path=db_path)


class TestListSourcesSampled:
    """list_sources_sampled — randomized source selection."""

    def test_returns_all_when_fewer_than_sample_size(self, store):
        """If active sources < sample_size, returns all without sampling."""
        for i in range(5):
            store.add_source("biz", "rss_item", f"Source {i}", content_hash=f"h{i}")
        result = store.list_sources_sampled("biz", sample_size=50, fresh_window=10)
        assert len(result) == 5

    def test_returns_exactly_sample_size(self, store):
        """With more sources than sample_size, returns exactly sample_size."""
        for i in range(100):
            store.add_source("biz", "rss_item", f"Source {i}", content_hash=f"h{i}")
        result = store.list_sources_sampled("biz", sample_size=30, fresh_window=5)
        assert len(result) == 30

    def test_fresh_sources_always_included(self, store):
        """The N most recent sources are always in the result."""
        for i in range(100):
            store.add_source("biz", "rss_item", f"Source {i}", content_hash=f"h{i}")
        result = store.list_sources_sampled("biz", sample_size=30, fresh_window=5)
        result_ids = {r["id"] for r in result}
        # The 5 most recent sources (highest IDs) should be present
        all_sources = store.list_sources("biz", limit=100)
        fresh_ids = {s["id"] for s in all_sources[:5]}
        assert fresh_ids.issubset(result_ids), \
            f"Fresh sources {fresh_ids - result_ids} missing from sample"

    def test_different_runs_produce_different_samples(self, store):
        """Two calls with the same params should produce different samples
        (probabilistic — with 100 sources and sample_size=30, overlap is
        expected but not 100%)."""
        for i in range(100):
            store.add_source("biz", "rss_item", f"Source {i}", content_hash=f"h{i}")
        result1 = store.list_sources_sampled("biz", sample_size=30, fresh_window=5)
        result2 = store.list_sources_sampled("biz", sample_size=30, fresh_window=5)
        ids1 = {r["id"] for r in result1}
        ids2 = {r["id"] for r in result2}
        # They should NOT be identical (extremely unlikely with 100 sources)
        assert ids1 != ids2, "Two samples produced identical results — randomization not working"

    def test_business_slug_scoping(self, store):
        """Only sources for the specified business are returned."""
        for i in range(10):
            store.add_source("biz-a", "rss_item", f"A{i}", content_hash=f"ha{i}")
        for i in range(10):
            store.add_source("biz-b", "rss_item", f"B{i}", content_hash=f"hb{i}")
        result = store.list_sources_sampled("biz-a", sample_size=50, fresh_window=10)
        assert all(r["business_slug"] == "biz-a" for r in result)
        assert len(result) == 10

    def test_respects_fresh_window_zero(self, store):
        """fresh_window=0 means all sources are randomly sampled."""
        for i in range(60):
            store.add_source("biz", "rss_item", f"Source {i}", content_hash=f"h{i}")
        result = store.list_sources_sampled("biz", sample_size=20, fresh_window=0)
        assert len(result) == 20
        # No guarantee any specific source is included — just check count


class TestSummarizeIdea:
    """_summarize_idea — sentence-complete extraction for existing_ideas."""

    def test_short_idea_returned_as_is(self):
        result = summarize_idea("This is a short idea.")
        assert result == "This is a short idea."

    def test_long_idea_cut_at_sentence_boundary(self):
        """Long idea is cut at a sentence boundary, not mid-word."""
        long_idea = (
            "The US just held an investment forum to position American companies "
            "in Guyana. The fastest-growing economy in the hemisphere is open for "
            "business. Foreign capital is arriving faster than any time in recent "
            "memory. But capital arriving isn't wealth built."
        )
        result = summarize_idea(long_idea, max_chars=160)
        # Should end with a period (complete sentence), not mid-word
        assert result.endswith(".") or result.endswith("…")
        assert len(result) <= 220  # some slack for completing a sentence
        # Should contain the key opening
        assert "US just held an investment forum" in result

    def test_no_sentence_boundary_falls_back_gracefully(self):
        """If there's no sentence boundary, falls back to word-boundary truncation."""
        no_boundary = "a" * 300  # no punctuation at all
        result = summarize_idea(no_boundary, max_chars=160)
        assert result.endswith("…")
        assert len(result) <= 165

    def test_empty_string(self):
        result = summarize_idea("")
        assert result == ""

    def test_preserves_core_claim_for_duplicate_detection(self):
        """The key test: two similar ideas should produce summaries that
        make the overlap obvious to the LLM."""
        idea_88 = (
            "The US just held an investment forum to position American companies "
            "in Guyana — the fastest-growing economy in the hemisphere. United, "
            "Southwest, and Cathay Pacific are all adding Caribbean routes. "
            "Foreign capital is arriving faster than any time in recent memory. "
            "But capital arriving isn't wealth built."
        )
        idea_92 = (
            "The US just held a forum to position American companies in Guyana, "
            "the fastest-growing economy in the hemisphere. Foreign capital is "
            "moving to remove friction and extract profit from the region. "
            "If Caribbean entrepreneurs don't build the systems now, they will "
            "be working for someone else in their own boom."
        )
        summary_88 = summarize_idea(idea_88)
        summary_92 = summarize_idea(idea_92)
        # Both summaries should contain the overlapping key phrase
        assert "US" in summary_88 and "Guyana" in summary_88
        assert "US" in summary_92 and "Guyana" in summary_92
        # Both should contain "American companies" (the core overlap)
        assert "American companies" in summary_88
        assert "American companies" in summary_92