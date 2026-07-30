"""Exact visual-treatment identity and lineage checks.

A supplied treatment reference is an immutable, tenant-owned selection.  This
module only performs mechanical identity checks; it never chooses an aesthetic.
Legacy records may omit the reference and remain readable, but a supplied
reference must resolve to one approved treatment version and its content hash.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


VISUAL_TREATMENT_REF_SCHEMA = {
    "type": "object",
    "required": ["treatment_id", "version", "treatment_hash"],
    "properties": {
        "treatment_id": {"type": "string", "minLength": 1},
        "version": {"type": "string", "minLength": 1},
        "treatment_hash": {"type": "string", "minLength": 64},
    },
}


class VisualTreatmentLineageError(ValueError):
    """A selected treatment is missing, stale, mixed, or otherwise invalid."""


def compute_visual_treatment_hash(treatment: dict) -> str:
    """Return the canonical hash of a complete treatment definition."""
    if not isinstance(treatment, dict):
        raise VisualTreatmentLineageError("visual treatment must be an object")
    data = {key: value for key, value in treatment.items() if key != "treatment_hash"}
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def make_visual_treatment_ref(treatment: dict) -> dict:
    """Create the exact stable identity used at Gate 1 and downstream."""
    if not isinstance(treatment, dict):
        raise VisualTreatmentLineageError("visual treatment must be an object")
    treatment_id = treatment.get("treatment_id")
    version = treatment.get("version")
    if not isinstance(treatment_id, str) or not treatment_id.strip():
        raise VisualTreatmentLineageError("visual treatment is missing treatment_id")
    if not isinstance(version, str) or not version.strip():
        raise VisualTreatmentLineageError("visual treatment is missing version")
    return {
        "treatment_id": treatment_id,
        "version": version,
        "treatment_hash": compute_visual_treatment_hash(treatment),
    }


def _treatments(style_data: dict) -> list[dict]:
    if not isinstance(style_data, dict):
        raise VisualTreatmentLineageError("visual style module is not an object")
    treatments = style_data.get("visual_treatments", [])
    if not isinstance(treatments, list):
        raise VisualTreatmentLineageError("visual_treatments must be a list")
    return treatments


def resolve_visual_treatment_ref(ref: dict, style_data: dict) -> dict:
    """Resolve and verify a supplied reference against the current module."""
    if not isinstance(ref, dict):
        raise VisualTreatmentLineageError("visual_treatment_ref must be an object")
    required = VISUAL_TREATMENT_REF_SCHEMA["required"]
    missing = [field for field in required if not ref.get(field)]
    if missing:
        raise VisualTreatmentLineageError(
            "visual_treatment_ref missing: " + ", ".join(missing)
        )
    matches = [
        item for item in _treatments(style_data)
        if isinstance(item, dict)
        and item.get("treatment_id") == ref.get("treatment_id")
        and item.get("version") == ref.get("version")
    ]
    if not matches:
        raise VisualTreatmentLineageError(
            f"visual treatment {ref.get('treatment_id')}@{ref.get('version')} not found"
        )
    if len(matches) != 1:
        raise VisualTreatmentLineageError("visual treatment identity is duplicated")
    treatment = matches[0]
    if treatment.get("status") != "approved":
        raise VisualTreatmentLineageError(
            f"visual treatment {ref.get('treatment_id')}@{ref.get('version')} is not approved"
        )
    expected_hash = compute_visual_treatment_hash(treatment)
    if ref.get("treatment_hash") != expected_hash:
        raise VisualTreatmentLineageError(
            "visual treatment hash mismatch: selected reference is stale"
        )
    return {
        "treatment_id": treatment["treatment_id"],
        "version": treatment["version"],
        "treatment_hash": expected_hash,
    }


def validate_visual_treatment_ref_shape(ref: dict | None) -> list[str]:
    """Validate the downstream wire shape without resolving tenant config."""
    if ref is None:
        return []
    if not isinstance(ref, dict):
        return ["visual_treatment_ref must be an object or null"]
    errors = []
    for field in VISUAL_TREATMENT_REF_SCHEMA["required"]:
        value = ref.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"visual_treatment_ref.{field} must be a non-empty string")
    if isinstance(ref.get("treatment_hash"), str) and len(ref["treatment_hash"]) != 64:
        errors.append("visual_treatment_ref.treatment_hash must be a SHA-256 hex string")
    return errors


def require_matching_visual_treatment_ref(expected: dict | None, actual: dict | None) -> dict | None:
    """Require two lineage points to carry the same treatment identity."""
    if expected is None and actual is None:
        return None
    if expected is None or actual is None:
        raise VisualTreatmentLineageError(
            "visual treatment reference mismatch: one lineage point is missing"
        )
    if expected != actual:
        raise VisualTreatmentLineageError(
            "visual treatment reference mismatch between production stages"
        )
    return expected


def ref_from_treatment(treatment: dict | None) -> dict | None:
    """Read an optional Gate-1 reference without inventing one for legacy data."""
    if not isinstance(treatment, dict):
        return None
    ref = treatment.get("visual_treatment_ref")
    return ref if ref is not None else None
