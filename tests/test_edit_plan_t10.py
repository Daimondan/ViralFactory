"""
Tests for T10.2 — Edit-plan record extension (AMENDMENT-008).

Covers:
- save_edit_plan with compliance contract + source draft hash
- get_edit_plan returns the extended fields
- append_review_round (append-only history)
- get_review_round_history
- get_compliance_contract
- Migration from old schema (columns added if missing)
- Backward compatibility: save_edit_plan without contract still works
"""

import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore


@pytest.fixture
def store(tmp_path):
    """Create a PipelineStore with a fresh DB, seeded with a draft and asset."""
    db_path = str(tmp_path / "test.db")
    store = PipelineStore(db_path)

    # Seed a business + idea card + draft + asset
    card_id = store.create_idea_card(
        business_slug="test",
        idea="Test idea",
        hook_options=["hook1"],
        treatment={"format_name": "reel"},
        origin="test",
    )
    draft_id = store.create_draft(
        business_slug="test",
        idea_card_id=card_id,
        origin="test",
        format_name="reel",
        scope="test scope",
    )
    asset_id = store.create_asset(
        business_slug="test",
        draft_id=draft_id,
        platform="instagram",
        variant_type="reel",
        content="Test content",
    )
    return store, draft_id, asset_id


class TestSaveEditPlanExtended:
    def test_save_with_compliance_contract(self, store):
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        contract = {"beats": [{"beat_id": "b1"}], "summary": "test"}
        plan_id = store.save_edit_plan(
            draft_id, asset_id, plan,
            compliance_contract=contract,
            source_draft_hash="abc123",
        )
        retrieved = store.get_edit_plan(plan_id)
        assert retrieved["compliance_contract_json"] is not None
        contract_json = json.loads(retrieved["compliance_contract_json"])
        assert contract_json["beats"][0]["beat_id"] == "b1"
        assert retrieved["source_draft_hash"] == "abc123"

    def test_save_without_contract_backward_compatible(self, store):
        """Old callers without contract args should still work."""
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, asset_id, plan)
        retrieved = store.get_edit_plan(plan_id)
        assert retrieved is not None
        assert retrieved["compliance_contract_json"] is None
        assert retrieved["source_draft_hash"] is None

    def test_review_round_history_starts_empty(self, store):
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, asset_id, plan)
        history = store.get_review_round_history(plan_id)
        assert history == []

    def test_get_compliance_contract(self, store):
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        contract = {"beats": [{"beat_id": "b1"}], "summary": "test"}
        plan_id = store.save_edit_plan(
            draft_id, asset_id, plan,
            compliance_contract=contract,
            source_draft_hash="sha256_hash",
        )
        result = store.get_compliance_contract(plan_id)
        assert result["contract"]["beats"][0]["beat_id"] == "b1"
        assert result["source_draft_hash"] == "sha256_hash"

    def test_get_compliance_contract_none_when_not_set(self, store):
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, asset_id, plan)
        result = store.get_compliance_contract(plan_id)
        assert result["contract"] is None
        assert result["source_draft_hash"] is None


class TestAppendReviewRound:
    def test_append_single_round(self, store):
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, asset_id, plan)

        round_entry = {
            "round": 1,
            "verdict": "revise_plan",
            "actions_taken": ["extended timeline"],
            "artifact_hashes": {"plan": "hash1"},
        }
        store.append_review_round(plan_id, round_entry)
        history = store.get_review_round_history(plan_id)
        assert len(history) == 1
        assert history[0]["round"] == 1
        assert history[0]["verdict"] == "revise_plan"

    def test_append_multiple_rounds_preserves_order(self, store):
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, asset_id, plan)

        for i in range(3):
            store.append_review_round(plan_id, {
                "round": i + 1,
                "verdict": "revise_plan" if i < 2 else "compliant",
                "actions_taken": [f"action_{i}"],
                "artifact_hashes": {f"plan": f"hash_{i}"},
            })

        history = store.get_review_round_history(plan_id)
        assert len(history) == 3
        assert history[0]["round"] == 1
        assert history[1]["round"] == 2
        assert history[2]["round"] == 3
        assert history[2]["verdict"] == "compliant"

    def test_append_is_not_mutating_existing_entries(self, store):
        """Append-only: existing round entries must not change."""
        store, draft_id, asset_id = store
        plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, asset_id, plan)

        store.append_review_round(plan_id, {"round": 1, "verdict": "revise_plan"})
        store.append_review_round(plan_id, {"round": 2, "verdict": "compliant"})

        history = store.get_review_round_history(plan_id)
        assert history[0]["round"] == 1
        assert history[0]["verdict"] == "revise_plan"
        assert history[1]["round"] == 2


class TestMigration:
    def test_old_db_migrates_columns(self, tmp_path):
        """A DB created with the old schema (no new columns) should migrate."""
        import sqlite3
        db_path = str(tmp_path / "old.db")
        # Create old-style edit_plans table
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE edit_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draft_id INTEGER NOT NULL,
                asset_id INTEGER NOT NULL,
                plan_json TEXT NOT NULL,
                feedback TEXT,
                status TEXT NOT NULL DEFAULT 'proposed',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO edit_plans (draft_id, asset_id, plan_json, status, created_at, updated_at)
            VALUES (1, 1, '{}', 'proposed', '2026-01-01', '2026-01-01');
        """)
        conn.commit()
        conn.close()

        # Now open with PipelineStore — should migrate
        store = PipelineStore(db_path)
        store._ensure_edit_plan_columns(sqlite3.connect(db_path))

        # Verify columns exist
        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(edit_plans)").fetchall()}
        conn.close()
        assert "compliance_contract_json" in cols
        assert "source_draft_hash" in cols
        assert "review_round_history" in cols

        # Old data should still be there
        plan = store.get_edit_plan(1)
        assert plan is not None
        assert plan["plan_json"] == "{}"