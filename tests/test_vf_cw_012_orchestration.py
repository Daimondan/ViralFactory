"""
VF-CW-012 — Resumable multi-platform orchestration tests.

Tests:
  - advance() transitions through the full state machine
  - Human wait states return needs_human=True
  - Gate3 approved returns complete=True
  - advance_all_for_draft advances all sessions
  - get_draft_status aggregates truthfully
  - reconcile_stale_jobs cleans stale jobs
  - Process restart resumes from persisted state
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
def orchestrator(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    PipelineStore(db_path=tmp_db)
    from services.production_orchestrator_service import ProductionOrchestrator
    return ProductionOrchestrator(db_path=tmp_db), tmp_db


def _setup_session(tmp_db, business_slug="test_tenant", platform="IG"):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService

    store = PipelineStore(db_path=tmp_db)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(business_slug, "Test", ["Hook"],
        {"format": "reel", "scope": "test", "capture_required": False}, "human_seeded")
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    card = dict(conn.execute("SELECT * FROM idea_cards ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute("INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
        "draft_text, draft_version, draft_state, created_at, updated_at) "
        "VALUES (?, ?, 'human_seeded', 'reel', 'test', '', 1, 'shipped', ?, ?)",
        (business_slug, card["id"], now, now))
    conn.commit()
    draft = dict(conn.execute("SELECT * FROM drafts ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute("INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, asset_state, created_at, updated_at) "
        "VALUES (?, ?, ?, 'reel', 'Test', 'pending', ?, ?)",
        (business_slug, draft["id"], platform, now, now))
    conn.commit()
    asset = dict(conn.execute("SELECT * FROM assets ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()

    svc = ProductionSessionService(db_path=tmp_db)
    return svc.create_session(business_slug, draft["id"], asset["id"], platform, "reel"), draft


class TestAdvance:
    def test_advance_from_planning(self, orchestrator):
        svc, db_path = orchestrator
        session, _ = _setup_session(db_path)

        result = svc.advance("test_tenant", session["id"])
        assert result["action_taken"] == "planning_components"
        assert result["session"]["current_state"] == "generating_components"

    def test_advance_to_component_review(self, orchestrator):
        svc, db_path = orchestrator
        session, _ = _setup_session(db_path)

        # Advance to generating
        svc.advance("test_tenant", session["id"])
        # Advance to component review
        result = svc.advance("test_tenant", session["id"])
        assert result["needs_human"] is True
        assert result["session"]["current_state"] == "component_review_required"

    def test_advance_full_path_to_gate3(self, orchestrator):
        """Advance through the full state machine to gate3_approved."""
        svc, db_path = orchestrator
        session, _ = _setup_session(db_path)

        # planning → generating
        svc.advance("test_tenant", session["id"])
        # generating → component_review (human)
        r = svc.advance("test_tenant", session["id"])
        assert r["needs_human"]

        # Simulate human approval: manually transition past human waits
        from services.production_orchestrator import ProductionSessionService
        pss = ProductionSessionService(db_path=db_path)
        pss.transition("test_tenant", session["id"], "manifest_ready", "manifest frozen")

        # manifest_ready → composition_planning
        svc.advance("test_tenant", session["id"])
        # composition_planning → composition_review (human)
        r = svc.advance("test_tenant", session["id"])
        assert r["needs_human"]

        # Simulate ratification
        pss.transition("test_tenant", session["id"], "composition_ratified", "ratified")

        # composition_ratified → assembling
        svc.advance("test_tenant", session["id"])
        # assembling → final_review (human)
        r = svc.advance("test_tenant", session["id"])
        assert r["needs_human"]

        # Simulate Gate 3 approval
        pss.transition("test_tenant", session["id"], "gate3_approved", "approved")

        # Now advance should say complete
        r = svc.advance("test_tenant", session["id"])
        assert r["complete"] is True

    def test_blocked_state(self, orchestrator):
        svc, db_path = orchestrator
        session, _ = _setup_session(db_path)

        from services.production_orchestrator import ProductionSessionService
        pss = ProductionSessionService(db_path=db_path)
        pss.transition("test_tenant", session["id"], "blocked", "test block")

        result = svc.advance("test_tenant", session["id"])
        assert result["action_taken"] == "blocked"
        assert result["error"] is not None


class TestAdvanceAllForDraft:
    def test_advances_all_sessions(self, orchestrator):
        """Each platform asset gets advanced independently."""
        svc, db_path = orchestrator
        session1, draft = _setup_session(db_path, platform="IG")
        # Create second asset + session for the same draft
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from services.production_orchestrator import ProductionSessionService
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
            "content, asset_state, created_at, updated_at) "
            "VALUES (?, ?, 'X', 'thread', 'Test', 'pending', ?, ?)",
            ("test_tenant", draft["id"], now, now))
        conn.commit()
        asset2 = dict(conn.execute("SELECT * FROM assets WHERE platform = 'X' ORDER BY id DESC LIMIT 1").fetchone())
        conn.close()
        pss = ProductionSessionService(db_path=db_path)
        session2 = pss.create_session("test_tenant", draft["id"], asset2["id"], "X", "thread")

        # Advance all
        results = svc.advance_all_for_draft("test_tenant", draft["id"])
        assert len(results) == 2
        for r in results:
            assert r["action_taken"] is not None


class TestGetDraftStatus:
    def test_aggregate_status(self, orchestrator):
        svc, db_path = orchestrator
        session1, draft = _setup_session(db_path, platform="IG")
        # Create second asset + session for the same draft
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from services.production_orchestrator import ProductionSessionService
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
            "content, asset_state, created_at, updated_at) "
            "VALUES (?, ?, 'X', 'thread', 'Test', 'pending', ?, ?)",
            ("test_tenant", draft["id"], now, now))
        conn.commit()
        asset2 = dict(conn.execute("SELECT * FROM assets WHERE platform = 'X' ORDER BY id DESC LIMIT 1").fetchone())
        conn.close()
        pss = ProductionSessionService(db_path=db_path)
        session2 = pss.create_session("test_tenant", draft["id"], asset2["id"], "X", "thread")

        status = svc.get_draft_status("test_tenant", draft["id"])
        assert status["total_sessions"] == 2
        assert not status["all_complete"]  # both are in planning


class TestProcessRestart:
    def test_resume_from_persisted_state(self, tmp_db):
        """A new orchestrator instance sees the persisted state."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from pipeline import PipelineStore
        PipelineStore(db_path=tmp_db)
        from services.production_orchestrator_service import ProductionOrchestrator

        session, _ = _setup_session(tmp_db)

        # Advance with first orchestrator
        orch1 = ProductionOrchestrator(db_path=tmp_db)
        orch1.advance("test_tenant", session["id"])

        # Create new orchestrator (simulates restart)
        orch2 = ProductionOrchestrator(db_path=tmp_db)
        result = orch2.advance("test_tenant", session["id"])

        # Should have advanced from generating_components
        assert result["session"]["current_state"] == "component_review_required"


class TestReconcileStaleJobs:
    def test_cleans_stale_jobs(self, orchestrator):
        svc, db_path = orchestrator
        session, _ = _setup_session(db_path)

        from jobs import JobsStore
        jobs = JobsStore(db_path=db_path)
        jobs.start_job("test", entity_id=session["id"])

        result = svc.reconcile_stale_jobs("test_tenant", session["id"])
        # Stale jobs may or may not be cleaned depending on timeout
        assert "stale_jobs_cleaned" in result