"""
VF-CW-007 — Soundtrack, source-sound, and SFX candidates service tests.

Tests:
  - Register soundtrack with valid rights as candidate
  - Soundtrack with unknown/stale rights fails closed
  - Soundtrack with unapproved cost fails closed
  - Music selection does not imply SFX approval
  - VO-only decision requires rationale
  - Multiple alternatives can be registered
  - Alternative selection records exact version
  - Missing preview/hash blocks registration
  - Source sound requires rationale
  - SFX cue registration
  - get_approved_soundtrack returns approved candidate
  - SFX and soundtrack are separate roles
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import struct
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = str(ROOT / "src")


# ── Fixtures ─────────────────────────────────────────────────────────────

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
def audio_service(tmp_db):
    import sys
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    PipelineStore(db_path=db_path)
    from services.audio_candidates import AudioCandidateService
    return AudioCandidateService(db_path=db_path), media_dir


def _setup_session(tmp_db, business_slug="test_tenant"):
    import sys
    if SRC_DIR not in sys.path:
        sys.path.insert(0, SRC_DIR)
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


def _make_wav(path, duration_s=1.0, sample_rate=8000):
    """Create a minimal valid WAV file."""
    n_samples = int(duration_s * sample_rate)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<h", 0) * n_samples)


def _file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rights(**overrides):
    """Build a valid rights record."""
    record = {
        "candidate_id": "pixabay:track-7",
        "rights_status": "verified",
        "rights_source": "provider_terms",
        "terms_url": "https://example.invalid/terms",
        "terms_retrieved_at": "2026-07-20T00:00:00+00:00",
        "terms_evidence_hash": "a" * 64,
        "commercial_use_allowed": True,
        "synchronization_allowed": True,
        "download_authorized": True,
        "acquisition_method": "provider_download",
        "platform_constraints": [],
        "territory_constraints": [],
        "account_type_constraints": [],
        "expires_at": None,
        "attribution_required": False,
        "attribution_text": None,
        "cost_usd": 0.0,
        "cost_approval_id": None,
    }
    record.update(overrides)
    return record


def _save_rights_and_artifact(db_path, media_dir, asset_id=1,
                              soundtrack_plan_id=1, rights_overrides=None,
                              artifact_duration=2.0, candidate_id="pixabay:track-7",
                              skip_validation=False):
    """Save a rights record and acquire a local artifact, returning both.

    When ``skip_validation`` is True the rights record is inserted directly
    via SQL, bypassing the validator — used for testing fail-closed paths
    with intentionally invalid rights (unknown status, expired, unapproved
    cost).
    """
    from soundtrack_rights import SoundtrackRightsStore, acquire_rights_valid_track

    store = SoundtrackRightsStore(db_path)
    rights_record = _rights(candidate_id=candidate_id)
    if rights_overrides:
        rights_record.update(rights_overrides)

    if skip_validation:
        rights = _insert_rights_raw(db_path, asset_id, soundtrack_plan_id,
                                    rights_record)
    else:
        rights = store.save_rights_record(
            asset_id=asset_id, soundtrack_plan_id=soundtrack_plan_id,
            record=rights_record,
        )

    def downloader(_url, destination):
        _make_wav(destination, artifact_duration)

    artifact = acquire_rights_valid_track(
        db_path=db_path,
        asset_id=asset_id,
        soundtrack_plan_id=soundtrack_plan_id,
        rights_record_id=rights["rights_record_id"],
        candidate={
            "candidate_id": candidate_id,
            "provider": "pixabay",
            "download_url": "https://cdn.invalid/audio.wav",
        },
        media_root=os.path.dirname(os.path.dirname(media_dir)),  # tmpdir/data
        downloader=downloader,
    )
    return rights, artifact


def _insert_rights_raw(db_path, asset_id, soundtrack_plan_id, record):
    """Insert a rights record directly via SQL, bypassing validation."""
    import hashlib as _hl
    from soundtrack_rights import sanitize_url, _now
    safe = json.loads(json.dumps(record))
    safe["terms_url"] = sanitize_url(safe["terms_url"])
    canonical = json.dumps(safe, sort_keys=True, ensure_ascii=False)
    rights_hash = _hl.sha256(canonical.encode("utf-8")).hexdigest()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT COALESCE(MAX(rights_version), 0) AS version "
            "FROM soundtrack_rights "
            "WHERE soundtrack_plan_id = ? AND candidate_id = ?",
            (soundtrack_plan_id, safe["candidate_id"]),
        ).fetchone()
        version = int(row["version"]) + 1
        cursor = conn.execute(
            """INSERT INTO soundtrack_rights
               (asset_id, soundtrack_plan_id, candidate_id, rights_version,
                rights_json, rights_hash, terms_url, terms_evidence_hash, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, soundtrack_plan_id, safe["candidate_id"], version,
             canonical, rights_hash, safe["terms_url"],
             safe["terms_evidence_hash"], _now()),
        )
        rights_record_id = int(cursor.lastrowid)
    return {
        "rights_record_id": rights_record_id,
        "rights_version": version,
        "rights_hash": rights_hash,
    }


