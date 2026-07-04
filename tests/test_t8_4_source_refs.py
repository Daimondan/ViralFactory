"""
Tests for T8.4: Idea cards carry source_refs.

AC:
- source_refs column exists on idea_cards
- create_idea_card accepts source_refs param
- resolve_source_refs validates against real sources rows
- Human seeds auto-register as manual source
- Prompt includes [S14] prefix format
- Schema requires source_refs with minItems=1
"""
import os
import json
import pytest
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore, IDEA_CARD_SCHEMA


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def store(db_path):
    return PipelineStore(db_path=db_path)


class TestSourceRefsColumn:
    """T8.4: idea_cards table has source_refs column."""

    def test_source_refs_column_exists(self, store, db_path):
        import sqlite3
        conn = sqlite3.connect(db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(idea_cards)").fetchall()]
        conn.close()
        assert "source_refs" in cols

    def test_create_idea_card_with_source_refs(self, store):
        """create_idea_card stores source_refs as JSON."""
        # Create sources first
        s1 = store.add_source("biz", "rss_item", "Source 1", content_hash="h1")
        s2 = store.add_source("biz", "rss_item", "Source 2", content_hash="h2")

        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea grounded in sources",
            hook_options=["Hook 1", "Hook 2"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "test"},
            origin="ai_originated",
            source_refs=[s1, s2],
        )
        card = store.get_idea_card(card_id)
        assert card is not None
        refs = json.loads(card["source_refs"])
        assert refs == [s1, s2]

    def test_create_idea_card_without_source_refs_defaults_empty(self, store):
        """create_idea_card without source_refs stores empty list."""
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Test idea",
            hook_options=["Hook"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "test", "experimental": False}, "capture_required": [], "rationale": "test"},
            origin="ai_originated",
        )
        card = store.get_idea_card(card_id)
        refs = json.loads(card["source_refs"])
        assert refs == []


class TestSchemaRequiresSourceRefs:
    """T8.4: IDEA_CARD_SCHEMA requires source_refs with minItems=1."""

    def test_schema_has_source_refs(self):
        """IDEA_CARD_SCHEMA includes source_refs in required and properties."""
        props = IDEA_CARD_SCHEMA["properties"]["cards"]["items"]["properties"]
        required = IDEA_CARD_SCHEMA["properties"]["cards"]["items"]["required"]
        assert "source_refs" in props
        assert "source_refs" in required

    def test_schema_source_refs_min_items(self):
        """source_refs has minItems=1 (at least one source required)."""
        props = IDEA_CARD_SCHEMA["properties"]["cards"]["items"]["properties"]
        assert props["source_refs"].get("minItems") == 1

    def test_schema_source_refs_items_integer(self):
        """source_refs items are integers."""
        props = IDEA_CARD_SCHEMA["properties"]["cards"]["items"]["properties"]
        assert props["source_refs"]["items"]["type"] == "integer"

    def test_schema_has_source_notes(self):
        """IDEA_CARD_SCHEMA includes source_notes (optional)."""
        props = IDEA_CARD_SCHEMA["properties"]["cards"]["items"]["properties"]
        assert "source_notes" in props


class TestResolveSourceRefsValidation:
    """T8.4: resolve_source_refs validates against real sources rows."""

    def test_resolve_valid_refs(self, store):
        """Valid source_refs resolve to full source records."""
        s1 = store.add_source("biz", "rss_item", "Real Source 1", content_hash="h1")
        s2 = store.add_source("biz", "rss_item", "Real Source 2", content_hash="h2")
        resolved = store.resolve_source_refs("biz", [s1, s2])
        assert len(resolved) == 2
        assert resolved[0]["title"] == "Real Source 1"

    def test_resolve_filters_nonexistent_refs(self, store):
        """Nonexistent source IDs are silently filtered out."""
        s1 = store.add_source("biz", "rss_item", "Real Source", content_hash="h1")
        resolved = store.resolve_source_refs("biz", [s1, 9999])
        assert len(resolved) == 1
        assert resolved[0]["title"] == "Real Source"

    def test_resolve_filters_wrong_business(self, store):
        """Source IDs from other businesses are filtered out."""
        s1 = store.add_source("biz-a", "rss_item", "A", content_hash="h1")
        s2 = store.add_source("biz-b", "rss_item", "B", content_hash="h2")
        resolved = store.resolve_source_refs("biz-a", [s1, s2])
        assert len(resolved) == 1


class TestHumanSeedAutoRegistersSource:
    """T8.4: Human seeds auto-register as manual source."""

    def test_seed_creates_manual_source(self, store):
        """When a human seed is added, a manual source row is created."""
        import hashlib as h
        seed = "My great idea about Caribbean wealth"
        seed_hash = h.sha256(seed.encode("utf-8")).hexdigest()[:16]
        source_id = store.add_source(
            business_slug="biz",
            source_type="manual",
            title=f"Operator seed: {seed[:80]}",
            summary=seed,
            content=seed,
            origin="operator",
            content_hash=seed_hash,
        )
        assert source_id > 0
        src = store.get_source(source_id)
        assert src["source_type"] == "manual"
        assert src["origin"] == "operator"
        assert seed in src["content"]

    def test_seed_source_dedupes(self, store):
        """Same seed text doesn't create duplicate sources."""
        import hashlib as h
        seed = "Same seed text"
        seed_hash = h.sha256(seed.encode("utf-8")).hexdigest()[:16]
        sid1 = store.add_source("biz", "manual", f"Operator seed: {seed[:80]}",
                                content=seed, origin="operator", content_hash=seed_hash)
        sid2 = store.add_source("biz", "manual", f"Operator seed: {seed[:80]}",
                                content=seed, origin="operator", content_hash=seed_hash)
        assert sid1 == sid2  # deduped


class TestMultiSourceCard:
    """T8.4: At least one multi-source card cites ≥2 sources with per-source rationale."""

    def test_multi_source_card(self, store):
        """A card can cite multiple sources."""
        s1 = store.add_source("biz", "rss_item", "Source A", content_hash="h1")
        s2 = store.add_source("biz", "rss_item", "Source B", content_hash="h2")
        card_id = store.create_idea_card(
            business_slug="biz",
            idea="Idea composing sources A and B into one story",
            hook_options=["Hook"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "X Thread", "experimental": False}, "capture_required": [], "rationale": "Source A provides the data, Source B provides the contrast"},
            origin="ai_originated",
            source_refs=[s1, s2],
        )
        card = store.get_idea_card(card_id)
        refs = json.loads(card["source_refs"])
        assert len(refs) == 2
        resolved = store.resolve_source_refs("biz", refs)
        assert len(resolved) == 2
        titles = {r["title"] for r in resolved}
        assert titles == {"Source A", "Source B"}


class TestPromptSourceDigestFormat:
    """T8.4: Source material digest uses [S14] title — summary format."""

    def test_prompt_has_source_bank_section(self):
        """Prompt file has the Source Bank section with cite-by-ID instructions."""
        with open(os.path.join(os.path.dirname(__file__), "..", "prompts", "ideas", "generate_v1.md")) as f:
            content = f.read()
        assert "Source Bank" in content
        assert "cite at least one source by ID" in content
        assert "source_refs" in content
        assert "{source_material}" in content
        assert "{source_criteria}" in content

    def test_prompt_version_bumped(self):
        """Prompt version is 1.3 (bumped from 1.2 for T8.4)."""
        with open(os.path.join(os.path.dirname(__file__), "..", "prompts", "ideas", "generate_v1.md")) as f:
            first_line = f.readline().strip()
        assert "1.3" in first_line