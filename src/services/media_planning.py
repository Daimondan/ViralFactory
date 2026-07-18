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
import time
from typing import Any

from services import ServiceResponse

# Provider names that must never appear in Writer/beat output
_PROVIDER_NAMES = {"fal", "grok", "veo", "sora", "pexels", "pixabay", "openai", "stability", "midjourney"}


def _resolve_video_generator(generator: str, media_config: dict) -> dict:
    if not (generator or "").startswith("ai_video"):
        raise ValueError(f"Not an AI video generator: {generator}")
    if ":" not in generator:
        return {"model": None, "provider": None, "name": "default"}
    name = generator.split(":", 1)[1]
    for configured in media_config.get("video_generators", []):
        if configured.get("name") == name:
            return {
                "model": configured.get("model"),
                "provider": configured.get("provider"),
                "name": name,
            }
    raise ValueError(
        f"Unknown AI video generator '{name}' — add it to media.video_generators"
    )


def _find_available_video_generator(
    media_config: dict,
    exclude_name: str | None = None,
) -> dict | None:
    for configured in media_config.get("video_generators", []):
        if exclude_name and configured.get("name") == exclude_name:
            continue
        api_key_env = configured.get("api_key_env", "")
        if api_key_env and os.environ.get(api_key_env, ""):
            return {
                "model": configured.get("model"),
                "provider": configured.get("provider"),
                "name": configured.get("name"),
            }
    return None


def _resolve_video_generator_with_fallback(generator: str, media_config: dict) -> dict:
    resolved = _resolve_video_generator(generator, media_config)
    api_key_env = ""
    for configured in media_config.get("video_generators", []):
        if configured.get("name") == resolved["name"]:
            api_key_env = configured.get("api_key_env", "")
            break
    if resolved["name"] == "default" and not api_key_env:
        fallback = _find_available_video_generator(media_config)
        if fallback:
            fallback["fell_back"] = True
            return fallback
        return resolved
    if api_key_env and os.environ.get(api_key_env, ""):
        resolved["fell_back"] = False
        return resolved
    fallback = _find_available_video_generator(
        media_config,
        exclude_name=resolved["name"],
    )
    if fallback:
        fallback["fell_back"] = True
        return fallback
    resolved["fell_back"] = False
    return resolved