def _make_raw_artifact(db_path, media_dir, asset_id=1,
                       soundtrack_plan_id=1, rights_overrides=None,
                       artifact_duration=2.0, candidate_id="pixabay:track-7"):
    """Insert a rights record bypassing validation (for fail-closed tests)
    and create a local artifact file manually.

    Unlike ``_save_rights_and_artifact``, this does NOT call
    ``acquire_rights_valid_track`` (which also validates rights), so it can
    produce artifacts with intentionally invalid rights.
    """
    rights_record = _rights(candidate_id=candidate_id)
    if rights_overrides:
        rights_record.update(rights_overrides)

    rights = _insert_rights_raw(db_path, asset_id, soundtrack_plan_id,
                                rights_record)

    # Create a local artifact file
    artifact_path = os.path.join(media_dir, f"raw_{candidate_id.replace(':', '_')}.wav")
    _make_wav(artifact_path, artifact_duration)
    content_hash = _file_hash(artifact_path)

    artifact = {
        "status": "render_ready",
        "artifact_id": 1,
        "local_path": artifact_path,
        "content_hash": content_hash,
        "byte_size": os.path.getsize(artifact_path),
        "duration_seconds": float(artifact_duration),
        "rights_record_id": rights["rights_record_id"],
        "candidate_id": candidate_id,
        "provider": "pixabay",
    }
    return rights, artifact


# ── Soundtrack candidate tests ──────────────────────────────────────────

