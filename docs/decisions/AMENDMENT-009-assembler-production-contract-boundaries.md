# AMENDMENT-009 — Assembler production-contract boundaries

**Filed:** 2026-07-17
**Filed by:** Builder, from operator direction + Assembler Full Upgrade handoff
**Status:** APPROVED WITH CONDITIONS — ratifies DIVERGENCE-013, incorporates into Charter v3.6
**Ratifies:** `docs/decisions/DIVERGENCE-013-assembler-production-contract-boundaries.md`
**Supersedes:** AMENDMENT-006 §2 (awaiting-capture non-blocking flag → refined into explicit capture policies); AMENDMENT-007 §2 (Assembler "zero LLM text calls" → clarified: no audience-copy generation, but schema-validated LLM judgment for media/edit/compliance planning is permitted)
**Related:** AMENDMENT-005 (Process Registry), AMENDMENT-008 (compliance loop)

## What this amends

DIVERGENCE-013 raised three boundary refinements required before the Assembler Full Upgrade can change runtime behavior. After reviewing the live code (`src/produce_chain.py`, `src/app.py`, `config/processes.yaml`, `src/pipeline.py`, `src/assembly.py`, `src/asset_review.py`), the prior amendments (005–008), and the baseline audit (`docs/reviews/ASSEMBLER-UPGRADE-BASELINE.md`), the architect approves all three with binding conditions.

## Architect's findings before ruling

1. **AMENDMENT-006's blanket non-blocking capture is confirmed unsafe for evidence.** `src/app.py` line 7191 (`generate-media` route) builds media plans from `capture_required` tasks and continues regardless of whether the missing capture represents evidence or B-roll. There is no policy distinguishing "missing evidence" from "missing supporting visual." AMENDMENT-006 §2 says capture tasks are "a non-blocking flag on the card" and the Assembler "produces the asset with whatever media it can generate." This is correct for pipeline flow but unsafe for final compliance — a generated image cannot represent a real receipt, product, or lived action.

2. **AMENDMENT-007's "zero LLM text calls" is confirmed too narrow for the Media Planner.** `prompts/draft/generate_v3.md` produces `visual_direction` with `image_prompt` fields. The `generate-media` route (`src/app.py` line 7191) then runs its own LLM media plan that writes provider-specific prompts. The Writer's image prompts are not used by the media execution path. AMENDMENT-007 §2 says "The Assembler makes zero LLM text calls. It is a mechanical assembly stage." But provider-aware media planning requires LLM judgment (which provider, which reference, which shot, which fallback) — this is not "text generation" in the audience-copy sense. The charter language must distinguish audience-copy generation (prohibited) from media-planning judgment (permitted, schema-validated).

3. **The production playbook is unregistered.** `docs/playbooks/viral-content-production-playbook-v1.md` exists but has no `playbook_type` metadata, no Process Registry entry, and no runtime registration. `config/processes.yaml` has no entry for it. If it appears as a ninth onboarding card, the Onboarding UI would confuse the operator. AMENDMENT-005's Process Registry is the correct home.

4. **The baseline audit confirmed all 10 drift claims.** `docs/reviews/ASSEMBLER-UPGRADE-BASELINE.md` verified every finding against live code with exact paths and line numbers. 7 implementation compliance, 1 design change (route→service refactor), 2 schema enrichment.

## Conditions

### Condition 1 — Capture policy is approved with the treatment at Gate 1

The capture policy (`capture_required`, `capture_preferred`, `archive_preferred`, `stock_allowed`, `generated_allowed`, `text_card`) is part of the treatment block approved at Gate 1. The Writer, Media Planner, or Python code may not silently infer, downgrade, or change it downstream.

**Rationale:** AMENDMENT-006 made capture tasks non-blocking to improve pipeline flow. But a blanket "continue with whatever media is available" rule is unsafe when the missing item is evidence, identity, a product, or a lived action. The policy must be an explicit operator decision, not a silent Assembler fallback.

**Implementation:** The treatment block schema gains a `capture_policy` field per capture task. The Writer reads it. The Media Planner reads it. The compliance contract enforces it. No code in the pipeline overrides it.

### Condition 2 — `capture_required` blocks compliance and Gate 3 readiness — not drafting or planning

Writer, VO, media planning, and acquisition preparation may continue with outstanding `capture_required` items. Final compliance cannot pass and Gate 3 readiness cannot be granted until the specific real capture is registered and mapped — or the operator changes the policy through an authoritative treatment revision.

