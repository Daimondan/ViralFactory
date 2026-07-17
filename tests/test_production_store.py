"""
Tests for Production Contract storage and versioning (VF-AU-103).

The production store persists contracts, variants/beats, recipes, cues,
performance records, contract/process version links, and append-only
artifact history — without destroying existing drafts.

Rules:
- Additive migration; archive/version old records.
- No INSERT OR REPLACE on audit/provenance history.
- Repeated revisions preserve history.
- Tenant scoping via business_slug.
- Rollback-safe failure.
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_store import ProductionStore
from production_contract import assemble_contract


def _make_contract(contract_id="c001", **overrides):
    """Helper: create a minimal valid full contract."""
    content = {
        "contract_id": contract_id,
        "core_claim": "Compound interest is the eighth wonder",
        "audience_value": "Understand how saving early compounds",
        "evidence_refs": ["source:14"],
        "primary_emotional_job": "conviction",
        "primary_audience_action": "save",
        "format_name": "reel",
        "platform": "instagram",
        "capture_policy": "generated_allowed",
        "evidence_label": "HYPOTHESIS",
    }
    content.update(overrides.pop("content_overrides", {}))
    beats = overrides.pop("beats", [
        {"beat_id": "b01", "platform_variant_id": "pv001", "role": "hook",
         "required": True, "vo_text": "The eighth wonder",
         "staged_action": "Close-up ledger", "capture_policy": "generated_allowed",
         "evidence_refs": ["source:14"]},
    ])
    return assemble_contract(
        content_contract=content,
        beats=beats,
        text_intents=overrides.pop("text_intents", []),
        media_recipes=overrides.pop("media_recipes", [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "context",
             "source_policy": "generated_allowed",
             "primary": {"kind": "generated_image"}},
        ]),
        edit_segments=overrides.pop("edit_segments", [
            {"segment_id": "s01", "beat_ids": ["b01"], "source": "generated:1"},
        ]),
    )


class TestStoreInit:
    """The store should initialize cleanly on a fresh DB."""

    def test_init_creates_tables(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        # Tables should exist
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        assert "production_contracts" in tables
        assert "production_contract_revisions" in tables
        assert "performance_records" in tables

    def test_init_is_idempotent(self, tmp_path):
        """Re-opening the store should not error or drop data."""
        store1 = ProductionStore(str(tmp_path / "test.db"))
        contract = _make_contract()
        store1.save_contract("stackpenni", 1, contract)

        store2 = ProductionStore(str(tmp_path / "test.db"))
        loaded = store2.get_contract("c001")
        assert loaded is not None
        assert loaded["contract_id"] == "c001"


class TestSaveAndGetContract:
    """Saving and retrieving contracts."""

    def test_save_and_get_contract(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        contract = _make_contract()
        store.save_contract("stackpenni", draft_id=1, contract=contract)

        loaded = store.get_contract("c001")
        assert loaded is not None
        assert loaded["contract_id"] == "c001"
        assert loaded["version"] == "2.0"
        assert len(loaded["beats"]) == 1
        assert "writer_contract_hash" in loaded

    def test_get_nonexistent_contract_returns_none(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        assert store.get_contract("nonexistent") is None

    def test_save_contract_stores_business_slug(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        contract = _make_contract()
        store.save_contract("stackpenni", draft_id=1, contract=contract)
        loaded = store.get_contract("c001")
        assert loaded["business_slug"] == "stackpenni"
        assert loaded["draft_id"] == 1


class TestVersioningAndHistory:
    """Repeated revisions preserve history (append-only)."""

    def test_revision_creates_history_entry(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        contract_v1 = _make_contract()
        store.save_contract("stackpenni", 1, contract_v1)

        # Save a revised version with changed content
        contract_v2 = _make_contract()
        contract_v2["content_contract"]["core_claim"] = "Updated claim"
        contract_v2 = assemble_contract(
            content_contract=contract_v2["content_contract"],
            beats=contract_v2["beats"],
            media_recipes=contract_v2["media_recipes"],
            edit_segments=contract_v2["edit_segments"],
        )
        store.save_contract("stackpenni", 1, contract_v2)

        # History should have 2 entries
        history = store.get_contract_history("c001")
        assert len(history) == 2
        # The latest should be the revised version
        latest = store.get_contract("c001")
        assert "Updated claim" in latest["content_contract"]["core_claim"]

    def test_history_is_append_only(self, tmp_path):
        """No INSERT OR REPLACE on audit/provenance history."""
        store = ProductionStore(str(tmp_path / "test.db"))
        contract = _make_contract()
        store.save_contract("stackpenni", 1, contract)
        store.save_contract("stackpenni", 1, contract)  # same contract saved twice

        history = store.get_contract_history("c001")
        assert len(history) == 2  # both saves recorded

    def test_revision_preserves_old_version_in_history(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        contract_v1 = _make_contract()
        store.save_contract("stackpenni", 1, contract_v1)

        contract_v2 = _make_contract()
        contract_v2["content_contract"]["core_claim"] = "Version 2 claim"
        contract_v2 = assemble_contract(
            content_contract=contract_v2["content_contract"],
            beats=contract_v2["beats"],
            media_recipes=contract_v2["media_recipes"],
            edit_segments=contract_v2["edit_segments"],
        )
        store.save_contract("stackpenni", 1, contract_v2)

        history = store.get_contract_history("c001")
        # First entry should have original claim
        first_contract = json.loads(history[0]["contract_json"])
        assert "Compound interest" in first_contract["content_contract"]["core_claim"]
        # Last entry should have updated claim
        last_contract = json.loads(history[-1]["contract_json"])
        assert "Version 2 claim" in last_contract["content_contract"]["core_claim"]


class TestTenantIsolation:
    """Tenant data must be isolated by business_slug."""

    def test_tenant_isolation(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        contract_a = _make_contract("c001")
        contract_b = _make_contract("c002")
        contract_b["content_contract"]["core_claim"] = "Business B claim"
        contract_b = assemble_contract(
            content_contract=contract_b["content_contract"],
            beats=contract_b["beats"],
            media_recipes=contract_b["media_recipes"],
            edit_segments=contract_b["edit_segments"],
        )

        store.save_contract("business_a", 1, contract_a)
        store.save_contract("business_b", 2, contract_b)

        a_contract = store.get_contract("c001")
        b_contract = store.get_contract("c002")
        assert a_contract["business_slug"] == "business_a"
        assert b_contract["business_slug"] == "business_b"

        # List contracts per tenant
        a_contracts = store.list_contracts("business_a")
        b_contracts = store.list_contracts("business_b")
        assert len(a_contracts) == 1
        assert len(b_contracts) == 1
        assert a_contracts[0]["contract_id"] == "c001"
        assert b_contracts[0]["contract_id"] == "c002"


class TestPerformanceRecord:
    """Performance records can be stored and retrieved."""

    def test_save_and_get_performance_record(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        # First create a contract
        contract = _make_contract()
        store.save_contract("stackpenni", 1, contract)

        # Save a performance record
        record = {
            "platform_post_id": "ig_12345",
            "published_at": "2026-07-17T12:00:00Z",
            "metrics": {
                "views": {"value": 1500, "confidence": "measured", "captured_at": "2026-07-18"},
                "likes": {"value": 42, "confidence": "measured", "captured_at": "2026-07-18"},
                "comments": {"value": 7, "confidence": "measured", "captured_at": "2026-07-18"},
            },
            "derived_ratios": {
                "comment_to_like": {"value": 0.167, "confidence": "computed", "captured_at": "2026-07-18"},
            },
            "creative_fingerprint": {
                "format": "reel",
                "narrative_pattern": "proof-first",
                "hook_mechanism": "claim-first",
                "emotional_job": "conviction",
                "primary_action": "save",
                "text_functions": ["hook", "caption"],
                "audio_mode": "vo_only",
                "media_mix": ["generated"],
            },
        }
        store.save_performance_record("c001", record)

        loaded = store.get_performance_record("c001")
        assert loaded is not None
        assert loaded["platform_post_id"] == "ig_12345"
        assert loaded["metrics"]["likes"]["value"] == 42
        assert "comment_to_like" in loaded["derived_ratios"]

    def test_performance_record_with_null_metrics(self, tmp_path):
        """Missing metrics must be preserved as null, not fabricated."""
        store = ProductionStore(str(tmp_path / "test.db"))
        contract = _make_contract()
        store.save_contract("stackpenni", 1, contract)

        record = {
            "platform_post_id": "ig_12346",
            "published_at": "2026-07-17T12:00:00Z",
            "metrics": {
                "views": {"value": None, "confidence": "unknown", "captured_at": None},
                "likes": {"value": None, "confidence": "unknown", "captured_at": None},
            },
            "derived_ratios": {},
            "creative_fingerprint": {},
        }
        store.save_performance_record("c001", record)
        loaded = store.get_performance_record("c001")
        assert loaded["metrics"]["views"]["value"] is None

    def test_repeated_captures_append_history(self, tmp_path):
        """Repeated metric captures should append, not replace."""
        store = ProductionStore(str(tmp_path / "test.db"))
        contract = _make_contract()
        store.save_contract("stackpenni", 1, contract)

        record_v1 = {
            "platform_post_id": "ig_123",
            "published_at": "2026-07-17",
            "metrics": {"likes": {"value": 10, "confidence": "measured", "captured_at": "2026-07-18"}},
            "derived_ratios": {},
            "creative_fingerprint": {},
        }
        store.save_performance_record("c001", record_v1)

        record_v2 = {
            "platform_post_id": "ig_123",
            "published_at": "2026-07-17",
            "metrics": {"likes": {"value": 25, "confidence": "measured", "captured_at": "2026-07-19"}},
            "derived_ratios": {},
            "creative_fingerprint": {},
        }
        store.save_performance_record("c001", record_v2)

        # Latest should have 25
        loaded = store.get_performance_record("c001")
        assert loaded["metrics"]["likes"]["value"] == 25

        # History should have 2 entries
        history = store.get_performance_history("c001")
        assert len(history) == 2


class TestMigrationSafety:
    """Migration from existing DB should not destroy existing tables."""

    def test_migration_preserves_existing_tables(self, tmp_path):
        """Opening ProductionStore on a DB that already has pipeline tables
        should not destroy existing data."""
        import sqlite3
        db_path = str(tmp_path / "test.db")

        # Create a DB with existing pipeline tables and data
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_slug TEXT,
                content TEXT
            );
            INSERT INTO drafts (business_slug, content) VALUES ('stackpenni', 'old draft');
        """)
        conn.commit()
        conn.close()

        # Now open ProductionStore — should add new tables, not destroy existing
        store = ProductionStore(db_path)

        # Verify old data is still there
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT content FROM drafts WHERE id = 1").fetchone()
        conn.close()
        assert row is not None
        assert row[0] == "old draft"