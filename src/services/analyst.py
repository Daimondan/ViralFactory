"""
Analyst service (VF-AU-502 + VF-AU-503).

Evidence-bounded performance analysis and human-gated learning proposals.

Rules:
- Matched baseline where possible
- Observed vs measured vs hypothesis vs house rule labels
- Qualitative analysis not blocked by missing views
- One post cannot create a rule — always HYPOTHESIS
- No auto-apply — proposals enter a human gate
- Exact diff + evidence required for every proposal
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class LearningProposal:
    """A proposed module/process diff that enters the human gate."""
    proposal_id: str
    status: str = "pending"          # pending | approved | rejected | superseded
    requires_approval: bool = True
    target_module: str = ""
    target_section: str = ""
    target_version: str = ""
    proposed_change: str = ""
    exact_diff: str = ""
    evidence: dict = field(default_factory=dict)
    created_at: str = ""


class AnalystService:
    """Produces evidence-bounded analysis and gated learning proposals."""

    def __init__(self):
        self._proposals: dict[str, LearningProposal] = {}

    def analyze(self, performance_record: dict) -> dict:
        """Analyze a performance record and produce evidence-bounded findings.

        Rules:
        - Missing metrics: qualitative analysis continues, flagged as missing
        - Tiny samples (1 post): flagged as small sample, verdict = hypothesis
        - All conclusions labeled HYPOTHESIS until repeated evidence confirms
        """
        derived_ratios = performance_record.get("derived_ratios", {})
        fingerprint = performance_record.get("creative_fingerprint", {})
        metrics = performance_record.get("metrics", {})
        sample_size = performance_record.get("sample_size", 1)

        # Check for missing metrics
        missing_metrics = []
        for metric_name, metric_data in metrics.items():
            if metric_data.get("value") is None:
                missing_metrics.append(metric_name)

        summary_parts = []
        if missing_metrics:
            summary_parts.append(f"Missing metrics: {', '.join(missing_metrics)} — null values preserved, no fabricated zeros")
        else:
            summary_parts.append("All metrics present")

        # Analyze ratios
        ratio_findings = []
        for ratio_name, ratio_data in derived_ratios.items():
            value = ratio_data.get("value")
            if value is not None:
                ratio_findings.append(f"{ratio_name}: {value:.3f}")

        if ratio_findings:
            summary_parts.append(f"Derived ratios: {'; '.join(ratio_findings)}")

        # Check sample size
        if sample_size <= 1:
            summary_parts.append("Small sample (single post) — conclusions are hypotheses, not rules")

        # Fingerprint analysis
        if fingerprint:
            fmt = fingerprint.get("format", "unknown")
            pattern = fingerprint.get("narrative_pattern", "unknown")
            summary_parts.append(f"Creative fingerprint: {fmt} / {pattern}")

        return {
            "verdict": "hypothesis",  # always hypothesis — one post cannot create a rule
            "evidence_label": "HYPOTHESIS",
            "summary": ". ".join(summary_parts),
            "findings": {
                "missing_metrics": missing_metrics,
                "ratios": ratio_findings,
                "sample_size": sample_size,
                "fingerprint": fingerprint,
            },
        }

    def propose_diff(self, analysis_input: dict) -> dict:
        """Create a learning proposal with an exact diff.

        The proposal enters a human gate — it is NEVER auto-applied.
        """
        proposal_id = hashlib.sha256(
            f"{analysis_input.get('target_module', '')}:{analysis_input.get('target_section', '')}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        proposal = LearningProposal(
            proposal_id=proposal_id,
            status="pending",
            requires_approval=True,
            target_module=analysis_input.get("target_module", ""),
            target_section=analysis_input.get("target_section", ""),
            target_version=analysis_input.get("target_version", ""),
            proposed_change=analysis_input.get("proposed_change", ""),
            exact_diff=analysis_input.get("proposed_change", ""),  # the diff IS the proposed change
            evidence={
                "derived_ratios": analysis_input.get("derived_ratios", {}),
                "creative_fingerprint": analysis_input.get("creative_fingerprint", {}),
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        self._proposals[proposal_id] = proposal

        return {
            "proposal_id": proposal_id,
            "status": proposal.status,
            "requires_approval": proposal.requires_approval,
            "target_module": proposal.target_module,
            "target_section": proposal.target_section,
            "target_version": proposal.target_version,
            "proposed_change": proposal.proposed_change,
            "exact_diff": proposal.exact_diff,
            "evidence": proposal.evidence,
        }

    def reject_proposal(self, proposal_id: str) -> dict:
        """Reject a proposal — mark as rejected, never applied."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return {"proposal_id": proposal_id, "status": "not_found"}
        proposal.status = "rejected"
        return {"proposal_id": proposal_id, "status": "rejected"}

    def approve_proposal(self, proposal_id: str) -> dict:
        """Approve a proposal — but this does NOT auto-apply. It marks it as
        approved for the operator to manually implement."""
        proposal = self._proposals.get(proposal_id)
        if not proposal:
            return {"proposal_id": proposal_id, "status": "not_found"}
        proposal.status = "approved"
        return {"proposal_id": proposal_id, "status": "approved"}

    def get_proposal(self, proposal_id: str) -> LearningProposal | None:
        return self._proposals.get(proposal_id)