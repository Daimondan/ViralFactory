"""
ViralFactory — Module Store

Stores the 8 living modules as versioned markdown files in modules/{business}/.
Gate-only writes — no module is stored without the user's confirmation.
Schema-checked on load — invalid modules can't be loaded by the drafter.
Version history is visible in the console.
"""

import os
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class GateTokenError(Exception):
    """Raised when a gate token is missing, invalid, or does not match an approval record."""
    pass


def verify_gate_token(db_path: str, run_id: int, gate_token: str) -> dict:
    """
    Verify a gate token against the playbook_runs database.

    A gate token is valid when:
    1. The run exists in playbook_runs
    2. The gate_results for this run contain an 'approve' decision
    3. The token matches "run_{run_id}_approved"

    Returns the gate result dict if valid.
    Raises GateTokenError if invalid.
    """
    if not gate_token:
        raise GateTokenError("No gate token provided. Gate approval is required for writes.")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Ensure table exists (PlaybookRunner creates it, but be defensive)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS playbook_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playbook_name TEXT NOT NULL,
                playbook_version TEXT NOT NULL,
                business_slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                current_step TEXT,
                collected_inputs TEXT,
                llm_outputs TEXT,
                gate_results TEXT,
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()

        row = conn.execute(
            "SELECT * FROM playbook_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if not row:
            raise GateTokenError(f"Run {run_id} not found.")

        # Convert Row to dict for safe .get() access
        row_dict = dict(row)
        gate_results = json.loads(row_dict.get("gate_results") or "{}")

        # Find any 'approve' decision in the gate results
        approved_step = None
        for step, result in gate_results.items():
            if isinstance(result, dict) and result.get("decision") == "approve":
                approved_step = step
                break

        if not approved_step:
            raise GateTokenError(
                f"Run {run_id} has no approved gate decision. "
                f"Gate approval is required before writing modules or config."
            )

        # Verify the token
        expected_token = f"run_{run_id}_approved"
        if gate_token != expected_token:
            raise GateTokenError(
                f"Invalid gate token. Expected '{expected_token}', got '{gate_token}'."
            )

        return gate_results[approved_step]
    finally:
        conn.close()


def generate_gate_token(run_id: int) -> str:
    """Generate a gate token for a run that has an approved gate decision."""
    return f"run_{run_id}_approved"


class ModuleStore:
    """Versioned markdown module storage with gate enforcement."""

    def __init__(self, modules_dir: str = "modules", db_path: str = "data/viralfactory.db"):
        self.modules_dir = modules_dir
        self.db_path = db_path

    def _module_path(self, business_slug: str, module_name: str) -> Path:
        """Get the path to a module file."""
        return Path(self.modules_dir) / business_slug / f"{module_name}.md"

    def _version_dir(self, business_slug: str, module_name: str) -> Path:
        """Get the path to the version history directory."""
        return Path(self.modules_dir) / business_slug / "versions" / module_name

    def store(self, business_slug: str, module_name: str, content: str,
              version: str = "1.0", provenance: dict = None,
              gate_token: str = None, run_id: int = None,
              status: str = "approved") -> str:
        """
        Store a module as versioned markdown.
        Returns the path to the stored module.

        P1-1: status parameter controls gate enforcement:
        - "approved" (default): gate_token + run_id required (existing behavior).
        - "draft": no gate token needed (onboarding auto-drafts). Draft-status
          modules never feed production pipelines.

        Gate enforcement: for approved modules, a valid gate_token (verified
        against the runs DB) is required before writing. The caller must have
        recorded an 'approve' gate decision on the run BEFORE calling this method.

        Raises GateTokenError if the gate token is missing or invalid (approved only).
        """
        if not business_slug or business_slug == "unknown":
            raise GateTokenError(
                f"Cannot write module with business_slug='{business_slug}'. "
                f"A valid business slug is required — orphans are not permitted."
            )

        # Gate enforcement only for approved modules
        if status == "approved":
            if not gate_token or run_id is None:
                raise GateTokenError(
                    "Gate token and run_id are required for approved module writes. "
                    "Record a gate approval on the run first, then pass the token."
                )
            # Verify the gate token against the DB
            verify_gate_token(self.db_path, run_id, gate_token)

        path = self._module_path(business_slug, module_name)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Archive previous version if it exists
        if path.exists():
            self._archive_version(business_slug, module_name, path)

        # P1-1: Prepend status marker for draft modules
        if status == "draft":
            # Insert a status marker at the top of the file
            content = f"<!-- status: draft -->\n{content}"

        # Write the new version
        path.write_text(content)

        # Store provenance alongside
        if provenance:
            prov_path = path.parent / f"{module_name}_provenance.json"
            prov_path.write_text(json.dumps(provenance, indent=2))

        return str(path)

    def get_status(self, business_slug: str, module_name: str) -> str:
        """P1-1: Get the status of a module ('draft' or 'approved').
        Checks for the status marker comment at the top of the file."""
        content = self.load(business_slug, module_name)
        if not content:
            return "none"
        if content.startswith("<!-- status: draft -->"):
            return "draft"
        return "approved"

    def promote_to_approved(self, business_slug: str, module_name: str,
                            gate_token: str = None, run_id: int = None) -> str:
        """P1-1: Promote a draft module to approved status.
        Removes the draft status marker and enforces the gate.
        Returns the path to the promoted module."""
        if not gate_token or run_id is None:
            raise GateTokenError(
                "Gate token and run_id are required to promote a draft to approved."
            )
        verify_gate_token(self.db_path, run_id, gate_token)

        content = self.load(business_slug, module_name)
        if not content:
            raise ValueError(f"Module '{module_name}' not found for '{business_slug}'")

        # Remove the draft status marker
        if content.startswith("<!-- status: draft -->\n"):
            content = content[len("<!-- status: draft -->\n"):]

        path = self._module_path(business_slug, module_name)
        # Archive the draft version
        if path.exists():
            self._archive_version(business_slug, module_name, path)
        path.write_text(content)
        return str(path)

    def load(self, business_slug: str, module_name: str) -> Optional[str]:
        """Load a module's current version. Returns None if not found."""
        path = self._module_path(business_slug, module_name)
        if not path.exists():
            return None
        return path.read_text()

    def load_validated(self, business_slug: str, module_name: str) -> Optional[str]:
        """Load a module and validate its schema marker.

        T2.5: Checks that the module file has a valid schema marker
        (e.g. 'Schema: voice_profile_v1'). Invalid modules can't be loaded
        by the drafter. Returns the content if valid, raises ValueError if
        the schema marker is missing or unknown.
        """
        content = self.load(business_slug, module_name)
        if not content:
            return None

        # Extract schema marker
        import re
        schema_match = re.search(r'Schema:\s*(\w+)', content)
        if not schema_match:
            raise ValueError(
                f"Module '{module_name}' for '{business_slug}' has no schema marker. "
                f"Cannot be loaded by the drafter."
            )
        schema_name = schema_match.group(1)

        # Known valid schema names
        VALID_SCHEMAS = {
            "voice_profile_v1", "brand_context_v1", "source_criteria_v1",
            "viral_patterns_v1", "audience_insights_v1", "story_frameworks_v1",
            "format_guide_v1", "visual_style_v1", "shot_library_v1",
        }
        if schema_name not in VALID_SCHEMAS:
            raise ValueError(
                f"Module '{module_name}' has unknown schema '{schema_name}'. "
                f"Valid schemas: {sorted(VALID_SCHEMAS)}"
            )
        return content

    def load_json(self, business_slug: str, module_name: str) -> Optional[dict]:
        """Load a module and parse its JSON metadata block (if present)."""
        content = self.load(business_slug, module_name)
        if not content:
            return None

        # Extract JSON metadata from a ```json block at the top
        match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

    def list_versions(self, business_slug: str, module_name: str) -> list[dict]:
        """List all archived versions of a module."""
        version_dir = self._version_dir(business_slug, module_name)
        if not version_dir.exists():
            return []

        versions = []
        for f in sorted(version_dir.glob("*.md")):
            # Parse version and timestamp from filename: v1.0_20260702_120000.md
            match = re.match(r'v([\d.]+)_(\d{8}_\d{6})\.md', f.name)
            if match:
                versions.append({
                    "version": match.group(1),
                    "timestamp": match.group(2),
                    "filename": f.name,
                })
        return versions

    def exists(self, business_slug: str, module_name: str) -> bool:
        """Check if a module exists."""
        return self._module_path(business_slug, module_name).exists()

    def _archive_version(self, business_slug: str, module_name: str, current_path: Path):
        """Archive the current version before overwriting."""
        content = current_path.read_text()

        # Extract version from the header line: # Voice Profile — X — v1.0
        match = re.search(r'v(\d+\.\d+)', content)
        version = match.group(1) if match else "0.0"

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        version_dir = self._version_dir(business_slug, module_name)
        version_dir.mkdir(parents=True, exist_ok=True)
        archive_path = version_dir / f"v{version}_{ts}.md"
        archive_path.write_text(content)

    def list_modules(self, business_slug: str) -> list[str]:
        """List all module names for a business."""
        biz_dir = Path(self.modules_dir) / business_slug
        if not biz_dir.exists():
            return []
        return [f.stem for f in biz_dir.glob("*.md")]


# Voice Profile output schema (for the validator)
VOICE_PROFILE_SCHEMA = {
    "type": "object",
    "required": ["identity_line", "audience", "positive_patterns", "dialect_features",
                 "anti_patterns", "tells_checklist"],
    "properties": {
        "identity_line": {"type": "string"},
        "audience": {"type": "string"},
        "positive_patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["dimension", "pattern", "evidence"],
                "properties": {
                    "dimension": {"type": "string"},
                    "pattern": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "dialect_features": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["feature", "evidence", "do_not_sanitize"],
                "properties": {
                    "feature": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "do_not_sanitize": {"type": "boolean"},
                },
            },
        },
        "anti_patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["pattern", "evidence_of_absence"],
                "properties": {
                    "pattern": {"type": "string"},
                    "evidence_of_absence": {"type": "string"},
                },
            },
        },
        "tells_checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tell", "check"],
                "properties": {
                    "tell": {"type": "string"},
                    "check": {"type": "string"},
                },
            },
        },
    },
}


