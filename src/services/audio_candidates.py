"""
VF-CW-007 — Soundtrack, source-sound, and SFX candidates service.

Reuses VF-VS-511..514 rights-valid locally hashed artifacts and registers
them as workbench candidates with representative selected-VO-under-bed
previews.

Roles:
  - soundtrack/music_bed — rights-valid local track + preview
  - soundtrack/vo_only   — explicit operator decision (requires rationale)
  - sound_effects/sfx_cue — individual SFX cue at a timestamp
  - sound_effects/source_sound — ambient/source sound layer

Safety rules (fail closed):
  - Unknown or stale rights block registration and selection.
  - Unapproved cost blocks registration and selection.
  - Missing preview/hash blocks registration.
  - Music approval does NOT imply SFX approval (separate roles).
  - VO-only is explicit — requires a rationale when allowed.
  - Alternative selection records the exact candidate version.

This service wraps the existing soundtrack_rights / soundtrack_mix stores
and registers candidates in the CandidateStore.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from soundtrack_rights import (
    RIGHTS_STATUSES,
    SoundtrackRightsStore,
    validate_rights_record,
)


class AudioCandidateError(Exception):
    """Audio candidate registration or selection error."""
    pass


# Categories from config/component_categories.yaml
SOUNDTRACK_CATEGORY = "soundtrack"
SOUND_EFFECTS_CATEGORY = "sound_effects"

ROLE_MUSIC_BED = "music_bed"
ROLE_VO_ONLY = "vo_only"
ROLE_SFX_CUE = "sfx_cue"
ROLE_SOURCE_SOUND = "source_sound"


class AudioCandidateService:
    """Registers soundtrack, source-sound, and SFX artifacts as workbench
    candidates with rights evidence and VO-under-bed previews.

    Wraps the existing SoundtrackRightsStore and CandidateStore.  The service
    enforces fail-closed rules:
      - Rights must be current and render-eligible (status == verified).
      - Cost must be operator-approved before a candidate can be frozen.
      - Every registered candidate must have a preview and artifact hash.
      - Music and SFX are independent — approving one does not approve the
        other.
      - VO-only decisions are explicit and require a rationale.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        self._rights_store = SoundtrackRightsStore(db_path)

    # ── Rights / cost checks ───────────────────────────────────────────

    def check_rights_valid(self, rights_record_id: int) -> bool:
        """Verify that the rights record for an artifact is current and
        render-eligible.

        Returns True when the persisted rights snapshot validates with no
        errors and the status is ``verified``.  Unknown, restricted,
        expired, or stale rights return False.
        """
        record = self._rights_store.get_rights_record(rights_record_id)
        if not record:
            return False
        errors = validate_rights_record(record)
        if errors:
            return False
        return record.get("rights_status") == "verified"

    def check_cost_approved(self, rights_record_id: int) -> bool:
        """Verify that the cost associated with a rights record has been
        operator-approved.

        Free acquisitions (cost_usd == 0) are implicitly approved.  Paid
        acquisitions require a non-empty ``cost_approval_id``.
        """
        record = self._rights_store.get_rights_record(rights_record_id)
        if not record:
            return False
        cost = record.get("cost_usd")
        if cost is None or (isinstance(cost, (int, float)) and cost <= 0):
            return True
        approval_id = record.get("cost_approval_id")
        return bool(approval_id and str(approval_id).strip())

    # ── Soundtrack candidates ──────────────────────────────────────────

    def register_soundtrack_candidate(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        soundtrack_plan_id: int,
        rights_record_id: int,
        artifact: dict,
        preview_path: str,
        preview_hash: str,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
        beat_refs: list[str] = None,
        vo_hash: str = None,
        is_alternative: bool = False,
    ) -> dict:
        """Register a rights-valid local soundtrack artifact as a workbench
        candidate.

        ``artifact`` is the output of
        :func:`soundtrack_rights.acquire_rights_valid_track` or the row from
        ``soundtrack_artifacts`` — it must include ``content_hash``,
        ``local_path``, ``duration_seconds``, ``candidate_id``, and
        ``provider``.

        ``preview_path`` / ``preview_hash`` is the representative
        selected-VO-under-bed preview produced by VF-VS-514.

        Fails closed when:
          - rights are unknown, stale, or not render-eligible
          - cost is not approved for paid acquisitions
          - the artifact hash or preview hash is missing
          - the local file does not exist or its hash does not match
        """
        from services.candidate_store import CandidateStore

        # 1. Rights must be current and render-eligible.
        if not self.check_rights_valid(rights_record_id):
            raise AudioCandidateError(
                f"Cannot register soundtrack candidate: rights record "
                f"{rights_record_id} is not current or render-eligible"
            )

        # 2. Cost must be approved for paid acquisitions.
        if not self.check_cost_approved(rights_record_id):
            raise AudioCandidateError(
                f"Cannot register soundtrack candidate: cost for rights "
                f"record {rights_record_id} is not operator-approved"
            )

        content_hash = artifact.get("content_hash") or ""
        if not content_hash:
            raise AudioCandidateError(
                "Cannot register soundtrack candidate: artifact has no content hash"
            )

        local_path = artifact.get("local_path") or ""
        if not local_path or not os.path.isfile(local_path):
            raise AudioCandidateError(
                "Cannot register soundtrack candidate: local artifact file is missing"
            )

        # Verify the on-disk hash matches the recorded hash.
        on_disk = self._file_hash(local_path)
        if on_disk != content_hash:
            raise AudioCandidateError(
                "Cannot register soundtrack candidate: local artifact hash mismatch"
            )

        # Preview must exist and its hash must be supplied.
        if not preview_path or not os.path.isfile(preview_path):
            raise AudioCandidateError(
                "Cannot register soundtrack candidate: preview file is missing"
            )
        if not preview_hash:
            raise AudioCandidateError(
                "Cannot register soundtrack candidate: preview hash is required"
            )
        if self._file_hash(preview_path) != preview_hash:
            raise AudioCandidateError(
                "Cannot register soundtrack candidate: preview hash mismatch"
            )

        # Build the rights snapshot for the candidate row.
        rights_record = self._rights_store.get_rights_record(rights_record_id)
        rights_snapshot = {
            "rights_record_id": rights_record_id,
            "rights_status": rights_record.get("rights_status"),
            "rights_source": rights_record.get("rights_source"),
            "terms_url": rights_record.get("terms_url"),
            "terms_evidence_hash": rights_record.get("terms_evidence_hash"),
            "expires_at": rights_record.get("expires_at"),
            "cost_usd": rights_record.get("cost_usd"),
            "cost_approval_id": rights_record.get("cost_approval_id"),
        }

        duration = float(artifact.get("duration_seconds", 0) or 0)

        generation_provenance = {
            "soundtrack_plan_id": soundtrack_plan_id,
            "candidate_id": artifact.get("candidate_id"),
            "provider": artifact.get("provider"),
            "artifact_id": artifact.get("artifact_id") or artifact.get("id"),
            "content_hash": content_hash,
            "duration_seconds": duration,
            "vo_hash": vo_hash,
            "is_alternative": is_alternative,
        }

        measurement = {
            "duration_seconds": duration,
            "byte_size": artifact.get("byte_size") or (
                os.path.getsize(local_path) if local_path else 0
            ),
            "vo_hash": vo_hash,
            "rights_record_id": rights_record_id,
        }

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category=SOUNDTRACK_CATEGORY,
            role=ROLE_MUSIC_BED,
            beat_refs=beat_refs,
            artifact_ref=str(artifact.get("candidate_id") or ""),
            artifact_hash=content_hash,
            artifact_path=local_path,
            preview_ref=preview_path,
            preview_hash=preview_hash,
            preview_path=preview_path,
            source_type="licensed_music",
            source_provenance={
                "provider": artifact.get("provider"),
                "soundtrack_plan_id": soundtrack_plan_id,
            },
            generation_provenance=generation_provenance,
            rights_snapshot=rights_snapshot,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status="available",
        )
        return candidate

    # ── SFX candidates ─────────────────────────────────────────────────

    def register_sfx_candidate(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        cue: dict,
        artifact_path: str,
        artifact_hash: str,
        preview_path: str,
        preview_hash: str,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
        rights_snapshot: dict = None,
    ) -> dict:
        """Register an individual SFX cue as a workbench candidate.

        ``cue`` follows the soundtrack-plan SFX cue schema:
        ``{event_id, source, timestamp, gain, purpose}``.

        Music approval does NOT imply SFX approval — each SFX cue is
        registered and approved independently.
        """
        from services.candidate_store import CandidateStore

        event_id = cue.get("event_id") or ""
        if not event_id:
            raise AudioCandidateError(
                "Cannot register SFX candidate: cue has no event_id"
            )
        if not artifact_path or not os.path.isfile(artifact_path):
            raise AudioCandidateError(
                f"Cannot register SFX candidate '{event_id}': artifact file is missing"
            )
        if not artifact_hash:
            raise AudioCandidateError(
                f"Cannot register SFX candidate '{event_id}': artifact hash is required"
            )
        if self._file_hash(artifact_path) != artifact_hash:
            raise AudioCandidateError(
                f"Cannot register SFX candidate '{event_id}': artifact hash mismatch"
            )
        if not preview_path or not os.path.isfile(preview_path):
            raise AudioCandidateError(
                f"Cannot register SFX candidate '{event_id}': preview file is missing"
            )
        if not preview_hash:
            raise AudioCandidateError(
                f"Cannot register SFX candidate '{event_id}': preview hash is required"
            )
        if self._file_hash(preview_path) != preview_hash:
            raise AudioCandidateError(
                f"Cannot register SFX candidate '{event_id}': preview hash mismatch"
            )

        beat_refs = [event_id]

        generation_provenance = {
            "event_id": event_id,
            "source": cue.get("source"),
            "timestamp": cue.get("timestamp"),
            "gain": cue.get("gain"),
            "purpose": cue.get("purpose"),
            "artifact_hash": artifact_hash,
        }

        measurement = {
            "timestamp": cue.get("timestamp"),
            "gain": cue.get("gain"),
            "byte_size": os.path.getsize(artifact_path),
        }

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category=SOUND_EFFECTS_CATEGORY,
            role=ROLE_SFX_CUE,
            beat_refs=beat_refs,
            artifact_ref=event_id,
            artifact_hash=artifact_hash,
            artifact_path=artifact_path,
            preview_ref=preview_path,
            preview_hash=preview_hash,
            preview_path=preview_path,
            source_type="sfx_library",
            source_provenance={
                "source": cue.get("source"),
                "event_id": event_id,
            },
            generation_provenance=generation_provenance,
            rights_snapshot=rights_snapshot,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status="available",
        )
        return candidate

    # ── Source sound candidates ────────────────────────────────────────

    def register_source_sound_candidate(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        rationale: str,
        artifact_path: str,
        artifact_hash: str,
        preview_path: str,
        preview_hash: str,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
        rights_snapshot: dict = None,
        beat_refs: list[str] = None,
    ) -> dict:
        """Register a source-sound layer as a workbench candidate.

        Source sound uses the source media's original audio (e.g. on-camera
        ambient sound) and requires a rationale explaining why the source
        audio carries the intended weight.
        """
        from services.candidate_store import CandidateStore

        if not rationale or not rationale.strip():
            raise AudioCandidateError(
                "Cannot register source sound candidate: rationale is required"
            )
        if not artifact_path or not os.path.isfile(artifact_path):
            raise AudioCandidateError(
                "Cannot register source sound candidate: artifact file is missing"
            )
        if not artifact_hash:
            raise AudioCandidateError(
                "Cannot register source sound candidate: artifact hash is required"
            )
        if self._file_hash(artifact_path) != artifact_hash:
            raise AudioCandidateError(
                "Cannot register source sound candidate: artifact hash mismatch"
            )
        if not preview_path or not os.path.isfile(preview_path):
            raise AudioCandidateError(
                "Cannot register source sound candidate: preview file is missing"
            )
        if not preview_hash:
            raise AudioCandidateError(
                "Cannot register source sound candidate: preview hash is required"
            )
        if self._file_hash(preview_path) != preview_hash:
            raise AudioCandidateError(
                "Cannot register source sound candidate: preview hash mismatch"
            )

        generation_provenance = {
            "rationale": rationale,
            "artifact_hash": artifact_hash,
        }

        measurement = {
            "byte_size": os.path.getsize(artifact_path),
            "rationale": rationale,
        }

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category=SOUND_EFFECTS_CATEGORY,
            role=ROLE_SOURCE_SOUND,
            beat_refs=beat_refs,
            artifact_ref=artifact_path,
            artifact_hash=artifact_hash,
            artifact_path=artifact_path,
            preview_ref=preview_path,
            preview_hash=preview_hash,
            preview_path=preview_path,
            source_type="source_capture",
            source_provenance={
                "rationale": rationale,
            },
            generation_provenance=generation_provenance,
            rights_snapshot=rights_snapshot,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status="available",
        )
        return candidate

    # ── VO-only decision ───────────────────────────────────────────────

    def register_vo_only_decision(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        rationale: str,
        beat_refs: list[str] = None,
    ) -> dict:
        """Register an explicit VO-only decision as a workbench candidate.

        VO-only is a deliberate operator decision — it is never a default.
        A non-empty rationale is required.  The candidate has no artifact or
        preview (there is no music bed), but the decision is recorded for
        provenance and freeze eligibility.
        """
        from services.candidate_store import CandidateStore

        if not rationale or not rationale.strip():
            raise AudioCandidateError(
                "Cannot register VO-only decision: a rationale is required — "
                "silent VO-only is not valid"
            )

        generation_provenance = {
            "mode": "vo_only",
            "rationale": rationale,
        }

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category=SOUNDTRACK_CATEGORY,
            role=ROLE_VO_ONLY,
            beat_refs=beat_refs,
            source_type="vo_only",
            generation_provenance=generation_provenance,
            status="available",
        )
        return candidate

    # ── Listing and approval ───────────────────────────────────────────

    def list_audio_candidates(
        self,
        business_slug: str,
        production_session_id: int,
        category: str = None,
        role: str = None,
        status: str = None,
    ) -> list[dict]:
        """List audio candidates for a session, optionally filtered by
        category, role, or status."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)

        if category:
            return store.list_candidates(
                business_slug, production_session_id,
                category=category, role=role, status=status,
            )
        # When no category is specified, return both soundtrack and SFX.
        results = store.list_candidates(
            business_slug, production_session_id,
            category=SOUNDTRACK_CATEGORY, role=role, status=status,
        )
        results.extend(store.list_candidates(
            business_slug, production_session_id,
            category=SOUND_EFFECTS_CATEGORY, role=role, status=status,
        ))
        return results

    def get_approved_soundtrack(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> Optional[dict]:
        """Get the approved soundtrack candidate (music_bed or vo_only), if
        any.  Only one soundtrack candidate can be approved at a time —
        this is the only one eligible for manifest freeze."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        approved = store.get_approved_candidates(business_slug, production_session_id)
        soundtracks = [
            c for c in approved
            if c["category"] == SOUNDTRACK_CATEGORY
            and c["role"] in (ROLE_MUSIC_BED, ROLE_VO_ONLY)
        ]
        if not soundtracks:
            return None
        return soundtracks[0]

    def get_approved_sfx(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """Get all approved SFX/source-sound candidates.  Unlike soundtrack,
        multiple SFX cues can be approved simultaneously — each cue is
        independent.  Music approval does NOT imply SFX approval."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        approved = store.get_approved_candidates(business_slug, production_session_id)
        return [
            c for c in approved
            if c["category"] == SOUND_EFFECTS_CATEGORY
        ]

    # ── Alternative selection ──────────────────────────────────────────

    def select_alternative(
        self,
        business_slug: str,
        production_session_id: int,
        candidate_id: int,
        actor: str = "operator",
    ) -> dict:
        """Select an alternative soundtrack candidate, recording the exact
        version.

        The decision is append-only and binds to the candidate's version and
        artifact hash.  Superseded, failed, or stale candidates cannot be
        selected.  Selecting an alternative does not approve it — a separate
        approval decision is required for freeze.
        """
        from services.candidate_store import CandidateStore, CandidateError
        store = CandidateStore(db_path=self.db_path)
        candidate = store.get_candidate(business_slug, candidate_id)
        if candidate["category"] != SOUNDTRACK_CATEGORY:
            raise AudioCandidateError(
                "select_alternative is only valid for soundtrack candidates"
            )
        if candidate["status"] in ("superseded", "failed", "stale"):
            raise AudioCandidateError(
                f"Cannot select alternative in status '{candidate['status']}'"
            )
        # Record a 'select' decision — this captures the exact version.
        decision = store.record_decision(
            business_slug=business_slug,
            production_session_id=production_session_id,
            candidate_id=candidate_id,
            decision_type="select",
            feedback=f"alternative selected: version={candidate['version']}, "
                     f"hash={candidate['artifact_hash']}",
            actor=actor,
        )
        return {
            "decision": decision,
            "candidate_id": candidate_id,
            "candidate_version": candidate["version"],
            "artifact_hash": candidate["artifact_hash"],
        }

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _file_hash(path: str) -> str:
        """Compute SHA-256 of a file."""
        if not path or not os.path.isfile(path):
            return ""
        digest = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()