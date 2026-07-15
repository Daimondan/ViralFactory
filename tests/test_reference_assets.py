"""
Tests for the Reference Asset Registry (T11.3).

Covers:
- Table creation and schema
- Propose → approve → retire lifecycle
- Version management (new versions from approved, locking approved payloads)
- Query methods (list, get, resolve_ref, get_grade_token)
- Error conditions (invalid kind, approving non-proposed, updating locked payload)
- Stats
"""
import json
import os
import sys
import tempfile

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from reference_assets import ReferenceAssetStore, VALID_KINDS, VALID_STATUSES


@pytest.fixture
def store(tmp_path):
    """Create a fresh store with a temp DB."""
    db_path = str(tmp_path / "test_ref.db")
    s = ReferenceAssetStore(db_path)
    yield s
    s.close()


@pytest.fixture
def business():
    return "test_business"


class TestSchema:
    def test_table_created(self, store):
        """reference_assets table exists after init."""
        cursor = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reference_assets'"
        )
        assert cursor.fetchone() is not None

    def test_indexes_created(self, store):
        """Indexes exist for efficient querying."""
        cursor = store.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='reference_assets'"
        )
        names = [r[0] for r in cursor.fetchall()]
        assert "idx_ref_assets_business" in names
        assert "idx_ref_assets_kind" in names
        assert "idx_ref_assets_status" in names
        assert "idx_ref_assets_unique" in names


class TestPropose:
    def test_propose_basic(self, store, business):
        """Proposing creates a proposed asset with version 1."""
        asset = store.propose(business, "grade_token", "default", {"grade_string": "test grade"})
        assert asset["id"] is not None
        assert asset["status"] == "proposed"
        assert asset["version"] == 1
        assert asset["business_slug"] == business

    def test_propose_stores_payload_as_json(self, store, business):
        """Payload is stored and retrievable as JSON."""
        payload = {"grade_string": "warm light", "palette": {"blue": "#0E1A2F"}}
        asset = store.propose(business, "grade_token", "default", payload)
        stored = json.loads(asset["payload_json"])
        assert stored == payload

    def test_propose_invalid_kind_raises(self, store, business):
        """Proposing with an invalid kind raises ValueError."""
        with pytest.raises(ValueError, match="Invalid kind"):
            store.propose(business, "invalid_kind", "test", {})

    def test_propose_creates_version_2_if_exists(self, store, business):
        """Proposing same kind+name again creates version 2."""
        store.propose(business, "grade_token", "default", {"v": 1})
        asset2 = store.propose(business, "grade_token", "default", {"v": 2})
        assert asset2["version"] == 2


class TestApprove:
    def test_approve_proposed(self, store, business):
        """Approving a proposed asset locks it as approved."""
        asset = store.propose(business, "character_ref", "fitzroy", {"name": "Fitzroy"})
        approved = store.approve(asset["id"])
        assert approved["status"] == "approved"
        assert approved["approved_at"] is not None
        assert approved["approved_by"] == "operator"

    def test_approve_non_proposed_raises(self, store, business):
        """Cannot approve an already-approved asset."""
        asset = store.propose(business, "character_ref", "fitzroy", {})
        store.approve(asset["id"])
        with pytest.raises(ValueError, match="can only approve 'proposed'"):
            store.approve(asset["id"])

    def test_approve_nonexistent_raises(self, store):
        """Cannot approve a non-existent asset."""
        with pytest.raises(ValueError, match="not found"):
            store.approve(99999)

    def test_approve_retires_previous_approved(self, store, business):
        """Approving a new version retires the previous approved version."""
        v1 = store.propose(business, "grade_token", "default", {"v": 1})
        v1_approved = store.approve(v1["id"])
        assert v1_approved["status"] == "approved"

        v2 = store.propose(business, "grade_token", "default", {"v": 2})
        store.approve(v2["id"])
        assert store.get_asset(v2["id"])["status"] == "approved"

        # v1 should now be retired
        v1_after = store.get_asset(v1["id"])
        assert v1_after["status"] == "retired"


