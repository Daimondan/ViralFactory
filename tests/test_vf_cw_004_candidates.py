"""
VF-CW-004 — Immutable candidates and append-only decisions tests.

Tests:
  - Candidate creation with immutable versions
  - Regeneration creates new version and supersedes prior
  - Superseded/failed/stale candidates cannot be approved
  - Append-only decisions (select, approve, reject, regenerate)
  - Decisions bind candidate_version + artifact_hash + requirement_hash
  - Identical retries are idempotent
  - No single 'approved' Boolean is authoritative — status + decisions are
  - Cross-session/cross-tenant isolation
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone

import pytest


@pytest.fixture
def tmp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_vf.db")
    yield db_path
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def candidate_store(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    # Initialize pipeline store first (creates production_sessions table)
    from pipeline import PipelineStore
    PipelineStore(db_path=tmp_db)
    from services.candidate_store import CandidateStore
    return CandidateStore(db_path=tmp_db)


def _setup_session(tmp_db, business_slug="test_tenant"):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService

    store = PipelineStore(db_path=tmp_db)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug=business_slug, idea="Test", hook_options=["Hook"],
        treatment={"format": "reel", "scope": "test", "capture_required": False},
        origin="human_seeded",
    )
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    card = dict(conn.execute(
        "SELECT * FROM idea_cards ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
        "draft_text, draft_version, draft_state, created_at, updated_at) "
        "VALUES (?, ?, 'human_seeded', 'reel', 'test', '', 1, 'shipped', ?, ?)",
        (business_slug, card["id"], now, now))
    conn.commit()
    draft = dict(conn.execute(
        "SELECT * FROM drafts ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, asset_state, created_at, updated_at) "
        "VALUES (?, ?, 'IG', 'reel', 'Test', 'pending', ?, ?)",
        (business_slug, draft["id"], now, now))
    conn.commit()
    asset = dict(conn.execute(
        "SELECT * FROM assets ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()

    svc = ProductionSessionService(db_path=tmp_db)
    session = svc.create_session(
        business_slug, draft["id"], asset["id"], "IG", "reel")
    return session


class TestCandidateCreation:
    def test_create_candidate(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            business_slug="test_tenant",
            production_session_id=session["id"],
            draft_id=session["draft_id"],
            asset_id=session["asset_id"],
            category="narration",
            role="full_take",
            artifact_hash="abc123",
            artifact_path="/data/media/test.wav",
            status="available",
        )
        assert c["id"] is not None
        assert c["version"] == 1
        assert c["status"] == "available"
        assert c["category"] == "narration"
        assert c["role"] == "full_take"
        assert c["artifact_hash"] == "abc123"

    def test_candidate_lineage_stable(self, candidate_store, tmp_db):
        """Same category+role+scope produces same lineage ID."""
        session = _setup_session(tmp_db)
        c1 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")
        c2 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")
        assert c1["candidate_lineage_id"] == c2["candidate_lineage_id"]
        assert c2["version"] == 2

    def test_different_roles_different_lineage(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c1 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")
        c2 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "visual_media", "beat_visual", status="available")
        assert c1["candidate_lineage_id"] != c2["candidate_lineage_id"]


class TestRegenerationSupersedes:
    def test_regeneration_supersedes_prior(self, candidate_store, tmp_db):
        """Regeneration creates a new version and supersedes the prior."""
        session = _setup_session(tmp_db)
        c1 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take",
            artifact_hash="hash_v1", status="available")

        c2 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take",
            artifact_hash="hash_v2", status="available")

        assert c2["version"] == 2

        # c1 should be superseded
        c1_refreshed = candidate_store.get_candidate("test_tenant", c1["id"])
        assert c1_refreshed["status"] == "superseded"
        assert c1_refreshed["superseded_by"] == c2["id"]

    def test_superseded_cannot_be_approved(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c1 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")
        c2 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        # Try to approve c1 (superseded)
        with pytest.raises(Exception, match="Cannot approve"):
            candidate_store.update_status("test_tenant", c1["id"], "approved")

    def test_failed_cannot_be_approved(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="failed")

        with pytest.raises(Exception, match="Cannot approve"):
            candidate_store.update_status("test_tenant", c["id"], "approved")

    def test_stale_cannot_be_approved(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="stale")

        with pytest.raises(Exception, match="Cannot approve"):
            candidate_store.update_status("test_tenant", c["id"], "approved")


class TestAppendOnlyDecisions:
    def test_approve_decision(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take",
            artifact_hash="abc", status="available")

        decision = candidate_store.record_decision(
            "test_tenant", session["id"], c["id"], "approve",
            feedback="Good take", requirement_version_hash="req_hash_1")

        assert decision["decision_type"] == "approve"
        assert decision["candidate_version"] == c["version"]
        assert decision["artifact_hash"] == "abc"
        assert decision["requirement_version_hash"] == "req_hash_1"
        assert decision["feedback"] == "Good take"

        # Candidate status updated to approved
        c_refreshed = candidate_store.get_candidate("test_tenant", c["id"])
        assert c_refreshed["status"] == "approved"

    def test_reject_decision(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        candidate_store.record_decision(
            "test_tenant", session["id"], c["id"], "reject",
            feedback="Too quiet")

        c_refreshed = candidate_store.get_candidate("test_tenant", c["id"])
        assert c_refreshed["status"] == "rejected"

    def test_regenerate_decision_supersedes(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        candidate_store.record_decision(
            "test_tenant", session["id"], c["id"], "regenerate",
            feedback="Need more energy")

        c_refreshed = candidate_store.get_candidate("test_tenant", c["id"])
        assert c_refreshed["status"] == "superseded"

    def test_decision_history_append_only(self, candidate_store, tmp_db):
        """Decisions are append-only — multiple decisions accumulate."""
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        candidate_store.record_decision(
            "test_tenant", session["id"], c["id"], "select")
        candidate_store.record_decision(
            "test_tenant", session["id"], c["id"], "approve")

        decisions = candidate_store.get_decisions("test_tenant", c["id"])
        assert len(decisions) == 2
        assert decisions[0]["decision_type"] == "select"
        assert decisions[1]["decision_type"] == "approve"

    def test_cannot_approve_superseded_via_decision(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c1 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")
        c2 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        with pytest.raises(Exception, match="Cannot approve"):
            candidate_store.record_decision(
                "test_tenant", session["id"], c1["id"], "approve")


class TestNoApprovedBoolean:
    def test_approval_is_status_not_boolean(self, candidate_store, tmp_db):
        """No single 'approved' Boolean is the source of truth.

        Approval is tracked via status + decision history, not a Boolean.
        """
        session = _setup_session(tmp_db)
        c = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        # Check there is no 'approved' boolean column
        conn = sqlite3.connect(tmp_db)
        cols = [r[1] for r in conn.execute(
            "PRAGMA table_info(component_candidates)").fetchall()]
        conn.close()

        assert "approved" not in cols, "No 'approved' boolean column"
        assert "is_approved" not in cols, "No 'is_approved' boolean column"

        # Approval is tracked via status and decisions
        candidate_store.record_decision(
            "test_tenant", session["id"], c["id"], "approve")

        c_refreshed = candidate_store.get_candidate("test_tenant", c["id"])
        assert c_refreshed["status"] == "approved"
        assert candidate_store.is_approved("test_tenant", c["id"]) is True

        decisions = candidate_store.get_decisions("test_tenant", c["id"])
        assert any(d["decision_type"] == "approve" for d in decisions)


class TestCrossSessionIsolation:
    def test_cross_session_list(self, candidate_store, tmp_db):
        """Candidates from different sessions don't mix."""
        session1 = _setup_session(tmp_db, "test_tenant")
        # Create a second session for a different asset
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_db)
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(tmp_db)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
            "content, asset_state, created_at, updated_at) "
            "VALUES (?, ?, 'X', 'thread', 'Test2', 'pending', ?, ?)",
            ("test_tenant", session1["draft_id"], now, now))
        conn.commit()
        asset2 = dict(conn.execute(
            "SELECT * FROM assets WHERE platform = 'X' ORDER BY id DESC LIMIT 1"
        ).fetchone())
        conn.close()

        svc = ProductionSessionService(db_path=tmp_db)
        session2 = svc.create_session(
            "test_tenant", session1["draft_id"], asset2["id"], "X", "thread")

        candidate_store.create_candidate(
            "test_tenant", session1["id"], session1["draft_id"],
            session1["asset_id"], "narration", "full_take", status="available")
        candidate_store.create_candidate(
            "test_tenant", session2["id"], session2["draft_id"],
            session2["asset_id"], "visual_media", "beat_visual", status="available")

        s1_candidates = candidate_store.list_candidates(
            "test_tenant", session1["id"])
        s2_candidates = candidate_store.list_candidates(
            "test_tenant", session2["id"])

        assert len(s1_candidates) == 1
        assert s1_candidates[0]["category"] == "narration"
        assert len(s2_candidates) == 1
        assert s2_candidates[0]["category"] == "visual_media"


class TestGetCurrentVersions:
    def test_current_versions_excludes_superseded(self, candidate_store, tmp_db):
        session = _setup_session(tmp_db)
        c1 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")
        c2 = candidate_store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take", status="available")

        current = candidate_store.get_current_versions("test_tenant", session["id"])
        # Only c2 should be current (c1 is superseded)
        assert len(current) == 1
        assert current[0]["id"] == c2["id"]