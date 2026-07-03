#!/usr/bin/env python3
"""
ViralFactory — Weekly Proposal Job (M5: T5.1)

Reads published results + Feedback Log + nightly performance notes →
generates module improvement proposals with evidence + exact diff.
Proposals land in the async gate queue for operator approval.

Designed to run via cron weekly. Uses the LLM adapter (temperature 0)
for the proposal generation — never keyword heuristics.

Usage:
    python3 cron_generate_proposals.py [--business slug]

Exit codes:
    0 — success
    1 — configuration error
"""

import sys
import os
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from config_loader import load_all, ConfigError
from pipeline import PipelineStore
from proposal_store import ProposalStore
from llm_adapter import LLMAdapter
from provenance import ProvenanceLog
from cache import ContentHashCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger("viralfactory.cron.proposals")


PROPOSAL_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["proposals"],
    "properties": {
        "proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["target_module", "target_section", "proposal_type",
                             "evidence", "change_description", "exact_diff", "rationale"],
                "properties": {
                    "target_module": {"type": "string"},
                    "target_section": {"type": "string"},
                    "proposal_type": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "change_description": {"type": "string"},
                    "exact_diff": {"type": "string"},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "string"},
                },
            },
        },
    },
}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate weekly module improvement proposals")
    parser.add_argument("--business", type=str, default=None, help="Business slug")
    parser.add_argument("--config-dir", type=str, default="config", help="Config directory")
    parser.add_argument("--db-path", type=str, default="data/viralfactory.db", help="Database path")
    parser.add_argument("--modules-dir", type=str, default="modules", help="Modules directory")
    args = parser.parse_args()

    # Load config
    try:
        config = load_all(args.config_dir)
        models_config = config["models"]
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        sys.exit(1)

    business_slug = args.business
    if not business_slug:
        try:
            business_slug = config["business"]["business"]["slug"]
        except (KeyError, ConfigError):
            logger.error("Could not determine business slug from config")
            sys.exit(1)

    # Initialize stores
    pipeline = PipelineStore(db_path=args.db_path)
    proposals = ProposalStore(db_path=args.db_path)
    provenance = ProvenanceLog(db_path=args.db_path)
    cache = ContentHashCache(db_path=args.db_path)

    # Gather inputs
    logger.info(f"Gathering inputs for business '{business_slug}'")

    # Feedback log
    feedback = pipeline.list_feedback(business_slug)
    feedback_text = "\n".join([
        f"[{f['feedback_type']} w={f['weight']}] {f['feedback_text']}"
        for f in feedback[-50:]  # Last 50 entries
    ])

    # Performance stats
    stats = pipeline.get_pipeline_stats(business_slug)
    performance_notes = json.dumps(stats, indent=2)

    # Published results
    all_drafts = pipeline.list_drafts(business_slug)
    published_results = []
    for draft in all_drafts:
        if draft["draft_state"] == "shipped":
            published_results.append({
                "draft_id": draft["id"],
                "origin": draft.get("origin"),
                "format": draft.get("format"),
                "scope": draft.get("scope"),
            })
    published_text = json.dumps(published_results, indent=2)

    # Module versions
    module_versions = {}
    modules_dir = os.path.join(args.modules_dir, business_slug)
    if os.path.isdir(modules_dir):
        for fname in os.listdir(modules_dir):
            if fname.endswith(".md"):
                module_versions[fname] = os.path.getmtime(
                    os.path.join(modules_dir, fname)
                )

    # Build prompt variables
    prompt_vars = {
        "published_results": published_text or "(no published pieces yet)",
        "feedback_log": feedback_text or "(no feedback entries yet)",
        "performance_notes": performance_notes,
        "module_versions": json.dumps(module_versions, indent=2),
    }

    # Generate proposals via LLM
    logger.info("Generating proposals via LLM...")
    adapter = LLMAdapter(
        models_config=models_config,
        provenance=provenance,
        cache=cache,
        db_path=args.db_path,
        business_slug=business_slug,
    )

    try:
        result = adapter.complete(
            prompt_file="prompts/learning/generate_proposals_v1.md",
            variables=prompt_vars,
            schema=PROPOSAL_OUTPUT_SCHEMA,
            backend="default",
            provenance_meta={"job": "weekly_proposals"},
        )
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        sys.exit(0)  # Don't fail the cron — retry next week

    proposal_list = result.get("proposals", [])
    if not proposal_list:
        logger.info("No proposals generated this week — nothing worth proposing.")
        sys.exit(0)

    # Store proposals
    created = 0
    for p in proposal_list:
        try:
            proposals.create_proposal(
                business_slug=business_slug,
                target_module=p["target_module"],
                target_section=p["target_section"],
                proposal_type=p["proposal_type"],
                evidence=p["evidence"],
                change_description=p["change_description"],
                exact_diff=p["exact_diff"],
                rationale=p["rationale"],
                confidence=p.get("confidence", "medium"),
            )
            created += 1
        except Exception as e:
            logger.warning(f"Failed to store proposal: {e}")

    logger.info(f"Generated {len(proposal_list)} proposals, {created} stored successfully.")
    sys.exit(0)


if __name__ == "__main__":
    main()