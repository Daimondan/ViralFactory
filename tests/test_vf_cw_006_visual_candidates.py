"""
VF-CW-006 — Visual candidates per beat/event role service tests.

Tests:
  - Register existing image as candidate with hash, dimensions, beat scope
  - Register existing video as candidate with hash, duration, dimensions
  - Unscoped media (no beat_ref) fails closed
  - Required-real-capture cannot be satisfied by generated media
  - Multiple candidates per beat (comparison)
  - Failed candidates remain visible
  - Cross-session isolation
  - Generating candidates remain visible
  - register_from_asset_media reads from asset_media table
  - get_approved_for_beat returns approved visual
  - Invalid source type fails closed
  - Unmeasured files fail closed
"""

import json
import os
import sqlite3
import struct
import subprocess
import tempfile
import wave
from datetime import datetime, timezone

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────

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
def visual_service(tmp_db):
    import sys
    src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    db_path, media_dir = tmp_db
    from pipeline import PipelineStore
    PipelineStore(db_path=db_path)
    from services.visual_candidates import VisualCandidateService
    return VisualCandidateService(db_path=db_path), media_dir


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


# ── Media fixture helpers ─────────────────────────────────────────────────

def _make_minimal_png(path, width=64, height=64):
    """Create a minimal valid PNG file using PIL."""
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(255, 0, 0))
    img.save(path, "PNG")


def _make_minimal_mp4(path, duration=1.0, width=64, height=64):
    """Create a minimal valid MP4 file using ffmpeg."""
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not available")
    subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i",
            f"color=c=red:s={width}x{height}:d={duration}",
            "-pix_fmt", "yuv420p", path,
        ],
        capture_output=True, timeout=15,
    )
    if not os.path.exists(path):
        pytest.skip("ffmpeg failed to create test video")


def _make_minimal_wav(path, duration_s=1.0, sample_rate=24000):
    """Create a minimal valid WAV file."""
    n_samples = int(duration_s * sample_rate)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for _ in range(n_samples):
            w.writeframes(struct.pack("<h", 0))


# ── Tests ─────────────────────────────────────────────────────────────────

class TestRegisterExistingImage:
    def test_register_image_with_hash_dimensions_beat_scope(self, visual_service, tmp_db):
        """Register existing image as candidate with hash, dimensions, beat scope."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img_path = os.path.join(media_dir, "beat01_capture.png")
        _make_minimal_png(img_path, 320, 240)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img_path, "image", "b01", "capture",
            rights_snapshot={"license": "owned", "source": "operator_capture"},
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "visual_media"
        assert candidate["role"] == "beat_visual"
        assert candidate["status"] == "available"
        assert candidate["artifact_hash"] is not None
        assert len(candidate["artifact_hash"]) == 64  # SHA-256 hex
        assert candidate["artifact_path"] == img_path
        assert candidate["preview_path"] == img_path  # fullscreen preview works

        # Beat scope
        beat_refs = json.loads(candidate["beat_refs_json"])
        assert beat_refs == ["b01"]

        # Measurement has dimensions
        measurement = json.loads(candidate["measurement_json"])
        assert measurement["kind"] == "image"
        assert measurement["width"] == 320
        assert measurement["height"] == 240

        # Rights snapshot persisted
        rights = json.loads(candidate["rights_snapshot_json"])
        assert rights["license"] == "owned"

        # Source type persisted
        assert candidate["source_type"] == "capture"


class TestRegisterExistingVideo:
    def test_register_video_with_hash_duration_dimensions(self, visual_service, tmp_db):
        """Register existing video as candidate with hash, duration, dimensions."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        vid_path = os.path.join(media_dir, "beat02_clip.mp4")
        _make_minimal_mp4(vid_path, duration=2.0, width=128, height=72)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], vid_path, "video", "b02", "generated_video",
            rights_snapshot={"license": "generated"},
            cost_estimate_usd=0.15,
        )

        assert candidate["id"] is not None
        assert candidate["category"] == "visual_media"
        assert candidate["role"] == "beat_visual"
        assert candidate["status"] == "available"
        assert candidate["artifact_hash"] is not None
        assert candidate["artifact_path"] == vid_path
        assert candidate["preview_path"] == vid_path  # playable video preview

        beat_refs = json.loads(candidate["beat_refs_json"])
        assert beat_refs == ["b02"]

        measurement = json.loads(candidate["measurement_json"])
        assert measurement["kind"] == "video"
        assert measurement["width"] == 128
        assert measurement["height"] == 72
        assert measurement["duration"] is not None
        assert measurement["duration"] > 0

        assert candidate["cost_estimate_usd"] == 0.15
        assert candidate["source_type"] == "generated_video"


