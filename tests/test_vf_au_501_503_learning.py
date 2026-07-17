"""
Tests for VF-AU-501 through VF-AU-503: Learning phase.

VF-AU-501: Performance records and creative fingerprints.
VF-AU-502: Analyst process — evidence-bounded analysis.
VF-AU-503: Gate learning proposals — no auto-apply.
"""

import json, os, sqlite3, pytest, sys, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_store import ProductionStore
from production_contract import assemble_contract


def _make_contract():
    content = {
        "contract_id": "c001",
        "core_claim": "Compound interest",
        "audience_value": "Understand saving",
        "evidence_refs": ["source:14"],
        "primary_emotional_job": "conviction",
        "primary_audience_action": "save",
        "format_name": "reel",
        "platform": "instagram",
        "capture_policy": "generated_allowed",
        "evidence_label": "HYPOTHESIS",
    }
    return assemble_contract(
        content_contract=content,
        beats=[{"beat_id": "b01", "platform_variant_id": "pv001", "role": "hook",
                "required": True, "vo_text": "test", "staged_action": "test",
                "capture_policy": "generated_allowed", "evidence_refs": ["source:14"]}],
        media_recipes=[{"media_recipe_id": "r01", "beat_id": "b01", "media_function": "context",
                        "source_policy": "generated_allowed", "primary": {"kind": "generated_image"}}],
        edit_segments=[{"segment_id": "s01", "beat_ids": ["b01"], "source": "generated:1"}],
    )


# ── VF-AU-501: Performance records ──────────────────────────────────────────

