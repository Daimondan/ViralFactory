"""QA-loop F-002, F-003, F-004 regression tests."""
import os
import sys
import json
import sqlite3
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _make_db(tmp_path):
    """Create a minimal VF database for pipeline store tests."""
    db = str(tmp_path / "test.db")
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE idea_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_slug TEXT, idea TEXT, hook_options TEXT, treatment TEXT,
            origin TEXT, evidence_links TEXT, seed_text TEXT, parent_id INTEGER,
            card_state TEXT, kill_reason TEXT, capture_uploads TEXT,
            created_at TEXT, updated_at TEXT, source_refs TEXT, production_error TEXT
        );
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, business_slug TEXT,
            idea_card_id INTEGER, origin TEXT, format TEXT, scope TEXT,
            draft_text TEXT, visual_direction TEXT, self_audit_flags TEXT,
            draft_version INTEGER, draft_state TEXT, human_edits TEXT,
            feedback_entries TEXT, created_at TEXT, updated_at TEXT,
            platform_content TEXT, review_history TEXT, review_converged TEXT
        );
        CREATE TABLE assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, business_slug TEXT,
            draft_id INTEGER, platform TEXT, variant_type TEXT, content TEXT,
            image_prompts TEXT, generated_images TEXT, asset_state TEXT,
            publish_scheduled_at TEXT, created_at TEXT, updated_at TEXT,
            posts TEXT, native INTEGER, vo_segments TEXT
        );
    """)
    conn.commit()
    conn.close()
    return db


# ── F-002: stale production_error cleared on successful state advance ──

def test_F002_production_error_cleared_on_success(tmp_path):
    """A successful state advance (no production_error arg) must clear any
    stale production_error so the UI doesn't show an old failure."""
    from pipeline import PipelineStore
    db = _make_db(tmp_path)
    store = PipelineStore(db)
    # Create a card in production_failed with an error
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO idea_cards (business_slug, idea, card_state, production_error, created_at, updated_at) "
        "VALUES ('test', 'test idea', 'production_failed', ?, '2026-01-01', '2026-01-01')",
        (json.dumps({"step": "edit_plan", "error": "boom"}),),
    )
    conn.commit()
    conn.close()
    card = store.list_idea_cards("test")[0]
    assert json.loads(card["production_error"])["step"] == "edit_plan"
    # Advance to a healthy state without passing production_error
    store.update_card_state(card["id"], "assembling")
    card = store.get_idea_card(card["id"])
    assert card["card_state"] == "assembling"
    assert card["production_error"] is None, (
        f"Stale production_error not cleared: {card['production_error']}"
    )


def test_F002_production_error_preserved_when_explicitly_set(tmp_path):
    """When production_error IS passed, it must be stored."""
    from pipeline import PipelineStore
    db = _make_db(tmp_path)
    store = PipelineStore(db)
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO idea_cards (business_slug, idea, card_state, production_error, created_at, updated_at) "
        "VALUES ('test', 'idea', 'new', NULL, '2026-01-01', '2026-01-01')",
    )
    conn.commit()
    conn.close()
    card = store.list_idea_cards("test")[0]
    store.update_card_state(card["id"], "production_failed",
                            production_error={"step": "vo", "error": "no voice"})
    card = store.get_idea_card(card["id"])
    assert json.loads(card["production_error"])["step"] == "vo"


# ── F-003: soundtrack-decision accepts both "action" and "decision" ──

def test_F003_soundtrack_decision_accepts_decision_field():
    """The /api/assets/<id>/soundtrack-decision endpoint should accept both
    'action' and 'decision' in the request body."""
    # This is a source-level check: the route reads body.get("action") or
    # body.get("decision"). We verify the code path exists.
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "app.py")).read()
    assert 'body.get("action") or body.get("decision")' in src, (
        "soundtrack-decision endpoint should accept both 'action' and 'decision'"
    )


# ── F-004: /ideas page has gate-stat summary cards ──

def test_F004_ideas_template_has_gate_stats():
    """The /ideas template should render gate stat summary cards."""
    tmpl = open(os.path.join(os.path.dirname(__file__), "..", "src", "templates", "ideas.html")).read()
    assert "gate-stats" in tmpl, "ideas.html should have gate-stats section"
    assert "gate_counts" in tmpl, "ideas.html should reference gate_counts"


def test_F004_ideas_route_passes_gate_counts():
    """The ideas_queue route should pass gate_counts to the template."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "app.py")).read()
    # The render_template call for ideas.html should include gate_counts
    assert 'gate_counts=gate_counts' in src, (
        "ideas_queue route should pass gate_counts to render_template"
    )