"""Mechanical helpers for the versioned visual-treatment operator gate."""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from module_store import (
    ModuleStore,
    VISUAL_TREATMENT_SCHEMA,
    parse_visual_style_markdown,
)
from validator import validate_llm_output


REFERENCE_CANDIDATE_SCHEMA = {
    "type": "object",
    "required": ["ref_id", "status", "evidence"],
    "properties": {
        "ref_id": {"type": "string"},
        "status": {"type": "string", "enum": ["proposed", "approved", "retired"]},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_visual_treatment(candidate: dict) -> dict:
    """Validate a complete treatment without selecting or judging its aesthetic."""
    return validate_llm_output(
        json.dumps(candidate, ensure_ascii=False),
        VISUAL_TREATMENT_SCHEMA,
        context="visual treatment proposal",
    )


def validate_reference_candidates(candidates: list[dict]) -> list[dict]:
    """Validate candidate references; proposed candidates never become approved."""
    if not isinstance(candidates, list):
        raise ValueError("reference_candidates must be a list")
    validated = []
    for candidate in candidates:
        validated.append(
            validate_llm_output(
                json.dumps(candidate, ensure_ascii=False),
                REFERENCE_CANDIDATE_SCHEMA,
                context="visual treatment reference candidate",
            )
        )
    return validated


def visual_style_data(modules_dir: str, db_path: str, business_slug: str) -> dict:
    """Load the current structured Visual Style module, preserving v1 compatibility."""
    store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
    content = store.load(business_slug, "visual-style")
    if not content:
        return {}
    try:
        return parse_visual_style_markdown(content)
    except ValueError:
        return {}


def treatment_diff(current: dict | None, proposed: dict, candidates: list[dict]) -> str:
    """Return a deterministic review diff including reference candidates."""
    before = json.dumps(current or {}, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    after = json.dumps(proposed, indent=2, ensure_ascii=False, sort_keys=True).splitlines()
    diff = list(
        difflib.unified_diff(
            before,
            after,
            fromfile="approved-visual-treatment",
            tofile="proposed-visual-treatment",
            lineterm="",
        )
    )
    diff.extend(["", "Reference candidates:"])
    diff.extend(json.dumps(candidates, indent=2, ensure_ascii=False, sort_keys=True).splitlines())
    return "\n".join(diff)