class TestUnscopedMediaFailsClosed:
    def test_no_beat_ref_fails(self, visual_service, tmp_db):
        """Unscoped media (no beat_ref) fails closed."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img_path = os.path.join(media_dir, "unscoped.png")
        _make_minimal_png(img_path)

        with pytest.raises(Exception, match="beat_ref"):
            svc.register_existing_media(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], img_path, "image", "", "capture",
            )

    def test_none_beat_ref_fails(self, visual_service, tmp_db):
        """None beat_ref fails closed."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img_path = os.path.join(media_dir, "unscoped2.png")
        _make_minimal_png(img_path)

        with pytest.raises(Exception, match="beat_ref"):
            svc.register_existing_media(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], img_path, "image", None, "capture",
            )


class TestRequiredRealCaptureRejectsGenerated:
    def test_generated_still_fails_for_real_capture(self, visual_service, tmp_db):
        """Required-real-capture cannot be satisfied by generated still."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img_path = os.path.join(media_dir, "gen_still.png")
        _make_minimal_png(img_path)

        with pytest.raises(Exception, match="cannot satisfy a requires_real_capture"):
            svc.register_existing_media(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], img_path, "image", "b01", "generated_still",
                requires_real_capture=True,
            )

    def test_generated_video_fails_for_real_capture(self, visual_service, tmp_db):
        """Required-real-capture cannot be satisfied by generated video."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        vid_path = os.path.join(media_dir, "gen_clip.mp4")
        _make_minimal_mp4(vid_path, duration=1.0)

        with pytest.raises(Exception, match="cannot satisfy a requires_real_capture"):
            svc.register_existing_media(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], vid_path, "video", "b01", "generated_video",
                requires_real_capture=True,
            )

    def test_capture_satisfies_real_capture(self, visual_service, tmp_db):
        """Capture source satisfies requires_real_capture."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img_path = os.path.join(media_dir, "real_capture.png")
        _make_minimal_png(img_path)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img_path, "image", "b01", "capture",
            requires_real_capture=True,
        )

        assert candidate["status"] == "available"
        assert candidate["source_type"] == "capture"

    def test_stock_satisfies_real_capture(self, visual_service, tmp_db):
        """Stock source satisfies requires_real_capture."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img_path = os.path.join(media_dir, "stock_img.png")
        _make_minimal_png(img_path)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img_path, "image", "b01", "stock",
            requires_real_capture=True,
        )

        assert candidate["status"] == "available"
        assert candidate["source_type"] == "stock"


