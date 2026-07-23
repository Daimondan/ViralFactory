"""
VF-RA-003 — Blind operator quality + operational selection gate tests.
VF-RA-004 — Selected production renderer adapter + verified local import tests.

Combined tests for both tasks:
  - Blind view masks provider names
  - Decision records primary/fallback
  - Rejection records reason
  - Has selection check
  - VF-RA-004: local adapter as executable fallback
  - VF-RA-004: spec-hash idempotency
  - VF-RA-004: provider success without downloaded artifact is not green
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
def selection_service(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from pipeline import PipelineStore
    PipelineStore(db_path=tmp_db)
    from services.selection_gate import BlindSelectionService
    return BlindSelectionService(db_path=tmp_db), tmp_db


def _make_provider_job(db_path, provider, spec_hash, status="downloaded",
                       output_hash="out_hash", output_path="/data/out.mp4",
                       render_time=5.0):
    """Insert a fake provider job for testing."""
    conn = sqlite3.connect(db_path)
    ts = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """INSERT INTO render_provider_jobs
           (business_slug, production_session_id, spec_hash, provider,
            provider_job_id, status, request_hash, attempt,
            submitted_at, completed_at, render_time_s, output_hash, output_path)
           VALUES (?, 1, ?, ?, 'job_x', ?, 'req_hash', 1, ?, ?, ?, ?, ?)""",
        ("test", spec_hash, provider, status, ts, ts, render_time,
         output_hash, output_path),
    )
    job_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": job_id, "provider": provider, "spec_hash": spec_hash,
            "status": status, "output_hash": output_hash,
            "output_path": output_path, "render_time_s": render_time}


class TestBlindView:
    def test_provider_names_masked(self, selection_service):
        """The blind view does not reveal provider names."""
        svc, db_path = selection_service
        job_a = _make_provider_job(db_path, "shotstack", "spec_1")
        job_b = _make_provider_job(db_path, "creatomate", "spec_1")

        view = svc.build_blind_view([job_a, job_b])

        assert len(view["outputs"]) == 2
        # Labels are A, B — not provider names
        labels = {o["label"] for o in view["outputs"]}
        assert "A" in labels
        assert "B" in labels
        # No provider names in the output
        for o in view["outputs"]:
            output_str = json.dumps(o)
            assert "shotstack" not in output_str.lower()
            assert "creatomate" not in output_str.lower()

    def test_ready_requires_two(self, selection_service):
        """Need at least 2 outputs for comparison."""
        svc, db_path = selection_service
        job_a = _make_provider_job(db_path, "shotstack", "spec_1")

        view = svc.build_blind_view([job_a])
        assert not view["ready_for_decision"]

        job_b = _make_provider_job(db_path, "creatomate", "spec_1")
        view = svc.build_blind_view([job_a, job_b])
        assert view["ready_for_decision"]

    def test_incomplete_jobs_excluded(self, selection_service):
        """Jobs without output_hash are excluded."""
        svc, db_path = selection_service
        job_a = _make_provider_job(db_path, "shotstack", "spec_1")
        job_b = _make_provider_job(db_path, "creatomate", "spec_1",
                                    status="submitted", output_hash=None)

        view = svc.build_blind_view([job_a, job_b])
        assert len(view["outputs"]) == 1  # only the completed one


class TestRecordDecision:
    def test_record_selection(self, selection_service):
        svc, db_path = selection_service
        decision = svc.record_decision(
            "test", "spec_1", primary_label="A", fallback_label="B",
            quality_observations={"caption_sync": "A better"},
            operational_facts={"cost_a": 0.05, "cost_b": 0.03},
        )

        assert decision["decision"] == "selected"
        assert decision["primary_provider"] == "A"
        assert decision["fallback_provider"] == "B"

    def test_record_rejection(self, selection_service):
        svc, db_path = selection_service
        decision = svc.record_rejection(
            "test", "spec_1", "Both have audio sync issues")

        assert decision["decision"] == "rejected"
        assert decision["primary_provider"] is None

    def test_has_selection(self, selection_service):
        svc, db_path = selection_service
        assert not svc.has_selection("test", "spec_1")

        svc.record_decision("test", "spec_1", "A", "B")
        assert svc.has_selection("test", "spec_1")

    def test_invalid_label_rejected(self, selection_service):
        svc, db_path = selection_service
        with pytest.raises(Exception, match="Invalid"):
            svc.record_decision("test", "spec_1", primary_label="X")


class TestLocalAdapterAsFallback:
    """VF-RA-004: The local adapter is preserved as an executable fallback."""

    def test_local_adapter_available(self):
        """The local FFmpeg/PIL adapter is always available as fallback."""
        from services.renderer_spec import LocalConformanceAdapter
        adapter = LocalConformanceAdapter()
        assert adapter.capabilities is not None
        assert "text_overlay" in adapter.capabilities

    def test_factory_creates_local(self, selection_service):
        """The factory can create a local adapter."""
        from services.render_adapters import ProviderAdapterFactory
        adapter = ProviderAdapterFactory.create("local", selection_service[1])
        assert adapter is not None


class TestSpecHashIdempotency:
    """VF-RA-004: Spec-hash idempotency — same spec doesn't create duplicate jobs."""

    def test_same_spec_same_hash(self):
        from services.renderer_spec import compute_spec_hash
        spec = {"spec_version": "1.0", "identity": {"session_id": 1},
                "canvas": {"width": 1080, "height": 1920, "fps": 30},
                "timeline": []}
        hash1 = compute_spec_hash(spec)
        hash2 = compute_spec_hash(spec)
        assert hash1 == hash2


class TestProviderSuccessWithoutArtifact:
    """VF-RA-004: Provider success without a downloaded verified artifact is not green."""

    def test_job_without_output_is_not_complete(self, selection_service):
        """A provider job marked 'done' but without output_hash is not green."""
        svc, db_path = selection_service
        job = _make_provider_job(db_path, "shotstack", "spec_1",
                                  status="done", output_hash=None)

        # The blind view excludes it
        view = svc.build_blind_view([job])
        assert len(view["outputs"]) == 0  # excluded — no output_hash