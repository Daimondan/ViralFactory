"""
ViralFactory — Asset Review Layer

Per CORRECTION-final-output-review-and-audio-fix-v1.0 Part 2:
- Mechanical post-render checks (ASSET-REVIEW-1): deterministic ffprobe checks
  after every render — file size, duration, stream presence, resolution, SAR.
- Vision-based visual inspection (ASSET-REVIEW-2): keyframe extraction + vision
  LLM examines frames vs content.
- Audio inspection (ASSET-REVIEW-3): whisper transcription + loop detection.
- Content alignment (ASSET-REVIEW-4): aggregates all checks into a single verdict.
- Image review (ASSET-REVIEW-6): lightweight vision check on standalone images.

The review is advisory, not blocking. The operator is always the final gate.
Every LLM call goes through the adapter with full provenance.
"""

import json
import os
import subprocess
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

# Support both package and direct imports
try:
    from .provenance import ProvenanceLog
except ImportError:
    from provenance import ProvenanceLog


ASSET_REVIEW_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    media_id INTEGER NOT NULL,          -- asset_media row this review is about
    media_path TEXT NOT NULL,
    review_type TEXT NOT NULL,           -- mechanical | visual | audio | alignment | image
    status TEXT NOT NULL,                -- pending | running | complete | failed
    verdict TEXT,                        -- pass | issues_found | ready_for_operator | needs_rerender
    findings_json TEXT,                  -- full JSON findings
    summary TEXT,                        -- plain-language summary for operator
    model TEXT,                          -- model used (for LLM-based reviews)
    prompt_file TEXT,                    -- prompt file used (for LLM-based reviews)
    prompt_version TEXT,                 -- prompt version
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id),
    FOREIGN KEY (media_id) REFERENCES asset_media(id)
);

