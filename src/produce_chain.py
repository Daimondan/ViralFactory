"""
T8.6: Production chain — split into Writer and Assembler stages.

Gate 1 approval triggers the WRITER chain: draft generation only.
The draft stops at draft_ready for human review (Gate 2).

When the operator ships the draft (Gate 2), the ASSEMBLER chain triggers:
per-platform fan-out → visual generation, producing assets for review (Gate 3).

No-auto-publish remains absolute — the chain terminates at asset review.

Card state transitions:
  Writer:   approved → writing → draft_ready (success) | writer_failed (error)
  Assembler: shipped → assembling → asset_ready (success) | assembly_failed (error)

Concurrency: serialized per business (single worker queue via jobs table).
"""

import json
import os
import sys
import threading
import traceback
from datetime import datetime, timezone

# Ensure src/ is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class ProductionChain:
    """Orchestrates the auto-production chain for an approved idea card.
    Runs in a background thread; card state tracks progress.
    """

    def __init__(self, db_path: str, config_dir: str, modules_dir: str, prompts_dir: str):
        self.db_path = db_path
        self.config_dir = config_dir
        self.modules_dir = modules_dir
        self.prompts_dir = prompts_dir

    def run_writer_chain(self, card_id: int, business_slug: str):
        """Writer stage: draft generation + AI review loop. Stops at draft_ready for Gate 2.
        Card state: writing → reviewing → draft_ready | writer_failed.

        T9.5: AI review loop runs between draft generation and draft_ready:
        1. Writer produces draft + self_audit_flags
        2. Self-audit fix: Writer revises its own draft to resolve flagged items
        3. Alignment check: second LLM call checks draft against approved idea
        4. If issues found, revise and re-check, max 3 rounds
        5. Only then does the draft reach draft_ready for Gate 2
        """
        from pipeline import PipelineStore
        store = PipelineStore(db_path=self.db_path)

        store.update_card_state(card_id, "writing")

        try:
            draft_id = self._step_draft(card_id, business_slug, store)
            if draft_id is None:
                raise RuntimeError("Draft generation returned no draft ID")

            # T9.5: AI review loop
            store.update_card_state(card_id, "reviewing")
            converged = self._run_ai_review_loop(draft_id, card_id, business_slug, store)

            # Writer stops here — draft is ready for human review (Gate 2)
            store.update_draft_state(draft_id, "draft_ready")
            store.update_card_state(card_id, "draft_ready")

        except Exception as e:
            error_msg = str(e)[:500]
            step = self._identify_failed_step(e)
            store.update_card_state(
                card_id,
                "writer_failed",
                production_error={"step": step, "error": error_msg},
            )

    def _run_ai_review_loop(self, draft_id: int, card_id: int,
                            business_slug: str, store) -> bool:
        """T9.5: AI review loop — self-audit fix + alignment check, max 3 rounds.

        Returns True if converged, False if hit the 3-round cap.
        All rounds logged in provenance and saved to review_history.
        """
        from config_loader import load_all, ConfigError
        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import ALIGNMENT_CHECK_SCHEMA

        try:
            config = load_all(self.config_dir)
            models_config = config["models"]
        except ConfigError as e:
            raise RuntimeError(f"Config error: {e}")

        card = store.get_idea_card(card_id)
        if not card:
            raise RuntimeError(f"Card {card_id} not found")

        draft = store.get_draft(draft_id)
        if not draft:
            raise RuntimeError(f"Draft {draft_id} not found")

        platform_content = json.loads(draft.get("platform_content") or "[]")
        self_audit_flags = json.loads(draft.get("self_audit_flags") or "[]")
        visual_direction = json.loads(draft.get("visual_direction") or "{}")

        hook_options = json.loads(card.get("hook_options") or "[]")
        source_ref_ids = json.loads(card.get("source_refs") or "[]")
        grounding_sources = "(no sources cited)"
        if source_ref_ids:
            resolved = store.resolve_source_refs(business_slug, source_ref_ids)
            if resolved:
                grounding_sources = "\n".join(
                    f"- [S{s['id']}] {s['title']}" for s in resolved
                )

        adapter = LLMAdapter(models_config, db_path=self.db_path, prompts_dir=self.prompts_dir)
        review_history = []
        max_rounds = 3
        converged = False

        for round_num in range(1, max_rounds + 1):
            # Step 1: Self-audit fix — if there are active flags, have the Writer fix them
            active_flags = [f for f in self_audit_flags if not f.get("status") or f.get("status") == "active"]
            applied_fixes = []

            if active_flags and round_num == 1:
                # Auto-fix: apply actual Writer-provided revised text. Do not
                # mark a flag applied unless platform_content changed.
                platform_content, applied_fixes = self._apply_self_audit_fixes(
                    platform_content, active_flags
                )
                draft_text_summary = platform_content[0].get("content", "") if platform_content else draft.get("draft_text", "")
                store.save_draft_content(
                    draft_id, draft_text_summary,
                    visual_direction, self_audit_flags,
                    platform_content=platform_content,
                )

            # Step 2: Alignment check
            # Convert platform_content to text for the alignment check
            pc_text_lines = []
            for pc in platform_content:
                pc_text_lines.append(f"### {pc.get('platform', '')} ({pc.get('variant_type', '')})")
                pc_text_lines.append(pc.get("content", ""))
                for p in pc.get("posts", []):
                    pc_text_lines.append(f"  - {p}")
            platform_content_text = "\n".join(pc_text_lines)

            fixes_text = "\n".join(
                f"- '{f['line']}' → '{f['fix']}' (rule: {f['rule']})"
                for f in applied_fixes
            ) if applied_fixes else "(no fixes applied)"

            try:
                alignment_result = adapter.complete(
                    prompt_file="draft/alignment_check_v1.md",
                    variables={
                        "idea": card["idea"],
                        "hook_options": "\n".join(f"- {h}" for h in hook_options),
                        "grounding_sources": grounding_sources,
                        "platform_content_text": platform_content_text[:6000],
                        "self_audit_fixes": fixes_text,
                    },
                    schema=ALIGNMENT_CHECK_SCHEMA,
                    backend="drafter",
                    context=f"AI review loop round {round_num} for draft {draft_id}",
                    business_slug=business_slug,
                    profile="drafter",
                )
            except (LLMAdapterError, Exception) as e:
                # If alignment check fails, don't block the draft — let the human review
                review_history.append({
                    "round": round_num,
                    "alignment_check": "error",
                    "error": str(e)[:200],
                })
                store.save_review_history(draft_id, review_history, converged=False)
                return False

            aligned = alignment_result.get("aligned", True)
            issues = alignment_result.get("issues", [])
            recommendations = alignment_result.get("recommendations", [])

            review_history.append({
                "round": round_num,
                "alignment_check": {
                    "aligned": aligned,
                    "issues": issues,
                    "recommendations": recommendations,
                },
                "self_audit_fixes": applied_fixes,
            })

            if aligned and not issues:
                converged = True
                break

            # If not converged and we have rounds left, revise
            if round_num < max_rounds and recommendations:
                # Send recommendations back to the Writer for revision
                platform_content = self._revise_draft_with_recommendations(
                    adapter, card, draft, platform_content, recommendations,
                    business_slug, round_num,
                )
                # Save the revised platform_content
                store.save_platform_content(draft_id, platform_content)
                draft = store.get_draft(draft_id)  # refresh

        # Save review history
        store.save_review_history(draft_id, review_history, converged=converged)
        return converged

    def _apply_self_audit_fixes(self, platform_content: list, active_flags: list) -> tuple[list, list]:
        """Apply self-audit fixes to platform_content.

        T9.5 requires the Writer to revise its own draft before Gate 2. The
        prompt supplies `fix_applied` for HIGH-confidence tells. This method is
        mechanical: replace the exact flagged line wherever it appears in the
        content/posts arrays. If no concrete fix is provided, keep the flag
        active so the alignment check/human can see it.
        """
        applied_fixes = []

        for flag in active_flags:
            original = (flag.get("line") or "").strip()
            fix = (flag.get("fix_applied") or "").strip()
            if not original or not fix:
                continue

            changed = False
            for pc in platform_content:
                content = pc.get("content", "")
                if original in content:
                    pc["content"] = content.replace(original, fix)
                    changed = True

                posts = pc.get("posts") or []
                revised_posts = []
                for post in posts:
                    if isinstance(post, str) and original in post:
                        revised_posts.append(post.replace(original, fix))
                        changed = True
                    elif isinstance(post, dict):
                        # Frame object (v4): fix in vo_text and text_on_screen.text
                        vo = post.get("vo_text", "")
                        if original in vo:
                            post["vo_text"] = vo.replace(original, fix)
                            changed = True
                        tos = post.get("text_on_screen") or {}
                        tos_text = tos.get("text", "")
                        if original in tos_text:
                            tos["text"] = tos_text.replace(original, fix)
                            post["text_on_screen"] = tos
                            changed = True
                        revised_posts.append(post)
                    else:
                        revised_posts.append(post)
                pc["posts"] = revised_posts

            if changed:
                flag["status"] = "applied"
                applied_fixes.append({
                    "line": original,
                    "rule": flag.get("rule", ""),
                    "confidence": flag.get("confidence", ""),
                    "suggestion": flag.get("suggestion", ""),
                    "fix": fix,
                })

        return platform_content, applied_fixes

    def _revise_draft_with_recommendations(self, adapter, card, draft,
                                            platform_content, recommendations,
                                            business_slug, round_num):
        """T9.5: Send alignment recommendations back to the Writer for revision.
        Returns updated platform_content."""
        from pipeline import DRAFT_SCHEMA
        from config_loader import load_all, ConfigError
        from context_assembly import assemble_module_context

        pc_text = json.dumps(platform_content, indent=2)
        recs_text = "\n".join(f"- {r}" for r in recommendations)

        try:
            config = load_all(self.config_dir)
            business = config["business"]
        except ConfigError:
            business = {"business": {"name": ""}, "audience_description": ""}

        module_vars, _module_prov = assemble_module_context(
            "draft/generate_v3.md", business_slug,
            dynamic={"treatment.format_name": draft.get("format", "")},
            db_path=self.db_path, modules_dir=self.modules_dir,
            prompts_dir=self.prompts_dir,
        )

        try:
            result = adapter.complete(
                prompt_file="draft/generate_v3.md",
                variables={
                    "business_name": business.get("business", {}).get("name", ""),
                    "audience_description": business.get("audience_description", ""),
                    "origin": card["origin"],
                    "format_name": draft.get("format", ""),
                    "scope": draft.get("scope", ""),
                    "idea": card["idea"],
                    "hook_options": "\n".join(f"- {h}" for h in json.loads(card.get("hook_options") or "[]")),
                    "grounding_sources": "(same as original draft)",
                    "capture_material": "(none)",
                    "previous_draft": pc_text[:6000],
                    "revision_feedback": f"[AI review round {round_num}] {recs_text}",
                    **module_vars,
                },
                schema=DRAFT_SCHEMA,
                backend="drafter",
                context=f"AI review revision round {round_num} for draft {draft['id']}",
                business_slug=business_slug,
                profile="drafter",
            )
            return result.get("platform_content", platform_content)
        except Exception:
            # If revision fails, return the original — the human will catch it
            return platform_content

    def run_assembler_chain(self, draft_id: int, card_id: int, business_slug: str):
        """Assembler stage: VO → media plan → media exec → edit plan → render.

        VO is the master timeline — it generates first so the media plan sees
        real durations and can plan coverage. Card state: assembling →
        asset_ready | assembly_failed.
        """
        from pipeline import PipelineStore
        store = PipelineStore(db_path=self.db_path)

        store.update_card_state(card_id, "assembling")

        try:
            self._step_fanout(draft_id, card_id, business_slug, store)
            self._step_vo(draft_id, card_id, business_slug, store)
            self._step_media_plan(draft_id, card_id, business_slug, store)
            self._step_media_exec(draft_id, card_id, business_slug, store)
            self._step_edit_plan(draft_id, card_id, business_slug, store)
            self._step_render(draft_id, card_id, business_slug, store)

            # Success — card is ready for asset review
            store.update_card_state(card_id, "asset_ready")

        except Exception as e:
            error_msg = str(e)[:500]
            step = self._identify_failed_step(e)
            store.update_card_state(
                card_id,
                "assembly_failed",
                production_error={"step": step, "error": error_msg},
            )

    def _step_vo(self, draft_id: int, card_id: int, business_slug: str, store):
        """Generate per-frame VO segments before media planning.

        VO is the master timeline. This step runs after fan-out (which creates
        asset rows) and before media plan (which needs real durations to plan
        visual coverage). For each asset with spoken content, generate one TTS
        call per post/frame, measure durations, and store on the asset row.
        """
        from vo_generator import VOGenerator, VOGenerationError
        from pipeline import PipelineStore

        assets = store.list_assets(draft_id)
        if not assets:
            return

        config = None
        try:
            from config_loader import load_all, ConfigError
            config = load_all(self.config_dir)
        except ConfigError:
            config = None

        vo_gen = VOGenerator(
            db_path=self.db_path,
            models_config=config.get("models", {}) if config else {},
        )

        for asset in assets:
            # Only generate VO for formats that have spoken content (reels, story_series)
            variant = asset.get("variant_type", "")
            if variant not in ("reel", "story_series"):
                continue

            # Skip if VO segments already exist for this asset
            existing = store.get_vo_segments(asset["id"])
            if existing:
                continue

            posts = json.loads(asset.get("posts") or "[]")
            if not posts:
                continue

            try:
                result = vo_gen.generate_vo_per_frame(
                    asset_id=asset["id"],
                    posts=posts,
                    business_slug=business_slug,
                )
                store.save_vo_segments(asset["id"], json.dumps(result["segments"]))
            except VOGenerationError as e:
                # Spoken Writer frames make VO mandatory. Continuing would create
                # a false-green silent reel and violate the approved contract.
                raise RuntimeError(
                    f"Complete voice-over generation failed for asset {asset['id']}: {e}"
                ) from e

    def _step_media_plan(self, draft_id: int, card_id: int, business_slug: str, store):
        """Plan and acquire media through the same service used by the UI."""
        from services.media_planning import MediaPlanningService

        asset = store.get_asset_by_draft(draft_id)
        if not asset:
            raise RuntimeError(f"No asset found for draft {draft_id}")

        result = MediaPlanningService(
            db_path=store.db_path,
            config_dir=self.config_dir,
            modules_dir=self.modules_dir,
            prompts_dir=self.prompts_dir,
        ).generate_for_asset(
            asset_id=asset["id"],
            business_slug=business_slug,
            store=store,
        )
        if not result.ok:
            raise RuntimeError(
                result.payload.get("error")
                or result.payload.get("message")
                or "Media planning failed"
            )
        store._set_step_data(draft_id, "media_plan_result", result.payload)

    def _step_media_exec(self, draft_id: int, card_id: int, business_slug: str, store):
        """Verify the shared media service completed acquisition."""
        plan_data = store._get_step_data(draft_id, "media_plan_result")
        if not plan_data:
            raise RuntimeError(f"No media plan found for draft {draft_id} — run media_plan first")
        if plan_data.get("results") and not plan_data.get("ready_to_render"):
            raise RuntimeError("Media plan completed without any render-ready ingredients")

    def _step_edit_plan(self, draft_id: int, card_id: int, business_slug: str, store):
        """Generate the edit plan through the same service used by the UI."""
        from services.edit_planning import EditPlanningService

        asset = store.get_asset_by_draft(draft_id)
        if not asset:
            raise RuntimeError(f"No asset found for draft {draft_id}")

        result = EditPlanningService(
            db_path=store.db_path,
            config_dir=self.config_dir,
            modules_dir=self.modules_dir,
            prompts_dir=self.prompts_dir,
        ).generate_for_asset(
            asset_id=asset["id"],
            business_slug=business_slug,
            store=store,
        )
        if not result.ok:
            raise RuntimeError(
                result.payload.get("error")
                or result.payload.get("message")
                or "Edit planning failed"
            )
        store._set_step_data(draft_id, "edit_plan_result", result.payload)

    def _step_render(self, draft_id: int, card_id: int, business_slug: str, store):
        """Render through the same Render/Review Service used by the UI."""
        from services.render_review import RenderReviewService

        asset = store.get_asset_by_draft(draft_id)
        if not asset:
            raise RuntimeError(f"No asset found for draft {draft_id}")

        edit_plans = store.list_edit_plans(asset["id"])
        if not edit_plans:
            raise RuntimeError(f"No edit plan found for asset {asset['id']}")

        result = RenderReviewService(
            db_path=store.db_path,
            config_dir=self.config_dir,
        ).render_for_asset(
            asset_id=asset["id"],
            plan_id=edit_plans[0]["id"],
            business_slug=business_slug,
            store=store,
        )
        if not result.ok:
            raise RuntimeError(
                result.payload.get("error")
                or result.payload.get("message")
                or "Render failed"
            )

    def _step_draft(self, card_id: int, business_slug: str, store) -> int:
        """Step 1: Generate draft from the approved card. Returns draft_id.
        T9.3: Uses generate_v3.md prompt — Writer produces per-platform content."""
        from config_loader import load_all, ConfigError
        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import DRAFT_SCHEMA
        from context_assembly import assemble_module_context

        card = store.get_idea_card(card_id)
        if not card:
            raise RuntimeError(f"Card {card_id} not found")

        treatment = json.loads(card.get("treatment") or "{}")
        hook_options = json.loads(card.get("hook_options") or "[]")
        format_name = treatment.get("format", {}).get("format_name", "")
        scope = treatment.get("scope", {}).get("type", "")

        # Load config
        try:
            config = load_all(self.config_dir)
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            raise RuntimeError(f"Config error: {e}")

        # T9.3: Load modules for the v3 prompt (per-platform content)
        module_vars, module_prov = assemble_module_context(
            "draft/generate_v3.md", business_slug,
            dynamic={"treatment.format_name": format_name},
            db_path=self.db_path, modules_dir=self.modules_dir,
        )

        # Load capture material
        capture_text = ""
        uploads = json.loads(card.get("capture_uploads") or "[]")
        if uploads:
            from materials import MaterialsIntake
            intake = MaterialsIntake(self.db_path)
            for mid in uploads:
                mat = intake.get_material(mid)
                if mat and mat.get("normalized_content"):
                    capture_text += mat["normalized_content"] + "\n\n"
                elif mat and mat.get("raw_content"):
                    capture_text += mat["raw_content"] + "\n\n"

        # T8.5: Assemble grounding_sources
        source_ref_ids = json.loads(card.get("source_refs") or "[]")
        grounding_sources = "(no sources cited on this card)"
        if source_ref_ids:
            resolved_sources = store.resolve_source_refs(business_slug, source_ref_ids)
            if resolved_sources:
                source_blocks = []
                for src in resolved_sources:
                    block = f"### [S{src['id']}] {src['title']}"
                    if src.get("url"):
                        block += f"\nURL: {src['url']}"
                    content = src.get("content") or ""
                    summary = src.get("summary") or ""
                    if content:
                        block += f"\n\n{content}"
                    elif summary:
                        block += f"\n\n{summary}\n\n(summary only — full content not available)"
                    else:
                        block += "\n\n(no content or summary available)"
                    source_blocks.append(block)
                grounding_sources = "\n\n---\n\n".join(source_blocks)

        # Revision context
        existing = None
        for d in store.list_drafts(business_slug):
            if d["idea_card_id"] == card_id:
                existing = d
                break

        if existing:
            # T9.3: For revision context, show previous platform_content as text
            prev_pc = json.loads(existing.get("platform_content") or "[]")
            if prev_pc:
                prev_lines = []
                for pc in prev_pc:
                    prev_lines.append(f"### {pc.get('platform', '')} ({pc.get('variant_type', '')})")
                    prev_lines.append(pc.get("content", ""))
                    for p in pc.get("posts", []):
                        prev_lines.append(f"  - {p}")
                previous_draft = "\n".join(prev_lines)
            else:
                previous_draft = existing["draft_text"] or ""
            if len(previous_draft) > 6000:
                cut = previous_draft.rfind('\n\n', 0, 6000)
                if cut > 3000:
                    previous_draft = previous_draft[:cut] + "\n\n[...truncated]"
                else:
                    previous_draft = previous_draft[:6000] + "\n\n[...truncated]"
            feedback_entries = store.list_feedback(business_slug, draft_id=existing["id"])
            revision_feedback = "\n".join(
                f"[{e.get('feedback_type','')} w{e.get('weight',1)}] {e.get('feedback_text','')}"
                for e in feedback_entries
            )
        else:
            previous_draft = "(first draft — no previous version)"
            revision_feedback = "(first draft — no previous version)"

        adapter = LLMAdapter(models_config, db_path=self.db_path, prompts_dir=self.prompts_dir)

        result = adapter.complete(
            prompt_file="draft/generate_v3.md",
            variables={
                "business_name": business["business"]["name"],
                "audience_description": business.get("audience_description", ""),
                "origin": card["origin"],
                "format_name": format_name,
                "scope": scope,
                "idea": card["idea"],
                "hook_options": "\n".join(f"- {h}" for h in hook_options),
                "grounding_sources": grounding_sources,
                "capture_material": capture_text[:2000] if capture_text else "(none)",
                "previous_draft": previous_draft,
                "revision_feedback": revision_feedback,
                **module_vars,
            },
            schema=DRAFT_SCHEMA,
            backend="drafter",
            context=f"Auto-chain draft for card {card_id} ({card['origin']}, {format_name}) | module_ctx: {module_prov}",
            business_slug=business_slug,
            profile="drafter",
        )

        # T9.3: Save draft with platform_content
        platform_content = result.get("platform_content", [])
        draft_text_summary = platform_content[0].get("content", "") if platform_content else ""

        if existing:
            store.save_draft_content(
                existing["id"],
                draft_text_summary,
                result["visual_direction"],
                result["self_audit_flags"],
                platform_content=platform_content,
            )
            draft_id = existing["id"]
        else:
            draft_id = store.create_draft(
                business_slug=business_slug,
                idea_card_id=card_id,
                origin=card["origin"],
                format_name=format_name,
                scope=scope,
            )
            store.save_draft_content(
                draft_id,
                draft_text_summary,
                result["visual_direction"],
                result["self_audit_flags"],
                platform_content=platform_content,
            )

        # Draft is saved — writer chain stops here for Gate 2 review.
        # The assembler chain (fan-out) triggers when the operator ships.

        return draft_id

    def _step_fanout(self, draft_id: int, card_id: int, business_slug: str, store):
        """T9.4: Assembler is media-only. Reads platform_content from the approved
        draft and creates assets directly — zero LLM text calls.

        The Writer already produced complete per-platform text. The Assembler
        just creates asset rows from platform_content (mechanical, no LLM).
        Media generation happens separately (Gate 3 review → generate visuals).
        """
        draft = store.get_draft(draft_id)
        if not draft:
            raise RuntimeError(f"Draft {draft_id} not found")

        platform_content = json.loads(draft.get("platform_content") or "[]")
        if not platform_content:
            raise RuntimeError("Draft has no platform_content — cannot assemble")

        # Create one asset per platform_content entry — no LLM calls
        for pc in platform_content:
            platform_name = pc.get("platform", "")
            variant_type = pc.get("variant_type", "single_post")
            content = pc.get("content", "")
            posts = pc.get("posts", [])
            image_prompts = pc.get("image_prompts", [])

            # Idempotency: skip if asset already exists for this platform
            existing_assets = store.list_assets(draft_id)
            existing_platforms = {a["platform"] for a in existing_assets
                                  if a.get("asset_state") != "killed"}
            if platform_name in existing_platforms:
                continue

            store.create_asset(
                business_slug=business_slug,
                draft_id=draft_id,
                platform=platform_name,
                variant_type=variant_type,
                content=content,
                image_prompts=image_prompts,
                posts=posts,
                native=True,  # All platform_content is native (Writer wrote it)
            )

    def _identify_failed_step(self, error: Exception) -> str:
        """Identify which step failed from the exception traceback."""
        tb = traceback.format_exc()
        if "_step_vo" in tb:
            return "vo_generation"
        elif "_step_media_plan" in tb:
            return "media_plan"
        elif "_step_media_exec" in tb:
            return "media_execution"
        elif "_step_edit_plan" in tb:
            return "edit_plan"
        elif "_step_render" in tb:
            return "render"
        elif "_step_draft" in tb:
            return "draft_generation"
        elif "_step_fanout" in tb:
            return "fan_out"
        else:
            return "unknown"


