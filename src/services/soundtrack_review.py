"""Shared operator soundtrack review service (VF-VS-503).

HTTP routes and the autonomous chain use this boundary so decisions always bind
to the current immutable soundtrack-plan reference persisted on the edit plan.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import subprocess
from pathlib import Path

from services import ServiceResponse
from soundtrack_gate import SoundtrackPreviewGate


class SoundtrackReviewService:
    """Resolve previews and persist explicit operator soundtrack decisions."""

    ACTIONS = {"approve", "reject", "replace", "vo_only"}

    def __init__(self, db_path: str = "data/viralfactory.db", media_root: str | None = None):
        self.db_path = db_path
        self.media_root = Path(media_root or Path(db_path).resolve().parent / "media")
        self.gate = SoundtrackPreviewGate(db_path)

    @staticmethod
    def _current(store, asset_id: int, edit_plan_id: int):
        asset = store.get_asset(asset_id)
        if not asset:
            return None, None, ServiceResponse({"error": "Asset not found"}, 404)
        edit_plan = store.get_edit_plan(edit_plan_id)
        if not edit_plan:
            return None, None, ServiceResponse({"error": "Edit plan not found"}, 404)
        if int(edit_plan.get("asset_id") or 0) != int(asset_id):
            return None, None, ServiceResponse(
                {"error": "Edit plan does not belong to this asset"}, 409
            )
        try:
            plan_data = json.loads(edit_plan.get("plan_json") or "{}")
        except (TypeError, ValueError):
            return None, None, ServiceResponse(
                {"error": "Edit plan contains invalid JSON"}, 409
            )
        reference = plan_data.get("soundtrack_plan")
        if not isinstance(reference, dict):
            return None, None, ServiceResponse(
                {"error": "Edit plan has no soundtrack proposal"}, 409
            )
        soundtrack = store.get_soundtrack_plan(reference.get("soundtrack_plan_id"))
        if not soundtrack:
            return None, None, ServiceResponse(
                {"error": "Referenced soundtrack proposal was not found"}, 409
            )
        if (
            int(soundtrack.get("asset_id") or 0) != int(asset_id)
            or int(soundtrack.get("edit_plan_id") or 0) != int(edit_plan_id)
            or soundtrack.get("contract_id") != reference.get("contract_id")
            or soundtrack.get("plan_hash") != reference.get("plan_hash")
        ):
            return None, None, ServiceResponse(
                {"error": "Current soundtrack reference does not match its owner"}, 409
            )
        return edit_plan, soundtrack, None

    @staticmethod
    def _is_playable(source: str | None) -> bool:
        if not source:
            return False
        return source.startswith(("http://", "https://", "/media/")) or os.path.isfile(source)

    def _public_source(self, source: str | None) -> str | None:
        if not source:
            return None
        if source.startswith(("http://", "https://", "/media/")):
            return source
        path = Path(source).resolve()
        if not path.is_file():
            return None
        try:
            relative = path.relative_to(self.media_root.resolve())
        except ValueError:
            return None
        return "/media/" + relative.as_posix()

    def _mixed_preview(
        self,
        *,
        asset_id: int,
        plan_hash: str,
        vo_path: str | None,
        bed_path: str | None,
        attenuation_db: float,
    ) -> str | None:
        if not vo_path or not bed_path or not os.path.isfile(vo_path) or not os.path.isfile(bed_path):
            return None
        output_dir = self.media_root / str(asset_id)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / f"soundtrack-preview-{plan_hash[:12]}.wav"
        if not output.exists():
            bed_gain = math.pow(10.0, attenuation_db / 20.0)
            command = [
                "ffmpeg", "-y", "-i", vo_path, "-stream_loop", "-1", "-i", bed_path,
                "-filter_complex",
                f"[1:a]volume={bed_gain:.8f}[bed];"
                "[0:a][bed]amix=inputs=2:duration=first:normalize=0[mix]",
                "-map", "[mix]", "-c:a", "pcm_s16le", str(output),
            ]
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=120, check=False
            )
            if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                output.unlink(missing_ok=True)
                return None
        return f"/media/{asset_id}/{output.name}"

    @staticmethod
    def _source_sound_path(store, asset_id: int, edit_plan: dict) -> str | None:
        plan = json.loads(edit_plan.get("plan_json") or "{}")
        for segment in plan.get("segments") or []:
            if segment.get("audio_contribution") != "source":
                continue
            source = str(segment.get("source") or "")
            if not source.startswith("asset_media:"):
                continue
            try:
                media_id = int(source.split(":", 1)[1])
            except (TypeError, ValueError):
                continue
            conn = sqlite3.connect(store.db_path)
            try:
                row = conn.execute(
                    "SELECT path FROM asset_media WHERE id = ? AND asset_id = ?",
                    (media_id, asset_id),
                ).fetchone()
            finally:
                conn.close()
            if row:
                return row[0]
        return None

    def get_review(self, *, asset_id: int, edit_plan_id: int, store) -> ServiceResponse:
        edit_plan, soundtrack, error = self._current(store, asset_id, edit_plan_id)
        if error:
            return error
        plan = soundtrack["plan"]
        edit_plan_data = json.loads(edit_plan.get("plan_json") or "{}")
        vo_path = ((edit_plan_data.get("audio") or {}).get("vo") or {}).get("path")
        bed = plan.get("music_bed_ref") or {}
        bed_path = bed.get("source_id")
        ducking = plan.get("ducking") or {}
        mixed_path = self._mixed_preview(
            asset_id=asset_id,
            plan_hash=soundtrack["plan_hash"],
            vo_path=vo_path,
            bed_path=bed_path,
            attenuation_db=float(ducking.get("attenuation_db") or -12.0),
        )
        manifest = self.gate.build_preview_manifest(
            plan,
            vo_file_path=self._public_source(vo_path),
            bed_file_path=self._public_source(bed_path),
            mixed_file_path=mixed_path,
            source_sound_file_path=self._public_source(
                self._source_sound_path(store, asset_id, edit_plan)
            ),
        )
        for track in manifest["tracks"]:
            if track.get("file") and not track.get("synthetic_placeholder"):
                track["file"] = self._public_source(track["file"])
        decision = self.gate.get_approval(
            soundtrack["contract_id"], soundtrack["plan_hash"]
        )
        alternatives = [
            {
                "soundtrack_plan_id": candidate["id"],
                "mode": candidate["plan"].get("mode"),
                "emotional_register": candidate["plan"].get("emotional_register"),
            }
            for candidate in store.list_soundtrack_plans(asset_id)
            if candidate["id"] != soundtrack["id"]
            and int(candidate["edit_plan_id"]) == int(edit_plan_id)
        ]
        return ServiceResponse({
            "status": "ok",
            "asset_id": asset_id,
            "edit_plan_id": edit_plan_id,
            "soundtrack_plan_id": soundtrack["id"],
            "plan_hash": soundtrack["plan_hash"],
            "mode": plan.get("mode"),
            "emotional_register": plan.get("emotional_register"),
            "rationale": plan.get("vo_only_rationale") or plan.get("source_sound_rationale"),
            "music_bed_ref": plan.get("music_bed_ref"),
            "sfx_cues": plan.get("sfx_cues") or [],
            "preview": manifest,
            "preview_ready": all(
                self._is_playable(track.get("file"))
                for track in manifest["tracks"]
            ) and bool(manifest["tracks"]),
            "approval": {
                "approved": bool(decision and decision.get("verdict") == "approved"),
                "verdict": decision.get("verdict") if decision else "pending",
                "reason": decision.get("reason") if decision else None,
            },
            "preview_acknowledged": self.gate.was_previewed(
                soundtrack["contract_id"], soundtrack["plan_hash"]
            ),
            "alternatives": alternatives,
            "current": True,
        })

    def acknowledge_preview(
        self,
        *,
        asset_id: int,
        edit_plan_id: int,
        business_slug: str,
        store,
    ) -> ServiceResponse:
        """Record that the operator heard every playable current preview."""
        _edit_plan, current, error = self._current(store, asset_id, edit_plan_id)
        if error:
            return error
        review = self.get_review(
            asset_id=asset_id,
            edit_plan_id=edit_plan_id,
            store=store,
        )
        if not review.ok:
            return review
        if not review.payload.get("preview_ready"):
            return ServiceResponse(
                {"error": "Every required soundtrack preview must be playable"},
                409,
            )
        evidence = self.gate.record_preview(
            current["contract_id"], business_slug, current["plan_hash"]
        )
        return ServiceResponse({
            "status": "preview_acknowledged",
            "soundtrack_plan_id": current["id"],
            "plan_hash": evidence["plan_hash"],
        })

    def decide(
        self,
        *,
        asset_id: int,
        edit_plan_id: int,
        action: str,
        business_slug: str,
        reason: str | None = None,
        replacement_plan_id: int | None = None,
        store,
    ) -> ServiceResponse:
        if action not in self.ACTIONS:
            return ServiceResponse({"error": "Unsupported soundtrack decision"}, 400)
        edit_plan, current, error = self._current(store, asset_id, edit_plan_id)
        if error:
            return error
        plan = current["plan"]
        contract_id = current["contract_id"]
        plan_hash = current["plan_hash"]
        mode = plan.get("mode")

        if action == "approve":
            if not self.gate.was_previewed(contract_id, plan_hash):
                return ServiceResponse(
                    {"error": "Listen to every soundtrack preview before approval"},
                    409,
                )
            decision = self.gate.record_approval(
                contract_id, business_slug, plan_hash, mode, reason
            )
            return ServiceResponse({
                "status": "approved",
                "mode": mode,
                "soundtrack_plan_id": current["id"],
                "gate_token": decision["gate_token"],
            })

        if action == "reject":
            if not reason or not reason.strip():
                return ServiceResponse({"error": "A rejection reason is required"}, 400)
            self.gate.record_rejection(
                contract_id, business_slug, plan_hash, mode, reason.strip()
            )
            store.update_edit_plan_status(
                edit_plan_id, "needs_operator_decision", reason.strip()
            )
            return ServiceResponse({"status": "rejected", "mode": mode})

        if action == "replace":
            replacement = store.get_soundtrack_plan(replacement_plan_id)
            if not replacement or (
                int(replacement.get("asset_id") or 0) != int(asset_id)
                or int(replacement.get("edit_plan_id") or 0) != int(edit_plan_id)
            ):
                return ServiceResponse(
                    {"error": "Replacement soundtrack plan does not belong to this asset and edit plan"},
                    409,
                )
            if replacement["id"] == current["id"]:
                return ServiceResponse({"error": "Replacement must be a different plan"}, 409)
            reference = store.save_soundtrack_plan(
                asset_id, edit_plan_id, replacement["plan"]
            )
            decision = self.gate.record_replacement(
                contract_id,
                business_slug,
                plan_hash,
                reference["plan_hash"],
                replacement["plan"].get("mode"),
                reason,
            )
            store.update_edit_plan_status(edit_plan_id, "needs_operator_decision")
            return ServiceResponse({
                "status": "replacement_selected",
                "soundtrack_plan_id": reference["soundtrack_plan_id"],
                "gate_token": decision["gate_token"],
            })

        if not self.gate.was_previewed(contract_id, plan_hash):
            return ServiceResponse(
                {"error": "Listen to the current preview before choosing VO only"},
                409,
            )
        if not reason or not reason.strip():
            return ServiceResponse(
                {"error": "Explain why this piece should use VO only"}, 400
            )
        replacement = {
            "contract_id": contract_id,
            "mode": "vo_only",
            "music_bed_ref": None,
            "ducking": None,
            "sfx_cues": [],
            "vo_only_rationale": reason.strip(),
            "source_sound_rationale": None,
            "emotional_register": plan.get("emotional_register") or reason.strip(),
            "operator_approval": None,
        }
        reference = store.save_soundtrack_plan(asset_id, edit_plan_id, replacement)
        self.gate.record_replacement(
            contract_id,
            business_slug,
            plan_hash,
            reference["plan_hash"],
            "vo_only",
            reason.strip(),
        )
        approval = self.gate.record_approval(
            contract_id,
            business_slug,
            reference["plan_hash"],
            "vo_only",
            reason.strip(),
        )
        store.update_edit_plan_status(edit_plan_id, "soundtrack_approved")
        return ServiceResponse({
            "status": "approved",
            "mode": "vo_only",
            "soundtrack_plan_id": reference["soundtrack_plan_id"],
            "gate_token": approval["gate_token"],
        })
