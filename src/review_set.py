"""Config-owned operator review sets for related idea cards."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


def list_review_sets(business_slug: str, config_dir: str = "config") -> list[dict]:
    path = Path(config_dir) / "review_sets.yaml"
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    configured = ((data.get("review_sets") or {}).get(business_slug) or {})
    return [
        {"name": name, "label": spec.get("label", name)}
        for name, spec in configured.items()
        if isinstance(spec, dict)
    ]


def load_review_set(name: str, business_slug: str, config_dir: str = "config") -> dict:
    data = yaml.safe_load((Path(config_dir) / "review_sets.yaml").read_text()) or {}
    spec = ((data.get("review_sets") or {}).get(business_slug) or {}).get(name)
    if not isinstance(spec, dict):
        raise ValueError(f"review set '{name}' is not configured for '{business_slug}'")
    if not isinstance(spec.get("source_id"), int) or not isinstance(spec.get("card_ids"), list):
        raise ValueError("review set requires integer source_id and card_ids list")
    return spec


def cards_for_review(store, business_slug: str, name: str, config_dir: str = "config") -> list[dict]:
    spec = load_review_set(name, business_slug, config_dir)
    wanted = set(spec["card_ids"])
    source_id = spec["source_id"]
    result = []
    for card in store.list_idea_cards(business_slug):
        if card["id"] not in wanted:
            continue
        try:
            source_refs = json.loads(card.get("source_refs") or "[]")
        except (TypeError, ValueError):
            source_refs = []
        if source_id in source_refs:
            result.append(card)
    return result
