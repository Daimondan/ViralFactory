"""Config-owned pending module/config proposals; never applies changes."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_module_proposal_specs(business_slug: str, config_dir: str = "config") -> list[dict]:
    path = Path(config_dir) / "module_proposals.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    proposals = (data.get("proposals") or {}).get(business_slug, [])
    if not isinstance(proposals, list):
        raise ValueError(f"module proposals for '{business_slug}' must be a list")
    required = {"target_module", "target_section", "proposal_type", "change_description", "exact_diff", "rationale"}
    for proposal in proposals:
        if not isinstance(proposal, dict) or not required.issubset(proposal):
            raise ValueError("module proposal is missing required fields")
    return proposals


def prepare_module_proposals(proposal_store, business_slug: str, config_dir: str = "config") -> list[int]:
    """Create pending queue rows only; approval/application remains operator-gated."""
    ids = []
    for proposal in load_module_proposal_specs(business_slug, config_dir):
        ids.append(proposal_store.create_proposal(
            business_slug=business_slug,
            target_module=proposal["target_module"],
            target_section=proposal["target_section"],
            proposal_type=proposal["proposal_type"],
            evidence=proposal.get("evidence", []),
            change_description=proposal["change_description"],
            exact_diff=proposal["exact_diff"],
            rationale=proposal["rationale"],
            confidence=proposal.get("confidence", "medium"),
        ))
    return ids
