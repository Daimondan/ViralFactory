"""
ViralFactory — Episode Format Module (T11.5 — CORRECTION-episode-format §1.1)

The episode-format module is the "show bible" — it defines the show, not any
episode. It is per-tenant, gated, section-addressable like every other module.

The harness knows the SCHEMA of an episode-format module; it never knows any
tenant's character names or grade string. All show-specific content lives in
the module file (e.g. modules/{business}/episode-format-*.md).

Schema sections per §1.1:
- Cast: recurring characters (name, age, description, wardrobe, demeanor) → character_ref IDs
- World: 4-6 recurring locations → location_ref IDs
- Grade: one verbatim color/light description string (grade_token)
- Beat grammar: ordered roles + rules (hook ≤3s, setup, struggle ×2-4, turn, lesson, cta)
- Delivery mode: narration-over-scenes (no on-camera dialogue, no lip-sync)
- Audio register map: beat registers → music_bed IDs
- Graphics vocabulary: card styles + when the format calls for them
- Critic rubric: Layer-3 editorial checklist (gated, improvable)
"""

import json
import re
from datetime import datetime, timezone


# ── JSON Schema for validation ─────────────────────────────────────────────

EPISODE_FORMAT_SCHEMA = {
    "type": "object",
    "required": [
        "type", "name", "cast", "world", "grade", "beat_grammar",
        "delivery_mode", "audio_register_map", "graphics_vocabulary",
        "critic_rubric",
    ],
    "properties": {
        "type": {
            "type": "string",
            "enum": ["episode-format"],
            "description": "Module type marker — must be 'episode-format'",
        },
        "name": {
            "type": "string",
            "description": "Format name (e.g. 'parable')",
        },
        "version": {
            "type": "string",
            "description": "Module version (e.g. '1.0')",
        },
        "target_duration_s": {
            "type": "number",
            "description": "Target episode duration in seconds (e.g. 90)",
        },
        "cast": {
            "type": "array",
            "description": "Recurring characters — each references a registry character_ref ID",
            "items": {
                "type": "object",
                "required": ["character_ref", "description", "wardrobe", "demeanor"],
                "properties": {
                    "character_ref": {
                        "type": "string",
                        "description": "Registry character_ref ID",
                    },
                    "description": {
                        "type": "string",
                        "description": "Character description — name, age, role",
                    },
                    "wardrobe": {
                        "type": "string",
                        "description": "Fixed wardrobe description",
                    },
                    "demeanor": {
                        "type": "string",
                        "description": "Character demeanor / behavioral notes",
                    },
                },
            },
        },
        "world": {
            "type": "array",
            "description": "4-6 recurring locations, each referencing a registry location_ref ID",
            "minItems": 4,
            "maxItems": 6,
            "items": {
                "type": "object",
                "required": ["location_ref", "description"],
                "properties": {
                    "location_ref": {
                        "type": "string",
                        "description": "Registry location_ref ID",
                    },
                    "description": {
                        "type": "string",
                        "description": "Location description",
                    },
                },
            },
        },
        "grade": {
            "type": "object",
            "required": ["grade_token_ref"],
            "description": "Grade — references the registry grade_token. The verbatim string is injected into every image prompt.",
            "properties": {
                "grade_token_ref": {
                    "type": "string",
                    "description": "Registry grade_token name (default: 'default')",
                },
                "description": {
                    "type": "string",
                    "description": "Human-readable grade description",
                },
            },
        },
        "beat_grammar": {
            "type": "object",
            "required": ["roles", "hook_max_s", "struggle_min", "struggle_max", "target_duration_s"],
            "description": "Ordered roles an episode must contain and their rules",
            "properties": {
                "roles": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered role names (e.g. ['hook', 'setup', 'struggle', 'turn', 'lesson', 'cta'])",
                },
                "hook_max_s": {
                    "type": "number",
                    "description": "Max hook duration in seconds (e.g. 3)",
                },
                "struggle_min": {
                    "type": "integer",
                    "description": "Minimum number of struggle beats (e.g. 2)",
                },
                "struggle_max": {
                    "type": "integer",
                    "description": "Maximum number of struggle beats (e.g. 4)",
                },
                "target_duration_s": {
                    "type": "number",
                    "description": "Target total duration in seconds (e.g. 90)",
                },
            },
        },
        "delivery_mode": {
            "type": "object",
            "required": ["mode"],
            "description": "Delivery mode — narration-over-scenes. No on-camera dialogue, no lip-sync.",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["narration_over_scenes"],
                    "description": "Must be 'narration_over_scenes'",
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Delivery rules (e.g. no on-camera dialogue, no lip-sync)",
                },
            },
        },
        "audio_register_map": {
            "type": "array",
            "description": "Beat registers → registry music_bed IDs. Fixed duck level and LUFS target.",
            "items": {
                "type": "object",
                "required": ["register", "music_bed_ref"],
                "properties": {
                    "register": {
                        "type": "string",
                        "description": "Beat register name (e.g. 'somber', 'hopeful', 'wry')",
                    },
                    "music_bed_ref": {
                        "type": "string",
                        "description": "Registry music_bed ID",
                    },
                    "duck_level_db": {
                        "type": "number",
                        "description": "Duck level in dB when VO is active",
                    },
                    "lufs_target": {
                        "type": "number",
                        "description": "Loudness target in LUFS (e.g. -14)",
                    },
                },
            },
        },
        "graphics_vocabulary": {
            "type": "object",
            "required": ["card_styles", "rules"],
            "description": "Card styles + when the format calls for them. Every number spoken in VO gets a card.",
            "properties": {
                "card_styles": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["card_type", "card_style_ref"],
                        "properties": {
                            "card_type": {
                                "type": "string",
                                "description": "Card type (e.g. 'number_card', 'title_card', 'quote_card')",
                            },
                            "card_style_ref": {
                                "type": "string",
                                "description": "Registry card_style ID",
                            },
                            "when": {
                                "type": "string",
                                "description": "When the format calls for this card",
                            },
                        },
                    },
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Graphics rules (e.g. 'every number spoken in VO gets a card')",
                },
            },
        },
        "critic_rubric": {
            "type": "object",
            "required": ["checks"],
            "description": "Layer-3 editorial checklist (gated, improvable by Analyst through module review gate)",
            "properties": {
                "checks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["criterion", "description"],
                        "properties": {
                            "criterion": {
                                "type": "string",
                                "description": "Criterion name (e.g. 'hook_contradiction')",
                            },
                            "description": {
                                "type": "string",
                                "description": "What the critic checks",
                            },
                            "weight": {
                                "type": "number",
                                "description": "Optional weight for scoring",
                            },
                        },
                    },
                },
                "notes": {
                    "type": "string",
                    "description": "Additional rubric notes",
                },
            },
        },
    },
}


