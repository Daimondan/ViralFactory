"""
Media-planning service v2 (VF-AU-203).

Plans every semantic beat by function. The Media Planner translates
approved semantic intent into provider-aware production prompts.

Per AMENDMENT-009 Condition 5: the Media Planner may translate intent,
not redefine it. It may not change the claim, subject, evidence
requirement, required beats, emotional job, audience action, or capture
policy.
"""

import os
from typing import Any

# Provider names that must never appear in Writer/beat output
_PROVIDER_NAMES = {"fal", "grok", "veo", "sora", "pexels", "pixabay", "openai", "stability", "midjourney"}


class ValidationError(Exception):
    """Raised when media plan validation fails."""
    pass


class MediaPlanResult:
    """Result of a media planning call — holds beats and recipes for validation."""

    def __init__(self, beats: list[dict], recipes: list[dict]):
        self.beats = beats
        self.recipes = recipes

    def validate(self) -> list[str]:
        """Validate the media plan against contract rules.

        Returns a list of error strings (empty = valid).
        """
        errors = []

        beat_ids = {b["beat_id"] for b in self.beats if "beat_id" in b}
        required_beat_ids = {
            b["beat_id"] for b in self.beats
            if b.get("beat_id") and b.get("required", False)
        }

        # Check for duplicate recipe IDs
        seen_recipe_ids = set()
        for recipe in self.recipes:
            rid = recipe.get("media_recipe_id", "")
            if rid in seen_recipe_ids:
                errors.append(f"Duplicate media_recipe_id: {rid}")
            else:
                seen_recipe_ids.add(rid)

        # Check that every recipe references a known beat
        recipe_beat_ids = set()
        for recipe in self.recipes:
            bid = recipe.get("beat_id", "")
            if bid and bid not in beat_ids:
                errors.append(f"Recipe '{recipe.get('media_recipe_id', '?')}' references unknown beat_id: {bid}")
            recipe_beat_ids.add(bid)

        # Check that every required beat has a recipe
        missing = required_beat_ids - recipe_beat_ids
        for bid in sorted(missing):
            errors.append(f"Required beat '{bid}' has no media recipe — every required beat must be covered")

        # Check capture policy consistency
        beat_policies = {b["beat_id"]: b.get("capture_policy", "") for b in self.beats}
        for recipe in self.recipes:
            bid = recipe.get("beat_id", "")
            beat_policy = beat_policies.get(bid, "")
            recipe_policy = recipe.get("source_policy", "")
            primary = recipe.get("primary", {}) or {}
            kind = primary.get("kind", "")

            # capture_required beat cannot resolve to generated/stock
            if beat_policy == "capture_required":
                if kind in ("generated_image", "generated_video", "stock"):
                    errors.append(
                        f"Beat '{bid}' has capture_required policy but recipe maps to {kind} — "
                        f"generated/stock cannot represent required real evidence"
                    )
                if recipe_policy == "generated_allowed":
                    errors.append(
                        f"Recipe for beat '{bid}' has source_policy=generated_allowed "
                        f"but beat has capture_required — policy mismatch"
                    )

            # Check for baked text/logos in generation prompts
            gen_prompt = primary.get("generation_prompt", "") or ""
            if gen_prompt:
                prompt_lower = gen_prompt.lower()
                banned_terms = ["text saying", "with text", "logo saying", "render text",
                                "accurate text", "readable text", "ui screenshot",
                                "chart with", "graph with numbers"]
                for term in banned_terms:
                    if term in prompt_lower:
                        errors.append(
                            f"Recipe for beat '{bid}' has generation prompt requesting baked text: "
                            f"'{term}' found — the renderer owns text, not the generator"
                        )
                        break

        return errors


