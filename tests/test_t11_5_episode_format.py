"""
Tests for T11.5: Episode Format module + StackPenni show bible bootstrap.

Covers:
1. Episode-format schema validation (EPISODE_FORMAT_SCHEMA)
2. Module file loading (ModuleStore.load_validated with episode_format_v1)
3. Markdown conversion (episode_format_to_markdown) and round-trip parsing
4. Bootstrap flow: candidates proposed → operator approves through gate
5. No show-specific strings in harness code (grep guard)
6. Visual-style amendment is proposed (not applied) — file exists but
   visual-style.md is unchanged
"""

import json
import os
import re
import sys
import tempfile

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from episode_format import (
    EPISODE_FORMAT_SCHEMA,
    validate_episode_format,
    episode_format_to_markdown,
    parse_episode_format_markdown,
)
from episode_bootstrap import EpisodeBootstrapFlow, BootstrapStep
from reference_assets import ReferenceAssetStore


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def ref_store(tmp_path):
    """Create a ReferenceAssetStore with a temp DB."""
    db_path = str(tmp_path / "test_bootstrap.db")
    s = ReferenceAssetStore(db_path)
    yield s
    s.close()


@pytest.fixture
def format_module():
    """A valid episode-format module dict (generic, no show-specific names)."""
    return {
        "type": "episode-format",
        "name": "parable",
        "version": "1.0",
        "target_duration_s": 90,
        "cast": [
            {
                "character_ref": "protagonist",
                "description": "The main character, age 70",
                "wardrobe": "linen shirt and trousers",
                "demeanor": "measured, reflective",
            },
        ],
        "world": [
            {"location_ref": "loc_one", "description": "First location"},
            {"location_ref": "loc_two", "description": "Second location"},
            {"location_ref": "loc_three", "description": "Third location"},
            {"location_ref": "loc_four", "description": "Fourth location"},
        ],
        "grade": {
            "grade_token_ref": "default",
            "description": "warm cinematic light",
        },
        "beat_grammar": {
            "roles": ["hook", "setup", "struggle", "turn", "lesson", "cta"],
            "hook_max_s": 3,
            "struggle_min": 2,
            "struggle_max": 4,
            "target_duration_s": 90,
        },
        "delivery_mode": {
            "mode": "narration_over_scenes",
            "rules": ["No on-camera dialogue", "No lip-sync"],
        },
        "audio_register_map": [
            {"register": "somber", "music_bed_ref": "bed_somber", "duck_level_db": -12, "lufs_target": -14},
            {"register": "hopeful", "music_bed_ref": "bed_hopeful", "duck_level_db": -12, "lufs_target": -14},
        ],
        "graphics_vocabulary": {
            "card_styles": [
                {"card_type": "number_card", "card_style_ref": "number_card_v1", "when": "every number in VO"},
                {"card_type": "title_card", "card_style_ref": "title_card_v1", "when": "episode title"},
            ],
            "rules": ["every number spoken in VO gets a card"],
        },
        "critic_rubric": {
            "checks": [
                {"criterion": "hook_contradiction", "description": "Hook has contradiction or confession"},
                {"criterion": "staged_action_depicts_vo", "description": "staged_action matches vo_text"},
            ],
            "notes": "Scores on Gate 2 card",
        },
    }


