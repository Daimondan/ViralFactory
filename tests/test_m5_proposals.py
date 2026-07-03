"""
Tests for M5: Inward learning loop + async gate (T5.1 + T5.2 + T5.3)
"""

import os
import sys
import json
import sqlite3
import tempfile
import pytest
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from proposal_store import ProposalStore


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def store(temp_db):
    return ProposalStore(db_path=temp_db)


class TestProposalStore:
    """Test the proposal store — T5.2 core."""

    def test_tables_created(self, store, temp_db):
        """proposals table created by ProposalStore."""
        conn = sqlite3.connect(temp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "proposals" in table_names
        conn.close()

    def test_create_proposal(self, store):
        """Can create a proposal and retrieve it."""
        pid = store.create_proposal(
            business_slug="testbiz",
            target_module="voice-profile",
            target_section="patterns[3]",
            proposal_type="add",
            evidence=["Direct edit on draft #5 kept 'I been' construction"],
            change_description="Add 'I been' as a natural voice pattern",
            exact_diff="Add to patterns: {pattern: 'I been', example: 'I been thinking', do_not_correct: true}",
            rationale="Operator's direct edit signals this is natural in their voice",
            confidence="high",
        )
        assert pid > 0

        proposal = store.get_proposal(pid)
        assert proposal["target_module"] == "voice-profile"
        assert proposal["target_section"] == "patterns[3]"
        assert proposal["proposal_type"] == "add"
        assert proposal["status"] == "pending"
        assert "I been" in proposal["evidence_parsed"][0]
        assert proposal["confidence"] == "high"

    def test_list_proposals(self, store):
        """Can list proposals filtered by status."""
        store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        store.create_proposal(
            business_slug="testbiz", target_module="viral-patterns",
            target_section="s2", proposal_type="modify",
            evidence=["e2"], change_description="d2",
            exact_diff="diff2", rationale="r2",
        )

        all_proposals = store.list_proposals("testbiz")
        assert len(all_proposals) == 2

        pending = store.list_proposals("testbiz", status="pending")
        assert len(pending) == 2

        voice_only = store.list_proposals("testbiz", target_module="voice-profile")
        assert len(voice_only) == 1
        assert voice_only[0]["target_module"] == "voice-profile"

    def test_approve_proposal(self, store):
        """Approving a proposal changes status and sets decided_at."""
        pid = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        result = store.approve_proposal(pid)
        assert result["status"] == "approved"
        assert result["decided_at"] is not None

    def test_reject_proposal(self, store):
        """Rejecting a proposal stores the reason."""
        pid = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        result = store.reject_proposal(pid, "not enough evidence")
        assert result["status"] == "rejected"
        assert result["reject_reason"] == "not enough evidence"
        assert result["decided_at"] is not None

    def test_superseding(self, store):
        """Newer proposal on same section supersedes older."""
        pid1 = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="patterns[3]", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        pid2 = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="patterns[3]", proposal_type="add",
            evidence=["e2"], change_description="d2",
            exact_diff="diff2", rationale="r2",
        )

        p1 = store.get_proposal(pid1)
        p2 = store.get_proposal(pid2)

        assert p1["status"] == "superseded"
        assert p1["superseded_by"] == pid2
        assert p2["status"] == "pending"
        assert p2["superseded_by"] is None

    def test_superseding_only_pending(self, store):
        """Already-decided proposals are not superseded."""
        pid1 = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        store.approve_proposal(pid1)

        pid2 = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="modify",
            evidence=["e2"], change_description="d2",
            exact_diff="diff2", rationale="r2",
        )

        p1 = store.get_proposal(pid1)
        assert p1["status"] == "approved"  # Not superseded — already decided
        p2 = store.get_proposal(pid2)
        assert p2["status"] == "pending"

    def test_pending_count(self, store):
        """get_pending_count counts across all types."""
        store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        store.create_proposal(
            business_slug="testbiz", target_module="viral-patterns",
            target_section="s2", proposal_type="modify",
            evidence=["e2"], change_description="d2",
            exact_diff="diff2", rationale="r2",
        )
        store.create_proposal(
            business_slug="testbiz", target_module="format-guide",
            target_section="s3", proposal_type="add",
            evidence=["e3"], change_description="d3",
            exact_diff="diff3", rationale="r3",
        )
        store.reject_proposal(1, "test")

        assert store.get_pending_count("testbiz") == 2

    def test_bulk_approve(self, store):
        """Bulk approve works."""
        pids = []
        for i in range(3):
            pids.append(store.create_proposal(
                business_slug="testbiz", target_module="voice-profile",
                target_section=f"s{i}", proposal_type="add",
                evidence=[f"e{i}"], change_description=f"d{i}",
                exact_diff=f"diff{i}", rationale=f"r{i}",
            ))
        results = store.bulk_approve(pids)
        assert len(results) == 3
        for r in results:
            assert r["status"] == "approved"

    def test_bulk_reject(self, store):
        """Bulk reject with a single reason."""
        pids = []
        for i in range(3):
            pids.append(store.create_proposal(
                business_slug="testbiz", target_module="voice-profile",
                target_section=f"s{i}", proposal_type="add",
                evidence=[f"e{i}"], change_description=f"d{i}",
                exact_diff=f"diff{i}", rationale=f"r{i}",
            ))
        results = store.bulk_reject(pids, "bulk test")
        assert len(results) == 3
        for r in results:
            assert r["status"] == "rejected"
            assert r["reject_reason"] == "bulk test"

    def test_get_superseded_chain(self, store):
        """Get chain of proposals superseded by a given one."""
        pid1 = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        pid2 = store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e2"], change_description="d2",
            exact_diff="diff2", rationale="r2",
        )
        chain = store.get_superseded_chain(pid2)
        assert len(chain) == 1
        assert chain[0]["id"] == pid1

    def test_proposal_age_days(self, store):
        """Age calculation works."""
        old_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        age = store.get_proposal_age_days(old_time)
        assert age == 5

    def test_proposal_summary(self, store):
        """Summary stats are correct."""
        store.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        store.create_proposal(
            business_slug="testbiz", target_module="viral-patterns",
            target_section="s2", proposal_type="modify",
            evidence=["e2"], change_description="d2",
            exact_diff="diff2", rationale="r2",
        )
        store.approve_proposal(1)

        summary = store.get_proposal_summary("testbiz")
        assert summary["pending"] == 1
        assert summary["approved"] == 1
        assert summary["rejected"] == 0
        assert summary["superseded"] == 0
        assert "viral-patterns" in summary["by_module"]

    def test_amendment_005_targets(self, store):
        """Per AMENDMENT-005: process-registry is a valid target_module."""
        pid = store.create_proposal(
            business_slug="testbiz",
            target_module="process-registry",
            target_section="draft_generate.modules.voice-profile.budget",
            proposal_type="mapping_change",
            evidence=["Drafter output improved when voice-profile budget was 3000 vs 2000"],
            change_description="Increase voice-profile budget in draft_generate from 2000 to 3000",
            exact_diff="Change: voice-profile: {budget: 2000} → voice-profile: {budget: 3000}",
            rationale="Higher voice-profile budget produced drafts rated closer to the operator's voice",
            confidence="medium",
        )
        proposal = store.get_proposal(pid)
        assert proposal["target_module"] == "process-registry"
        assert proposal["proposal_type"] == "mapping_change"