class TestRetire:
    def test_retire_approved(self, store, business):
        """Retiring an approved asset preserves it with retired status."""
        asset = store.propose(business, "location_ref", "porch", {})
        store.approve(asset["id"])
        retired = store.retire(asset["id"])
        assert retired["status"] == "retired"

    def test_retire_non_approved_raises(self, store, business):
        """Cannot retire a proposed asset."""
        asset = store.propose(business, "location_ref", "porch", {})
        with pytest.raises(ValueError, match="can only retire 'approved'"):
            store.retire(asset["id"])


class TestUpdatePayload:
    def test_update_proposed_payload(self, store, business):
        """Can update payload of a proposed asset."""
        asset = store.propose(business, "card_style", "number_card", {"font": "Georgia"})
        updated = store.update_payload(asset["id"], {"font": "Inter"})
        stored = json.loads(updated["payload_json"])
        assert stored["font"] == "Inter"

    def test_update_approved_payload_raises(self, store, business):
        """Cannot update payload of an approved (locked) asset."""
        asset = store.propose(business, "card_style", "number_card", {"font": "Georgia"})
        store.approve(asset["id"])
        with pytest.raises(ValueError, match="approved assets are locked"):
            store.update_payload(asset["id"], {"font": "Inter"})


class TestQueryMethods:
    def test_list_assets(self, store, business):
        """List returns all assets for a business."""
        store.propose(business, "grade_token", "default", {})
        store.propose(business, "character_ref", "fitzroy", {})
        store.propose(business, "character_ref", "stackwell", {})
        all_assets = store.list_assets(business)
        assert len(all_assets) == 3

    def test_list_assets_filter_by_kind(self, store, business):
        """List filtered by kind returns only that kind."""
        store.propose(business, "grade_token", "default", {})
        store.propose(business, "character_ref", "fitzroy", {})
        chars = store.list_assets(business, kind="character_ref")
        assert len(chars) == 1
        assert chars[0]["kind"] == "character_ref"

    def test_list_assets_filter_by_status(self, store, business):
        """List filtered by status returns only that status."""
        a1 = store.propose(business, "grade_token", "default", {})
        a2 = store.propose(business, "character_ref", "fitzroy", {})
        store.approve(a2["id"])
        proposed = store.list_assets(business, status="proposed")
        approved = store.list_assets(business, status="approved")
        assert len(proposed) == 1
        assert len(approved) == 1

    def test_list_assets_isolated_by_business(self, store):
        """Assets are isolated per business slug."""
        store.propose("business_a", "grade_token", "default", {})
        store.propose("business_b", "grade_token", "default", {})
        a_assets = store.list_assets("business_a")
        b_assets = store.list_assets("business_b")
        assert len(a_assets) == 1
        assert len(b_assets) == 1
        assert a_assets[0]["business_slug"] == "business_a"

    def test_get_approved(self, store, business):
        """get_approved returns the latest approved version."""
        v1 = store.propose(business, "grade_token", "default", {"v": 1})
        store.approve(v1["id"])
        approved = store.get_approved(business, "grade_token", "default")
        assert approved is not None
        assert approved["version"] == 1

        v2 = store.propose(business, "grade_token", "default", {"v": 2})
        store.approve(v2["id"])
        approved = store.get_approved(business, "grade_token", "default")
        assert approved["version"] == 2

    def test_get_approved_returns_none_if_not_approved(self, store, business):
        """get_approved returns None if no approved version exists."""
        store.propose(business, "grade_token", "default", {})
        assert store.get_approved(business, "grade_token", "default") is None

    def test_resolve_ref(self, store, business):
        """resolve_ref returns approved asset for a kind+name reference."""
        asset = store.propose(business, "character_ref", "fitzroy", {"name": "Fitzroy"})
        store.approve(asset["id"])
        resolved = store.resolve_ref(business, "character_ref", "fitzroy")
        assert resolved is not None
        assert resolved["name"] == "fitzroy"

    def test_resolve_ref_unapproved_returns_none(self, store, business):
        """resolve_ref returns None for unapproved assets."""
        store.propose(business, "character_ref", "fitzroy", {})
        assert store.resolve_ref(business, "character_ref", "fitzroy") is None

    def test_get_grade_token(self, store, business):
        """get_grade_token returns the verbatim grade string."""
        grade = "warm golden-hour Caribbean light"
        asset = store.propose(business, "grade_token", "default", {"grade_string": grade})
        store.approve(asset["id"])
        assert store.get_grade_token(business) == grade

    def test_get_grade_token_none_if_not_approved(self, store, business):
        """get_grade_token returns None if no approved grade token."""
        store.propose(business, "grade_token", "default", {"grade_string": "test"})
        assert store.get_grade_token(business) is None