CREATE INDEX IF NOT EXISTS idx_asset_reviews_asset ON asset_reviews(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_reviews_media ON asset_reviews(media_id);
CREATE INDEX IF NOT EXISTS idx_asset_reviews_type ON asset_reviews(review_type);
"""


class AssetReviewer:
    """
    Runs mechanical + AI checks on rendered output.

    Usage:
        reviewer = AssetReviewer(models_config, db_path="data/viralfactory.db")
        review = reviewer.review_render(output_path, plan, asset_id, media_id)
        # review = {"verdict": "pass", "summary": "...", "findings": {...}}
    """

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config
        self.db_path = db_path
        self.provenance = ProvenanceLog(db_path)
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(ASSET_REVIEW_SCHEMA)
        conn.commit()
        conn.close()

    # ── ffprobe helpers (shared with assembly.py but standalone) ─────────

    def _probe(self, file_path: str) -> dict:
        """Run ffprobe and return full stream/format info."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", file_path],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return {}
            return json.loads(result.stdout)
        except Exception:
            return {}

    def _get_duration(self, file_path: str) -> float:
        data = self._probe(file_path)
        return float(data.get("format", {}).get("duration", 0))

    def _has_stream(self, file_path: str, codec_type: str) -> bool:
        data = self._probe(file_path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == codec_type:
                return True
        return False

    def _get_resolution(self, file_path: str) -> tuple:
        data = self._probe(file_path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return (int(stream.get("width", 0)), int(stream.get("height", 0)))
        return (0, 0)

    def _get_sar(self, file_path: str) -> str:
        data = self._probe(file_path)
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                return stream.get("sample_aspect_ratio", "1:1")
        return "1:1"

    def _is_silent_audio(self, file_path: str) -> bool:
        """Check if the audio track is silent (all zeros or -inf mean volume)."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-i", file_path, "-vn", "-ac", "1",
                 "-af", "volumedetect", "-f", "null", "-"],
                capture_output=True, text=True, timeout=60,
            )
            for line in result.stderr.split("\n"):
                if "mean_volume" in line:
                    vol_str = line.split("mean_volume:")[1].strip()
                    if vol_str == "-inf":
                        return True
                    vol_db = float(vol_str.replace(" dB", ""))
                    return vol_db < -50
            return True  # No audio at all = silent
        except Exception:
            return True

    # ── ASSET-REVIEW-1: Mechanical post-render checks ────────────────────

    def run_mechanical_checks(self, file_path: str, plan: dict) -> dict:
        """Run deterministic ffprobe-based checks on the rendered output.

        No LLM calls — pure mechanical. Returns a findings dict.
        """
        checks = {
            "file_exists": os.path.exists(file_path),
            "file_size_kb": 0,
            "duration_s": 0,
            "has_video_stream": False,
            "has_audio_stream": False,
            "resolution": [0, 0],
            "sar": "1:1",
            "warnings": [],
        }

        if not checks["file_exists"]:
            checks["warnings"].append("Output file does not exist")
            return checks

        checks["file_size_kb"] = round(os.path.getsize(file_path) / 1024, 1)

        if checks["file_size_kb"] < 1:
            checks["warnings"].append("Output file is less than 1KB — likely corrupt")

        checks["duration_s"] = round(self._get_duration(file_path), 1)
        checks["has_video_stream"] = self._has_stream(file_path, "video")
        checks["has_audio_stream"] = self._has_stream(file_path, "audio")
        checks["resolution"] = list(self._get_resolution(file_path))
        checks["sar"] = self._get_sar(file_path)

        # Compare to plan
        canvas = plan.get("canvas", {})
        plan_duration = canvas.get("duration_target", 0)
        plan_resolution = canvas.get("resolution", "")

        if plan_duration and checks["duration_s"] > 0:
            duration_diff = abs(checks["duration_s"] - plan_duration)
            if duration_diff > 2.0:
                checks["warnings"].append(
                    f"Duration mismatch: output is {checks['duration_s']}s, "
                    f"plan target is {plan_duration}s (diff: {duration_diff:.1f}s)"
                )

        if plan_resolution and checks["resolution"] != [0, 0]:
            plan_w, plan_h = plan_resolution.split("x")
            plan_res = [int(plan_w), int(plan_h)]
            if checks["resolution"] != plan_res:
                checks["warnings"].append(
                    f"Resolution mismatch: output is {checks['resolution'][0]}x{checks['resolution'][1]}, "
                    f"plan target is {plan_res[0]}x{plan_res[1]}"
                )

        # Audio expectations vs reality
        audio_block = plan.get("audio", {})
        original_audio = audio_block.get("original_audio", False)
        music = audio_block.get("music", {})
        music_ref = music.get("stock_ref") if music else None
        expects_sound = original_audio or bool(music_ref)

        if expects_sound and checks["has_audio_stream"]:
            if self._is_silent_audio(file_path):
                checks["warnings"].append(
                    "Audio expected (original_audio or music) but output audio is silent"
                )
        elif not expects_sound and checks["has_audio_stream"]:
            if not self._is_silent_audio(file_path):
                checks["warnings"].append(
                    "Plan says no audio (original_audio=false, no music) but output has non-silent audio"
                )
        elif expects_sound and not checks["has_audio_stream"]:
            checks["warnings"].append(
                "Audio expected but output has no audio stream"
            )

        return checks

    def _save_review(self, asset_id: int, media_id: int, media_path: str,
                     review_type: str, status: str, verdict: str,
                     findings: dict, summary: str,
                     model: str = None, prompt_file: str = None,
                     prompt_version: str = None) -> int:
        """Save a review result to the asset_reviews table."""
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """INSERT INTO asset_reviews
               (asset_id, media_id, media_path, review_type, status, verdict,
                findings_json, summary, model, prompt_file, prompt_version,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, media_id, media_path, review_type, status, verdict,
             json.dumps(findings), summary, model, prompt_file, prompt_version,
             ts, ts),
        )
        review_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return review_id

    def _log_provenance(self, asset_id: int, review_type: str,
                        message: str, verdict: str,
                        model: str = "mechanical", provider: str = "local",
                        prompt_file: str = "(asset_review)", prompt_version: str = "1.0",
                        business_slug: str = None):
        """Log review to provenance."""
        import hashlib
        self.provenance.log(
            input_hash=hashlib.sha256(f"review:{review_type}:{asset_id}".encode()).hexdigest(),
            prompt_file=prompt_file,
            prompt_version=prompt_version,
            model=model,
            provider=provider,
            raw_output=message,
            validated_output={"asset_id": asset_id, "review_type": review_type, "message": message},
            validator_verdict=verdict,
            context=f"Asset review ({review_type}) for asset {asset_id}",
            temperature=0,
            business_slug=business_slug,
        )

    def review_render(self, output_path: str, plan: dict, asset_id: int,
                      media_id: int, business_slug: str = None) -> dict:
        """Run mechanical checks on a rendered video.

        This is the entry point called after render completes.
        Returns the mechanical check findings + saved review record.
        """
        findings = self.run_mechanical_checks(output_path, plan)

        verdict = "pass" if not findings["warnings"] else "issues_found"
        summary = self._mechanical_summary(findings)

        review_id = self._save_review(
            asset_id=asset_id,
            media_id=media_id,
            media_path=output_path,
            review_type="mechanical",
            status="complete",
            verdict=verdict,
            findings=findings,
            summary=summary,
        )

        self._log_provenance(
            asset_id, "mechanical",
            f"Mechanical checks: {verdict}. {summary}",
            verdict, business_slug=business_slug,
        )

        return {
            "review_id": review_id,
            "review_type": "mechanical",
            "verdict": verdict,
            "findings": findings,
            "summary": summary,
        }

    def _mechanical_summary(self, findings: dict) -> str:
        """Generate a plain-language summary of mechanical check results."""
        parts = []
        parts.append(f"File: {findings['file_size_kb']}KB")
        if findings["duration_s"]:
            parts.append(f"Duration: {findings['duration_s']}s")
        if findings["resolution"] != [0, 0]:
            parts.append(f"Resolution: {findings['resolution'][0]}×{findings['resolution'][1]}")
        parts.append(f"Video stream: {'yes' if findings['has_video_stream'] else 'no'}")
        parts.append(f"Audio stream: {'yes' if findings['has_audio_stream'] else 'no'}")

        if findings["warnings"]:
            parts.append(f"Warnings: {'; '.join(findings['warnings'])}")
        else:
            parts.append("All mechanical checks passed")

        return ". ".join(parts)

    # ── Query helpers for UI ──────────────────────────────────────────────

    def get_reviews_for_media(self, media_id: int) -> list:
        """Get all reviews for a specific media item."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM asset_reviews WHERE media_id = ? ORDER BY created_at DESC",
            (media_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_reviews_for_asset(self, asset_id: int) -> list:
        """Get all reviews for an asset (across all media items)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM asset_reviews WHERE asset_id = ? ORDER BY created_at DESC",
            (asset_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_latest_review_summary(self, media_id: int) -> Optional[dict]:
        """Get the latest review summary for a media item (for UI display)."""
        reviews = self.get_reviews_for_media(media_id)
        if not reviews:
            return None
        # Prefer alignment > mechanical > visual > audio
        type_priority = {"alignment": 0, "mechanical": 1, "visual": 2, "audio": 3, "image": 4}
        reviews.sort(key=lambda r: type_priority.get(r.get("review_type", ""), 99))
        latest = reviews[0]
        return {
            "review_id": latest["id"],
            "review_type": latest["review_type"],
            "status": latest["status"],
            "verdict": latest["verdict"],
            "summary": latest["summary"],
            "findings": json.loads(latest.get("findings_json") or "{}"),
            "created_at": latest["created_at"],
        }