"""
VF-CW-009 — Component Workbench UI service.

Provides the data assembly for the server-rendered workbench surface.
The template (templates/component_workbench.html) renders candidates
grouped by category and semantic role with playable/fullscreen previews,
descriptive labels, versions, provenance, rights/cost/evidence age,
feedback, valid Select/Approve/Reject/Regenerate actions, and a
persistent structured blocker/readiness summary.

Covers fresh/generating/partial/available/approved/rejected/failed/
stale/superseded/unavailable/rights-blocked/cost-blocked/complete states
in plain language. No false greens, raw technical states, dead actions,
or hidden materially used choices.
"""

from __future__ import annotations

import json
import os
from typing import Optional


# Plain-language state labels (no raw technical states to the operator)
STATE_LABELS = {
    "generating": "Generating…",
    "available": "Ready to review",
    "approved": "Approved",
    "rejected": "Rejected",
    "superseded": "Replaced by newer version",
    "stale": "Out of date — needs regeneration",
    "failed": "Generation failed",
    "planning_components": "Planning components…",
    "generating_components": "Generating components…",
    "component_review_required": "Your review needed",
    "manifest_ready": "Ready to freeze",
    "composition_planning": "Planning composition…",
    "composition_review_required": "Review the composition plan",
    "composition_ratified": "Composition ratified",
    "assembling": "Assembling…",
    "final_review_required": "Final review needed",
    "gate3_approved": "Approved at Gate 3",
    "blocked": "Blocked",
    "failed": "Failed",
}

# Category labels (from config, but with fallback)
CATEGORY_LABELS = {
    "narration": "Narration",
    "visual_media": "Visual media",
    "soundtrack": "Soundtrack",
    "sound_effects": "Sound effects",
    "typography": "Typography",
    "graphics": "Graphics",
}

# Readiness level for each state (for the summary)
READY = "ready"
NEEDS_ACTION = "needs_action"
BLOCKED = "blocked"
INCOMPLETE = "incomplete"


