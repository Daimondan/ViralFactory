"""
ViralFactory — Validator

JSON-schema validation + allowlist checks for LLM outputs.
Ensures every LLM response conforms to the expected schema before it's used.

The validator is the gate between "AI said something" and "the system trusts it."
"""

import json
from typing import Any, Optional


class ValidationError(Exception):
    """Raised when an LLM output fails validation."""
    pass


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

        # Type checking
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
    # Parse JSON
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as e:
        raise ValidationError(f"LLM output is not valid JSON: {e} {context}")

    # Validate schema
    validated = validate_json_schema(parsed, schema, context)

    # Validate allowlists
    if allowlists:
        for field, allowed in allowlists.items():
            validate_allowlist(validated, field, allowed, context)

    return validated