"""
VF-CW-006 — Visual candidates per beat/event role.

Registers visual media (captures, archive, stock, generated video, generated
stills, renderer plates) as workbench candidates in the CandidateStore.

Key rules:
1. Candidates are grouped by exact requirement — beat/event role.
   The visual_media category has role "beat_visual" with scope "beat_event".
2. No assembly and no first-stock auto-selection. The operator must explicitly
   select/approve. Nothing is auto-picked.
3. Persists preview path, duration/dimensions, source type, rights/cost,
   file hash, and beat/event linkage.
4. Missing/processing/failed candidates remain partial (status='generating'
   or 'failed') and stay visible to the operator.
5. Unscoped (no beat_ref) or unmeasured (no dimensions/duration) files fail
   closed — they are rejected at registration time. Generated substitutes
   for required real evidence (requires_real_capture=True) also fail closed.
6. Fullscreen image previews and playable video previews work — the preview
   path is always the artifact path for locally available files.

This service wraps the CandidateStore and optionally the MediaAdapter for
generation flows.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from typing import Optional


class VisualCandidateError(Exception):
    """Visual candidate error."""
    pass


# Valid visual source types — config-driven from component_categories.yaml
# description, enumerated here for mechanical validation.
VALID_VISUAL_SOURCE_TYPES = {
    "capture",           # operator capture / upload
    "archive",           # archive / reference media
    "stock",             # stock media (licensed)
    "generated_video",   # AI-generated video clip
    "generated_still",   # AI-generated still image
    "renderer_plate",    # renderer output plate
}

# Source types that are "real evidence" (not generated)
REAL_EVIDENCE_SOURCE_TYPES = {"capture", "archive", "stock", "renderer_plate"}

# Source types that are "generated"
GENERATED_SOURCE_TYPES = {"generated_video", "generated_still"}


class VisualCandidateService:
    """Registers visual media as workbench candidates in the CandidateStore.

    Visual media are scoped per beat/event. Each candidate carries:
    - artifact/preview hashes and paths
    - duration (for video) or dimensions (for image/still)
    - source type and provenance
    - rights snapshot and cost estimate
    - beat/event linkage via beat_refs

    Unscoped or unmeasured media fail closed. Generated media cannot satisfy
    a requires_real_capture requirement.
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

    # ── Hashing ────────────────────────────────────────────────────────

    def _compute_file_hash(self, path: str) -> str:
        """Compute SHA-256 of a file."""
        if not path or not os.path.exists(path):
            return ""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    # ── Measurement ────────────────────────────────────────────────────

    @staticmethod
    def _probe_image_dimensions(path: str) -> Optional[tuple[int, int]]:
        """Probe image dimensions (width, height) using PIL if available."""
        try:
            from PIL import Image
            with Image.open(path) as img:
                return img.size  # (width, height)
        except Exception:
            return None

    @staticmethod
    def _probe_video_metadata(path: str) -> Optional[dict]:
        """Probe video duration and dimensions using ffprobe if available."""
        import subprocess
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet", "-print_format", "json",
                    "-show_streams", "-show_format", path,
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return None
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            video_stream = next(
                (s for s in streams if s.get("codec_type") == "video"), None
            )
            if not video_stream:
                return None
            duration = None
            fmt = data.get("format", {})
            if "duration" in fmt:
                duration = float(fmt["duration"])
            elif "duration" in video_stream:
                duration = float(video_stream["duration"])
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            return {
                "duration": duration,
                "width": width,
                "height": height,
            }
        except Exception:
            return None

    def _measure_media(self, path: str, kind: str) -> dict:
        """Measure media file: dimensions for images, duration+dimensions for video.

        Returns dict with keys: kind, width, height, duration (if video).
        Raises VisualCandidateError if measurement fails.
        """
        measurement = {"kind": kind}

        if kind == "video":
            probed = self._probe_video_metadata(path)
            if probed:
                measurement["width"] = probed.get("width", 0)
                measurement["height"] = probed.get("height", 0)
                measurement["duration"] = probed.get("duration")
            else:
                # ffprobe not available — we still need dimensions/duration
                raise VisualCandidateError(
                    f"Cannot measure video (ffprobe unavailable?): {path}"
                )
        else:
            # Image or still
            dims = self._probe_image_dimensions(path)
            if dims:
                measurement["width"] = dims[0]
                measurement["height"] = dims[1]
            else:
                raise VisualCandidateError(
                    f"Cannot measure image (PIL unavailable?): {path}"
                )

        return measurement

    # ── Validation ─────────────────────────────────────────────────────

    def _validate_scope(
        self,
        beat_refs: list[str] | None,
        source_type: str,
        requires_real_capture: bool = False,
    ) -> None:
        """Validate that the candidate is properly scoped and sourced.

        Fail closed for:
        - Unscoped media (no beat_ref) — visual_media requires beat_event scope
        - Generated media for a requires_real_capture requirement
        """
        if not beat_refs or len(beat_refs) == 0:
            raise VisualCandidateError(
                "Cannot register visual candidate: no beat_ref provided. "
                "Visual media must be scoped to a beat/event."
            )
        # Also check for empty/None values inside the list
        if not all(isinstance(r, str) and r.strip() for r in beat_refs):
            raise VisualCandidateError(
                "Cannot register visual candidate: beat_ref is empty or None. "
                "Visual media must be scoped to a beat/event."
            )

        if requires_real_capture and source_type in GENERATED_SOURCE_TYPES:
            raise VisualCandidateError(
                f"Cannot register visual candidate: source type '{source_type}' "
                "cannot satisfy a requires_real_capture requirement. "
                "Generated media is not real evidence."
            )

    def _validate_measurement(self, measurement: dict, kind: str) -> None:
        """Validate that measurement has required fields.

        Images must have width and height. Videos must have duration,
        width, and height. Unmeasured files fail closed.
        """
        if kind == "video":
            required = ["width", "height", "duration"]
        else:
            required = ["width", "height"]

        for field in required:
            if field not in measurement or measurement[field] is None:
                raise VisualCandidateError(
                    f"Cannot register visual candidate: measurement missing '{field}'. "
                    "Unmeasured files fail closed."
                )
            if measurement[field] is not None and measurement[field] <= 0:
                raise VisualCandidateError(
                    f"Cannot register visual candidate: measurement '{field}' "
                    f"is {measurement[field]} (must be positive). "
                    "Unmeasured files fail closed."
                )

    # ── Registration ───────────────────────────────────────────────────

    def register_existing_media(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        media_path: str,
        kind: str,
        beat_ref: str,
        source_type: str,
        rights_snapshot: dict = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
        source_provenance: dict = None,
        requires_real_capture: bool = False,
        status: str = "available",
    ) -> dict:
        """Register an existing media file as a visual candidate.

        Args:
            business_slug: tenant slug
            production_session_id: production session ID
            draft_id: draft ID
            asset_id: asset ID
            media_path: path to the media file (image or video)
            kind: "image" or "video"
            beat_ref: the beat/event this visual is scoped to (e.g. "b01")
            source_type: one of VALID_VISUAL_SOURCE_TYPES
            rights_snapshot: rights/licensing snapshot dict
            cost_estimate_usd: estimated cost in USD
            cost_approved: whether cost is pre-approved
            source_provenance: provenance dict (e.g. capture metadata)
            requires_real_capture: if True, generated media fails closed
            status: candidate status (default "available")

        Returns:
            The created candidate dict.

        Raises:
            VisualCandidateError: if the media is unscoped, unmeasured,
                or if generated media is used for a requires_real_capture
                requirement.
        """
        from services.candidate_store import CandidateStore

        # Validate source type
        if source_type not in VALID_VISUAL_SOURCE_TYPES:
            raise VisualCandidateError(
                f"Invalid source type: '{source_type}'. "
                f"Must be one of: {sorted(VALID_VISUAL_SOURCE_TYPES)}"
            )

        # Validate scope — unscoped media fails closed
        self._validate_scope([beat_ref], source_type, requires_real_capture)

        # Validate file exists
        if not media_path or not os.path.exists(media_path):
            raise VisualCandidateError(
                f"Cannot register visual candidate: file does not exist: {media_path}"
            )

        # Measure the media — unmeasured files fail closed
        measurement = self._measure_media(media_path, kind)
        self._validate_measurement(measurement, kind)

        # Compute artifact hash
        artifact_hash = self._compute_file_hash(media_path)

        # Build beat refs list
        beat_refs = [beat_ref]

        # Build generation provenance for generated sources
        generation_provenance = None
        if source_type in GENERATED_SOURCE_TYPES:
            generation_provenance = {
                "source_type": source_type,
                "kind": kind,
                "beat_ref": beat_ref,
                **(source_provenance or {}),
            }
        elif source_provenance:
            generation_provenance = source_provenance

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category="visual_media",
            role="beat_visual",
            beat_refs=beat_refs,
            artifact_ref=f"visual:{source_type}:{beat_ref}",
            artifact_hash=artifact_hash,
            artifact_path=media_path,
            preview_ref=f"visual:{source_type}:{beat_ref}",
            preview_hash=artifact_hash,  # same file serves as preview
            preview_path=media_path,
            source_type=source_type,
            source_provenance=source_provenance,
            generation_provenance=generation_provenance,
            rights_snapshot=rights_snapshot,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status=status,
        )

        return candidate

    def register_from_asset_media(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        asset_media_id: int,
        beat_ref: str,
        source_type: str = None,
        rights_snapshot: dict = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
        requires_real_capture: bool = False,
    ) -> dict:
        """Register a visual candidate from the asset_media table.

        Reads the asset_media row, determines kind (image/video) from the
        'kind' column, resolves the file path, and registers it.

        Args:
            asset_media_id: the ID in the asset_media table
            beat_ref: the beat/event to scope this visual to
            source_type: override the source type (if None, inferred from
                the asset_media row's provider/model fields)
            requires_real_capture: if True, generated media fails closed

        Returns:
            The created candidate dict.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_media WHERE id = ? AND asset_id = ?",
            (asset_media_id, asset_id),
        ).fetchone()
        conn.close()

        if not row:
            raise VisualCandidateError(
                f"asset_media row {asset_media_id} not found for asset {asset_id}"
            )

        row = dict(row)
        kind = row.get("kind", "image") or "image"

        # Resolve file path — asset_media paths may be relative to data/media/
        path = row.get("path", "")
        if path and not os.path.isabs(path) and not os.path.exists(path):
            # Try resolving relative to data/media/<asset_id>/
            candidate_path = os.path.join(
                "data", "media", str(asset_id), os.path.basename(path)
            )
            if os.path.exists(candidate_path):
                path = candidate_path

        # Infer source type if not provided
        if not source_type:
            model = (row.get("model") or "").lower()
            provider = (row.get("provider") or "").lower()
            if kind == "video":
                source_type = "generated_video"
            else:
                source_type = "generated_still"
            # If model/provider is empty, it might be a capture
            if not model and not provider:
                source_type = "capture" if kind in ("image", "video") else "archive"

        # Build source provenance from asset_media row
        source_provenance = {
            "asset_media_id": asset_media_id,
            "model": row.get("model"),
            "prompt": row.get("prompt"),
            "beat_id": row.get("beat_id"),
        }

        # Use cost from asset_media if not overridden
        if cost_estimate_usd is None and row.get("cost_usd") is not None:
            cost_estimate_usd = row.get("cost_usd")

        return self.register_existing_media(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            media_path=path,
            kind=kind,
            beat_ref=beat_ref,
            source_type=source_type,
            rights_snapshot=rights_snapshot,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            source_provenance=source_provenance,
            requires_real_capture=requires_real_capture,
        )

    def register_failed(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        beat_ref: str,
        source_type: str,
        error_message: str,
        kind: str = "image",
    ) -> dict:
        """Register a failed visual candidate so the operator can see it.

        Failed candidates remain visible with status='failed'.
        """
        from services.candidate_store import CandidateStore

        if source_type not in VALID_VISUAL_SOURCE_TYPES:
            raise VisualCandidateError(
                f"Invalid source type: '{source_type}'. "
                f"Must be one of: {sorted(VALID_VISUAL_SOURCE_TYPES)}"
            )

        if not beat_ref:
            raise VisualCandidateError(
                "Cannot register failed visual candidate: no beat_ref provided."
            )

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category="visual_media",
            role="beat_visual",
            beat_refs=[beat_ref],
            artifact_ref=f"visual:{source_type}:{beat_ref}",
            source_type=source_type,
            generation_provenance={
                "error": str(error_message)[:500],
                "source_type": source_type,
                "kind": kind,
                "beat_ref": beat_ref,
            },
            status="failed",
        )

        return candidate

    def register_generating(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        beat_ref: str,
        source_type: str,
        kind: str = "image",
        generation_provenance: dict = None,
    ) -> dict:
        """Register a 'generating' (in-progress) visual candidate.

        Processing candidates remain visible with status='generating'.
        """
        from services.candidate_store import CandidateStore

        if source_type not in VALID_VISUAL_SOURCE_TYPES:
            raise VisualCandidateError(
                f"Invalid source type: '{source_type}'. "
                f"Must be one of: {sorted(VALID_VISUAL_SOURCE_TYPES)}"
            )

        if not beat_ref:
            raise VisualCandidateError(
                "Cannot register generating visual candidate: no beat_ref provided."
            )

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category="visual_media",
            role="beat_visual",
            beat_refs=[beat_ref],
            artifact_ref=f"visual:{source_type}:{beat_ref}",
            source_type=source_type,
            generation_provenance={
                "source_type": source_type,
                "kind": kind,
                "beat_ref": beat_ref,
                **(generation_provenance or {}),
            },
            status="generating",
        )

        return candidate

    # ── Listing / Querying ─────────────────────────────────────────────

    def list_visual_candidates(
        self,
        business_slug: str,
        production_session_id: int,
        beat_ref: str = None,
    ) -> dict[str, list[dict]]:
        """List visual candidates grouped by beat/event.

        Returns a dict mapping beat_ref → list of candidate dicts.
        If beat_ref is provided, returns only candidates for that beat.

        The grouping uses the beat_refs_json field. Each visual candidate
        is scoped to exactly one beat_ref, so this maps beat_ref → candidates.
        """
        from services.candidate_store import CandidateStore

        store = CandidateStore(db_path=self.db_path)
        candidates = store.list_candidates(
            business_slug, production_session_id,
            category="visual_media", role="beat_visual",
        )

        grouped: dict[str, list[dict]] = {}
        for c in candidates:
            refs_json = c.get("beat_refs_json")
            refs = json.loads(refs_json) if refs_json else []
            for ref in refs:
                if beat_ref and ref != beat_ref:
                    continue
                grouped.setdefault(ref, []).append(c)

        return grouped

    def get_current_visuals(
        self,
        business_slug: str,
        production_session_id: int,
        beat_ref: str = None,
    ) -> dict[str, list[dict]]:
        """Get current (non-superseded, non-stale) visual candidates
        grouped by beat/event.

        Returns a dict mapping beat_ref → list of current candidate dicts.
        """
        from services.candidate_store import CandidateStore

        store = CandidateStore(db_path=self.db_path)
        current = store.get_current_versions(business_slug, production_session_id)
        visuals = [c for c in current if c["category"] == "visual_media"]

        grouped: dict[str, list[dict]] = {}
        for c in visuals:
            refs_json = c.get("beat_refs_json")
            refs = json.loads(refs_json) if refs_json else []
            for ref in refs:
                if beat_ref and ref != beat_ref:
                    continue
                grouped.setdefault(ref, []).append(c)

        return grouped

    def get_approved_for_beat(
        self,
        business_slug: str,
        production_session_id: int,
        beat_ref: str,
    ) -> Optional[dict]:
        """Get the approved visual candidate for a specific beat/event.

        Returns the approved candidate dict, or None if no visual is
        approved for this beat.
        """
        from services.candidate_store import CandidateStore

        store = CandidateStore(db_path=self.db_path)
        approved = store.get_approved_candidates(business_slug, production_session_id)
        visuals = [c for c in approved if c["category"] == "visual_media"]

        for c in visuals:
            refs_json = c.get("beat_refs_json")
            refs = json.loads(refs_json) if refs_json else []
            if beat_ref in refs:
                return c

        return None