class TestRegisterSoundtrackCandidate:
    def test_register_with_valid_rights(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
            soundtrack_plan_id=1,
        )

        # Create a preview file (simulated VO-under-bed preview)
        preview_path = os.path.join(media_dir, "preview_v1.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        candidate = svc.register_soundtrack_candidate(
            business_slug="test_tenant",
            production_session_id=session["id"],
            draft_id=session["draft_id"],
            asset_id=asset["id"],
            soundtrack_plan_id=1,
            rights_record_id=rights["rights_record_id"],
            artifact=artifact,
            preview_path=preview_path,
            preview_hash=preview_hash,
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "soundtrack"
        assert candidate["role"] == "music_bed"
        assert candidate["status"] == "available"
        assert candidate["artifact_hash"] == artifact["content_hash"]
        assert candidate["preview_hash"] == preview_hash
        assert candidate["rights_snapshot_json"] is not None

        rights_snap = json.loads(candidate["rights_snapshot_json"])
        assert rights_snap["rights_status"] == "verified"

    def test_unknown_rights_fails_closed(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, artifact = _make_raw_artifact(
            db_path, media_dir, asset_id=asset["id"],
            rights_overrides={"rights_status": "unknown"},
        )

        preview_path = os.path.join(media_dir, "preview_unknown.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        with pytest.raises(Exception, match="not current or render-eligible"):
            svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path, preview_hash,
            )

    def test_stale_rights_fails_closed(self, audio_service, tmp_db):
        """Expired rights fail closed."""
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        from datetime import timedelta
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        rights, artifact = _make_raw_artifact(
            db_path, media_dir, asset_id=asset["id"],
            rights_overrides={"expires_at": past},
        )

        preview_path = os.path.join(media_dir, "preview_stale.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        with pytest.raises(Exception, match="not current or render-eligible"):
            svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path, preview_hash,
            )

    def test_unapproved_cost_fails_closed(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, artifact = _make_raw_artifact(
            db_path, media_dir, asset_id=asset["id"],
            rights_overrides={
                "cost_usd": 10.0,
                "cost_approval_id": None,
            },
        )

        preview_path = os.path.join(media_dir, "preview_paid.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        with pytest.raises(Exception, match="(cost.*not operator-approved|not current or render-eligible)"):
            svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path, preview_hash,
            )

    def test_missing_preview_blocks_registration(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )

        with pytest.raises(Exception, match="preview file is missing"):
            svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact,
                preview_path="/nonexistent/preview.wav",
                preview_hash="somehash",
            )

    def test_missing_preview_hash_blocks_registration(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )

        preview_path = os.path.join(media_dir, "preview_no_hash.wav")
        _make_wav(preview_path, 2.0)

        with pytest.raises(Exception, match="preview hash is required"):
            svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path, preview_hash="",
            )

    def test_preview_hash_mismatch_blocks_registration(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )

        preview_path = os.path.join(media_dir, "preview_mismatch.wav")
        _make_wav(preview_path, 2.0)

        with pytest.raises(Exception, match="preview hash mismatch"):
            svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path,
                preview_hash="0" * 64,  # wrong hash
            )


# ── Multiple alternatives ───────────────────────────────────────────────

class TestMultipleAlternatives:
    def test_multiple_alternatives_can_be_registered(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        candidates = []
        for i in range(3):
            rights, artifact = _save_rights_and_artifact(
                db_path, media_dir, asset_id=asset["id"],
                soundtrack_plan_id=1,
                candidate_id=f"pixabay:track-{i}",
            )
            preview_path = os.path.join(media_dir, f"preview_alt_{i}.wav")
            _make_wav(preview_path, 2.0)
            preview_hash = _file_hash(preview_path)

            candidate = svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path, preview_hash,
                is_alternative=(i > 0),
            )
            candidates.append(candidate)

        assert len(candidates) == 3
        # Each candidate has a unique lineage version
        versions = [c["version"] for c in candidates]
        assert versions == [1, 2, 3]

        # All are available
        for c in candidates:
            assert c["status"] == "available"

    def test_alternative_selection_records_exact_version(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        from services.candidate_store import CandidateStore

        # Register two alternatives
        registered = []
        for i in range(2):
            rights, artifact = _save_rights_and_artifact(
                db_path, media_dir, asset_id=asset["id"],
                soundtrack_plan_id=1,
                candidate_id=f"pixabay:track-alt-{i}",
            )
            preview_path = os.path.join(media_dir, f"preview_sel_{i}.wav")
            _make_wav(preview_path, 2.0)
            preview_hash = _file_hash(preview_path)

            candidate = svc.register_soundtrack_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], 1, rights["rights_record_id"],
                artifact, preview_path, preview_hash,
                is_alternative=(i > 0),
            )
            registered.append(candidate)

        # Select the second alternative
        target = registered[1]
        result = svc.select_alternative(
            "test_tenant", session["id"], target["id"],
        )

        assert result["candidate_id"] == target["id"]
        assert result["candidate_version"] == target["version"]
        assert result["artifact_hash"] == target["artifact_hash"]

        # Verify a 'select' decision was recorded
        store = CandidateStore(db_path=db_path)
        decisions = store.get_decisions("test_tenant", target["id"])
        select_decisions = [d for d in decisions if d["decision_type"] == "select"]
        assert len(select_decisions) == 1
        assert select_decisions[0]["candidate_version"] == target["version"]
        assert select_decisions[0]["artifact_hash"] == target["artifact_hash"]


