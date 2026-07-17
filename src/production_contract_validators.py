"""
Production Contract v2 — Cross-document validators (VF-AU-102).

Validates relationships that JSON Schema alone cannot prove:
- Globally unique IDs within a contract
- All required beats represented in edit segments
- Exact approved text hash preserved through assembly/remediation
- Evidence references resolve to non-empty source IDs
- Required capture cannot resolve to generated/stock
- Compliance coverage references known beats
- Legacy unclassified tasks flagged for operator classification
- No positional fallback in segments

These validators wrap and extend the functions in production_contract.py
into a comprehensive validation suite with a clean ValidationResult API.
"""

from typing import Any
from production_contract import (
    validate_contract_schema,
    validate_segment_beat_references,
    validate_recipe_beat_references,
    validate_text_intent_beat_references,
    validate_capture_policy_consistency,
    validate_no_positional_fallback,
    find_duplicate_ids,
    compute_writer_contract_hash,
    CONTENT_CONTRACT_SCHEMA,
)


class ValidationResult:
    """Accumulates validation errors from multiple checks."""

    def __init__(self):
        self.errors: list[str] = []

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_errors(self, msgs: list[str]) -> None:
        self.errors.extend(msgs)

    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def __repr__(self) -> str:
        if self.is_valid():
            return "ValidationResult(valid)"
        return f"ValidationResult(invalid, {len(self.errors)} errors)"


def validate_required_beat_coverage(
    beats: list[dict], segments: list[dict]
) -> ValidationResult:
    """Check that every required beat is represented in at least one edit segment.

    A required beat that has no segment mapping means the edit plan is incomplete
    and the rendered output will not contain that beat's content.
    """
    result = ValidationResult()

    # Collect all beat_ids referenced by segments
    covered_beats: set[str] = set()
    for seg in segments:
        for bid in seg.get("beat_ids", []):
            covered_beats.add(bid)

    for beat in beats:
        bid = beat.get("beat_id", "")
        is_required = beat.get("required", False)
        if is_required and bid and bid not in covered_beats:
            result.add_error(
                f"Required beat '{bid}' has no edit segment mapping — "
                f"the rendered output will not contain this beat's content"
            )

    return result


def validate_evidence_references(beats: list[dict]) -> ValidationResult:
    """Check that evidence references resolve to non-empty source IDs.

    A required beat with empty evidence refs cannot ground its claim.
    An empty evidence ref string is a broken reference.
    """
    result = ValidationResult()

    for beat in beats:
        bid = beat.get("beat_id", "?")
        refs = beat.get("evidence_refs", [])
        is_required = beat.get("required", False)

        # Check for empty strings in evidence_refs
        empty_refs = [r for r in refs if not r or not r.strip()]
        if empty_refs:
            result.add_error(
                f"Beat '{bid}' has empty evidence reference(s) — "
                f"evidence refs must be non-empty source IDs"
            )

        # Required beats must have at least one evidence ref
        if is_required and not refs:
            result.add_error(
                f"Required beat '{bid}' has no evidence references — "
                f"a required beat must ground its claim in at least one source"
            )

    return result


def validate_compliance_coverage(
    compliance_beats: list[dict], contract_beats: list[dict]
) -> ValidationResult:
    """Check that compliance coverage references known beats and covers required ones.

    The compliance review's per-beat coverage must:
    1. Only reference beat_ids that exist in the contract
    2. Cover every required beat
    """
    result = ValidationResult()

    contract_beat_ids = {b["beat_id"] for b in contract_beats if "beat_id" in b}
    required_beat_ids = {
        b["beat_id"] for b in contract_beats
        if b.get("beat_id") and b.get("required", False)
    }

    compliance_beat_ids: set[str] = set()
    for cb in compliance_beats:
        cbid = cb.get("beat_id", "")
        if cbid and cbid not in contract_beat_ids:
            result.add_error(
                f"Compliance coverage references unknown beat_id: {cbid}"
            )
        compliance_beat_ids.add(cbid)

    # Check that all required beats are covered
    missing = required_beat_ids - compliance_beat_ids
    for bid in sorted(missing):
        result.add_error(
            f"Required beat '{bid}' is missing from compliance coverage — "
            f"every required beat must have a compliance verdict"
        )

    return result


