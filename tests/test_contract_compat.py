"""
Tests for the compatibility reader (VF-AU-105).

Reads existing platform_content drafts (from generate_v3 / DRAFT_SCHEMA)
without pretending they are full Production Contract v2 structures.
Missing information stays null/unknown — never invented.
"""

import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from contract_compat import convert_legacy_draft, CompatResult


class TestConvertLegacyDraft:
    """Convert a legacy draft (v3 DRAFT_SCHEMA) to a partial Production Contract v2."""

    def test_text_format_draft_converts(self):
        """A text-format draft (thread) with string posts should convert."""
        legacy = {
            "platform_content": [
                {
                    "platform": "x",
                    "variant_type": "thread",
                    "content": "Compound interest thread",
                    "posts": ["Tweet 1", "Tweet 2", "Tweet 3"],
                    "image_prompts": ["none"],
                }
            ],
            "visual_direction": {
                "image_prompts": ["none"],
                "reference_notes": [],
                "shot_format_choices": ["text-only"],
            },
            "self_audit_flags": [],
        }
        result = convert_legacy_draft(legacy, draft_id=5, business_slug="stackpenni")
        assert result.is_valid
        contract = result.contract
        assert contract["contract_id"] == "c5_x"
        assert contract["content_contract"]["format_name"] == "thread"
        assert contract["content_contract"]["platform"] == "x"
        assert contract["content_contract"]["capture_policy"] == "legacy_unclassified"
        assert contract["content_contract"]["evidence_label"] == "HYPOTHESIS"
        assert len(contract["beats"]) == 0  # text format — no beats
        assert "writer_contract_hash" in contract

    def test_reel_format_draft_converts_with_synthesized_beats(self):
        """A reel draft with frame objects should get synthesized beats."""
        legacy = {
            "platform_content": [
                {
                    "platform": "instagram",
                    "variant_type": "reel",
                    "content": "Compound interest reel",
                    "posts": [
                        {"label": "HOOK", "vo_text": "The eighth wonder",
                         "visual": {"image_prompt": "Close-up ledger",
                                    "shot_type": "tight close-up"}},
                        {"label": "PAYOFF", "vo_text": "Start now",
                         "visual": {"image_prompt": "Hand writing check",
                                    "shot_type": "medium"}},
                    ],
                    "image_prompts": ["Close-up ledger", "Hand writing check"],
                }
            ],
            "visual_direction": {
                "image_prompts": ["Close-up ledger", "Hand writing check"],
                "reference_notes": [],
                "shot_format_choices": ["talking head"],
            },
            "self_audit_flags": [],
        }
        result = convert_legacy_draft(legacy, draft_id=3, business_slug="stackpenni")
        assert result.is_valid
        contract = result.contract
        assert len(contract["beats"]) == 2
        assert contract["beats"][0]["beat_id"] == "b01"
        assert contract["beats"][1]["beat_id"] == "b02"
        assert contract["beats"][0]["vo_text"] == "The eighth wonder"
        assert contract["beats"][0]["capture_policy"] == "legacy_unclassified"
        # Synthesized IDs should be marked
        assert result.warnings  # should have warnings about synthesized fields

    def test_missing_fields_stay_null(self):
        """Missing information must remain null/unknown — never invented."""
        legacy = {
            "platform_content": [
                {
                    "platform": "instagram",
                    "variant_type": "reel",
                    "content": "",
                    "posts": [{"label": "HOOK", "vo_text": "test"}],
                    "image_prompts": [],
                }
            ],
            "visual_direction": {
                "image_prompts": [],
                "reference_notes": [],
                "shot_format_choices": [],
            },
            "self_audit_flags": [],
        }
        result = convert_legacy_draft(legacy, draft_id=1, business_slug="test")
        contract = result.contract
        # Missing evidence refs should be empty, not invented
        assert contract["content_contract"]["evidence_refs"] == []
        # Missing core_claim should be empty or from content
        # Missing authenticity_anchor should be "none" (not invented)
        assert contract["content_contract"].get("authenticity_anchor", "") == "none"
        # Capture policy should be legacy_unclassified (not invented as capture_required)
        assert contract["content_contract"]["capture_policy"] == "legacy_unclassified"

    def test_never_invents_evidence(self):
        """The compat reader must never invent evidence, capture policy, or approved intent."""
        legacy = {
            "platform_content": [
                {
                    "platform": "x",
                    "variant_type": "single_post",
                    "content": "test post",
                    "posts": ["test post"],
                    "image_prompts": ["none"],
                }
            ],
            "visual_direction": {
                "image_prompts": ["none"],
                "reference_notes": [],
                "shot_format_choices": ["text"],
            },
            "self_audit_flags": [],
        }
        result = convert_legacy_draft(legacy, draft_id=10, business_slug="test")
        contract = result.contract
        # evidence_refs should be empty — never invented
        assert contract["content_contract"]["evidence_refs"] == []
        # performance_hypothesis should be empty — never invented
        assert contract["content_contract"].get("performance_hypothesis", "") == ""
        # visual_intent in beats should be None for legacy beats (not invented)
        if contract["beats"]:
            for beat in contract["beats"]:
                assert beat.get("visual_intent") is None or beat["visual_intent"] == {}

    def test_warnings_emitted_for_synthesized_fields(self):
        """The result should warn about synthesized IDs and unknown fields."""
        legacy = {
            "platform_content": [
                {
                    "platform": "instagram",
                    "variant_type": "reel",
                    "content": "test",
                    "posts": [{"label": "HOOK", "vo_text": "test"}],
                    "image_prompts": ["test"],
                }
            ],
            "visual_direction": {
                "image_prompts": ["test"],
                "reference_notes": [],
                "shot_format_choices": ["test"],
            },
            "self_audit_flags": [],
        }
        result = convert_legacy_draft(legacy, draft_id=1, business_slug="test")
        assert len(result.warnings) > 0
        assert any("synthesized" in w.lower() or "legacy" in w.lower() or "unknown" in w.lower() for w in result.warnings)

    def test_multiple_platforms_get_separate_contracts(self):
        """Each platform variant should get its own contract_id."""
        legacy = {
            "platform_content": [
                {"platform": "x", "variant_type": "thread", "content": "t", "posts": ["t"], "image_prompts": ["none"]},
                {"platform": "instagram", "variant_type": "carousel", "content": "c", "posts": ["c1", "c2"], "image_prompts": ["img1", "img2"]},
            ],
            "visual_direction": {"image_prompts": [], "reference_notes": [], "shot_format_choices": []},
            "self_audit_flags": [],
        }
        results = convert_legacy_draft(legacy, draft_id=7, business_slug="test", per_platform=True)
        assert len(results) == 2
        assert results[0].contract["contract_id"] != results[1].contract["contract_id"]
        assert "x" in results[0].contract["contract_id"]
        assert "instagram" in results[1].contract["contract_id"]

    def test_empty_draft_returns_empty_result(self):
        """An empty legacy draft should return a result with is_valid=False."""
        result = convert_legacy_draft({}, draft_id=1, business_slug="test")
        assert not result.is_valid
        assert len(result.warnings) > 0