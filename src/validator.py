"""
ViralFactory — Validator

JSON-schema validation + allowlist checks for LLM outputs.
Ensures every LLM response conforms to the expected schema before it's used.

The validator is the gate between "AI said something" and "the system trusts it."
"""

import json
import re
from typing import Any, Optional


class ValidationError(Exception):
    """Raised when an LLM output fails validation."""
    pass


def _strip_code_fences(raw: str) -> str:
    """
    Strip markdown code fences that some LLMs wrap around JSON output.
    Handles ```json ... ``` and plain ``` ... ``` fences.
    """
    stripped = raw.strip()
    # Match opening fence (```json, ```JSON, ```javascript, or just ```)
    # followed by content, followed by closing ```
    match = re.match(
        r'^```(?:json|JSON|javascript|js)?\s*\n?(.*?)\n?```\s*$',
        stripped,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return stripped


def validate_json_schema(output: dict, schema: dict, context: str = "") -> dict:
    """
    Validate a dict against a JSON-schema-like definition.

    Schema format (simplified):
    {
        "type": "object",
        "required": ["field1", "field2"],
        "properties": {
            "field1": {"type": "string"},
            "field2": {"type": "integer", "minimum": 0},
            "field3": {"type": "array", "items": {"type": "string"}},
            "field4": {"type": "object", "required": ["sub1"], "properties": {...}},
        }
    }

    Raises ValidationError on any mismatch.
    """
    if not isinstance(output, dict):
        raise ValidationError(f"Expected object, got {type(output).__name__} {context}")

    # Check required fields
    for field in schema.get("required", []):
        if field not in output:
            raise ValidationError(f"Missing required field '{field}' {context}")

    # Check each property
    for field, field_schema in schema.get("properties", {}).items():
        if field not in output:
            continue  # optional field, skip

        value = output[field]
        expected_type = field_schema.get("type")

        # P0-2: Coerce None → "" for optional string fields.
        # LLMs return null for optional fields when they have no value.
        # This prevents validation crashes on fields like next_focus.
        if value is None and expected_type == "string" and field not in schema.get("required", []):
            output[field] = ""
            value = ""

        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }

        if expected_type and expected_type in type_map:
            # Don't let bool pass as int
            if expected_type == "integer" and isinstance(value, bool):
                raise ValidationError(
                    f"Field '{field}' must be integer, got boolean {context}"
                )
            if not isinstance(value, type_map[expected_type]):
                raise ValidationError(
                    f"Field '{field}' must be {expected_type}, got {type(value).__name__} {context}"
                )

        # Minimum check
        if "minimum" in field_schema and isinstance(value, (int, float)):
            if value < field_schema["minimum"]:
                raise ValidationError(
                    f"Field '{field}' must be >= {field_schema['minimum']}, got {value} {context}"
                )

        # Array item validation
        if expected_type == "array" and "items" in field_schema:
            item_schema = field_schema["items"]
            if "type" in item_schema:
                item_type = type_map.get(item_schema["type"])
                if item_type:
                    for i, item in enumerate(value):
                        if not isinstance(item, item_type):
                            raise ValidationError(
                                f"Field '{field}[{i}]' must be {item_schema['type']} {context}"
                            )
            # Validate array items as objects (check required fields + nested properties)
            if "properties" in item_schema or "required" in item_schema:
                for i, item in enumerate(value):
                    if not isinstance(item, dict):
                        raise ValidationError(
                            f"Field '{field}[{i}]' must be an object {context}"
                        )
                    # Check required fields in each item
                    for req in item_schema.get("required", []):
                        if req not in item:
                            raise ValidationError(
                                f"Field '{field}[{i}].{req}' is required {context}"
                            )
                    # Validate properties in each item
                    for prop, prop_schema in item_schema.get("properties", {}).items():
                        if prop not in item:
                            continue
                        prop_type = prop_schema.get("type")
                        if prop_type and prop_type in type_map:
                            # Don't let bool pass as int
                            if prop_type == "integer" and isinstance(item[prop], bool):
                                raise ValidationError(
                                    f"Field '{field}[{i}].{prop}' must be integer, got boolean {context}"
                                )
                            if not isinstance(item[prop], type_map[prop_type]):
                                raise ValidationError(
                                    f"Field '{field}[{i}].{prop}' must be {prop_type}, "
                                    f"got {type(item[prop]).__name__} {context}"
                                )

        # Nested object validation
        if expected_type == "object" and "properties" in field_schema:
            validate_json_schema(value, field_schema, f"in '{field}' {context}")

    return output


def validate_allowlist(
    output: dict,
    field: str,
    allowlist: list[str],
    context: str = "",
) -> dict:
    """
    Check that a field's value (or list of values) is in the allowlist.
    Used for taxonomy enforcement — e.g., subjects must come from business.yaml.

    Raises ValidationError if any value is not in the allowlist.
    """
    if field not in output:
        return output  # field absent, skip (use required in schema if it must exist)

    value = output[field]

    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        raise ValidationError(
            f"Field '{field}' must be string or array for allowlist check {context}"
        )

    for v in values:
        if v not in allowlist:
            raise ValidationError(
                f"Field '{field}' value '{v}' is not in the allowed list {context}. "
                f"Allowed: {allowlist}"
            )

    return output


def validate_llm_output(
    raw_output: str,
    schema: dict,
    allowlists: Optional[dict[str, list[str]]] = None,
    context: str = "",
) -> dict:
    """
    Full validation pipeline for an LLM output:
    1. Parse JSON (raise if invalid JSON)
    2. Validate against schema
    3. Validate allowlists

    Returns the validated dict.
    Raises ValidationError on any failure.
    """
    # Parse JSON — strip markdown code fences first (some LLMs wrap output)
    try:
        parsed = json.loads(_strip_code_fences(raw_output))
    except json.JSONDecodeError as e:
        raise ValidationError(f"LLM output is not valid JSON: {e} {context}")

    # Validate schema
    validated = validate_json_schema(parsed, schema, context)

    # Validate allowlists
    if allowlists:
        for field, allowed in allowlists.items():
            validate_allowlist(validated, field, allowed, context)

    return validated