# ── T9.1: Format Guide metadata parsers (mechanical, no keyword heuristics) ──
# These replace the charter-violating _resolve_format_platforms (regex parser)
# and _determine_variant_type (keyword heuristic). Per AMENDMENT-007, the
# format + platform set are locked from the treatment at Gate 1 — no code
# re-derives them with keyword matching or regex parsing. These functions
# parse the Format Guide entry's STRUCTURED metadata fields (e.g.
# "- **Platforms:** X, Instagram") mechanically, the same way you'd parse a
# YAML field — no judgment, no pattern matching on content.


def _get_platforms_from_format_entry(ms, business_slug: str, format_name: str,
                                     business_config: dict = None) -> list:
    """Resolve platforms for a format from the Format Guide entry's structured
    '- **Platforms:**' field. Falls back to business config platforms (config-driven)
    if the entry or line is not found.
    """
    if not format_name:
        return []
    try:
        entry = ms.get_entry(business_slug, "format-guide", "Formats", format_name)
        if not entry:
            if business_config:
                return [p["name"] for p in business_config.get("platforms", [])]
            return []
        for line in entry.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- **Platforms:**"):
                raw = stripped.split("**Platforms:**", 1)[1].strip()
                return [p.strip() for p in raw.split(",") if p.strip()]
        if business_config:
            return [p["name"] for p in business_config.get("platforms", [])]
        return []
    except Exception:
        if business_config:
            return [p["name"] for p in business_config.get("platforms", [])]
        return []


