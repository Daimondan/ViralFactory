"""Tests for idea card editing (Gate 1 edit button)."""
import json
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from pipeline import PipelineStore


@pytest.fixture
def store(tmp_path):
    db = str(tmp_path / "test.db")
    s = PipelineStore(db_path=db)
    return s


def test_update_idea_card_fields_idea(store):
    """Editing idea text updates the card."""
    card_id = store.create_idea_card(
        business_slug="test",
        idea="Original idea text",
        hook_options=["hook 1", "hook 2"],
        treatment={"scope": {"type": "one_off"}, "format": "reel", "capture_required": [], "rationale": "test"},
        origin="human_seeded",
    )
    updated = store.update_idea_card_fields(card_id, idea="Edited idea text")
    assert updated["idea"] == "Edited idea text"


def test_update_idea_card_fields_hooks(store):
    """Editing hook options updates the card."""
    card_id = store.create_idea_card(
        business_slug="test",
        idea="Original idea",
        hook_options=["old hook"],
        treatment={"scope": {"type": "one_off"}, "format": "reel", "capture_required": [], "rationale": "test"},
        origin="human_seeded",
    )
    updated = store.update_idea_card_fields(card_id, hook_options=["new hook 1", "new hook 2"])
    hooks = json.loads(updated["hook_options"])
    assert hooks == ["new hook 1", "new hook 2"]


def test_update_idea_card_fields_both(store):
    """Editing both idea and hooks updates the card."""
    card_id = store.create_idea_card(
        business_slug="test",
        idea="Original",
        hook_options=["old"],
        treatment={"scope": {"type": "one_off"}, "format": "reel", "capture_required": [], "rationale": "test"},
        origin="human_seeded",
    )
    updated = store.update_idea_card_fields(card_id, idea="New idea", hook_options=["new hook"])
    assert updated["idea"] == "New idea"
    hooks = json.loads(updated["hook_options"])
    assert hooks == ["new hook"]


def test_update_idea_card_fields_no_change(store):
    """Calling with no kwargs returns the card unchanged."""
    card_id = store.create_idea_card(
        business_slug="test",
        idea="Stays the same",
        hook_options=["hook"],
        treatment={"scope": {"type": "one_off"}, "format": "reel", "capture_required": [], "rationale": "test"},
        origin="human_seeded",
    )
    updated = store.update_idea_card_fields(card_id)
    assert updated["idea"] == "Stays the same"