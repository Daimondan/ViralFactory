"""VF-VS-514 immutable soundtrack mix versions and alternatives."""

from pathlib import Path
import hashlib
import json
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from soundtrack_mix import (
    SoundtrackMixError,
    SoundtrackMixStore,
    create_mix_versions,
)
from soundtrack_rights import SoundtrackRightsStore
from pipeline import PipelineStore


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _tone(path, frequency, duration=2.0):
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            f"sine=frequency={frequency}:duration={duration}",
            "-c:a", "pcm_s16le", str(path),
        ],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0


def _seed_artifact(db_path, tmp_path, asset_id, index, provider):
    path = tmp_path / f"bed-{index}.wav"
    _tone(path, 300 + index * 100, duration=3.0)
    content_hash = _sha(path)
    now = "2026-07-20T00:00:00+00:00"
    rights_record = {
        "candidate_id": f"track-{index}",
        "rights_source": "fixture",
        "terms_url": "https://terms.invalid",
        "terms_retrieved_at": now,
        "terms_evidence_hash": "a" * 64,
        "acquisition_method": "fixture",
        "rights_status": "verified",
        "commercial_use_allowed": True,
        "synchronization_allowed": True,
        "download_authorized": True,
        "platform_constraints": [],
        "territory_constraints": [],
        "account_type_constraints": [],
        "attribution_required": False,
        "attribution_text": None,
        "expires_at": None,
        "cost_usd": 0,
        "cost_approval_id": None,
    }
    rights_json = json.dumps(rights_record, sort_keys=True, ensure_ascii=False)
    rights_hash = hashlib.sha256(rights_json.encode()).hexdigest()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """INSERT INTO soundtrack_rights
               (asset_id, soundtrack_plan_id, candidate_id, rights_version,
                rights_json, rights_hash, terms_url, terms_evidence_hash, created_at)
               VALUES (?, 77, ?, 1, ?, ?, 'https://terms.invalid', ?, ?)""",
            (
                asset_id, f"track-{index}", rights_json, rights_hash,
                "a" * 64, now,
            ),
        )
        rights_id = cursor.lastrowid
        cursor = conn.execute(
            """INSERT INTO soundtrack_artifacts
               (asset_id, soundtrack_plan_id, rights_record_id, candidate_id,
                provider, source_url, local_path, content_hash, byte_size,
                duration_seconds, acquisition_method, acquired_at, active)
               VALUES (?, 77, ?, ?, ?, '', ?, ?, ?, 3.0, 'fixture', ?, 0)""",
            (
                asset_id, rights_id, f"track-{index}", provider, str(path),
                content_hash, path.stat().st_size, now,
            ),
        )
        artifact_id = cursor.lastrowid
    return {
        "candidate_id": f"track-{index}",
        "provider": provider,
        "rights_record_id": rights_id,
        "rights_hash": rights_hash,
        "artifact_id": artifact_id,
        "artifact_hash": content_hash,
    }


@pytest.fixture
def mix_fixture(tmp_path):
    db_path = str(tmp_path / "mix.db")
    SoundtrackRightsStore(db_path)
    SoundtrackMixStore(db_path)
    vo_path = tmp_path / "vo.wav"
    _tone(vo_path, 900)
    candidates = [
        _seed_artifact(db_path, tmp_path, 9, 1, "catalog-a"),
        _seed_artifact(db_path, tmp_path, 9, 2, "catalog-a"),
        _seed_artifact(db_path, tmp_path, 9, 3, "catalog-b"),
        _seed_artifact(db_path, tmp_path, 9, 4, "catalog-b"),
    ]
    ranking = {
        "recommended": {"candidate_id": "track-1"},
        "alternatives": [
            {"candidate_id": "track-2"},
            {"candidate_id": "track-3"},
            {"candidate_id": "track-4"},
        ],
    }
    config = {
        "mixing": {
            "bed_target_loudness_lufs": -18,
            "final_target_loudness_lufs": -14,
            "preview_bitrate": "96k",
            "finished_bitrate": "192k",
            "max_alternatives": 3,
            "duration_tolerance_s": 0.15,
            "ducking": {"default_depth": 0.20},
            "energy_curve_mapping": {"intro": 0.25},
        }
    }
    return db_path, vo_path, candidates, ranking, config, tmp_path / "media"


