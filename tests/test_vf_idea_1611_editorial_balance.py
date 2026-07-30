"""VF-IDEA-1611 editorial-balance context tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from editorial_balance import (
    FRAMING_FAMILY_SCHEMA,
    EditorialBalanceService,
    compute_lens_counts,
)


def test_lens_counts_use_persisted_ids_only():
    cards = [
        {"editorial_fit": '{"lens_id":"ai","status":"supported"}'},
        {"editorial_fit": '{"lens_id":"ai","status":"partial"}'},
        {"editorial_fit": '{"lens_id":"culture","status":"supported"}'},
        {"editorial_fit": None},
    ]
    assert compute_lens_counts(cards) == {"ai": 2, "culture": 1}


def test_lens_counts_ignore_malformed_or_unrecorded_values():
    assert compute_lens_counts([
        {"editorial_fit": "not-json"},
        {"editorial_fit": '{"status":"supported"}'},
        {"editorial_fit": {"lens_id": "money"}},
    ]) == {"money": 1}


def test_framing_analysis_receives_history_and_counts_as_evidence():
    captured = {}
    result = {
        "analysis_version": "1.0",
        "framing_families": [{
            "family_id": "family_1", "description": "A repeated framing family",
            "card_ids": [1, 2], "repetition_note": "Two cards share this family.",
        }],
        "advisory_note": "Use as context only.",
    }

    class FakeAdapter:
        def complete(self, **kwargs):
            captured.update(kwargs)
            return result

    service = EditorialBalanceService(FakeAdapter(), config_dir="config")
    output = service.analyze(
        business_slug="stackpenni",
        recent_cards=[{"id": 1, "idea": "A", "editorial_fit": '{"lens_id":"ai"}'}, {"id": 2, "idea": "B", "editorial_fit": '{"lens_id":"ai"}'}],
        current_candidates=[{"id": 9, "idea": "C"}],
    )
    assert output["framing_analysis"] == result
    assert output["lens_counts"] == {"ai": 2}
    assert captured["variables"]["lens_counts"] == {"ai": 2}
    assert captured["variables"]["recent_cards"][0]["id"] == 1
    assert captured["context"].startswith("Editorial framing-family analysis")


def test_analysis_does_not_reject_source_required_lens():
    assert "advisory" in str(FRAMING_FAMILY_SCHEMA).lower()
