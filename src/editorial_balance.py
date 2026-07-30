"""VF-IDEA-1611 recent editorial-balance context."""

from __future__ import annotations

import json
from typing import Any


FRAMING_FAMILY_SCHEMA = {
    "type": "object",
    "required": ["analysis_version", "framing_families", "advisory_note"],
    "properties": {
        "analysis_version": {"type": "string"},
        "framing_families": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["family_id", "description", "card_ids", "repetition_note"],
                "properties": {
                    "family_id": {"type": "string"},
                    "description": {"type": "string"},
                    "card_ids": {"type": "array", "items": {"type": "integer"}},
                    "repetition_note": {"type": "string"},
                },
            },
        },
        "advisory_note": {"type": "string"},
    },
}


def compute_lens_counts(cards: list[dict]) -> dict[str, int]:
    """Count persisted lens IDs; malformed/unrecorded values are skipped."""
    counts: dict[str, int] = {}
    for card in cards:
        value = card.get("editorial_fit")
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                continue
        if not isinstance(value, dict) or not isinstance(value.get("lens_id"), str):
            continue
        lens_id = value["lens_id"]
        counts[lens_id] = counts.get(lens_id, 0) + 1
    return counts


class EditorialBalanceService:
    """Build advisory history context and run separate framing analysis."""

    prompt_file = "ideas/framing_family_analysis_v1.md"

    def __init__(self, adapter: Any, config_dir: str = "config"):
        self.adapter = adapter
        self.config_dir = config_dir

    def analyze(
        self,
        business_slug: str,
        recent_cards: list[dict],
        current_candidates: list[dict],
    ) -> dict:
        lens_counts = compute_lens_counts(recent_cards)
        variables = {
            "recent_cards": recent_cards,
            "lens_counts": lens_counts,
            "current_candidates": current_candidates,
        }
        result = self.adapter.complete(
            prompt_file=self.prompt_file,
            variables=variables,
            schema=FRAMING_FAMILY_SCHEMA,
            backend="default",
            context=f"Editorial framing-family analysis for {business_slug}",
            business_slug=business_slug,
            profile="editorial_balance",
        )
        allowed_card_ids = {card.get("id") for card in recent_cards if isinstance(card, dict)}
        for family in result.get("framing_families", []):
            unknown = set(family.get("card_ids", [])) - allowed_card_ids
            if unknown:
                raise ValueError(f"framing family contains unknown card IDs: {sorted(unknown)}")
        return {"lens_counts": lens_counts, "framing_analysis": result}
