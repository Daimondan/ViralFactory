# AMENDMENT-018 — Versioned visual treatments may coexist; one treatment governs a piece

**Filed:** 2026-07-30
**Filed by:** Architect
**Status:** APPROVED WITH CONDITIONS — ratifies DIVERGENCE-025
**Ratifies:** `docs/decisions/DIVERGENCE-025-fitzroy-vector-film-style-request.md`
**Amends:** AMENDMENT-015 §3; Visual Style and Format Guide contracts
**Type:** STRATEGIC / STRUCTURE

## Decision

Approve the operator's 2D-vector Fitzroy direction as a **new, versioned Tier-1 visual treatment**, not as a silent rewrite of the existing cinematic treatment and not as an isolated Tier-2 exception.

AMENDMENT-015's useful invariant remains: Tier 1 world subjects and Tier 2 renderer graphics are different layers. Its global prohibition on a vector Tier-1 subject is replaced by a piece-scoped rule:

> One approved Tier-1 treatment governs every world subject in a piece. Tier 2 remains deterministic renderer graphics. A piece may not mix incompatible Tier-1 treatments unless an approved treatment explicitly defines the transition.

## Generic treatment contract

The Visual Style module gains versioned `visual_treatments` entries. Each entry declares:

- stable treatment ID and version;
- human description and approved reference set;
- palette, line/texture/lighting rules, and prohibited characteristics;
- allowed formats/artifact classes;
- character/location continuity requirements;
- Tier-1 generation rules and Tier-2 overlay relationship;
- disclosure requirements;
- status and provenance.

The Format Guide production binding or Gate-1 treatment selects an exact `visual_treatment_ref`. That exact version is carried through requirements, candidates, manifest, CompositionPlan, RendererSpec, Gate 3, and provenance. It is visible as a badge on review surfaces. Any treatment change invalidates downstream approvals.

Python may validate IDs, versions, hashes, palette membership where an exact palette is declared, dimensions, and manifest consistency. It may not decide which aesthetic suits an idea.

## StackPenni application

1. Preserve the current cinematic-painted treatment and its existing assets as a valid treatment; do not delete or rewrite history.
2. Propose a `flat_vector_pennifold` treatment using the operator's comparison specification: outline `#1D1C21`, cream `#FCF8E4`, deep navy `#0E1A2F`, gold `#D9A93F`, warm wood brown `#8A5A2B`, warm-brown skin tones, and the approved newspaper-grey swatch; no teal, turquoise, coral, pink, gradients, texture, grain, or generated text/signage.
3. The five comparison outputs (room, Fitzroy, Stacks, blank newspaper, controller) enter the registry only as **proposed candidates** under that treatment. Mechanical palette lock is evidence, not approval.
4. `episode-format-parable` v1 remains cinematic. A future vector episode requires an operator-gated module/version or Format Guide binding that selects the vector treatment. No existing piece is migrated.
5. Within a vector piece, characters and locations use the vector treatment consistently; renderer captions/cards/watermarks remain Tier 2 and may use the same palette without becoming world subjects.
6. Gate 3 shows the treatment name/version and exact reference lineage. It does not require a per-piece realism-vs-vector bake-off once the treatment was selected and approved at Gate 1; changing treatment returns upstream.

## Definition of Done

- Visual Style schema and module gate support multiple versioned treatments.
- Gate-1 treatment selects and persists one exact treatment; Format Guide may supply a default that remains operator-editable before approval.
- Candidate/manifest/CompositionPlan/RendererSpec lineage carries the exact treatment and hashes.
- Operator gates the StackPenni vector treatment and each canonical reference candidate; no bootstrap or migration self-approves.
- Two treatment fixtures render visibly different world layers with zero Python changes.
- Mixed or stale treatment inputs fail closed.
- DIVERGENCE-025 is marked ratified and BUILDER-NOTE-020 is processed only after the gate-ready proposal exists.
