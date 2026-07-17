# DIVERGENCE-013 — Assembler production-contract boundaries

**Date:** 2026-07-17
**Filed by:** Builder, from operator direction + Assembler Full Upgrade handoff
**Status:** APPROVED WITH CONDITIONS — ratified via AMENDMENT-009, Charter v3.6 (2026-07-17)
**Type:** STRUCTURE / LOGIC

## Summary

Three boundary refinements are required before the Assembler Full Upgrade can change runtime behavior. Each refines a previously approved boundary. None is a blank-slate rewrite; all preserve existing strengths.

## Decision A — Capture semantics

### Current tension

AMENDMENT-006 made capture tasks non-blocking and allowed the Assembler to continue with generated or placeholder media. That is useful for pipeline flow but unsafe when the missing item is evidence, identity, a product, a lived action, or another claim that must be real.

**Live code evidence:** The `generate-media` route (`src/app.py` line 7191) builds media plans from `capture_required` tasks and continues regardless of whether the capture represents evidence. There is no policy distinguishing "missing evidence" from "missing B-roll."

### Proposed rule

Split capture intent into explicit policies:

- `capture_required`: Writer and high-level planning may continue. Final assembly/compliance cannot pass until the specific real capture is registered and mapped. No generated substitute may represent it as evidence.
- `capture_preferred`: real capture is preferred. A declared fallback may be used if it preserves meaning and does not impersonate evidence.
- `archive_preferred`: use approved existing tenant media where possible.
- `stock_allowed`: stock may provide generic context, not evidence.
- `generated_allowed`: generated media is valid as primary support.
- `text_card`: words/graphics are the visual.

### Gate impact

- Gate 1 may approve an idea with outstanding capture.
- Writer may produce the contract and draft.
- Media Planner may produce pending acquisition requirements.
- Rendering may proceed only when required real evidence is available — or the operator returns the treatment through an authoritative decision path and changes the requirement.
- Gate 3 never receives an asset falsely represented as complete.

### What remains unchanged

- AMENDMENT-006's non-blocking capture flag at the idea-card level.
- The operator's authority to override any capture policy via an explicit decision path.

## Decision B — Writer versus Media Planner prompt ownership

### Current tension

AMENDMENT-007 says the Writer produces visual direction including image prompts, while the Assembler performs media-only work. Provider-specific prompts require knowledge of current tools, inventory, references, price, source policy, and provider capabilities. These are Media Planner concerns, not Writer concerns.

**Live code evidence:** `prompts/draft/generate_v3.md` produces `visual_direction` with `image_prompt` fields. The `generate-media` route (`src/app.py` line 7191) then builds its own LLM media plan that writes provider-specific prompts. The Writer's image prompts are not used by the media execution path — they are decorative context.

### Proposed rule

- Writer owns exact approved content and semantic visual/audio intent (what the visual should show, what mood, what evidence — not how to prompt a specific generator).
- Media Planner owns provider-aware acquisition and generation prompts (FAL prompt strings, stock search queries, reference-conditioned prompts).
- Assembler may call LLMs for media/edit judgment but never generates or rewrites approved copy.
- Approved `platform_content` and required text are hash-locked through assembly/remediation (already required by AMENDMENT-008).

### What remains unchanged

- AMENDMENT-007's core split: Writer produces per-platform text, Assembler is media-only.
- The Writer's semantic visual intent still guides the Media Planner's choices.
- Direct edits remain authoritative.

## Decision C — Production playbook classification

### Current tension

The eight files in `playbooks/` are onboarding procedures that build living modules. The viral-content production playbook (`docs/playbooks/viral-content-production-playbook-v1.md`) is a production process, not an onboarding card. If it appears as an unfiltered ninth onboarding card, the Onboarding UI would show it alongside module-building playbooks, confusing the operator.

**Live code evidence:** `docs/playbooks/viral-content-production-playbook-v1.md` exists but is not registered in the Onboarding UI. `config/processes.yaml` has no entry for it. It is currently a standalone document with no runtime registration.

### Proposed rule

- The eight onboarding playbooks remain onboarding procedures that build living modules.
- The viral-content production playbook is encoded as a versioned Process Registry composition consuming those modules.
- If one directory stores multiple playbook types, add explicit metadata: `playbook_type: onboarding | production | learning`.
- The Onboarding UI filters mechanically on `playbook_type`.

### What remains unchanged