def validate_hash_integrity(
    expected_hash: str, writer_contract: dict
) -> ValidationResult:
    """Check that the writer contract hash matches the expected hash.

    Per AMENDMENT-009 Condition 4: the hash-lock protects the entire approved
    Writer contract. If the hash changes during assembly or remediation, it
    means the approved content was modified — which must be rejected.
    """
    result = ValidationResult()

    actual_hash = compute_writer_contract_hash(writer_contract)
    if actual_hash != expected_hash:
        result.add_error(
            f"Writer contract hash mismatch — approved content was modified. "
            f"Expected: {expected_hash[:16]}..., got: {actual_hash[:16]}... "
            f"This is a text-boundary firewall violation (AMENDMENT-009 Condition 4)."
        )

    return result


def validate_legacy_capture_classification(beats: list[dict]) -> ValidationResult:
    """Check for legacy_unclassified capture tasks that need operator classification.

    Per AMENDMENT-009 Condition 3: existing capture_required tasks from the
    AMENDMENT-006 era must not be silently migrated. They are marked
    legacy_unclassified and must be classified when they next enter production.
    """
    result = ValidationResult()

    for beat in beats:
        bid = beat.get("beat_id", "?")
        policy = beat.get("capture_policy", "")
        if policy == "legacy_unclassified":
            result.add_error(
                f"Beat '{bid}' has capture_policy='legacy_unclassified' — "
                f"operator must classify this capture task (capture_required, "
                f"capture_preferred, archive_preferred, stock_allowed, "
                f"generated_allowed, or text_card) before it can proceed to compliance"
            )

    return result


def validate_full_contract(contract: dict) -> ValidationResult:
    """Run all validators on a full production contract.

    This is the comprehensive validation entry point. It checks:
    1. Content contract schema
    2. Duplicate IDs (beats, text intents, recipes, segments)
    3. Cross-document referential integrity
    4. Required beat coverage in segments
    5. Evidence references
    6. Capture policy consistency
    7. Compliance coverage (if present)
    8. Hash integrity
    9. Legacy capture classification
    10. No positional fallback
    """
    result = ValidationResult()

    # 1. Content contract schema
    content = contract.get("content_contract", {})
    schema_errors = validate_contract_schema(content, CONTENT_CONTRACT_SCHEMA)
    result.add_errors(schema_errors)

    beats = contract.get("beats", [])
    text_intents = contract.get("text_intents", [])
    media_recipes = contract.get("media_recipes", [])
    edit_segments = contract.get("edit_segments", [])

    # 2. Duplicate IDs
    beat_dupes = find_duplicate_ids(beats, "beat_id")
    for d in beat_dupes:
        result.add_error(f"Duplicate beat_id: {d}")

    ti_dupes = find_duplicate_ids(text_intents, "text_intent_id")
    for d in ti_dupes:
        result.add_error(f"Duplicate text_intent_id: {d}")

    mr_dupes = find_duplicate_ids(media_recipes, "media_recipe_id")
    for d in mr_dupes:
        result.add_error(f"Duplicate media_recipe_id: {d}")

    seg_dupes = find_duplicate_ids(edit_segments, "segment_id")
    for d in seg_dupes:
        result.add_error(f"Duplicate segment_id: {d}")

    # 3. Cross-document referential integrity
    result.add_errors(validate_text_intent_beat_references(text_intents, beats))
    result.add_errors(validate_recipe_beat_references(media_recipes, beats))
    result.add_errors(validate_segment_beat_references(edit_segments, beats))

    # 4. Required beat coverage
    coverage_result = validate_required_beat_coverage(beats, edit_segments)
    result.add_errors(coverage_result.errors)

    # 5. Evidence references
    evidence_result = validate_evidence_references(beats)
    result.add_errors(evidence_result.errors)

    # 6. Capture policy consistency
    result.add_errors(validate_capture_policy_consistency(beats, media_recipes))

    # 7. Compliance coverage (if present in contract)
    compliance = contract.get("compliance_coverage", [])
    if compliance:
        comp_result = validate_compliance_coverage(compliance, beats)
        result.add_errors(comp_result.errors)

    # 8. Hash integrity
    expected_hash = contract.get("writer_contract_hash", "")
    if expected_hash:
        writer_contract = {
            "platform_content": content.get("platform_content", []),
            "beats": beats,
            "primary_audience_action": content.get("primary_audience_action", ""),
            "capture_policy": content.get("capture_policy", ""),
        }
        hash_result = validate_hash_integrity(expected_hash, writer_contract)
        result.add_errors(hash_result.errors)

    # 9. Legacy capture classification
    legacy_result = validate_legacy_capture_classification(beats)
    result.add_errors(legacy_result.errors)

    # 10. No positional fallback
    result.add_errors(validate_no_positional_fallback(edit_segments))

    return result