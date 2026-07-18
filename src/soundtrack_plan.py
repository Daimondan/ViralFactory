"""Soundtrack plan contract (VF-VS-501, AMENDMENT-010 Condition 4).

A parallel contract referenced by the production contract's
``soundtrack_plan`` field. Makes audio intent explicit:

- Every Reel has a ``mode``: ``vo_only``, ``music_bed``, ``source_sound``,
  or ``vo_plus_bed``.
- ``vo_only`` requires a ``vo_only_rationale`` and explicit operator
  approval. Silent VO-only is not valid.
- ``music_bed`` / ``vo_plus_bed`` requires ``music_bed_ref`` with licence
  provenance and a fresh operator-approved cost estimate.
- ``source_sound`` uses the source media's original audio (e.g. on-camera
  ambient sound) and requires a rationale.
- Generic code must not infer genre or add random effects.

This module provides the schema, validator, and helpers.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional


SOUNDTRACK_MODES = frozenset({
    "vo_only",
    "music_bed",
    "source_sound",
    "vo_plus_bed",
})

SOUNDTRACK_PLAN_VERSION = "1.0"

# Ducking attenuation bounds (dB). The VO must always be intelligible.
DUCKING_ATTENUATION_MIN_DB = -24.0
DUCKING_ATTENUATION_MAX_DB = -6.0

# SFX gain bounds (linear 0.0–1.0).
SFX_GAIN_MIN = 0.0
SFX_GAIN_MAX = 1.0


class SoundtrackPlanValidationError(Exception):
    """Raised when a soundtrack plan fails validation."""


# ── Schema ───────────────────────────────────────────────────────────────────

SOUNDTRACK_PLAN_SCHEMA = {
    "type": "object",
    "required": [
        "contract_id",
        "mode",
        "sfx_cues",
        "operator_approval",
    ],
    "properties": {
        "contract_id": {"type": "string", "minLength": 1},
        "mode": {
            "type": "string",
            "enum": list(SOUNDTRACK_MODES),
        },
        "music_bed_ref": {
            "type": ["object", "null"],
            "properties": {
                "source_id": {"type": "string", "minLength": 1},
                "licence": {
                    "type": ["object", "null"],
                    "properties": {
                        "type": {"type": "string"},
                        "id": {"type": "string"},
                        "url": {"type": "string"},
                    },
                },
                "cost_usd": {"type": "number"},
            },
        },
        "ducking": {
            "type": ["object", "null"],
            "properties": {
                "attenuation_db": {"type": "number"},
                "envelope": {"type": "array"},
            },
        },
        "sfx_cues": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["event_id", "source", "timestamp", "gain", "purpose"],
                "properties": {
                    "event_id": {"type": "string", "minLength": 1},
                    "source": {"type": "string"},
                    "timestamp": {"type": "number"},
                    "gain": {"type": "number"},
                    "purpose": {"type": "string"},
                },
            },
        },
        "vo_only_rationale": {"type": ["string", "null"]},
        "source_sound_rationale": {"type": ["string", "null"]},
        "operator_approval": {"type": ["string", "null"]},  # gate token or null
    },
}


# ── Validation ───────────────────────────────────────────────────────────────

def validate_soundtrack_plan(plan: dict) -> list[str]:
    """Validate a soundtrack plan against the schema + semantic rules.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    # Required top-level fields
    for field in ("contract_id", "mode", "sfx_cues", "operator_approval"):
        if field not in plan:
            errors.append(f"Missing required field: {field}")
    if errors:
        return errors  # can't continue without basics

    mode = plan.get("mode", "")
    if mode not in SOUNDTRACK_MODES:
        errors.append(
            f"mode '{mode}' not in allowed: {sorted(SOUNDTRACK_MODES)}"
        )

    # vo_only requires rationale
    if mode == "vo_only":
        rationale = plan.get("vo_only_rationale")
        if not rationale or not rationale.strip():
            errors.append(
                "vo_only mode requires a vo_only_rationale — silent VO-only is not valid"
            )

    # source_sound requires rationale
    if mode == "source_sound":
        rationale = plan.get("source_sound_rationale")
        if not rationale or not rationale.strip():
            errors.append(
                "source_sound mode requires a source_sound_rationale"
            )

    # music_bed / vo_plus_bed requires music_bed_ref with licence + cost
    if mode in ("music_bed", "vo_plus_bed"):
        ref = plan.get("music_bed_ref")
        if not ref or not isinstance(ref, dict):
            errors.append(
                f"{mode} mode requires music_bed_ref with licence provenance"
            )
        else:
            if not ref.get("source_id"):
                errors.append("music_bed_ref.source_id is required")
            licence = ref.get("licence")
            if not licence or not isinstance(licence, dict):
                errors.append(
                    "music_bed_ref.licence is required with provenance"
                )
            else:
                for field in ("type", "id", "url"):
                    if not licence.get(field):
                        errors.append(
                            f"music_bed_ref.licence.{field} is required"
                        )
            cost = ref.get("cost_usd")
            if (
                isinstance(cost, bool)
                or not isinstance(cost, (int, float))
                or cost < 0
            ):
                errors.append(
                    "music_bed_ref.cost_usd is required (fresh operator-approved estimate)"
                )

    # ducking bounds
    ducking = plan.get("ducking")
    if ducking is not None and not isinstance(ducking, dict):
        errors.append("ducking must be an object or null")
    elif ducking:
        att = ducking.get("attenuation_db")
        if isinstance(att, bool) or not isinstance(att, (int, float)):
            errors.append("ducking.attenuation_db must be numeric")
        else:
            if att < DUCKING_ATTENUATION_MIN_DB or att > DUCKING_ATTENUATION_MAX_DB:
                errors.append(
                    f"ducking.attenuation_db {att} out of bounds "
                    f"[{DUCKING_ATTENUATION_MIN_DB}, {DUCKING_ATTENUATION_MAX_DB}]"
                )

    # SFX cues
    sfx_cues = plan.get("sfx_cues") or []
    if not isinstance(sfx_cues, list):
        errors.append("sfx_cues must be an array")
    else:
        seen_ids = set()
        for i, cue in enumerate(sfx_cues):
            if not isinstance(cue, dict):
                errors.append(f"sfx_cues[{i}] must be an object")
                continue
            eid = cue.get("event_id", "")
            if not eid:
                errors.append(f"sfx_cues[{i}]: event_id is required")
            elif eid in seen_ids:
                errors.append(f"sfx_cues[{i}]: duplicate event_id '{eid}'")
            else:
                seen_ids.add(eid)
            source = cue.get("source")
            if not isinstance(source, str) or not source.strip():
                errors.append(f"sfx_cues[{i}]: source is required")
            purpose = cue.get("purpose")
            if not isinstance(purpose, str) or not purpose.strip():
                errors.append(f"sfx_cues[{i}]: purpose is required")
            gain = cue.get("gain")
            if isinstance(gain, bool) or not isinstance(gain, (int, float)):
                errors.append(f"sfx_cues[{i}]: gain must be numeric")
            else:
                if gain < SFX_GAIN_MIN or gain > SFX_GAIN_MAX:
                    errors.append(
                        f"sfx_cues[{i}] gain {gain} out of bounds "
                        f"[{SFX_GAIN_MIN}, {SFX_GAIN_MAX}]"
                    )
            ts = cue.get("timestamp")
            if isinstance(ts, bool) or not isinstance(ts, (int, float)):
                errors.append(f"sfx_cues[{i}]: timestamp must be numeric")
            elif ts < 0:
                errors.append(f"sfx_cues[{i}] timestamp {ts} must be >= 0")

    return errors