def voice_profile_to_markdown(profile: dict, business_name: str, version: str = "1.0") -> str:
    """
    Convert a validated Voice Profile JSON into the markdown schema
    defined in the playbook (fixed headings the drafter depends on).
    """
    lines = [f"# Voice Profile — {business_name} — v{version}"]

    lines.append(f"\n## Identity line\n{profile.get('identity_line', '')}")
    lines.append(f"\n## Audience\n{profile.get('audience', '')}")

    lines.append("\n## Positive patterns")
    for p in profile.get("positive_patterns", []):
        lines.append(f"- **[{p['dimension']}]** {p['pattern']}")
        for ev in p.get("evidence", []):
            lines.append(f'  - "{ev}"')

    lines.append("\n## Dialect & register")
    for d in profile.get("dialect_features", []):
        dns = "DO NOT SANITIZE" if d.get("do_not_sanitize") else ""
        lines.append(f"- {d['feature']} {dns}")
        for ev in d.get("evidence", []):
            lines.append(f'  - "{ev}"')

    lines.append("\n## Anti-patterns")
    for a in profile.get("anti_patterns", []):
        lines.append(f"- {a['pattern']}")
        lines.append(f"  - Evidence of absence: {a['evidence_of_absence']}")

    lines.append("\n## Tells Checklist")
    for t in profile.get("tells_checklist", []):
        lines.append(f"- **{t['tell']}** — {t['check']}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: voice_profile_v1")

    return "\n".join(lines)


