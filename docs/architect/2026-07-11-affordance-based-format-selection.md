# Architect Note: Affordance-Based Format Selection + User Distribution Intent

**Date:** 2026-07-11  
**Author:** Hermes Agent, implementing Daimon's direction  
**Status:** Implemented for architect review  
**Related ruling:** `docs/corrections/CORRECTION-format-selection-living-v1.0.md`

## Operator decision

Daimon rejected deterministic format routing. The Format Guide must be a guide to what each medium enables, not a table assigning content categories to formats. A piece is not required to target both X and Instagram. When unconstrained, the LLM may choose the primary destination; when the user asks for Instagram, or specifically for Instagram Reels, that request is a real constraint and cannot be silently replaced.

In product-facing language the human is the **user**. “Operator” remains valid in architecture and approval-gate language, but persisted request provenance uses `user_request` for clarity.

## Architectural decisions implemented

### 1. Format Guide is descriptive, not prescriptive

`FORMAT_GUIDE_SCHEMA` v2 removes:

- `decision_table`
- `best_for` message-category lists

Each format now requires:

- `audience_experience`
- `native_mechanics`
- `expressive_strengths`
- `limitations`
- `production_demands`
- `performance_evidence` (`platform_prior` or `tenant_data`)
- `aspect_ratio`

Production fields such as skeleton, structure, capture, effort, status, and provenance remain.

The converter emits two stage-appropriate projections from the same gated data:

1. `## Selection profiles` — compact affordances/evidence for treatment selection.
2. `## Formats` — full mechanical entries for drafting and assembly.

There is no generated decision table.

### 2. Concept generation and treatment selection are separate LLM stages

The prior call invented the concept and selected its format simultaneously. That allowed format priors to shape the creative act.

The implemented flow is:

```text
sources + voice + audience
        ↓
ideas/concepts_v1.md → format-neutral locked concepts
        ↓
ideas/treatment_select_v1.md → one primary platform + one primary format
        ↓
idea card persisted for Gate 1
```

For an open or platform-constrained request, concepts are established before format selection. For an exact-format request, the concept stage knows the user constraint so it proposes only ideas that can genuinely work in that medium, but it still defers treatment mechanics to stage two.

Legacy cached/mock outputs that already contain treatments remain accepted as a compatibility seam.

### 3. User distribution intent is explicit

Canonical request contract:

```json
{
  "distribution_intent": {
    "mode": "open | platform_constrained | exact_format",
    "platforms": ["Instagram"],
    "formats": ["Instagram Reel Script"]
  }
}
```

Rules:

- `open`: LLM chooses one primary platform and format.
- `platform_constrained`: LLM chooses a format only within the user-allowed platform list.
- `exact_format`: exactly one platform and one format; substitution is forbidden.
- If an exact format cannot support enough strong source-grounded concepts, return fewer concepts instead of changing destination.

The Ideas UI exposes these three choices. Platform options come from `business.yaml`; format options come from the living Format Guide rather than hardcoded UI constants.

### 4. One primary destination per idea

`IDEA_CARD_SCHEMA.treatment.format` now requires:

- `primary_platform`
- `format_name`
- `constraint_source`: `user_request | llm_selected`
- `selection_reason`
- optional `alternatives_considered`

Cross-platform reuse is optional downstream work. It is not an ideation requirement, and the model is instructed not to manufacture derivatives merely because multiple platforms exist.

### 5. Structured guide data persists beside markdown

Approved format-guide writes now persist:

- `format-guide.md` — human-readable living module
- `format-guide.json` — canonical structured data

Both pass through the same gate-enforced `ModuleStore.store()` call. When overwritten, markdown and JSON sidecars are archived under the module's version directory. `load_json()` reads the sidecar first and retains the legacy fenced-JSON fallback.

### 6. StackPenni migration

The existing StackPenni guide was migrated under Daimon's explicit approval:

- v1.0 → v2.0
- eight formats retained
- decision table removed
- affordances, limitations, production demands, evidence priors, and ratios added
- selection profiles added
- JSON sidecar created
- no undeclared platform added

All evidence currently starts as `platform_prior`; it must not be represented as observed StackPenni performance until tenant analytics support that claim.

## Main files changed

- `src/distribution_intent.py`
- `src/pipeline.py`
- `src/module_store.py`
- `src/app.py`
- `src/templates/ideas.html`
- `src/templates/format_guide.html`
- `prompts/ideas/concepts_v1.md`
- `prompts/ideas/treatment_select_v1.md`
- `prompts/ideas/generate_v1.md` (legacy combined prompt updated for compatibility)
- `prompts/format_guide/analyze_v3.md`
- `prompts/views.yaml`
- `config/processes.yaml`
- `modules/stackpenni/format-guide.md`
- `modules/stackpenni/format-guide.json`

## Invariants for future architect/builder work

1. Do not reintroduce message-type → format routing tables.
2. Do not use `best_for` topic lists as selection authority.
3. Prompts carry selection procedure; the gated Format Guide carries medium knowledge.
4. User constraints override LLM format autonomy.
5. Every idea has one primary destination.
6. Multi-platform derivatives are separate editorial decisions.
7. Platform priors must not be mislabeled as tenant evidence.
8. Drafting/assembly receives the full selected entry; selection receives all compact profiles.
9. No automatic publication follows format selection; Gate 1 remains human-controlled.

## Verification expected before acceptance

- Schema and converter regression tests.
- Distribution-intent normalization tests.
- Flask integration test proving an exact-format request runs concept generation then treatment selection and reaches stage two unchanged.
- Exact assembled context inspection proving all descriptive profiles are present and skeletons/decision tables are absent.
- Full test suite.
- One real LLM experiment comparing open selection with exact Instagram Reel selection.
