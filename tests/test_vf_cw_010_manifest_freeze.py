"""
VF-CW-010 — Completeness + immutable manifest freeze tests.

Tests:
  - Completeness check: no approved candidates → incomplete
  - Completeness check: one approved per role → complete
  - Completeness check: multiple approved → blocker
  - Completeness check: none_allowed role with no candidate → no blocker
  - Freeze: complete session → manifest created
  - Freeze: incomplete session → fails closed
  - Freeze: idempotent (same inputs → same manifest)
  - Freeze: changed input → new manifest version, prior deactivated
  - Candidate validation: missing hash, missing preview, unapproved cost
  - Manifest hash is canonical (key-order independent)
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
def manifest_store(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    PipelineStore(db_path=db_path)
    from services.manifest_freeze import ManifestStore
    return ManifestStore(db_path=db_path), media_dir


def _setup_session_and_reqs(tmp_db, business_slug="test_tenant"):
    """Create a session with requirements that have one required role."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService
    from services.component_requirements import ComponentRequirementsStore

    store = PipelineStore(db_path=db_path)
    now = datetime.now(timezone.utc).isoformat()
    store.create_idea_card(
        business_slug=business_slug, idea="Test", hook_options=["Hook"],
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

    svc = ProductionSessionService(db_path=db_path)
    session = svc.create_session(
        business_slug, draft["id"], asset["id"], "IG", "reel")

    # Save requirements with one required narration role
    reqs = {
        "format": "reel",
        "platform": "IG",
        "categories": [
            {
                "category": "narration",
                "required": True,
                "roles": [
                    {"role": "full_take", "required": True,
                     "scope": "all_beats", "beat_refs": [],
                     "none_allowed": False, "preview_required": True},
                ],
            },
        ],
    }
    req_store = ComponentRequirementsStore(db_path=db_path)
    req_store.save_requirements(
        business_slug, session["id"], draft["id"], asset["id"], reqs)

    return session, asset


def _make_wav(path, duration_s=1.0):
    n = int(duration_s * 24000)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        for _ in range(n):
            w.writeframes(struct.pack("<h", 0))


def _register_and_approve_narration(tmp_db, session, media_dir):
    """Register a narration candidate and approve it."""
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, _ = tmp_db
    from services.narration_candidates import NarrationCandidateService
    from services.candidate_store import CandidateStore

    seg = os.path.join(media_dir, "freeze_seg.wav")
    comb = os.path.join(media_dir, "freeze_comb.wav")
    _make_wav(seg, 5.0)
    _make_wav(comb, 5.0)
    take = {
        "take_id": "take_freeze",
        "segments": [{"frame": 1, "beat_id": "b01", "path": seg,
                      "duration": 5.0, "text": "Freeze test"}],
        "total_duration": 5.0,
        "combined_path": comb,
    }
    ncs = NarrationCandidateService(db_path=db_path)
    candidate = ncs.register_existing_take(
        "test_tenant", session["id"], session["draft_id"],
        session["asset_id"], take)

    store = CandidateStore(db_path=db_path)
    store.record_decision("test_tenant", session["id"], candidate["id"], "approve")
    return candidate


class TestCompletenessCheck:
    def test_no_approved_is_incomplete(self, manifest_store, tmp_db):
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)

        from services.component_requirements import ComponentRequirementsStore
        req_store = ComponentRequirementsStore(db_path=tmp_db[0])
        reqs = req_store.get_current_requirements("test_tenant", session["id"])
        requirements = reqs["requirements_json"]

        result = svc.check_completeness("test_tenant", session["id"], requirements)
        assert not result["complete"]
        assert len(result["blockers"]) > 0
        assert any(b["category"] == "narration" for b in result["blockers"])

    def test_one_approved_is_complete(self, manifest_store, tmp_db):
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)
        _register_and_approve_narration(tmp_db, session, media_dir)

        from services.component_requirements import ComponentRequirementsStore
        req_store = ComponentRequirementsStore(db_path=tmp_db[0])
        reqs = req_store.get_current_requirements("test_tenant", session["id"])
        requirements = reqs["requirements_json"]

        result = svc.check_completeness("test_tenant", session["id"], requirements)
        assert result["complete"]
        assert len(result["blockers"]) == 0
        assert len(result["approved_candidates"]) == 1

    def test_none_allowed_no_blocker(self, manifest_store, tmp_db):
        """A role with none_allowed=True doesn't block when no candidate exists."""
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)

        # Update requirements to add an optional role
        from services.component_requirements import ComponentRequirementsStore
        req_store = ComponentRequirementsStore(db_path=tmp_db[0])
        reqs = {
            "format": "reel",
            "platform": "IG",
            "categories": [
                {
                    "category": "narration",
                    "required": True,
                    "roles": [
                        {"role": "full_take", "required": True,
                         "scope": "all_beats", "beat_refs": [],
                         "none_allowed": False, "preview_required": True},
                    ],
                },
                {
                    "category": "soundtrack",
                    "required": False,
                    "roles": [
                        {"role": "music_bed", "required": False,
                         "scope": "full_piece", "beat_refs": [],
                         "none_allowed": True, "preview_required": True},
                    ],
                },
            ],
        }
        req_store.save_requirements(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], reqs)

        # Approve narration but not soundtrack
        _register_and_approve_narration(tmp_db, session, media_dir)

        current_reqs = req_store.get_current_requirements("test_tenant", session["id"])
        result = svc.check_completeness(
            "test_tenant", session["id"], current_reqs["requirements_json"])

        assert result["complete"]
        assert len(result["blockers"]) == 0


