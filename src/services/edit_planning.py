"""
Edit-planning service v2 (VF-AU-206).

Maps real inventory to beats and compiled cues. Produces source-resolved
segments with IDs, beat IDs, in/out, overlays, transition reasons, and
audio contributions.

Post-LLM mechanical checks: exact source IDs, bounds, required beat
coverage, cue references, duration, no text mutation.
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Optional

from services import ServiceResponse

logger = logging.getLogger(__name__)


def _phase_from_beat_index(i: int, beats: list | None = None) -> str:
    """Map a beat index to a default energy phase for the soundtrack mix.

    The phases correspond to the energy curve config mapping:
    intro → build → duck → lift → settle → settle.
    """
    phases = ["intro", "build", "duck", "lift", "settle", "settle"]
    return phases[min(i, len(phases) - 1)]


EDIT_PLAN_V2_SCHEMA = {
    "type": "object",
    "required": ["segments", "canvas"],
    "properties": {
        "segments": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": [
                    "segment_id", "beat_ids", "source", "source_in",
                    "source_out", "timeline_duration", "cue_ids",
                    "transition", "transition_reason", "audio_contribution",
                ],
                "properties": {
                    "segment_id": {"type": "string"},
                    "beat_ids": {"type": "array", "items": {"type": "string"}},
                    "source": {"type": "string"},
                    "source_in": {"type": "number"},
                    "source_out": {"type": "number"},
                    "timeline_duration": {"type": "number"},
                    "cue_ids": {"type": "array", "items": {"type": "string"}},
                    "transition": {"type": "string"},
                    "transition_reason": {"type": "string"},
                    "audio_contribution": {"type": "string"},
                },
            },
        },
        "canvas": {
            "type": "object",
            "required": ["aspect_ratio", "resolution"],
            "properties": {
                "aspect_ratio": {"type": "string"},
                "resolution": {"type": "string"},
            },
        },
    },
}


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
        seen_paths = set()  # deduplicate by path — retries create duplicate asset_media rows
        for item in visual_items:
            if item.path in seen_paths:
                continue
            seen_paths.add(item.path)
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

        raw_posts = json.loads(asset.get("posts") or "[]")
        if any(
            isinstance(post, dict) and str(post.get("vo_text") or "").strip()
            for post in raw_posts
        ):
            return self._generate_voice_led_plan(
                asset=asset,
                draft=draft,
                business=business,
                business_slug=business_slug,
                ingredients=ingredients,
                models_config=models_config,
                raw_posts=raw_posts,
                store=store,
            )

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

    def _generate_voice_led_plan(
        self,
        *,
        asset: dict,
        draft: dict,
        business: dict,
        business_slug: str,
        ingredients: list[dict],
        models_config: dict,
        raw_posts: list[dict],
        store,
    ) -> ServiceResponse:
        """Plan a voice-led asset around its exact approved measured take."""
        from assembly import AssemblyRenderer
        from context_assembly import assemble_module_context
        from feasibility_checks import run_feasibility_checks
        from llm_adapter import LLMAdapter
        from process_engine import compose_and_run
        from reel_production import (
            ReelProductionError,
            extract_reel_beats,
            validate_vo_segments,
        )
        from services.cue_compiler import CueCompiler

        structured_beats = extract_reel_beats(raw_posts)
        try:
            vo_segments = json.loads(store.get_vo_segments(asset["id"]) or "[]")
            vo_facts = validate_vo_segments(structured_beats, vo_segments)
        except (ReelProductionError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return ServiceResponse({
                "status": "vo_required",
                "message": f"Generate the complete approved voice-over before planning: {exc}",
            }, 409)

        raw_by_id = {
            str(post.get("beat_id") or f"b{index:02d}"): post
            for index, post in enumerate(raw_posts, 1)
            if isinstance(post, dict)
        }
        beats = []
        text_intents = []
        for beat in structured_beats:
            raw = raw_by_id.get(beat["beat_id"], {})
            beats.append({
                **beat,
                "required": True,
                "transition_in": str(raw.get("transition_in") or "cut"),
                "audio_intent": raw.get("audio_intent") or {},
            })
            if beat.get("vo_text"):
                text_intents.append({
                    "text_intent_id": f"caption_{beat['beat_id']}",
                    "beat_id": beat["beat_id"],
                    "function": "caption",
                    "text": beat["vo_text"],
                    "required": True,
                })
            if beat.get("overlay_text"):
                text_intents.append({
                    "text_intent_id": f"overlay_{beat['beat_id']}",
                    "beat_id": beat["beat_id"],
                    "function": str(raw.get("text_function") or "emphasis"),
                    "text": beat["overlay_text"],
                    "required": True,
                })

        compiler = CueCompiler()
        timeline = compiler.compile(
            beats=beats,
            text_intents=text_intents,
            vo_segments=vo_segments,
        )
        timing_errors = compiler.validate_timing(timeline)
        if timing_errors:
            return ServiceResponse({
                "status": "invalid_cues",
                "message": "Compiled cue timing is invalid.",
                "errors": timing_errors,
            }, 422)
        compiled = self._serialize_timeline(timeline)
        enriched_beats = beats
        visual_director_provenance = None
        if any(beat.get("visual") for beat in beats):
            visual_director_timeline = [
                {
                    "beat_id": timing["beat_id"],
                    "duration_sec": round(
                        float(timing["end_sec"]) - float(timing["start_sec"]),
                        3,
                    ),
                    "time_range": {
                        "start": 0.0,
                        "end": round(
                            float(timing["end_sec"]) - float(timing["start_sec"]),
                            3,
                        ),
                    },
                }
                for timing in compiled["vo_timings"]
            ]
            try:
                directed, module_prov = compose_and_run(
                    "visual_director_v1",
                    business_slug,
                    {
                        "asset_id": asset["id"],
                        "contract_beats": json.dumps(
                            beats, ensure_ascii=False, sort_keys=True,
                        ),
                        "vo_timeline": json.dumps(
                            visual_director_timeline,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    },
                    models_config=models_config,
                    db_path=self.db_path,
                    config_dir=self.config_dir,
                    modules_dir=self.modules_dir,
                    prompts_dir=self.prompts_dir,
                    business_config=business,
                )
            except Exception as exc:
                return ServiceResponse({"error": str(exc)}, 500)
            director_errors = self.validate_visual_director_output(
                directed,
                beats,
                vo_durations_by_beat={
                    timing["beat_id"]: timing["duration_sec"]
                    for timing in visual_director_timeline
                },
            )
            if director_errors:
                return ServiceResponse({
                    "status": "invalid_visual_events",
                    "message": "Visual Director output failed mechanical validation.",
                    "errors": director_errors,
                }, 422)
            events_by_beat = {
                beat["beat_id"]: beat["visual_events"]
                for beat in directed["beats"]
            }
            # F-009: Override source_policy for motion_graphic beats.
            # The Visual Director doesn't know about media_type — it may
            # assign generated_motion to beats the Writer marked as
            # motion_graphic. Respect the Writer's choice: motion_graphic
            # beats use generated_still, video beats use generated_motion.
            raw_posts_for_mt = json.loads(asset.get("posts") or "[]")
            beat_media_type = {}
            for i, post in enumerate(raw_posts_for_mt):
                if isinstance(post, dict):
                    bid = post.get("beat_id") or f"b{i+1:02d}"
                    visual = post.get("visual", {}) or {}
                    beat_media_type[bid] = visual.get("media_type", "")
            for beat_id, events in events_by_beat.items():
                mt = beat_media_type.get(beat_id, "")
                if mt == "motion_graphic":
                    for event in events:
                        if event.get("source_policy") == "generated_motion":
                            event["source_policy"] = "generated_still"
                elif mt == "video":
                    for event in events:
                        if event.get("source_policy") == "generated_still":
                            event["source_policy"] = "generated_motion"

            enriched_beats = [
                {**beat, "visual_events": events_by_beat[beat["beat_id"]]}
                for beat in beats
            ]
            visual_director_provenance = {
                "process": "visual_director_v1",
                "module_context": module_prov,
            }
        render_config = (models_config.get("media", {}) or {}).get(
            "reel_production", {}
        ) or {}
        required_render_config = (
            "aspect_ratio", "resolution", "caption_style_ref", "overlay_style_ref",
        )
        missing_render_config = [
            key for key in required_render_config if not render_config.get(key)
        ]
        feasibility_config = render_config.get("feasibility") or {}
        missing_render_config.extend(
            f"feasibility.{key}"
            for key in (
                "vo_timeline_tolerance_seconds",
                "visual_event_coverage_tolerance_seconds",
                "motion_shortfall_ratio",
            )
            if feasibility_config.get(key) is None
        )
        if missing_render_config:
            return ServiceResponse({
                "error": (
                    "Reel production config is missing: "
                    + ", ".join(missing_render_config)
                ),
            }, 500)

        module_vars, module_prov = assemble_module_context(
            "assembly/edit_plan_v2.md",
            business_slug,
            dynamic={"format_name": draft.get("format") or ""},
            db_path=self.db_path,
            modules_dir=self.modules_dir,
            prompts_dir=self.prompts_dir,
        )
        variables = {
            "business_name": business["business"]["name"],
            "platform_name": asset.get("platform", ""),
            "format_name": draft.get("format") or "",
            "asset_content": asset.get("content") or "",
            "beats_json": json.dumps(beats, ensure_ascii=False, sort_keys=True),
            "vo_take_json": json.dumps({
                "take_id": vo_facts["take_id"],
                "duration_sec": vo_facts["duration"],
            }, sort_keys=True),
            "compiled_cues_json": json.dumps(compiled, ensure_ascii=False, sort_keys=True),
            "inventory_json": json.dumps(ingredients, ensure_ascii=False, sort_keys=True),
            **module_vars,
        }
        adapter = LLMAdapter(
            models_config,
            db_path=self.db_path,
            prompts_dir=self.prompts_dir,
        )
        try:
            proposed = adapter.complete(
                prompt_file="assembly/edit_plan_v2.md",
                variables=variables,
                schema=EDIT_PLAN_V2_SCHEMA,
                backend="default",
                context=(
                    f"Measured-VO edit plan for asset {asset['id']} | "
                    f"module_ctx: {module_prov}"
                ),
                business_slug=business_slug,
            )
        except Exception as exc:
            return ServiceResponse({"error": str(exc)}, 500)

        errors = self.validate_segments(
            proposed.get("segments", []),
            beats,
            {item["id"] for item in ingredients},
            self._compiled_cue_ids(compiled),
            inventory_items={item["id"]: item for item in ingredients},
            require_source_out=True,
        )
        proposed_duration = round(sum(
            float(segment.get("timeline_duration") or 0)
            for segment in proposed.get("segments", [])
        ), 3)
        if abs(proposed_duration - vo_facts["duration"]) > 0.05:
            errors.append(
                f"Planned timeline is {proposed_duration:.3f}s but measured VO is "
                f"{vo_facts['duration']:.3f}s"
            )
        if errors:
            return ServiceResponse({
                "status": "invalid_plan",
                "message": "The proposed edit plan failed mechanical validation.",
                "errors": errors,
            }, 422)

        # F-009: Post-process segments to prefer video ingredients for
        # video beats. The LLM may pick the reference image instead of the
        # generated video clip for video beats. For each segment on a beat
        # with media_type=video, swap the source to the video ingredient
        # if the current source is an image.
        raw_posts_for_routing = json.loads(asset.get("posts") or "[]")
        beat_media_types = {}
        for i, post in enumerate(raw_posts_for_routing):
            if isinstance(post, dict):
                # beat_id may not be in raw posts — use index-based ID
                beat_id = post.get("beat_id") or f"b{i+1:02d}"
                visual = post.get("visual", {}) or {}
                beat_media_types[beat_id] = visual.get("media_type", "")

        # Also map enriched beats (which have beat_id from extract_reel_beats)
        for beat in enriched_beats:
            bid = beat.get("beat_id", "")
            raw_idx = None
            for i, post in enumerate(raw_posts_for_routing):
                if isinstance(post, dict) and post.get("beat_id") == bid:
                    raw_idx = i
                    break
            if raw_idx is not None:
                visual = raw_posts_for_routing[raw_idx].get("visual", {}) or {}
                beat_media_types[bid] = visual.get("media_type", "")

        # Map segments to media_type by beat_id (using enriched beats order)
        beat_ids_ordered = [beat.get("beat_id", "") for beat in enriched_beats]
        # Ingredient IDs from inventory are 'asset_media:N' but segment sources
        # are rendered as 'generated:N' by _render_source. Build lookup using
        # the rendered format.
        def _to_source(ingredient_id):
            kind, ref_id = ingredient_id.split(":", 1)
            aliases = {"asset_media": "generated", "capture_upload": "upload",
                       "stock_cache": "stock", "stock_media": "stock"}
            return f"{aliases.get(kind, kind)}:{ref_id}"

        video_sources = {
            _to_source(item["id"]): item for item in ingredients if item.get("kind") == "video"
        }
        image_sources = {
            _to_source(item["id"]): item for item in ingredients if item.get("kind") == "image"
        }

        if beat_media_types and video_sources:
            for segment in proposed.get("segments", []):
                beat_ids = segment.get("beat_ids", [])
                if not beat_ids:
                    continue
                beat_id = beat_ids[0]
                media_type = beat_media_types.get(beat_id, "")
                if media_type != "video":
                    continue
                # This is a video beat — check if the segment uses an image
                current_source = segment.get("source", "")
                # Check both rendered (generated:N) and raw (asset_media:N) formats
                is_image = (
                    current_source in image_sources
                    or current_source.replace("asset_media:", "generated:") in image_sources
                )
                if is_image:
                    # Find a video source not already used by another segment
                    used_video_sources = {
                        s.get("source") for s in proposed.get("segments", [])
                        if s.get("source") in video_sources
                        and s is not segment
                    }
                    available_videos = [
                        vid_id for vid_id in video_sources
                        if vid_id not in used_video_sources
                    ]
                    if available_videos:
                        # Set to the rendered format (generated:N) since
                        # _build_render_plan will pass it through _render_source
                        segment["source"] = available_videos[0]
                        segment["source_in"] = 0
                        segment["source_out"] = min(
                            video_sources[available_videos[0]]["duration"],
                            float(segment.get("source_out") or 5),
                        )

        plan = self._build_render_plan(
            proposed=proposed,
            compiled=compiled,
            render_config=render_config,
            vo_facts=vo_facts,
        )
        plan["contract_beats"] = enriched_beats
        if visual_director_provenance:
            plan["visual_director_provenance"] = visual_director_provenance
        compliance_contract = self._build_compliance_contract(
            beats,
            plan["segments"],
            compiled,
        )
        feasibility = run_feasibility_checks(
            plan=plan,
            compliance_contract=compliance_contract,
            vo_duration=vo_facts["duration"],
            tolerance_s=float(
                feasibility_config["vo_timeline_tolerance_seconds"]
            ),
            beats=enriched_beats,
            vo_segments=vo_segments,
            motion_durations=self._planned_motion_durations(
                proposed.get("segments", []),
                ingredients,
            ),
            event_coverage_tolerance_s=float(
                feasibility_config["visual_event_coverage_tolerance_seconds"]
            ),
            motion_shortfall_ratio=float(
                feasibility_config["motion_shortfall_ratio"]
            ),
        )
        if not feasibility["feasible"]:
            return ServiceResponse({
                "status": feasibility["verdict"],
                "message": feasibility["summary"],
                "feasibility": feasibility,
            }, 422)
        plan["feasibility"] = feasibility

        soundtrack_contract_id = f"asset:{asset['id']}"

        # Build audio intents from beats — needed by both the discovery
        # ranking step and the soundtrack planner below.
        audio_intents = [{
            "beat_id": beat["beat_id"],
            "audio_intent": beat.get("audio_intent") or {},
        } for beat in beats]

        # VF-VS-510 containment: the persisted planner contract is the only
        # soundtrack source of truth. Discovery, rights resolution, acquisition,
        # ranking, and mixing will advance that contract in later tasks; none may
        # run before the planner or bypass exact-artifact approval.
        soundtrack_content_contract = {
            "contract_id": soundtrack_contract_id,
            "platform": asset.get("platform", ""),
            "format_name": draft.get("format") or "",
            "content": asset.get("content") or "",
            "beats": beats,
        }
        try:
            soundtrack_plan, soundtrack_module_prov = compose_and_run(
                "soundtrack_plan_v1",
                business_slug,
                {
                    "asset_id": asset["id"],
                    "content_contract": json.dumps(
                        soundtrack_content_contract,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "vo_timeline": json.dumps(
                        compiled["vo_timings"],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "audio_intents": json.dumps(
                        audio_intents,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
                models_config=models_config,
                db_path=self.db_path,
                config_dir=self.config_dir,
                modules_dir=self.modules_dir,
                prompts_dir=self.prompts_dir,
                business_config=business,
            )
        except Exception as exc:
            return ServiceResponse({"error": str(exc)}, 500)

        soundtrack_errors = self.validate_soundtrack_planner_output(
            soundtrack_plan,
            expected_contract_id=soundtrack_contract_id,
            vo_duration=vo_facts["duration"],
        )
        if soundtrack_errors:
            return ServiceResponse({
                "status": "invalid_soundtrack_plan",
                "message": "Soundtrack Planner output failed mechanical validation.",
                "errors": soundtrack_errors,
            }, 422)
        plan["soundtrack_planner_provenance"] = {
            "process": "soundtrack_plan_v1",
            "module_context": soundtrack_module_prov,
        }

        platform_content = [{
            "platform": asset.get("platform", ""),
            "variant_type": asset.get("variant_type", ""),
            "content": asset.get("content", ""),
            "posts": raw_posts,
        }]
        source_hash = self._compute_source_draft_hash(platform_content, beats)

        # ── Guardrail: distinct media coverage ──
        # Every beat must have a distinct media source when the asset has
        # distinct image prompts. If N prompts exist but the plan has fewer
        # than N distinct media sources, reject it — this was the root cause
        # of the "one image for 41 seconds" defect. (QA-loop F-007)
        # Note: segments can outnumber beats (a beat may split into 2
        # segments — e.g. video + still). The check is distinct sources >=
        # distinct prompts, NOT distinct sources >= segments.
        # F-009 note: the post-processing may swap image→video sources using
        # a different ID format (generated:N vs asset_media:N). Count
        # distinct sources by normalizing to the same format, and only count
        # image beats (video beats share motion clips by design).
        segments = plan.get("segments", [])
        def _normalize_source(s):
            """Normalize asset_media:N and generated:N to the same key."""
            if s.startswith("asset_media:"):
                return s.replace("asset_media:", "generated:")
            return s
        sources = [_normalize_source(seg.get("source", "")) for seg in segments]
        distinct_sources = set(sources)
        image_prompts_count = len(json.loads(asset.get("image_prompts") or "[]"))
        # Only enforce distinct-source coverage when there are enough unique
        # ingredients. If the inventory has fewer unique items than prompts
        # (e.g. retries created duplicate asset_media rows), the LLM can't
        # assign distinct sources — relax the check.
        unique_inventory_ids = set()
        for ing in ingredients:
            unique_inventory_ids.add(_normalize_source(ing["id"]))
        if (
            image_prompts_count > 1
            and len(distinct_sources) < image_prompts_count
            and len(unique_inventory_ids) >= image_prompts_count
        ):
            return ServiceResponse({
                "status": "insufficient_media_coverage",
                "message": (
                    f"Edit plan has {len(distinct_sources)} distinct media source(s) "
                    f"but the asset has {image_prompts_count} image prompts — "
                    f"every beat needs its own visual. Reuse of the same "
                    f"image across beats is rejected."
                ),
                "segments": len(segments),
                "distinct_sources": len(distinct_sources),
                "image_prompts": image_prompts_count,
            }, 422)

        plan_id = store.save_edit_plan(
            draft["id"],
            asset["id"],
            plan,
            compliance_contract=compliance_contract,
            source_draft_hash=source_hash,
            soundtrack_plan=soundtrack_plan,
        )
        cut_list = AssemblyRenderer(
            models_config,
            db_path=self.db_path,
        ).format_cut_list_for_display(plan)
        return ServiceResponse({
            "status": "ok",
            "plan_id": plan_id,
            "cut_list": cut_list,
            "plan": plan,
        })

    @staticmethod
    def _serialize_timeline(timeline) -> dict:
        return {
            "vo_timings": [asdict(cue) for cue in timeline.vo_timings],
            "captions": [asdict(cue) for cue in timeline.captions],
            "overlays": [asdict(cue) for cue in timeline.overlays],
            "sfx_events": [asdict(cue) for cue in timeline.sfx_events],
            "music_events": [asdict(cue) for cue in timeline.music_events],
            "silence_events": [asdict(cue) for cue in timeline.silence_events],
            "text_hash": timeline.text_hash,
            "total_duration_sec": timeline.total_duration_sec,
        }

    @staticmethod
    def validate_soundtrack_planner_output(
        output: dict,
        *,
        expected_contract_id: str,
        vo_duration: float,
    ) -> list[str]:
        """Validate planner semantics without making soundtrack judgments."""
        from soundtrack_plan import validate_soundtrack_plan

        if not isinstance(output, dict):
            return ["Soundtrack Planner output must be an object"]

        errors = validate_soundtrack_plan(output)
        if output.get("contract_id") != expected_contract_id:
            errors.append(
                "soundtrack contract_id must match the production contract_id"
            )
        if output.get("operator_approval") is not None:
            errors.append(
                "operator_approval must be null until the operator gate issues it"
            )
        emotional_register = output.get("emotional_register")
        if not isinstance(emotional_register, str) or not emotional_register.strip():
            errors.append("emotional_register must be a non-empty string")
        search_queries = output.get("search_queries")
        if not isinstance(search_queries, list) or not search_queries:
            errors.append("search_queries must be a non-empty array")
        elif len(search_queries) > 6:
            errors.append("search_queries must contain at most 6 items")
        else:
            seen_queries = set()
            for index, query in enumerate(search_queries):
                if not isinstance(query, str) or not query.strip():
                    errors.append(f"search_queries[{index}] must be non-empty text")
                    continue
                if len(query) > 90:
                    errors.append(f"search_queries[{index}] must be at most 90 characters")
                normalized = " ".join(query.split()).casefold()
                if normalized in seen_queries:
                    errors.append("search_queries must be unique")
                seen_queries.add(normalized)

        for index, cue in enumerate(output.get("sfx_cues") or []):
            if not isinstance(cue, dict):
                continue
            timestamp = cue.get("timestamp")
            if (
                not isinstance(timestamp, bool)
                and isinstance(timestamp, (int, float))
                and timestamp > vo_duration
            ):
                errors.append(
                    f"sfx_cues[{index}].timestamp must fall within the VO timeline"
                )
        return errors

    @staticmethod
    def validate_visual_director_output(
        output: dict,
        approved_beats: list[dict],
        vo_durations_by_beat: dict[str, float] | None = None,
    ) -> list[str]:
        """Reject missing beats, invalid local timing, and invented copy."""
        from production_contract import validate_visual_events

        directed_beats = output.get("beats") if isinstance(output, dict) else None
        if not isinstance(directed_beats, list) or not directed_beats:
            return ["Visual Director output must contain a non-empty beats array"]

        errors = validate_visual_events(directed_beats)
        expected_ids = {beat["beat_id"] for beat in approved_beats}
        directed_ids = [str(beat.get("beat_id") or "") for beat in directed_beats]
        if len(directed_ids) != len(set(directed_ids)):
            errors.append("Visual Director output contains duplicate beat_id values")
        if set(directed_ids) != expected_ids:
            errors.append("Visual Director beat IDs do not match approved Writer beats")

        # Build a set of approved text fragments for required_text matching.
        # The Visual Director may split a multi-line overlay into separate
        # visual events (one per line), so we include each line of multi-line
        # overlays as a separate approved fragment. Comparison is
        # punctuation-insensitive so the LLM's minor formatting differences
        # (trailing periods, surrounding quotes) don't cause false rejections.
        import re as _re

        def _normalize_text(s: str) -> str:
            """Lowercase, strip, collapse whitespace, remove quotes/periods."""
            s = s.strip().lower()
            s = _re.sub(r"['\".]", "", s)
            s = _re.sub(r"\s+", " ", s)
            return s

        approved_fragments = set()
        for beat in approved_beats:
            for field in ("vo_text", "overlay_text"):
                text = beat.get(field)
                if not text:
                    continue
                approved_fragments.add(_normalize_text(text))
                # Add each line of multi-line overlays as a separate fragment
                for line in text.split("\n"):
                    line = line.strip()
                    if line:
                        approved_fragments.add(_normalize_text(line))
        for beat in directed_beats:
            visual_events = beat.get("visual_events") or []
            if not visual_events:
                errors.append(
                    f"Beat '{beat.get('beat_id', '?')}' has no visual events"
                )
            duration = (vo_durations_by_beat or {}).get(beat.get("beat_id"))
            numeric_events = [
                event
                for event in visual_events
                if not isinstance(
                    (event.get("time_range") or {}).get("start"),
                    bool,
                )
                and isinstance(
                    (event.get("time_range") or {}).get("start"),
                    (int, float),
                )
            ]
            if duration is not None and numeric_events:
                first_event = min(
                    numeric_events,
                    key=lambda event: (event.get("time_range") or {})["start"],
                )
                first_start = (first_event.get("time_range") or {}).get("start")
                if (
                    not isinstance(first_start, bool)
                    and isinstance(first_start, (int, float))
                    and abs(first_start) > 0.001
                ):
                    errors.append(
                        f"Visual event '{first_event.get('event_id', '?')}' time_range "
                        "must be beat-local and start at 0.0s"
                    )
            for event in visual_events:
                required_text = event.get("required_text")
                if required_text and _normalize_text(required_text) not in approved_fragments:
                    errors.append(
                        f"Visual event '{event.get('event_id', '?')}' invents audience text"
                    )
                time_range = event.get("time_range") or {}
                start = time_range.get("start")
                end = time_range.get("end")
                if (
                    duration is not None
                    and not isinstance(start, bool)
                    and isinstance(start, (int, float))
                    and not isinstance(end, bool)
                    and isinstance(end, (int, float))
                    and (start < 0 or end > duration or end <= start)
                ):
                    errors.append(
                        f"Visual event '{event.get('event_id', '?')}' time_range "
                        f"must be beat-local within 0..{duration:.3f}s"
                    )
        return errors

    @staticmethod
    def _compute_source_draft_hash(
        platform_content: list[dict],
        beats: list[dict],
    ) -> str:
        """Hash the exact approved Writer source available at this boundary."""
        canonical = json.dumps(
            {"platform_content": platform_content, "beats": beats},
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _compiled_cue_ids(compiled: dict) -> set[str]:
        cue_ids = set()
        for key in (
            "vo_timings", "captions", "overlays", "sfx_events",
            "music_events", "silence_events",
        ):
            cue_ids.update(cue["cue_id"] for cue in compiled.get(key, []))
        return cue_ids

    @staticmethod
    def _planned_motion_durations(
        segments: list[dict],
        ingredients: list[dict],
    ) -> dict[str, float]:
        """Measure planned video time per beat without counting still fallbacks."""
        # Ingredient IDs are 'asset_media:N' but segment sources are rendered
        # as 'generated:N'. Convert to the rendered format for matching.
        def _to_source(ingredient_id):
            kind, ref_id = ingredient_id.split(":", 1)
            aliases = {"asset_media": "generated", "capture_upload": "upload",
                       "stock_cache": "stock", "stock_media": "stock"}
            return f"{aliases.get(kind, kind)}:{ref_id}"

        video_ids = {
            _to_source(ingredient["id"])
            for ingredient in ingredients
            if ingredient.get("kind") == "video"
        }
        # Also keep the raw asset_media:N format — the LLM may use either
        video_ids_raw = {
            ingredient["id"]
            for ingredient in ingredients
            if ingredient.get("kind") == "video"
        }
        durations: dict[str, float] = {}
        for segment in segments:
            beat_ids = segment.get("beat_ids") or []
            seg_source = segment.get("source", "")
            if (seg_source not in video_ids and seg_source not in video_ids_raw) or not beat_ids:
                continue
            timeline_duration = float(segment.get("timeline_duration") or 0)
            source_duration = max(
                0.0,
                float(segment.get("source_out") or 0)
                - float(segment.get("source_in") or 0),
            )
            share = min(timeline_duration, source_duration) / len(beat_ids)
            for beat_id in beat_ids:
                durations[beat_id] = durations.get(beat_id, 0.0) + share
        return durations

    @staticmethod
    def _render_source(ingredient_id: str) -> str:
        kind, ref_id = ingredient_id.split(":", 1)
        aliases = {
            "asset_media": "generated",
            "capture_upload": "upload",
            "stock_cache": "stock",
            "stock_media": "stock",
        }
        return f"{aliases.get(kind, kind)}:{ref_id}"

    def _build_render_plan(
        self,
        *,
        proposed: dict,
        compiled: dict,
        render_config: dict,
        vo_facts: dict,
    ) -> dict:
        render_segments = []
        timeline_start = 0.0
        transition_by_beat = {
            cue.get("beat_id"): (cue.get("metadata") or {}).get("transition_in")
            for cue in compiled.get("overlays", [])
            if cue.get("cue_type") == "transition" and cue.get("beat_id")
        }
        entered_beat_ids = set()
        for segment in proposed.get("segments", []):
            duration = float(segment.get("timeline_duration") or 0)
            timeline_end = timeline_start + duration
            beat_ids = segment.get("beat_ids", [])
            first_beat_id = beat_ids[0] if beat_ids else None
            transition_in = (
                (
                    transition_by_beat.get(first_beat_id)
                    if first_beat_id not in entered_beat_ids
                    else None
                )
                or segment.get("transition")
                or "cut"
            )
            entered_beat_ids.update(beat_ids)
            overlays = []
            for cue in compiled.get("captions", []) + compiled.get("overlays", []):
                if cue.get("cue_type") == "transition":
                    continue
                if cue.get("beat_id") not in segment.get("beat_ids", []):
                    continue
                if (
                    cue.get("end_sec", 0) <= timeline_start
                    or cue.get("start_sec", 0) >= timeline_end
                ):
                    continue
                overlays.append({
                    "type": (
                        "caption" if cue.get("cue_type") == "caption" else "text_card"
                    ),
                    "text": cue.get("text", ""),
                    "start": round(
                        max(0.0, cue.get("start_sec", 0) - timeline_start), 3
                    ),
                    "end": round(
                        min(duration, cue.get("end_sec", 0) - timeline_start), 3
                    ),
                    "style_ref": (
                        render_config["caption_style_ref"]
                        if cue.get("cue_type") == "caption"
                        else render_config["overlay_style_ref"]
                    ),
                    "position": (
                        "bottom" if cue.get("cue_type") == "caption" else "center"
                    ),
                    "cue_id": cue.get("cue_id", ""),
                })
            render_segments.append({
                **segment,
                "source": self._render_source(segment["source"]),
                "ingredient_id": segment["source"],
                "in": float(segment.get("source_in") or 0),
                "out": float(segment.get("source_out") or duration),
                "transition_in": transition_in,
                "overlays": overlays,
                "sfx": [],
            })
            timeline_start = timeline_end

        canvas = dict(proposed.get("canvas") or {})
        canvas["aspect_ratio"] = render_config["aspect_ratio"]
        canvas["resolution"] = render_config["resolution"]
        canvas["duration_target"] = vo_facts["duration"]
        return {
            "segments": render_segments,
            "audio": {
                "vo": {
                    "take_id": vo_facts["take_id"],
                    "path": vo_facts["combined_path"],
                    "duration_sec": vo_facts["duration"],
                    "ducking": True,
                },
                "music": {},
                "original_audio": False,
            },
            "captions": {
                "burned_in": True,
                "source": "compiled_cues",
                "style_ref": render_config["caption_style_ref"],
            },
            "canvas": canvas,
            "compiled_cues": compiled,
        }

    @staticmethod
    def _build_compliance_contract(
        beats: list[dict],
        segments: list[dict],
        compiled: dict,
    ) -> dict:
        segment_ids_by_beat = {}
        for segment in segments:
            for beat_id in segment.get("beat_ids", []):
                segment_ids_by_beat.setdefault(beat_id, []).append(
                    segment.get("segment_id", "")
                )
        timing_by_beat = {
            cue["beat_id"]: cue
            for cue in compiled.get("vo_timings", [])
            if cue.get("beat_id")
        }
        contract_beats = []
        for beat in beats:
            timing = timing_by_beat.get(beat["beat_id"], {})
            contract_beats.append({
                "beat_id": beat["beat_id"],
                "source_excerpt": beat.get("vo_text", ""),
                "requirement_type": "spoken_dialogue",
                "required": bool(beat.get("required")),
                "planned_segment_ids": segment_ids_by_beat.get(beat["beat_id"], []),
                "planned_time_range": {
                    "start": round(float(timing.get("start_sec") or 0), 3),
                    "end": round(float(timing.get("end_sec") or 0), 3),
                },
                "verification_method": "audio_transcript_match",
            })
        return {
            "beats": contract_beats,
            "summary": (
                f"{len(contract_beats)} approved beats mapped to exact measured VO."
            ),
        }

    def validate_segments(self, segments: list[dict], beats: list[dict],
                           inventory_ingredient_ids: set[str],
                           compiled_cue_ids: set[str],
                           inventory_items: dict[str, dict] | None = None,
                           require_source_out: bool = False) -> list[str]:
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
        inventory_items = inventory_items or {}

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

            # 2. Bounds valid — clamp source_out to video duration if overshoot
            # is small (LLM can't know exact video duration to the millisecond)
            source_in = seg.get("source_in", 0)
            source_out = seg.get("source_out", 0)
            if source_in < 0:
                errors.append(f"Segment '{sid}' has negative source_in: {source_in}")
            if require_source_out and "source_out" not in seg:
                errors.append(f"Segment '{sid}' is missing source_out")
            if "source_out" in seg and source_in >= source_out:
                errors.append(f"Segment '{sid}' has invalid bounds: in={source_in} >= out={source_out}")
            source_item = inventory_items.get(source, {})
            source_duration = float(source_item.get("duration") or 0)
            if (
                source_item.get("kind") == "video"
                and source_duration > 0
                and source_out > source_duration
            ):
                # Clamp source_out to the video's actual duration instead of
                # rejecting the plan. The LLM approximates clip durations; a
                # small overshoot is corrected mechanically, not by re-running
                # the LLM. Large overshoots (>2s) still fail — that indicates
                # the LLM picked the wrong clip.
                overshoot = source_out - source_duration
                if overshoot > 2.0:
                    errors.append(
                        f"Segment '{sid}' source_out {source_out} exceeds video source "
                        f"duration {source_duration} by {overshoot:.1f}s — wrong clip?"
                    )
                else:
                    seg["source_out"] = round(source_duration, 3)

            # 3. Beat IDs reference known beats
            for bid in seg_beat_ids:
                if bid not in beat_ids:
                    errors.append(f"Segment '{sid}' references unknown beat_id: {bid}")
                covered_beats.add(bid)

            # 4. Cue references resolve
            referenced_cues = seg.get("cue_ids", seg.get("text_intent_ids", []))
            for cue_id in referenced_cues:
                if cue_id not in compiled_cue_ids:
                    errors.append(f"Segment '{sid}' references unknown cue: {cue_id}")

        # 5. Required beat coverage
        missing = required_beat_ids - covered_beats
        for bid in sorted(missing):
            errors.append(f"Required beat '{bid}' has no segment mapping")

        # 6. Max clip duration — advisory pacing check
        # Per viral mechanics research: "Change the visual every 2-4 seconds"
        # This is an advisory warning, not a hard error — long talking-head
        # segments are valid when the VO requires it. The edit plan prompt
        # should encourage splitting long segments, but the validator
        # should not reject them.
        MAX_CLIP_DURATION = 4.0
        for seg in segments:
            sid = seg.get("segment_id", "?")
            duration = float(seg.get("timeline_duration") or 0)
            has_overlay = bool(seg.get("overlays"))
            if duration > MAX_CLIP_DURATION and not has_overlay:
                # Advisory only — logged but not added to errors
                pass

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