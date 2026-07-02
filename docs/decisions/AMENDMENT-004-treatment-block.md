# AMENDMENT-004 — Treatment block on idea cards (v2, revised per operator direction)

*Repo location: `docs/decisions/AMENDMENT-004-treatment-block.md` · Proposed by Claude architect, revised per operator direction (Daimon) 2026-07-02 · **Status: APPROVED by operator (Daimon) 2026-07-02 — Hermes applies to charter.***

## What changes

Charter v3.2 gives each idea card a single "suggested format" field. That undersells the real decision made at the Ideas gate. Every idea needs a **treatment**: how the concept becomes a piece — its scope, its format, whether the human must gather raw material first, and how it may be reused. This amendment expands "suggested format" into a treatment block on the card. **No new stage, no new gate.** The four-gate funnel from AMENDMENT-003 is unchanged.

**Sequencing ruling (operator question resolved):** treatment rides ON the card and is approved WITH the idea at Gate 1 — not developed after idea approval. Rationale: approving an idea without its treatment is approving blind of its cost (a six-part street-interview series and a single carousel are different commitments of the human's time). Treatment is LLM text — cheap enough to generate for cards that die. UI mitigation: cards display a compact treatment line (scope · format · capture flag) so weak cards are fast to kill; the full treatment expands on demand.

**Per-platform ruling (operator question resolved):** the Draft stage produces ONE master script (in voice, with visual direction) in the treatment's chosen format; the human's deep pass happens on the master. Per-platform fan-out happens at Assets, AFTER the human pass, per AMENDMENT-003 — so the human reviews one thing deeply and N variants quickly, and edits propagate from one source. Fan-out before the human pass is explicitly rejected (multiplies review load, spends variant effort on drafts that may die).

## The treatment block (card schema addition)

1. **scope** — `one_off` | `series_of_n` (N + cadence; approval spawns linked child cards sharing `parent_id`) | `pillar_with_derivatives`.
2. **format** — a Format Guide entry (existing, or a new experimental entry debuting on this card — see below). Never an unrecorded free-typed value.
3. **capture_required** — `none` | list of human capture tasks (e.g. "record 4–6 street interviews on X"). Formats declare their capture needs in the guide; the treatment instantiates them.
4. **reuse** — optional `derived_from` link + reuse notes. v1 is linkage only.
5. **rationale** — short paragraph: why this scope + format for this idea and audience, citing the modules consulted. The human judges the reasoning, not just the conclusion.

The human may edit any part at Gate 1 (direct-edit authority per D1), including proposing a different format or scope — co-ideation is the treatment block plus existing edit rights.

## Format experimentation (operator-directed mechanism)

The system is expected to have ideas of its own about formats and to experiment — gated once, not queued twice:

- **New formats debut inside treatments.** When the outward loop identifies a working format in the domain, or the system conceives one, it may propose that format directly on a card, flagged `experimental: true`, carrying the full format spec (what it is, structural mechanics, capture needs, effort) and its evidence (outward-loop examples, or reasoning if AI-conceived).
- **One approval, two effects.** The human approving that card's treatment green-lights the experiment AND admits the format to the Format Guide automatically — recorded as `status: experimental`, provenance pointing at the debut card. No separate format-approval queue exists.
- **Graduation by evidence.** The inward loop promotes experimental formats to `proven` or proposes retirement based on results, through the normal module-update gate.
- **The invariant that survives:** no format is ever used without (a) landing in the Format Guide and (b) passing the human gate. "No inventing on the fly" means no unrecorded, ungated formats — not no new formats.

## Format learning (both loops, made explicit)

- **Inward:** the nightly performance note records `format` and `scope` alongside `origin` per piece; the weekly loop learns the operator's format × messaging × audience performance and proposes Format Guide updates through the gate.
- **Outward:** the continuous loop decomposes viral content in the domain into format mechanics — what format, how it is structured, for what messaging, for which audiences — and proposes new entries or updates to existing ones. The Format Guide is a living map of exactly how formats work for this business; this specificity is a defensibility asset.

## Pipeline state: awaiting-capture

Cards approved with `capture_required ≠ none` enter **awaiting-capture** between Gate 1 and Draft. Capture uploads flow through the existing materials intake; audio is transcribed via the T2.6 path and the transcript becomes draft input. The console shows awaiting-capture cards with outstanding tasks — same no-pressure rules as the async queue.

## Charter impact (v3.2 → v3.3 on approval)

In "The core loop" step 2, replace the card-contents sentence with: "Each card carries: the idea, its hook/title options, a **treatment** (scope, format from the Format Guide — including experimental formats debuting on the card, capture-required tasks, reuse links, rationale), origin, and evidence links. Cards approved with outstanding capture tasks wait in **awaiting-capture** until the human supplies the material through the materials intake; only then do they flow to Draft."

In the provenance requirement paragraph, add `format` and `scope` alongside `origin`.

In step 3 (Draft), no text change — this amendment affirms the existing master-draft-then-fan-out order.

## BUILD_PLAN impact

- **M2 (time-sensitive):** T2.3's Format Guide starter schema gains: `requires_human_capture` (+ capture type), `effort_level`, `best_for`, `platforms`, `reuse_pathways`, `status` (proven | experimental | retired), `provenance` (origin of the entry, incl. debut card ref). This lands BEFORE the Format Guide module is first built.
- **M3:** idea-card tasks absorb the treatment block (schema + compact treatment line in Gate 1 UI + expandable full view, all editable). New tasks: awaiting-capture state + capture task list + intake hand-off; series spawning (parent/child + cadence); experimental-format debut path (card approval auto-writes the guide entry with provenance); nightly note extended to format + scope.
- **M6 (outward loop):** format-mechanics decomposition added to the loop's analysis scope; its proposals may arrive as guide updates OR as debut-format treatments on new cards.
- **M4:** unchanged. Series cadence hands scheduled dates to the existing Publish gate.

## What is explicitly NOT approved

- No new stage or gate — treatment is a property of the card, decided at Gate 1.
- No per-platform scripts before the human pass — master draft first, fan-out at Assets.
- No automated atomization/repurposing engine in v1 — derivative proposals belong to the inward loop later, evidence first. v1 ships linkage only.
- No unrecorded or ungated formats — every format used exists in the Format Guide and passed the human gate (normal entry or experimental debut).
- No change to the four-gate funnel, the no-auto-publish hard rule, or async queue rules.

## Naming ruling

The capability is called the **treatment** (operator approved). The eight living modules keep their name — the treatment consumes them; it is not a ninth module.
