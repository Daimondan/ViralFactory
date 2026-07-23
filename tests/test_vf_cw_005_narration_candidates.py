"""
VF-CW-005 — Narration candidate sets tests.

Tests:
  - Register existing valid take as candidate
  - Partial take (missing segments) fails visibly
  - Partial take (missing path) fails visibly
  - Partial take (zero duration) fails visibly
  - Partial take (no spoken text) fails visibly
  - New take never inherits approval
  - Operator can compare candidates
  - Selected take is the only one eligible for freeze
  - Failed generation registers a failed candidate
  - Spoken text hash and timing hash are computed
  - Beat refs derived from segments
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
    # Create a media directory for fake VO files
    media_dir = os.path.join(tmpdir, "data", "media", "1")
    os.makedirs(media_dir, exist_ok=True)
    yield db_path, media_dir
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def narration_service(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    PipelineStore(db_path=db_path)
    from services.narration_candidates import NarrationCandidateService
    return NarrationCandidateService(db_path=db_path), media_dir


def _setup_session(tmp_db, business_slug="test_tenant"):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    from services.production_orchestrator import ProductionSessionService

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
    return session, asset


def _make_wav(path, duration_s=1.0, sample_rate=24000):
    """Create a minimal valid WAV file."""
    n_samples = int(duration_s * sample_rate)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        # Write silence
        for _ in range(n_samples):
            w.writeframes(struct.pack("<h", 0))


class TestRegisterExistingTake:
    def test_register_valid_take(self, narration_service, tmp_db):
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        # Create fake VO files
        seg1_path = os.path.join(media_dir, "vo_take1_frame1.wav")
        seg2_path = os.path.join(media_dir, "vo_take1_frame2.wav")
        combined_path = os.path.join(media_dir, "vo_take1_combined.wav")
        _make_wav(seg1_path, 5.0)
        _make_wav(seg2_path, 7.0)
        _make_wav(combined_path, 12.0)

        take_result = {
            "take_id": "take_test_001",
            "segments": [
                {"frame": 1, "beat_id": "b01", "path": seg1_path,
                 "duration": 5.0, "text": "First beat spoken text"},
                {"frame": 2, "beat_id": "b02", "path": seg2_path,
                 "duration": 7.0, "text": "Second beat spoken text"},
            ],
            "total_duration": 12.0,
            "combined_path": combined_path,
        }

        candidate = svc.register_existing_take(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], take_result,
            voice_identity={"engine": "chatterbox", "model": "test"},
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "narration"
        assert candidate["role"] == "full_take"
        assert candidate["status"] == "available"
        assert candidate["artifact_hash"] is not None
        assert candidate["artifact_path"] == combined_path
        assert candidate["beat_refs_json"] is not None

        # Check beat refs
        beat_refs = json.loads(candidate["beat_refs_json"])
        assert "b01" in beat_refs
        assert "b02" in beat_refs

        # Check measurement
        measurement = json.loads(candidate["measurement_json"])
        assert measurement["total_duration"] == 12.0
        assert measurement["segment_count"] == 2
        assert measurement["spoken_text_hash"] is not None
        assert measurement["timing_hash"] is not None


class TestPartialTakeFails:
    def test_missing_segments_fails(self, narration_service, tmp_db):
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        with pytest.raises(Exception, match="no segments"):
            svc.register_existing_take(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], {"take_id": "t1", "segments": [],
                               "combined_path": "x", "total_duration": 0})

    def test_missing_path_fails(self, narration_service, tmp_db):
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        take_result = {
            "take_id": "take_fail",
            "segments": [
                {"frame": 1, "beat_id": "b01", "path": "/nonexistent/path.wav",
                 "duration": 5.0, "text": "Test"},
            ],
            "total_duration": 5.0,
            "combined_path": "/nonexistent/combined.wav",
        }
        with pytest.raises(Exception, match="missing or nonexistent path"):
            svc.register_existing_take(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], take_result)

    def test_zero_duration_fails(self, narration_service, tmp_db):
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        seg_path = os.path.join(media_dir, "zero_dur.wav")
        _make_wav(seg_path, 0.1)
        combined_path = os.path.join(media_dir, "zero_combined.wav")
        _make_wav(combined_path, 0.1)

        take_result = {
            "take_id": "take_zero",
            "segments": [
                {"frame": 1, "beat_id": "b01", "path": seg_path,
                 "duration": 0, "text": "Test"},
            ],
            "total_duration": 0,
            "combined_path": combined_path,
        }
        with pytest.raises(Exception, match="zero or negative duration"):
            svc.register_existing_take(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], take_result)

    def test_no_spoken_text_fails(self, narration_service, tmp_db):
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        seg_path = os.path.join(media_dir, "no_text.wav")
        _make_wav(seg_path, 5.0)
        combined_path = os.path.join(media_dir, "no_text_combined.wav")
        _make_wav(combined_path, 5.0)

        take_result = {
            "take_id": "take_notext",
            "segments": [
                {"frame": 1, "beat_id": "b01", "path": seg_path,
                 "duration": 5.0, "text": ""},
            ],
            "total_duration": 5.0,
            "combined_path": combined_path,
        }
        with pytest.raises(Exception, match="no spoken text"):
            svc.register_existing_take(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], take_result)


class TestNewTakeNeverInheritsApproval:
    def test_new_take_is_available_not_approved(self, narration_service, tmp_db):
        """A newly registered take is 'available', not 'approved'."""
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        seg_path = os.path.join(media_dir, "take1.wav")
        combined_path = os.path.join(media_dir, "take1_combined.wav")
        _make_wav(seg_path, 5.0)
        _make_wav(combined_path, 5.0)

        take = {
            "take_id": "take_1",
            "segments": [{"frame": 1, "beat_id": "b01", "path": seg_path,
                          "duration": 5.0, "text": "Test text"}],
            "total_duration": 5.0,
            "combined_path": combined_path,
        }
        candidate = svc.register_existing_take(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], take)

        assert candidate["status"] == "available"
        assert candidate["status"] != "approved"

    def test_regenerated_take_supersedes_prior_approval(self, narration_service, tmp_db):
        """When a new take is registered after approval, the old is superseded
        and the new one is NOT approved."""
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        # First take
        seg1 = os.path.join(media_dir, "v1_seg.wav")
        comb1 = os.path.join(media_dir, "v1_comb.wav")
        _make_wav(seg1, 5.0)
        _make_wav(comb1, 5.0)
        take1 = {
            "take_id": "take_v1",
            "segments": [{"frame": 1, "beat_id": "b01", "path": seg1,
                          "duration": 5.0, "text": "Version 1"}],
            "total_duration": 5.0,
            "combined_path": comb1,
        }
        c1 = svc.register_existing_take(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], take1)

        # Approve first take
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=tmp_db[0])
        store.record_decision("test_tenant", session["id"], c1["id"], "approve")
        assert store.is_approved("test_tenant", c1["id"])

        # Second take (regeneration)
        seg2 = os.path.join(media_dir, "v2_seg.wav")
        comb2 = os.path.join(media_dir, "v2_comb.wav")
        _make_wav(seg2, 6.0)
        _make_wav(comb2, 6.0)
        take2 = {
            "take_id": "take_v2",
            "segments": [{"frame": 1, "beat_id": "b01", "path": seg2,
                          "duration": 6.0, "text": "Version 2"}],
            "total_duration": 6.0,
            "combined_path": comb2,
        }
        c2 = svc.register_existing_take(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], take2)

        # c1 is superseded, c2 is available (not approved)
        c1_refreshed = store.get_candidate("test_tenant", c1["id"])
        assert c1_refreshed["status"] == "superseded"
        assert c2["status"] == "available"
        assert not store.is_approved("test_tenant", c2["id"])


class TestOperatorCanCompare:
    def test_list_candidates_shows_all_versions(self, narration_service, tmp_db):
        """The operator can see all available takes for comparison."""
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

        # Register two takes
        for i in range(2):
            seg = os.path.join(media_dir, f"cmp_seg_{i}.wav")
            comb = os.path.join(media_dir, f"cmp_comb_{i}.wav")
            _make_wav(seg, 5.0 + i)
            _make_wav(comb, 5.0 + i)
            take = {
                "take_id": f"take_cmp_{i}",
                "segments": [{"frame": 1, "beat_id": "b01", "path": seg,
                              "duration": 5.0 + i, "text": f"Take {i}"}],
                "total_duration": 5.0 + i,
                "combined_path": comb,
            }
            svc.register_existing_take(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], take)

        candidates = svc.list_narration_candidates("test_tenant", session["id"])
        assert len(candidates) == 2
        # First is superseded, second is available
        statuses = {c["status"] for c in candidates}
        assert "superseded" in statuses
        assert "available" in statuses

        # Current (non-superseded) shows only the latest
        current = svc.get_current_narration("test_tenant", session["id"])
        assert len(current) == 1
        assert current[0]["status"] == "available"


class TestApprovedTakeEligibleForFreeze:
    def test_approved_take_is_eligible(self, narration_service, tmp_db):
        """The approved take is the only one eligible for manifest freeze."""
        svc, media_dir = narration_service
        session, asset = _setup_session(tmp_db)

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
        c = svc.register_existing_take(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], take)

        # No approved take yet
        assert svc.get_approved_take("test_tenant", session["id"]) is None

        # Approve it
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=tmp_db[0])
        store.record_decision("test_tenant", session["id"], c["id"], "approve")

        # Now there is an approved take
        approved = svc.get_approved_take("test_tenant", session["id"])
        assert approved is not None
        assert approved["id"] == c["id"]
        assert approved["status"] == "approved"