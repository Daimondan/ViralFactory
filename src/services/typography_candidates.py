"""
VF-CW-008 — Typography and graphics specimens service.

Resolves exact font files and config/module renderer styles, then registers
deterministic role specimens as workbench candidates for the piece's declared
hook/caption/emphasis/proof/lower-third/CTA/graphics/transition roles.

Key invariants:
  1. Exact font/config/renderer hashes are visible and bindable — every
     candidate carries a font_hash, style_hash, and combined specimen_hash.
  2. Defaults are replaceable and require an exact decision — the role→font_key
     and role→style_ref maps are passed explicitly or use the documented
     defaults; overriding them is an explicit parameter, never a silent guess.
  3. Missing files/specimens block instead of silently falling back — a
     missing font file or missing overlay style raises immediately.
  4. Two tenants vary with zero Python edits — all variation flows through
     config_dir (render_styles.yaml, models.yaml) and modules_dir (visual-style.md).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional

import yaml


class TypographyCandidateError(Exception):
    """Typography or graphics candidate error."""
    pass


# ── Default role → font-config-key mapping ──
# These are the documented defaults. Override by passing role_font_keys
# explicitly to register_typography_candidate(). Replacing a default requires
# an exact decision — no silent fallback to a different font.
DEFAULT_ROLE_FONT_KEYS: dict[str, str] = {
    "hook_font": "font_path",
    "caption_font": "font_path",
    "emphasis_font": "font_path",
    "lower_third_font": "font_path",
    "cta_font": "font_display",
}

# ── Default role → overlay-style-ref mapping ──
# Maps typography roles to render_styles.yaml overlay_styles keys.
DEFAULT_ROLE_STYLE_REFS: dict[str, str] = {
    "hook_font": "hook",
    "caption_font": "caption",
    "emphasis_font": "emphasis",
    "lower_third_font": "default",
    "cta_font": "cta",
}

# ── Graphics roles → overlay-style-ref mapping ──
DEFAULT_GRAPHICS_STYLE_REFS: dict[str, str] = {
    "overlay_graphic": "default",
    "transition": "default",
}

# ── Valid roles (from component_categories.yaml) ──
VALID_TYPOGRAPHY_ROLES = {
    "hook_font", "caption_font", "emphasis_font",
    "lower_third_font", "cta_font",
}

VALID_GRAPHICS_ROLES = {
    "overlay_graphic", "transition",
}


class TypographyCandidateService:
    """Resolves font files and renderer styles, registers specimens as candidates.

    Wraps the config loading (models.yaml for font paths, render_styles.yaml
    for overlay styles) and CandidateStore. All variation is config-driven:
    two tenants with different config dirs resolve different fonts/styles
    with zero Python edits.
    """

    def __init__(
        self,
        db_path: str = "data/viralfactory.db",
        config_dir: str = "config",
        modules_dir: str = "modules",
    ):
        self.db_path = db_path
        self.config_dir = config_dir
        self.modules_dir = modules_dir

    # ── Font resolution ──

    def check_font_exists(self, font_path: str) -> None:
        """Verify a font file exists. Fail closed — raise if missing.

        Never silently falls back to a different font. A missing font file
        is a hard blocker.
        """
        if not font_path:
            raise TypographyCandidateError(
                "Font path is empty — cannot resolve font file"
            )
        if not os.path.isfile(font_path):
            raise TypographyCandidateError(
                f"Font file does not exist: {font_path}"
                " — missing fonts block; no silent fallback"
            )

    def resolve_font_file(
        self,
        font_key: str,
        business_slug: str = "",
    ) -> dict:
        """Resolve a font path from config and compute its hash.

        Reads models.yaml → rendering.{font_key} for the path, verifies
        the file exists, and returns the path + SHA-256 hash.

        If business_slug is set, loads render_styles via the tenant-aware
        loader so module overrides are visible. Font paths themselves come
        from models.yaml rendering config.

        Returns:
            {"font_key": ..., "font_path": ..., "font_hash": ...}
        """
        models = self._load_models_yaml()
        rendering = models.get("rendering") or {}
        if not isinstance(rendering, dict):
            raise TypographyCandidateError(
                "models.yaml 'rendering' section must be a mapping"
            )
        if font_key not in rendering:
            raise TypographyCandidateError(
                f"models.yaml rendering.{font_key} is not configured"
                " — font config is required, no silent fallback"
            )
        font_path = rendering[font_key]
        if not isinstance(font_path, str) or not font_path:
            raise TypographyCandidateError(
                f"models.yaml rendering.{font_key} must be a non-empty string"
            )

        self.check_font_exists(font_path)
        font_hash = self._compute_file_hash(font_path)

        return {
            "font_key": font_key,
            "font_path": font_path,
            "font_hash": font_hash,
        }

    # ── Style resolution ──

    def resolve_style(
        self,
        style_ref: str,
        business_slug: str = "",
    ) -> dict:
        """Resolve an overlay style from render_styles.yaml (+ tenant overrides).

        Returns the merged style dict and its hash.
        """
        from render_style_config import load_render_styles, RenderStyleConfigError

        try:
            merged = load_render_styles(
                config_dir=self.config_dir,
                modules_dir=self.modules_dir,
                business_slug=business_slug,
            )
        except RenderStyleConfigError as e:
            raise TypographyCandidateError(
                f"Cannot load render styles: {e}"
            ) from e

        overlay_styles = merged.get("overlay_styles") or {}
        if style_ref not in overlay_styles:
            raise TypographyCandidateError(
                f"Overlay style '{style_ref}' not found in render_styles"
                " — missing style blocks; no silent fallback to default"
            )
        style_config = overlay_styles[style_ref]
        if not isinstance(style_config, dict):
            raise TypographyCandidateError(
                f"Overlay style '{style_ref}' must be a mapping"
            )
        style_hash = self._compute_style_hash(style_config)
        return {
            "style_ref": style_ref,
            "style_config": style_config,
            "style_hash": style_hash,
        }

    # ── Typography candidate registration ──

    def register_typography_candidate(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        role: str,
        font_key: str = None,
        style_ref: str = None,
        beat_refs: list[str] = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
    ) -> dict:
        """Register a font specimen as a typography candidate.

        Resolves the font file (from models.yaml rendering config) and the
        overlay style (from render_styles.yaml), computes exact hashes, and
        registers the candidate in the store.

        Args:
            role: one of VALID_TYPOGRAPHY_ROLES (hook_font, caption_font, etc.)
            font_key: models.yaml rendering key (e.g. "font_path", "font_display").
                      If None, uses DEFAULT_ROLE_FONT_KEYS[role].
            style_ref: overlay_styles key in render_styles.yaml.
                       If None, uses DEFAULT_ROLE_STYLE_REFS[role].
        """
        from services.candidate_store import CandidateStore

        if role not in VALID_TYPOGRAPHY_ROLES:
            raise TypographyCandidateError(
                f"Invalid typography role '{role}'. Valid: {sorted(VALID_TYPOGRAPHY_ROLES)}"
            )

        # Resolve font key — explicit override or documented default
        resolved_font_key = font_key or DEFAULT_ROLE_FONT_KEYS.get(role)
        if not resolved_font_key:
            raise TypographyCandidateError(
                f"No font_key specified and no default for role '{role}'"
                " — an exact font decision is required"
            )

        # Resolve style ref — explicit override or documented default
        resolved_style_ref = style_ref or DEFAULT_ROLE_STYLE_REFS.get(role)
        if not resolved_style_ref:
            raise TypographyCandidateError(
                f"No style_ref specified and no default for role '{role}'"
                " — an exact style decision is required"
            )

        # Resolve font file (fail closed if missing)
        font_info = self.resolve_font_file(resolved_font_key, business_slug)

        # Resolve overlay style (fail closed if missing)
        style_info = self.resolve_style(resolved_style_ref, business_slug)

        # Compute combined specimen hash — bindable across the pipeline
        specimen_hash = self._compute_specimen_hash(
            font_info["font_hash"],
            style_info["style_hash"],
            role,
        )

        # Build measurement — exact hashes visible and bindable
        measurement = {
            "role": role,
            "font_key": font_info["font_key"],
            "font_path": font_info["font_path"],
            "font_hash": font_info["font_hash"],
            "style_ref": style_info["style_ref"],
            "style_hash": style_info["style_hash"],
            "specimen_hash": specimen_hash,
            "style_config": style_info["style_config"],
        }

        # Build provenance
        generation_provenance = {
            "font_key": font_info["font_key"],
            "font_path": font_info["font_path"],
            "font_hash": font_info["font_hash"],
            "style_ref": style_info["style_ref"],
            "style_hash": style_info["style_hash"],
            "specimen_hash": specimen_hash,
            "config_dir": self.config_dir,
            "modules_dir": self.modules_dir,
            "business_slug": business_slug,
        }

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category="typography",
            role=role,
            beat_refs=beat_refs,
            artifact_ref=f"typography:{role}:{font_info['font_key']}",
            artifact_hash=specimen_hash,
            artifact_path=font_info["font_path"],
            preview_ref=f"typography:{role}",
            preview_hash=specimen_hash,
            preview_path=font_info["font_path"],
            source_type="font_file",
            source_provenance={
                "font_path": font_info["font_path"],
                "font_hash": font_info["font_hash"],
            },
            generation_provenance=generation_provenance,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status="available",
        )

        return candidate

    # ── Graphics candidate registration ──

    def register_graphics_candidate(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        role: str,
        style_ref: str = None,
        beat_refs: list[str] = None,
        cost_estimate_usd: float = None,
        cost_approved: bool = False,
    ) -> dict:
        """Register a graphics/overlay/transition specimen as a candidate.

        Graphics candidates resolve an overlay style from render_styles.yaml
        (no font file — the artifact is the style config itself).

        Args:
            role: one of VALID_GRAPHICS_ROLES (overlay_graphic, transition)
            style_ref: overlay_styles key in render_styles.yaml.
                       If None, uses DEFAULT_GRAPHICS_STYLE_REFS[role].
        """
        from services.candidate_store import CandidateStore

        if role not in VALID_GRAPHICS_ROLES:
            raise TypographyCandidateError(
                f"Invalid graphics role '{role}'. Valid: {sorted(VALID_GRAPHICS_ROLES)}"
            )

        # Resolve style ref — explicit override or documented default
        resolved_style_ref = style_ref or DEFAULT_GRAPHICS_STYLE_REFS.get(role)
        if not resolved_style_ref:
            raise TypographyCandidateError(
                f"No style_ref specified and no default for role '{role}'"
                " — an exact style decision is required"
            )

        # Resolve overlay style (fail closed if missing)
        style_info = self.resolve_style(resolved_style_ref, business_slug)

        # Compute specimen hash from style alone (no font for graphics)
        specimen_hash = self._compute_specimen_hash(
            "",
            style_info["style_hash"],
            role,
        )

        measurement = {
            "role": role,
            "style_ref": style_info["style_ref"],
            "style_hash": style_info["style_hash"],
            "specimen_hash": specimen_hash,
            "style_config": style_info["style_config"],
        }

        generation_provenance = {
            "style_ref": style_info["style_ref"],
            "style_hash": style_info["style_hash"],
            "specimen_hash": specimen_hash,
            "config_dir": self.config_dir,
            "modules_dir": self.modules_dir,
            "business_slug": business_slug,
        }

        store = CandidateStore(db_path=self.db_path)
        candidate = store.create_candidate(
            business_slug=business_slug,
            production_session_id=production_session_id,
            draft_id=draft_id,
            asset_id=asset_id,
            category="graphics",
            role=role,
            beat_refs=beat_refs,
            artifact_ref=f"graphics:{role}:{style_info['style_ref']}",
            artifact_hash=specimen_hash,
            artifact_path=None,
            preview_ref=f"graphics:{role}",
            preview_hash=specimen_hash,
            preview_path=None,
            source_type="render_style",
            source_provenance={
                "style_ref": style_info["style_ref"],
                "style_hash": style_info["style_hash"],
            },
            generation_provenance=generation_provenance,
            cost_estimate_usd=cost_estimate_usd,
            cost_approved=cost_approved,
            measurement=measurement,
            status="available",
        )

        return candidate

    # ── Listing / querying ──

    def list_typography_candidates(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """List all typography candidates for a session."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        return store.list_candidates(
            business_slug, production_session_id,
            category="typography",
        )

    def list_graphics_candidates(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """List all graphics candidates for a session."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        return store.list_candidates(
            business_slug, production_session_id,
            category="graphics",
        )

    def get_approved_typography(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """Get approved typography candidates for a session."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        approved = store.get_approved_candidates(business_slug, production_session_id)
        return [c for c in approved if c["category"] == "typography"]

    def get_approved_graphics(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> list[dict]:
        """Get approved graphics candidates for a session."""
        from services.candidate_store import CandidateStore
        store = CandidateStore(db_path=self.db_path)
        approved = store.get_approved_candidates(business_slug, production_session_id)
        return [c for c in approved if c["category"] == "graphics"]

    # ── Internal helpers ──

    def _load_models_yaml(self) -> dict:
        """Load models.yaml directly (bypassing schema validation that
        requires 'active' backends — we only need the rendering section)."""
        path = Path(self.config_dir) / "models.yaml"
        if not path.exists():
            raise TypographyCandidateError(
                f"models.yaml not found: {path}"
                " — config is required, no silent fallback"
            )
        try:
            data = yaml.safe_load(path.read_text()) or {}
        except yaml.YAMLError as e:
            raise TypographyCandidateError(
                f"Invalid models.yaml: {path}: {e}"
            ) from e
        if not isinstance(data, dict):
            raise TypographyCandidateError(
                f"models.yaml must be a mapping: {path}"
            )
        return data

    def _compute_file_hash(self, file_path: str) -> str:
        """Compute SHA-256 of a file."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _compute_style_hash(self, style_config: dict) -> str:
        """Compute SHA-256 of a style config dict (deterministic JSON)."""
        combined = json.dumps(style_config, sort_keys=True)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _compute_specimen_hash(
        self,
        font_hash: str,
        style_hash: str,
        role: str,
    ) -> str:
        """Compute a combined specimen hash from font + style + role."""
        combined = f"{role}|{font_hash}|{style_hash}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()