# ── VO-only decision ────────────────────────────────────────────────────

class TestVOOnlyDecision:
    def test_vo_only_with_rationale(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        candidate = svc.register_vo_only_decision(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"],
            rationale="The source content is a serious news piece where "
                      "music would undermine the tone.",
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "soundtrack"
        assert candidate["role"] == "vo_only"
        assert candidate["status"] == "available"

        prov = json.loads(candidate["generation_provenance_json"])
        assert prov["mode"] == "vo_only"
        assert "serious news" in prov["rationale"]

    def test_vo_only_without_rationale_fails(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        with pytest.raises(Exception, match="rationale is required"):
            svc.register_vo_only_decision(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], rationale="",
            )

    def test_vo_only_with_whitespace_rationale_fails(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        with pytest.raises(Exception, match="rationale is required"):
            svc.register_vo_only_decision(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], rationale="   ",
            )


# ── SFX candidates ──────────────────────────────────────────────────────

class TestSFXCandidate:
    def test_register_sfx_cue(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        sfx_path = os.path.join(media_dir, "sfx_whoosh.wav")
        _make_wav(sfx_path, 0.5)
        sfx_hash = _file_hash(sfx_path)
        preview_path = os.path.join(media_dir, "sfx_whoosh_preview.wav")
        _make_wav(preview_path, 0.5)
        preview_hash = _file_hash(preview_path)

        cue = {
            "event_id": "sfx_001",
            "source": "library:whoosh",
            "timestamp": 2.5,
            "gain": 0.8,
            "purpose": "transition emphasis",
        }

        candidate = svc.register_sfx_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], cue, sfx_path, sfx_hash,
            preview_path, preview_hash,
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "sound_effects"
        assert candidate["role"] == "sfx_cue"
        assert candidate["status"] == "available"
        assert candidate["artifact_hash"] == sfx_hash

        beat_refs = json.loads(candidate["beat_refs_json"])
        assert "sfx_001" in beat_refs

    def test_sfx_missing_event_id_fails(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        sfx_path = os.path.join(media_dir, "sfx_no_id.wav")
        _make_wav(sfx_path, 0.5)
        sfx_hash = _file_hash(sfx_path)
        preview_path = os.path.join(media_dir, "sfx_no_id_prev.wav")
        _make_wav(preview_path, 0.5)
        preview_hash = _file_hash(preview_path)

        with pytest.raises(Exception, match="no event_id"):
            svc.register_sfx_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], {"source": "x", "timestamp": 1, "gain": 0.5,
                              "purpose": "test"},
                sfx_path, sfx_hash, preview_path, preview_hash,
            )

    def test_sfx_missing_preview_blocks(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        sfx_path = os.path.join(media_dir, "sfx_no_prev.wav")
        _make_wav(sfx_path, 0.5)
        sfx_hash = _file_hash(sfx_path)

        cue = {"event_id": "sfx_002", "source": "lib", "timestamp": 1,
               "gain": 0.5, "purpose": "test"}

        with pytest.raises(Exception, match="preview file is missing"):
            svc.register_sfx_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], cue, sfx_path, sfx_hash,
                "/nonexistent/preview.wav", "somehash",
            )


# ── Source sound ────────────────────────────────────────────────────────

