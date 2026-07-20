"""Immutable soundtrack mix versions from rights-valid local artifacts (VF-VS-514)."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from soundtrack_rights import SoundtrackRightsStore, validate_rights_record


class SoundtrackMixError(RuntimeError):
    """Raised when an exact mix set cannot be validated and activated."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_hash(value) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_duration(path: str) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip()) if result.returncode == 0 else 0.0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return 0.0


def _probe_loudness(path: str) -> dict:
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-i", path,
                "-af", "loudnorm=print_format=json", "-f", "null", "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        start = result.stderr.rfind("{")
        end = result.stderr.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(result.stderr[start:end])
            return {
                "input_i": float(data.get("input_i", -99)),
                "input_tp": float(data.get("input_tp", -99)),
                "input_lra": float(data.get("input_lra", 0)),
            }
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
        pass
    return {"input_i": -99.0, "input_tp": -99.0, "input_lra": 0.0}


def _phase_from_index(index: int) -> str:
    phases = ["intro", "build", "duck", "lift", "settle", "settle"]
    return phases[min(index, len(phases) - 1)]


def _build_volume_filter(
    energy_curve: list[dict],
    vo_timeline: list[dict],
    config: dict,
) -> str:
    """Build deterministic per-beat bed gain automation from configured values."""
    del energy_curve
    mixing = config.get("mixing", {})
    mapping = mixing.get("energy_curve_mapping", {})
    default = float(mixing.get("ducking", {}).get("default_depth", 0.20))
    segments = []
    for index, beat in enumerate(vo_timeline):
        start = float(beat.get("start_sec", 0))
        end = float(beat.get("end_sec", start + 5))
        phase = beat.get("energy_phase", _phase_from_index(index))
        segments.append((start, end, float(mapping.get(phase, default))))
    if not segments:
        return f"volume={default}"
    return ",".join(
        f"volume={volume:.2f}:enable='between(t,{start:.2f},{end:.2f})'"
        for start, end, volume in segments
    )


class SoundtrackMixStore:
    """Append-only candidate previews and finished mixes with atomic activation."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS soundtrack_mix_versions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mix_set_id TEXT NOT NULL,
        asset_id INTEGER NOT NULL,
        soundtrack_plan_id INTEGER NOT NULL,
        candidate_id TEXT NOT NULL,
        provider TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('preview', 'finished')),
        mix_version INTEGER NOT NULL,
        rights_record_id INTEGER NOT NULL,
        rights_hash TEXT NOT NULL,
        soundtrack_artifact_id INTEGER NOT NULL,
        soundtrack_artifact_hash TEXT NOT NULL,
        vo_hash TEXT NOT NULL,
        config_hash TEXT NOT NULL,
        local_path TEXT NOT NULL,
        output_hash TEXT NOT NULL,
        byte_size INTEGER NOT NULL,
        duration_seconds REAL NOT NULL,
        loudness_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(rights_record_id) REFERENCES soundtrack_rights(id),
        FOREIGN KEY(soundtrack_artifact_id) REFERENCES soundtrack_artifacts(id),
        UNIQUE(mix_set_id, candidate_id, kind),
        UNIQUE(asset_id, output_hash)
    );
    CREATE INDEX IF NOT EXISTS idx_soundtrack_mix_active
        ON soundtrack_mix_versions(asset_id, active, id);
    CREATE INDEX IF NOT EXISTS idx_soundtrack_mix_set
        ON soundtrack_mix_versions(asset_id, mix_set_id, candidate_id, kind);
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        SoundtrackRightsStore(db_path)
        with sqlite3.connect(db_path) as conn:
            conn.executescript(self.SCHEMA)

    def list_versions(self, asset_id: int, mix_set_id: str) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(self.SCHEMA)
            rows = conn.execute(
                """SELECT * FROM soundtrack_mix_versions
                   WHERE asset_id = ? AND mix_set_id = ? ORDER BY id""",
                (asset_id, mix_set_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_active_version(self, asset_id: int) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(self.SCHEMA)
            row = conn.execute(
                """SELECT * FROM soundtrack_mix_versions
                   WHERE asset_id = ? AND active = 1 ORDER BY id DESC LIMIT 1""",
                (asset_id,),
            ).fetchone()
        return dict(row) if row else None

    def activate_candidate(
        self, asset_id: int, mix_set_id: str, candidate_id: str
    ) -> dict:
        """Atomically activate one validated finished mix from the exact set."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(self.SCHEMA)
            row = conn.execute(
                """SELECT * FROM soundtrack_mix_versions
                   WHERE asset_id = ? AND mix_set_id = ? AND candidate_id = ?
                     AND kind = 'finished'""",
                (asset_id, mix_set_id, candidate_id),
            ).fetchone()
            if not row:
                raise SoundtrackMixError("validated finished candidate mix not found")
            path = str(row["local_path"])
            if not os.path.isfile(path) or _file_hash(path) != row["output_hash"]:
                raise SoundtrackMixError("finished candidate mix failed identity validation")
            conn.execute(
                "UPDATE soundtrack_mix_versions SET active = 0 WHERE asset_id = ?",
                (asset_id,),
            )
            conn.execute(
                "UPDATE soundtrack_mix_versions SET active = 1 WHERE id = ?",
                (int(row["id"]),),
            )
            active = dict(row)
            active["active"] = 1
            return active


def _selected_candidate_ids(ranking: dict, maximum: int) -> list[str]:
    recommended = ranking.get("recommended")
    if not isinstance(recommended, dict) or not recommended.get("candidate_id"):
        raise SoundtrackMixError("ranking has no recommended candidate")
    ids = [recommended["candidate_id"]]
    ids.extend(
        item.get("candidate_id")
        for item in ranking.get("alternatives", [])[:maximum]
        if isinstance(item, dict) and item.get("candidate_id")
    )
    if len(ids) != len(set(ids)):
        raise SoundtrackMixError("ranking candidate IDs must be unique")
    return ids


def _load_exact_artifact(
    db_path: str,
    asset_id: int,
    soundtrack_plan_id: int,
    candidate: dict,
) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT a.*, r.rights_hash, r.rights_json
               FROM soundtrack_artifacts a
               JOIN soundtrack_rights r ON r.id = a.rights_record_id
               WHERE a.id = ? AND a.asset_id = ? AND a.soundtrack_plan_id = ?
                 AND a.rights_record_id = ? AND a.candidate_id = ?""",
            (
                candidate.get("artifact_id"), asset_id, soundtrack_plan_id,
                candidate.get("rights_record_id"), candidate.get("candidate_id"),
            ),
        ).fetchone()
    if not row:
        raise SoundtrackMixError("exact soundtrack artifact/rights binding not found")
    artifact = dict(row)
    rights = json.loads(artifact.pop("rights_json"))
    if validate_rights_record(rights):
        raise SoundtrackMixError("soundtrack rights are no longer render-eligible")
    persisted_rights_hash = hashlib.sha256(
        json.dumps(rights, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    if persisted_rights_hash != artifact["rights_hash"]:
        raise SoundtrackMixError("persisted rights snapshot failed identity validation")
    if candidate.get("provider") != artifact["provider"]:
        raise SoundtrackMixError("candidate provider does not match local artifact")
    if candidate.get("rights_hash") != artifact["rights_hash"]:
        raise SoundtrackMixError("candidate rights hash does not match persisted evidence")
    if candidate.get("artifact_hash") != artifact["content_hash"]:
        raise SoundtrackMixError("candidate artifact hash does not match persisted evidence")
    path = artifact["local_path"]
    if not os.path.isfile(path) or _file_hash(path) != artifact["content_hash"]:
        raise SoundtrackMixError("local soundtrack artifact failed identity validation")
    if _probe_duration(path) <= 0:
        raise SoundtrackMixError("local soundtrack artifact has no measurable duration")
    return artifact


def _run(command: list[str], label: str) -> None:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SoundtrackMixError(f"{label} failed: {exc}") from exc
    if result.returncode != 0:
        raise SoundtrackMixError(f"{label} failed: {result.stderr[-300:]}")


def _render_candidate(
    vo_path: str,
    bed_path: str,
    duration: float,
    volume_filter: str,
    mixing: dict,
    bitrate: str,
    output_path: str,
) -> None:
    """Normalize inputs separately, then mix without loudnorm in filter_complex."""
    target = float(mixing.get("final_target_loudness_lufs", -14))
    bed_target = float(mixing.get("bed_target_loudness_lufs", -18))
    work_dir = os.path.dirname(output_path)
    vo_fd, vo_normalized = tempfile.mkstemp(prefix="vo-norm-", suffix=".wav", dir=work_dir)
    bed_fd, bed_normalized = tempfile.mkstemp(prefix="bed-norm-", suffix=".wav", dir=work_dir)
    os.close(vo_fd)
    os.close(bed_fd)
    try:
        _run(
            [
                "ffmpeg", "-y", "-i", vo_path, "-af",
                f"loudnorm=I={target}:TP=-1.0:LRA=11", "-t", f"{duration:.3f}",
                vo_normalized,
            ],
            "VO normalization",
        )
        _run(
            [
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", bed_path,
                "-af", f"atrim=0:{duration:.3f},loudnorm=I={bed_target}:TP=-1.5:LRA=11,{volume_filter}",
                "-t", f"{duration:.3f}", bed_normalized,
            ],
            "bed normalization",
        )
        _run(
            [
                "ffmpeg", "-y", "-i", vo_normalized, "-i", bed_normalized,
                "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map", "[aout]", "-c:a", "aac", "-b:a", bitrate,
                "-t", f"{duration:.3f}", output_path,
            ],
            "soundtrack mix",
        )
    finally:
        for path in (vo_normalized, bed_normalized):
            if os.path.exists(path):
                os.remove(path)


def create_mix_versions(
    db_path: str,
    asset_id: int,
    soundtrack_plan_id: int,
    vo_path: str,
    vo_timeline: list[dict],
    energy_curve: list[dict],
    ranking: dict,
    candidates: list[dict],
    config: dict,
    media_root: str,
) -> dict:
    """Build and atomically persist one top pick plus configured alternatives."""
    store = SoundtrackMixStore(db_path)
    if not os.path.isfile(vo_path):
        raise SoundtrackMixError("approved VO artifact not found")
    vo_hash = _file_hash(vo_path)
    vo_duration = _probe_duration(vo_path)
    if vo_duration <= 0:
        raise SoundtrackMixError("approved VO has no measurable duration")
    mixing = config.get("mixing")
    if not isinstance(mixing, dict):
        raise SoundtrackMixError("soundtrack mixing config is required")
    maximum = int(mixing.get("max_alternatives", 3))
    selected_ids = _selected_candidate_ids(ranking, maximum)
    by_id = {item.get("candidate_id"): item for item in candidates}
    if any(candidate_id not in by_id for candidate_id in selected_ids):
        raise SoundtrackMixError("ranking references a candidate outside supplied evidence")
    exact = [
        (by_id[candidate_id], _load_exact_artifact(
            db_path, asset_id, soundtrack_plan_id, by_id[candidate_id],
        ))
        for candidate_id in selected_ids
    ]
    config_hash = _canonical_hash(mixing)
    mix_set_id = _canonical_hash({
        "asset_id": asset_id,
        "soundtrack_plan_id": soundtrack_plan_id,
        "vo_hash": vo_hash,
        "candidate_artifact_hashes": [artifact["content_hash"] for _, artifact in exact],
        "rights_hashes": [artifact["rights_hash"] for _, artifact in exact],
        "config_hash": config_hash,
        "vo_timeline": vo_timeline,
        "energy_curve": energy_curve,
    })
    existing = store.list_versions(asset_id, mix_set_id)
    if existing:
        expected = len(selected_ids) * 2
        if len(existing) != expected:
            raise SoundtrackMixError("existing immutable mix set is incomplete")
        active = store.get_active_version(asset_id)
        return {
            "mix_set_id": mix_set_id,
            "active_candidate_id": (
                active["candidate_id"]
                if active and active["mix_set_id"] == mix_set_id else None
            ),
            "candidates": selected_ids,
            "reused": True,
        }

    output_dir = Path(media_root) / str(asset_id) / "soundtrack-mixes" / mix_set_id
    output_dir.mkdir(parents=True, exist_ok=True)
    volume_filter = _build_volume_filter(energy_curve, vo_timeline, config)
    tolerance = float(mixing.get("duration_tolerance_s", 0.15))
    generated = []
    created_paths: list[str] = []
    try:
        for candidate, artifact in exact:
            for kind, bitrate in (
                ("preview", str(mixing.get("preview_bitrate", "96k"))),
                ("finished", str(mixing.get("finished_bitrate", "192k"))),
            ):
                fd, temp_path = tempfile.mkstemp(
                    prefix=f"{candidate['candidate_id']}-{kind}-",
                    suffix=".m4a",
                    dir=output_dir,
                )
                os.close(fd)
                try:
                    _render_candidate(
                        vo_path, artifact["local_path"], vo_duration, volume_filter,
                        mixing, bitrate, temp_path,
                    )
                    duration = _probe_duration(temp_path)
                    if abs(duration - vo_duration) > tolerance:
                        raise SoundtrackMixError(
                            f"{kind} duration does not match approved VO"
                        )
                    loudness = _probe_loudness(temp_path)
                    if loudness["input_i"] <= -99:
                        raise SoundtrackMixError(f"{kind} loudness is not measurable")
                    output_hash = _file_hash(temp_path)
                    final_path = output_dir / f"{output_hash}.m4a"
                    existed = final_path.exists()
                    os.replace(temp_path, final_path)
                    if not existed:
                        created_paths.append(str(final_path))
                    generated.append({
                        "candidate": candidate,
                        "artifact": artifact,
                        "kind": kind,
                        "local_path": str(final_path),
                        "output_hash": output_hash,
                        "byte_size": final_path.stat().st_size,
                        "duration_seconds": duration,
                        "loudness_json": json.dumps(loudness, sort_keys=True),
                    })
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(store.SCHEMA)
            for item in generated:
                candidate = item["candidate"]
                artifact = item["artifact"]
                row = conn.execute(
                    """SELECT COALESCE(MAX(mix_version), 0) AS version
                       FROM soundtrack_mix_versions
                       WHERE asset_id = ? AND candidate_id = ? AND kind = ?""",
                    (asset_id, candidate["candidate_id"], item["kind"]),
                ).fetchone()
                conn.execute(
                    """INSERT INTO soundtrack_mix_versions
                       (mix_set_id, asset_id, soundtrack_plan_id, candidate_id,
                        provider, kind, mix_version, rights_record_id, rights_hash,
                        soundtrack_artifact_id, soundtrack_artifact_hash, vo_hash,
                        config_hash, local_path, output_hash, byte_size,
                        duration_seconds, loudness_json, created_at, active)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                    (
                        mix_set_id, asset_id, soundtrack_plan_id,
                        candidate["candidate_id"], artifact["provider"], item["kind"],
                        int(row["version"]) + 1, artifact["rights_record_id"],
                        artifact["rights_hash"], artifact["id"], artifact["content_hash"],
                        vo_hash, config_hash, item["local_path"], item["output_hash"],
                        item["byte_size"], item["duration_seconds"],
                        item["loudness_json"], _now(),
                    ),
                )
        active = store.activate_candidate(asset_id, mix_set_id, selected_ids[0])
        return {
            "mix_set_id": mix_set_id,
            "active_candidate_id": active["candidate_id"],
            "candidates": selected_ids,
            "reused": False,
        }
    except Exception:
        for path in created_paths:
            if os.path.exists(path):
                os.remove(path)
        raise