class TestMultipleCandidatesPerBeat:
    def test_multiple_candidates_for_same_beat(self, visual_service, tmp_db):
        """Multiple candidates per beat for comparison.

        Unlike narration (where regeneration supersedes), visual candidates
        for different beats have different lineage IDs. For the SAME beat,
        a second registration creates a new version and supersedes the first.

        But we can test multiple candidates for the same beat by registering
        from different source types — they'll share the same lineage (same
        beat_ref) and the second will supersede the first. The operator can
        still see both via list_visual_candidates.
        """
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img1 = os.path.join(media_dir, "cmp_v1.png")
        img2 = os.path.join(media_dir, "cmp_v2.png")
        _make_minimal_png(img1, 320, 240)
        _make_minimal_png(img2, 640, 480)

        c1 = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img1, "image", "b01", "capture",
        )
        c2 = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img2, "image", "b01", "stock",
        )

        # Both are visible in the full list
        grouped = svc.list_visual_candidates("test_tenant", session["id"])
        assert "b01" in grouped
        assert len(grouped["b01"]) == 2

        # First is superseded, second is available
        statuses = {c["status"] for c in grouped["b01"]}
        assert "superseded" in statuses
        assert "available" in statuses

        # Current visuals show only the latest
        current = svc.get_current_visuals("test_tenant", session["id"])
        assert "b01" in current
        assert len(current["b01"]) == 1
        assert current["b01"][0]["status"] == "available"

    def test_multiple_beats_grouped_separately(self, visual_service, tmp_db):
        """Candidates for different beats are grouped separately."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img1 = os.path.join(media_dir, "beat_a.png")
        img2 = os.path.join(media_dir, "beat_b.png")
        _make_minimal_png(img1, 100, 100)
        _make_minimal_png(img2, 200, 200)

        svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img1, "image", "b01", "capture",
        )
        svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img2, "image", "b02", "capture",
        )

        grouped = svc.list_visual_candidates("test_tenant", session["id"])
        assert "b01" in grouped
        assert "b02" in grouped
        assert len(grouped["b01"]) == 1
        assert len(grouped["b02"]) == 1


class TestFailedCandidatesRemainVisible:
    def test_failed_candidate_registered_and_visible(self, visual_service, tmp_db):
        """Failed candidates remain visible to the operator."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        candidate = svc.register_failed(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "b03", "generated_video",
            "Generation timed out after 30s",
            kind="video",
        )

        assert candidate["status"] == "failed"
        assert candidate["category"] == "visual_media"
        assert candidate["role"] == "beat_visual"

        # Failed candidate is visible in list
        grouped = svc.list_visual_candidates("test_tenant", session["id"])
        assert "b03" in grouped
        assert len(grouped["b03"]) == 1
        assert grouped["b03"][0]["status"] == "failed"

    def test_generating_candidate_remains_visible(self, visual_service, tmp_db):
        """Generating (in-progress) candidates remain visible."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        candidate = svc.register_generating(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], "b04", "generated_still",
            kind="image",
            generation_provenance={"job_id": "job_123"},
        )

        assert candidate["status"] == "generating"

        # Generating candidate is visible in list
        grouped = svc.list_visual_candidates("test_tenant", session["id"])
        assert "b04" in grouped
        assert grouped["b04"][0]["status"] == "generating"

        # Also visible in current (non-superseded) visuals
        current = svc.get_current_visuals("test_tenant", session["id"])
        assert "b04" in current
        assert current["b04"][0]["status"] == "generating"


class TestCrossSessionIsolation:
    def test_sessions_are_isolated(self, visual_service, tmp_db):
        """Candidates from one session don't appear in another."""
        svc, media_dir = visual_service
        session1, asset1 = _setup_session(tmp_db, "test_tenant")
        session2, asset2 = _setup_session(tmp_db, "other_tenant")

        img = os.path.join(media_dir, "iso.png")
        _make_minimal_png(img)

        svc.register_existing_media(
            "test_tenant", session1["id"], session1["draft_id"],
            asset1["id"], img, "image", "b01", "capture",
        )

        # Session 1 has the candidate
        grouped1 = svc.list_visual_candidates("test_tenant", session1["id"])
        assert "b01" in grouped1
        assert len(grouped1["b01"]) == 1

        # Session 2 has no visual candidates
        grouped2 = svc.list_visual_candidates("other_tenant", session2["id"])
        assert len(grouped2) == 0

    def test_business_slug_isolation(self, visual_service, tmp_db):
        """Candidates from one business don't appear for another."""
        svc, media_dir = visual_service
        session1, asset1 = _setup_session(tmp_db, "biz_a")
        session2, asset2 = _setup_session(tmp_db, "biz_b")

        img = os.path.join(media_dir, "biz_iso.png")
        _make_minimal_png(img)

        svc.register_existing_media(
            "biz_a", session1["id"], session1["draft_id"],
            asset1["id"], img, "image", "b01", "capture",
        )

        # biz_a sees it
        grouped_a = svc.list_visual_candidates("biz_a", session1["id"])
        assert len(grouped_a) == 1

        # biz_b does not
        grouped_b = svc.list_visual_candidates("biz_b", session2["id"])
        assert len(grouped_b) == 0


