# MANIFEST — 2026-07-19 — DIVERGENCE-015/016 architect rulings

**Protocol:** `docs/inbox/README.md` manifest-first handoff
**Sender:** Architect (vf-architect)
**Recipient:** Builder (viralfactory / vf-coder)
**Priority:** BLOCKING
**Scope:** documentation/ruling batch only; production corrections are now actionable tasks in BUILD_PLAN

## Summary

The architect reviewed both pending inbox notes against Charter v3.7, live implementation, provider/licensing evidence, source architecture, and operator UI rules.

- DIVERGENCE-015: **ratified with binding conditions** as AMENDMENT-011. Product simplification approved; existing pre-ruling implementation rejected as completion proof. VF-VS-510..516 are blocking.
- DIVERGENCE-016: **ratified with binding conditions** as AMENDMENT-012. Top-level Researcher-owned Inspiration workbench approved. M14 follows M13 proof.
- Charter advanced to v3.8 and active docs were aligned.

## Files already filed canonically by architect

| File | Action | Purpose |
|---|---|---|
| `docs/decisions/AMENDMENT-011-soundtrack-discovery-rights-and-asset-gate.md` | READ / GOVERN | Binding soundtrack ruling |
| `docs/decisions/AMENDMENT-012-inspiration-evidence-workbench.md` | READ / GOVERN | Binding Inspiration ruling |
| `docs/CHARTER-v3.8.md` | READ / GOVERN | Current constitution; supersedes v3.7 |
| `docs/reviews/REVIEW-inbox-divergences-015-016-2026-07-19.md` | READ / APPLY | Code/UI/doc findings with evidence |
| `BUILD_PLAN.md` | EXECUTE | New VF-VS-510..516 and M14 VF-INSP-001..005 |
| `docs/CONTEXT.md` | READ | Current operational mirror |
| `README.md` | NONE | Status/reference alignment already applied |
| `docs/PROGRESS.md` | UPDATE AS WORK LANDS | Current blockers already recorded |
| `CHANGELOG.md` | UPDATE AS DECISIONS LAND | Architect decisions recorded; intervening builder decisions still require backfill |
| `docs/decisions/DIVERGENCE-007-source-review-queue-and-network.md` | READ | Status clarified: source gate resolved; source network still open |
| `docs/decisions/DIVERGENCE-015-soundtrack-discovery-ranking-auto-apply.md` | NONE | Status marked ratified |
| `docs/decisions/DIVERGENCE-016-inspiration-center-and-trend-discovery.md` | NONE | Status marked ratified |

## APPLY instructions

1. Read the required files in the order in `ARCHITECT-NOTE-2026-07-19-divergences-015-016.md`.
2. Do not reinterpret or soften the binding conditions in code. A blocked condition requires a new divergence, not an implementation workaround.
3. Execute BUILD_PLAN top-down from VF-VS-510:
   - VF-VS-510 false-ready/dual-contract containment;
   - VF-VS-511 rights + local acquisition contract;
   - VF-VS-512 planner-led search + provider config;
   - VF-VS-513 evidence-honest LLM ranking;
   - VF-VS-514 immutable mixes/alternatives;
   - VF-VS-515 coherent Gate 3 soundtrack UX/state machine;
   - VF-VS-516 fresh behavioral proof;
   - then VF-VS-702/703 fresh M13 proof.
4. Do not start M14 until all preceding M13 proof tasks are accepted.
5. M14 then runs VF-INSP-001..005 in order. The read-only first slice is VF-INSP-001..004; VF-INSP-005 stays disabled until the operator signs off on the read-only walkthrough.
6. Backfill `CHANGELOG.md` for omitted builder decisions since its prior 2026-07-09 endpoint. Do not duplicate routine task logs; record every actual TECH/LOGIC/STRUCTURE/STRATEGIC/OPS/FIX decision with rationale.
7. Preserve per-task commits, tests, PROGRESS entries, and CHANGELOG decisions. No task is done from unit tests alone: run the required deployed/browser proof.
8. When this handoff is consumed, move all four inbox files below to `docs/inbox/processed/` in the same filing commit:
   - `BUILDER-NOTE-015-soundtrack-divergence.md`
   - `BUILDER-NOTE-016-inspiration-center.md`
   - `ARCHITECT-NOTE-2026-07-19-divergences-015-016.md`
   - `MANIFEST-2026-07-19-divergences-015-016.md`

## Hard stop conditions

Stop and file a divergence instead of improvising if:

- a provider exposes audio but no evidence-backed synchronization/republication rights;
- a live provider response does not match the recorded contract;
- ranking evidence is unavailable or incomparable and the design would manufacture a score;
- provider collection would need to run synchronously during page render;
- a recommendation feed would be labelled as a measured trend;
- a trend observation would feed Source Bank, a module, an experiment, or production without an explicit promotion/gate;
- changing the active soundtrack cannot mechanically invalidate the prior exact-asset approval.

## Completion evidence expected in the builder response

For VF-VS-510..516:

- task commits and full test result;
- fresh deployed asset and exact contract/rights/local-artifact/mix/approval hashes;
- browser review covering every soundtrack state at laptop and mobile widths;
- proof that no credentials or signed secrets reached DB/logs;
- no reused old final media or skip-on-connection tests.

For VF-INSP-001..004:

- fixture-driven full test result;
- separate live-provider smoke with secret-free evidence summary;
- proof `/inspiration` makes zero provider calls while rendering;
- DB rows showing exact evidence semantics and repeated observations;
- deep 10-dimension browser review including first-run, empty, stale, partial, failed, unavailable, long-content, and mobile states;
- proof that the first slice has no promotion or production write path.

## Builder response route

After applying each task or filing a blocker, update `docs/PROGRESS.md` and `CHANGELOG.md`. For design blockers, add a numbered divergence under `docs/decisions/` and leave a new builder note + manifest in `docs/inbox/`.