class TestStats:
    def test_stats_counts_by_kind_and_status(self, store, business):
        """Stats returns counts grouped by kind and status."""
        a1 = store.propose(business, "grade_token", "default", {})
        a2 = store.propose(business, "character_ref", "fitzroy", {})
        a3 = store.propose(business, "character_ref", "stackwell", {})
        store.approve(a1["id"])
        store.approve(a2["id"])

        stats = store.stats(business)
        assert stats["grade_token"]["approved"] == 1
        assert stats["character_ref"]["approved"] == 1
        assert stats["character_ref"]["proposed"] == 1

    def test_stats_empty_for_new_business(self, store):
        """Stats returns empty dict for a business with no assets."""
        stats = store.stats("new_business")
        assert stats == {}


class TestUpdateNotes:
    def test_update_notes_on_proposed(self, store, business):
        """Can update notes on a proposed asset."""
        asset = store.propose(business, "grade_token", "default", {}, notes="initial")
        updated = store.update_notes(asset["id"], "updated notes")
        assert updated["notes"] == "updated notes"

    def test_update_notes_on_approved(self, store, business):
        """Can update notes on an approved asset (notes are not payload)."""
        asset = store.propose(business, "grade_token", "default", {}, notes="initial")
        store.approve(asset["id"])
        updated = store.update_notes(asset["id"], "post-approval note")
        assert updated["notes"] == "post-approval note"


class TestFileManagement:
    def test_asset_dir_path(self):
        """asset_dir returns correct path."""
        path = ReferenceAssetStore.asset_dir("stackpenni", "character_ref", "fitzroy")
        assert "stackpenni" in path
        assert "character_ref" in path
        assert "fitzroy" in path

    def test_list_asset_files_nonexistent_dir(self, store):
        """list_asset_files returns empty list for nonexistent directory."""
        files = store.list_asset_files("nonexistent", "character_ref", "nobody")
        assert files == []


class TestGetGenerationContext:
    def test_empty_context_for_no_approved(self, store, business):
        """get_generation_context returns empty structure when no approved assets."""
        ctx = store.get_generation_context(business)
        assert ctx["grade_string"] is None
        assert ctx["characters"] == {}
        assert ctx["locations"] == {}

    def test_only_approved_assets_included(self, store, business):
        """Only approved assets appear in generation context — proposed are excluded."""
        # Propose but don't approve
        store.propose(business, "character_ref", "fitzroy", {"face_canon": "test"})
        ctx = store.get_generation_context(business)
        assert ctx["characters"] == {}

    def test_full_context_with_approved_assets(self, store, business):
        """get_generation_context returns all approved assets in structured format."""
        # Grade token
        g = store.propose(business, "grade_token", "default", {
            "grade_string": "warm Caribbean light",
            "palette": {"navy": "#0E1A2F"},
            "tagline": "Smart Money.",
        })
        store.approve(g["id"])

        # Character
        c = store.propose(business, "character_ref", "fitzroy", {
            "name": "Fitzroy",
            "face_canon": "Elderly Black Barbadian man, age 74",
            "wardrobe_canon": "Cream guayabera",
            "files": ["reference_render.png"],
        })
        store.approve(c["id"])

        ctx = store.get_generation_context(business)
        assert ctx["grade_string"] == "warm Caribbean light"
        assert ctx["tagline"] == "Smart Money."
        assert "fitzroy" in ctx["characters"]
        assert ctx["characters"]["fitzroy"]["face_canon"] == "Elderly Black Barbadian man, age 74"
        assert ctx["characters"]["fitzroy"]["files"] == ["reference_render.png"]
        assert ctx["characters"]["fitzroy"]["asset_id"] == c["id"]


class TestValidKinds:
    def test_all_expected_kinds_present(self):
        """VALID_KINDS contains all expected kinds."""
        expected = {"character_ref", "location_ref", "music_bed", "grade_token", "card_style", "lockup_svg"}
        assert VALID_KINDS == expected

    def test_valid_statuses(self):
        """VALID_STATUSES contains the three lifecycle states."""
        assert VALID_STATUSES == {"proposed", "approved", "retired"}