class TestSourceSound:
    def test_register_source_sound_with_rationale(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        src_path = os.path.join(media_dir, "source_ambient.wav")
        _make_wav(src_path, 3.0)
        src_hash = _file_hash(src_path)
        preview_path = os.path.join(media_dir, "source_ambient_prev.wav")
        _make_wav(preview_path, 3.0)
        preview_hash = _file_hash(preview_path)

        candidate = svc.register_source_sound_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"],
            rationale="On-camera ambient sound from the workshop carries "
                      "the authentic atmosphere for this piece.",
            artifact_path=src_path, artifact_hash=src_hash,
            preview_path=preview_path, preview_hash=preview_hash,
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "sound_effects"
        assert candidate["role"] == "source_sound"
        assert candidate["status"] == "available"

    def test_source_sound_without_rationale_fails(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        src_path = os.path.join(media_dir, "source_no_rationale.wav")
        _make_wav(src_path, 3.0)
        src_hash = _file_hash(src_path)
        preview_path = os.path.join(media_dir, "source_no_rat_prev.wav")
        _make_wav(preview_path, 3.0)
        preview_hash = _file_hash(preview_path)

        with pytest.raises(Exception, match="rationale is required"):
            svc.register_source_sound_candidate(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], rationale="",
                artifact_path=src_path, artifact_hash=src_hash,
                preview_path=preview_path, preview_hash=preview_hash,
            )


# ── Music does not imply SFX approval ───────────────────────────────────

class TestMusicDoesNotImplySFX:
    def test_music_approval_does_not_imply_sfx_approval(self, audio_service, tmp_db):
        """Approving a music bed does not approve any SFX candidates."""
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=db_path)

        # Register a soundtrack candidate
        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )
        preview_path = os.path.join(media_dir, "preview_music.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        music_candidate = svc.register_soundtrack_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], 1, rights["rights_record_id"],
            artifact, preview_path, preview_hash,
        )

        # Register an SFX candidate
        sfx_path = os.path.join(media_dir, "sfx_cue.wav")
        _make_wav(sfx_path, 0.5)
        sfx_hash = _file_hash(sfx_path)
        sfx_preview = os.path.join(media_dir, "sfx_cue_prev.wav")
        _make_wav(sfx_preview, 0.5)
        sfx_preview_hash = _file_hash(sfx_preview)

        sfx_candidate = svc.register_sfx_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"],
            {"event_id": "sfx_100", "source": "lib", "timestamp": 1,
             "gain": 0.7, "purpose": "impact"},
            sfx_path, sfx_hash, sfx_preview, sfx_preview_hash,
        )

        # Approve the music bed
        store.record_decision(
            "test_tenant", session["id"],
            music_candidate["id"], "approve",
        )

        # The SFX candidate must NOT be approved
        assert store.is_approved("test_tenant", music_candidate["id"])
        assert not store.is_approved("test_tenant", sfx_candidate["id"])

        # get_approved_soundtrack returns the music, not SFX
        approved_st = svc.get_approved_soundtrack("test_tenant", session["id"])
        assert approved_st is not None
        assert approved_st["id"] == music_candidate["id"]
        assert approved_st["role"] == "music_bed"

        # get_approved_sfx returns nothing (SFX not approved)
        approved_sfx = svc.get_approved_sfx("test_tenant", session["id"])
        assert approved_sfx == []


# ── Separate roles ──────────────────────────────────────────────────────

