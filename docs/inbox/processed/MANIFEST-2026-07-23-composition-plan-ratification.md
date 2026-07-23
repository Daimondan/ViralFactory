# MANIFEST — 2026-07-23 — Composition plan + ratification (AMENDMENT-014)

**Batch:** AMENDMENT-014 / DIVERGENCE-020
**Architect files (do not move until consumed):**

## APPLY order

1. Read `docs/decisions/DIVERGENCE-020-two-phase-composition-plan-and-ratification.md`
2. Read `docs/decisions/AMENDMENT-014-two-phase-composition-plan-and-ratification.md`
3. Read `docs/CHARTER-v3.10.md` (current charter)
4. Read `docs/inbox/ARCHITECT-NOTE-2026-07-23-composition-plan-ratification.md`
5. Read `BUILD_PLAN.md` Phase M15-D (new tasks VF-CP-001..004)

## Files created by architect

| File | Purpose |
|---|---|
| `docs/decisions/DIVERGENCE-020-two-phase-composition-plan-and-ratification.md` | Filed divergence describing the two-phase split |
| `docs/decisions/AMENDMENT-014-two-phase-composition-plan-and-ratification.md` | Ratified amendment with binding clauses |
| `docs/CHARTER-v3.10.md` | Current charter (v3.9 superseded) |
| `docs/CHARTER-v3.9.md` | Marked superseded, preserved for audit |
| `docs/inbox/ARCHITECT-NOTE-2026-07-23-composition-plan-ratification.md` | Builder handoff note |
| `docs/inbox/MANIFEST-2026-07-23-composition-plan-ratification.md` | This file |
| `BUILD_PLAN.md` | Updated: new Phase M15-D, updated M15 header and version |
| `docs/CONTEXT.md` | Updated: composition plan reference |
| `docs/PROGRESS.md` | Updated: AMENDMENT-014 entry |
| `CHANGELOG.md` | Updated: AMENDMENT-014 entry |
| `README.md` | Updated: charter reference |

## Task order

```
VF-CW-010 (manifest freeze)
  → VF-CP-001 (CompositionPlan schema + generator)
    → VF-CP-002 (per-element preview generator)
      → VF-CP-003 (composition ratification surface)
        → VF-CP-004 (RendererSpec compilation from ratified plan)
          → VF-RA-001 (canonical RendererSpec — now depends on VF-CP-004)
```

## Expected proof

- CompositionPlan schema round-trips and is content-hashed.
- Two tenant/format fixtures produce visibly different plans with zero Python edits.
- Per-element previews are generated locally (no provider API).
- Ratification surface shows all element categories with previews.
- `Ratify composition` is enabled only when all previews are generated and all elements trace to approved manifest ingredients.
- Unratified plan cannot compile to RendererSpec.
- Stale plan (spec hash mismatch) cannot compile.
- Full automated suite passes.

## Inbox processing

After reading and applying this batch, move these files to `docs/inbox/processed/`:
- `ARCHITECT-NOTE-2026-07-23-composition-plan-ratification.md`
- `MANIFEST-2026-07-23-composition-plan-ratification.md`