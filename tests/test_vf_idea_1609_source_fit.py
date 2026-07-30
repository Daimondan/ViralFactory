"""VF-IDEA-1609: Source-Fit Critic process and mechanical boundary tests."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_adapter import LLMAdapter
from process_engine import load_process_registry
from source_fit_critic import (
    SOURCE_FIT_CRITIC_SCHEMA,
    SourceFitCritic,
    SourceFitValidationError,
    validate_source_fit_result,
)


def valid_result():
    return {
        "critic_version": "1.0",
        "card_fit": {
            "lens_id": "ai", "verdict": "supported",
            "evidence_quotes": ["Exact source sentence."],
            "rationale": "The card fits AI.",
        },
        "source_fit": [{
            "source_id": 111,
            "fits": [{
                "lens_id": "ai",
                "verdict": "supported",
                "evidence_quotes": ["Exact source sentence."],
                "rationale": "The source directly discusses AI.",
            }],
            "unresolved": False,
        }],
        "batch_range": {
            "lens_ids": ["ai"],
            "coverage_note": "One source supports one proposed lens.",
        },
    }


def test_source_fit_schema_has_exact_evidence_boundary():
    assert set(SOURCE_FIT_CRITIC_SCHEMA["required"]) == {"critic_version", "card_fit", "source_fit", "batch_range"}
    assert "source_id" in SOURCE_FIT_CRITIC_SCHEMA["properties"]["source_fit"]["items"]["properties"]


def test_validator_rejects_unknown_source_and_lens():
    with pytest.raises(SourceFitValidationError, match="source"):
        validate_source_fit_result(valid_result(), [112], ["ai"])
    bad = valid_result()
    bad["source_fit"][0]["fits"][0]["lens_id"] = "invented"
    with pytest.raises(SourceFitValidationError, match="lens"):
        validate_source_fit_result(bad, [111], ["ai"])


def test_validator_rejects_invalid_verdict_and_missing_source_membership():
    bad = valid_result()
    bad["source_fit"][0]["fits"][0]["verdict"] = "maybe"
    with pytest.raises(SourceFitValidationError, match="verdict"):
        validate_source_fit_result(bad, [111], ["ai"])
    bad = valid_result()
    bad["source_fit"].append({"source_id": 222, "fits": [], "unresolved": True})
    with pytest.raises(SourceFitValidationError, match="source"):
        validate_source_fit_result(bad, [111], ["ai"])


def test_registry_prompt_and_schema_are_declared():
    registry = load_process_registry("config", "prompts")
    spec = registry["processes"]["source_fit_critic"]
    assert spec["prompt_file"] == "ideas/source_fit_critic_v1.md"
    assert spec["schema"] == "SOURCE_FIT_CRITIC_SCHEMA"


def test_critic_passes_exact_source_evidence_and_proposed_fit(tmp_path):
    captured = {}
    result = valid_result()

    class FakeAdapter:
        def complete(self, **kwargs):
            captured.update(kwargs)
            return result

    critic = SourceFitCritic(FakeAdapter(), config_dir="config")
    output = critic.run(
        business_slug="stackpenni",
        sources=[{"id": 111, "title": "Source", "content": "Exact source sentence."}],
        proposed_fit=[{"lens_id": "ai", "reason": "Candidate lens"}],
    )
    assert output == result
    assert captured["variables"]["source_evidence"][0]["id"] == 111
    assert captured["variables"]["proposed_fit"][0]["lens_id"] == "ai"
    assert captured["context"].startswith("Source-Fit Critic")
    assert captured["backend"] == "source_fit_critic"


def test_adapter_cache_and_provenance_are_used_for_unchanged_critic_input(tmp_path):
    db_path = str(tmp_path / "critic.db")
    models = {
        "active": {"default": "critic"},
        "critic": {
            "provider": "openai_compatible", "model": "critic-test",
            "temperature": 0, "max_tokens": 1000, "base_url": "http://unused",
        },
    }
    adapter = LLMAdapter(models, db_path=db_path, prompts_dir="prompts")
    calls = []
    raw = json.dumps(valid_result())
    with patch.object(adapter, "_call_openai_compatible", return_value=(raw, 1)) as call:
        critic = SourceFitCritic(adapter, config_dir="config")
        args = {
            "business_slug": "stackpenni",
            "sources": [{"id": 111, "title": "Source", "content": "Exact source sentence."}],
            "proposed_fit": [{"lens_id": "ai", "reason": "Candidate lens"}],
        }
        critic.run(**args)
        critic.run(**args)
        assert call.call_count == 1
    rows = adapter.provenance.get_by_hash(adapter.cache.hash_variables({
        "source_evidence": args["sources"],
        "proposed_fit": args["proposed_fit"],
    }))
    assert len(rows) == 2
    assert any(row["cached"] == 1 for row in rows)