class TestRegisterFromAssetMedia:
    def test_register_from_asset_media_table(self, visual_service, tmp_db):
        """register_from_asset_media reads from the asset_media table."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        # Create a valid image
        img_path = os.path.join(media_dir, "asset_media_img.png")
        _make_minimal_png(img_path, 256, 256)

        # Insert into asset_media table
        from media_adapter import ASSET_MEDIA_SCHEMA
        conn = sqlite3.connect(tmp_db[0])
        conn.executescript(ASSET_MEDIA_SCHEMA)
        now = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO asset_media (asset_id, kind, path, model, prompt, "
            "cost_usd, beat_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (asset["id"], "image", img_path, "test-model", "a red square",
             0.05, "b01", now),
        )
        am_id = cursor.lastrowid
        conn.commit()
        conn.close()

        candidate = svc.register_from_asset_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], am_id, "b01",
        )

        assert candidate["status"] == "available"
        assert candidate["category"] == "visual_media"
        assert candidate["role"] == "beat_visual"
        assert candidate["artifact_path"] == img_path

        beat_refs = json.loads(candidate["beat_refs_json"])
        assert beat_refs == ["b01"]

        measurement = json.loads(candidate["measurement_json"])
        assert measurement["width"] == 256
        assert measurement["height"] == 256


class TestGetApprovedForBeat:
    def test_no_approved_returns_none(self, visual_service, tmp_db):
        """get_approved_for_beat returns None when nothing is approved."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "not_approved.png")
        _make_minimal_png(img)

        svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img, "image", "b01", "capture",
        )

        assert svc.get_approved_for_beat("test_tenant", session["id"], "b01") is None

    def test_approved_returns_candidate(self, visual_service, tmp_db):
        """get_approved_for_beat returns the approved candidate."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "approve_me.png")
        _make_minimal_png(img)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img, "image", "b01", "capture",
        )

        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=tmp_db[0])
        store.record_decision("test_tenant", session["id"], candidate["id"], "approve")

        approved = svc.get_approved_for_beat("test_tenant", session["id"], "b01")
        assert approved is not None
        assert approved["id"] == candidate["id"]
        assert approved["status"] == "approved"

    def test_approved_for_wrong_beat_returns_none(self, visual_service, tmp_db):
        """get_approved_for_beat for a different beat returns None."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "beat01_only.png")
        _make_minimal_png(img)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img, "image", "b01", "capture",
        )

        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=tmp_db[0])
        store.record_decision("test_tenant", session["id"], candidate["id"], "approve")

        assert svc.get_approved_for_beat("test_tenant", session["id"], "b02") is None


class TestInvalidSourceType:
    def test_invalid_source_type_fails(self, visual_service, tmp_db):
        """Invalid source type fails closed."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "bad_source.png")
        _make_minimal_png(img)

        with pytest.raises(Exception, match="Invalid source type"):
            svc.register_existing_media(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], img, "image", "b01", "random_source",
            )


class TestUnmeasuredFilesFailsClosed:
    def test_nonexistent_file_fails(self, visual_service, tmp_db):
        """Nonexistent file fails closed."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        with pytest.raises(Exception, match="file does not exist"):
            svc.register_existing_media(
                "test_tenant", session["id"], session["draft_id"],
                asset["id"], "/nonexistent/file.png", "image", "b01", "capture",
            )


class TestNoAutoSelection:
    def test_new_candidate_is_available_not_approved(self, visual_service, tmp_db):
        """No first-stock auto-selection — new candidates are 'available' not 'approved'."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "no_auto.png")
        _make_minimal_png(img)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img, "image", "b01", "capture",
        )

        assert candidate["status"] == "available"
        assert candidate["status"] != "approved"

    def test_no_auto_approval_on_registration(self, visual_service, tmp_db):
        """Even with cost_approved=True, status is 'available' not 'approved'."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "cost_approved.png")
        _make_minimal_png(img)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img, "image", "b01", "stock",
            cost_estimate_usd=5.00,
            cost_approved=True,
        )

        assert candidate["status"] == "available"
        assert candidate["cost_approved"] == 1  # cost is approved, but status is not


class TestPreviewWorks:
    def test_image_preview_path_is_artifact_path(self, visual_service, tmp_db):
        """Fullscreen image preview works — preview path is the artifact path."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        img = os.path.join(media_dir, "preview_img.png")
        _make_minimal_png(img, 480, 360)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], img, "image", "b01", "capture",
        )

        assert candidate["preview_path"] == candidate["artifact_path"]
        assert candidate["preview_hash"] == candidate["artifact_hash"]
        assert os.path.exists(candidate["preview_path"])

    def test_video_preview_path_is_artifact_path(self, visual_service, tmp_db):
        """Playable video preview works — preview path is the artifact path."""
        svc, media_dir = visual_service
        session, asset = _setup_session(tmp_db)

        vid = os.path.join(media_dir, "preview_vid.mp4")
        _make_minimal_mp4(vid, duration=1.0)

        candidate = svc.register_existing_media(
            "test_tenant", session["id"], session["draft_id"],
            asset["id"], vid, "video", "b01", "generated_video",
        )

        assert candidate["preview_path"] == candidate["artifact_path"]
        assert candidate["preview_hash"] == candidate["artifact_hash"]
        assert os.path.exists(candidate["preview_path"])