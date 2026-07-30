# VF-VIS-1616 — Exact visual-treatment lineage proof

**Date:** 2026-07-30
**Status:** Implemented and focused-tested

## Contract

A supplied `visual_treatment_ref` contains exactly:

- `treatment_id`
- `version`
- `treatment_hash` (SHA-256 of the canonical treatment contract)

Gate 1 resolves the supplied reference against the current tenant Visual Style module and requires the treatment to be approved. A stale version, unknown treatment, bad hash, or proposed treatment fails closed.

## Boundaries covered

- Gate 1 card treatment selection and approval re-resolution
- production session persistence
- component requirements
- candidate generation provenance (central `CandidateStore` stamping)
- manifest top-level and per-candidate lineage
- CompositionPlan
- RendererSpec identity and preconditions
- Gate 3 readiness and decision record
- writer-contract hash sensitivity

Legacy sessions with no selected treatment remain backward-compatible. Once a treatment is selected, missing or mixed candidate lineage blocks manifest freeze and downstream compilation.

## Verification

```text
/tmp/viralfactory-test/bin/python -m pytest -q tests/test_vf_vis_1616_treatment_lineage.py
5 passed

/tmp/viralfactory-test/bin/python -m pytest -q \
  tests/test_vf_cp_004_renderer_spec.py \
  tests/test_vf_ra_001_renderer_spec.py \
  tests/test_vf_cw_011_gate3_service.py \
  tests/test_t11_6_episode_plan.py
115 passed
```

The integration fixture verified that a treatment-bound session stamps the exact ref into candidate provenance and manifest output, then rejects the same candidate after its ref is removed.

## Remaining operator boundary

The existing StackPenni cinematic module is still the legacy v1 Visual Style document and remains valid for existing assets. The submitted `flat_vector_pennifold` treatment is a separate pending proposal; it is not selected or approved by this implementation.
