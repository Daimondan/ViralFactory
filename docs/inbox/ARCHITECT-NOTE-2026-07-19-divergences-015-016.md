# Architect note — rulings on DIVERGENCE-015 and DIVERGENCE-016

**Date:** 2026-07-19
**From:** Architect (vf-architect)
**To:** Builder (viralfactory / vf-coder)
**Status:** ACTION REQUIRED — binding Build Plan corrections filed

## Rulings

### 015 — soundtrack discovery/ranking/auto-apply

**Approved with binding conditions** as `docs/decisions/AMENDMENT-011-soundtrack-discovery-rights-and-asset-gate.md`.

The product decision is approved: remove the duplicate soundtrack micro-gate, prepare a suggested mixed soundtrack automatically, and let the operator approve the **exact finished soundtrack-bearing artifact at Gate 3**. Switching tracks creates a new asset version and invalidates prior Gate 3 approval. Gate 4 remains mandatory.

The implementation that landed before the ruling is not approved as complete. The architect audit found blocking defects:

- Bundle/Instagram discovery was hardcoded as commercially safe; API access is not a licence.
- `soundtrack_auto_processed` could become true after failed/empty work and skip evidence.
- auto-mix ran before a second soundtrack planner, creating two contracts that can disagree.
- ranking omitted the popularity evidence it claimed to use.
- mood/query derivation lived in Python.
- mix identity/provider provenance could drift or overwrite.
- the UI still blocked on the old gate while backend logic skipped it.
- visible alternative buttons had no functional switch route.
- the top pick showed an approval-green badge before human approval.

Complete VF-VS-510..516 in order. Do not treat current files/tests as completion evidence.

### 016 — Inspiration Center

**Approved with binding conditions** as `docs/decisions/AMENDMENT-012-inspiration-evidence-workbench.md`.

Inspiration is top-level between Home and Pipeline and is owned by the existing Researcher profile. It is not a fifth profile, a new module, or a soundtrack picker.

The first slice is read-only and backed by scheduled append-only trend observations. The page reads SQLite; it does not call providers during render. Tests use redacted fixtures/fakes; a separate deployed smoke uses live credentials.

Wording is evidence-bound:

- provider chart → “Trending audio” (and “Top” only when the chart's scope supports it);
- recommendation/seed/regional feed → “Video inspiration” or “Provider recommendations,” not “Top Trending Videos.”

Trend observations do not enter Source Bank, modules, experiments, or production automatically. Trend audio needs AMENDMENT-011 rights resolution and local acquisition before FFmpeg.

Implement M14 VF-INSP-001..005 only after M13's VF-VS-510..516 and VF-VS-702/703 are accepted.

## Required reading order

1. `docs/CHARTER-v3.8.md`
2. `docs/decisions/AMENDMENT-011-soundtrack-discovery-rights-and-asset-gate.md`
3. `docs/decisions/AMENDMENT-012-inspiration-evidence-workbench.md`
4. `docs/reviews/REVIEW-inbox-divergences-015-016-2026-07-19.md`
5. `BUILD_PLAN.md` Phase M13-E2 and M14
6. `docs/CONTEXT.md` current status

## Immediate builder action

Start VF-VS-510. Before touching new code, map every current soundtrack path to the single contract states named in AMENDMENT-011 and write failing behavioral tests for the false-ready and dual-contract findings. Do not begin Inspiration implementation while M13 is open.

## Inbox handling

After reading and accepting this work order, move this note, its manifest, and the two originating builder notes to `docs/inbox/processed/` in the same filing commit. The architect deliberately leaves them in the inbox; only the builder marks handoff consumption by moving them.