def _summarize_results(results: list[dict]) -> dict:
    available_count = sum(1 for result in results if result.get("status") == "ok")
    processing_count = sum(
        1 for result in results if result.get("status") == "processing"
    )
    submitted_count = sum(
        1 for result in results if result.get("status") == "submitted"
    )
    failed_count = sum(1 for result in results if result.get("status") == "failed")
    skipped_count = sum(1 for result in results if result.get("status") == "skipped")
    return {
        "available_count": available_count,
        "processing_count": processing_count,
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "ready_to_render": available_count > 0,
    }


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

    def __init__(
        self,
        models_config: dict = None,
        db_path: str = "data/viralfactory.db",
        config_dir: str = "config",
        modules_dir: str = "modules",
        prompts_dir: str = "prompts",
    ):
        self.models_config = models_config or {}
        self.db_path = db_path
        self.config_dir = config_dir
        self.modules_dir = modules_dir
        self.prompts_dir = prompts_dir

    def _poll_video(
        self,
        media_adapter,
        external_job_id: str,
        asset_id: int,
        model: str,
        prompt: str,
        business_slug: str,
        provider: str | None = None,
        estimated_cost_usd: float = 0,
    ) -> dict:
        for _ in range(60):
            time.sleep(5)
            kwargs = {"provider": provider}
            if provider == "fal":
                kwargs["model"] = model
            poll_result = media_adapter.check_video_job(external_job_id, **kwargs)
            status = poll_result.get("status", "")
            if status == "completed":
                download_url = poll_result.get("download_url", "")
                if not download_url:
                    return {
                        "status": "failed",
                        "error": "Job completed but no download URL was returned by the provider",
                    }
                downloaded = media_adapter.download_video(
                    external_job_id,
                    download_url,
                    asset_id,
                    model,
                    prompt,
                    poll_result.get("cost_usd", 0) or estimated_cost_usd,
                    business_slug,
                    video_provider=provider,
                )
                return {
                    "status": "ok",
                    "path": downloaded["file_path"],
                    "ingredient_id": f"generated:{downloaded['media_id']}",
                }
            if status == "failed":
                return {
                    "status": "failed",
                    "error": poll_result.get("error", "Video generation failed"),
                }
        return {"status": "processing", "external_job_id": external_job_id}

    def generate_for_asset(
        self,
        *,
        asset_id: int,
        business_slug: str,
        store=None,
    ) -> ServiceResponse:
        """Plan and acquire missing media through one shared service path."""
        from config_loader import ConfigError, load_all
        from context_assembly import assemble_module_context
        from llm_adapter import LLMAdapter
        from media_adapter import MediaAdapter
        from pipeline import MEDIA_PLAN_SCHEMA, PipelineStore
        from stock_adapter import StockAdapter

        store = store or PipelineStore(self.db_path)
        asset = store.get_asset(asset_id)
        if not asset:
            return ServiceResponse({"error": "Asset not found"}, 404)
        draft = store.get_draft(asset["draft_id"])
        if not draft:
            return ServiceResponse({"error": "Draft not found"}, 404)
        card = (
            store.get_idea_card(draft["idea_card_id"])
            if draft.get("idea_card_id")
            else None
        )
        if not card:
            return ServiceResponse({"error": "No idea card for this asset"}, 400)

        treatment = json.loads(card.get("treatment") or "{}")
        capture_required = treatment.get("capture_required", [])
        uploads = json.loads(card.get("capture_uploads") or "[]")
        missing = capture_required[len(uploads):]
        if not missing:
            return ServiceResponse({
                "status": "ok",
                "message": "No missing captures — all fulfilled",
            })

        try:
            config = load_all(self.config_dir)
            models_config = self.models_config or config["models"]
            business = config["business"]
        except ConfigError as exc:
            return ServiceResponse({"error": f"Config error: {exc}"}, 500)

        module_vars, module_prov = assemble_module_context(
            "assembly/media_plan_v1.md",
            business_slug,
            db_path=self.db_path,
            modules_dir=self.modules_dir,
            prompts_dir=self.prompts_dir,
        )
        media_config = models_config.get("media", {})
        generator_lines = self._build_generator_descriptions(models_config)

        vo_timeline = "(no VO generated yet — plan visuals against the script beats)"
        coverage_gaps = "(no VO duration data — estimate based on script structure)"
        vo_segments_json = store.get_vo_segments(asset_id)
        if vo_segments_json:
            try:
                vo_segments = json.loads(vo_segments_json)
                timeline_lines = []
                gap_lines = []
                for segment in vo_segments:
                    frame = segment.get("frame", "?")
                    duration = segment.get("duration", 0)
                    preview = segment.get("text", "")[:60]
                    timeline_lines.append(
                        f"  Frame {frame}: {duration:.1f}s — \"{preview}...\""
                    )
                    gap_lines.append(
                        f"  Frame {frame}: needs {duration:.1f}s of visual coverage — "
                        "no ingredient assigned yet"
                    )
                total_duration = sum(
                    segment.get("duration", 0) for segment in vo_segments
                )
                timeline_lines.append(f"  TOTAL: {total_duration:.1f}s")
                vo_timeline = "\n".join(timeline_lines)
                coverage_gaps = "\n".join(gap_lines)
            except (json.JSONDecodeError, TypeError):
                pass

        adapter = LLMAdapter(
            models_config,
            db_path=self.db_path,
            prompts_dir=self.prompts_dir,
        )
        try:
            plan = adapter.complete(
                prompt_file="assembly/media_plan_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "platform_name": asset.get("platform", ""),
                    "format_name": draft.get("format") or "",
                    "asset_content": asset["content"][:2000],
                    "vo_timeline": vo_timeline,
                    "coverage_gaps": coverage_gaps,
                    "missing_captures": "\n".join(
                        f"{index}. {task}" for index, task in enumerate(missing)
                    ),
                    "available_generators": generator_lines,
                    **module_vars,
                },
                schema=MEDIA_PLAN_SCHEMA,
                backend="default",
                context=(
                    f"Media plan for asset {asset_id} ({asset.get('platform', '')}) | "
                    f"module_ctx: {module_prov}"
                ),
                business_slug=business_slug,
            )
        except Exception as exc:
            return ServiceResponse({"error": str(exc)}, 500)

        media_adapter = MediaAdapter(models_config, db_path=self.db_path)
        stock_adapter = StockAdapter(models_config, db_path=self.db_path)
        results = []
        for plan_item in plan.get("media_plan", []):
            results.append(self._execute_plan_item(
                plan_item=plan_item,
                asset_id=asset_id,
                business_slug=business_slug,
                media_config=media_config,
                media_adapter=media_adapter,
                stock_adapter=stock_adapter,
            ))

        summary = _summarize_results(results)
        payload = {
            "status": "ok",
            "media_plan": plan.get("media_plan", []),
            "results": results,
            "count": len(results),
            **summary,
        }
        if (
            results
            and summary["available_count"] == 0
            and summary["submitted_count"] == 0
            and summary["processing_count"] == 0
        ):
            payload["status"] = "error"
            payload["error"] = (
                f"No renderable media was generated — {summary['failed_count']} failed, "
                f"{summary['skipped_count']} skipped."
            )
            return ServiceResponse(payload, 500)
        return ServiceResponse(payload)

    def _build_generator_descriptions(self, models_config: dict) -> str:
        media_config = models_config.get("media", {})
        stock_config = models_config.get("stock", {})
        generators = []
        stock_providers = stock_config.get("providers", [])
        if stock_providers:
            key_env = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}
            available = [
                provider for provider in stock_providers
                if os.environ.get(key_env.get(provider, ""), "")
            ]
            status = (
                f"available: {', '.join(available)}"
                if available
                else "needs API key"
            )
            generators.append(
                f"- **stock** — Search {', '.join(stock_providers)} for real-world "
                f"footage. {status}."
            )
        video_generators = media_config.get("video_generators", [])
        for generator in video_generators:
            available = bool(os.environ.get(generator.get("api_key_env", ""), ""))
            generators.append(
                f"- **ai_video:{generator['name']}** — {generator.get('provider', '')} "
                f"video generation ({generator.get('model', '')}). "
                f"{'available' if available else 'needs API key'}."
            )
        if not video_generators and media_config.get("video_default"):
            generators.append("- **ai_video** — Generate a video clip with AI.")
        if media_config.get("image_default"):
            generators.append("- **ai_image** — Generate a static image with AI.")
        if models_config.get("voice_cloning", {}).get("engine"):
            generators.append("- **voice** — Generate narration/voiceover.")
        if media_config.get("animation", {}).get("enabled"):
            generators.append("- **animation** — Generate 3D animation or motion graphics.")
        return "\n".join(generators) or "(no generators configured)"

    def _execute_plan_item(
        self,
        *,
        plan_item: dict,
        asset_id: int,
        business_slug: str,
        media_config: dict,
        media_adapter,
        stock_adapter,
    ) -> dict:
        generator = plan_item.get("generator", "")
        result = {
            "capture_index": plan_item.get("capture_index", 0),
            "frame": plan_item.get("frame"),
            "generator": generator,
        }
        try:
            if generator == "stock":
                query = plan_item.get("search_query", "")
                matches = stock_adapter.search(query, kind="video", per_page=3)
                if matches:
                    path = stock_adapter.download(matches[0])
                    provider = matches[0].get("provider", "stock")
                    media_id = media_adapter._record_media(
                        asset_id,
                        "video",
                        path,
                        f"stock:{provider}",
                        query,
                        0,
                        owner_type="asset",
                    )
                    result.update({
                        "status": "ok",
                        "ingredient_id": f"generated:{media_id}",
                        "path": path,
                    })
                else:
                    fallback = plan_item.get("fallback_generator", "ai_video")
                    prompt = plan_item.get("fallback_prompt") or plan_item.get(
                        "generation_prompt", ""
                    )
                    if not (fallback and prompt):
                        raise RuntimeError(
                            "Stock search returned nothing and no fallback configured"
                        )
                    return self._execute_video(
                        result,
                        fallback,
                        prompt,
                        plan_item,
                        asset_id,
                        business_slug,
                        media_config,
                        media_adapter,
                    )
            elif generator.startswith("ai_video"):
                prompt = plan_item.get("generation_prompt", "")
                if not prompt:
                    raise RuntimeError("Video generation prompt is required")
                return self._execute_video(
                    result,
                    generator,
                    prompt,
                    plan_item,
                    asset_id,
                    business_slug,
                    media_config,
                    media_adapter,
                )
            elif generator == "ai_image":
                prompt = plan_item.get("generation_prompt", "")
                image = media_adapter.generate_image(
                    prompt=prompt,
                    asset_id=asset_id,
                    aspect_ratio="9:16",
                    context=f"Media plan AI image for asset {asset_id}",
                    business_slug=business_slug,
                )
                result.update({"status": "ok", "path": image["path"]})
                if image.get("media_id"):
                    result["ingredient_id"] = f"generated:{image['media_id']}"
            elif generator in {"voice", "animation"}:
                result.update({
                    "status": "skipped",
                    "error": f"{generator.title()} generation is not wired",
                })
            else:
                result.update({
                    "status": "skipped",
                    "error": f"Unknown generator: {generator}",
                })
        except Exception as exc:
            result.update({"status": "failed", "error": str(exc)[:200]})
        return result

    def _execute_video(
        self,
        result: dict,
        generator: str,
        prompt: str,
        plan_item: dict,
        asset_id: int,
        business_slug: str,
        media_config: dict,
        media_adapter,
    ) -> dict:
        resolved = _resolve_video_generator_with_fallback(generator, media_config)
        if resolved.get("fell_back"):
            result["fallback_used"] = resolved["name"]
        submitted = media_adapter.submit_video(
            prompt=prompt,
            asset_id=asset_id,
            aspect_ratio="9:16",
            duration=plan_item.get("duration", 5),
            model=resolved.get("model"),
            provider=resolved.get("provider"),
            context=f"Media plan AI generation ({generator}) for asset {asset_id}",
            business_slug=business_slug,
        )
        external_job_id = submitted.get("external_job_id")
        if not external_job_id:
            result.update({
                "status": "failed",
                "error": "Video API returned no job ID",
            })
            return result
        result.update(self._poll_video(
            media_adapter,
            external_job_id,
            asset_id,
            submitted.get("model", resolved.get("model") or ""),
            prompt,
            business_slug,
            provider=submitted.get("provider") or resolved.get("provider"),
        ))
        return result

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