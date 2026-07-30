<!-- version: 1.0 -->
# Source-Fit Critic — bounded repair

Repair the previous Source-Fit Critic result for this exact card. Do not add
sources, lens IDs, evidence, or fields that are not present below. Correct only
the mechanical findings and preserve uncertainty as `unresolved: true`.

## Card context
{card_context}

## Exact source evidence
{source_evidence}

## Proposed editorial fit
{proposed_fit}

## Mechanical critic findings
{critic_findings}

Return only JSON matching SOURCE_FIT_CRITIC_SCHEMA. This is the one allowed
repair pass; a result that still fails validation is omitted from production.