@pytest.fixture
def format_module_minimal():
    """Minimal valid episode-format module (bare required fields)."""
    return {
        "type": "episode-format",
        "name": "test",
        "cast": [
            {"character_ref": "char1", "description": "d", "wardrobe": "w", "demeanor": "dm"},
        ],
        "world": [
            {"location_ref": "l1", "description": "d"},
            {"location_ref": "l2", "description": "d"},
            {"location_ref": "l3", "description": "d"},
            {"location_ref": "l4", "description": "d"},
        ],
        "grade": {"grade_token_ref": "default"},
        "beat_grammar": {
            "roles": ["hook", "setup", "struggle", "turn", "lesson", "cta"],
            "hook_max_s": 3,
            "struggle_min": 2,
            "struggle_max": 4,
            "target_duration_s": 90,
        },
        "delivery_mode": {"mode": "narration_over_scenes"},
        "audio_register_map": [
            {"register": "somber", "music_bed_ref": "bed_somber"},
        ],
        "graphics_vocabulary": {
            "card_styles": [{"card_type": "number_card", "card_style_ref": "nc1"}],
            "rules": ["every number gets a card"],
        },
        "critic_rubric": {
            "checks": [{"criterion": "c1", "description": "d1"}],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaValidation:

    def test_valid_module_passes(self, format_module):
        """A complete valid module passes validation."""
        errors = validate_episode_format(format_module)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_minimal_valid_module_passes(self, format_module_minimal):
        """A minimal valid module passes validation."""
        errors = validate_episode_format(format_module_minimal)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_missing_required_key_fails(self, format_module):
        """Missing a required top-level key fails validation."""
        del format_module["cast"]
        errors = validate_episode_format(format_module)
        assert any("cast" in e for e in errors)

    def test_wrong_type_fails(self, format_module):
        """Type must be 'episode-format'."""
        format_module["type"] = "wrong-type"
        errors = validate_episode_format(format_module)
        assert any("type" in e.lower() for e in errors)

    def test_empty_cast_fails(self, format_module):
        """Cast must be non-empty."""
        format_module["cast"] = []
        errors = validate_episode_format(format_module)
        assert any("cast" in e for e in errors)

    def test_cast_missing_subkey_fails(self, format_module):
        """Cast entry missing a sub-key fails."""
        del format_module["cast"][0]["wardrobe"]
        errors = validate_episode_format(format_module)
        assert any("wardrobe" in e for e in errors)

    def test_world_too_few_fails(self, format_module):
        """World must have 4-6 locations."""
        format_module["world"] = format_module["world"][:3]
        errors = validate_episode_format(format_module)
        assert any("world" in e and "4" in e for e in errors)

    def test_world_too_many_fails(self, format_module):
        """World must have max 6 locations."""
        format_module["world"] = format_module["world"] + [
            {"location_ref": "l5", "description": "d"},
            {"location_ref": "l6", "description": "d"},
            {"location_ref": "l7", "description": "d"},
        ]
        errors = validate_episode_format(format_module)
        assert any("world" in e and "6" in e for e in errors)

    def test_beat_grammar_hook_not_first_fails(self, format_module):
        """Beat grammar roles[0] must be 'hook'."""
        format_module["beat_grammar"]["roles"] = ["setup", "hook", "lesson", "cta"]
        errors = validate_episode_format(format_module)
        assert any("hook" in e and "roles[0]" in e for e in errors)

    def test_beat_grammar_missing_lesson_fails(self, format_module):
        """Beat grammar must contain 'lesson'."""
        format_module["beat_grammar"]["roles"] = ["hook", "setup", "struggle", "turn", "cta"]
        errors = validate_episode_format(format_module)
        assert any("lesson" in e for e in errors)

    def test_beat_grammar_missing_cta_fails(self, format_module):
        """Beat grammar must contain 'cta'."""
        format_module["beat_grammar"]["roles"] = ["hook", "setup", "struggle", "turn", "lesson"]
        errors = validate_episode_format(format_module)
        assert any("cta" in e for e in errors)

    def test_wrong_delivery_mode_fails(self, format_module):
        """Delivery mode must be 'narration_over_scenes'."""
        format_module["delivery_mode"]["mode"] = "on_camera_dialogue"
        errors = validate_episode_format(format_module)
        assert any("delivery_mode" in e for e in errors)

    def test_empty_audio_register_map_fails(self, format_module):
        """Audio register map must be non-empty."""
        format_module["audio_register_map"] = []
        errors = validate_episode_format(format_module)
        assert any("audio_register_map" in e for e in errors)

    def test_empty_critic_rubric_checks_fails(self, format_module):
        """Critic rubric checks must be non-empty."""
        format_module["critic_rubric"]["checks"] = []
        errors = validate_episode_format(format_module)
        assert any("checks" in e for e in errors)

    def test_graphics_vocabulary_missing_rules_fails(self, format_module):
        """Graphics vocabulary must have rules."""
        del format_module["graphics_vocabulary"]["rules"]
        errors = validate_episode_format(format_module)
        assert any("rules" in e for e in errors)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. MODULE FILE LOADING (ModuleStore integration)
# ═══════════════════════════════════════════════════════════════════════════════

class TestModuleFileLoading:

    def test_stackpenni_module_loads_and_validates(self):
        """The StackPenni episode-format module file loads and validates."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules")
        content = store.load("stackpenni", "episode-format-parable")
        assert content is not None, "Module file not found"
        assert "episode_format_v1" in content, "Schema marker missing"

    def test_stackpenni_module_load_validated_passes(self):
        """load_validated accepts the episode_format_v1 schema."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules")
        content = store.load_validated("stackpenni", "episode-format-parable")
        assert content is not None
        assert "Episode Format" in content

    def test_section_addressable_cast(self):
        """The module is section-addressable — Cast section exists."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules")
        section = store.get_section("stackpenni", "episode-format-parable", "Cast")
        assert section is not None
        assert "fitzroy" in section.lower() or "stackwell" in section.lower()

    def test_section_addressable_world(self):
        """The World section exists and has locations."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules")
        section = store.get_section("stackpenni", "episode-format-parable", "World")
        assert section is not None
        assert "kitchen_dawn" in section

    def test_section_addressable_beat_grammar(self):
        """The Beat grammar section exists."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules")
        section = store.get_section("stackpenni", "episode-format-parable", "Beat grammar")
        assert section is not None
        assert "hook" in section.lower()

    def test_section_addressable_critic_rubric(self):
        """The Critic rubric section exists."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules")
        section = store.get_section("stackpenni", "episode-format-parable", "Critic rubric")
        assert section is not None
        assert "hook_contradiction" in section


