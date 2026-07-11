"""
ViralFactory — Compliance Contract Validators (T10.1 — AMENDMENT-008)

Validators for the three compliance-loop schemas:
1. Compliance contract (script-to-plan): validates the LLM-authored contract
   has every required beat with a verification method.
2. Compliance review (final-output): validates the post-render verdict has
   per-beat coverage with evidence.
3. Remediation instruction: validates the remediation actions are within
   the safe scope.

These extend the generic validate_json_schema with domain-specific checks
that the generic validator cannot express (e.g., "every required beat must
have a verification method", "compliant verdict requires all beats verified").
"""

# Support both package and direct imports
try:
    from .validator import validate_json_schema, ValidationError
except ImportError:
    from validator import validate_json_schema, ValidationError


def validate_compliance_contract(output: dict) -> dict:
    """
    Validate a compliance contract against COMPLIANCE_CONTRACT_SCHEMA.

    Domain-specific checks beyond generic schema:
    - Every beat with required=true must have a non-empty verification_method
    - Every beat with required=true must have a non-empty source_excerpt
    - beat_id values must be unique
    """
    # Support both package and direct imports
    try:
        from .pipeline import COMPLIANCE_CONTRACT_SCHEMA
    except ImportError:
        from pipeline import COMPLIANCE_CONTRACT_SCHEMA

    # Generic schema validation (includes enum checks on requirement_type and verification_method)
    validated = validate_json_schema(output, COMPLIANCE_CONTRACT_SCHEMA, context="compliance_contract")

    beats = validated.get("beats", [])

    # Domain-specific: required beats must have verification_method and source_excerpt
    for i, beat in enumerate(beats):
        if beat.get("required", False):
            if not beat.get("verification_method"):
                raise ValidationError(
                    f"Compliance contract beat[{i}] (beat_id={beat.get('beat_id')}) "
                    f"is required but has no verification_method"
                )
            if not beat.get("source_excerpt", "").strip():
                raise ValidationError(
                    f"Compliance contract beat[{i}] (beat_id={beat.get('beat_id')}) "
                    f"is required but has no source_excerpt"
                )

    # Domain-specific: beat_ids must be unique
    beat_ids = [b.get("beat_id") for b in beats]
    seen = set()
    for bid in beat_ids:
        if bid in seen:
            raise ValidationError(
                f"Compliance contract has duplicate beat_id: '{bid}'"
            )
        seen.add(bid)

    return validated


def validate_compliance_review(output: dict) -> dict:
    """
    Validate a compliance review against COMPLIANCE_REVIEW_SCHEMA.

    Domain-specific checks beyond generic schema:
    - If verdict is "compliant", every coverage entry must be "verified"
    - Every issue with remediable=true must have a beat_id
    """
    # Support both package and direct imports
    try:
        from .pipeline import COMPLIANCE_REVIEW_SCHEMA
    except ImportError:
        from pipeline import COMPLIANCE_REVIEW_SCHEMA

    validated = validate_json_schema(output, COMPLIANCE_REVIEW_SCHEMA, context="compliance_review")

    verdict = validated.get("verdict")
    coverage = validated.get("coverage", [])

    # Domain-specific: compliant verdict requires all beats verified
    if verdict == "compliant":
        for cov in coverage:
            status = cov.get("status")
            if status != "verified":
                raise ValidationError(
                    f"Compliance review verdict is 'compliant' but beat "
                    f"{cov.get('beat_id')} has status '{status}' — "
                    f"compliant requires every beat to be 'verified'"
                )

    return validated


def validate_remediation_instruction(output: dict) -> dict:
    """
    Validate a remediation instruction against REMEDIATION_INSTRUCTION_SCHEMA.

    Domain-specific checks beyond generic schema:
    - If escalate=true, actions must be empty (escalation means no safe fix)
    - If escalate=false, actions must have at least one entry
    - estimated_cost_usd must be >= 0
    """
    # Support both package and direct imports
    try:
        from .pipeline import REMEDIATION_INSTRUCTION_SCHEMA
    except ImportError:
        from pipeline import REMEDIATION_INSTRUCTION_SCHEMA

    validated = validate_json_schema(output, REMEDIATION_INSTRUCTION_SCHEMA, context="remediation_instruction")

    escalate = validated.get("escalate", False)
    actions = validated.get("actions", [])
    cost = validated.get("estimated_cost_usd", 0)

    # Domain-specific: escalate=true should have no actions
    if escalate and len(actions) > 0:
        raise ValidationError(
            "Remediation instruction has escalate=true but also has actions — "
            "escalation means no safe fix is possible"
        )

    # Domain-specific: escalate=false should have at least one action
    if not escalate and len(actions) == 0:
        raise ValidationError(
            "Remediation instruction has escalate=false but no actions — "
            "if not escalating, at least one remediation action is required"
        )

    # Domain-specific: cost must be non-negative
    if cost < 0:
        raise ValidationError(
            f"Remediation instruction estimated_cost_usd is negative: {cost}"
        )

    return validated