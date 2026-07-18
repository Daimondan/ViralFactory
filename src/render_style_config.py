"""Mechanical loading and merging of renderer presentation configuration."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml


class RenderStyleConfigError(ValueError):
    """Raised when renderer style configuration is missing or malformed."""


def _load_yaml_mapping(path: Path) -> dict:
    if not path.exists():
        raise RenderStyleConfigError(f"Render style config not found: {path}")
    try:
        value = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise RenderStyleConfigError(f"Invalid render style config: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RenderStyleConfigError(f"Render style config must be a mapping: {path}")
    return value


def _load_visual_style_overrides(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        raise RenderStyleConfigError(f"Unclosed YAML frontmatter: {path}")
    try:
        frontmatter = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        raise RenderStyleConfigError(f"Invalid Visual Style frontmatter: {path}: {exc}") from exc
    if not isinstance(frontmatter, dict):
        raise RenderStyleConfigError(f"Visual Style frontmatter must be a mapping: {path}")
    render_styles = frontmatter.get("render_styles") or {}
    if not isinstance(render_styles, dict):
        raise RenderStyleConfigError(f"render_styles must be a mapping: {path}")
    return render_styles


def load_render_styles(
    config_dir: str = "config",
    modules_dir: str = "modules",
    business_slug: str = "",
) -> dict:
    """Load generic renderer defaults, then apply tenant module overrides."""
    config = _load_yaml_mapping(Path(config_dir) / "render_styles.yaml")
    overlay_styles = config.get("overlay_styles") or {}
    if not isinstance(overlay_styles, dict) or "default" not in overlay_styles:
        raise RenderStyleConfigError("render_styles.yaml requires overlay_styles.default")
    sfx_presets = config.get("sfx_presets") or {}
    default_sfx = config.get("sfx_default_preset")
    if not isinstance(sfx_presets, dict):
        raise RenderStyleConfigError("render_styles.yaml sfx_presets must be a mapping")
    if default_sfx is not None and not isinstance(default_sfx, str):
        raise RenderStyleConfigError("render_styles.yaml sfx_default_preset must be a string")

    merged = deepcopy(config)
    merged["overlay_styles"] = deepcopy(overlay_styles)
    merged["sfx_presets"] = deepcopy(sfx_presets)
    if business_slug:
        module = _load_visual_style_overrides(
            Path(modules_dir) / business_slug / "visual-style.md"
        )
        overrides = module.get("overlay_styles") or {}
        if not isinstance(overrides, dict):
            raise RenderStyleConfigError("Visual Style overlay_styles must be a mapping")
        for style_ref, values in overrides.items():
            if not isinstance(values, dict):
                raise RenderStyleConfigError(
                    f"Overlay style '{style_ref}' must be a mapping"
                )
            base = merged["overlay_styles"].setdefault(style_ref, {})
            if not isinstance(base, dict):
                raise RenderStyleConfigError(
                    f"Configured overlay style '{style_ref}' must be a mapping"
                )
            base.update(deepcopy(values))
        sfx_overrides = module.get("sfx_presets") or {}
        if not isinstance(sfx_overrides, dict):
            raise RenderStyleConfigError("Visual Style sfx_presets must be a mapping")
        for preset_name, values in sfx_overrides.items():
            if not isinstance(values, dict):
                raise RenderStyleConfigError(
                    f"SFX preset '{preset_name}' must be a mapping"
                )
            base = merged["sfx_presets"].setdefault(preset_name, {})
            if not isinstance(base, dict):
                raise RenderStyleConfigError(
                    f"Configured SFX preset '{preset_name}' must be a mapping"
                )
            base.update(deepcopy(values))
        module_default = module.get("sfx_default_preset")
        if module_default is not None:
            if not isinstance(module_default, str):
                raise RenderStyleConfigError(
                    "Visual Style sfx_default_preset must be a string"
                )
            merged["sfx_default_preset"] = module_default
    if (
        merged.get("sfx_default_preset") is not None
        and merged["sfx_default_preset"] not in merged["sfx_presets"]
    ):
        raise RenderStyleConfigError(
            "Resolved sfx_default_preset must name a configured preset"
        )
    return merged
