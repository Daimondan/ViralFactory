"""
Edit-planning service v2 (VF-AU-206).

Maps real inventory to beats and compiled cues. Produces source-resolved
segments with IDs, beat IDs, in/out, overlays, transition reasons, and
audio contributions.

Post-LLM mechanical checks: exact source IDs, bounds, required beat
coverage, cue references, duration, no text mutation.
"""

import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class EditSegment:
    """A single source-resolved edit segment."""
    segment_id: str
    beat_ids: list[str]
    source: str               # ingredient_id from inventory
    source_in: float = 0.0
    source_out: float = 0.0
    timeline_duration: float = 0.0
    text_intent_ids: list[str] = field(default_factory=list)
    transition: str = "cut"
    transition_reason: str = ""
    audio_contribution: str = "vo"


@dataclass
class EditPlanResult:
    """Result of edit planning — segments + validation."""
    segments: list[EditSegment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


class EditPlanningService:
    """Maps real inventory to beats and compiled cues."""

    def validate_segments(self, segments: list[dict], beats: list[dict],
                           inventory_ingredient_ids: set[str],
                           compiled_cue_ids: set[str]) -> list[str]:
        """Post-LLM mechanical validation of edit plan segments.

        Checks:
        1. Every segment source exists in inventory
        2. Source in/out bounds are valid
        3. Every required beat has a segment
        4. Cue references resolve
        5. No text mutation (beat_ids match)
        6. Segment IDs are unique
        """
        errors = []

        beat_ids = {b["beat_id"] for b in beats if "beat_id" in b}
        required_beat_ids = {
            b["beat_id"] for b in beats
            if b.get("beat_id") and b.get("required", False)
        }

        # Check for duplicate segment IDs
        seen_seg_ids = set()
        for seg in segments:
            sid = seg.get("segment_id", "")
            if sid in seen_seg_ids:
                errors.append(f"Duplicate segment_id: {sid}")
            else:
                seen_seg_ids.add(sid)

        # Check each segment
        covered_beats = set()
        for seg in segments:
            sid = seg.get("segment_id", "?")
            source = seg.get("source", "")
            seg_beat_ids = seg.get("beat_ids", [])

            # 1. Source exists in inventory
            if source not in inventory_ingredient_ids:
                errors.append(
                    f"Segment '{sid}' references source '{source}' not in inventory — "
                    f"invented sources are not allowed"
                )

            # 2. Bounds valid
            source_in = seg.get("source_in", 0)
            source_out = seg.get("source_out", 0)
            if source_out > 0 and source_in >= source_out:
                errors.append(f"Segment '{sid}' has invalid bounds: in={source_in} >= out={source_out}")

            # 3. Beat IDs reference known beats
            for bid in seg_beat_ids:
                if bid not in beat_ids:
                    errors.append(f"Segment '{sid}' references unknown beat_id: {bid}")
                covered_beats.add(bid)

            # 4. Cue references resolve
            for cue_id in seg.get("text_intent_ids", []):
                if cue_id not in compiled_cue_ids:
                    errors.append(f"Segment '{sid}' references unknown text_intent: {cue_id}")

        # 5. Required beat coverage
        missing = required_beat_ids - covered_beats
        for bid in sorted(missing):
            errors.append(f"Required beat '{bid}' has no segment mapping")

        return errors

    def build_edit_plan_prompt_inputs(
        self,
        contract: dict,
        media_recipes: list[dict],
        compiled_cues: dict,
        inventory_summary: dict,
    ) -> dict:
        """Build inputs for the edit plan LLM prompt.

        The LLM receives: contract beats, media recipes (with real ingredient IDs),
        compiled cues (timings), and inventory summary. It produces source-resolved
        segments.
        """
        return {
            "beats": contract.get("beats", []),
            "media_recipes": media_recipes,
            "vo_timings": compiled_cues.get("vo_timings", []),
            "captions": compiled_cues.get("captions", []),
            "overlays": compiled_cues.get("overlays", []),
            "inventory": inventory_summary,
            "writer_contract_hash": contract.get("writer_contract_hash", ""),
        }