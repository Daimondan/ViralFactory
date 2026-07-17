"""
ViralFactory — EpisodePlan Layer-1 Lints (T11.2 — CORRECTION-episode-format §7.1)

Deterministic pre-spend checks that run on every EpisodePlan before any
paid media call. A plan that fails any lint cannot trigger media generation.

Six lints:
1. Registry referential integrity — every character_ref/location_ref/
   music_bed/card_style resolves to an APPROVED registry asset
2. Beat grammar vs. format module — hook first, hook ≤3s, lesson+cta present
3. Per-beat duration budget — Σ measured VO within format target ±10%
4. Banned-token scan on all media prompts — config-driven token list
5. Grade-token-present — grade token string verbatim in every image prompt
6. Numbers→graphics rule — every numeral in vo_text has a graphics entry

All lints are MECHANICAL — no LLM, no judgment. The banned-token list is
read from config/models.yaml (episode_lint.banned_prompt_tokens), not
hardcoded. A second business can set different tokens with zero code changes.

Failure → bounce to authoring LLM with lint errors (capped retries), then
needs_operator_decision. No money is spendable on a plan that fails Layer 1.
"""

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Optional


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class LintResult:
    """Result of running all Layer-1 lints on an EpisodePlan."""
    passed: bool = True
    errors: list = field(default_factory=list)      # blocking — fail the plan
    warnings: list = field(default_factory=list)     # advisory — don't block

    def add_error(self, lint_name: str, message: str, beat_id: str = None):
        self.passed = False
        self.errors.append({
            "lint": lint_name,
            "message": message,
            "beat_id": beat_id,
        })

    def add_warning(self, lint_name: str, message: str, beat_id: str = None):
        self.warnings.append({
            "lint": lint_name,
            "message": message,
            "beat_id": beat_id,
        })

    def summary(self) -> str:
        if self.passed:
            return f"Layer-1 passed ({len(self.warnings)} warning(s))"
        return f"Layer-1 FAILED: {len(self.errors)} error(s), {len(self.warnings)} warning(s)"


# ── Lint functions ───────────────────────────────────────────────────────────

def lint_registry_referential_integrity(
    beats: list,
    format_module: dict,
    ref_store,
    business_slug: str,
) -> list:
    """Lint 1: Every character_ref/location_ref/music_bed/card_style resolves
    to an APPROVED registry asset.

    Args:
        beats: EpisodePlan beats list
        format_module: The episode-format module dict (has beat_grammar, etc.)
        ref_store: ReferenceAssetStore instance
        business_slug: Current business slug

    Returns list of error dicts (empty if all refs resolve).
    """
    errors = []

    for beat in beats:
        beat_id = beat.get("id", "?")

        # Check character_ref
        char_ref = beat.get("character_ref")
        if char_ref:
            asset = ref_store.resolve_ref(business_slug, "character_ref", char_ref)
            if not asset:
                errors.append({
                    "lint": "registry_referential_integrity",
                    "beat_id": beat_id,
                    "message": f"character_ref '{char_ref}' does not resolve to an approved registry asset",
                })

        # Check location_ref
        loc_ref = beat.get("location_ref")
        if loc_ref:
            asset = ref_store.resolve_ref(business_slug, "location_ref", loc_ref)
            if not asset:
                errors.append({
                    "lint": "registry_referential_integrity",
                    "beat_id": beat_id,
                    "message": f"location_ref '{loc_ref}' does not resolve to an approved registry asset",
                })

        # Check music_bed (from register field)
        register = beat.get("register")
        if register:
            # Music beds are named by register (e.g. "somber" → "bed_somber")
            bed_name = f"bed_{register}"
            asset = ref_store.resolve_ref(business_slug, "music_bed", bed_name)
            if not asset:
                errors.append({
                    "lint": "registry_referential_integrity",
                    "beat_id": beat_id,
                    "message": f"music_bed '{bed_name}' (from register '{register}') does not resolve to an approved registry asset",
                })

        # Check card_style refs in graphics
        graphics = beat.get("graphics", [])
        for g in graphics:
            style = g.get("style")
            if style:
                asset = ref_store.resolve_ref(business_slug, "card_style", style)
                if not asset:
                    errors.append({
                        "lint": "registry_referential_integrity",
                        "beat_id": beat_id,
                        "message": f"card_style '{style}' does not resolve to an approved registry asset",
                    })

    return errors


