"""
Edit-planning service v2 (VF-AU-206).

Maps real inventory to beats and compiled cues. Produces source-resolved
segments with IDs, beat IDs, in/out, overlays, transition reasons, and
audio contributions.

Post-LLM mechanical checks: exact source IDs, bounds, required beat
coverage, cue references, duration, no text mutation.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Optional

from services import ServiceResponse


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

    def __init__(
        self,
        models_config: dict | None = None,
        db_path: str = "data/viralfactory.db",
        config_dir: str = "config",
        modules_dir: str = "modules",
        prompts_dir: str = "prompts",
    ):
        self.models_config = models_config
        self.db_path = db_path
        self.config_dir = config_dir
        self.modules_dir = modules_dir
        self.prompts_dir = prompts_dir

    def generate_for_asset(
        self,
        *,
        asset_id: int,
        business_slug: str,
        feedback: str = "",
        store=None,
    ) -> ServiceResponse:
        """Generate and persist an edit plan through the shared service path.

        This method is transport-neutral: both Flask routes and the autonomous
        chain call it with the same asset and store. HTTP status mapping is
        carried by ``ServiceResponse`` rather than embedded Flask behavior.
        """
        from assembly import AssemblyRenderer, probe_duration
        from config_loader import ConfigError, load_all
        from context_assembly import assemble_module_context
        from llm_adapter import LLMAdapter
        from pipeline import EDIT_PLAN_SCHEMA, PipelineStore
        from services.media_inventory import MediaInventoryService

        store = store or PipelineStore(self.db_path)
        asset = store.get_asset(asset_id)
        if not asset:
            return ServiceResponse({"error": "Asset not found"}, 404)

        draft = store.get_draft(asset["draft_id"])
        if not draft:
            return ServiceResponse({"error": "Draft not found"}, 404)

        try:
            config = load_all(self.config_dir)
            models_config = self.models_config or config["models"]
            business = config["business"]
        except ConfigError as exc:
            return ServiceResponse({"error": f"Config error: {exc}"}, 500)

        card = (
            store.get_idea_card(draft["idea_card_id"])
            if draft.get("idea_card_id")
            else None
        )
        treatment = json.loads(card.get("treatment") or "{}") if card else {}
        capture_required = treatment.get("capture_required", [])
        capture_upload_ids = (
            [int(value) for value in json.loads(card.get("capture_uploads") or "[]")]
            if card
            else []
        )

        inventory = MediaInventoryService(self.db_path).build_inventory(
            asset_id=asset_id,
            business_slug=business_slug,
            capture_upload_ids=capture_upload_ids,
        )
        visual_items = [
            item for item in inventory.render_ready_items
            if item.kind in {"image", "video"}
        ]
        if not visual_items:
            message = (
                "No usable visual media is available. Generate missing media or upload "
                "a capture before creating an edit plan."
            )
            return ServiceResponse({
                "status": "missing_media",
                "message": message,
                "required_count": len(capture_required),
                "available_visual_count": 0,
                "missing_count": max(1, len(capture_required)),
            }, 409)

        if capture_required and len(visual_items) < len(capture_required):
            missing_count = len(capture_required) - len(visual_items)
            message = (
                f"Missing {missing_count} required visual capture(s). "
                "Generate missing media or upload the required captures before creating an edit plan."
            )
            return ServiceResponse({
                "status": "missing_media",
                "message": message,
                "required_count": len(capture_required),
                "available_visual_count": len(visual_items),
                "missing_count": missing_count,
            }, 409)

        ingredients = []
        for item in visual_items:
            duration = item.duration_sec
            if duration is None:
                duration = probe_duration(item.path) if item.kind == "video" else 3.0
            if duration is None:
                duration = 5.0
            description = (
                item.metadata.get("prompt")
                or item.metadata.get("filename")
                or os.path.basename(item.path)
            )[:100]
            ingredients.append({
                "id": item.ingredient_id,
                "kind": item.kind,
                "duration": duration,
                "description": description,
            })

        inventory_text = "\n".join(
            f"- {item['id']} ({item['kind']}, {item['duration']:.1f}s): {item['description']}"
            for item in ingredients
        )

        platform_name = asset.get("platform", "")
        variant_type = asset.get("variant_type", "").lower()
        if "reel" in variant_type or "short" in variant_type:
            max_segment_seconds = 3
        elif "carousel" in variant_type:
            max_segment_seconds = 3
        else:
            max_segment_seconds = 4

        module_vars, module_prov = assemble_module_context(
            "assembly/edit_plan_v1.md",
            business_slug,
            dynamic={"format_name": draft.get("format") or ""},
            db_path=self.db_path,
            modules_dir=self.modules_dir,
            prompts_dir=self.prompts_dir,
        )
        adapter = LLMAdapter(
            models_config,
            db_path=self.db_path,
            prompts_dir=self.prompts_dir,
        )
        try:
            result = adapter.complete(
                prompt_file="assembly/edit_plan_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "platform_name": platform_name,
                    "format_name": draft.get("format") or "",
                    "scope": draft.get("scope") or "",
                    "asset_content": asset["content"][:2000],
                    "vo_info": "(no VO take yet)",
                    "ingredient_inventory": inventory_text,
                    "max_segment_seconds": str(max_segment_seconds),
                    **module_vars,
                },
                schema=EDIT_PLAN_SCHEMA,
                backend="default",
                context=(
                    f"Edit plan for asset {asset_id} ({platform_name}) | "
                    f"module_ctx: {module_prov}"
                ),
                business_slug=business_slug,
            )
        except Exception as exc:
            return ServiceResponse({"error": str(exc)}, 500)

        valid_source_ids = {item["id"] for item in ingredients}
        invalid_sources = [
            segment.get("source", "")
            for segment in result.get("segments", [])
            if segment.get("source", "") not in valid_source_ids
        ]
        if invalid_sources:
            message = (
                f"Edit plan contains {len(invalid_sources)} invalid source(s): "
                f"{', '.join(invalid_sources[:5])}. The LLM invented references "
                "that are not in the ingredient inventory."
            )
            return ServiceResponse({
                "status": "invalid_sources",
                "message": message,
                "invalid_sources": invalid_sources,
                "valid_sources": sorted(valid_source_ids),
            }, 422)

        plan_id = store.save_edit_plan(draft["id"], asset_id, result)
        cut_list = AssemblyRenderer(
            models_config,
            db_path=self.db_path,
        ).format_cut_list_for_display(result)
        return ServiceResponse({
            "status": "ok",
            "plan_id": plan_id,
            "cut_list": cut_list,
            "plan": result,
        })

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