class MediaPlanningService:
    """Plans media for every semantic beat in a Production Contract v2."""

    def __init__(self, models_config: dict = None, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config or {}
        self.db_path = db_path

    def build_available_providers(self) -> list[str]:
        """Build the available providers list from config — not hardcoded."""
        providers = []
        media_config = self.models_config.get("media", {})
        stock_config = self.models_config.get("stock", {})

        # Stock footage
        stock_providers = stock_config.get("providers", [])
        for sp in stock_providers:
            providers.append(f"stock:{sp} — search real-world footage")

        # Image generators
        image_gens = media_config.get("image_generators", [])
        for ig in image_gens:
            cost = ig.get("cost_per_image_usd", 0)
            providers.append(f"ai_image:{ig['name']} — {ig.get('provider', '')} ({cost:.3f}/img)")

        # Video generators
        video_gens = media_config.get("video_generators", [])
        for vg in video_gens:
            cost = vg.get("cost_per_second_usd", 0)
            providers.append(f"ai_video:{vg['name']} — {vg.get('provider', '')} ({cost:.3f}/s)")

        # Voice
        voice_config = self.models_config.get("voice_cloning", {})
        if voice_config.get("engine"):
            providers.append(f"voice:{voice_config['engine']} — narration/voiceover")

        return providers

    def extract_visual_intent(self, beat: dict) -> dict:
        """Extract semantic visual intent from a beat (not provider prompts)."""
        vi = beat.get("visual_intent", {}) or {}
        return {
            "subject": vi.get("subject", ""),
            "action": vi.get("action", ""),
            "meaning": vi.get("meaning", ""),
        }

    def extract_audio_intent(self, beat: dict) -> dict:
        """Extract audio intent from a beat."""
        ai = beat.get("audio_intent", {}) or {}
        return {
            "mode": ai.get("mode", ""),
            "music_action": ai.get("music_action", ""),
        }

    def check_no_provider_names(self, beats: list[dict]) -> list[str]:
        """Verify that beats don't contain provider-specific names.

        The Writer produces semantic intent, not provider prompts.
        Provider names (FAL, Grok, Veo, etc.) should not appear in
        beat visual_intent or any Writer output.
        """
        violations = []
        for beat in beats:
            vi = beat.get("visual_intent", {}) or {}
            for field in ("subject", "action", "meaning"):
                val = vi.get(field, "").lower()
                for provider in _PROVIDER_NAMES:
                    if provider in val:
                        violations.append(
                            f"Beat '{beat.get('beat_id', '?')}' visual_intent.{field} "
                            f"contains provider name '{provider}' — Writer should produce "
                            f"semantic intent, not provider-specific prompts"
                        )
                        break
        return violations

    def build_plan_prompt_inputs(
        self,
        beats: list[dict],
        measured_vo: dict | None = None,
        inventory: Any = None,
    ) -> dict:
        """Build the input variables for the media plan LLM prompt.

        The prompt receives semantic intent (not provider prompts),
        available providers from config, measured VO durations, and
        the scoped inventory.
        """
        # Extract semantic intents from beats
        beat_inputs = []
        for beat in beats:
            beat_inputs.append({
                "beat_id": beat.get("beat_id", ""),
                "role": beat.get("role", ""),
                "required": beat.get("required", True),
                "vo_text": beat.get("vo_text", ""),
                "staged_action": beat.get("staged_action", ""),
                "capture_policy": beat.get("capture_policy", "generated_allowed"),
                "visual_intent": self.extract_visual_intent(beat),
                "audio_intent": self.extract_audio_intent(beat),
                "intended_duration_sec": beat.get("intended_duration_sec"),
            })

        # Build VO timeline if available
        vo_timeline = "(no VO generated yet)"
        if measured_vo:
            vo_timeline = json.dumps(measured_vo, indent=2)

        # Build inventory summary
        inv_summary = "(no inventory)"
        if inventory:
            inv_summary = json.dumps(inventory.summary, indent=2)

        # Available providers from config
        available_providers = "\n".join(self.build_available_providers())

        return {
            "beats": beat_inputs,
            "vo_timeline": vo_timeline,
            "inventory": inv_summary,
            "available_providers": available_providers,
        }


# Import json at module level for build_plan_prompt_inputs
import json