def test_top_pick_and_three_alternatives_have_immutable_playable_versions(mix_fixture):
    db_path, vo_path, candidates, ranking, config, media_root = mix_fixture
    result = create_mix_versions(
        db_path=db_path,
        asset_id=9,
        soundtrack_plan_id=77,
        vo_path=str(vo_path),
        vo_timeline=[{"start_sec": 0, "end_sec": 2, "energy_phase": "intro"}],
        energy_curve=[],
        ranking=ranking,
        candidates=candidates,
        config=config,
        media_root=str(media_root),
    )

    assert len(result["candidates"]) == 4
    assert result["active_candidate_id"] == "track-1"
    rows = SoundtrackMixStore(db_path).list_versions(9, result["mix_set_id"])
    assert len(rows) == 8
    assert {row["kind"] for row in rows} == {"preview", "finished"}
    assert len({row["output_hash"] for row in rows}) == 8
    assert {row["provider"] for row in rows if row["candidate_id"] == "track-4"} == {
        "catalog-b"
    }
    assert all(Path(row["local_path"]).exists() for row in rows)
    assert all(row["duration_seconds"] == pytest.approx(2.0, abs=0.15) for row in rows)
    assert sum(row["active"] for row in rows) == 1
    assert next(row for row in rows if row["active"])["candidate_id"] == "track-1"
    assert all(row["vo_hash"] == _sha(vo_path) for row in rows)
    assert all(row["rights_hash"] in {item["rights_hash"] for item in candidates} for row in rows)


def test_switching_each_alternative_activates_distinct_validated_finished_hash(mix_fixture):
    db_path, vo_path, candidates, ranking, config, media_root = mix_fixture
    result = create_mix_versions(
        db_path, 9, 77, str(vo_path), [], [], ranking, candidates, config,
        str(media_root),
    )
    store = SoundtrackMixStore(db_path)
    hashes = []
    for candidate_id in ("track-2", "track-3", "track-4"):
        active = store.activate_candidate(9, result["mix_set_id"], candidate_id)
        hashes.append(active["output_hash"])
        assert active["kind"] == "finished"
        assert active["active"] == 1
    assert len(set(hashes)) == 3


def test_failed_replacement_preserves_previous_active_mix(mix_fixture):
    db_path, vo_path, candidates, ranking, config, media_root = mix_fixture
    first = create_mix_versions(
        db_path, 9, 77, str(vo_path), [], [], ranking, candidates, config,
        str(media_root),
    )
    store = SoundtrackMixStore(db_path)
    previous = store.get_active_version(9)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE soundtrack_artifacts SET local_path = ? WHERE id = ?",
            (str(media_root / "missing.wav"), candidates[1]["artifact_id"]),
        )
    with pytest.raises(SoundtrackMixError):
        create_mix_versions(
            db_path, 9, 77, str(vo_path), [], [], ranking, candidates, config,
            str(media_root),
        )
    assert store.get_active_version(9)["id"] == previous["id"]
    assert store.get_active_version(9)["mix_set_id"] == first["mix_set_id"]


def test_retry_same_inputs_reuses_versions_without_overwrite(mix_fixture):
    db_path, vo_path, candidates, ranking, config, media_root = mix_fixture
    first = create_mix_versions(
        db_path, 9, 77, str(vo_path), [], [], ranking, candidates, config,
        str(media_root),
    )
    mtimes = {
        row["local_path"]: Path(row["local_path"]).stat().st_mtime_ns
        for row in SoundtrackMixStore(db_path).list_versions(9, first["mix_set_id"])
    }
    switched = SoundtrackMixStore(db_path).activate_candidate(
        9, first["mix_set_id"], "track-3"
    )
    second = create_mix_versions(
        db_path, 9, 77, str(vo_path), [], [], ranking, candidates, config,
        str(media_root),
    )
    assert second["mix_set_id"] == first["mix_set_id"]
    assert second["active_candidate_id"] == "track-3"
    assert SoundtrackMixStore(db_path).get_active_version(9)["id"] == switched["id"]
    assert len(SoundtrackMixStore(db_path).list_versions(9, first["mix_set_id"])) == 8
    assert {
        path: Path(path).stat().st_mtime_ns for path in mtimes
    } == mtimes


def test_pipeline_store_initializes_mix_version_schema(tmp_path):
    db_path = str(tmp_path / "pipeline.db")
    PipelineStore(db_path)
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "soundtrack_mix_versions" in tables