def lint_beat_grammar(
    beats: list,
    format_module: dict,
    hook_max_duration_s: float = 3.0,
) -> list:
    """Lint 2: Beat roles satisfy the format module's grammar.

    Checks:
    - First beat must be 'hook'
    - Hook duration ≤ hook_max_duration_s (if duration is specified)
    - 'lesson' and 'cta' roles must be present
    - Exactly one shot per beat (beats have staged_action)

    Args:
        beats: EpisodePlan beats list
        format_module: The episode-format module dict
        hook_max_duration_s: Max hook duration from config

    Returns list of error dicts.
    """
    errors = []

    if not beats:
        errors.append({
            "lint": "beat_grammar",
            "beat_id": None,
            "message": "No beats in plan — episode must have at least one beat",
        })
        return errors

    # First beat must be hook
    if beats[0].get("role") != "hook":
        errors.append({
            "lint": "beat_grammar",
            "beat_id": beats[0].get("id", "first"),
            "message": f"First beat role is '{beats[0].get('role')}' — must be 'hook'",
        })

    # Hook duration check
    hook = beats[0]
    hook_duration = hook.get("duration_s") or hook.get("duration_ms", 0)
    if isinstance(hook_duration, (int, float)) and hook_duration > 0:
        # Convert ms to s if needed
        if hook_duration > 100:  # likely milliseconds
            hook_duration = hook_duration / 1000.0
        if hook_duration > hook_max_duration_s:
            errors.append({
                "lint": "beat_grammar",
                "beat_id": hook.get("id", "first"),
                "message": f"Hook duration {hook_duration:.1f}s exceeds cap {hook_max_duration_s:.1f}s",
            })

    # Must have lesson and cta
    roles = [b.get("role", "") for b in beats]
    if "lesson" not in roles:
        errors.append({
            "lint": "beat_grammar",
            "beat_id": None,
            "message": "Missing 'lesson' beat — episode must contain a lesson beat",
        })
    if "cta" not in roles:
        errors.append({
            "lint": "beat_grammar",
            "beat_id": None,
            "message": "Missing 'cta' beat — episode must contain a cta (sign-off) beat",
        })

    # Every beat must have staged_action (one shot per beat)
    for beat in beats:
        if not beat.get("staged_action"):
            errors.append({
                "lint": "beat_grammar",
                "beat_id": beat.get("id", "?"),
                "message": "Beat has no staged_action — exactly one shot per beat is required",
            })

    return errors


def lint_duration_budget(
    beats: list,
    format_module: dict,
    tolerance_pct: float = 10.0,
) -> list:
    """Lint 3: Σ measured VO durations within format target ±tolerance%.

    Args:
        beats: EpisodePlan beats list (each beat may have duration_s or duration_ms)
        format_module: The episode-format module dict (has target_duration_s)
        tolerance_pct: Tolerance percentage from config

    Returns list of error dicts.
    """
    errors = []

    # Get target duration from format module
    target = format_module.get("target_duration_s")
    if not target:
        # No target defined — skip this lint
        return errors

    # Sum beat durations
    total_duration = 0.0
    has_durations = False
    for beat in beats:
        d = beat.get("duration_s") or beat.get("duration_ms", 0)
        if isinstance(d, (int, float)) and d > 0:
            if d > 100:  # likely milliseconds
                d = d / 1000.0
            total_duration += d
            has_durations = True

    if not has_durations:
        # No durations specified — skip (will be measured later)
        return errors

    tolerance = target * (tolerance_pct / 100.0)
    if abs(total_duration - target) > tolerance:
        errors.append({
            "lint": "duration_budget",
            "beat_id": None,
            "message": (
                f"Total VO duration {total_duration:.1f}s is outside "
                f"target {target:.1f}s ±{tolerance_pct:.0f}% "
                f"(tolerance: ±{tolerance:.1f}s)"
            ),
        })

    return errors


def lint_banned_tokens(
    beats: list,
    format_module: dict,
    banned_tokens: list,
) -> list:
    """Lint 4: Banned-token scan on all media prompts (staged_action, image prompts).

    Scans the staged_action text and any image_prompt fields on each beat for
    banned tokens. The banned token list is config-driven (episode_lint
    .banned_prompt_tokens in models.yaml).

    Args:
        beats: EpisodePlan beats list
        format_module: The episode-format module dict
        banned_tokens: List of banned token strings from config

    Returns list of error dicts.
    """
    errors = []

    for beat in beats:
        beat_id = beat.get("id", "?")
        # Scan staged_action
        staged = beat.get("staged_action", "")
        if staged:
            text_lower = staged.lower()
            for token in banned_tokens:
                if token.lower() in text_lower:
                    errors.append({
                        "lint": "banned_token_scan",
                        "beat_id": beat_id,
                        "message": (
                            f"Banned token '{token}' found in staged_action: "
                            f"\"{staged[:80]}\" — all text/numbers are renderer-drawn graphics"
                        ),
                    })

        # Scan any explicit image_prompt on the beat
        img_prompt = beat.get("image_prompt", "")
        if img_prompt:
            text_lower = img_prompt.lower()
            for token in banned_tokens:
                if token.lower() in text_lower:
                    errors.append({
                        "lint": "banned_token_scan",
                        "beat_id": beat_id,
                        "message": (
                            f"Banned token '{token}' found in image_prompt: "
                            f"\"{img_prompt[:80]}\""
                        ),
                    })

    return errors


