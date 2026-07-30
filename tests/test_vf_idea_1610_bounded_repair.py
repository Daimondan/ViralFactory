import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from source_fit_critic import SourceFitCritic, SourceFitValidationError
def valid_result():
    return {
        "critic_version": "1.0",
        "card_fit": {
            "lens_id": "ai", "verdict": "supported",
            "evidence_quotes": ["quote"], "rationale": "r",
        },
        "source_fit": [{
            "source_id": 111,
            "fits": [{"lens_id": "ai", "verdict": "supported", "evidence_quotes": ["quote"], "rationale": "r"}],
            "unresolved": False,
        }],
        "batch_range": {"lens_ids": ["ai"], "coverage_note": "coverage"},
    }


def test_bounded_repair_is_one_pass_and_card_specific():
    first = valid_result()
    first["source_fit"][0]["source_id"] = 999
    repaired = valid_result()
    calls = []

    class FakeAdapter:
        def complete(self, **kwargs):
            calls.append(kwargs)
            return first if len(calls) == 1 else repaired

    critic = SourceFitCritic(FakeAdapter(), config_dir="config")
    output = critic.run_with_bounded_repair(
        business_slug="stackpenni",
        card_context={"card_id": 7, "idea": "A grounded idea"},
        sources=[{"id": 111, "title": "Source", "content": "Exact source sentence."}],
        proposed_fit=[{"lens_id": "ai", "reason": "Candidate lens"}],
    )
    assert output == repaired
    assert len(calls) == 2
    assert calls[1]["prompt_file"] == "ideas/source_fit_repair_v1.md"
    assert calls[1]["variables"]["critic_findings"]
    assert calls[1]["variables"]["card_context"]["card_id"] == 7


def test_bounded_repair_does_not_retry_more_than_once():
    bad = valid_result()
    bad["source_fit"][0]["source_id"] = 999
    calls = []

    class FakeAdapter:
        def complete(self, **kwargs):
            calls.append(kwargs)
            return bad

    critic = SourceFitCritic(FakeAdapter(), config_dir="config")
    with pytest.raises(SourceFitValidationError):
        critic.run_with_bounded_repair(
            business_slug="stackpenni", card_context={"card_id": 8},
            sources=[{"id": 111, "title": "Source", "content": "Exact source sentence."}],
            proposed_fit=[{"lens_id": "ai", "reason": "Candidate lens"}],
        )
    assert len(calls) == 2


def test_invalid_batch_members_are_omitted_not_padded():
    good = valid_result()
    bad = valid_result()
    bad["source_fit"][0]["source_id"] = 999
    kept, omitted = SourceFitCritic.retain_valid_results(
        [("good", good), ("bad", bad)], {"good": [111], "bad": [112]}, ["ai"]
    )
    assert kept == [("good", good)]
    assert omitted[0]["card_id"] == "bad"
