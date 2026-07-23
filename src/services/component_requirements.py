"""
VF-CW-003 — Config + prompt-driven component requirements.

Provides:
  - ComponentCategoryRegistry: loads config/component_categories.yaml
  - COMPONENT_REQUIREMENTS_SCHEMA: JSON schema for the LLM planner output
  - ComponentRequirementsValidator: validates LLM output against the schema
    and the category registry (mechanical validation only — no keyword judgment)
  - ComponentRequirementsStore: persists requirement plans with provenance
  - ComponentRequirementsService: orchestrates the LLM call + validation + persistence

The LLM planner reads the approved Writer contract, format, visual events,
audio intents, capture policy, and tenant modules to determine which component
roles are required. Python validates IDs, cardinality, and references only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import yaml


# ── Schema ─────────────────────────────────────────────────────────────

COMPONENT_REQUIREMENTS_SCHEMA = {
    "type": "object",
    "required": ["format", "platform", "categories"],
    "properties": {
        "format": {"type": "string"},
        "platform": {"type": "string"},
        "categories": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["category", "required", "roles"],
                "properties": {
                    "category": {"type": "string"},
                    "required": {"type": "boolean"},
                    "roles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": [
                                "role", "required", "scope",
                                "none_allowed", "preview_required",
                            ],
                            "properties": {
                                "role": {"type": "string"},
                                "required": {"type": "boolean"},
                                "scope": {"type": "string"},
                                "beat_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "none_allowed": {"type": "boolean"},
                                "preview_required": {"type": "boolean"},
                                "requires_real_capture": {"type": "boolean"},
                                "requires_rationale": {"type": "boolean"},
                            },
                        },
                    },
                },
            },
        },
        "planner_notes": {"type": "string"},
    },
}


# ── Category Registry ──────────────────────────────────────────────────

class ComponentCategoryRegistry:
    """Loads the config/component_categories.yaml registry.

    Provides mechanical lookups: valid categories, valid roles within a
    category, cardinality, and format overrides. No creative judgment.
    """

    def __init__(self, config_dir: str = "config"):
        self.config_dir = config_dir
        self._config = None
        self._load()

    def _load(self):
        path = os.path.join(self.config_dir, "component_categories.yaml")
        with open(path, "r") as f:
            self._config = yaml.safe_load(f)

    @property
    def categories(self) -> dict:
        """All categories keyed by category key."""
        cats = self._config.get("categories", {})
        if isinstance(cats, dict):
            return cats
        # If YAML has a list format, convert to dict
        return {c["key"]: c for c in cats}

    @property
    def format_overrides(self) -> dict:
        """Format overrides keyed by format name."""
        return self._config.get("format_overrides", {})

    def get_category(self, category_key: str) -> Optional[dict]:
        """Get a category by key."""
        return self.categories.get(category_key)

    def get_role(self, category_key: str, role_key: str) -> Optional[dict]:
        """Get a role within a category."""
        cat = self.get_category(category_key)
        if not cat:
            return None
        for role in cat.get("roles", []):
            if role["key"] == role_key:
                return role
        return None

    def is_valid_category(self, category_key: str) -> bool:
        return category_key in self.categories

    def is_valid_role(self, category_key: str, role_key: str) -> bool:
        return self.get_role(category_key, role_key) is not None

    def get_format_override(self, format_name: str) -> dict:
        """Get format-specific category requirements."""
        return self.format_overrides.get(format_name, {})

    def get_required_categories(self, format_name: str) -> list[str]:
        """Get required category keys for a format."""
        override = self.get_format_override(format_name)
        return override.get("required_categories", [])

    def get_optional_categories(self, format_name: str) -> list[str]:
        """Get optional category keys for a format."""
        override = self.get_format_override(format_name)
        return override.get("optional_categories", [])


# ── Validator ──────────────────────────────────────────────────────────

class ComponentRequirementsValidator:
    """Validates component requirements against the schema and category registry.

    Mechanical validation only: known category/role IDs, correct structure,
    valid cardinality references. No keyword creative judgment.
    """

    def __init__(self, registry: ComponentCategoryRegistry):
        self.registry = registry

    def validate(self, requirements: dict) -> tuple[bool, list[str]]:
        """Validate a requirements plan.

        Returns (is_valid, errors).
        """
        errors = []

        # Check top-level fields
        if not isinstance(requirements, dict):
            return False, ["Requirements must be a JSON object"]

        if "format" not in requirements:
            errors.append("Missing required field: format")
        if "platform" not in requirements:
            errors.append("Missing required field: platform")
        if "categories" not in requirements:
            errors.append("Missing required field: categories")
            return False, errors

        categories = requirements.get("categories", [])
        if not isinstance(categories, list):
            errors.append("categories must be an array")
            return False, errors

        seen_categories = set()
        for cat_entry in categories:
            if not isinstance(cat_entry, dict):
                errors.append("Each category entry must be an object")
                continue

            cat_key = cat_entry.get("category", "")
            if not cat_key:
                errors.append("Category entry missing 'category' field")
                continue

            if not self.registry.is_valid_category(cat_key):
                errors.append(f"Unknown category: {cat_key}")
                continue

            if cat_key in seen_categories:
                errors.append(f"Duplicate category: {cat_key}")
                continue
            seen_categories.add(cat_key)

            roles = cat_entry.get("roles", [])
            if not isinstance(roles, list):
                errors.append(f"Category {cat_key}: roles must be an array")
                continue

            seen_roles = set()
            for role_entry in roles:
                if not isinstance(role_entry, dict):
                    errors.append(f"Category {cat_key}: each role must be an object")
                    continue

                role_key = role_entry.get("role", "")
                if not role_key:
                    errors.append(f"Category {cat_key}: role missing 'role' field")
                    continue

                if not self.registry.is_valid_role(cat_key, role_key):
                    errors.append(f"Unknown role '{role_key}' in category '{cat_key}'")
                    continue

                if role_key in seen_roles:
                    errors.append(f"Duplicate role '{role_key}' in category '{cat_key}'")
                    continue
                seen_roles.add(role_key)

                # Check required boolean fields
                for field in ["required", "none_allowed", "preview_required"]:
                    if field not in role_entry:
                        errors.append(
                            f"Category {cat_key} role {role_key}: missing '{field}'"
                        )
                    elif not isinstance(role_entry[field], bool):
                        errors.append(
                            f"Category {cat_key} role {role_key}: '{field}' must be boolean"
                        )

                # Check beat_refs is an array of strings
                beat_refs = role_entry.get("beat_refs", [])
                if not isinstance(beat_refs, list):
                    errors.append(
                        f"Category {cat_key} role {role_key}: beat_refs must be an array"
                    )
                elif not all(isinstance(r, str) for r in beat_refs):
                    errors.append(
                        f"Category {cat_key} role {role_key}: beat_refs must be strings"
                    )

                # If requires_rationale is true and none_allowed is true,
                # that's valid — rationale is needed when none is chosen
                # (mechanical check, not creative judgment)

        return len(errors) == 0, errors


# ── Store ──────────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS component_requirements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    production_session_id INTEGER NOT NULL,
    draft_id INTEGER NOT NULL,
    asset_id INTEGER NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    requirements_json TEXT NOT NULL,
    requirements_hash TEXT NOT NULL,
    format TEXT,
    platform TEXT,
    provenance_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (production_session_id) REFERENCES production_sessions(id),
    FOREIGN KEY (draft_id) REFERENCES drafts(id),
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE INDEX IF NOT EXISTS idx_req_session ON component_requirements(production_session_id);
CREATE INDEX IF NOT EXISTS idx_req_asset ON component_requirements(asset_id);
CREATE INDEX IF NOT EXISTS idx_req_business ON component_requirements(business_slug);
"""


