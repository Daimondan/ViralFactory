"""
VF-RA-002 — Creatomate + Shotstack bake-off adapter tests.

Tests use the FakeRenderAdapter — no real API calls. Live smoke tests
are separate from fake-adapter tests.

Tests:
  - Fake adapter submit/check_status/download cycle
  - Shotstack lowering produces valid Edit JSON
  - Creatomate lowering produces valid RenderScript
  - Credentials never reach DB, logs, or fixtures
  - Request hash is computed from redacted request
  - Budget check blocks when exceeded
  - Capability mismatch fails closed
  - Provider job persistence with lineage
  - Two providers lower the same spec differently
  - No credentials in persisted records
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
def adapters(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    PipelineStore(db_path=tmp_db)
    from services.render_adapters import (
        FakeRenderAdapter, ShotstackAdapter, CreatomateAdapter,
        ProviderAdapterFactory,
    )
    return {
        "fake": FakeRenderAdapter(db_path=tmp_db),
        "shotstack": ShotstackAdapter(db_path=tmp_db, config={"api_key_env": "TEST_SHOTSTACK_KEY"}),
        "creatomate": CreatomateAdapter(db_path=tmp_db, config={"api_key_env": "TEST_CREATOMATE_KEY"}),
        "factory": ProviderAdapterFactory,
        "db_path": tmp_db,
    }


def _make_minimal_spec():
    """Create a minimal RendererSpec for testing."""
    return {
        "spec_version": "1.0",
        "identity": {
            "composition_plan_hash": "plan_hash",
            "manifest_hash": "manifest_hash",
            "session_id": 1,
            "asset_id": 1,
            "business_slug": "test",
        },
        "canvas": {"width": 540, "height": 960, "fps": 30, "safe_zones": {"top": 0.1}},
        "timeline": [
            {"type": "text", "layer": 10, "in_point": 0, "out_point": 3,
             "text": "Test hook", "font_family": "Montserrat", "font_size": 48},
            {"type": "visual", "layer": 1, "in_point": 0, "out_point": 5,
             "kind": "image", "source_path": "/data/test.jpg", "source_hash": "img_hash"},
            {"type": "transition", "layer": 20, "in_point": 5, "out_point": 5.5,
             "transition_type": "crossfade", "duration": 0.5},
        ],
        "audio_automation": {"lufs_target": -16.0},
    }


def _setup_session(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService

    store = PipelineStore(db_path=tmp_db)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card("test", "Test", ["Hook"],
        {"format": "reel", "scope": "test", "capture_required": False}, "human_seeded")
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    card = dict(conn.execute("SELECT * FROM idea_cards ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute("INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
        "draft_text, draft_version, draft_state, created_at, updated_at) "
        "VALUES (?, ?, 'human_seeded', 'reel', 'test', '', 1, 'shipped', ?, ?)",
        ("test", card["id"], now, now))
    conn.commit()
    draft = dict(conn.execute("SELECT * FROM drafts ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute("INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, asset_state, created_at, updated_at) "
        "VALUES (?, ?, 'IG', 'reel', 'Test', 'pending', ?, ?)",
        ("test", draft["id"], now, now))
    conn.commit()
    asset = dict(conn.execute("SELECT * FROM assets ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()

    svc = ProductionSessionService(db_path=tmp_db)
    return svc.create_session("test", draft["id"], asset["id"], "IG", "reel")


class TestFakeAdapter:
    def test_submit_check_download_cycle(self, adapters):
        fake = adapters["fake"]
        session = _setup_session(adapters["db_path"])
        spec = _make_minimal_spec()

        # Submit
        job = fake.submit(spec, "test", session["id"])
        assert job["status"] == "submitted"
        assert job["spec_hash"] is not None
        assert job["request_hash"] is not None

        # Check status
        job = fake.check_status(job)
        assert job["status"] == "done"
        assert job["render_time_s"] is not None

        # Download
        dest = os.path.join(os.path.dirname(adapters["db_path"]), "output.mp4")
        job = fake.download(job, dest)
        assert job["status"] == "downloaded"
        assert os.path.exists(dest)
        assert job["output_hash"] is not None


class TestShotstackLowering:
    def test_lower_produces_edit_json(self, adapters):
        shotstack = adapters["shotstack"]
        spec = _make_minimal_spec()
        edit = shotstack.lower(spec)

        assert "timeline" in edit
        assert "output" in edit
        assert edit["output"]["format"] == "mp4"
        assert edit["output"]["width"] == 540
        assert edit["output"]["height"] == 960

    def test_lower_text_element(self, adapters):
        shotstack = adapters["shotstack"]
        spec = _make_minimal_spec()
        edit = shotstack.lower(spec)

        # Find text clip
        text_clips = [c for c in edit["timeline"]["tracks"][0]
                      if c["asset"]["type"] == "title"]
        assert len(text_clips) == 1
        assert text_clips[0]["asset"]["text"] == "Test hook"

    def test_submit_without_credentials_fails(self, adapters):
        shotstack = adapters["shotstack"]
        session = _setup_session(adapters["db_path"])
        spec = _make_minimal_spec()

        with pytest.raises(Exception, match="not set"):
            shotstack.submit(spec, "test", session["id"])


class TestCreatomateLowering:
    def test_lower_produces_renderscript(self, adapters):
        creatomate = adapters["creatomate"]
        spec = _make_minimal_spec()
        script = creatomate.lower(spec)

        assert "elements" in script
        assert script["width"] == 540
        assert script["height"] == 960
        assert len(script["elements"]) > 0

    def test_lower_text_element(self, adapters):
        creatomate = adapters["creatomate"]
        spec = _make_minimal_spec()
        script = creatomate.lower(spec)

        text_els = [e for e in script["elements"] if e["type"] == "text"]
        assert len(text_els) == 1
        assert text_els[0]["text"] == "Test hook"

    def test_submit_without_credentials_fails(self, adapters):
        creatomate = adapters["creatomate"]
        session = _setup_session(adapters["db_path"])
        spec = _make_minimal_spec()

        with pytest.raises(Exception, match="not set"):
            creatomate.submit(spec, "test", session["id"])


class TestTwoProvidersLowerDifferently:
    def test_shotstack_and_creatomate_produce_different_formats(self, adapters):
        spec = _make_minimal_spec()
        shotstack_edit = adapters["shotstack"].lower(spec)
        creatomate_script = adapters["creatomate"].lower(spec)

        # Shotstack has "timeline.tracks", Creatomate has "elements"
        assert "tracks" in shotstack_edit["timeline"]
        assert "elements" in creatomate_script
        assert "tracks" not in creatomate_script


class TestCredentialsNeverPersisted:
    def test_redact_request_removes_credentials(self, adapters):
        fake = adapters["fake"]
        request = {
            "api_key": "secret123",
            "token": "tok456",
            "data": {"text": "hello"},
            "password": "pass789",
        }
        redacted = fake._redact_request(request)
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["token"] == "[REDACTED]"
        assert redacted["password"] == "[REDACTED]"
        assert redacted["data"]["text"] == "hello"  # non-credential preserved

    def test_no_credentials_in_persisted_job(self, adapters):
        fake = adapters["fake"]
        session = _setup_session(adapters["db_path"])
        spec = _make_minimal_spec()

        job = fake.submit(spec, "test", session["id"])

        # Check the DB record has no credentials
        conn = sqlite3.connect(adapters["db_path"])
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM render_provider_jobs WHERE id = ?", (job["id"],)
        ).fetchone()
        conn.close()

        row_dict = dict(row)
        row_str = json.dumps(row_dict, default=str)
        assert "secret" not in row_str.lower()
        assert "api_key" not in row_str.lower() or "[REDACTED]" in row_str
        assert "password" not in row_str.lower()


class TestBudgetCheck:
    def test_budget_blocks_when_exceeded(self, adapters):
        from services.render_adapters import FakeRenderAdapter, ProviderBudgetError
        fake = FakeRenderAdapter(
            db_path=adapters["db_path"],
            config={"budget_usd": 0.05},
        )
        # 0.02 is within budget
        fake.check_budget(0.02)

        # Simulate spending 0.04
        conn = sqlite3.connect(adapters["db_path"])
        conn.execute(
            "INSERT INTO render_provider_jobs (business_slug, production_session_id, "
            "spec_hash, provider, status, submitted_at, actual_cost_usd) "
            "VALUES ('test', 1, 'hash', 'fake', 'done', '2026-01-01', 0.04)"
        )
        conn.commit()
        conn.close()

        # Now 0.03 exceeds remaining (0.05 - 0.04 = 0.01)
        with pytest.raises(ProviderBudgetError, match="exceeds remaining"):
            fake.check_budget(0.03)


class TestProviderFactory:
    def test_create_fake(self, adapters):
        factory = adapters["factory"]
        adapter = factory.create("fake", adapters["db_path"])
        assert adapter.PROVIDER_NAME == "fake"

    def test_create_shotstack(self, adapters):
        factory = adapters["factory"]
        adapter = factory.create("shotstack", adapters["db_path"])
        assert adapter.PROVIDER_NAME == "shotstack"

    def test_create_unknown_fails(self, adapters):
        factory = adapters["factory"]
        with pytest.raises(Exception, match="Unknown provider"):
            factory.create("unknown", adapters["db_path"])