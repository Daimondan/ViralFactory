"""
Production Contract v2 — stable, versioned structures for the Assembler pipeline.

Per AMENDMENT-009 / DIVERGENCE-013:
- Stable IDs: contract_id, platform_variant_id, beat_id, text_intent_id,
  media_recipe_id, ingredient_id, segment_id.
- Capture policy per beat (capture_required, capture_preferred, archive_preferred,
  stock_allowed, generated_allowed, text_card, legacy_unclassified).
- Hash-lock covers the full Writer contract layer (not just platform_content).
- Evidence labels: OBSERVED, MEASURED, HYPOTHESIS, HOUSE_RULE.

This module provides:
- JSON schemas for each contract layer (content, beats, text intents, recipes, segments).
- Schema validation.
- Cross-document referential integrity checks.
- Writer contract hash computation.
- Full contract assembly with validation.

The schemas are additive — existing DRAFT_SCHEMA and COMPLIANCE_CONTRACT_SCHEMA
in pipeline.py remain for backward compatibility. This module is the authoritative
source for Production Contract v2 structures going forward.
"""

import json
import hashlib
from typing import Any


# ── Constants ────────────────────────────────────────────────────────────────

CAPTURE_POLICIES = frozenset({
    "capture_required",
    "capture_preferred",
    "archive_preferred",
    "stock_allowed",
    "generated_allowed",
    "text_card",
    "legacy_unclassified",
})

EVIDENCE_LABELS = frozenset({
    "OBSERVED",
    "MEASURED",
    "HYPOTHESIS",
    "HOUSE_RULE",
})

BEAT_ROLES = frozenset({
    "hook", "orientation", "setup", "proof", "development",
    "turn", "payoff", "close",
})

TEXT_FUNCTIONS = frozenset({
    "hook", "orientation", "caption", "emphasis",
    "proof", "reframe", "cta",
})

MEDIA_FUNCTIONS = frozenset({
    "proof", "human_presence", "context", "demonstration",
    "metaphor", "texture", "pace", "breathing_room",
})

PRODUCTION_CONTRACT_VERSION = "2.0"


# ── Custom exception ─────────────────────────────────────────────────────────

class ContractValidationError(Exception):
    """Raised when a production contract fails validation."""
    pass


# ── Schemas ─────────────────────────────────────────────────────────────────

CONTENT_CONTRACT_SCHEMA = {
    "type": "object",
    "required": [
        "contract_id",
        "core_claim",
        "audience_value",
        "evidence_refs",
        "primary_emotional_job",
        "primary_audience_action",
        "format_name",
        "platform",
        "capture_policy",
        "evidence_label",
    ],
    "properties": {
        "contract_id": {"type": "string", "minLength": 1},
        "core_claim": {"type": "string", "minLength": 1},
        "audience_value": {"type": "string", "minLength": 1},
        "evidence_refs": {
            "type": "array",
            "items": {"type": "string"},
        },
        "primary_emotional_job": {"type": "string"},
        "primary_audience_action": {
            "type": "string",
            "enum": ["finish", "share", "save", "comment", "follow", "click"],
        },
        "format_name": {"type": "string"},
        "platform": {"type": "string"},
        "capture_policy": {
            "type": "string",
            "enum": list(CAPTURE_POLICIES),
        },
        "authenticity_anchor": {"type": "string"},
        "performance_hypothesis": {"type": "string"},
        "evidence_label": {
            "type": "string",
            "enum": list(EVIDENCE_LABELS),
        },
    },
}