def compute_requirements_hash(requirements: dict) -> str:
    """Compute a canonical content hash for a requirements plan."""
    canonical = json.dumps(requirements, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ComponentRequirementsStore:
    """Persists component requirement plans with provenance."""

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def save_requirements(
        self,
        business_slug: str,
        production_session_id: int,
        draft_id: int,
        asset_id: int,
        requirements: dict,
        provenance: dict = None,
    ) -> dict:
        """Save a new requirements version. Versions are append-only."""
        req_hash = compute_requirements_hash(requirements)
        ts = self._now()

        # Get current max version for this session
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT MAX(version) as max_v FROM component_requirements WHERE production_session_id = ?",
            (production_session_id,),
        ).fetchone()
        next_version = (row["max_v"] or 0) + 1

        cursor = conn.execute(
            """INSERT INTO component_requirements
               (business_slug, production_session_id, draft_id, asset_id,
                version, requirements_json, requirements_hash, format, platform,
                provenance_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (business_slug, production_session_id, draft_id, asset_id,
             next_version, json.dumps(requirements, ensure_ascii=False),
             req_hash, requirements.get("format"), requirements.get("platform"),
             json.dumps(provenance, ensure_ascii=False) if provenance else None,
             ts),
        )
        req_id = cursor.lastrowid
        conn.commit()
        row = conn.execute(
            "SELECT * FROM component_requirements WHERE id = ?", (req_id,)
        ).fetchone()
        conn.close()
        return dict(row)

    def get_current_requirements(
        self, business_slug: str, production_session_id: int
    ) -> Optional[dict]:
        """Get the latest requirements version for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM component_requirements
               WHERE business_slug = ? AND production_session_id = ?
               ORDER BY version DESC LIMIT 1""",
            (business_slug, production_session_id),
        ).fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        req_json = result.get("requirements_json")
        if isinstance(req_json, str):
            result["requirements_json"] = json.loads(req_json)
        elif isinstance(req_json, dict):
            pass  # already parsed
        prov = result.get("provenance_json")
        if prov and isinstance(prov, str):
            result["provenance_json"] = json.loads(prov)
        return result

    def get_requirements_by_hash(self, req_hash: str) -> Optional[dict]:
        """Get requirements by hash (for lineage verification)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM component_requirements WHERE requirements_hash = ?",
            (req_hash,),
        ).fetchone()
        conn.close()
        if not row:
            return None
        result = dict(row)
        result["requirements_json"] = json.loads(result["requirements_json"])
        return result

    def list_versions(
        self, business_slug: str, production_session_id: int
    ) -> list[dict]:
        """List all requirement versions for a session."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, version, requirements_hash, format, platform, created_at
               FROM component_requirements
               WHERE business_slug = ? AND production_session_id = ?
               ORDER BY version DESC""",
            (business_slug, production_session_id),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]