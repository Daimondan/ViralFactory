"""Run the controlled VF-IDEA-1613 Source-Fit proof.

This runner performs no editorial classification. It loads the operator-selected
source IDs from config, resolves their exact stored evidence, and delegates
judgment to the real configured adapter and Source-Fit Critic.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config_loader import load_all
from llm_adapter import LLMAdapter
from pipeline import PipelineStore
from source_fit_critic import SourceFitCritic


CONFIG_DIR = ROOT / "config"
DB_PATH = ROOT / "data" / "viralfactory.db"


def main() -> int:
    proof = yaml.safe_load((CONFIG_DIR / "source_fit_proof.yaml").read_text())["source_fit_proof"]
    business_slug = proof["business_slug"]
    source_specs = proof["sources"]
    source_ids = [item["id"] for item in source_specs]
    proposed_fit = [{"lens_id": lens_id, "reason": "Controlled fixed-source proof candidate."}
                    for lens_id in proof["proposed_lenses"]]

    store = PipelineStore(db_path=str(DB_PATH))
    sources = store.resolve_source_refs(business_slug, source_ids)
    resolved_ids = [source["id"] for source in sources]
    if set(resolved_ids) != set(source_ids) or len(resolved_ids) != len(source_ids):
        raise RuntimeError(f"fixed source set did not resolve exactly: expected={source_ids} got={resolved_ids}")
    sources_by_id = {source["id"]: source for source in sources}
    sources = [sources_by_id[source_id] for source_id in source_ids]
    if any(not isinstance(source.get("content"), str) or not source["content"].strip() for source in sources):
        raise RuntimeError("fixed source set contains missing exact content")

    config = load_all(str(CONFIG_DIR))
    adapter = LLMAdapter(config["models"], db_path=str(DB_PATH), prompts_dir=str(ROOT / "prompts"))
    critic = SourceFitCritic(adapter, config_dir=str(CONFIG_DIR))
    result = critic.run_with_bounded_repair(
        business_slug=business_slug,
        card_context={"proof": "VF-IDEA-1613", "source_ids": source_ids},
        sources=[{"id": source["id"], "title": source.get("title", ""),
                  "content": source.get("content", ""), "url": source.get("url") or ""}
                 for source in sources],
        proposed_fit=proposed_fit,
    )
    output = {
        "status": "ok",
        "proof": "VF-IDEA-1613",
        "business_slug": business_slug,
        "source_ids": source_ids,
        "evidence_roles": {str(item["id"]): item["evidence_role"] for item in source_specs},
        "critic_version": result["critic_version"],
        "card_fit": result["card_fit"],
        "source_fit_ids": [item["source_id"] for item in result["source_fit"]],
        "batch_range": result["batch_range"],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