class TestPerformanceRecords:
    """Store: post ID, metrics with confidence, derived_ratios, contract/process versions,
    operator edits, cost, compliance/remediation history."""

    def test_store_performance_record_with_derived_ratios(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        store.save_contract("stackpenni", 1, _make_contract())
        record = {
            "platform_post_id": "ig_12345",
            "published_at": "2026-07-17T12:00:00Z",
            "metrics": {
                "views": {"value": 1500, "confidence": "measured", "captured_at": "2026-07-18"},
                "likes": {"value": 42, "confidence": "measured", "captured_at": "2026-07-18"},
                "comments": {"value": 7, "confidence": "measured", "captured_at": "2026-07-18"},
            },
            "derived_ratios": {
                "comment_to_like": {"value": 0.167, "confidence": "computed", "captured_at": "2026-07-18"},
                "share_to_like": {"value": 0.05, "confidence": "computed", "captured_at": "2026-07-18"},
                "save_to_like": {"value": 0.12, "confidence": "computed", "captured_at": "2026-07-18"},
            },
            "creative_fingerprint": {
                "format": "reel",
                "narrative_pattern": "proof-first",
                "hook_mechanism": "claim-first",
                "emotional_job": "conviction",
                "primary_action": "save",
                "text_functions": ["hook", "caption"],
                "audio_mode": "vo_only",
                "media_mix": ["generated"],
            },
            "contract_version": "2.0",
            "process_version": "2.0",
            "operator_edits": [],
            "generation_cost_usd": 0.03,
            "compliance_history": [],
            "remediation_history": [],
        }
        store.save_performance_record("c001", record)
        loaded = store.get_performance_record("c001")
        assert loaded["derived_ratios"]["comment_to_like"]["value"] == 0.167
        assert loaded["creative_fingerprint"]["narrative_pattern"] == "proof-first"
        assert loaded["contract_version"] == "2.0"

    def test_null_metrics_preserved(self, tmp_path):
        """Missing metrics must be stored as null, not fabricated."""
        store = ProductionStore(str(tmp_path / "test.db"))
        store.save_contract("stackpenni", 1, _make_contract())
        record = {
            "platform_post_id": "ig_123",
            "published_at": "2026-07-17",
            "metrics": {
                "views": {"value": None, "confidence": "unknown", "captured_at": None},
                "likes": {"value": None, "confidence": "unknown", "captured_at": None},
            },
            "derived_ratios": {},
            "creative_fingerprint": {},
        }
        store.save_performance_record("c001", record)
        loaded = store.get_performance_record("c001")
        assert loaded["metrics"]["views"]["value"] is None

    def test_append_only_history(self, tmp_path):
        """Repeated captures append, never replace."""
        store = ProductionStore(str(tmp_path / "test.db"))
        store.save_contract("stackpenni", 1, _make_contract())
        store.save_performance_record("c001", {
            "platform_post_id": "ig_1", "published_at": "x",
            "metrics": {"likes": {"value": 10, "confidence": "measured", "captured_at": "2026-07-18"}},
            "derived_ratios": {}, "creative_fingerprint": {},
        })
        store.save_performance_record("c001", {
            "platform_post_id": "ig_1", "published_at": "x",
            "metrics": {"likes": {"value": 25, "confidence": "measured", "captured_at": "2026-07-19"}},
            "derived_ratios": {}, "creative_fingerprint": {},
        })
        history = store.get_performance_history("c001")
        assert len(history) == 2
        # Latest should have 25
        latest = store.get_performance_record("c001")
        assert latest["metrics"]["likes"]["value"] == 25

    def test_tenant_isolation(self, tmp_path):
        store = ProductionStore(str(tmp_path / "test.db"))
        # Use different contract IDs since the table has UNIQUE(contract_id)
        contract_a = _make_contract()
        contract_b = _make_contract()
        contract_b["contract_id"] = "c002"
        store.save_contract("business_a", 1, contract_a)
        store.save_contract("business_b", 2, contract_b)
        # Each business can list its own contracts
        a_contracts = store.list_contracts("business_a")
        b_contracts = store.list_contracts("business_b")
        assert len(a_contracts) == 1
        assert len(b_contracts) == 1
        assert a_contracts[0]["business_slug"] == "business_a"
        assert b_contracts[0]["business_slug"] == "business_b"

    def test_no_fabricated_zero(self, tmp_path):
        """Missing metrics must not be replaced with fabricated zeros."""
        store = ProductionStore(str(tmp_path / "test.db"))
        store.save_contract("stackpenni", 1, _make_contract())
        record = {
            "platform_post_id": "ig_1", "published_at": "x",
            "metrics": {"shares": {"value": None, "confidence": "unknown", "captured_at": None}},
            "derived_ratios": {"share_to_like": {"value": None, "confidence": "unknown", "captured_at": None}},
            "creative_fingerprint": {},
        }
        store.save_performance_record("c001", record)
        loaded = store.get_performance_record("c001")
        assert loaded["metrics"]["shares"]["value"] is None  # not 0
        assert loaded["derived_ratios"]["share_to_like"]["value"] is None  # not 0


# ── VF-AU-502: Analyst process ───────────────────────────────────────────────

class TestAnalystProcess:
    """Evidence-bounded analysis with matched baseline. One post cannot create a rule."""

    def test_analyst_labels_conclusions_as_hypothesis(self):
        """Ratio-based conclusions must be labeled HYPOTHESIS."""
        from services.analyst import AnalystService
        svc = AnalystService()
        result = svc.analyze({
            "derived_ratios": {"comment_to_like": {"value": 0.15}},
            "creative_fingerprint": {"format": "reel", "narrative_pattern": "proof-first"},
        })
        # The analysis must label conclusions as HYPOTHESIS
        assert result["evidence_label"] == "HYPOTHESIS"

    def test_missing_metrics_handled(self):
        """Missing metrics should not block qualitative analysis."""
        from services.analyst import AnalystService
        svc = AnalystService()
        result = svc.analyze({
            "derived_ratios": {},
            "creative_fingerprint": {"format": "reel"},
            "metrics": {"views": {"value": None, "confidence": "unknown"}},
        })
        # Analysis should still produce a result
        assert "summary" in result
        assert "missing" in result["summary"].lower() or "null" in result["summary"].lower() or "no metrics" in result["summary"].lower()

    def test_tiny_sample_flagged(self):
        """A single post's analysis should flag small sample size."""
        from services.analyst import AnalystService
        svc = AnalystService()
        result = svc.analyze({
            "derived_ratios": {"comment_to_like": {"value": 0.15}},
            "creative_fingerprint": {"format": "reel"},
            "sample_size": 1,
        })
        assert "small sample" in result["summary"].lower() or "single" in result["summary"].lower() or "one post" in result["summary"].lower()

    def test_exact_target_diff_required(self):
        """The analysis must produce an exact target module/process diff for proposals."""
        from services.analyst import AnalystService
        svc = AnalystService()
        result = svc.propose_diff({
            "creative_fingerprint": {"format": "reel", "narrative_pattern": "proof-first"},
            "derived_ratios": {"comment_to_like": {"value": 0.15}},
            "target_module": "viral-patterns",
            "target_section": "Performance hypotheses",
            "proposed_change": "Add proof-first as a tested pattern for reels with high comment-to-like ratio",
        })
        assert "target_module" in result
        assert "target_section" in result
        assert "proposed_change" in result
        assert "exact_diff" in result


# ── VF-AU-503: Gate learning proposals ────────────────────────────────────────

class TestGateLearningProposals:
    """No auto-apply. Exact diff + evidence enters human gate."""

    def test_no_auto_apply(self):
        """Proposals must not be auto-applied — they enter a human gate."""
        from services.analyst import AnalystService
        svc = AnalystService()
        proposal = svc.propose_diff({
            "creative_fingerprint": {"format": "reel"},
            "derived_ratios": {"comment_to_like": {"value": 0.15}},
            "target_module": "viral-patterns",
            "target_section": "Performance hypotheses",
            "proposed_change": "test change",
        })
        assert proposal["status"] == "pending"  # not "applied"
        assert proposal["requires_approval"] is True

    def test_approval_versions_target(self):
        """Proposals target specific module versions for approval."""
        from services.analyst import AnalystService
        svc = AnalystService()
        proposal = svc.propose_diff({
            "creative_fingerprint": {"format": "reel"},
            "derived_ratios": {},
            "target_module": "viral-patterns",
            "target_section": "Performance hypotheses",
            "proposed_change": "test",
            "target_version": "3.1",
        })
        assert proposal["target_version"] == "3.1"

    def test_rejection_works(self):
        """A rejected proposal should be marked as rejected, not applied."""
        from services.analyst import AnalystService
        svc = AnalystService()
        proposal = svc.propose_diff({
            "creative_fingerprint": {"format": "reel"},
            "derived_ratios": {},
            "target_module": "viral-patterns",
            "target_section": "test",
            "proposed_change": "test",
        })
        # Simulate rejection
        rejected = svc.reject_proposal(proposal["proposal_id"])
        assert rejected["status"] == "rejected"

    def test_one_post_cannot_create_rule(self):
        """A single post's evidence must produce a hypothesis, not a rule."""
        from services.analyst import AnalystService
        svc = AnalystService()
        result = svc.analyze({
            "derived_ratios": {"comment_to_like": {"value": 0.15}},
            "creative_fingerprint": {"format": "reel"},
            "sample_size": 1,
        })
        # The verdict must be "hypothesis" not "rule" or "confirmed"
        assert result["verdict"] == "hypothesis"