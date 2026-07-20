"""VF-VS-511 rights evidence and local soundtrack acquisition."""

from __future__ import annotations

import sqlite3
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from soundtrack_rights import (
    RightsValidationError,
    SoundtrackRightsStore,
    acquire_rights_valid_track,
    validate_rights_record,
)


def _rights(**overrides):
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


def _write_wav(path: Path, seconds: float = 1.0):
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * int(8000 * seconds))


@pytest.mark.parametrize("field,value", [
    ("rights_status", "unknown"),
    ("rights_status", "restricted"),
    ("rights_status", "expired"),
    ("commercial_use_allowed", False),
    ("synchronization_allowed", False),
    ("download_authorized", False),
    ("terms_evidence_hash", "not-a-sha256"),
])
def test_non_render_eligible_rights_fail_closed(field, value):
    errors = validate_rights_record(_rights(**{field: value}))
    assert errors


def test_paid_rights_require_fresh_cost_approval_record():
    errors = validate_rights_record(_rights(cost_usd=4.0, cost_approval_id=None))
    assert any("cost approval" in error.lower() for error in errors)


@pytest.mark.parametrize("field,value", [
    ("platform_constraints", "instagram"),
    ("territory_constraints", [""]),
    ("account_type_constraints", None),
    ("attribution_required", "false"),
])
def test_rights_constraints_require_typed_evidence(field, value):
    assert validate_rights_record(_rights(**{field: value}))


def test_required_attribution_must_include_persistable_text():
    errors = validate_rights_record(
        _rights(attribution_required=True, attribution_text=None)
    )
    assert any("attribution_text" in error for error in errors)


def test_rights_records_are_versioned_and_terms_snapshot_survives_url_expiry(tmp_path):
    store = SoundtrackRightsStore(str(tmp_path / "pipeline.db"))
    first = store.save_rights_record(
        asset_id=11,
        soundtrack_plan_id=21,
        record=_rights(),
    )
    second = store.save_rights_record(
        asset_id=11,
        soundtrack_plan_id=21,
        record=_rights(terms_url="https://expired.invalid/signed?token=secret"),
    )

    assert first["rights_version"] == 1
    assert second["rights_version"] == 2
    persisted = store.get_rights_record(first["rights_record_id"])
    assert persisted["terms_evidence_hash"] == "a" * 64
    assert "token" not in store.get_rights_record(second["rights_record_id"])["terms_url"]


def test_rights_valid_fixture_acquires_nonempty_hashed_local_artifact(tmp_path):
    db_path = str(tmp_path / "pipeline.db")
    store = SoundtrackRightsStore(db_path)
    rights = store.save_rights_record(11, 21, _rights())

    def downloader(_url, destination):
        _write_wav(Path(destination), seconds=1.25)

    result = acquire_rights_valid_track(
        db_path=db_path,
        asset_id=11,
        soundtrack_plan_id=21,
        rights_record_id=rights["rights_record_id"],
        candidate={
            "candidate_id": "pixabay:track-7",
            "provider": "pixabay",
            "download_url": "https://cdn.invalid/audio.wav?token=secret",
        },
        media_root=str(tmp_path / "media"),
        downloader=downloader,
    )

    assert result["status"] == "render_ready"
    assert Path(result["local_path"]).is_file()
    assert result["content_hash"] and len(result["content_hash"]) == 64
    assert result["duration_seconds"] > 1.0
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT source_url, rights_record_id, content_hash FROM soundtrack_artifacts"
        ).fetchone()
    assert "token" not in row[0]
    assert row[1] == rights["rights_record_id"]
    assert row[2] == result["content_hash"]


def test_failed_download_does_not_replace_last_valid_artifact(tmp_path):
    db_path = str(tmp_path / "pipeline.db")
    store = SoundtrackRightsStore(db_path)
    rights = store.save_rights_record(11, 21, _rights())

    def valid_download(_url, destination):
        _write_wav(Path(destination))

    first = acquire_rights_valid_track(
        db_path, 11, 21, rights["rights_record_id"],
        {"candidate_id": "pixabay:track-7", "provider": "pixabay", "download_url": "https://cdn.invalid/a.wav"},
        str(tmp_path / "media"), valid_download,
    )

    def empty_download(_url, destination):
        Path(destination).write_bytes(b"")

    with pytest.raises(RightsValidationError):
        acquire_rights_valid_track(
            db_path, 11, 21, rights["rights_record_id"],
            {"candidate_id": "pixabay:track-8", "provider": "pixabay", "download_url": "https://cdn.invalid/b.wav"},
            str(tmp_path / "media"), empty_download,
        )

    assert store.get_active_artifact(11)["content_hash"] == first["content_hash"]


def test_social_discovery_candidate_has_no_inferred_commercial_rights():
    from soundtrack_discovery import _make_candidate

    candidate = _make_candidate(
        source="bundle_instagram",
        external_id="ig-1",
        title="Observed sound",
        artist="Creator",
        duration_s=30,
        preview_url="https://example.invalid/preview",
        download_url="https://example.invalid/audio",
        license_type="",
    )
    assert "commercial_safe" not in candidate
    assert candidate["rights_status"] == "unknown"


def test_pipeline_store_initializes_rights_tables_for_every_writer(tmp_path):
    from pipeline import PipelineStore

    db_path = str(tmp_path / "pipeline.db")
    PipelineStore(db_path)
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"soundtrack_rights", "soundtrack_artifacts"} <= tables
