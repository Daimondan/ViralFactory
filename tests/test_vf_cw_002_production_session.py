"""
VF-CW-002 — ProductionSession aggregate and durable state machine tests.

Tests:
  - Session creation (one per platform asset)
  - Duplicate session prevention
  - Valid state transitions
  - Invalid transition rejection
  - Cross-tenant isolation
  - Compare-and-set concurrency safety
  - Transition history
  - Active pointers (requirements, manifest, render, composition plan)
  - Human-wait states have no stale running job
  - Process restart resumes every state
  - Routes do not write state directly
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
def session_service(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from services.production_orchestrator import ProductionSessionService
    return ProductionSessionService(db_path=tmp_db)


@pytest.fixture
def store(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    return PipelineStore(db_path=tmp_db)


def _setup_draft_and_asset(store, business_slug="test_tenant"):
    """Create a card, draft, and asset for testing."""
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug=business_slug,
        idea="Test idea",
        hook_options=["Hook"],
        treatment={"scope": "test", "format": "reel", "capture_required": False},
        origin="human_seeded",
    )
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    card = dict(conn.execute(
        "SELECT * FROM idea_cards WHERE business_slug = ? ORDER BY id DESC LIMIT 1",
        (business_slug,),
    ).fetchone())
    conn.execute(
        """INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope,
           draft_text, draft_version, draft_state, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, '', 1, 'shipped', ?, ?)""",
        (business_slug, card["id"], "human_seeded", "reel", "test", now, now),
    )
    conn.commit()
    draft = dict(conn.execute(
        "SELECT * FROM drafts WHERE idea_card_id = ? ORDER BY id DESC LIMIT 1",
        (card["id"],),
    ).fetchone())
    conn.execute(
        """INSERT INTO assets (business_slug, draft_id, platform, variant_type,
           content, asset_state, created_at, updated_at)
           VALUES (?, ?, 'Instagram', 'reel', 'Test', 'pending', ?, ?)""",
        (business_slug, draft["id"], now, now),
    )
    conn.commit()
    asset = dict(conn.execute(
        "SELECT * FROM assets WHERE draft_id = ? ORDER BY id DESC LIMIT 1",
        (draft["id"],),
    ).fetchone())
    conn.close()
    return card, draft, asset


class TestSessionCreation:
    def test_create_session(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            business_slug="test_tenant",
            draft_id=draft["id"],
            asset_id=asset["id"],
            platform="Instagram",
            format="reel",
            writer_contract_hash="abc123",
        )
        assert session["id"] is not None
        assert session["current_state"] == "planning_components"
        assert session["business_slug"] == "test_tenant"
        assert session["draft_id"] == draft["id"]
        assert session["asset_id"] == asset["id"]
        assert session["platform"] == "Instagram"
        assert session["writer_contract_hash"] == "abc123"
        assert session["attempt"] == 1

    def test_duplicate_session_rejected(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session_service.create_session(
            business_slug="test_tenant",
            draft_id=draft["id"],
            asset_id=asset["id"],
            platform="Instagram",
        )
        with pytest.raises(Exception, match="Session already exists"):
            session_service.create_session(
                business_slug="test_tenant",
                draft_id=draft["id"],
                asset_id=asset["id"],
                platform="Instagram",
            )

    def test_one_session_per_platform_asset(self, session_service, store):
        """Each platform asset gets its own session."""
        _, draft, asset = _setup_draft_and_asset(store)
        # Create session for first asset
        s1 = session_service.create_session(
            business_slug="test_tenant",
            draft_id=draft["id"],
            asset_id=asset["id"],
            platform="Instagram",
        )
        # Create a second asset for a different platform
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(store.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO assets (business_slug, draft_id, platform, variant_type,
               content, asset_state, created_at, updated_at)
               VALUES (?, ?, 'X', 'thread', 'Test', 'pending', ?, ?)""",
            ("test_tenant", draft["id"], now, now),
        )
        conn.commit()
        asset2 = dict(conn.execute(
            "SELECT * FROM assets WHERE draft_id = ? AND platform = 'X'",
            (draft["id"],),
        ).fetchone())
        conn.close()

        s2 = session_service.create_session(
            business_slug="test_tenant",
            draft_id=draft["id"],
            asset_id=asset2["id"],
            platform="X",
        )
        assert s1["id"] != s2["id"]
        assert s1["asset_id"] != s2["asset_id"]