def is_valid_soundtrack_plan(plan: dict) -> bool:
    """True if the plan validates with no errors."""
    return len(validate_soundtrack_plan(plan)) == 0


def requires_operator_approval(plan: dict) -> bool:
    """Every soundtrack plan requires operator approval before use."""
    mode = plan.get("mode", "")
    if mode not in SOUNDTRACK_MODES:
        return True
    # vo_only, music_bed, source_sound, vo_plus_bed — all require approval
    return plan.get("operator_approval") is None


def is_approved(plan: dict) -> bool:
    """True if the plan has a non-null operator_approval gate token."""
    return plan.get("operator_approval") is not None


def compute_soundtrack_plan_hash(plan: dict) -> str:
    """SHA-256 hash of the plan's canonical JSON (for provenance/lock)."""
    canonical = json.dumps(plan, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ── Factory ──────────────────────────────────────────────────────────────────

def make_vo_only_plan(
    contract_id: str,
    rationale: str,
    sfx_cues: list[dict] | None = None,
) -> dict:
    """Create a vo_only soundtrack plan (pre-approval)."""
    return {
        "contract_id": contract_id,
        "mode": "vo_only",
        "music_bed_ref": None,
        "ducking": None,
        "sfx_cues": sfx_cues or [],
        "vo_only_rationale": rationale,
        "source_sound_rationale": None,
        "operator_approval": None,
    }


def make_music_bed_plan(
    contract_id: str,
    source_id: str,
    licence: dict,
    cost_usd: float,
    ducking: dict | None = None,
    sfx_cues: list[dict] | None = None,
) -> dict:
    """Create a music_bed soundtrack plan (pre-approval)."""
    return {
        "contract_id": contract_id,
        "mode": "music_bed",
        "music_bed_ref": {
            "source_id": source_id,
            "licence": licence,
            "cost_usd": cost_usd,
        },
        "ducking": ducking,
        "sfx_cues": sfx_cues or [],
        "vo_only_rationale": None,
        "source_sound_rationale": None,
        "operator_approval": None,
    }