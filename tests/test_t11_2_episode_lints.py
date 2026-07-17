"""
Tests for T11.2: EpisodePlan Layer-1 lints.

AC: A plan violating any lint cannot trigger a paid media call.
    The banned-token list is config, not code.

Six lints:
1. Registry referential integrity (approved assets only)
2. Beat grammar vs. format module (hook first, ≤3s, lesson+cta present)
3. Per-beat duration budget (Σ VO within target ±10%)
4. Banned-token scan on all media prompts
5. Grade-token-present check
6. Numbers→graphics rule
"""

import json
import os
import pytest
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def ref_store():
    """Create a ReferenceAssetStore with an in-memory DB and some approved assets."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    from reference_assets import ReferenceAssetStore
    store = ReferenceAssetStore(db_path)

    # Approve a character ref
    store.propose("test", "character_ref", "fitzroy", {
        "name": "Fitzroy", "face_canon": "elderly Caribbean man",
        "wardrobe_canon": "linen shirt", "files": ["ref1.jpg", "ref2.jpg"],
    })
    store.approve(1)

    # Approve a location ref
    store.propose("test", "location_ref", "kitchen_dawn", {
        "prompt_text": "kitchen at dawn", "files": ["kitchen.jpg"],
    })
    store.approve(2)

    # Approve a music bed
    store.propose("test", "music_bed", "bed_somber", {
        "file": "bed_somber.mp3", "register": "somber", "duration": 80,
    })
    store.approve(3)

    # Approve a grade token
    store.propose("test", "grade_token", "default", {
        "grade_string": "warm golden-hour Caribbean light, teal and coral accents",
    })
    store.approve(4)

    # Approve a card style
    store.propose("test", "card_style", "title_card_v1", {
        "font": "Georgia", "palette": {"fg": "#E54B2C"},
    })
    store.approve(5)

    yield store

    store.close()
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def lint_config():
    """Standard lint config from models.yaml episode_lint block."""
    return {
        "banned_prompt_tokens": [
            "text", "words", "sign", "screen", "phone",
            "logo", "document", "chart", "letters", "numbers on",
        ],
        "duration_tolerance_pct": 10,
        "hook_max_duration_s": 3.0,
    }


@pytest.fixture
def format_module():
    """Minimal episode-format module (show bible)."""
    return {
        "type": "episode-format",
        "name": "parable",
        "target_duration_s": 90,
        "beat_grammar": {
            "roles": ["hook", "setup", "struggle", "turn", "lesson", "cta"],
            "hook_max_s": 3,
        },
    }


def _make_beat(beat_id="b01", role="hook", vo_text="test",
               staged_action="the man sits at the table",
               character_ref="fitzroy", location_ref="kitchen_dawn",
               register="somber", duration_s=3.0, graphics=None, **kw):
    beat = {
        "id": beat_id, "role": role, "vo_text": vo_text,
        "staged_action": staged_action,
        "character_ref": character_ref, "location_ref": location_ref,
        "register": register, "duration_s": duration_s,
    }
    if graphics is not None:
        beat["graphics"] = graphics
    beat.update(kw)
    return beat


def _make_plan(beats):
    return {"format_module": "episode-format-parable@v1", "beats": beats}


# ═══════════════════════════════════════════════════════════════════════════════
# 1. REGISTRY REFERENTIAL INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegistryReferentialIntegrity:

    def test_all_refs_resolve_passes(self, ref_store, format_module, lint_config):
        """All refs resolve to approved assets → no errors."""
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="I worked fifty years"),
            _make_beat("b02", role="setup", vo_text="Then everything changed"),
            _make_beat("b03", role="struggle", vo_text="I lost it all"),
            _make_beat("b04", role="turn", vo_text="Then I learned"),
            _make_beat("b05", role="lesson", vo_text="Save early"),
            _make_beat("b06", role="cta", vo_text="Start now",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        ref_errors = [e for e in result.errors if e["lint"] == "registry_referential_integrity"]
        assert len(ref_errors) == 0

    def test_unapproved_character_ref_fails(self, ref_store, format_module, lint_config):
        """An unapproved character_ref → lint fails."""
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test", character_ref="ghost"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        ref_errors = [e for e in result.errors if e["lint"] == "registry_referential_integrity"]
        assert len(ref_errors) > 0
        assert any("ghost" in e["message"] for e in ref_errors)

    def test_unapproved_location_ref_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test", location_ref="mars"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        ref_errors = [e for e in result.errors if e["lint"] == "registry_referential_integrity"]
        assert len(ref_errors) > 0
        assert any("mars" in e["message"] for e in ref_errors)

    def test_unapproved_card_style_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       graphics=[{"type": "number_card", "text": "50", "style": "nonexistent_style"}]),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        ref_errors = [e for e in result.errors if e["lint"] == "registry_referential_integrity"]
        assert len(ref_errors) > 0
        assert any("nonexistent_style" in e["message"] for e in ref_errors)

    def test_approved_card_style_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       graphics=[{"type": "number_card", "text": "50", "style": "title_card_v1"}]),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        ref_errors = [e for e in result.errors if e["lint"] == "registry_referential_integrity"]
        assert len(ref_errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. BEAT GRAMMAR
# ═══════════════════════════════════════════════════════════════════════════════

class TestBeatGrammar:

    def test_valid_grammar_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="I worked fifty years"),
            _make_beat("b02", role="setup", vo_text="Then it changed"),
            _make_beat("b03", role="struggle", vo_text="Lost it"),
            _make_beat("b04", role="turn", vo_text="Learned"),
            _make_beat("b05", role="lesson", vo_text="Save early"),
            _make_beat("b06", role="cta", vo_text="Go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grammar_errors = [e for e in result.errors if e["lint"] == "beat_grammar"]
        assert len(grammar_errors) == 0

    def test_first_beat_not_hook_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="setup", vo_text="Not a hook"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grammar_errors = [e for e in result.errors if e["lint"] == "beat_grammar"]
        assert any("hook" in e["message"].lower() for e in grammar_errors)

    def test_missing_lesson_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test"),
            _make_beat("b02", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grammar_errors = [e for e in result.errors if e["lint"] == "beat_grammar"]
        assert any("lesson" in e["message"] for e in grammar_errors)

    def test_missing_cta_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test"),
            _make_beat("b02", role="lesson", vo_text="learn"),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grammar_errors = [e for e in result.errors if e["lint"] == "beat_grammar"]
        assert any("cta" in e["message"] for e in grammar_errors)

    def test_hook_too_long_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test", duration_s=5.0),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grammar_errors = [e for e in result.errors if e["lint"] == "beat_grammar"]
        assert any("hook" in e["message"].lower() and "exceed" in e["message"].lower() for e in grammar_errors)

    def test_missing_staged_action_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test", staged_action=""),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grammar_errors = [e for e in result.errors if e["lint"] == "beat_grammar"]
        assert any("staged_action" in e["message"] for e in grammar_errors)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DURATION BUDGET
# ═══════════════════════════════════════════════════════════════════════════════

class TestDurationBudget:

    def test_within_tolerance_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        # Target 90s, tolerance 10% = ±9s. Total = 88s → within.
        beats = [
            _make_beat("b01", role="hook", vo_text="test", duration_s=3),
            _make_beat("b02", role="setup", vo_text="setup", duration_s=15),
            _make_beat("b03", role="struggle", vo_text="struggle", duration_s=20),
            _make_beat("b04", role="turn", vo_text="turn", duration_s=20),
            _make_beat("b05", role="lesson", vo_text="learn", duration_s=15),
            _make_beat("b06", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None, duration_s=15),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        duration_errors = [e for e in result.errors if e["lint"] == "duration_budget"]
        assert len(duration_errors) == 0

    def test_outside_tolerance_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        # Target 90s, tolerance 10% = ±9s. Total = 50s → outside (40s under).
        beats = [
            _make_beat("b01", role="hook", vo_text="test", duration_s=3),
            _make_beat("b02", role="setup", vo_text="setup", duration_s=10),
            _make_beat("b03", role="struggle", vo_text="struggle", duration_s=10),
            _make_beat("b04", role="turn", vo_text="turn", duration_s=10),
            _make_beat("b05", role="lesson", vo_text="learn", duration_s=10),
            _make_beat("b06", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None, duration_s=7),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        duration_errors = [e for e in result.errors if e["lint"] == "duration_budget"]
        assert len(duration_errors) > 0
        assert any("50" in e["message"] or "outside" in e["message"] for e in duration_errors)

    def test_no_target_skips_lint(self, ref_store, lint_config):
        from episode_lints import run_episode_plan_lints
        # No target_duration_s in format module → skip
        fmt = {"type": "episode-format", "name": "test"}
        beats = [
            _make_beat("b01", role="hook", vo_text="test", duration_s=3),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, fmt, ref_store, "test", lint_config)
        duration_errors = [e for e in result.errors if e["lint"] == "duration_budget"]
        assert len(duration_errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. BANNED-TOKEN SCAN
# ═══════════════════════════════════════════════════════════════════════════════

class TestBannedTokenScan:

    def test_clean_staged_action_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="the man sits alone at the table"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        banned_errors = [e for e in result.errors if e["lint"] == "banned_token_scan"]
        assert len(banned_errors) == 0

    def test_banned_token_phone_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="the man looks at his phone screen"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        banned_errors = [e for e in result.errors if e["lint"] == "banned_token_scan"]
        assert len(banned_errors) > 0
        assert any("phone" in e["message"] for e in banned_errors)

    def test_banned_token_logo_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="a logo on the wall"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        banned_errors = [e for e in result.errors if e["lint"] == "banned_token_scan"]
        assert any("logo" in e["message"] for e in banned_errors)

    def test_banned_token_in_image_prompt_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="the man sits",
                       image_prompt="a man holding a phone"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        banned_errors = [e for e in result.errors if e["lint"] == "banned_token_scan"]
        assert any("phone" in e["message"] and "image_prompt" in e["message"] for e in banned_errors)

    def test_banned_token_list_from_config(self, ref_store, format_module):
        """The banned-token list comes from config, not hardcoded."""
        from episode_lints import lint_banned_tokens
        # Custom config with a non-standard banned token
        custom_config = {"banned_prompt_tokens": ["banana", "umbrella"]}
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="the man holds a banana"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        errors = lint_banned_tokens(beats, format_module, custom_config["banned_prompt_tokens"])
        assert any("banana" in e["message"] for e in errors)
        # Standard tokens like "phone" should NOT be banned in this custom config
        errors_standard = lint_banned_tokens(
            [_make_beat("b01", role="hook", vo_text="test",
                        staged_action="a phone on the desk")],
            format_module,
            custom_config["banned_prompt_tokens"],
        )
        assert len(errors_standard) == 0  # "phone" not in custom list


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GRADE-TOKEN-PRESENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestGradeTokenPresent:

    def test_grade_present_in_image_prompt_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        grade = "warm golden-hour Caribbean light, teal and coral accents"
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="the man sits",
                       image_prompt=f"the man sits, {grade}"),
            _make_beat("b02", role="lesson", vo_text="learn",
                       image_prompt=f"the man learns, {grade}"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grade_errors = [e for e in result.errors if e["lint"] == "grade_token_present"]
        assert len(grade_errors) == 0

    def test_grade_missing_from_image_prompt_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test",
                       staged_action="the man sits",
                       image_prompt="the man sits in a dark room"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grade_errors = [e for e in result.errors if e["lint"] == "grade_token_present"]
        assert len(grade_errors) > 0

    def test_no_image_prompts_skips_lint(self, ref_store, format_module, lint_config):
        """Beats without image_prompt fields (Writer output) skip this lint —
        the assembler injects the grade token mechanically."""
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="test"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        grade_errors = [e for e in result.errors if e["lint"] == "grade_token_present"]
        assert len(grade_errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 6. NUMBERS→GRAPHICS
# ═══════════════════════════════════════════════════════════════════════════════

class TestNumbersToGraphics:

    def test_number_with_graphics_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="I worked 50 years",
                       graphics=[{"type": "number_card", "text": "50 YEARS", "style": "title_card_v1"}]),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        numbers_errors = [e for e in result.errors if e["lint"] == "numbers_to_graphics"]
        assert len(numbers_errors) == 0

    def test_number_without_graphics_fails(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="I worked 50 years"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        numbers_errors = [e for e in result.errors if e["lint"] == "numbers_to_graphics"]
        assert len(numbers_errors) > 0
        assert any("50" in e["message"] for e in numbers_errors)

    def test_no_number_no_graphics_passes(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="I worked for years"),
            _make_beat("b02", role="lesson", vo_text="learn"),
            _make_beat("b03", role="cta", vo_text="go",
                       character_ref=None, location_ref=None, register=None),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        numbers_errors = [e for e in result.errors if e["lint"] == "numbers_to_graphics"]
        assert len(numbers_errors) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION: full plan passes/fails
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullPlanLint:

    def test_valid_plan_passes_all_lints(self, ref_store, format_module, lint_config):
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="hook", vo_text="I worked 50 years",
                       duration_s=3,
                       graphics=[{"type": "number_card", "text": "50 YEARS", "style": "title_card_v1"}]),
            _make_beat("b02", role="setup", vo_text="Then it changed", duration_s=15),
            _make_beat("b03", role="struggle", vo_text="Lost it", duration_s=20),
            _make_beat("b04", role="turn", vo_text="Learned", duration_s=20),
            _make_beat("b05", role="lesson", vo_text="Save early", duration_s=15),
            _make_beat("b06", role="cta", vo_text="Start now",
                       character_ref=None, location_ref=None, register=None, duration_s=15),
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        assert result.passed, f"Expected pass, got errors: {json.dumps(result.errors, indent=2)}"

    def test_failing_plan_blocked(self, ref_store, format_module, lint_config):
        """A plan violating multiple lints is blocked — no paid media call."""
        from episode_lints import run_episode_plan_lints
        beats = [
            _make_beat("b01", role="setup", vo_text="I worked 50 years",  # not hook, has number, no graphics
                       staged_action="the man looks at his phone",  # banned token
                       character_ref="ghost",  # unapproved ref
                       duration_s=5),  # hook too long (if it were hook)
            _make_beat("b02", role="lesson", vo_text="learn"),
            # No cta
        ]
        plan = _make_plan(beats)
        result = run_episode_plan_lints(plan, format_module, ref_store, "test", lint_config)
        assert not result.passed
        assert len(result.errors) >= 4  # at least 4 lint categories failed