# ── Validation ─────────────────────────────────────────────────────────────

def validate_episode_format(data: dict) -> list:
    """Validate an episode-format module dict against the schema.

    Returns a list of error strings (empty if valid).

    This is a lightweight structural validator — it checks required keys,
    types, and constraints. It does NOT resolve registry references (that's
    the Layer-1 lint's job via episode_lints.py).
    """
    errors = []

    # Check required top-level keys
    required = EPISODE_FORMAT_SCHEMA["required"]
    for key in required:
        if key not in data:
            errors.append(f"Missing required key: '{key}'")

    if errors:
        return errors  # Can't continue if top-level keys are missing

    # Type check
    if data.get("type") != "episode-format":
        errors.append(f"type must be 'episode-format', got '{data.get('type')}'")

    # Cast: at least one, each has required sub-keys
    cast = data.get("cast", [])
    if not isinstance(cast, list) or len(cast) == 0:
        errors.append("cast must be a non-empty array")
    else:
        for i, c in enumerate(cast):
            if not isinstance(c, dict):
                errors.append(f"cast[{i}] must be an object")
                continue
            for sub in ["character_ref", "description", "wardrobe", "demeanor"]:
                if sub not in c:
                    errors.append(f"cast[{i}] missing '{sub}'")
                elif not isinstance(c[sub], str) or not c[sub].strip():
                    errors.append(f"cast[{i}].{sub} must be a non-empty string")

    # World: 4-6 locations
    world = data.get("world", [])
    if not isinstance(world, list):
        errors.append("world must be an array")
    elif len(world) < 4 or len(world) > 6:
        errors.append(f"world must have 4-6 locations, got {len(world)}")
    else:
        for i, loc in enumerate(world):
            if not isinstance(loc, dict):
                errors.append(f"world[{i}] must be an object")
                continue
            for sub in ["location_ref", "description"]:
                if sub not in loc:
                    errors.append(f"world[{i}] missing '{sub}'")
                elif not isinstance(loc[sub], str) or not loc[sub].strip():
                    errors.append(f"world[{i}].{sub} must be a non-empty string")

    # Grade
    grade = data.get("grade", {})
    if not isinstance(grade, dict):
        errors.append("grade must be an object")
    elif "grade_token_ref" not in grade:
        errors.append("grade missing 'grade_token_ref'")
    elif not isinstance(grade["grade_token_ref"], str) or not grade["grade_token_ref"].strip():
        errors.append("grade.grade_token_ref must be a non-empty string")

    # Beat grammar
    bg = data.get("beat_grammar", {})
    if not isinstance(bg, dict):
        errors.append("beat_grammar must be an object")
    else:
        for sub in ["roles", "hook_max_s", "struggle_min", "struggle_max", "target_duration_s"]:
            if sub not in bg:
                errors.append(f"beat_grammar missing '{sub}'")
        if "roles" in bg:
            if not isinstance(bg["roles"], list) or len(bg["roles"]) == 0:
                errors.append("beat_grammar.roles must be a non-empty array")
            else:
                # Hook must be first
                if bg["roles"][0] != "hook":
                    errors.append(f"beat_grammar.roles[0] must be 'hook', got '{bg['roles'][0]}'")
                # Must have lesson and cta
                if "lesson" not in bg["roles"]:
                    errors.append("beat_grammar.roles must contain 'lesson'")
                if "cta" not in bg["roles"]:
                    errors.append("beat_grammar.roles must contain 'cta'")
        if "hook_max_s" in bg:
            if not isinstance(bg["hook_max_s"], (int, float)) or bg["hook_max_s"] <= 0:
                errors.append("beat_grammar.hook_max_s must be a positive number")
        if "target_duration_s" in bg:
            if not isinstance(bg["target_duration_s"], (int, float)) or bg["target_duration_s"] <= 0:
                errors.append("beat_grammar.target_duration_s must be a positive number")

    # Delivery mode
    dm = data.get("delivery_mode", {})
    if not isinstance(dm, dict):
        errors.append("delivery_mode must be an object")
    elif dm.get("mode") != "narration_over_scenes":
        errors.append(f"delivery_mode.mode must be 'narration_over_scenes', got '{dm.get('mode')}'")

    # Audio register map: at least one register
    arm = data.get("audio_register_map", [])
    if not isinstance(arm, list) or len(arm) == 0:
        errors.append("audio_register_map must be a non-empty array")
    else:
        for i, entry in enumerate(arm):
            if not isinstance(entry, dict):
                errors.append(f"audio_register_map[{i}] must be an object")
                continue
            for sub in ["register", "music_bed_ref"]:
                if sub not in entry:
                    errors.append(f"audio_register_map[{i}] missing '{sub}'")
                elif not isinstance(entry[sub], str) or not entry[sub].strip():
                    errors.append(f"audio_register_map[{i}].{sub} must be a non-empty string")

    # Graphics vocabulary
    gv = data.get("graphics_vocabulary", {})
    if not isinstance(gv, dict):
        errors.append("graphics_vocabulary must be an object")
    else:
        if "card_styles" not in gv:
            errors.append("graphics_vocabulary missing 'card_styles'")
        elif not isinstance(gv["card_styles"], list):
            errors.append("graphics_vocabulary.card_styles must be an array")
        else:
            for i, cs in enumerate(gv["card_styles"]):
                if not isinstance(cs, dict):
                    errors.append(f"graphics_vocabulary.card_styles[{i}] must be an object")
                    continue
                for sub in ["card_type", "card_style_ref"]:
                    if sub not in cs:
                        errors.append(f"graphics_vocabulary.card_styles[{i}] missing '{sub}'")
        if "rules" not in gv:
            errors.append("graphics_vocabulary missing 'rules'")
        elif not isinstance(gv["rules"], list):
            errors.append("graphics_vocabulary.rules must be an array")

    # Critic rubric
    cr = data.get("critic_rubric", {})
    if not isinstance(cr, dict):
        errors.append("critic_rubric must be an object")
    elif "checks" not in cr:
        errors.append("critic_rubric missing 'checks'")
    elif not isinstance(cr["checks"], list) or len(cr["checks"]) == 0:
        errors.append("critic_rubric.checks must be a non-empty array")
    else:
        for i, check in enumerate(cr["checks"]):
            if not isinstance(check, dict):
                errors.append(f"critic_rubric.checks[{i}] must be an object")
                continue
            for sub in ["criterion", "description"]:
                if sub not in check:
                    errors.append(f"critic_rubric.checks[{i}] missing '{sub}'")

    return errors


