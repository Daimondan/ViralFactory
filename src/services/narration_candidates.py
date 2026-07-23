"""
VF-CW-005 — Narration candidate sets.

Registers configured multiple complete VO takes as workbench candidates
with full playable preview, complete measured beat segments, exact
spoken-text/timing hashes, voice/model/source identity, provenance,
and cost status.

Existing valid takes may register as candidates. Partial takes fail
visibly. The operator can listen, compare, select, reject with feedback,
or regenerate. A new take never inherits approval. The selected take
becomes the only narration item eligible for manifest freeze.

This service wraps the existing VOGenerator and registers the result
as a candidate in the CandidateStore.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Optional


class NarrationCandidateError(Exception):
    """Narration candidate error."""
    pass


class NarrationCandidateService:
    """Generates and registers VO takes as workbench candidates.

    Wraps VOGenerator.generate_vo_per_frame and registers the result
    as a candidate in the CandidateStore with full provenance.
    """

    def __init__(
        self,
        db_path: str = "data/viralfactory.db",
        config_dir: str = "config",
        modules_dir: str = "modules",
        prompts_dir: str = "prompts",
    ):
        self.db_path = db_path
        self.config_dir = config_dir
        self.modules_dir = modules_dir
        self.prompts_dir = prompts_dir

    def _compute_spoken_text_hash(self, segments: list[dict]) -> str:
        """Compute a hash of the exact spoken text across all segments."""
        texts = [s.get("text", "") for s in segments]
        combined = "|".join(texts)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _compute_timing_hash(self, segments: list[dict]) -> str:
        """Compute a hash of the timing (beat_id + duration per segment)."""
        timing = [(s.get("beat_id", ""), s.get("duration", 0)) for s in segments]
        combined = json.dumps(timing, sort_keys=True)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _compute_artifact_hash(self, combined_path: str) -> str:
        """Compute SHA-256 of the combined audio file."""
        if not combined_path or not os.path.exists(combined_path):
            return ""
        h = hashlib.sha256()
        with open(combined_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def register_existing_take(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        take_result: dict,
        voice_identity: dict = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
    ) -> dict:
        """Register an existing valid VO take as a workbench candidate.

        The take_result is the output of VOGenerator.generate_vo_per_frame:
        {
            "take_id": "take_...",
            "segments": [{"frame": 1, "path": "...", "duration": 6.2, "text": "...", "beat_id": "b01"}],
            "total_duration": 61.5,
            "combined_path": "..."
        }

        Partial takes (missing segments, missing paths, zero duration) fail visibly.
        """
        from services.candidate_store import CandidateStore

        # Validate the take is complete
        segments = take_result.get("segments", [])
        if not segments:
            raise NarrationCandidateError(
                "Cannot register take: no segments in take result"
            )

        for i, seg in enumerate(segments):
            seg_path = seg.get("path", "")
            if not seg_path or not os.path.exists(seg_path):
                raise NarrationCandidateError(
                    f"Cannot register take: segment {i+1} has missing or nonexistent path: {seg_path}"
                )
            if seg.get("duration", 0) <= 0:
                raise NarrationCandidateError(
                    f"Cannot register take: segment {i+1} has zero or negative duration"
                )
            if not seg.get("text"):
                raise NarrationCandidateError(
                    f"Cannot register take: segment {i+1} has no spoken text"
                )

        combined_path = take_result.get("combined_path", "")
        if not combined_path or not os.path.exists(combined_path):
            raise NarrationCandidateError(
                "Cannot register take: combined audio path is missing or file does not exist"
            )

        # Compute hashes
        spoken_text_hash = self._compute_spoken_text_hash(segments)
        timing_hash = self._compute_timing_hash(segments)
        artifact_hash = self._compute_artifact_hash(combined_path)

        # Build measurement data
        measurement = {
            "total_duration": take_result.get("total_duration", 0),
            "segment_count": len(segments),
            "segments": [
                {
                    "frame": s.get("frame"),
                    "beat_id": s.get("beat_id"),
                    "duration": s.get("duration"),
                    "text_length": len(s.get("text", "")),
                }
                for s in segments
            ],
            "spoken_text_hash": spoken_text_hash,
            "timing_hash": timing_hash,
        }

        # Build provenance
        generation_provenance = {
            "take_id": take_result.get("take_id"),
            "voice_identity": voice_identity or {},
            "spoken_text_hash": spoken_text_hash,
            "timing_hash": timing_hash,
            "segment_count": len(segments),
            "total_duration": take_result.get("total_duration", 0),
        }

        # Build beat refs from segments
        beat_refs = [s.get("beat_id", f"b{i+1:02d}") for i, s in enumerate(segments)]

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category="narration",
            role="full_take",
            beat_refs=beat_refs,
            artifact_ref=take_result.get("take_id"),
            artifact_hash=artifact_hash,
            artifact_path=combined_path,
            preview_ref=take_result.get("take_id"),
            preview_hash=artifact_hash,  # same file serves as preview
            preview_path=combined_path,
            source_type="tts",
            source_provenance=voice_identity,
            generation_provenance=generation_provenance,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status="available",
        )

        return candidate

    def generate_and_register(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        posts: list,
        voice_identity: dict = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
    ) -> dict:
        """Generate a new VO take and register it as a candidate.

        This wraps VOGenerator.generate_vo_per_frame and registers the
        result. If generation fails, a failed candidate is registered
        so the operator can see the failure.
        """
        from vo_generator import VOGenerator, VOGenerationError
        from services.candidate_store import CandidateStore

        # Try to load config
        config = None
        try:
            from config_loader import load_all, ConfigError
            config = load_all(self.config_dir)
        except (ConfigError, Exception):
            config = None

        try:
            vo_gen = VOGenerator(
                db_path=self.db_path,
                models_config=config.get("models", {}) if config else {},
            )
            result = vo_gen.generate_vo_per_frame(
                asset_id=asset_id,
                posts=posts,
                business_slug=business_slug,
            )
            return self.register_existing_take(
                business_slug=business_slug,
                production_session_id=production_session_id,
                draft_id=draft_id,
                asset_id=asset_id,
                take_result=result,
                voice_identity=voice_identity,
                cost_estimate_usd=cost_estimate_usd,
                cost_approved=cost_approved,
            )
        except (VOGenerationError, Exception) as e:
            # Register a failed candidate so the operator can see it
            store = CandidateStore(db_path=self.db_path)
            beat_refs = []
            if isinstance(posts, list):
                for i, post in enumerate(posts, 1):
                    if isinstance(post, dict):
                        beat_refs.append(str(post.get("beat_id") or f"b{i:02d}"))
                    else:
                        beat_refs.append(f"b{i:02d}")

            candidate = store.create_candidate(
                business_slug=business_slug,
                production_session_id=production_session_id,
                draft_id=draft_id,
                asset_id=asset_id,
                category="narration",
                role="full_take",
                beat_refs=beat_refs,
                source_type="tts",
                generation_provenance={
                    "error": str(e)[:500],
                    "voice_identity": voice_identity or {},
                },
                status="failed",
            )
            return candidate

    def list_narration_candidates(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """List all narration candidates for a session."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        return store.list_candidates(
            business_slug, production_session_id,
            category="narration", role="full_take",
        )

    def get_current_narration(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """Get the current (non-superseded) narration candidates."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        current = store.get_current_versions(business_slug, production_session_id)
        return [c for c in current if c["category"] == "narration"]

    def get_approved_take(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> Optional[dict]:
        """Get the approved narration candidate, if any.

        Only one narration take can be approved at a time. This is the
        only take eligible for manifest freeze.
        """
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        approved = store.get_approved_candidates(business_slug, production_session_id)
        narration = [c for c in approved if c["category"] == "narration"]
        if not narration:
            return None
        # There should be exactly one approved narration take
        return narration[0]