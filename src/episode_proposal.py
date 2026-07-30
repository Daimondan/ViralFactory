"""Prepare exact operator-gated proposals for a production format.

This module only reads proposal data from config and writes pending queue rows.
It never approves, edits modules, or changes a process registry status.
"""

from __future__ import annotations

from pathlib import Path

import yaml


_REQUIRED = {
    "target_module",
    "target_section",
    "proposal_type",
    "change_description",
    "exact_diff",
    "evidence",
    "rationale",
}


def load_episode_proposal_spec(config_dir: str, business_slug: str) -> dict:
    path = Path(config_dir) / "production_proposals.yaml"
    if not path.exists():
        raise ValueError(f"production proposal config not found: {path}")
    try:
        root = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"production proposal config is invalid: {path}") from exc
    spec = ((root.get("proposals") or {}).get(business_slug))
    if not isinstance(spec, dict):
        raise ValueError(f"no production proposal is configured for '{business_slug}'")
    for name, proposal in spec.items():
        if not isinstance(proposal, dict) or not _REQUIRED.issubset(proposal):
            raise ValueError(f"proposal '{name}' is incomplete")
        if not isinstance(proposal["evidence"], list) or not proposal["evidence"]:
            raise ValueError(f"proposal '{name}' requires evidence")
    return spec


def create_episode_proposals(proposal_store, business_slug: str, config_dir: str) -> list[int]:
    """Create pending proposal rows from exact config data; never approve."""
    spec = load_episode_proposal_spec(config_dir, business_slug)
    ids = []
    for proposal in spec.values():
        ids.append(
            proposal_store.create_proposal(
                business_slug=business_slug,
                target_module=proposal["target_module"],
                target_section=proposal["target_section"],
                proposal_type=proposal["proposal_type"],
                evidence=proposal["evidence"],
                change_description=proposal["change_description"],
                exact_diff=proposal["exact_diff"],
                rationale=proposal["rationale"],
                confidence=proposal.get("confidence", "medium"),
            )
        )
    return ids
