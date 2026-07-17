"""
Tests for VF-AU-203: Media-planning service v2.

Plans every semantic beat by function. The Media Planner translates
approved semantic intent into provider-aware production prompts.
Per AMENDMENT-009 Condition 5: Media Planner may translate intent,
not redefine it.
"""

import json
import os
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.media_planning import (
    MediaPlanningService,
    MediaPlanResult,
    ValidationError,
)


def _make_beat(beat_id="b01", capture_policy="generated_allowed", **kw):
    base = {
        "beat_id": beat_id,
        "platform_variant_id": "pv001",
        "role": "hook",
        "required": True,
        "vo_text": "The eighth wonder",
        "staged_action": "Close-up ledger",
        "capture_policy": capture_policy,
        "evidence_refs": ["source:14"],
        "visual_intent": {"subject": "ledger", "action": "close-up", "meaning": "proof"},
        "audio_intent": {"mode": "vo_only"},
    }
    base.update(kw)
    return base


def _make_inventory():
    """Create a minimal mock inventory."""
    from services.media_inventory import Inventory, InventoryItem
    return Inventory(
        asset_id=1,
        business_slug="stackpenni",
        items=[
            InventoryItem(
                ingredient_id="asset_media:1",
                kind="image",
                source_type="asset_media",
                path="/local/img.png",
                is_render_ready=True,
                status="ready",
            ),
        ],
    )


class TestMediaPlanValidation:
    """The service must validate the LLM output against contract rules."""

    def test_every_required_beat_covered(self):
        """A plan missing a required beat must fail validation."""
        beats = [_make_beat("b01", required=True), _make_beat("b02", required=True)]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
            # b02 missing — no recipe
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert len(errors) > 0
        assert any("b02" in e for e in errors)

    def test_all_beats_covered_passes(self):
        beats = [_make_beat("b01", required=True), _make_beat("b02", required=False)]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
            {"media_recipe_id": "r02", "beat_id": "b02", "media_function": "context",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert errors == []

    def test_capture_required_cannot_use_generated(self):
        """capture_required beat mapped to generated media must fail."""
        beats = [_make_beat("b01", capture_policy="capture_required")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "capture_required",
             "primary": {"kind": "generated_image"}},  # VIOLATION
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert any("capture" in e.lower() or "generated" in e.lower() for e in errors)

    def test_capture_required_with_upload_ok(self):
        """capture_required beat mapped to upload (real evidence) is valid."""
        beats = [_make_beat("b01", capture_policy="capture_required")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "capture_required",
             "primary": {"kind": "upload", "ingredient_id": "capture_upload:22"}},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert errors == []

    def test_recipe_references_unknown_beat(self):
        """A recipe referencing an unknown beat_id must fail."""
        beats = [_make_beat("b01")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b99", "media_function": "proof",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert any("b99" in e for e in errors)

    def test_no_baked_text_in_generation_prompt(self):
        """Generation prompts must not request accurate text, logos, or interfaces."""
        beats = [_make_beat("b01")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed",
             "primary": {
                 "kind": "generated_image",
                 "generation_prompt": "Image with text saying 'Compound interest is 8%'",  # VIOLATION
             }},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert any("text" in e.lower() or "logo" in e.lower() for e in errors)

    def test_cost_estimate_present(self):
        """Each recipe should have a cost estimate."""
        beats = [_make_beat("b01")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed",
             "primary": {"kind": "generated_image"},
             "cost_estimate_usd": 0.03},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        # Cost present — no error for missing cost
        assert not any("cost" in e.lower() for e in errors)

    def test_media_planner_does_not_redefine_intent(self):
        """The Media Planner must not change the claim, subject, or evidence requirement.

        This is a structural check — the service verifies that the recipe's
        source_policy matches or is compatible with the beat's capture_policy.
        A capture_required beat cannot have a recipe with source_policy=generated_allowed.
        """
        beats = [_make_beat("b01", capture_policy="capture_required")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed",  # MISMATCH — beat says capture_required
             "primary": {"kind": "generated_image"}},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert any("policy" in e.lower() or "capture" in e.lower() for e in errors)

    def test_optional_beat_without_recipe_ok(self):
        """Optional beats don't require a recipe."""
        beats = [_make_beat("b01", required=True), _make_beat("b02", required=False)]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert errors == []

    def test_duplicate_recipe_id_detected(self):
        beats = [_make_beat("b01"), _make_beat("b02")]
        recipes = [
            {"media_recipe_id": "r01", "beat_id": "b01", "media_function": "proof",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
            {"media_recipe_id": "r01", "beat_id": "b02", "media_function": "context",
             "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}},
        ]
        result = MediaPlanResult(beats=beats, recipes=recipes)
        errors = result.validate()
        assert any("duplicate" in e.lower() for e in errors)


class TestMediaPlanningService:
    """The service wraps the LLM call and validates output."""

    def test_service_builds_available_providers_from_config(self):
        """The service should build the available providers list from config, not hardcode."""
        service = MediaPlanningService(
            models_config={
                "media": {
                    "image_generators": [
                        {"name": "fal-flux", "provider": "fal", "cost_per_image_usd": 0.03},
                    ],
                },
                "stock": {"providers": ["pexels"]},
            },
        )
        providers = service.build_available_providers()
        assert len(providers) > 0
        # Should mention the image generator
        assert any("fal" in p.lower() or "image" in p.lower() for p in providers)

    def test_service_extracts_semantic_visual_intent(self):
        """The service should pass semantic visual intent (not provider prompts) to the LLM."""
        beat = _make_beat("b01", visual_intent={"subject": "ledger", "action": "close-up", "meaning": "proof"})
        service = MediaPlanningService(models_config={})
        extracted = service.extract_visual_intent(beat)
        assert extracted["subject"] == "ledger"
        assert extracted["meaning"] == "proof"

    def test_service_extracts_audio_intent(self):
        """The service should pass audio intent to the LLM."""
        beat = _make_beat("b01", audio_intent={"mode": "vo_only", "music_action": "continue"})
        service = MediaPlanningService(models_config={})
        extracted = service.extract_audio_intent(beat)
        assert extracted["mode"] == "vo_only"

    def test_service_validates_no_provider_names_in_beats(self):
        """The service must verify beats don't contain provider-specific names."""
        beat = _make_beat("b01", visual_intent={"subject": "FAL flux image of ledger", "action": "x", "meaning": "x"})
        service = MediaPlanningService(models_config={})
        violations = service.check_no_provider_names([beat])
        assert len(violations) > 0
        assert any("fal" in v.lower() for v in violations)