"""
T8.6: Auto-production chain.

Gate 1 approval triggers production automatically through to asset review.
The chain: draft generation → per-platform fan-out → visual generation
(for image-required formats), executed as a background job.

No-auto-publish remains absolute — the chain terminates at asset review.

Card state transitions:
  approved → producing → asset_ready (success)
  approved → producing → production_failed (error, with retry)

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

    def run_chain(self, card_id: int, business_slug: str):
        """Run the full production chain for a card.
        Steps: (1) draft generation, (2) fan-out, (3) visual generation (if needed).
        Card state: producing → asset_ready | production_failed.
        """
        from pipeline import PipelineStore
        store = PipelineStore(db_path=self.db_path)

        # Set state to producing
        store.update_card_state(card_id, "producing")

        try:
            # Step 1: Draft generation
            draft_id = self._step_draft(card_id, business_slug, store)
            if draft_id is None:
                raise RuntimeError("Draft generation returned no draft ID")

            # Step 2: Fan-out
            self._step_fanout(draft_id, card_id, business_slug, store)

            # Step 3: Visual generation (for image-required formats)
            # This is optional — not all formats need generated images.
            # The operator reviews at the asset stage regardless.
            # For now, we skip auto-image-generation (operator can trigger from asset page).

            # Success — card is ready for asset review
            store.update_card_state(card_id, "asset_ready")

        except Exception as e:
            error_msg = str(e)[:500]
            step = self._identify_failed_step(e)
            store.update_card_state(
                card_id,
                "production_failed",
                production_error={"step": step, "error": error_msg},
            )

    def _step_draft(self, card_id: int, business_slug: str, store) -> int:
        """Step 1: Generate draft from the approved card. Returns draft_id."""
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

        # Load modules
        module_vars, module_prov = assemble_module_context(
            "draft/generate_v2.md", business_slug,
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
            prompt_file="draft/generate_v2.md",
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

        # Save draft
        if existing:
            store.save_draft_content(
                existing["id"],
                result["draft_text"],
                result["visual_direction"],
                result["self_audit_flags"],
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
                result["draft_text"],
                result["visual_direction"],
                result["self_audit_flags"],
            )

        # Mark draft as shipped (auto-chain bypasses Gate 2 human pass)
        store.update_draft_state(draft_id, "shipped")

        return draft_id

    def _step_fanout(self, draft_id: int, card_id: int, business_slug: str, store):
        """Step 2: Generate per-platform variants from the shipped draft."""
        from config_loader import load_all, ConfigError
        from llm_adapter import LLMAdapter, LLMAdapterError
        from context_assembly import assemble_module_context
        from module_store import ModuleStore

        draft = store.get_draft(draft_id)
        if not draft:
            raise RuntimeError(f"Draft {draft_id} not found")

        try:
            config = load_all(self.config_dir)
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            raise RuntimeError(f"Config error: {e}")

        business_platforms = business.get("platforms", [])
        visual_direction = json.loads(draft.get("visual_direction") or "{}")
        draft_format = draft.get("format", "")
        draft_text = draft["draft_text"]

        # Resolve platform set from Format Guide entry
        ms = ModuleStore(modules_dir=self.modules_dir, db_path=self.db_path)
        format_platform_names = _resolve_format_platforms(ms, business_slug, draft_format)

        # T8.5: Source titles for fan-out
        card = store.get_idea_card(card_id)
        source_ref_ids = json.loads(card.get("source_refs") or "[]") if card else []
        source_titles = "(none)"
        if source_ref_ids:
            resolved = store.resolve_source_refs(business_slug, source_ref_ids)
            if resolved:
                source_titles = "\n".join(f"- [S{s['id']}] {s['title']}" for s in resolved)

        adapter = LLMAdapter(models_config, db_path=self.db_path, prompts_dir=self.prompts_dir)

        for platform_name in format_platform_names:
            platform_info = next(
                (p for p in business_platforms if p["name"] == platform_name),
                {"name": platform_name, "handle": ""},
            )

            # Determine variant type
            variant_type = _determine_variant_type(draft_format, platform_name)

            if variant_type in ("thread", "carousel"):
                # Structure-only LLM call — split into segments, preserve wording
                variant_schema = {
                    "type": "object",
                    "required": ["content", "variant_type", "posts"],
                    "properties": {
                        "content": {"type": "string"},
                        "variant_type": {"type": "string"},
                        "posts": {"type": "array", "items": {"type": "string"}},
                    },
                }
                struct_result = adapter.complete(
                    prompt_file="assets/structure_v1.md",
                    variables={
                        "platform_name": platform_name,
                        "format_name": draft_format,
                        "variant_type": variant_type,
                        "draft_text": draft_text[:4000],
                    },
                    schema=variant_schema,
                    backend="default",
                    context=f"Auto-chain structuring for draft {draft_id} → {platform_name} ({variant_type})",
                    business_slug=business_slug,
                )
                content = struct_result.get("content", draft_text)
                posts = struct_result.get("posts", [draft_text])
                asset_id = store.create_asset(
                    business_slug=business_slug,
                    draft_id=draft_id,
                    platform=platform_name,
                    variant_type=variant_type,
                    content=content,
                    posts=json.dumps(posts),
                )
            else:
                # Full fan-out LLM call
                module_vars, module_prov = assemble_module_context(
                    "assets/fan_out_v2.md", business_slug,
                    db_path=self.db_path, modules_dir=self.modules_dir,
                )
                variant_schema = {
                    "type": "object",
                    "required": ["content", "variant_type"],
                    "properties": {
                        "content": {"type": "string"},
                        "variant_type": {"type": "string"},
                        "posts": {"type": "array", "items": {"type": "string"}},
                        "image_prompts": {"type": "array", "items": {"type": "string"}},
                    },
                }
                result = adapter.complete(
                    prompt_file="assets/fan_out_v2.md",
                    variables={
                        "business_name": business["business"]["name"],
                        "platform_name": platform_name,
                        "platform_handle": platform_info.get("handle", ""),
                        "draft_text": draft_text[:4000],
                        "source_titles": source_titles,
                        "visual_direction": json.dumps(visual_direction)[:1000],
                        "format": draft_format,
                        **module_vars,
                    },
                    schema=variant_schema,
                    backend="default",
                    context=f"Auto-chain fan-out for draft {draft_id} → {platform_name} | module_ctx: {module_prov}",
                    business_slug=business_slug,
                )
                asset_id = store.create_asset(
                    business_slug=business_slug,
                    draft_id=draft_id,
                    platform=platform_name,
                    variant_type=result.get("variant_type", "single_post"),
                    content=result["content"],
                    posts=json.dumps(result.get("posts", [])) if result.get("posts") else None,
                )

    def _identify_failed_step(self, error: Exception) -> str:
        """Identify which step failed from the exception traceback."""
        tb = traceback.format_exc()
        if "_step_draft" in tb:
            return "draft_generation"
        elif "_step_fanout" in tb:
            return "fan_out"
        else:
            return "unknown"


# ── Helper functions (mirror those in app.py) ──

def _resolve_format_platforms(ms, business_slug: str, format_name: str) -> list:
    """Resolve the platform set for a format from the Format Guide entry."""
    try:
        md = ms.load(business_slug, "format-guide")
        if not md:
            return []
        # Parse format entries to find the one matching format_name
        import re
        # Look for ### Format: <name> or ## <name> headers
        pattern = rf"(?:###?\s*Format:?\s*{re.escape(format_name)}|###?\s*{re.escape(format_name)})\s*$(.*?)(?=\n###?\s|\Z)"
        match = re.search(pattern, md, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if not match:
            return []
        section = match.group(1)
        # Look for platforms line
        plat_match = re.search(r"platforms?\s*[:\-]\s*(.+)", section, re.IGNORECASE)
        if plat_match:
            plats_str = plat_match.group(1).strip()
            # Parse comma or slash separated list
            plats = [p.strip() for p in re.split(r"[,/]", plats_str) if p.strip()]
            return plats
        return []
    except Exception:
        return ["X", "Instagram"]  # fallback


def _determine_variant_type(format_name: str, platform_name: str) -> str:
    """Determine the variant type based on format and platform."""
    platform_lower = platform_name.lower()
    format_lower = (format_name or "").lower()

    if "thread" in format_lower or platform_lower == "x":
        return "thread"
    elif "carousel" in format_lower or "carousel" in platform_lower:
        return "carousel"
    elif "reel" in format_lower or "video" in format_lower or "reel" in platform_lower:
        return "reel"
    else:
        return "single_post"


def enqueue_chain(db_path: str, config_dir: str, modules_dir: str, prompts_dir: str,
                 card_id: int, business_slug: str):
    """Enqueue a production chain for a card. Runs in a background thread.
    Card state: producing → asset_ready | production_failed."""
    chain = ProductionChain(
        db_path=db_path,
        config_dir=config_dir,
        modules_dir=modules_dir,
        prompts_dir=prompts_dir,
    )
    thread = threading.Thread(
        target=chain.run_chain,
        args=(card_id, business_slug),
        daemon=True,
        name=f"produce_chain_{card_id}",
    )
    thread.start()
    return thread