SEMANTIC_BEAT_SCHEMA = {
    "type": "object",
    "required": [
        "beat_id",
        "platform_variant_id",
        "role",
        "required",
        "vo_text",
        "staged_action",
    ],
    "properties": {
        "beat_id": {"type": "string", "minLength": 1},
        "platform_variant_id": {"type": "string", "minLength": 1},
        "role": {
            "type": "string",
            "enum": list(BEAT_ROLES),
        },
        "required": {"type": "boolean"},
        "vo_text": {"type": "string"},
        "register": {"type": "string"},
        "evidence_refs": {
            "type": "array",
            "items": {"type": "string"},
        },
        "intended_duration_sec": {
            "type": ["object", "null"],
            "properties": {
                "min": {"type": "number"},
                "max": {"type": "number"},
            },
        },
        "viewer_state_before": {"type": "string"},
        "viewer_state_after": {"type": "string"},
        "staged_action": {"type": "string"},
        "text_intents": {
            "type": "array",
            "items": {"type": "string"},  # text_intent_id references
        },
        "visual_intent": {
            "type": ["object", "null"],
            "properties": {
                "subject": {"type": "string"},
                "action": {"type": "string"},
                "shot": {"type": "string"},
                "movement": {"type": "string"},
                "meaning": {"type": "string"},  # what the visual should convey (semantic)
            },
        },
        "audio_intent": {
            "type": ["object", "null"],
            "properties": {
                "mode": {"type": "string"},
                "music_action": {"type": "string"},
                "sfx": {"type": "array"},
                "silence": {"type": ["object", "null"]},
            },
        },
        "capture_policy": {
            "type": "string",
            "enum": list(CAPTURE_POLICIES),
        },
    },
}

TEXT_INTENT_SCHEMA = {
    "type": "object",
    "required": [
        "text_intent_id",
        "beat_id",
        "function",
    ],
    "properties": {
        "text_intent_id": {"type": "string", "minLength": 1},
        "beat_id": {"type": "string", "minLength": 1},
        "function": {
            "type": "string",
            "enum": list(TEXT_FUNCTIONS),
        },
        "text": {"type": "string"},
        "required": {"type": "boolean"},
    },
}

MEDIA_RECIPE_SCHEMA = {
    "type": "object",
    "required": [
        "media_recipe_id",
        "beat_id",
        "media_function",
        "source_policy",
    ],
    "properties": {
        "media_recipe_id": {"type": "string", "minLength": 1},
        "beat_id": {"type": "string", "minLength": 1},
        "media_function": {
            "type": "string",
            "enum": list(MEDIA_FUNCTIONS),
        },
        "source_policy": {
            "type": "string",
            "enum": list(CAPTURE_POLICIES),
        },
        "primary": {
            "type": ["object", "null"],
            "properties": {
                "kind": {"type": "string"},
                "ingredient_id": {"type": "string"},
                "subject": {"type": "string"},
                "action": {"type": "string"},
                "shot": {"type": "string"},
                "movement": {"type": "string"},
                "duration_needed_sec": {"type": "number"},
                "original_audio": {"type": "boolean"},
            },
        },
        "fallback": {
            "type": ["object", "null"],
            "properties": {
                "kind": {"type": "string"},
                "reason": {"type": "string"},
            },
        },
        "continuity": {
            "type": ["object", "null"],
            "properties": {
                "character_ref": {"type": "string"},
                "location_ref": {"type": "string"},
                "grade_ref": {"type": "string"},
            },
        },
        "disclosure": {"type": "string"},
        "cost_estimate_usd": {"type": "number"},
    },
}

EDIT_SEGMENT_SCHEMA = {
    "type": "object",
    "required": [
        "segment_id",
        "beat_ids",
        "source",
    ],
    "properties": {
        "segment_id": {"type": "string", "minLength": 1},
        "beat_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "source": {"type": "string", "minLength": 1},
        "source_in": {"type": "number"},
        "source_out": {"type": "number"},
        "timeline_duration": {"type": "number"},
        "text_intent_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "transition": {"type": "string"},
        "transition_reason": {"type": "string"},
        "audio_contribution": {"type": "string"},
    },
}