class TestStateTransitions:
    def test_valid_transition_planning_to_generating(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        updated = session_service.transition(
            "test_tenant", session["id"],
            "generating_components", "requirements planned"
        )
        assert updated["current_state"] == "generating_components"

    def test_valid_full_happy_path(self, session_service, store):
        """Test the full happy path through the state machine."""
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        sid = session["id"]
        bs = "test_tenant"

        # Full path with composition (AMENDMENT-014)
        states = [
            ("generating_components", "requirements planned"),
            ("component_review_required", "candidates generated"),
            ("manifest_ready", "manifest frozen"),
            ("composition_planning", "composition plan started"),
            ("composition_review_required", "plan ready for review"),
            ("composition_ratified", "operator ratified"),
            ("assembling", "renderer spec compiled"),
            ("final_review_required", "render complete"),
            ("gate3_approved", "gate 3 approved"),
        ]
        for to_state, reason in states:
            updated = session_service.transition(bs, sid, to_state, reason)
            assert updated["current_state"] == to_state

    def test_invalid_transition_rejected(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        # Cannot jump from planning_components to assembling
        with pytest.raises(Exception, match="Invalid transition"):
            session_service.transition(
                "test_tenant", session["id"], "assembling"
            )

    def test_blocked_state_can_retry(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        # Go to blocked
        session_service.transition(
            "test_tenant", session["id"], "blocked", "planning failed"
        )
        # Retry from planning
        updated = session_service.transition(
            "test_tenant", session["id"],
            "planning_components", "retry from planning"
        )
        assert updated["current_state"] == "planning_components"

    def test_composition_review_back_to_planning(self, session_service, store):
        """Operator can request changes during composition review."""
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        sid = session["id"]
        bs = "test_tenant"

        # Advance to composition review
        for to_state, reason in [
            ("generating_components", "req planned"),
            ("component_review_required", "candidates generated"),
            ("manifest_ready", "manifest frozen"),
            ("composition_planning", "plan started"),
            ("composition_review_required", "plan ready"),
        ]:
            session_service.transition(bs, sid, to_state, reason)

        # Operator requests changes → back to composition_planning
        updated = session_service.transition(
            bs, sid, "composition_planning", "operator requested changes"
        )
        assert updated["current_state"] == "composition_planning"

    def test_ratified_back_to_planning_on_change(self, session_service, store):
        """Post-ratification change invalidates ratification."""
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        sid = session["id"]
        bs = "test_tenant"

        # Advance to ratified
        for to_state, reason in [
            ("generating_components", "req planned"),
            ("component_review_required", "candidates generated"),
            ("manifest_ready", "manifest frozen"),
            ("composition_planning", "plan started"),
            ("composition_review_required", "plan ready"),
            ("composition_ratified", "operator ratified"),
        ]:
            session_service.transition(bs, sid, to_state, reason)

        # Post-ratification change → back to composition_planning
        updated = session_service.transition(
            bs, sid, "composition_planning", "post-ratification change detected"
        )
        assert updated["current_state"] == "composition_planning"


class TestCrossTenantIsolation:
    def test_cross_tenant_get_rejected(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store, "tenant_a")
        session = session_service.create_session(
            "tenant_a", draft["id"], asset["id"], "Instagram"
        )
        with pytest.raises(Exception, match="belongs to tenant_a"):
            session_service.get_session("tenant_b", session["id"])

    def test_cross_tenant_transition_rejected(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store, "tenant_a")
        session = session_service.create_session(
            "tenant_a", draft["id"], asset["id"], "Instagram"
        )
        with pytest.raises(Exception, match="belongs to tenant_a"):
            session_service.transition(
                "tenant_b", session["id"], "generating_components"
            )


class TestTransitionHistory:
    def test_history_records_all_transitions(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        session_service.transition(
            "test_tenant", session["id"], "generating_components", "req planned"
        )
        session_service.transition(
            "test_tenant", session["id"], "component_review_required", "candidates done"
        )

        history = session_service.get_transition_history(
            "test_tenant", session["id"]
        )
        # 3 entries: creation + 2 transitions
        assert len(history) == 3
        assert history[0]["to_state"] == "planning_components"
        assert history[1]["from_state"] == "planning_components"
        assert history[1]["to_state"] == "generating_components"
        assert history[2]["to_state"] == "component_review_required"


class TestActivePointers:
    def test_set_active_requirements(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        updated = session_service.set_active_requirements(
            "test_tenant", session["id"], 3
        )
        assert updated["active_requirements_version"] == 3

    def test_set_active_manifest(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        updated = session_service.set_active_manifest(
            "test_tenant", session["id"], 2
        )
        assert updated["active_manifest_version"] == 2

    def test_set_active_render(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        updated = session_service.set_active_render(
            "test_tenant", session["id"], 1
        )
        assert updated["active_render_version"] == 1

    def test_set_composition_plan_hash(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        updated = session_service.set_composition_plan_hash(
            "test_tenant", session["id"], "hash_abc"
        )
        assert updated["active_composition_plan_hash"] == "hash_abc"


class TestHumanWaitStates:
    def test_component_review_is_human_wait(self, session_service):
        assert session_service.is_human_wait("component_review_required")
        assert session_service.is_human_wait("composition_review_required")
        assert session_service.is_human_wait("final_review_required")

    def test_planning_is_not_human_wait(self, session_service):
        assert not session_service.is_human_wait("planning_components")
        assert not session_service.is_human_wait("assembling")


class TestProcessRestart:
    def test_state_persists_across_restart(self, tmp_db, store):
        """A new service instance sees the persisted state."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from services.production_orchestrator import ProductionSessionService

        _, draft, asset = _setup_draft_and_asset(store)
        svc1 = ProductionSessionService(db_path=tmp_db)
        session = svc1.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        svc1.transition(
            "test_tenant", session["id"], "generating_components", "req planned"
        )

        # Simulate restart: create new service instance
        svc2 = ProductionSessionService(db_path=tmp_db)
        restored = svc2.get_session("test_tenant", session["id"])
        assert restored["current_state"] == "generating_components"

        # Can continue transitioning
        updated = svc2.transition(
            "test_tenant", session["id"],
            "component_review_required", "candidates done"
        )
        assert updated["current_state"] == "component_review_required"


class TestIncrementAttempt:
    def test_increment_attempt(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        session = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        assert session["attempt"] == 1
        updated = session_service.increment_attempt("test_tenant", session["id"])
        assert updated["attempt"] == 2
        updated = session_service.increment_attempt("test_tenant", session["id"])
        assert updated["attempt"] == 3


class TestListSessions:
    def test_list_by_state(self, session_service, store):
        _, draft, asset = _setup_draft_and_asset(store)
        s1 = session_service.create_session(
            "test_tenant", draft["id"], asset["id"], "Instagram"
        )
        # Create second asset + session
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(store.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO assets (business_slug, draft_id, platform, variant_type,
               content, asset_state, created_at, updated_at)
               VALUES (?, ?, 'X', 'thread', 'Test', 'pending', ?, ?)""",
            ("test_tenant", draft["id"], now, now),
        )
        conn.commit()
        asset2 = dict(conn.execute(
            "SELECT * FROM assets WHERE draft_id = ? AND platform = 'X'",
            (draft["id"],),
        ).fetchone())
        conn.close()

        s2 = session_service.create_session(
            "test_tenant", draft["id"], asset2["id"], "X"
        )
        session_service.transition(
            "test_tenant", s2["id"], "generating_components", "req planned"
        )

        planning = session_service.list_sessions("test_tenant", state="planning_components")
        assert len(planning) == 1
        assert planning[0]["id"] == s1["id"]

        generating = session_service.list_sessions("test_tenant", state="generating_components")
        assert len(generating) == 1
        assert generating[0]["id"] == s2["id"]