# ── Markdown conversion ─────────────────────────────────────────────────────

def episode_format_to_markdown(data: dict, version: str = "1.0") -> str:
    """Convert a validated episode-format module dict into the section-addressable
    markdown that the drafter loads.

    Headings follow the ## = section, ### = entry contract (same as other modules).
    Renaming or removing a ## heading is a breaking change — update views.yaml
    in the same commit.
    """
    lines = [f"# Episode Format — {data.get('name', 'unnamed')} — v{version}"]

    # Summary
    lines.append(f"\n## Summary\nThe show bible for the {data.get('name', 'unnamed')} format. "
                 f"Defines cast, world, grade, beat grammar, delivery mode, audio registers, "
                 f"graphics vocabulary, and the critic rubric. "
                 f"Target duration: {data.get('beat_grammar', {}).get('target_duration_s', 'unspecified')}s.")

    # Cast
    lines.append("\n## Cast")
    for c in data.get("cast", []):
        lines.append(f"\n### {c['character_ref']}")
        lines.append(f"- **Description:** {c.get('description', '')}")
        lines.append(f"- **Wardrobe:** {c.get('wardrobe', '')}")
        lines.append(f"- **Demeanor:** {c.get('demeanor', '')}")

    # World
    lines.append("\n## World")
    for loc in data.get("world", []):
        lines.append(f"\n### {loc['location_ref']}")
        lines.append(f"- **Description:** {loc.get('description', '')}")

    # Grade
    lines.append("\n## Grade")
    grade = data.get("grade", {})
    lines.append(f"- **Grade token ref:** {grade.get('grade_token_ref', 'default')}")
    if grade.get("description"):
        lines.append(f"- **Description:** {grade['description']}")

    # Beat grammar
    lines.append("\n## Beat grammar")
    bg = data.get("beat_grammar", {})
    lines.append(f"- **Roles:** {' → '.join(bg.get('roles', []))}")
    lines.append(f"- **Hook max:** {bg.get('hook_max_s', 3)}s")
    lines.append(f"- **Struggle range:** {bg.get('struggle_min', 2)}–{bg.get('struggle_max', 4)} beats")
    lines.append(f"- **Target duration:** {bg.get('target_duration_s', 90)}s")
    lines.append(f"- **Rules:** hook ≤3s (spoken contradiction or confession, character shown in that exact state); "
                 f"setup; struggle ×{bg.get('struggle_min', 2)}–{bg.get('struggle_max', 4)}; turn; "
                 f"lesson (concept named in plain words); cta (recurring sign-off line, payoff-first).")

    # Delivery mode
    lines.append("\n## Delivery mode")
    dm = data.get("delivery_mode", {})
    lines.append(f"- **Mode:** {dm.get('mode', 'narration_over_scenes')}")
    for rule in dm.get("rules", []):
        lines.append(f"- {rule}")
    lines.append("- No on-camera dialogue, no lip-sync.")

    # Audio register map
    lines.append("\n## Audio register map")
    for entry in data.get("audio_register_map", []):
        lines.append(f"\n### {entry['register']}")
        lines.append(f"- **Music bed:** {entry.get('music_bed_ref', '')}")
        if "duck_level_db" in entry:
            lines.append(f"- **Duck level:** {entry['duck_level_db']} dB")
        if "lufs_target" in entry:
            lines.append(f"- **LUFS target:** {entry['lufs_target']}")
    lines.append("\n- Fixed duck level and −14 LUFS target enforced on render.")

    # Graphics vocabulary
    lines.append("\n## Graphics vocabulary")
    gv = data.get("graphics_vocabulary", {})
    for cs in gv.get("card_styles", []):
        lines.append(f"\n### {cs['card_type']}")
        lines.append(f"- **Card style ref:** {cs.get('card_style_ref', '')}")
        if cs.get("when"):
            lines.append(f"- **When:** {cs['when']}")
    if gv.get("rules"):
        lines.append("\n**Rules:**")
        for rule in gv["rules"]:
            lines.append(f"- {rule}")

    # Critic rubric
    lines.append("\n## Critic rubric")
    cr = data.get("critic_rubric", {})
    for check in cr.get("checks", []):
        weight_str = f" (weight: {check['weight']})" if "weight" in check else ""
        lines.append(f"- **{check['criterion']}**{weight_str} — {check.get('description', '')}")
    if cr.get("notes"):
        lines.append(f"\n**Notes:** {cr['notes']}")
    lines.append("\nScores + one-line reasons on the Gate 2 card. Never blocks; "
                 "the operator's judgment is the gate. "
                 "Analyst may propose rubric edits only through the module review gate.")

    # Provenance
    lines.append(f"\n## Provenance\n- Version: {version}")
    lines.append(f"- Generated: {datetime.now(timezone.utc).isoformat()}")
    lines.append("- Schema: episode_format_v1")

    return "\n".join(lines)