class TestFlaskRoutes:
    """Test Flask routes for the gate queue — T5.2."""

    @pytest.fixture
    def flask_app(self, tmp_path):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from app import create_app

        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)

        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            f.write("""
business:
  name: "TestBiz"
  slug: "testbiz"
  description: "Test business"
brands:
  - name: "TestBiz"
    purpose: "Test"
subjects:
  - "test"
platforms:
  - name: "X"
    handle: "@test"
    priority: 1
goals:
  - "test"
red_lines:
  - "no spam"
audience_description: "test audience"
""")
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            f.write("""
active:
  default: "test_backend"
  drafter: "test_backend"
  converse: "test_backend"
test_backend:
  provider: "ollama_cloud"
  model: "test-model"
  temperature: 0
  max_tokens: 100
  base_url: "http://localhost:1"
""")
        with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
            f.write("feeds: []\nchannels: []\nqueries: []\n")

        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        return app

    def test_proposals_page_renders(self, flask_app):
        """GET /proposals renders the gate queue page."""
        with flask_app.test_client() as client:
            resp = client.get("/proposals")
            assert resp.status_code == 200
            assert b"Gate Queue" in resp.data

    def test_approve_proposal_route(self, flask_app):
        """POST /api/proposals/<id>/approve approves a proposal."""
        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=flask_app.config["DB_PATH"])
        pid = ps.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )

        with flask_app.test_client() as client:
            resp = client.post(f"/api/proposals/{pid}/approve", json={})
            assert resp.status_code == 200
            assert ps.get_proposal(pid)["status"] == "approved"

    def test_reject_proposal_route(self, flask_app):
        """POST /api/proposals/<id>/reject rejects with a reason."""
        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=flask_app.config["DB_PATH"])
        pid = ps.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )

        with flask_app.test_client() as client:
            resp = client.post(f"/api/proposals/{pid}/reject", json={"reason": "too vague"})
            assert resp.status_code == 200
            assert ps.get_proposal(pid)["status"] == "rejected"
            assert ps.get_proposal(pid)["reject_reason"] == "too vague"

    def test_bulk_approve_route(self, flask_app):
        """POST /api/proposals/bulk-approve bulk approves."""
        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=flask_app.config["DB_PATH"])
        pids = []
        for i in range(3):
            pids.append(ps.create_proposal(
                business_slug="testbiz", target_module="voice-profile",
                target_section=f"s{i}", proposal_type="add",
                evidence=[f"e{i}"], change_description=f"d{i}",
                exact_diff=f"diff{i}", rationale=f"r{i}",
            ))

        with flask_app.test_client() as client:
            resp = client.post("/api/proposals/bulk-approve", json={"ids": pids})
            assert resp.status_code == 200
            for pid in pids:
                assert ps.get_proposal(pid)["status"] == "approved"

    def test_bulk_reject_route(self, flask_app):
        """POST /api/proposals/bulk-reject bulk rejects."""
        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=flask_app.config["DB_PATH"])
        pids = []
        for i in range(3):
            pids.append(ps.create_proposal(
                business_slug="testbiz", target_module="voice-profile",
                target_section=f"s{i}", proposal_type="add",
                evidence=[f"e{i}"], change_description=f"d{i}",
                exact_diff=f"diff{i}", rationale=f"r{i}",
            ))

        with flask_app.test_client() as client:
            resp = client.post("/api/proposals/bulk-reject", json={"ids": pids, "reason": "bulk test"})
            assert resp.status_code == 200
            for pid in pids:
                assert ps.get_proposal(pid)["status"] == "rejected"

    def test_approve_already_decided_fails(self, flask_app):
        """Can't approve an already-decided proposal."""
        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=flask_app.config["DB_PATH"])
        pid = ps.create_proposal(
            business_slug="testbiz", target_module="voice-profile",
            target_section="s1", proposal_type="add",
            evidence=["e1"], change_description="d1",
            exact_diff="diff1", rationale="r1",
        )
        ps.approve_proposal(pid)

        with flask_app.test_client() as client:
            resp = client.post(f"/api/proposals/{pid}/approve", json={})
            assert resp.status_code == 400

    def test_proposal_not_found(self, flask_app):
        """404 for non-existent proposal."""
        with flask_app.test_client() as client:
            resp = client.post("/api/proposals/99999/approve", json={})
            assert resp.status_code == 404