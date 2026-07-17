"""
Contract Compatibility Reader (VF-AU-105).

Reads existing platform_content drafts (from generate_v3 / DRAFT_SCHEMA)
without pretending they are full Production Contract v2 structures.

Behavior:
- Deterministic conversion where possible.
- Missing information remains null/unknown — never invented.
- Synthesized IDs are marked explicitly.
- New writes always use Production Contract v2 (generate_v4.md).
- Legacy capture tasks default to legacy_unclassified (AMENDMENT-009 Condition 3).
"""

import json
from typing import Any
from production_contract import (
    assemble_contract,
    compute_writer_contract_hash,
    PRODUCTION_CONTRACT_VERSION,
)


class CompatResult:
    """Result of a compatibility conversion."""

    def __init__(self, contract: dict | None = None, warnings: list[str] | None = None,
                 is_valid: bool = True):
        self.contract = contract
        self.warnings = warnings or []
        self.is_valid = is_valid


def convert_legacy_draft(
    legacy: dict,
    draft_id: int,
    business_slug: str,
    per_platform: bool = False,
) -> CompatResult | list[CompatResult]:
    """Convert a legacy draft (v3 DRAFT_SCHEMA) to partial Production Contract v2.

    Args:
        legacy: the legacy draft dict with platform_content, visual_direction, self_audit_flags
        draft_id: the draft's database ID (used for synthesized contract_id)
        business_slug: tenant slug
        per_platform: if True, return one CompatResult per platform variant

    Returns:
        CompatResult (single) or list[CompatResult] (if per_platform=True)
    """
    if not legacy or "platform_content" not in legacy:
        return CompatResult(is_valid=False, warnings=["Empty or invalid legacy draft"])

    platform_contents = legacy.get("platform_content", [])
    if not platform_contents:
        return CompatResult(is_valid=False, warnings=["No platform_content in legacy draft"])

    warnings = []

    if per_platform:
        results = []
        for pc in platform_contents:
            result = _convert_single_platform(pc, legacy, draft_id, business_slug, warnings)
            results.append(result)
        return results

    # Single contract for the primary platform (first entry)
    return _convert_single_platform(
        platform_contents[0], legacy, draft_id, business_slug, warnings
    )


def _convert_single_platform(
    platform_content: dict,
    legacy: dict,
    draft_id: int,
    business_slug: str,
    shared_warnings: list[str],
) -> CompatResult:
    """Convert a single platform_content entry to a partial Production Contract v2."""
    warnings = list(shared_warnings)
    platform = platform_content.get("platform", "unknown")
    variant_type = platform_content.get("variant_type", "unknown")
    content = platform_content.get("content", "")
    posts = platform_content.get("posts", [])

    contract_id = f"c{draft_id}_{platform}"

    # Synthesize beats from frame objects (reel/story_series only)
    beats = []
    if variant_type in ("reel", "story_series") and posts:
        for i, post in enumerate(posts):
            if isinstance(post, dict):
                beat_id = f"b{i+1:02d}"
                beat = {
                    "beat_id": beat_id,
                    "platform_variant_id": f"pv{draft_id}_{platform}",
                    "role": _infer_role(post.get("label", "")),
                    "required": True,  # all frames are required in a reel
                    "vo_text": post.get("vo_text", ""),
                    "staged_action": post.get("visual", {}).get("image_prompt", "") if isinstance(post.get("visual"), dict) else "",
                    "capture_policy": "legacy_unclassified",
                    "evidence_refs": [],  # unknown — never invented
                }
                # visual_intent: None for legacy (we don't know semantic meaning)
                beat["visual_intent"] = None
                beat["audio_intent"] = None
                beats.append(beat)
        if beats:
            warnings.append(f"Synthesized {len(beats)} beat_id(s) from frame positions — these are not stable pipeline IDs")

    # Build content contract from available fields
    # All unknown fields default to empty/legacy_unclassified — never invented
    # Required fields must be non-empty for assemble_contract to accept
    content_contract = {
        "contract_id": contract_id,
        "core_claim": content if content else f"Legacy draft {draft_id} for {platform}",
        "audience_value": "unknown (legacy conversion)",  # unknown from legacy
        "evidence_refs": [],  # unknown — never invented
        "primary_emotional_job": "unknown",  # unknown from legacy
        "primary_audience_action": "finish",  # safe default for legacy
        "format_name": variant_type,
        "platform": platform,
        "capture_policy": "legacy_unclassified",  # AMENDMENT-009 Condition 3
        "authenticity_anchor": "none",  # unknown
        "performance_hypothesis": "",  # never invented
        "evidence_label": "HYPOTHESIS",  # safe default for legacy
    }

    warnings.append("capture_policy=legacy_unclassified — operator must classify before compliance (AMENDMENT-009 Condition 3)")

    # Build text intents from text_on_screen if present
    text_intents = []
    for i, post in enumerate(posts):
        if isinstance(post, dict) and post.get("text_on_screen"):
            tos = post["text_on_screen"]
            if isinstance(tos, dict) and tos.get("text"):
                beat_id = f"b{i+1:02d}" if variant_type in ("reel", "story_series") else f"b{i+1:02d}"
                text_intents.append({
                    "text_intent_id": f"t{i+1:02d}",
                    "beat_id": beat_id,
                    "function": "caption",  # safe default — we don't know the real function
                    "text": tos.get("text", ""),
                    "required": False,  # legacy — don't know if it was required
                })

    # Assemble the contract using the production contract module
    # This computes the writer_contract_hash
    try:
        contract = assemble_contract(
            content_contract=content_contract,
            beats=beats,
            text_intents=text_intents,
            media_recipes=[],  # legacy drafts have no recipes — media planning is separate
            edit_segments=[],  # legacy drafts have no segments — edit planning is separate
        )
    except Exception as e:
        return CompatResult(
            is_valid=False,
            warnings=warnings + [f"Contract assembly failed: {e}"],
        )

    # Preserve visual_direction from legacy for reference
    contract["legacy_visual_direction"] = legacy.get("visual_direction", {})
    contract["legacy_self_audit_flags"] = legacy.get("self_audit_flags", [])

    return CompatResult(contract=contract, warnings=warnings, is_valid=True)


def _infer_role(label: str) -> str:
    """Map a frame label to a beat role."""
    label_upper = label.upper().strip()
    mapping = {
        "HOOK": "hook",
        "SETUP": "setup",
        "BUILD": "development",
        "TURN": "turn",
        "PAYOFF": "payoff",
        "CLOSE": "close",
        "ORIENTATION": "orientation",
        "PROOF": "proof",
    }
    return mapping.get(label_upper, "development")  # safe default