PRODUCTION_CONTRACT_V2_SCHEMA = {
    "type": "object",
    "required": [
        "contract_id",
        "version",
        "content_contract",
        "beats",
        "writer_contract_hash",
    ],
    "properties": {
        "contract_id": {"type": "string"},
        "version": {"type": "string"},
        "content_contract": CONTENT_CONTRACT_SCHEMA,
        "beats": {
            "type": "array",
            "items": SEMANTIC_BEAT_SCHEMA,
        },
        "text_intents": {
            "type": "array",
            "items": TEXT_INTENT_SCHEMA,
        },
        "media_recipes": {
            "type": "array",
            "items": MEDIA_RECIPE_SCHEMA,
        },
        "edit_segments": {
            "type": "array",
            "items": EDIT_SEGMENT_SCHEMA,
        },
        "writer_contract_hash": {"type": "string"},
    },
}


# ── Schema validation ────────────────────────────────────────────────────────

def validate_contract_schema(data: dict, schema: dict) -> list[str]:
    """Validate a data dict against a JSON-schema-like schema.

    Returns a list of error strings (empty = valid).
    This is a lightweight validator — not a full jsonschema implementation.
    It checks required fields, types, enums, and minLength.
    """
    errors = []

    # Check required fields
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"Missing required field: {field}")
        elif isinstance(data[field], str) and len(data[field].strip()) == 0:
            errors.append(f"Empty required field: {field}")

    # Check properties
    props = schema.get("properties", {})
    for field, value in data.items():
        if field not in props:
            continue  # allow extra fields

        prop_schema = props[field]
        if value is None:
            # null is OK if the type allows it
            allowed_types = prop_schema.get("type", [])
            if isinstance(allowed_types, str):
                allowed_types = [allowed_types]
            if "null" not in allowed_types and not isinstance(allowed_types, list):
                pass  # let it through — we're lenient on optional nulls
            continue

        # Type check
        expected_type = prop_schema.get("type")
        if expected_type:
            if isinstance(expected_type, list):
                # union type
                type_ok = False
                for t in expected_type:
                    if t == "null":
                        continue
                    if _check_type(value, t):
                        type_ok = True
                        break
                if not type_ok and value is not None:
                    errors.append(f"Field '{field}' has wrong type, expected {expected_type}")
            elif isinstance(expected_type, str):
                if not _check_type(value, expected_type):
                    errors.append(f"Field '{field}' has wrong type, expected {expected_type}")

        # Enum check
        if "enum" in prop_schema and value not in prop_schema["enum"]:
            errors.append(f"Field '{field}' value '{value}' not in allowed enum: {prop_schema['enum']}")

        # minLength check
        if "minLength" in prop_schema and isinstance(value, str):
            if len(value) < prop_schema["minLength"]:
                errors.append(f"Field '{field}' is shorter than minLength {prop_schema['minLength']}")

    return errors


def _check_type(value: Any, expected: str) -> bool:
    """Check if a Python value matches a JSON-schema type string."""
    if expected == "string":
        return isinstance(value, str)
    elif expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    elif expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    elif expected == "boolean":
        return isinstance(value, bool)
    elif expected == "array":
        return isinstance(value, list)
    elif expected == "object":
        return isinstance(value, dict)
    elif expected == "null":
        return value is None
    return True  # unknown type — lenient


# ── Cross-document referential integrity ─────────────────────────────────────

def find_duplicate_ids(items: list[dict], id_field: str) -> list[str]:
    """Find duplicate IDs in a list of dicts."""
    seen = set()
    dupes = []
    for item in items:
        id_val = item.get(id_field, "")
        if id_val in seen:
            dupes.append(id_val)
        else:
            seen.add(id_val)
    return dupes


def validate_segment_beat_references(segments: list[dict], beats: list[dict]) -> list[str]:
    """Validate that all segment beat_ids reference existing beats."""
    beat_ids = {b["beat_id"] for b in beats if "beat_id" in b}
    errors = []
    for seg in segments:
        for bid in seg.get("beat_ids", []):
            if bid not in beat_ids:
                errors.append(f"Segment '{seg.get('segment_id', '?')}' references unknown beat_id: {bid}")
    return errors