# ── Module loader: parse markdown → dict ───────────────────────────────────

def parse_episode_format_markdown(content: str) -> dict:
    """Parse an episode-format module markdown file back into a dict.

    Uses the ## section headings to extract structured data. This is the
    reverse of episode_format_to_markdown — used when the module is loaded
    from disk for use by lints and the assembler.

    Extracts:
    - name (from title line)
    - version (from title line or provenance)
    - cast (from ## Cast ### entries)
    - world (from ## World ### entries)
    - beat_grammar (from ## Beat grammar section)
    - target_duration_s (from beat grammar)
    """
    result = {
        "type": "episode-format",
        "cast": [],
        "world": [],
        "beat_grammar": {},
    }

    lines = content.split("\n")

    # Parse title: # Episode Format — {name} — v{version}
    for line in lines:
        if line.startswith("# Episode Format — "):
            rest = line[len("# Episode Format — "):]
            # Split on " — v" to separate name and version
            parts = rest.rsplit(" — v", 1)
            result["name"] = parts[0].strip()
            if len(parts) > 1:
                result["version"] = parts[1].strip()
            break

    # Parse sections
    current_section = None
    current_entry = None
    current_entry_data = {}

    for line in lines:
        stripped = line.strip()

        # ## heading (section)
        if line.startswith("## ") and not line.startswith("### "):
            # Save previous entry
            if current_entry and current_entry_data:
                _save_entry(result, current_section, current_entry, current_entry_data)
            current_entry = None
            current_entry_data = {}
            current_section = stripped.lstrip("# ").strip()
            continue

        # ### heading (entry)
        if line.startswith("### "):
            # Save previous entry
            if current_entry and current_entry_data:
                _save_entry(result, current_section, current_entry, current_entry_data)
            current_entry = stripped.lstrip("# ").strip()
            current_entry_data = {}
            continue

        # Parse content lines
        if current_entry and stripped.startswith("- "):
            content_text = stripped[2:].strip()
            # Parse **Key:** value format
            m = re.match(r'\*\*(.+?):\*\*\s*(.*)', content_text)
            if m:
                key = m.group(1).lower().replace(" ", "_")
                val = m.group(2).strip()
                current_entry_data[key] = val
        elif not current_entry and current_section and stripped.startswith("- "):
            # Section-level content (no ### entry active) — e.g. Beat grammar body
            content_text = stripped[2:].strip()
            m = re.match(r'\*\*(.+?):\*\*\s*(.*)', content_text)
            if m:
                key = m.group(1).lower().replace(" ", "_")
                val = m.group(2).strip()
                _save_section_data(result, current_section, key, val)

    # Save last entry
    if current_entry and current_entry_data:
        _save_entry(result, current_section, current_entry, current_entry_data)

    # Extract target_duration_s from beat grammar section
    bg = result.get("beat_grammar", {})
    if "target_duration" in bg:
        result["target_duration_s"] = _safe_float(bg["target_duration"])
    if "hook_max" in bg:
        bg["hook_max_s"] = _safe_float(bg["hook_max"])

    return result