# Business Profile output schema (for the validator)
BUSINESS_PROFILE_SCHEMA = {
    "type": "object",
    "required": ["business", "brands", "subjects", "platforms",
                 "goals", "red_lines", "audience_description"],
    "properties": {
        "business": {
            "type": "object",
            "required": ["name", "slug", "description"],
            "properties": {
                "name": {"type": "string"},
                "slug": {"type": "string"},
                "description": {"type": "string"},
            },
        },
        "brands": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "purpose"],
                "properties": {
                    "name": {"type": "string"},
                    "purpose": {"type": "string"},
                },
            },
        },
        "subjects": {
            "type": "array",
            "items": {"type": "string"},
        },
        "platforms": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "handle", "priority"],
                "properties": {
                    "name": {"type": "string"},
                    "handle": {"type": "string"},
                    "priority": {"type": "integer"},
                },
            },
        },
        "goals": {
            "type": "array",
            "items": {"type": "string"},
        },
        "red_lines": {
            "type": "array",
            "items": {"type": "string"},
        },
        "audience_description": {"type": "string"},
    },
}


def business_profile_to_yaml(profile: dict) -> str:
    """Convert a validated business profile JSON into YAML for config/business.yaml."""
    import yaml as _yaml
    return _yaml.dump(profile, default_flow_style=False, sort_keys=False, allow_unicode=True)