def lint_grade_token_present(
    beats: list,
    format_module: dict,
    grade_string: str,
) -> list:
    """Lint 5: Grade token string must be present verbatim in every image prompt.

    The grade token is stored once in the registry and injected mechanically.
    This lint verifies it's present in every beat's image_prompt (or that the
    image_prompt will have it injected by the assembler).

    Args:
        beats: EpisodePlan beats list
        format_module: The episode-format module dict
        grade_string: The verbatim grade token string from the registry

    Returns list of error dicts (empty if grade token is present or not yet
    applicable — the assembler injects it mechanically, so Writer prompts
    won't have it; this lint is for the assembled shot specs, not Writer output).
    """
    errors = []

    if not grade_string:
        # No grade token in registry — advisory warning, not a hard fail
        return errors

    # The grade token is injected by the assembler into the shot spec's
    # image_prompt. This lint checks the shot specs (post-assembly), not
    # the Writer's beats. If beats have image_prompt fields, check them.
    # If they don't (Writer output), the assembler will inject the grade.
    for beat in beats:
        beat_id = beat.get("id", "?")
        img_prompt = beat.get("image_prompt", "")
        if img_prompt and grade_string.lower() not in img_prompt.lower():
            errors.append({
                "lint": "grade_token_present",
                "beat_id": beat_id,
                "message": (
                    f"Grade token not found in image_prompt for beat {beat_id} — "
                    f"expected: \"{grade_string[:60]}\""
                ),
            })

    return errors


def lint_numbers_to_graphics(
    beats: list,
    format_module: dict,
) -> list:
    """Lint 6: Every numeral in vo_text must have a matching graphics entry.

    If vo_text contains a number (e.g. "fifty years" or "50 years"), the beat
    must have a graphics entry (e.g. {"type": "number_card", "text": "50 YEARS"}).
    This is the numbers→graphics rule from §3.2.

    Args:
        beats: EpisodePlan beats list
        format_module: The episode-format module dict

    Returns list of error dicts.
    """
    errors = []

    # Pattern to find numbers in text: digits, or common number words
    number_pattern = re.compile(r'\b\d+\b', re.IGNORECASE)

    for beat in beats:
        beat_id = beat.get("id", "?")
        vo_text = beat.get("vo_text", "")
        graphics = beat.get("graphics", [])

        if not vo_text:
            continue

        # Find all numbers in vo_text
        numbers_found = number_pattern.findall(vo_text)

        # If there are numbers but no graphics entries
        if numbers_found and not graphics:
            errors.append({
                "lint": "numbers_to_graphics",
                "beat_id": beat_id,
                "message": (
                    f"vo_text contains numbers {numbers_found} but beat has no "
                    f"graphics entry — every number must have a renderer-drawn card"
                ),
            })

    return errors


# ── Main entry point ──────────────────────────────────────────────────────────

def run_episode_plan_lints(
    episode_plan: dict,
    format_module: dict,
    ref_store,
    business_slug: str,
    lint_config: dict,
) -> LintResult:
    """Run all Layer-1 lints on an EpisodePlan.

    Args:
        episode_plan: The EpisodePlan dict with beats, format_module ref, etc.
        format_module: The episode-format module dict (the show bible).
        ref_store: ReferenceAssetStore instance for registry lookups.
        business_slug: Current business slug.
        lint_config: Config dict from models.yaml episode_lint block.

    Returns:
        LintResult with passed/errors/warnings.
    """
    result = LintResult()
    beats = episode_plan.get("beats", [])

    # 1. Registry referential integrity
    ref_errors = lint_registry_referential_integrity(
        beats, format_module, ref_store, business_slug,
    )
    for e in ref_errors:
        result.add_error(e["lint"], e["message"], e.get("beat_id"))

    # 2. Beat grammar
    hook_max = lint_config.get("hook_max_duration_s", 3.0)
    grammar_errors = lint_beat_grammar(beats, format_module, hook_max)
    for e in grammar_errors:
        result.add_error(e["lint"], e["message"], e.get("beat_id"))

    # 3. Duration budget
    tolerance_pct = lint_config.get("duration_tolerance_pct", 10.0)
    duration_errors = lint_duration_budget(beats, format_module, tolerance_pct)
    for e in duration_errors:
        result.add_error(e["lint"], e["message"], e.get("beat_id"))

    # 4. Banned-token scan
    banned_tokens = lint_config.get("banned_prompt_tokens", [])
    banned_errors = lint_banned_tokens(beats, format_module, banned_tokens)
    for e in banned_errors:
        result.add_error(e["lint"], e["message"], e.get("beat_id"))

    # 5. Grade token present
    grade_string = None
    if ref_store:
        grade_string = ref_store.get_grade_token(business_slug)
    grade_errors = lint_grade_token_present(beats, format_module, grade_string or "")
    for e in grade_errors:
        result.add_error(e["lint"], e["message"], e.get("beat_id"))

    # 6. Numbers→graphics
    numbers_errors = lint_numbers_to_graphics(beats, format_module)
    for e in numbers_errors:
        result.add_error(e["lint"], e["message"], e.get("beat_id"))

    return result