**Rationale:** The divergence's proposed rule contained an internal contradiction: one section says "final assembly/compliance cannot pass" while another says "rendering may proceed only when required real evidence is available." The first is correct; the second would prevent rough previews. A rough preview may be rendered for operator review if clearly marked non-final. It may not use generated or stock media to impersonate the missing evidence, and it may not be presented as Gate 3-ready.

**Implementation:** The compliance validator checks: for every `capture_required` beat, is there a registered real capture ingredient mapped to that beat? If not → `needs_operator_decision`. A rough preview may be rendered with a `preview_only` flag that excludes it from compliance.

### Condition 3 — Legacy capture tasks are not silently migrated

Existing idea cards with `capture_required` lists were created under AMENDMENT-006's non-blocking semantics. They must not silently become hard blockers under the new policy.

**Rationale:** Silently upgrading old records to a stricter policy would block cards that were approved under different rules. The operator should classify them when they next enter production, not retroactively.

**Implementation:** Existing `capture_required` fields are marked `legacy_unclassified` on schema migration. When a card with `legacy_unclassified` captures next enters the Writer or Media Planner, the system prompts the operator to classify each task. New cards use the explicit policy from Gate 1.

### Condition 4 — The hash-lock protects the entire approved Writer contract, not just `platform_content`

AMENDMENT-008 Condition 1 locks `platform_content` (approved text). The Media Planner boundary requires protecting more: exact copy, semantic beats, evidence references, required visual meaning, capture policy, and primary audience action.

**Rationale:** A Media Planner could preserve every word of `platform_content` while visually changing the meaning — substituting a different person, location, or emotional register. Semantic intent needs equal protection.

**Implementation:** The hash covers the full Writer contract layer: `platform_content` + `beats[]` (including `vo_text`, `evidence_refs`, `staged_action`, `visual_intent`, `audio_intent`, `capture_policy`, `primary_audience_action`). Any remediation or planning action that would change these fields is rejected and escalated to `needs_operator_decision`.

### Condition 5 — The Media Planner may translate intent, not redefine it

The Media Planner owns provider-aware acquisition and generation prompts. It may choose providers, shots, stock queries, production prompts, references, fallbacks, and costs. It may not change:

- the claim;
- the subject or identity;
- the evidence requirement;
- required beats;
- the emotional job;
- the audience action;
- the capture policy.

If available media cannot faithfully represent approved intent, the system returns `needs_operator_decision`.

**Rationale:** AMENDMENT-007 says "the Assembler does no text generation." The Media Planner boundary requires clarifying what "text generation" means. Provider-specific media prompts (FAL prompt strings, stock search queries) are not audience-copy generation — they are production instructions to media providers. The Assembler may use LLM judgment for media planning, edit planning, and compliance review as long as it is schema-validated, provenance-logged, and never produces or revises audience-facing content.

**Implementation:** AMENDMENT-007 §2 is clarified: "no text generation" means no generation or revision of audience-facing content (`platform_content`, `beats[].vo_text`, `beats[].text_intents`, captions, overlays). It does not prohibit schema-validated LLM judgment for media planning, edit planning, or compliance review.

### Condition 6 — Playbook type metadata is required and enforced

Every playbook file must carry `playbook_type: onboarding | production | learning` metadata. The Onboarding UI filters mechanically on `playbook_type: onboarding`. A playbook missing valid type metadata must not appear in any UI surface (fail closed).

**Rationale:** The eight onboarding playbooks build living modules. The viral-content production playbook is a runtime composition consuming those modules. If it appears as a ninth onboarding card, the operator sees a production process alongside module-building procedures — a category error. AMENDMENT-005's Process Registry is the correct home.

**Implementation:** Add `playbook_type` to the playbook schema. Mark all eight onboarding playbooks as `onboarding`. Mark the production playbook as `production`. The Onboarding UI filters on this field. The Process Registry is the executable source of truth for production processes; the Markdown playbook documents the process and links to its registry version.

### Condition 7 — Process changes remain versioned and human-gated

The production playbook's Process Registry entry is versioned, provenance-tracked, and gate-only writes — same discipline as the eight modules (AMENDMENT-005 R3). No self-modifying routing. Every run logs the registry version used.

**Rationale:** AMENDMENT-005 established the Process Registry as the "9th module" with gate-only writes. This condition ensures the production playbook follows the same discipline.

## Amendment sections

### Amendment 1: Capture policies

The treatment block approved at Gate 1 carries an explicit capture policy per capture task:

- `capture_required`: the real capture must exist and be mapped before final compliance. No generated substitute may represent it as evidence. Drafting and planning continue; Gate 3 readiness is blocked.
- `capture_preferred`: real capture is preferred. A declared fallback may preserve meaning if it does not impersonate evidence.
- `archive_preferred`: use approved existing tenant media where possible.
- `stock_allowed`: stock may provide generic context, not evidence.
- `generated_allowed`: generated media is valid as primary support.
- `text_card`: words/graphics are the visual.