def validate_recipe_beat_references(recipes: list[dict], beats: list[dict]) -> list[str]:
    """Validate that all recipe beat_ids reference existing beats."""
    beat_ids = {b["beat_id"] for b in beats if "beat_id" in b}
    errors = []
    for recipe in recipes:
        bid = recipe.get("beat_id", "")
        if bid and bid not in beat_ids:
            errors.append(f"Recipe '{recipe.get('media_recipe_id', '?')}' references unknown beat_id: {bid}")
    return errors


def validate_text_intent_beat_references(intents: list[dict], beats: list[dict]) -> list[str]:
    """Validate that all text intent beat_ids reference existing beats."""
    beat_ids = {b["beat_id"] for b in beats if "beat_id" in b}
    errors = []
    for intent in intents:
        bid = intent.get("beat_id", "")
        if bid and bid not in beat_ids:
            errors.append(f"Text intent '{intent.get('text_intent_id', '?')}' references unknown beat_id: {bid}")
    return errors


def validate_capture_policy_consistency(beats: list[dict], recipes: list[dict]) -> list[str]:
    """Validate that capture_required beats are not mapped to generated/stock media.

    Per AMENDMENT-009 Condition 2: capture_required blocks compliance if the
    real capture is missing or replaced by generated/stock.
    """
    errors = []
    beat_recipes = {}
    for recipe in recipes:
        bid = recipe.get("beat_id", "")
        if bid:
            beat_recipes.setdefault(bid, []).append(recipe)

    for beat in beats:
        bid = beat.get("beat_id", "")
        policy = beat.get("capture_policy", "")

        if policy == "capture_required":
            beat_rs = beat_recipes.get(bid, [])
            if not beat_rs:
                errors.append(f"Beat '{bid}' has capture_required policy but no media recipe — compliance blocked")
                continue
            for recipe in beat_rs:
                primary = recipe.get("primary", {}) or {}
                kind = primary.get("kind", "")
                if kind in ("generated_image", "generated_video", "stock"):
                    errors.append(
                        f"Beat '{bid}' has capture_required policy but recipe maps to {kind} — "
                        f"generated/stock cannot represent required real evidence"
                    )
    return errors


def validate_no_positional_fallback(segments: list[dict]) -> list[str]:
    """Validate that segments do not rely on positional indices instead of beat_ids."""
    errors = []
    for seg in segments:
        beat_ids = seg.get("beat_ids", [])
        if not beat_ids and "position" in seg:
            errors.append(
                f"Segment '{seg.get('segment_id', '?')}' uses positional fallback "
                f"instead of beat_ids — identity must be stable, not positional"
            )
    return errors


# ── Writer contract hash ────────────────────────────────────────────────────