class WorkbenchDataService:
    """Assembles the data for the Component Workbench UI.

    Reads candidates, decisions, requirements, and session state,
    then groups them by category with plain-language labels and
    readiness summaries. No false greens.
    """

    def __init__(self, db_path: str = "data/viralfactory.db", config_dir: str = "config"):
        self.db_path = db_path
        self.config_dir = config_dir

    def build_workbench_view(
        self,
        business_slug: str,
        production_session_id: int,
    ) -> dict:
        """Build the complete workbench view data for rendering.

        Returns:
        {
            "session": {...},
            "categories": [
                {
                    "key": "narration",
                    "label": "Narration",
                    "required": true,
                    "roles": [
                        {
                            "role": "full_take",
                            "label": "Full voice take",
                            "required": true,
                            "candidates": [...],
                            "status_summary": "1 approved, 1 available",
                            "readiness": "ready",
                        }
                    ],
                    "readiness": "ready",
                }
            ],
            "overall_readiness": "ready",
            "blockers": [...],
            "freeze_enabled": false,
        }
        """
        from services.production_orchestrator import ProductionSessionService
        from services.candidate_store import CandidateStore
        from services.component_requirements import (
            ComponentCategoryRegistry,
            ComponentRequirementsValidator,
        )

        session_svc = ProductionSessionService(db_path=self.db_path)
        candidate_store = CandidateStore(db_path=self.db_path)
        registry = ComponentCategoryRegistry(config_dir=self.config_dir)

        # Get the session
        session = session_svc.get_session(business_slug, production_session_id)

        # Get current requirements
        from services.component_requirements import ComponentRequirementsStore
        req_store = ComponentRequirementsStore(db_path=self.db_path)
        current_reqs = req_store.get_current_requirements(business_slug, production_session_id)

        # Get all current (non-superseded) candidates
        all_candidates = candidate_store.get_current_versions(
            business_slug, production_session_id
        )

        # Group candidates by category and role
        candidates_by_cat = {}
        for c in all_candidates:
            cat = c["category"]
            role = c["role"]
            if cat not in candidates_by_cat:
                candidates_by_cat[cat] = {}
            if role not in candidates_by_cat[cat]:
                candidates_by_cat[cat][role] = []
            candidates_by_cat[cat][role].append(self._enrich_candidate(c))

        # Build category views
        categories_view = []
        blockers = []

        # If we have requirements, use them; otherwise use format overrides
        req_categories = {}
        if current_reqs:
            for cat_entry in current_reqs.get("categories", []):
                req_categories[cat_entry["category"]] = cat_entry
        else:
            # Fall back to format overrides from the registry
            format_name = session.get("format", "")
            required_cats = registry.get_required_categories(format_name)
            for cat_key in required_cats:
                req_categories[cat_key] = {"category": cat_key, "required": True, "roles": []}

        # Get all categories from registry
        all_cats = registry.categories
        for cat_key, cat_def in all_cats.items():
            cat_req = req_categories.get(cat_key, {})
            cat_candidates = candidates_by_cat.get(cat_key, {})

            roles_view = []
            cat_readiness = READY
            cat_required = cat_req.get("required", False)

            for role_def in cat_def.get("roles", []):
                role_key = role_def["key"]
                role_candidates = cat_candidates.get(role_key, [])
                role_req = None
                if cat_req:
                    for r in cat_req.get("roles", []):
                        if r["role"] == role_key:
                            role_req = r
                            break

                role_required = role_req.get("required", False) if role_req else False
                # A role is only a blocker if it's required, or if the category
                # is required AND the role doesn't allow explicit none
                role_none_allowed = role_def.get("none_allowed", False)
                is_blocking = role_required or (cat_required and not role_none_allowed)
                status_summary, role_readiness = self._summarize_role(
                    role_candidates, is_blocking
                )

                if role_readiness in (BLOCKED, INCOMPLETE):
                    if is_blocking:
                        if cat_readiness != BLOCKED:
                            cat_readiness = role_readiness
                        blockers.append({
                            "category": cat_key,
                            "role": role_key,
                            "message": status_summary,
                        })

                roles_view.append({
                    "role": role_key,
                    "label": role_def.get("label", role_key),
                    "description": role_def.get("description", ""),
                    "required": role_required,
                    "candidates": role_candidates,
                    "status_summary": status_summary,
                    "readiness": role_readiness,
                })

            # If category has candidates but no requirements, show them
            if not cat_req and cat_candidates:
                cat_required = False

            # Skip empty optional categories with no candidates
            if not cat_required and not cat_candidates:
                continue

            categories_view.append({
                "key": cat_key,
                "label": cat_def.get("label", cat_key),
                "required": cat_required,
                "roles": roles_view,
                "readiness": cat_readiness,
            })

        # Compute overall readiness
        overall_readiness = READY
        for cat in categories_view:
            if cat["readiness"] == BLOCKED:
                overall_readiness = BLOCKED
                break
            elif cat["readiness"] == INCOMPLETE:
                overall_readiness = INCOMPLETE

        # Freeze is enabled only when all required categories are ready
        freeze_enabled = overall_readiness == READY and len(blockers) == 0

        return {
            "session": session,
            "categories": categories_view,
            "overall_readiness": overall_readiness,
            "blockers": blockers,
            "freeze_enabled": freeze_enabled,
            "state_label": STATE_LABELS.get(
                session["current_state"], session["current_state"]
            ),
        }

    def _enrich_candidate(self, candidate: dict) -> dict:
        """Enrich a candidate dict with parsed JSON fields and labels."""
        c = dict(candidate)
        # Parse JSON fields
        for field in ["beat_refs_json", "measurement_json",
                       "source_provenance_json", "generation_provenance_json",
                       "rights_snapshot_json"]:
            key = field.replace("_json", "")
            val = c.get(field)
            if val and isinstance(val, str):
                try:
                    c[key] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    c[key] = None
            elif val is None:
                c[key] = None
            else:
                c[key] = val

        # Add state label
        c["status_label"] = STATE_LABELS.get(c["status"], c["status"])

        # Add readable provenance
        gen_prov = c.get("generation_provenance") or {}
        c["voice_identity"] = gen_prov.get("voice_identity", {})
        c["error"] = gen_prov.get("error")

        return c

    def _summarize_role(
        self, candidates: list[dict], required: bool
    ) -> tuple[str, str]:
        """Summarize the status of a role's candidates.

        Returns (summary_text, readiness_level).
        readiness_level is one of: ready, needs_action, blocked, incomplete
        """
        if not candidates:
            if required:
                return "No candidates generated yet", INCOMPLETE
            else:
                return "No candidates needed", READY

        approved = [c for c in candidates if c["status"] == "approved"]
        available = [c for c in candidates if c["status"] == "available"]
        generating = [c for c in candidates if c["status"] == "generating"]
        failed = [c for c in candidates if c["status"] == "failed"]
        rejected = [c for c in candidates if c["status"] == "rejected"]

        parts = []
        if approved:
            parts.append(f"{len(approved)} approved")
        if available:
            parts.append(f"{len(available)} ready to review")
        if generating:
            parts.append(f"{len(generating)} generating")
        if failed:
            parts.append(f"{len(failed)} failed")
        if rejected:
            parts.append(f"{len(rejected)} rejected")

        summary = ", ".join(parts) if parts else "No candidates"

        # Determine readiness
        if approved:
            return summary, READY
        elif failed and not available and not generating:
            return summary, BLOCKED
        elif generating:
            return summary, INCOMPLETE
        elif available:
            return summary, NEEDS_ACTION
        else:
            return summary, INCOMPLETE