Gate impact: Gate 1 may approve with outstanding capture. Writer may draft. Media Planner may plan. Rendering for preview may proceed (marked `preview_only`). Gate 3 readiness requires `capture_required` items to be registered and mapped.

### Amendment 2: Writer versus Media Planner

- **Writer owns:** exact approved content, semantic beats, evidence references, required visual meaning, audio intent, capture policy, primary audience action. The Writer does not produce provider-specific media prompts.
- **Media Planner owns:** provider-aware acquisition and generation prompts, stock queries, reference selection, fallback, disclosure, cost estimates. The Media Planner translates approved semantic intent into production instructions. It may not redefine intent.
- **Assembler owns:** local registered ingredient IDs, measured timing, overlays/captions, transitions, audio mix, renderer mechanics, feasibility, compliance evidence. It may use LLM judgment for media/edit planning and compliance review (schema-validated, provenance-logged) but may never generate or revise audience-facing content.

AMENDMENT-007 §2 "zero LLM text calls" is clarified: "no text generation" means no generation or revision of audience-facing content. It does not prohibit schema-validated LLM judgment for media planning, edit planning, or compliance review.

### Amendment 3: Production playbook classification

- The eight onboarding playbooks remain onboarding procedures that build living modules.
- The viral-content production playbook is a versioned Process Registry composition consuming those modules.
- Every playbook file carries `playbook_type: onboarding | production | learning` metadata.
- The Onboarding UI filters mechanically on `playbook_type: onboarding` (fail closed on missing metadata).
- The Process Registry is the executable source of truth. The Markdown playbook documents the process and links to its registry version.

### Amendment 4: Compliance and learning authority (no new transfer)

Decisions D (compliance authority) and E (learning authority) from DIVERGENCE-013 require no new transfer of authority. They are already governed by AMENDMENT-008 and the existing charter. The implementation gaps (advisory-only review in live code, no performance/learning code) are implementation compliance issues, not design changes.

Charter v3.6 clarifies: a noncompliant result may be visible as a blocker or rough preview but must not be shown as a false-green Gate 3-ready asset. If resolving a failure requires changing approved meaning or required evidence, the system returns to the authoritative treatment/draft path.

## What this does NOT change

- **Four content gates** — Ideas (rigorous), Draft (deep human pass), Assets (quick per-platform), Publish (go/hold). All remain.
- **Per-piece approval before publish** — hard rule, unchanged.
- **No auto-publish** — hard rule, unchanged.
- **The Writer/Assembler boundary** — the Writer produces all audience-facing text; the Assembler produces media and may use LLM judgment for planning/compliance but never generates audience copy.
- **AMENDMENT-007's core split** — Writer produces per-platform content, Assembler is media-only. This amendment refines what "media-only" means: no audience-copy generation, but schema-validated LLM planning judgment is permitted.
- **AMENDMENT-008's compliance loop** — the text-boundary firewall, cost guard, and operator visibility conditions remain in full force. The hash-lock is extended to cover the full Writer contract (Condition 4).
- **The treatment block** — still approved at Gate 1, still carries format + scope + capture + reuse + rationale. The capture policy is added as a structured field.
- **Provenance** — every LLM call still logged: input hash, prompt file + version, model, raw output, validated output, verdict, profile.
- **Determinism** — temperature 0 for processing, content-hash caching.
- **The eight living modules** — unchanged. The Process Registry is the 9th module (AMENDMENT-005), not a 9th onboarding playbook.

## What this retires

1. **AMENDMENT-006 §2's blanket non-blocking capture flag** is refined into explicit capture policies. The card still flows through the pipeline, but `capture_required` items block final compliance and Gate 3 readiness until the real capture is registered. The "produce with whatever media it can generate" rule is replaced by "produce with approved fallback media marked as preview if capture is required but not yet available."

2. **AMENDMENT-007 §2's "zero LLM text calls"** is clarified, not removed. "No text generation" means no audience-copy generation. Schema-validated LLM judgment for media planning, edit planning, and compliance review is permitted and required for the Assembler Full Upgrade.

3. **The unregistered production playbook** is retired as a standalone document with no runtime registration. It is registered in the Process Registry with `playbook_type: production` metadata.

## Implementation order (for BUILD_PLAN)

The Assembler Full Upgrade implementation plan (`02-IMPLEMENTATION-PLAN.md` from the handoff) proceeds in order. The conditions above are binding constraints on that implementation:

1. **VF-AU-101 (Contract schemas):** The contract schema includes `capture_policy` per beat. The hash-lock covers the full Writer contract layer (Condition 4).
2. **VF-AU-102 (Validators):** Cross-document validators enforce `capture_required` blocking (Condition 2). Legacy classification migration (Condition 3).
3. **VF-AU-104 (Writer prompt v4):** The Writer produces semantic visual/audio intent, not provider-specific prompts. Capture policy travels from treatment.
4. **VF-AU-201 (Process Registry):** Retire `draft/generate_v2.md`, `fan_out_v2.md`, `structure_v1.md` from active runtime. Register Writer v4, media plan v2, edit plan v2, compliance, remediation, performance analysis. Production playbook registered with `playbook_type: production` (Conditions 6–7).
5. **VF-AU-203 (Media planning service):** Media Planner translates approved intent into provider-aware prompts. May not redefine intent (Condition 5). LLM judgment is schema-validated.
6. **VF-AU-402 (Blocking compliance):** `capture_required` blocks compliance (Condition 2). Rough preview may render with `preview_only` flag.
7. **VF-AU-502 (Analyst process):** Derived ratios (comment-to-like, share-to-like, save-to-like) are evidence inputs, not automatic routing rules (Decision E — no new transfer of authority).

## Charter text to update

In CHARTER-v3.6, the following sections change:

### Core loop §2 (Ideas)

After "capture-required tasks, reuse links, rationale), origin, and source_refs":
> — add: ", **capture policy** (capture_required, capture_preferred, archive_preferred, stock_allowed, generated_allowed, or text_card per capture task, approved with the treatment at Gate 1)"

After "Cards approved with outstanding capture tasks carry a non-blocking capture flag":
> — replace with: "Cards approved with outstanding `capture_required` tasks carry a blocking capture flag for final compliance — drafting, VO, media planning, and preview rendering may continue, but Gate 3 readiness is blocked until the real capture is registered and mapped, or the operator changes the policy through an authoritative treatment revision. (AMENDMENT-009)"

### Core loop §4 (Assets)

After "The Assembler does no text generation":
> — replace with: "The Assembler does no audience-copy generation — it receives finished per-platform text and semantic intent from the Writer and produces media, edit plans, and compliance evidence. The Media Planner owns provider-aware acquisition and generation prompts, translating approved semantic intent into production instructions. It may use schema-validated LLM judgment for media planning, edit planning, and compliance review, but may never generate or revise audience-facing content. (AMENDMENT-009)"

### Design rules

After the AMENDMENT-007 rule about "The Writer produces all per-platform text; the Assembler does no text generation":
> — update to: "**The Writer produces all per-platform text and semantic intent; the Assembler does no audience-copy generation.** The Media Planner owns provider-aware production prompts and may use schema-validated LLM judgment for media planning, edit planning, and compliance review. It may never generate or revise audience-facing content. (AMENDMENT-007, clarified by AMENDMENT-009)"

Add new design rules:
> - **Capture policy is approved with the treatment at Gate 1.** `capture_required` blocks final compliance and Gate 3 readiness; drafting and planning continue. No generated substitute may represent required real evidence. The operator may change the policy through an authoritative treatment revision. (AMENDMENT-009)
> - **The hash-lock protects the entire approved Writer contract** — not only `platform_content` text but semantic beats, evidence references, visual/audio intent, capture policy, and primary audience action. Any remediation or planning action that would change these fields is rejected and escalated. (AMENDMENT-009)
> - **Production playbooks are Process Registry compositions, not onboarding cards.** Every playbook carries `playbook_type: onboarding | production | learning` metadata. The Onboarding UI filters mechanically on `playbook_type: onboarding` and fails closed on missing metadata. (AMENDMENT-009)

### The Onboarding Engine section

After "The eight playbooks: Business Profile intake · Voice Profile builder · Sources Engine · Viral Patterns starter · Audience Insights · Story Frameworks · Format Guide · Visual Style intake.":
> — add: "Production processes (e.g., the viral-content production playbook) are versioned Process Registry compositions consuming those modules, not ninth onboarding cards. Every playbook carries `playbook_type` metadata distinguishing onboarding from production from learning. (AMENDMENT-009)"

In CONTEXT.md:

- Update the Core Loop diagram to show capture policy on the idea card and the Media Planner as a distinct role between Writer and Assembler.
- Update the capture description (non-blocking flag → explicit capture policies with `capture_required` blocking compliance).
- Update the Assembler description (media-only → no audience-copy generation; LLM planning judgment permitted).
- Add the Media Planner role to the four-role nav table (or note it as a sub-role of the Assembler).
- Add `playbook_type` to the playbook schema description.