def compute_writer_contract_hash(writer_contract: dict) -> str:
    """Compute SHA-256 hash of the full Writer contract layer.

    Per AMENDMENT-009 Condition 4: the hash-lock protects the entire approved
    Writer contract — not only platform_content text but semantic beats,
    evidence references, visual/audio intent, capture policy, and primary
    audience action.

    The hash is computed over a canonical JSON representation of:
    - platform_content (exact approved text)
    - beats (vo_text, evidence_refs, staged_action, visual_intent, audio_intent, capture_policy)
    - primary_audience_action
    - capture_policy

    Any remediation or planning action that would change these fields
    must be detected by comparing the hash before and after.
    """
    hash_fields = {
        "platform_content": writer_contract.get("platform_content", []),
        "beats": _extract_hashable_beats(writer_contract.get("beats", [])),
        "primary_audience_action": writer_contract.get("primary_audience_action", ""),
        "capture_policy": writer_contract.get("capture_policy", ""),
    }
    canonical = json.dumps(hash_fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extract_hashable_beats(beats: list[dict]) -> list[dict]:
    """Extract the hash-relevant fields from beats.

    Only fields that represent approved meaning are hashed:
    - beat_id, vo_text, evidence_refs, staged_action
    - visual_intent (semantic visual meaning, not provider prompt)
    - audio_intent (semantic audio meaning)
    - capture_policy
    """
    hashable = []
    for beat in beats:
        h = {
            "beat_id": beat.get("beat_id", ""),
            "vo_text": beat.get("vo_text", ""),
            "evidence_refs": beat.get("evidence_refs", []),
            "staged_action": beat.get("staged_action", ""),
            "capture_policy": beat.get("capture_policy", ""),
        }
        # Include visual_intent only if it carries semantic meaning
        vi = beat.get("visual_intent")
        if vi and isinstance(vi, dict):
            h["visual_intent"] = {
                "subject": vi.get("subject", ""),
                "action": vi.get("action", ""),
                "meaning": vi.get("meaning", ""),
            }
        # Include audio_intent if it carries semantic meaning
        ai = beat.get("audio_intent")
        if ai and isinstance(ai, dict):
            h["audio_intent"] = {
                "mode": ai.get("mode", ""),
            }
        hashable.append(h)
    return hashable


# ── Full contract assembly ───────────────────────────────────────────────────

def assemble_contract(
    content_contract: dict,
    beats: list[dict],
    text_intents: list[dict] | None = None,
    media_recipes: list[dict] | None = None,
    edit_segments: list[dict] | None = None,
) -> dict:
    """Assemble a full Production Contract v2 with all validation.

    Raises ContractValidationError if any cross-document reference is invalid
    or if duplicate IDs are found.
    """
    text_intents = text_intents or []
    media_recipes = media_recipes or []
    edit_segments = edit_segments or []

    # Validate content contract schema
    errors = validate_contract_schema(content_contract, CONTENT_CONTRACT_SCHEMA)
    if errors:
        raise ContractValidationError(f"Content contract invalid: {'; '.join(errors)}")

    # Check for duplicate beat IDs
    beat_dupes = find_duplicate_ids(beats, "beat_id")
    if beat_dupes:
        raise ContractValidationError(f"Duplicate beat_id(s): {beat_dupes}")

    # Check for duplicate text_intent IDs
    ti_dupes = find_duplicate_ids(text_intents, "text_intent_id")
    if ti_dupes:
        raise ContractValidationError(f"Duplicate text_intent_id(s): {ti_dupes}")

    # Check for duplicate media_recipe IDs
    mr_dupes = find_duplicate_ids(media_recipes, "media_recipe_id")
    if mr_dupes:
        raise ContractValidationError(f"Duplicate media_recipe_id(s): {mr_dupes}")

    # Check for duplicate segment IDs
    seg_dupes = find_duplicate_ids(edit_segments, "segment_id")
    if seg_dupes:
        raise ContractValidationError(f"Duplicate segment_id(s): {seg_dupes}")

    # Validate cross-document references
    ti_errors = validate_text_intent_beat_references(text_intents, beats)
    if ti_errors:
        raise ContractValidationError("; ".join(ti_errors))

    mr_errors = validate_recipe_beat_references(media_recipes, beats)
    if mr_errors:
        raise ContractValidationError("; ".join(mr_errors))

    seg_errors = validate_segment_beat_references(edit_segments, beats)
    if seg_errors:
        raise ContractValidationError("; ".join(seg_errors))

    # Validate capture policy consistency
    cp_errors = validate_capture_policy_consistency(beats, media_recipes)
    if cp_errors:
        raise ContractValidationError("; ".join(cp_errors))

    # Validate no positional fallback
    pos_errors = validate_no_positional_fallback(edit_segments)
    if pos_errors:
        raise ContractValidationError("; ".join(pos_errors))

    # Compute writer contract hash
    writer_contract = {
        "platform_content": content_contract.get("platform_content", []),
        "beats": beats,
        "primary_audience_action": content_contract.get("primary_audience_action", ""),
        "capture_policy": content_contract.get("capture_policy", ""),
    }
    writer_hash = compute_writer_contract_hash(writer_contract)

    # Assemble full contract
    return {
        "contract_id": content_contract["contract_id"],
        "version": PRODUCTION_CONTRACT_VERSION,
        "content_contract": content_contract,
        "beats": beats,
        "text_intents": text_intents,
        "media_recipes": media_recipes,
        "edit_segments": edit_segments,
        "writer_contract_hash": writer_hash,
    }