"""
ViralFactory — Configuration Loader

Loads YAML config files (business.yaml, models.yaml, sources.yaml) with schema
validation. Bad config fails loudly with a clear message. No defaults hidden in code.

This is the first thing any ViralFactory component touches — it defines the business.
"""

import os
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when config is missing, malformed, or violates schema."""
    pass


# --- Schema definitions ---

BUSINESS_SCHEMA = {
    "required": ["business", "subjects", "platforms"],
    "fields": {
        "business": {
            "required": ["name", "slug", "description"],
            "types": {"name": str, "slug": str, "description": str},
        },
        "brands": {
            "required": [],  # optional
            "min_items": 0,
            "item_fields": {"name": str, "purpose": str},
        },
        "subjects": {
            "required": True,
            "min_items": 1,
            "item_type": str,
        },
        "platforms": {
            "required": True,
            "min_items": 1,
            "item_fields": {"name": str, "handle": str, "priority": int},
        },
        "goals": {"required": [], "item_type": str},
        "red_lines": {"required": [], "item_type": str},
        "audience_description": {"type": str, "required": False},
    },
}

MODELS_SCHEMA = {
    "required": ["active"],
    "fields": {
        "active": {
            "required": ["default", "drafter"],
            "types": {
                "default": (str, type(None)),
                "drafter": (str, type(None)),
                "ideator": (str, type(None)),
            },
            "optional": {"drafter_ab_candidate": (str, type(None))},
        },
    },
    # Named backends are arbitrary keys at the top level, each with this shape.
    # The config loader validates "active" above, then we validate backends separately.
}

SOURCES_SCHEMA = {
    "required": [],
    "fields": {
        "feeds": {"required": [], "item_fields": {"name": str, "url": str, "type": str, "enabled": bool}},
        "channels": {"required": [], "item_fields": {"name": str, "platform": str, "enabled": bool}},
        "queries": {"required": [], "item_fields": {"query": str, "engine": str, "enabled": bool}},
    },
}


# --- Loader ---

def load_yaml(filepath: str) -> dict:
    """Load a YAML file, raising ConfigError on any issue."""
    path = Path(filepath)
    if not path.exists():
        raise ConfigError(f"Config file not found: {filepath}")
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML parse error in {filepath}: {e}")
    if data is None:
        raise ConfigError(f"Config file is empty: {filepath}")
    if not isinstance(data, dict):
        raise ConfigError(f"Config file must be a YAML mapping, got {type(data).__name__}: {filepath}")
    return data


def validate_section(data: dict, schema: dict, section_name: str, filepath: str):
    """Validate a config section against its schema."""
    # Check required top-level fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            raise ConfigError(f"Missing required field '{field}' in {section_name} ({filepath})")

    for field, field_schema in schema.get("fields", {}).items():
        if field not in data:
            if field in required:
                raise ConfigError(f"Missing required field '{field}' in {section_name} ({filepath})")
            continue  # optional field, skip

        value = data[field]

        # Scalar type check
        if "type" in field_schema:
            expected = field_schema["type"]
            if not isinstance(value, expected):
                raise ConfigError(
                    f"Field '{field}' in {section_name} must be {expected.__name__}, "
                    f"got {type(value).__name__} ({filepath})"
                )

        # List of strings (check item_type before nested object — item_type means list)
        elif "item_type" in field_schema:
            if not isinstance(value, list):
                raise ConfigError(f"Field '{field}' must be a list ({filepath})")
            if "min_items" in field_schema and len(value) < field_schema["min_items"]:
                raise ConfigError(
                    f"Field '{field}' must have at least {field_schema['min_items']} items ({filepath})"
                )
            for i, item in enumerate(value):
                if not isinstance(item, field_schema["item_type"]):
                    raise ConfigError(
                        f"Field '{field}[{i}]' must be {field_schema['item_type'].__name__} ({filepath})"
                    )

        # List of objects (check item_fields before nested object — item_fields means list)
        elif "item_fields" in field_schema:
            if not isinstance(value, list):
                raise ConfigError(f"Field '{field}' must be a list ({filepath})")
            if "min_items" in field_schema and len(value) < field_schema["min_items"]:
                raise ConfigError(
                    f"Field '{field}' must have at least {field_schema['min_items']} items ({filepath})"
                )
            for i, item in enumerate(value):
                if not isinstance(item, dict):
                    raise ConfigError(f"Field '{field}[{i}]' must be a mapping ({filepath})")
                for item_field, item_type in field_schema["item_fields"].items():
                    if item_field in item and not isinstance(item[item_field], item_type):
                        raise ConfigError(
                            f"Field '{field}[{i}].{item_field}' must be "
                            f"{item_type.__name__} ({filepath})"
                        )

        # Nested object (has required or types but NOT item_type/item_fields)
        elif "required" in field_schema or "types" in field_schema:
            if not isinstance(value, dict):
                raise ConfigError(
                    f"Field '{field}' in {section_name} must be a mapping ({filepath})"
                )
            for sub_field, sub_type in field_schema.get("types", {}).items():
                if sub_field in value and not isinstance(value[sub_field], sub_type):
                    raise ConfigError(
                        f"Field '{field}.{sub_field}' must be {sub_type.__name__}, "
                        f"got {type(value[sub_field]).__name__} ({filepath})"
                    )
            for sub_field in field_schema.get("required", []):
                if sub_field not in value:
                    raise ConfigError(
                        f"Missing required field '{field}.{sub_field}' in {section_name} ({filepath})"
                    )


def load_business(config_dir: str = "config") -> dict:
    """Load and validate business.yaml."""
    filepath = os.path.join(config_dir, "business.yaml")
    data = load_yaml(filepath)
    validate_section(data, BUSINESS_SCHEMA, "business.yaml", filepath)
    return data


def load_models(config_dir: str = "config") -> dict:
    """Load and validate models.yaml."""
    filepath = os.path.join(config_dir, "models.yaml")
    data = load_yaml(filepath)
    validate_section(data, MODELS_SCHEMA, "models.yaml", filepath)

    # Validate that the named backends referenced by "active" exist and have required fields
    active = data.get("active", {})
    for role, backend_name in active.items():
        if backend_name is None:
            continue  # null is OK (e.g. drafter_ab_candidate not set yet)
        if not isinstance(backend_name, str):
            raise ConfigError(
                f"active.{role} in models.yaml ({filepath}) must be a string or null, "
                f"got {type(backend_name).__name__}"
            )
        backend = data.get(backend_name)
        if not backend:
            raise ConfigError(
                f"active.{role} references backend '{backend_name}' which is not defined "
                f"in models.yaml ({filepath})"
            )
        for req in ("provider", "model", "temperature", "max_tokens"):
            if req not in backend:
                raise ConfigError(
                    f"Backend '{backend_name}' in models.yaml ({filepath}) "
                    f"is missing required field '{req}'"
                )

    return data


def load_sources(config_dir: str = "config") -> dict:
    """Load and validate sources.yaml."""
    filepath = os.path.join(config_dir, "sources.yaml")
    data = load_yaml(filepath)
    validate_section(data, SOURCES_SCHEMA, "sources.yaml", filepath)
    return data


def load_all(config_dir: str = "config") -> dict:
    """Load all config files. Returns dict with 'business', 'models', 'sources' keys."""
    return {
        "business": load_business(config_dir),
        "models": load_models(config_dir),
        "sources": load_sources(config_dir),
    }