# BUILDER NOTE — Start Here: Draft 8 Visual + Soundtrack Pipeline Upgrade

**Date:** 2026-07-18
**From:** Hermes builder
**To:** vf-architect
**Status:** AWAITING ARCHITECT

## Operator ruling

Daimon approved corrected Draft 8 Reel v3 as the visual standard, chose to leave that artifact VO-only, and asked that the proven visual treatment plus explicit future music/SFX handling be promoted into the reusable pipeline only after architect ratification.

## Review these canonical documents

1. Architect review request: [`docs/reviews/REQUEST-architect-review-draft8-pipeline-upgrade-2026-07-18.md`](../reviews/REQUEST-architect-review-draft8-pipeline-upgrade-2026-07-18.md)
2. Full proposed implementation sequence: [`docs/plans/2026-07-18-draft-8-reel-correction-then-pipeline-upgrade.md`](../plans/2026-07-18-draft-8-reel-correction-then-pipeline-upgrade.md)
3. Artifact evidence and operator learning ledger: [`docs/reviews/2026-07-18-draft-8-reel-correction-ledger.md`](../reviews/2026-07-18-draft-8-reel-correction-ledger.md)
4. Prior assembler audit: [`docs/reviews/ASSEMBLER-UPGRADE-BASELINE.md`](../reviews/ASSEMBLER-UPGRADE-BASELINE.md)

## Architect action requested

Please reconcile the proposal with Charter v3.5, completed M10/M11 work, and the assembler baseline. Return a versioned `MANIFEST-*.md` through this inbox that:

- rules on the semantic-event and soundtrack-plan contracts;
- identifies any required amendment/divergence;
- adds ordered task IDs and acceptance criteria to `BUILD_PLAN.md`;
- states which existing tasks are reused, replaced, or superseded;
- preserves the approved Reel as regression evidence without hardcoding its scenes or StackPenni values.

The builder will not implement the reusable runtime upgrade until that manifest is received and processed.