def _save_entry(result: dict, section: str, entry: str, data: dict):
    """Save a parsed ### entry into the result dict under its section."""
    if section == "Cast":
        result["cast"].append({
            "character_ref": entry,
            "description": data.get("description", ""),
            "wardrobe": data.get("wardrobe", ""),
            "demeanor": data.get("demeanor", ""),
        })
    elif section == "World":
        result["world"].append({
            "location_ref": entry,
            "description": data.get("description", ""),
        })
    elif section == "Audio register map":
        if "audio_register_map" not in result:
            result["audio_register_map"] = []
        result["audio_register_map"].append({
            "register": entry,
            "music_bed_ref": data.get("music_bed", ""),
            "duck_level_db": _safe_float(data.get("duck_level")),
            "lufs_target": _safe_float(data.get("lufs_target")),
        })
    elif section == "Beat grammar":
        # Beat grammar has no ### entries; data is in the section body
        result["beat_grammar"].update(data)
    elif section == "Graphics vocabulary":
        if "graphics_vocabulary" not in result:
            result["graphics_vocabulary"] = {"card_styles": [], "rules": []}
        result["graphics_vocabulary"]["card_styles"].append({
            "card_type": entry,
            "card_style_ref": data.get("card_style_ref", ""),
            "when": data.get("when", ""),
        })


def _save_section_data(result: dict, section: str, key: str, val: str):
    """Save section-level content (lines not inside a ### entry) into the result dict."""
    if section == "Beat grammar":
        result["beat_grammar"][key] = val
    elif section == "Grade":
        if "grade" not in result:
            result["grade"] = {}
        result["grade"][key] = val
    elif section == "Delivery mode":
        if "delivery_mode" not in result:
            result["delivery_mode"] = {}
        result["delivery_mode"][key] = val


def _safe_float(val) -> float | None:
    """Safely parse a float from a string, stripping units. Returns None on failure."""
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    # Strip common suffixes
    cleaned = re.sub(r'[^\d.\-]', '', str(val))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None