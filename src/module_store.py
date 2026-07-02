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
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class ModuleStore:
    """Versioned markdown module storage with gate enforcement."""

    def __init__(self, modules_dir: str = "modules"):
        self.modules_dir = modules_dir

    def _module_path(self, business_slug: str, module_name: str) -> Path:
        """Get the path to a module file."""
        return Path(self.modules_dir) / business_slug / f"{module_name}.md"

    def _version_dir(self, business_slug: str, module_name: str) -> Path:
        """Get the path to the version history directory."""
        return Path(self.modules_dir) / business_slug / "versions" / module_name

    def store(self, business_slug: str, module_name: str, content: str,
              version: str = "1.0", provenance: dict = None) -> str:
        """
        Store a module as versioned markdown.
        Returns the path to the stored module.

        Gate enforcement: this method should only be called AFTER gate approval.
        The caller (playbook runner / gate UI) is responsible for checking.
        """
        path = self._module_path(business_slug, module_name)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Archive previous version if it exists
        if path.exists():
            self._archive_version(business_slug, module_name, path)

        # Write the new version
        path.write_text(content)

        # Store provenance alongside
        if provenance:
            prov_path = path.parent / f"{module_name}_provenance.json"
            prov_path.write_text(json.dumps(provenance, indent=2))

        return str(path)

    def load(self, business_slug: str, module_name: str) -> Optional[str]:
        """Load a module's current version. Returns None if not found."""
        path = self._module_path(business_slug, module_name)
        if not path.exists():
            return None
        return path.read_text()

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