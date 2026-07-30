"""VF-IDEA-1613 Gate 1 persistence and fixed-source proof boundary."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore


def test_validated_card_fit_and_critic_evidence_round_trip(tmp_path):
    store = PipelineStore(db_path=str(tmp_path / "proof.db"))
    card_id = store.create_idea_card(
        "stackpenni", "Fixed source proof card", ["Hook"],
        {"scope": {"type": "one_off"}, "format": {}, "capture_required": [], "rationale": "r"},
        "ai_originated", source_refs=[1001],
    )
    fit = {
        "lens_id": "policy", "verdict": "supported",
        "evidence_quotes": ["Institutions and regulation."],
        "rationale": "Exact source evidence supports policy.",
        "critic_result": {"critic_version": "1.0", "source_fit": [{"source_id": 1001}]},
    }
    updated = store.update_card_editorial_fit(
        card_id, fit, {"critic_version": "1.0", "source_ids": [1001], "profile": "source_fit_critic"}
    )
    assert json.loads(updated["editorial_fit"])["lens_id"] == "policy"
    assert json.loads(updated["editorial_fit_provenance"])["source_ids"] == [1001]


def test_gate_ui_exposes_source_fit_action_and_endpoint():
    template = Path("src/templates/ideas.html").read_text()
    assert "Check source fit" in template
    assert "/editorial-fit" in template
