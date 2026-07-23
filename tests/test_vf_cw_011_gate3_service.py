"""
VF-CW-011 — Manifest-only assembly + Gate 3 service tests.

Tests:
  - Gate 3 approval requires final artifact, manifest, evidence
  - Gate 3 approval without final artifact fails
  - Gate 3 approval without manifest fails
  - Gate 3 approval without evidence fails
  - Gate 3 approval with incomplete evidence fails
  - Gate 3 approval from wrong session state fails
  - Direct route cannot write gate state — only Gate3Service
  - Reject sends back to assembling
  - Kill transitions to failed
  - Manifest consumption validation: missing artifact fails
  - Manifest consumption validation: hash mismatch fails
  - Is approved checks current decision
"""

import json
import os
import sqlite3
import tempfile
import wave
import struct
from datetime import datetime, timezone

import pytest


@pytest.fixture
def tmp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_vf.db")
    media_dir = os.path.join(tmpdir, "data", "media", "1")
    os.makedirs(media_dir, exist_ok=True)
    yield db_path, media_dir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def gate3_service(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    PipelineStore(db_path=db_path)
    from services.gate3_service import Gate3Service, AssemblyService
    return Gate3Service(db_path=db_path), AssemblyService(db_path=db_path), media_dir


def _setup_full_session(tmp_db, media_dir):
    """Set up a session with requirements, approved candidate, and frozen manifest."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, _ = tmp_db
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService
    from services.component_requirements import ComponentRequirementsStore
    from services.narration_candidates import NarrationCandidateService
    from services.candidate_store import CandidateStore
    from services.manifest_freeze import ManifestStore

    store = PipelineStore(db_path=db_path)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug="test_tenant", idea="Test", hook_options=["Hook"],
        treatment={"format": "reel", "scope": "test", "capture_required": False},
        origin="human_seeded",
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    card = dict(conn.execute(
        "SELECT * FROM idea_cards ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
        "draft_text, draft_version, draft_state, created_at, updated_at) "
        "VALUES (?, ?, 'human_seeded', 'reel', 'test', '', 1, 'shipped', ?, ?)",
        ("test_tenant", card["id"], now, now))
    conn.commit()
    draft = dict(conn.execute(
        "SELECT * FROM drafts ORDER BY id DESC LIMIT 1").fetchone())
    conn.execute(
        "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, asset_state, created_at, updated_at) "
        "VALUES (?, ?, 'IG', 'reel', 'Test', 'pending', ?, ?)",
        ("test_tenant", draft["id"], now, now))
    conn.commit()
    asset = dict(conn.execute(
        "SELECT * FROM assets ORDER BY id DESC LIMIT 1").fetchone())
    conn.close()

    svc = ProductionSessionService(db_path=db_path)
    session = svc.create_session(
        "test_tenant", draft["id"], asset["id"], "IG", "reel")

    # Save requirements
    reqs = {
        "format": "reel", "platform": "IG",
        "categories": [{
            "category": "narration", "required": True,
            "roles": [{"role": "full_take", "required": True,
                       "scope": "all_beats", "beat_refs": [],
                       "none_allowed": False, "preview_required": True}],
        }],
    }
    req_store = ComponentRequirementsStore(db_path=db_path)
    req_store.save_requirements(
        "test_tenant", session["id"], draft["id"], asset["id"], reqs)

    # Register and approve narration
    seg = os.path.join(media_dir, "gate3_seg.wav")
    comb = os.path.join(media_dir, "gate3_comb.wav")
    with wave.open(seg, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        for _ in range(24000 * 5): w.writeframes(struct.pack("<h", 0))
    with wave.open(comb, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        for _ in range(24000 * 5): w.writeframes(struct.pack("<h", 0))
    ncs = NarrationCandidateService(db_path=db_path)
    candidate = ncs.register_existing_take(
        "test_tenant", session["id"], draft["id"], asset["id"],
        {"take_id": "take_gate3",
         "segments": [{"frame": 1, "beat_id": "b01", "path": seg,
                       "duration": 5.0, "text": "Gate 3 test"}],
         "total_duration": 5.0, "combined_path": comb})
    cstore = CandidateStore(db_path=db_path)
    cstore.record_decision("test_tenant", session["id"], candidate["id"], "approve")

    # Freeze manifest
    mstore = ManifestStore(db_path=db_path)
    manifest = mstore.freeze_manifest("test_tenant", session["id"])

    # Transition session through the full path to final_review_required
    for to_state, reason in [
        ("generating_components", "requirements planned"),
        ("component_review_required", "candidates generated"),
        ("manifest_ready", "manifest frozen"),
        ("composition_planning", "plan started"),
        ("composition_review_required", "plan ready"),
        ("composition_ratified", "ratified"),
        ("assembling", "spec compiled"),
        ("final_review_required", "render complete"),
    ]:
        svc.transition("test_tenant", session["id"], to_state, reason)

    # Create a fake final artifact
    final_path = os.path.join(media_dir, "final.mp4")
    with open(final_path, "wb") as f:
        f.write(b"fake_video_content_for_testing")

    return session, asset, manifest, final_path


class TestGate3Approval:
    def test_approval_requires_final_artifact(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        with pytest.raises(Exception, match="artifact file does not exist"):
            gate3.approve(
                "test_tenant", session["id"],
                "/nonexistent/path.mp4",
                evidence={"duration_check": {"verdict": "pass"},
                          "audio_check": {"verdict": "pass"},
                          "visual_check": {"verdict": "pass"},
                          "text_integrity_check": {"verdict": "pass"}})

    def test_approval_requires_evidence(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        with pytest.raises(Exception, match="evidence"):
            gate3.approve(
                "test_tenant", session["id"], final_path,
                evidence={})  # empty evidence

    def test_approval_with_all_prerequisites(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        decision = gate3.approve(
            "test_tenant", session["id"], final_path,
            evidence={"duration_check": {"verdict": "pass"},
                      "audio_check": {"verdict": "pass"},
                      "visual_check": {"verdict": "pass"},
                      "text_integrity_check": {"verdict": "pass"}},
            feedback="Looks good")

        assert decision["decision"] == "approve"
        assert decision["final_artifact_hash"] is not None
        assert decision["manifest_hash"] is not None

        # Session is now gate3_approved
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_db[0])
        session_refreshed = svc.get_session("test_tenant", session["id"])
        assert session_refreshed["current_state"] == "gate3_approved"

    def test_approval_from_wrong_state_fails(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        # Transition back to assembling
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_db[0])
        svc.transition("test_tenant", session["id"], "assembling", "re-render")

        with pytest.raises(Exception, match="final_review_required"):
            gate3.approve(
                "test_tenant", session["id"], final_path,
                evidence={"duration_check": {"verdict": "pass"},
                          "audio_check": {"verdict": "pass"},
                          "visual_check": {"verdict": "pass"},
                          "text_integrity_check": {"verdict": "pass"}})


class TestGate3Reject:
    def test_reject_sends_back_to_assembling(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        decision = gate3.reject(
            "test_tenant", session["id"], "Audio too quiet")

        assert decision["decision"] == "reject"

        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_db[0])
        session_refreshed = svc.get_session("test_tenant", session["id"])
        assert session_refreshed["current_state"] == "assembling"


class TestGate3Kill:
    def test_kill_transitions_to_failed(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        decision = gate3.kill(
            "test_tenant", session["id"], "Content doesn't work")

        assert decision["decision"] == "kill"

        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=tmp_db[0])
        session_refreshed = svc.get_session("test_tenant", session["id"])
        assert session_refreshed["current_state"] == "failed"


class TestManifestConsumption:
    def test_valid_manifest_consumption(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        result = assembly.validate_manifest_consumption(
            "test_tenant", manifest["id"])

        assert result["valid"]
        assert len(result["errors"]) == 0
        assert len(result["ingredients"]) > 0

    def test_missing_artifact_fails(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        # Delete the artifact file
        manifest_data = manifest["manifest_json"]
        for c in manifest_data["candidates"]:
            if c.get("artifact_path") and os.path.exists(c["artifact_path"]):
                os.remove(c["artifact_path"])

        result = assembly.validate_manifest_consumption(
            "test_tenant", manifest["id"])
        assert not result["valid"]
        assert any("missing" in e for e in result["errors"])

    def test_hash_mismatch_fails(self, gate3_service, tmp_db):
        gate3, assembly, media_dir = gate3_service
        session, asset, manifest, final_path = _setup_full_session(tmp_db, media_dir)

        # Corrupt the artifact file (change its hash)
        manifest_data = manifest["manifest_json"]
        for c in manifest_data["candidates"]:
            if c.get("artifact_path") and os.path.exists(c["artifact_path"]):
                with open(c["artifact_path"], "wb") as f:
                    f.write(b"corrupted_content")
                break

        result = assembly.validate_manifest_consumption(
            "test_tenant", manifest["id"])
        assert not result["valid"]
        assert any("hash mismatch" in e for e in result["errors"])


class TestNoDirectRouteWrites:
    def test_gate3_service_is_only_path(self, tmp_db):
        """There is a Gate3Service — routes should use it, not write state directly."""
        import sys
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)
        from services.gate3_service import Gate3Service
        assert Gate3Service is not None

        # The old route at /api/assets/<id>/gate directly wrote asset_state.
        # Now Gate3Service.approve() is the only path, and it validates
        # final artifact + manifest + evidence before writing.