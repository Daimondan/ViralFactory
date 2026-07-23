"""
VF-CW-001 — Behavioral baseline + correlated runtime evidence.

These are sanitized RED fixtures that demonstrate the observed production
defects at their current boundaries. They use no personal content or
credentials. Each fixture calls the current shared boundaries and fails
for the documented reason.

After VF-CW-002..010 are implemented, these tests should turn GREEN —
the defects they expose will be fixed by the production session state
machine, immutable candidates, manifest freeze, and hardened Gate 3.

Defects covered:
  1. Stuck soundtrack wait — no durable continuation after human pause
  2. Done job / missing artifact mismatch
  3. Missing VO / manual-only recovery
  4. First-child multi-platform selection (get_asset_by_draft)
  5. Direct Gate 3 bypass (API approves without final artifact)
  6. Ambiguous newest edit plan (no explicit active pointer)

Correlation IDs:
  7. Jobs table carries business_slug, draft_id, asset_id, state, attempt, upstream hash
  8. Production step data carries session correlation
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ── Test fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def tmp_db():
    """Create a fresh temporary database for each test."""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_vf.db")
    yield db_path
    # cleanup
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def store(tmp_db):
    """PipelineStore with a fresh temp DB."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    return PipelineStore(db_path=tmp_db)


@pytest.fixture
def jobs_store(tmp_db):
    """JobsStore with the same temp DB."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from jobs import JobsStore
    return JobsStore(db_path=tmp_db)


def _make_approved_card(store, business_slug="test_tenant"):
    """Create an approved idea card for testing."""
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug=business_slug,
        idea="Test idea for baseline fixtures",
        hook_options=["Test hook"],
        treatment={"scope": "test", "format": "reel", "capture_required": False},
        origin="human_seeded",
    )
    # Get the card we just created
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM idea_cards WHERE business_slug = ? ORDER BY id DESC LIMIT 1",
        (business_slug,),
    ).fetchone()
    conn.close()
    return dict(row)


def _make_draft(store, card, business_slug="test_tenant"):
    """Create a shipped draft for testing."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """INSERT INTO drafts
           (business_slug, idea_card_id, origin, format, scope, draft_text,
            platform_content, draft_version, draft_state, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (business_slug, card["id"], card["origin"], "reel", "test",
         "Test draft text",
         json.dumps([{"platform": "Instagram", "variant_type": "reel",
                       "content": "Test content", "posts": [{"frame": 1, "text": "Test", "vo_text": "Test VO"}],
                       "image_prompts": []}]),
         1, "shipped", now, now),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM drafts WHERE idea_card_id = ? ORDER BY id DESC LIMIT 1",
        (card["id"],),
    ).fetchone()
    conn.close()
    return dict(row)