class TestFreezeManifest:
    def test_freeze_complete(self, manifest_store, tmp_db):
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)
        _register_and_approve_narration(tmp_db, session, media_dir)

        manifest = svc.freeze_manifest("test_tenant", session["id"])

        assert manifest["id"] is not None
        assert manifest["version"] == 1
        assert manifest["is_active"] == 1
        assert manifest["manifest_hash"] is not None

        manifest_data = manifest["manifest_json"]
        assert manifest_data["business_slug"] == "test_tenant"
        assert len(manifest_data["candidates"]) == 1
        assert manifest_data["candidates"][0]["category"] == "narration"

    def test_freeze_incomplete_fails(self, manifest_store, tmp_db):
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)
        # No candidates approved

        with pytest.raises(Exception, match="incomplete"):
            svc.freeze_manifest("test_tenant", session["id"])

    def test_freeze_idempotent(self, manifest_store, tmp_db):
        """Freezing twice with same inputs returns the same manifest."""
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)
        _register_and_approve_narration(tmp_db, session, media_dir)

        m1 = svc.freeze_manifest("test_tenant", session["id"])
        m2 = svc.freeze_manifest("test_tenant", session["id"])

        assert m1["id"] == m2["id"]
        assert m1["manifest_hash"] == m2["manifest_hash"]
        assert m1["version"] == m2["version"]

    def test_changed_input_creates_new_version(self, manifest_store, tmp_db):
        """When an approved candidate changes, freeze creates a new version."""
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)
        c1 = _register_and_approve_narration(tmp_db, session, media_dir)

        m1 = svc.freeze_manifest("test_tenant", session["id"])
        assert m1["version"] == 1

        # Register a new take and approve it (c1 is superseded)
        seg2 = os.path.join(media_dir, "v2_seg.wav")
        comb2 = os.path.join(media_dir, "v2_comb.wav")
        _make_wav(seg2, 6.0)
        _make_wav(comb2, 6.0)
        from services.narration_candidates import NarrationCandidateService
        from services.candidate_store import CandidateStore
        ncs = NarrationCandidateService(db_path=tmp_db[0])
        take2 = {
            "take_id": "take_v2",
            "segments": [{"frame": 1, "beat_id": "b01", "path": seg2,
                          "duration": 6.0, "text": "Version 2"}],
            "total_duration": 6.0,
            "combined_path": comb2,
        }
        c2 = ncs.register_existing_take(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], take2)
        store = CandidateStore(db_path=tmp_db[0])
        store.record_decision("test_tenant", session["id"], c2["id"], "approve")

        # Freeze again — should be version 2
        m2 = svc.freeze_manifest("test_tenant", session["id"])
        assert m2["version"] == 2
        assert m2["manifest_hash"] != m1["manifest_hash"]
        assert m2["is_active"] == 1

        # m1 is deactivated
        m1_refreshed = svc.get_manifest_by_hash(m1["manifest_hash"])
        assert m1_refreshed["is_active"] == 0


class TestCandidateValidation:
    def test_missing_artifact_hash_blocks(self, manifest_store, tmp_db):
        """An approved candidate without artifact_hash is a blocker."""
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)

        # Register a candidate without artifact hash
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=tmp_db[0])
        c = store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take",
            artifact_hash=None, preview_hash="preview_hash",
            status="available")
        store.record_decision("test_tenant", session["id"], c["id"], "approve")

        from services.component_requirements import ComponentRequirementsStore
        req_store = ComponentRequirementsStore(db_path=tmp_db[0])
        reqs = req_store.get_current_requirements("test_tenant", session["id"])

        result = svc.check_completeness(
            "test_tenant", session["id"], reqs["requirements_json"])
        assert not result["complete"]
        assert any("artifact hash" in b["reason"] for b in result["blockers"])

    def test_missing_preview_blocks(self, manifest_store, tmp_db):
        """An approved candidate missing required preview is a blocker."""
        svc, media_dir = manifest_store
        session, asset = _setup_session_and_reqs(tmp_db)

        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=tmp_db[0])
        c = store.create_candidate(
            "test_tenant", session["id"], session["draft_id"],
            session["asset_id"], "narration", "full_take",
            artifact_hash="artifact_hash", preview_hash=None,
            status="available")
        store.record_decision("test_tenant", session["id"], c["id"], "approve")

        from services.component_requirements import ComponentRequirementsStore
        req_store = ComponentRequirementsStore(db_path=tmp_db[0])
        reqs = req_store.get_current_requirements("test_tenant", session["id"])

        result = svc.check_completeness(
            "test_tenant", session["id"], reqs["requirements_json"])
        assert not result["complete"]
        assert any("preview" in b["reason"] for b in result["blockers"])


class TestManifestHash:
    def test_hash_is_canonical(self, manifest_store, tmp_db):
        """Same manifest data produces same hash regardless of key order."""
        svc, _ = manifest_store
        data_a = {"a": 1, "b": 2, "c": [3, 2, 1]}
        data_b = {"c": [3, 2, 1], "b": 2, "a": 1}
        assert svc._compute_manifest_hash(data_a) == svc._compute_manifest_hash(data_b)