def brand_context_to_markdown(profile: dict, version: str = "1.0") -> str:
    """
    Convert a validated business profile JSON into the brand-context module
    markdown that the drafter loads.
    """
    biz = profile["business"]
    lines = [f"# Brand Context — {biz['name']} — v{version}"]

    lines.append(f"\n## Business\n- **Name:** {biz['name']}")
    lines.append(f"- **Slug:** {biz['slug']}")
    lines.append(f"- **Description:** {biz['description']}")

    lines.append("\n## Brands")
    for b in profile.get("brands", []):
        lines.append(f"- **{b['name']}** — {b['purpose']}")

    lines.append("\n## Subjects (tag taxonomy)")
    for s in profile.get("subjects", []):
        lines.append(f"- {s}")

    lines.append("\n## Platforms")
    for p in profile.get("platforms", []):
        lines.append(f"- **{p['name']}** ({p['handle']}) — priority {p['priority']}")

    lines.append("\n## Goals")
    for g in profile.get("goals", []):
        lines.append(f"- {g}")

    lines.append("\n## Red lines (never do)")
    for r in profile.get("red_lines", []):
        lines.append(f"- {r}")

    lines.append(f"\n## Audience\n{profile.get('audience_description', '')}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: brand_context_v1")

    return "\n".join(lines)


# Source Criteria output schema (for the validator)
SOURCE_CRITERIA_SCHEMA = {
    "type": "object",
    "required": [
        "subjects_covered", "formats_favored", "freshness",
        "quality_signals", "disqualifiers", "regional_relevance",
        "monitoring_plan", "criteria_summary",
    ],
    "properties": {
        "subjects_covered": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["subject", "evidence"],
                "properties": {
                    "subject": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "formats_favored": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["format", "evidence"],
                "properties": {
                    "format": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "freshness": {
            "type": "object",
            "required": ["expectation", "evidence"],
            "properties": {
                "expectation": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
        },
        "quality_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["signal", "description", "evidence"],
                "properties": {
                    "signal": {"type": "string"},
                    "description": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "disqualifiers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["disqualifier", "evidence"],
                "properties": {
                    "disqualifier": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "regional_relevance": {
            "type": "object",
            "required": ["requirement", "evidence"],
            "properties": {
                "requirement": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
        },
        "monitoring_plan": {
            "type": "object",
            "required": ["feeds", "channels", "queries"],
            "properties": {
                "feeds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "url", "type", "enabled"],
                        "properties": {
                            "name": {"type": "string"},
                            "url": {"type": "string"},
                            "type": {"type": "string"},
                            "enabled": {"type": "boolean"},
                        },
                    },
                },
                "channels": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["name", "platform", "handle", "enabled"],
                        "properties": {
                            "name": {"type": "string"},
                            "platform": {"type": "string"},
                            "handle": {"type": "string"},
                            "enabled": {"type": "boolean"},
                        },
                    },
                },
                "queries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["query", "engine", "enabled"],
                        "properties": {
                            "query": {"type": "string"},
                            "engine": {"type": "string"},
                            "enabled": {"type": "boolean"},
                        },
                    },
                },
            },
        },
        "criteria_summary": {"type": "string"},
    },
}


