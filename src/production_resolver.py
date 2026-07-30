"""Fail-closed resolution of persisted production bindings.

This module only resolves declared IDs and versions. It does not choose a
format, infer a route from text, or call an LLM/provider.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


class ProductionResolutionError(ValueError):
    """A persisted production binding cannot be resolved safely."""


def _load_registry(config_dir: str) -> dict:
    path = Path(config_dir) / "processes.yaml"
    if not path.exists():
        raise ProductionResolutionError(f"Process registry not found: {path}")
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ProductionResolutionError(f"Process registry is invalid: {path}") from exc
    if not isinstance(data, dict):
        raise ProductionResolutionError("Process registry must be a mapping")
    return data


def _module_version(content: str) -> str | None:
    first_line = (content or "").splitlines()[0] if content else ""
    match = re.search(r"\bv([0-9]+\.[0-9]+)\b", first_line)
    return match.group(1) if match else None


def resolve_production_binding(
    binding: dict | None,
    business_slug: str,
    config_dir: str = "config",
    modules_dir: str = "modules",
    db_path: str = "data/viralfactory.db",
) -> dict:
    """Resolve an approved binding into immutable production context.

    ``None`` is the legacy/standard path. Episode-like paths are never inferred:
    every process, module, status, schema, and exact version must be declared
    and approved before context is returned.
    """
    if binding is None:
        return {
            "mode": "standard",
            "process_ref": None,
            "governance_module_ref": None,
            "governance_module_version": None,
            "module_variable": None,
            "module_content": None,
            "provenance": "production_binding:null -> standard",
        }
    if not isinstance(binding, dict):
        raise ProductionResolutionError("production binding must be an object or null")

    mode = binding.get("mode")
    if mode == "standard":
        return {
            "mode": "standard",
            "process_ref": binding.get("process_ref"),
            "governance_module_ref": None,
            "governance_module_version": None,
            "module_variable": None,
            "module_content": None,
            "provenance": "production_binding:standard",
        }
    if mode != "episode":
        raise ProductionResolutionError(f"production binding mode is unsupported: {mode!r}")

    process_ref = binding.get("process_ref")
    module_ref = binding.get("governance_module_ref")
    expected_version = binding.get("governance_module_version")
    if not process_ref or not module_ref or not expected_version:
        raise ProductionResolutionError(
            "episode production binding requires process_ref, "
            "governance_module_ref, and governance_module_version"
        )

    registry = _load_registry(config_dir)
    production_processes = registry.get("production_processes")
    if not isinstance(production_processes, dict) or process_ref not in production_processes:
        raise ProductionResolutionError(f"process '{process_ref}' is not registered")
    process = production_processes[process_ref]
    if not isinstance(process, dict) or process.get("status") != "approved":
        status = process.get("status") if isinstance(process, dict) else None
        raise ProductionResolutionError(
            f"process '{process_ref}' is not approved (status={status or 'unknown'})"
        )

    from module_store import ModuleStore

    store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
    status = store.get_status(business_slug, module_ref)
    if status != "approved":
        raise ProductionResolutionError(
            f"module '{module_ref}' is not approved (status={status})"
        )
    try:
        content = store.load_validated(business_slug, module_ref)
    except (ValueError, OSError) as exc:
        raise ProductionResolutionError(
            f"module '{module_ref}' failed validation"
        ) from exc
    if not content:
        raise ProductionResolutionError(f"module '{module_ref}' is missing")

    actual_version = _module_version(content)
    if actual_version != str(expected_version):
        raise ProductionResolutionError(
            f"module '{module_ref}' version mismatch: expected {expected_version}, got {actual_version or 'unknown'}"
        )

    module_variable = process.get("module_variable", "episode_format")
    budget = process.get("budget", 0)
    return {
        "mode": "episode",
        "process_ref": process_ref,
        "governance_module_ref": module_ref,
        "governance_module_version": str(expected_version),
        "module_variable": module_variable,
        "module_budget": budget,
        "module_content": content,
        "provenance": (
            f"production_binding:{process_ref} -> {module_ref}@{expected_version}"
        ),
    }