def _get_variant_type_from_format_entry(ms, business_slug: str, format_name: str) -> str | None:
    """Resolve variant_type for a format from the Format Guide entry's structured
    '- **Variant type:**' field. Returns None if the field is not present
    (T9.2 adds this field to the Format Guide schema). The caller falls back
    to 'single_post' when None.
    """
    if not format_name:
        return None
    try:
        entry = ms.get_entry(business_slug, "format-guide", "Formats", format_name)
        if not entry:
            return None
        for line in entry.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- **Variant type:**"):
                return stripped.split("**Variant type:**", 1)[1].strip()
        return None
    except Exception:
        return None


def enqueue_writer_chain(db_path: str, config_dir: str, modules_dir: str, prompts_dir: str,
                         card_id: int, business_slug: str):
    """Enqueue the WRITER chain for a card: draft generation only.
    Card state: writing → draft_ready | writer_failed."""
    chain = ProductionChain(
        db_path=db_path,
        config_dir=config_dir,
        modules_dir=modules_dir,
        prompts_dir=prompts_dir,
    )
    thread = threading.Thread(
        target=chain.run_writer_chain,
        args=(card_id, business_slug),
        daemon=True,
        name=f"writer_chain_{card_id}",
    )
    thread.start()
    return thread


def enqueue_assembler_chain(db_path: str, config_dir: str, modules_dir: str, prompts_dir: str,
                            draft_id: int, card_id: int, business_slug: str):
    """Enqueue the ASSEMBLER chain for a shipped draft: fan-out + assets.
    Card state: assembling → asset_ready | assembly_failed."""
    chain = ProductionChain(
        db_path=db_path,
        config_dir=config_dir,
        modules_dir=modules_dir,
        prompts_dir=prompts_dir,
    )
    thread = threading.Thread(
        target=chain.run_assembler_chain,
        args=(draft_id, card_id, business_slug),
        daemon=True,
        name=f"assembler_chain_{card_id}",
    )
    thread.start()
    return thread


# ── Legacy alias for backward compatibility (tests) ──

def enqueue_chain(db_path: str, config_dir: str, modules_dir: str, prompts_dir: str,
                 card_id: int, business_slug: str):
    """Legacy alias — enqueue the writer chain. Tests reference this."""
    return enqueue_writer_chain(db_path, config_dir, modules_dir, prompts_dir,
                                card_id, business_slug)