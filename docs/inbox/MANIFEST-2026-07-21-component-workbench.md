# MANIFEST — 2026-07-21 — Pre-assembly Component Workbench

**Status:** APPLY
**Owner:** Builder (`viralfactory` / vf-coder)
**Constitution:** `docs/CHARTER-v3.9.md`
**Decision:** AMENDMENT-013

## Canonical files — read in this order

1. `README.md`
2. `docs/CONTEXT.md`
3. `docs/CHARTER-v3.9.md`
4. `docs/decisions/DIVERGENCE-018-pre-assembly-component-workbench.md`
5. `docs/decisions/AMENDMENT-013-pre-assembly-component-workbench.md`
6. `docs/reviews/REVIEW-pipeline-runtime-and-component-workbench-2026-07-21.md`
7. `docs/plans/2026-07-21-pre-assembly-component-workbench.md`
8. `BUILD_PLAN.md` — M15 / VF-CW-001..012
9. `docs/PROGRESS.md`
10. `CHANGELOG.md`
11. relevant production playbooks and prior AMENDMENT-009/010/011

## Apply order

- **Foundation:** VF-CW-001 → 002 → 003 → 004
- **Candidate producers:** VF-CW-005 → 006 → 007 → 008
- **Operator boundary:** VF-CW-009 → 010
- **Consumption and gate:** VF-CW-011
- **Orchestration and proof:** VF-CW-012
- **Then only:** VF-VS-516 → VF-VS-702 → VF-VS-703

VF-VS-515 is superseded and must not be implemented.

## Invariants to prove throughout

- one tenant-scoped production session per platform asset;
- exact immutable candidate versions and append-only decisions;
- config/prompt-driven requirements, no creative keyword judgment in code;
- category completeness distinct from candidate approval;
- immutable manifest contains every materially used component and upstream hash;
- assembler accepts only current `manifest_id`, never mutable/latest inventory;
- ingredient changes create a new manifest/render and invalidate Gate 3;
- Gate 3 validates current final + manifest + blocking evidence server-side;
- human waits are persisted states, not long-running jobs;
- operator routes and autonomous chain call the same orchestrator/services;
- exact final Gate 3 and Gate 4 no-auto-publish remain intact.

## Proof package

Automated tests alone are insufficient. Provide:

- RED→GREEN behavior for every audit defect;
- full suite result;
- fresh port-9121 Reel with multiple candidates in configured categories;
- operator selection and regeneration lineage;
- service restart while waiting for component review;
- immutable manifest and exact consumed hashes;
- final review evidence and Gate 3 lineage;
- post-assembly component change creating a new manifest/render and invalidating approval;
- Gate 4 hold, no publish;
- deep laptop + mobile UI review across the 10 dimensions;
- zero credentials in logs, DB excerpts, fixtures, or handoff.

## Inbox processing

After reading and beginning this work order, move both files to `docs/inbox/processed/` in the builder's first task commit:

- `docs/inbox/ARCHITECT-NOTE-2026-07-21-component-workbench.md`
- `docs/inbox/MANIFEST-2026-07-21-component-workbench.md`

Do not move DIVERGENCE-017; it remains a separate pending architect decision.