class TestSeparateRoles:
    def test_soundtrack_and_sfx_are_separate_roles(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        # Register one of each
        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )
        preview_path = os.path.join(media_dir, "prev_mix.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        music = svc.register_soundtrack_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], 1, rights["rights_record_id"],
            artifact, preview_path, preview_hash,
        )

        sfx_path = os.path.join(media_dir, "sfx_sep.wav")
        _make_wav(sfx_path, 0.5)
        sfx_hash = _file_hash(sfx_path)
        sfx_prev = os.path.join(media_dir, "sfx_sep_prev.wav")
        _make_wav(sfx_prev, 0.5)
        sfx_prev_hash = _file_hash(sfx_prev)

        sfx = svc.register_sfx_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"],
            {"event_id": "sfx_sep", "source": "lib", "timestamp": 0,
             "gain": 0.5, "purpose": "test"},
            sfx_path, sfx_hash, sfx_prev, sfx_prev_hash,
        )

        src_path = os.path.join(media_dir, "src_sep.wav")
        _make_wav(src_path, 2.0)
        src_hash = _file_hash(src_path)
        src_prev = os.path.join(media_dir, "src_sep_prev.wav")
        _make_wav(src_prev, 2.0)
        src_prev_hash = _file_hash(src_prev)

        source = svc.register_source_sound_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], rationale="Ambient room tone.",
            artifact_path=src_path, artifact_hash=src_hash,
            preview_path=src_prev, preview_hash=src_prev_hash,
        )

        vo_only = svc.register_vo_only_decision(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], rationale="Not needed for this piece.",
        )

        all_candidates = svc.list_audio_candidates("test_tenant", session["id"])
        assert len(all_candidates) == 4

        categories = {(c["category"], c["role"]) for c in all_candidates}
        assert ("soundtrack", "music_bed") in categories
        assert ("soundtrack", "vo_only") in categories
        assert ("sound_effects", "sfx_cue") in categories
        assert ("sound_effects", "source_sound") in categories


# ── Approved soundtrack ─────────────────────────────────────────────────

class TestApprovedSoundtrack:
    def test_get_approved_soundtrack_returns_none_initially(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)

        assert svc.get_approved_soundtrack("test_tenant", session["id"]) is None

    def test_get_approved_soundtrack_after_approval(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        from services.candidate_store import CandidateStore

        rights, artifact = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )
        preview_path = os.path.join(media_dir, "prev_appr.wav")
        _make_wav(preview_path, 2.0)
        preview_hash = _file_hash(preview_path)

        candidate = svc.register_soundtrack_candidate(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], 1, rights["rights_record_id"],
            artifact, preview_path, preview_hash,
        )

        store = CandidateStore(db_path=db_path)
        store.record_decision(
            "test_tenant", session["id"], candidate["id"], "approve",
        )

        approved = svc.get_approved_soundtrack("test_tenant", session["id"])
        assert approved is not None
        assert approved["id"] == candidate["id"]


# ── Rights / cost checks ────────────────────────────────────────────────

class TestRightsAndCostChecks:
    def test_check_rights_valid_returns_true_for_valid(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, _ = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )
        assert svc.check_rights_valid(rights["rights_record_id"]) is True

    def test_check_rights_valid_returns_false_for_unknown(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, _ = _make_raw_artifact(
            db_path, media_dir, asset_id=asset["id"],
            rights_overrides={"rights_status": "unknown"},
        )
        assert svc.check_rights_valid(rights["rights_record_id"]) is False

    def test_check_rights_valid_returns_false_for_missing_record(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        assert svc.check_rights_valid(99999) is False

    def test_check_cost_approved_free_acquisition(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, _ = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
        )
        assert svc.check_cost_approved(rights["rights_record_id"]) is True

    def test_check_cost_approved_paid_without_approval(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, _ = _make_raw_artifact(
            db_path, media_dir, asset_id=asset["id"],
            rights_overrides={"cost_usd": 15.0, "cost_approval_id": None},
        )
        assert svc.check_cost_approved(rights["rights_record_id"]) is False

    def test_check_cost_approved_paid_with_approval(self, audio_service, tmp_db):
        svc, media_dir = audio_service
        session, asset = _setup_session(tmp_db)
        db_path = tmp_db[0]

        rights, _ = _save_rights_and_artifact(
            db_path, media_dir, asset_id=asset["id"],
            rights_overrides={
                "cost_usd": 15.0,
                "cost_approval_id": "cost_approval_abc",
            },
        )
        assert svc.check_cost_approved(rights["rights_record_id"]) is True