def source_criteria_to_markdown(criteria: dict, version: str = "1.0") -> str:
    """Convert validated Source Criteria JSON into the module markdown."""
    lines = [f"# Source Criteria — v{version}"]

    lines.append(f"\n## Summary\n{criteria.get('criteria_summary', '')}")

    lines.append("\n## Subjects covered")
    for s in criteria.get("subjects_covered", []):
        lines.append(f"- **{s['subject']}**")
        for ev in s.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    lines.append("\n## Formats favored")
    for f in criteria.get("formats_favored", []):
        lines.append(f"- **{f['format']}**")
        for ev in f.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    fr = criteria.get("freshness", {})
    lines.append(f"\n## Freshness\n{fr.get('expectation', '')}")
    for ev in fr.get("evidence", []):
        lines.append(f'- Evidence: "{ev}"')

    lines.append("\n## Quality signals")
    for q in criteria.get("quality_signals", []):
        lines.append(f"- **{q['signal']}** — {q['description']}")
        for ev in q.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    lines.append("\n## Disqualifiers")
    for d in criteria.get("disqualifiers", []):
        lines.append(f"- **{d['disqualifier']}**")
        for ev in d.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    rr = criteria.get("regional_relevance", {})
    lines.append(f"\n## Regional relevance\n{rr.get('requirement', '')}")
    for ev in rr.get("evidence", []):
        lines.append(f'- Evidence: "{ev}"')

    lines.append("\n## Monitoring plan")
    mp = criteria.get("monitoring_plan", {})
    if mp.get("feeds"):
        lines.append("\n### Feeds")
        for f in mp["feeds"]:
            lines.append(f"- {f['name']} ({f['type']}) — {f['url']}")
    if mp.get("channels"):
        lines.append("\n### Channels")
        for c in mp["channels"]:
            lines.append(f"- {c['name']} ({c['platform']}/{c['handle']})")
    if mp.get("queries"):
        lines.append("\n### Search queries")
        for q in mp["queries"]:
            lines.append(f"- \"{q['query']}\" ({q['engine']})")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: source_criteria_v1")

    return "\n".join(lines)


def monitoring_plan_to_yaml(criteria: dict) -> str:
    """Extract the monitoring plan from Source Criteria JSON into sources.yaml format."""
    import yaml as _yaml
    mp = criteria.get("monitoring_plan", {})
    sources = {
        "feeds": mp.get("feeds", []),
        "channels": mp.get("channels", []),
        "queries": mp.get("queries", []),
    }
    return _yaml.dump(sources, default_flow_style=False, sort_keys=False, allow_unicode=True)


# ────────────────────────────────────────────────────────────────────
# T2.3: Viral Patterns + Audience Insights + Story Frameworks + Format Guide
# ────────────────────────────────────────────────────────────────────

# --- Viral Patterns ---