def _make_assets(store, draft, count=2, business_slug="test_tenant"):
    """Create N assets under a draft (for multi-platform testing)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(store.db_path)
    conn.row_factory = sqlite3.Row
    platforms = ["Instagram", "X"]
    assets = []
    for i in range(count):
        platform = platforms[i % len(platforms)]
        conn.execute(
            """INSERT INTO assets
               (business_slug, draft_id, platform, variant_type, content, posts,
                asset_state, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (business_slug, draft["id"], platform, "reel",
             "Test content", json.dumps([{"frame": 1, "text": "Test", "vo_text": "Test VO"}]),
             "pending", now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM assets WHERE draft_id = ? ORDER BY id DESC LIMIT 1",
            (draft["id"],),
        ).fetchone()
        assets.append(dict(row))
    conn.close()
    return assets


# ── 1. Stuck soundtrack wait — no durable continuation ──────────────────


class TestStuckSoundtrackWait:
    """RED: Card stays at awaiting_soundtrack_approval with no resume mechanism.

    The approval route records a decision but does not resume the autonomous
    chain or reconcile card state. There is no production session state
    machine to advance.
    """

    def test_soundtrack_approval_does_not_resume_chain(self, store):
        """After soundtrack approval, there is no service to advance the session.

        This is a RED test: it demonstrates that the current code has no
        ProductionOrchestrator or resume mechanism. When VF-CW-002 adds the
        state machine, this test will flip to GREEN by calling the resume
        service and verifying state advancement.
        """
        card = _make_approved_card(store)
        draft = _make_draft(store, card)
        assets = _make_assets(store, draft, count=1)

        # Set card to awaiting_soundtrack_approval (the stuck state)
        store.update_card_state(card["id"], "awaiting_soundtrack_approval")

        # Verify there is no production session or resume service
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        # VF-CW-002 will add ProductionOrchestrator — it does not exist yet
        try:
            from services.production_orchestrator import ProductionOrchestrator
            has_orchestrator = True
        except ImportError:
            has_orchestrator = False

        # Also check for production_sessions table
        conn = sqlite3.connect(store.db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()
        has_sessions_table = "production_sessions" in tables

        # RED: Neither the orchestrator service nor the sessions table exists
        assert not has_orchestrator, (
            "ProductionOrchestrator exists — VF-CW-002 may be partially implemented. "
            "Update this test to call it and verify resume."
        )
        assert not has_sessions_table, (
            "production_sessions table exists — VF-CW-002 may be partially implemented. "
            "Update this test to verify state machine advancement."
        )

    def test_human_wait_has_stale_running_job(self, store, jobs_store):
        """When the chain pauses for soundtrack approval, the job stays 'running'.

        A human wait should not have a stale running job. VF-CW-002 will
        make human waits persisted states, not long-running jobs.
        """
        card = _make_approved_card(store)
        draft = _make_draft(store, card)

        # Simulate what produce_chain does: start a job, then pause
        result = jobs_store.start_job("assembly_render", draft["id"])
        job_id = result["job_id"]

        # The chain "returns" (pauses) but the job is still running
        job = jobs_store.get_job(job_id)
        assert job["status"] == "running", "Job should be running during the pause"

        # RED: There is no production session state machine to transition
        # to a human-wait state. The job stays running until a stale
        # timeout kills it. VF-CW-002 will add ProductionOrchestrator
        # that transitions to component_review_required instead.
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        try:
            from services.production_orchestrator import ProductionOrchestrator
            has_orchestrator = True
        except ImportError:
            has_orchestrator = False

        assert not has_orchestrator, (
            "ProductionOrchestrator exists — VF-CW-002 may be partially implemented. "
            "Update this test to verify state machine advancement."
        )


# ── 2. Done job / missing artifact mismatch ────────────────────────────


class TestDoneJobMissingArtifact:
    """RED: A job can be marked 'done' while no final artifact exists."""

    def test_done_job_without_final_artifact(self, store, jobs_store):
        """A job marked done does not guarantee a downstream artifact exists.

        The job table tracks job status, not production completeness.
        VF-CW-002 will add a production session that tracks the real state.
        """
        card = _make_approved_card(store)
        draft = _make_draft(store, card)
        assets = _make_assets(store, draft, count=1)

        # Mark a job as done (as _step_media_exec does)
        result = jobs_store.start_job("media_plan", draft["id"])
        job_id = result["job_id"]
        jobs_store.complete_job(job_id, json.dumps({"status": "ok"}))

        job = jobs_store.get_job(job_id)
        assert job["status"] == "done"

        # But the asset has no final artifact — check that no edit plans exist
        # The edit_plans table is created lazily, so create it first
        conn = sqlite3.connect(store.db_path)
        conn.executescript(store.EDIT_PLAN_SCHEMA)
        plans = conn.execute(
            "SELECT * FROM edit_plans WHERE asset_id = ?", (assets[0]["id"],)
        ).fetchall()
        conn.close()
        assert len(plans) == 0, "No edit plans should exist for this asset"

        # RED: The job is "done" but there is no artifact. There is no
        # invariant that prevents calling this production-success.
        # VF-CW-002's state machine will require downstream artifacts before
        # advancing past assembling.


# ── 3. Missing VO / manual-only recovery ────────────────────────────────


class TestMissingVOManualRecovery:
    """RED: A reel asset with no VO has no automated recovery path."""

    def test_reel_without_vo_has_no_recovery(self, store):
        """A reel asset with spoken beats but no VO segments cannot recover
        through the autonomous chain. Only manual route endpoints can fix it.

        VF-CW-005 will register VO takes as candidates with status tracking.
        """
        card = _make_approved_card(store)
        draft = _make_draft(store, card)
        assets = _make_assets(store, draft, count=1)

        # Asset has no VO segments
        vo_segments = store.get_vo_segments(assets[0]["id"])
        assert vo_segments is None or len(vo_segments) == 0

        # RED: The produce_chain does not have a candidate-based recovery.
        # It generates one take and if that fails, the chain fails.
        # VF-CW-005 will produce multiple candidate takes.
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        try:
            from services.component_workbench import ComponentWorkbenchService
            has_workbench = True
        except ImportError:
            has_workbench = False

        assert not has_workbench, (
            "ComponentWorkbenchService exists — VF-CW-005 may be partially implemented."
        )


# ── 4. First-child multi-platform selection ─────────────────────────────


class TestFirstChildMultiPlatform:
    """RED: get_asset_by_draft returns only the first asset, breaking
    multi-platform production."""

    def test_get_asset_by_draft_returns_first_only(self, store):
        """When a draft has multiple platform assets, get_asset_by_draft
        returns only the first one. The autonomous chain then operates on
        that one, ignoring other platform assets.

        VF-CW-012 will create one child session per platform asset.
        """
        card = _make_approved_card(store)
        draft = _make_draft(store, card)
        assets = _make_assets(store, draft, count=2)

        assert len(assets) == 2

        # The chain calls get_asset_by_draft which returns the first
        first = store.get_asset_by_draft(draft["id"])
        assert first["id"] == assets[0]["id"]

        # RED: There is no get_all_assets_for_draft that the chain uses
        # to advance each platform asset independently
        all_assets = store.list_assets(draft["id"])
        assert len(all_assets) == 2

        # But produce_chain._step_media_plan and _step_edit_plan call
        # get_asset_by_draft, not list_assets — so only the first asset
        # gets media/edit plan/render
        # VF-CW-012 will fix this with per-asset sessions


# ── 5. Direct Gate 3 bypass ──────────────────────────────────────────────


class TestDirectGate3Bypass:
    """RED: The Gate 3 API route approves without checking for a final
    artifact, manifest, or evidence."""

    def test_gate3_approves_without_final_artifact(self, store):
        """POST /api/assets/<id>/gate with action=approve writes
        asset_state='approved' without checking for a final artifact,
        manifest hash, or blocking evidence.

        VF-CW-011 will move Gate 3 writes into a shared service that
        requires current final artifact + manifest + evidence.
        """
        card = _make_approved_card(store)
        draft = _make_draft(store, card)
        assets = _make_assets(store, draft, count=1)

        # Simulate the Gate 3 route's direct state write
        # (This is what app.py:6718-6719 does)
        store.update_asset_state(assets[0]["id"], "approved")

        # Verify: asset is now "approved" with NO final artifact
        asset = store.get_asset(assets[0]["id"])
        assert asset["asset_state"] == "approved"

        # RED: There is no final artifact, no manifest, no evidence
        # But the API accepted the approval
        # VF-CW-011 will require:
        #   - current final artifact hash
        #   - current manifest hash
        #   - complete blocking evidence
        #   - human decision
        # before allowing asset_state='approved'
        conn = sqlite3.connect(store.db_path)
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        conn.close()

        # No manifest table exists yet
        assert "assembly_manifests" not in tables, (
            "assembly_manifests table exists — VF-CW-010 may be partially implemented."
        )

    def test_no_gate3_service_exists(self):
        """There is no central Gate 3 service — routes write state directly."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        try:
            from services.gate3_service import Gate3Service
            has_service = True
        except ImportError:
            has_service = False

        assert not has_service, (
            "Gate3Service exists — VF-CW-011 may be partially implemented."
        )


# ── 6. Ambiguous newest edit plan ────────────────────────────────────────


class TestAmbiguousNewestEditPlan:
    """RED: list_edit_plans returns newest first, but there is no explicit
    active plan pointer. Multiple plans can exist and the UI uses index 0."""

    def test_no_active_plan_pointer(self, store):
        """When multiple edit plans exist, there is no explicit active
        version pointer. The UI and chain use list_edit_plans()[0]."""
        card = _make_approved_card(store)
        draft = _make_draft(store, card)
        assets = _make_assets(store, draft, count=1)

        now = datetime.now(timezone.utc).isoformat()

        # Create the edit_plans table and insert two plans
        conn = sqlite3.connect(store.db_path)
        conn.executescript(store.EDIT_PLAN_SCHEMA)
        for i in range(2):
            conn.execute(
                """INSERT INTO edit_plans
                   (draft_id, asset_id, plan_json, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (draft["id"], assets[0]["id"],
                 json.dumps({"version": i, "cuts": []}),
                 "proposed", now, now),
            )
        conn.commit()
        conn.close()

        plans = store.list_edit_plans(assets[0]["id"])
        assert len(plans) == 2

        # RED: plans[0] is "newest" by ID order, but there is no
        # active_plan_id column or explicit version pointer
        conn = sqlite3.connect(store.db_path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(edit_plans)").fetchall()]
        conn.close()

        # No active/current pointer column
        assert "is_active" not in cols and "active" not in str(cols).lower(), (
            "edit_plans has an active pointer — VF-CW-004 may be partially implemented."
        )


# ── 7. Correlation IDs in jobs table ─────────────────────────────────────


class TestJobCorrelationIDs:
    """GREEN: VF-CW-001 adds correlation fields to the jobs table for
    production observability.

    Every production job/step carries business_slug, production_session_id,
    draft_id, asset_id, state, attempt, and upstream_hash.
    """

    def test_jobs_table_has_correlation_columns(self, tmp_db):
        """The jobs table has correlation columns for production observability."""
        from jobs import JobsStore
        js = JobsStore(db_path=tmp_db)

        conn = sqlite3.connect(tmp_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()

        required = ["business_slug", "production_session_id", "draft_id",
                     "asset_id", "state", "attempt", "upstream_hash"]
        for col in required:
            assert col in cols, f"jobs table missing correlation column: {col}"

    def test_start_job_persists_correlation(self, tmp_db):
        """start_job accepts and persists correlation fields."""
        from jobs import JobsStore
        js = JobsStore(db_path=tmp_db)

        result = js.start_job(
            "assembly_render",
            entity_id=42,
            business_slug="test_tenant",
            production_session_id=99,
            draft_id=7,
            asset_id=42,
            state="assembling",
            attempt=2,
            upstream_hash="abc123",
        )
        assert result["status"] == "started"
        job_id = result["job_id"]

        job = js.get_job(job_id)
        assert job["business_slug"] == "test_tenant"
        assert job["production_session_id"] == 99
        assert job["draft_id"] == 7
        assert job["asset_id"] == 42
        assert job["state"] == "assembling"
        assert job["attempt"] == 2
        assert job["upstream_hash"] == "abc123"

    def test_existing_db_migrates_correlation_columns(self, tmp_db):
        """An existing jobs table without correlation columns gets them added."""
        # Create a jobs table without the new columns (simulating an old DB)
        conn = sqlite3.connect(tmp_db)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_key TEXT NOT NULL,
                job_type TEXT NOT NULL,
                entity_id INTEGER,
                status TEXT NOT NULL DEFAULT 'running',
                result_ref TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.execute(
            "INSERT INTO jobs (job_key, job_type, entity_id, status, started_at, created_at) "
            "VALUES ('test|1', 'test', 1, 'done', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()

        # Now initialize JobsStore — it should add the missing columns
        from jobs import JobsStore
        js = JobsStore(db_path=tmp_db)

        conn = sqlite3.connect(tmp_db)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        conn.close()

        assert "business_slug" in cols
        assert "production_session_id" in cols
        assert "upstream_hash" in cols

        # Old data is preserved
        job = js.list_jobs(job_type="test")[0]
        assert job["status"] == "done"


# ── 8. Production step data lacks session correlation ────────────────────


class TestStepDataCorrelation:
    """GREEN: VF-CW-001 adds correlation fields to production_step_data."""

    def test_step_data_has_correlation(self, store):
        """production_step_data has asset_id, session_id, state, attempt,
        and upstream_hash columns for production correlation."""
        conn = sqlite3.connect(store.db_path)
        cols = [r[1] for r in conn.execute(
            "PRAGMA table_info(production_step_data)"
        ).fetchall()]
        conn.close()

        required = ["asset_id", "production_session_id", "state",
                     "attempt", "upstream_hash"]
        for col in required:
            assert col in cols, f"production_step_data missing column: {col}"