# ═══════════════════════════════════════════════════════════════════════════════
# 3. MARKDOWN CONVERSION + ROUND-TRIP
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarkdownConversion:

    def test_markdown_has_schema_marker(self, format_module):
        """Generated markdown has the episode_format_v1 schema marker."""
        md = episode_format_to_markdown(format_module, "1.0")
        assert "Schema: episode_format_v1" in md

    def test_markdown_has_all_sections(self, format_module):
        """Generated markdown has all required ## sections."""
        md = episode_format_to_markdown(format_module, "1.0")
        for section in ["## Cast", "## World", "## Grade", "## Beat grammar",
                        "## Delivery mode", "## Audio register map",
                        "## Graphics vocabulary", "## Critic rubric"]:
            assert section in md, f"Missing section: {section}"

    def test_markdown_has_provenance(self, format_module):
        """Generated markdown has provenance section."""
        md = episode_format_to_markdown(format_module, "1.0")
        assert "## Provenance" in md
        assert "Version: 1.0" in md

    def test_round_trip_parse(self, format_module):
        """Parse generated markdown back into a dict — key fields survive."""
        md = episode_format_to_markdown(format_module, "1.0")
        parsed = parse_episode_format_markdown(md)
        assert parsed["type"] == "episode-format"
        assert parsed["name"] == "parable"
        assert len(parsed["cast"]) == 1
        assert parsed["cast"][0]["character_ref"] == "protagonist"
        assert len(parsed["world"]) == 4
        assert parsed["world"][0]["location_ref"] == "loc_one"

    def test_round_trip_target_duration(self, format_module):
        """Target duration survives the round-trip."""
        md = episode_format_to_markdown(format_module, "1.0")
        parsed = parse_episode_format_markdown(md)
        assert parsed.get("target_duration_s") == 90.0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BOOTSTRAP FLOW — candidates proposed, operator approves through gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestBootstrapFlow:

    def test_flow_initialization(self, ref_store, format_module):
        """Bootstrap flow initializes with 4 steps."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        assert len(flow.steps) == 4
        assert flow.steps[0].name == "characters"
        assert flow.steps[1].name == "locations"
        assert flow.steps[2].name == "music_beds"
        assert flow.steps[3].name == "card_styles"
        assert not flow.is_complete()

    def test_step_1_propose_characters(self, ref_store, format_module):
        """Step 1: proposing characters creates 'proposed' assets."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        seeds = [
            {"name": "char_a", "payload": {"face_canon": "desc A", "wardrobe_canon": "w A"}},
            {"name": "char_b", "payload": {"face_canon": "desc B", "wardrobe_canon": "w B"}},
        ]
        candidates = flow.generate_character_candidates(seeds)
        assert len(candidates) == 2
        assert all(c["status"] == "proposed" for c in candidates)
        step = flow.get_step(1)
        assert step.status == "awaiting_approval"

    def test_step_1_approve_characters(self, ref_store, format_module):
        """Step 1: operator approves characters through the gate."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        seeds = [{"name": "char_a", "payload": {"face_canon": "desc A"}}]
        candidates = flow.generate_character_candidates(seeds)
        asset_id = candidates[0]["id"]

        # Approve through the gate
        approved = flow.approve_candidate(1, asset_id)
        assert approved["status"] == "approved"
        assert flow.is_step_complete(1)

    def test_step_1_partial_approval(self, ref_store, format_module):
        """Step 1: not complete until ALL candidates approved."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        seeds = [
            {"name": "char_a", "payload": {"face_canon": "A"}},
            {"name": "char_b", "payload": {"face_canon": "B"}},
        ]
        candidates = flow.generate_character_candidates(seeds)

        # Approve only one
        flow.approve_candidate(1, candidates[0]["id"])
        assert not flow.is_step_complete(1)

        # Approve the other
        flow.approve_candidate(1, candidates[1]["id"])
        assert flow.is_step_complete(1)

    def test_step_2_locations_conditioned_on_grade(self, ref_store, format_module):
        """Step 2: locations are conditioned on the grade token."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")

        # First propose and approve a grade token
        grade_asset = flow.propose_grade_token(
            "warm golden-hour Caribbean light, teal accents"
        )
        flow.approve_grade_token(grade_asset["id"])

        # Now generate locations
        seeds = [
            {"name": "loc_one", "payload": {"prompt_text": "a kitchen at dawn"}},
        ]
        candidates = flow.generate_location_candidates(seeds)
        assert len(candidates) == 1
        # The grade token should be in the prompt_text
        payload = json.loads(candidates[0]["payload_json"])
        assert "warm golden-hour" in payload["prompt_text"].lower()

    def test_step_2_locations_without_grade(self, ref_store, format_module):
        """Step 2: locations can be proposed without a grade token (no conditioning)."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        assert flow.needs_grade_token_first()

        seeds = [{"name": "loc_one", "payload": {"prompt_text": "a kitchen at dawn"}}]
        candidates = flow.generate_location_candidates(seeds)
        assert len(candidates) == 1
        payload = json.loads(candidates[0]["payload_json"])
        # No grade token — prompt_text should be as-is
        assert payload["prompt_text"] == "a kitchen at dawn"

    def test_step_2_locations_after_grade_approval(self, ref_store, format_module):
        """Step 2: needs_grade_token_first becomes False after approval."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        grade_asset = flow.propose_grade_token("warm light")
        flow.approve_grade_token(grade_asset["id"])
        assert not flow.needs_grade_token_first()

    def test_step_3_music_beds(self, ref_store, format_module):
        """Step 3: music beds are proposed — one per register."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        seeds = [
            {"name": "bed_somber", "payload": {"file": "bed_somber.mp3", "register": "somber", "duration": 80}},
            {"name": "bed_hopeful", "payload": {"file": "bed_hopeful.mp3", "register": "hopeful", "duration": 80}},
        ]
        candidates = flow.generate_music_bed_candidates(seeds)
        assert len(candidates) == 2
        assert all(c["status"] == "proposed" for c in candidates)

        # Approve both
        for c in candidates:
            flow.approve_candidate(3, c["id"])
        assert flow.is_step_complete(3)

    def test_step_4_card_styles(self, ref_store, format_module):
        """Step 4: card styles are proposed from visual-style module tokens."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        seeds = [
            {"name": "number_card_v1", "payload": {"font": "Georgia", "palette": {"fg": "#E54B2C"}}},
            {"name": "title_card_v1", "payload": {"font": "Georgia", "palette": {"fg": "#0A4D5C"}}},
        ]
        candidates = flow.generate_card_style_candidates(seeds)
        assert len(candidates) == 2
        assert all(c["status"] == "proposed" for c in candidates)

        # Approve both
        for c in candidates:
            flow.approve_candidate(4, c["id"])
        assert flow.is_step_complete(4)

    def test_reject_candidate(self, ref_store, format_module):
        """Rejecting a candidate retires it (stays for provenance)."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        seeds = [{"name": "char_a", "payload": {"face_canon": "A"}}]
        candidates = flow.generate_character_candidates(seeds)
        asset_id = candidates[0]["id"]

        rejected = flow.reject_candidate(1, asset_id)
        assert rejected["status"] == "retired"

    def test_full_bootstrap_sequence(self, ref_store, format_module):
        """Full bootstrap: grade → characters → locations → music → cards → complete."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")

        # 0. Grade token first
        grade = flow.propose_grade_token("warm cinematic light, teal and gold")
        flow.approve_grade_token(grade["id"])
        assert not flow.needs_grade_token_first()

        # 1. Characters
        char_candidates = flow.generate_character_candidates([
            {"name": "protagonist", "payload": {"face_canon": "desc", "wardrobe_canon": "w"}},
        ])
        for c in char_candidates:
            flow.approve_candidate(1, c["id"])
        assert flow.is_step_complete(1)

        # 2. Locations (conditioned on grade)
        loc_candidates = flow.generate_location_candidates([
            {"name": "loc_one", "payload": {"prompt_text": "a kitchen at dawn"}},
            {"name": "loc_two", "payload": {"prompt_text": "a porch at noon"}},
            {"name": "loc_three", "payload": {"prompt_text": "a market"}},
            {"name": "loc_four", "payload": {"prompt_text": "a beach"}},
        ])
        for c in loc_candidates:
            flow.approve_candidate(2, c["id"])
        assert flow.is_step_complete(2)

        # 3. Music beds
        music_candidates = flow.generate_music_bed_candidates([
            {"name": "bed_somber", "payload": {"file": "s.mp3", "register": "somber", "duration": 80}},
            {"name": "bed_hopeful", "payload": {"file": "h.mp3", "register": "hopeful", "duration": 80}},
        ])
        for c in music_candidates:
            flow.approve_candidate(3, c["id"])
        assert flow.is_step_complete(3)

        # 4. Card styles
        card_candidates = flow.generate_card_style_candidates([
            {"name": "number_card_v1", "payload": {"font": "Georgia"}},
            {"name": "title_card_v1", "payload": {"font": "Georgia"}},
        ])
        for c in card_candidates:
            flow.approve_candidate(4, c["id"])
        assert flow.is_step_complete(4)

        # Bootstrap complete
        assert flow.is_complete()
        state = flow.get_state()
        assert state["complete"]

    def test_no_approval_means_not_usable(self, ref_store, format_module):
        """Proposed (unapproved) assets are NOT usable — resolve_ref returns None."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        flow.generate_character_candidates([
            {"name": "protagonist", "payload": {"face_canon": "desc"}},
        ])
        # Proposed but not approved
        assert ref_store.resolve_ref("test_biz", "character_ref", "protagonist") is None

    def test_bootstrap_state_tracking(self, ref_store, format_module):
        """Bootstrap state tracks progress correctly."""
        flow = EpisodeBootstrapFlow(ref_store, format_module, "test_biz")
        state = flow.get_state()
        assert not state["complete"]
        assert len(state["steps"]) == 4
        assert all(s["status"] == "pending" for s in state["steps"])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. NO SHOW-SPECIFIC STRINGS IN HARNESS CODE
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoShowSpecificStrings:

    def test_no_stackpenni_strings_in_episode_format_py(self):
        """src/episode_format.py must contain no show-specific strings."""
        path = os.path.join(os.path.dirname(__file__), "..", "src", "episode_format.py")
        with open(path) as f:
            content = f.read().lower()
        # These are show-specific names that must NOT appear in harness code
        banned = ["stackpenni", "fitzroy", "stackwell", "kitchen_dawn", "bed_somber",
                  "pennifold", "bajan", "barbados", "guayabera"]
        for word in banned:
            assert word not in content, f"Show-specific string '{word}' found in episode_format.py"

    def test_no_stackpenni_strings_in_episode_bootstrap_py(self):
        """src/episode_bootstrap.py must contain no show-specific strings."""
        path = os.path.join(os.path.dirname(__file__), "..", "src", "episode_bootstrap.py")
        with open(path) as f:
            content = f.read().lower()
        banned = ["stackpenni", "fitzroy", "stackwell", "kitchen_dawn", "bed_somber",
                  "pennifold", "bajan", "barbados", "guayabera"]
        for word in banned:
            assert word not in content, f"Show-specific string '{word}' found in episode_bootstrap.py"

    def test_no_stackpenni_strings_in_module_store_py(self):
        """src/module_store.py must contain no show-specific strings
        (episode_format_v1 schema name is OK — it's a schema type, not a show name)."""
        path = os.path.join(os.path.dirname(__file__), "..", "src", "module_store.py")
        with open(path) as f:
            content = f.read().lower()
        banned = ["stackpenni", "fitzroy", "stackwell", "kitchen_dawn", "pennifold",
                  "bajan", "barbados", "guayabera"]
        for word in banned:
            assert word not in content, f"Show-specific string '{word}' found in module_store.py"

    def test_stackpenni_strings_only_in_module_file(self):
        """Show-specific strings should only appear in the module file, not harness."""
        module_path = os.path.join(os.path.dirname(__file__), "..",
                                    "modules", "stackpenni", "episode-format-parable.md")
        with open(module_path) as f:
            module_content = f.read()
        # These SHOULD appear in the module file
        assert "fitzroy" in module_content.lower()
        assert "stackwell" in module_content.lower()
        assert "kitchen_dawn" in module_content.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. VISUAL-STYLE AMENDMENT (proposed, NOT applied)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVisualStyleAmendment:

    def test_amendment_file_exists(self):
        """The proposed amendment file exists."""
        path = os.path.join(os.path.dirname(__file__), "..",
                            "modules", "stackpenni", "visual-style-amendment-proposed.md")
        assert os.path.isfile(path)

    def test_amendment_is_proposed_not_applied(self):
        """The amendment is a proposal — the visual-style.md file is unchanged
        (does NOT contain the fictional persona rule)."""
        vs_path = os.path.join(os.path.dirname(__file__), "..",
                               "modules", "stackpenni", "visual-style.md")
        with open(vs_path) as f:
            vs_content = f.read()
        # The amendment text must NOT be in the current visual-style.md
        assert "Fictional recurring persona" not in vs_content
        assert "fictional, AI-generated persona" not in vs_content

    def test_amendment_contains_correct_text(self):
        """The amendment contains the §1.4 text from the correction."""
        path = os.path.join(os.path.dirname(__file__), "..",
                            "modules", "stackpenni", "visual-style-amendment-proposed.md")
        with open(path) as f:
            content = f.read()
        assert "Fictional recurring persona" in content
        assert "storytelling device" in content
        assert "platform AI-disclosure rules" in content
        assert "Never present a generated visual as a real person" in content
        assert "PROPOSED" in content or "proposed" in content.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. CONTEXT ASSEMBLY INTEGRATION (views.yaml wiring)