VIRAL_PATTERNS_SCHEMA = {
    "type": "object",
    "required": ["patterns", "never_list", "summary"],
    "properties": {
        "patterns": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "hook_type", "structure", "emotional_beat",
                             "format", "pacing", "why_it_likely_worked", "examples"],
                "properties": {
                    "name": {"type": "string"},
                    "hook_type": {"type": "string"},
                    "structure": {"type": "string"},
                    "emotional_beat": {"type": "string"},
                    "format": {"type": "string"},
                    "pacing": {"type": "string"},
                    "why_it_likely_worked": {"type": "string"},
                    "examples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["url", "name"],
                            "properties": {
                                "url": {"type": "string"},
                                "name": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
        "never_list": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["pattern", "reason", "evidence"],
                "properties": {
                    "pattern": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


def viral_patterns_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert validated Viral Patterns JSON into the module markdown."""
    lines = [f"# Viral Patterns Playbook — v{version}"]

    lines.append(f"\n## Summary\n{data.get('summary', '')}")

    lines.append("\n## Patterns")
    for p in data.get("patterns", []):
        lines.append(f"\n### {p['name']}")
        lines.append(f"- **Hook type:** {p['hook_type']}")
        lines.append(f"- **Structure:** {p['structure']}")
        lines.append(f"- **Emotional beat:** {p['emotional_beat']}")
        lines.append(f"- **Format:** {p['format']}")
        lines.append(f"- **Pacing:** {p['pacing']}")
        lines.append(f"- **Why it likely worked (hypothesis):** {p['why_it_likely_worked']}")
        lines.append("- **Examples:**")
        for ex in p.get("examples", []):
            lines.append(f'  - [{ex.get("name", ex.get("url", ""))}]({ex.get("url", "")}) — {ex.get("note", "")}')

    lines.append("\n## Never list")
    for n in data.get("never_list", []):
        lines.append(f"- **{n['pattern']}** — {n['reason']}")
        lines.append(f'  - Evidence: "{n["evidence"]}"')

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: viral_patterns_v1")

    return "\n".join(lines)


# --- Audience Insights ---

AUDIENCE_INSIGHTS_SCHEMA = {
    "type": "object",
    "required": ["who_they_are", "what_they_care_about", "language",
                 "what_they_reward", "what_turns_them_off", "summary"],
    "properties": {
        "who_they_are": {"type": "string"},
        "what_they_care_about": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["concern", "type", "evidence"],
                "properties": {
                    "concern": {"type": "string"},
                    "type": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "language": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["phrase", "type"],
                "properties": {
                    "phrase": {"type": "string"},
                    "context": {"type": "string"},
                    "type": {"type": "string"},
                },
            },
        },
        "what_they_reward": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["behavior", "type", "evidence"],
                "properties": {
                    "behavior": {"type": "string"},
                    "type": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "what_turns_them_off": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["turn_off", "type", "evidence"],
                "properties": {
                    "turn_off": {"type": "string"},
                    "type": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "evidence_vs_belief": {"type": "string"},
        "summary": {"type": "string"},
    },
}


def audience_insights_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert validated Audience Insights JSON into the module markdown."""
    lines = [f"# Audience Insights — v{version}"]

    lines.append(f"\n## Who they are\n{data.get('who_they_are', '')}")

    lines.append("\n## What they care about")
    for c in data.get("what_they_care_about", []):
        lines.append(f"- **{c['concern']}** ({c['type']})")
        for ev in c.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    lines.append("\n## Language they use")
    for l in data.get("language", []):
        lines.append(f'- "{l["phrase"]}" ({l["type"]})')
        if l.get("context"):
            lines.append(f'  - Context: {l["context"]}')

    lines.append("\n## What they reward")
    for r in data.get("what_they_reward", []):
        lines.append(f"- **{r['behavior']}** ({r['type']})")
        for ev in r.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    lines.append("\n## What turns them off")
    for t in data.get("what_turns_them_off", []):
        lines.append(f"- **{t['turn_off']}** ({t['type']})")
        for ev in t.get("evidence", []):
            lines.append(f'  - Evidence: "{ev}"')

    evb = data.get("evidence_vs_belief")
    if evb:
        lines.append(f"\n## Evidence vs belief\n{evb}")

    lines.append(f"\n## Summary\n{data.get('summary', '')}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: audience_insights_v1")

    return "\n".join(lines)


# --- Story Frameworks ---

STORY_FRAMEWORKS_SCHEMA = {
    "type": "object",
    "required": ["frameworks", "summary"],
    "properties": {
        "frameworks": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["subject_type", "entry_point", "tension", "turn",
                             "landing", "grounded_in_example", "grounded_in_story",
                             "voice_compatible", "voice_note"],
                "properties": {
                    "subject_type": {"type": "string"},
                    "entry_point": {"type": "string"},
                    "tension": {"type": "string"},
                    "turn": {"type": "string"},
                    "landing": {"type": "string"},
                    "grounded_in_example": {"type": "string"},
                    "grounded_in_story": {"type": "string"},
                    "voice_compatible": {"type": "boolean"},
                    "voice_note": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


def story_frameworks_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert validated Story Frameworks JSON into the module markdown."""
    lines = [f"# Story Frameworks — v{version}"]

    lines.append(f"\n## Summary\n{data.get('summary', '')}")

    lines.append("\n## Frameworks")
    for f in data.get("frameworks", []):
        lines.append(f"\n### {f['subject_type']}")
        lines.append(f"- **Entry point:** {f['entry_point']}")
        lines.append(f"- **Tension:** {f['tension']}")
        lines.append(f"- **Turn:** {f['turn']}")
        lines.append(f"- **Landing:** {f['landing']}")
        lines.append(f"- **Grounded in example:** {f['grounded_in_example']}")
        lines.append(f"- **Grounded in story:** {f['grounded_in_story']}")
        vc = "✓" if f.get("voice_compatible") else "✗"
        lines.append(f"- **Voice compatible:** {vc}")
        if f.get("voice_note"):
            lines.append(f"- **Voice note:** {f['voice_note']}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: story_frameworks_v1")

    return "\n".join(lines)


# --- Format Guide (with AMENDMENT-004 enrichment) ---

FORMAT_GUIDE_SCHEMA = {
    "type": "object",
    "required": ["formats", "decision_table", "summary"],
    "properties": {
        "formats": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["format_name", "platforms", "best_for", "length",
                             "structure_notes", "skeleton", "requires_human_capture",
                             "capture_tasks", "effort_level", "reuse_pathways",
                             "status", "provenance"],
                "properties": {
                    "format_name": {"type": "string"},
                    "platforms": {"type": "array", "items": {"type": "string"}},
                    "best_for": {"type": "array", "items": {"type": "string"}},
                    "length": {"type": "string"},
                    "structure_notes": {"type": "string"},
                    "skeleton": {"type": "string"},
                    "requires_human_capture": {"type": "string"},
                    "capture_tasks": {"type": "array", "items": {"type": "string"}},
                    "effort_level": {"type": "string"},
                    "reuse_pathways": {"type": "array", "items": {"type": "string"}},
                    "status": {"type": "string"},
                    "provenance": {"type": "string"},
                },
            },
        },
        "decision_table": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["message_type", "platform", "recommended_format", "rationale"],
                "properties": {
                    "message_type": {"type": "string"},
                    "platform": {"type": "string"},
                    "recommended_format": {"type": "string"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "summary": {"type": "string"},
    },
}


def format_guide_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert validated Format Guide JSON into the module markdown."""
    lines = [f"# Format Guide — v{version}"]

    lines.append(f"\n## Summary\n{data.get('summary', '')}")

    lines.append("\n## Formats")
    for f in data.get("formats", []):
        lines.append(f"\n### {f['format_name']}")
        lines.append(f"- **Platforms:** {', '.join(f.get('platforms', []))}")
        lines.append(f"- **Best for:** {', '.join(f.get('best_for', []))}")
        lines.append(f"- **Length:** {f.get('length', '')}")
        lines.append(f"- **Effort level:** {f.get('effort_level', '')}")
        lines.append(f"- **Requires human capture:** {f.get('requires_human_capture', 'none')}")
        if f.get("capture_tasks"):
            lines.append("- **Capture tasks:**")
            for task in f["capture_tasks"]:
                lines.append(f"  - {task}")
        lines.append(f"- **Status:** {f.get('status', 'proven')}")
        lines.append(f"- **Reuse pathways:** {', '.join(f.get('reuse_pathways', []))}")
        lines.append(f"- **Provenance:** {f.get('provenance', '')}")
        lines.append(f"- **Structure notes:** {f.get('structure_notes', '')}")
        lines.append(f"\n**Skeleton:**\n```\n{f.get('skeleton', '')}\n```")

    lines.append("\n## Decision table")
    for d in data.get("decision_table", []):
        lines.append(f"- **{d['message_type']}** on {d['platform']} → **{d['recommended_format']}**")
        lines.append(f'  - Rationale: {d["rationale"]}')

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: format_guide_v1")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
# T2.4: Visual Style Guide + Shot Library
# ────────────────────────────────────────────────────────────────────

SHOT_LIBRARY_ITEM_SCHEMA = {
    "type": "object",
    "required": ["description", "tags", "mood", "best_for", "platforms"],
    "properties": {
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "mood": {"type": "string"},
        "best_for": {"type": "array", "items": {"type": "string"}},
        "platforms": {"type": "array", "items": {"type": "string"}},
    },
}


VISUAL_STYLE_SCHEMA = {
    "type": "object",
    "required": ["palette", "typography", "stylization_level",
                 "blend_rules", "platform_adjustments", "summary"],
    "properties": {
        "palette": {
            "type": "object",
            "required": ["primary", "secondary", "accent", "background"],
            "properties": {
                "primary": {"type": "object", "required": ["hex", "name"],
                    "properties": {"hex": {"type": "string"}, "name": {"type": "string"}}},
                "secondary": {"type": "object", "required": ["hex", "name"],
                    "properties": {"hex": {"type": "string"}, "name": {"type": "string"}}},
                "accent": {"type": "object", "required": ["hex", "name"],
                    "properties": {"hex": {"type": "string"}, "name": {"type": "string"}}},
                "background": {"type": "object", "required": ["hex", "name"],
                    "properties": {"hex": {"type": "string"}, "name": {"type": "string"}}},
            },
        },
        "typography": {
            "type": "object",
            "required": ["feel", "weight", "sizing"],
            "properties": {
                "feel": {"type": "string"},
                "weight": {"type": "string"},
                "sizing": {"type": "string"},
            },
        },
        "stylization_level": {"type": "string"},
        "stylization_rationale": {"type": "string"},
        "blend_rules": {
            "type": "object",
            "required": ["real_anchors", "generated_supporting", "disclosure"],
            "properties": {
                "real_anchors": {"type": "array", "items": {"type": "string"}},
                "generated_supporting": {"type": "array", "items": {"type": "string"}},
                "disclosure": {"type": "array", "items": {"type": "string"}},
            },
        },
        "platform_adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["platform", "aspect_ratio", "notes"],
                "properties": {
                    "platform": {"type": "string"},
                    "aspect_ratio": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
        },
        "shot_library_usage": {"type": "string"},
        "summary": {"type": "string"},
    },
}


def visual_style_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert validated Visual Style Guide JSON into the module markdown."""
    lines = [f"# Visual Style Guide — v{version}"]

    lines.append(f"\n## Summary\n{data.get('summary', '')}")

    lines.append("\n## Palette")
    pal = data.get("palette", {})
    for key in ["primary", "secondary", "accent", "background"]:
        c = pal.get(key, {})
        lines.append(f"- **{key.title()}:** {c.get('name', '')} ({c.get('hex', '')})")

    lines.append("\n## Typography")
    typ = data.get("typography", {})
    lines.append(f"- **Feel:** {typ.get('feel', '')}")
    lines.append(f"- **Weight:** {typ.get('weight', '')}")
    lines.append(f"- **Sizing:** {typ.get('sizing', '')}")

    lines.append(f"\n## Stylization level\n{data.get('stylization_level', '')}")
    if data.get("stylization_rationale"):
        lines.append(f"\n{data['stylization_rationale']}")

    lines.append("\n## Blend rules")
    br = data.get("blend_rules", {})
    lines.append("\n### Real anchors (require real footage)")
    for r in br.get("real_anchors", []):
        lines.append(f"- {r}")
    lines.append("\n### Generated supporting (what AI visuals are for)")
    for g in br.get("generated_supporting", []):
        lines.append(f"- {g}")
    lines.append("\n### Disclosure (platform AI-disclosure rules)")
    for d in br.get("disclosure", []):
        lines.append(f"- {d}")

    lines.append("\n## Platform adjustments")
    for p in data.get("platform_adjustments", []):
        lines.append(f"- **{p['platform']}** — {p['aspect_ratio']}: {p['notes']}")

    if data.get("shot_library_usage"):
        lines.append(f"\n## Shot library usage\n{data['shot_library_usage']}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: visual_style_v1")

    return "\n".join(lines)


def shot_library_to_markdown(items: list, version: str = "1.0") -> str:
    """Convert a list of indexed shot-library items into the module markdown."""
    lines = [f"# Shot Library — v{version}"]
    lines.append(f"\n*{len(items)} indexed items. Grows continuously.*")

    for i, item in enumerate(items, 1):
        lines.append(f"\n### Item {i}")
        lines.append(f"- **Description:** {item.get('description', '')}")
        lines.append(f"- **Tags:** {', '.join(item.get('tags', []))}")
        lines.append(f"- **Mood:** {item.get('mood', '')}")
        lines.append(f"- **Best for:** {', '.join(item.get('best_for', []))}")
        lines.append(f"- **Platforms:** {', '.join(item.get('platforms', []))}")

    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- Schema: shot_library_v1")

    return "\n".join(lines)