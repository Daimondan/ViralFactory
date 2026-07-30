"""Config-owned editorial lens catalogue mechanics.

This module validates references to configured lens IDs. It does not decide
whether a source supports a lens; that judgment belongs to the Source-Fit
Critic process added in VF-IDEA-1609.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_lens_catalogue(business_slug: str, config_dir: str = "config") -> list[dict]:
    path = Path(config_dir) / "editorial_lenses.yaml"
    if not path.exists():
        return []
    try:
        root = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"editorial lens config is invalid: {path}") from exc
    catalogue = (root.get("catalogues") or {}).get(business_slug, {})
    lenses = catalogue.get("lenses", []) if isinstance(catalogue, dict) else []
    if not isinstance(lenses, list):
        raise ValueError(f"lens catalogue for '{business_slug}' must be a list")
    return lenses


def validate_editorial_fit(
    editorial_fit: dict | None, business_slug: str, config_dir: str = "config"
) -> dict | None:
    """Validate configured IDs and shape; never assess source support."""
    if editorial_fit is None:
        return None
    if not isinstance(editorial_fit, dict):
        raise ValueError("editorial_fit must be an object or null")
    lens_id = editorial_fit.get("lens_id")
    configured = {item.get("id") for item in load_lens_catalogue(business_slug, config_dir) if isinstance(item, dict)}
    if not lens_id or lens_id not in configured:
        raise ValueError(f"editorial lens '{lens_id}' is not configured")
    if not isinstance(editorial_fit.get("status"), str):
        raise ValueError("editorial_fit status is required")
    evidence = editorial_fit.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise ValueError("editorial_fit evidence must be a list of strings")
    return editorial_fit


def editorial_fit_label(editorial_fit: dict | None) -> str:
    if not editorial_fit:
        return "Not recorded"
    return str(editorial_fit.get("lens_id") or "Recorded")