# ═══════════════════════════════════════════════════════════════════════════════

class TestContextAssemblyWiring:

    def test_views_yaml_has_episode_format_for_writer(self):
        """views.yaml maps the Writer v4 prompt to the episode_format module."""
        import yaml
        views_path = os.path.join(os.path.dirname(__file__), "..",
                                  "prompts", "views.yaml")
        with open(views_path) as f:
            views = yaml.safe_load(f) or {}

        # Writer v4 should have episode_format view
        writer_views = views.get("draft/generate_v4.md", {})
        assert "episode_format" in writer_views
        assert writer_views["episode_format"]["module"] == "episode-format-parable"

    def test_views_yaml_has_episode_format_for_media_plan(self):
        """views.yaml maps media_plan_v2 to the episode_format module."""
        import yaml
        views_path = os.path.join(os.path.dirname(__file__), "..",
                                  "prompts", "views.yaml")
        with open(views_path) as f:
            views = yaml.safe_load(f) or {}

        mp_views = views.get("assembly/media_plan_v2.md", {})
        assert "episode_format" in mp_views

    def test_views_yaml_has_episode_format_for_edit_plan(self):
        """views.yaml maps edit_plan_v2 to the episode_format module."""
        import yaml
        views_path = os.path.join(os.path.dirname(__file__), "..",
                                  "prompts", "views.yaml")
        with open(views_path) as f:
            views = yaml.safe_load(f) or {}

        ep_views = views.get("assembly/edit_plan_v2.md", {})
        assert "episode_format" in ep_views

    def test_context_assembly_resolves_episode_format(self):
        """Context assembly resolves the episode_format view from the module."""
        from context_assembly import assemble_module_context
        variables, prov = assemble_module_context(
            "draft/generate_v4.md",
            "stackpenni",
            db_path="data/viralfactory.db",
            modules_dir=os.path.join(os.path.dirname(__file__), "..", "modules"),
            prompts_dir=os.path.join(os.path.dirname(__file__), "..", "prompts"),
        )
        # The episode_format variable should be present
        assert "episode_format" in variables
        assert len(variables["episode_format"]) > 0
        # It should contain the format name
        assert "parable" in variables["episode_format"].lower()
        # Provenance should mention episode-format-parable
        assert "episode-format-parable" in prov