- The content of the production playbook itself.
- The eight onboarding playbooks.

## Decisions D and E — Already ratified (no change required)

### Decision D — Compliance authority

AMENDMENT-008 already ratified: compliance is blocking before `ready_for_operator`, bounded remediation with scope/cost/round limits, approved text is immutable, Gate 3 remains human authority, no compliance state implies publication approval. **No new divergence needed.** The implementation gap (advisory-only review in live code) is an implementation compliance issue, not a design change.

### Decision E — Learning authority

The charter already requires human-gated module updates. Performance analysis may propose diffs but may not apply them automatically. **No new divergence needed.** The implementation gap (no performance/learning code exists) is a schema enrichment + implementation issue.

## Options

1. **Approve all three (A, B, C).** File as AMENDMENT-009, bump Charter to v3.6.
2. **Approve B and C only.** Defer A (capture semantics) for further discussion. Risk: implementation cannot distinguish evidence-required captures from optional ones.
3. **Approve A only.** Defer B and C. Risk: Writer/Media Planner boundary remains ambiguous; production playbook classification stays unresolved.
4. **Reject all.** Keep existing boundaries. Risk: the Assembler Full Upgrade cannot proceed without these refinements.

## Recommendation

Option 1 — approve all three. Each is a refinement of an existing approved boundary, not a new architecture. The operator has already reviewed the handoff and signed the four ratification decisions (A–D) and the learning authority (E) as-is. This divergence formalizes that approval.

## Operator impact

- **A:** Operator sees capture policies on idea cards. `capture_required` items show a blocking indicator until the real capture is registered. Operator can override any policy via an explicit decision.
- **B:** Operator sees Writer output with semantic visual intent (not provider prompts). Media Planner output shows provider-specific prompts separately. No change to Gate 2 review (operator still approves exact text).
- **C:** Operator sees no change to the Onboarding UI. Production playbook appears in the Process Registry, not as an onboarding card.

## Migration concerns

- **A:** Existing idea cards with `capture_required` lists need migration to the new policy field. Additive: default all existing to `capture_required`.
- **B:** Existing drafts with `visual_direction.image_prompt` fields remain readable via the compatibility reader (VF-AU-105). New drafts use semantic intent only.
- **C:** Add `playbook_type` metadata to existing playbook files. Additive: default all eight onboarding playbooks to `playbook_type: onboarding`.

## Acceptance criteria

- [x] Divergence status updated to APPROVED.
- [x] AMENDMENT-009 written, Charter v3.6 created.
- [ ] All living cross-references updated: CONTEXT.md, BUILD_PLAN.md, README.md, PROGRESS.md, CHANGELOG.md, diagrams.
- [ ] Stale current-charter references searched and updated across the repo (excluding historical records).
- [ ] Core-loop diagram matches the new boundaries.

## RULING: APPROVED WITH CONDITIONS (2026-07-17)

**Ratified via AMENDMENT-009 (`docs/decisions/AMENDMENT-009-assembler-production-contract-boundaries.md`), Charter v3.5 → v3.6.**

All three decisions (A: capture semantics, B: Writer/Media Planner, C: production playbook classification) are approved subject to seven binding conditions:

1. **Capture policy is approved with the treatment at Gate 1** — no silent inference or downgrade downstream.
2. **`capture_required` blocks compliance and Gate 3 readiness** — not drafting or planning. Rough previews may render with `preview_only` flag.
3. **Legacy capture tasks are not silently migrated** — mark `legacy_unclassified`, require classification when next entering production.
4. **Hash-lock protects the entire approved Writer contract** — not just `platform_content`, but semantic beats, evidence references, visual/audio intent, capture policy, and primary audience action.
5. **Media Planner may translate intent, not redefine it** — may not change claim, subject, evidence requirement, beats, emotional job, audience action, or capture policy.
6. **Playbook type metadata is required and enforced** — `playbook_type: onboarding | production | learning`; Onboarding UI fails closed on missing metadata.
7. **Process changes remain versioned and human-gated** — same discipline as the eight modules (AMENDMENT-005 R3).

Decisions D (compliance authority) and E (learning authority) require no new transfer of authority — already governed by AMENDMENT-008 and the existing charter.

AMENDMENT-007 §2 "zero LLM text calls" is clarified: "no text generation" means no audience-copy generation. Schema-validated LLM judgment for media planning, edit planning, and compliance review is permitted.