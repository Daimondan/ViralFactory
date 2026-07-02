# AMENDMENT-003 — Staged Content Pipeline (four content gates)

*Repo location: `docs/decisions/AMENDMENT-003-staged-content-pipeline.md` · Proposed by operator (Daimon), specified by Claude architect · 2026-07-02 · Status: APPROVED by operator — Hermes applies to charter*

## What changes

Charter v3.1 "The core loop" compresses everything between seed and ship into one Draft → React step. The first artifact the operator sees is a complete draft; a weak idea is only discovered after a full piece is written. This amendment expands the loop into a staged funnel with four content gates, so weak candidates die at the cheapest possible point.

**This does NOT reinstate a seven-stage spine.** Titles are properties of idea cards, not a stage. Storyboards are the visual-direction block of a draft, not a stage.

## Replacement text for Charter "The core loop" (charter bumps to v3.2)

1. **Gather** — automated, **configured by onboarding**: the person's onboarding inputs (seed sources, anti-examples) produce the Source Criteria and `sources.yaml`, which dictate what the AI scouts from then on. The Sources Engine ingests and scores every item against those criteria; the continuous loop proposes new sources and criteria amendments through the gate.
2. **Ideas** — generation is **grounded in the living modules**, not just raw source material: AI-originated ideas are produced by crossing Source Bank items with the Viral Patterns, Audience Insights, Story Frameworks, and Format Guide modules. Cards come from three origins, each tagged with provenance:
   - **ai-originated:** AI proposes from the Source Bank × modules
   - **human-seeded:** the person's raw seed (spoken or typed; messy is fine)
   - **human-seeded, ai-developed:** the person's seed sharpened by AI — angle variants proposed, supporting Source Bank material attached. This is the primary path; the person supplies sparks, never finished ideas.
   Each card carries: the idea, its hook/title options, suggested format, origin, and evidence links.
   **GATE (rigorous):** approve / kill / park per card. The funnel kills most here — by design. Kill reasons logged to the Feedback Log.
3. **Draft** — AI, all modules loaded, self-audited against the Tells Checklist. A draft is: **full text in voice + light visual direction** (image prompts, reference notes, shot/format choices per the Visual Style Guide). **No rendered images at this stage** — visual direction is text; render cost is only spent on survivors. *(Amendable: if co-production evidence shows drafts can't be judged without pixels, a single rough reference render per draft may be added via a future amendment — evidence first.)*
   **GATE (the human pass, unchanged from v3.1):** react via chips + text and/or direct edits (authoritative, highest Feedback Log weight); AI revises; **ship-forward or kill.**
4. **Assets** — for surviving drafts only: real images generated per the visual direction, captions rendered, the piece fanned out into per-platform variants (X thread, IG carousel/reel, …).
   **GATE (quick, per platform):** approve / fix / kill per variant, side by side.
5. **Publish** — **every piece passes human approval before posting. No auto-publish, ever, at any trust level. Hard rule.** Go/hold + timing only; everything upstream is already approved. Approved pieces flow to Postiz for scheduling, posting, and metrics.
6. **Learn** — unchanged (inward weekly loop + outward continuous loop).
7. **Improve** — unchanged (gate-approved proposals bump modules; every future draft inherits).

Gate intensity tapers: Ideas is rigorous, Draft is the deep human pass, Assets is quick, Publish is go/hold. All four feed the same async gate queue (DIVERGENCE-001 rules apply: age visible, superseding, no pressure mechanics).

## Provenance requirement

`origin` (ai-originated | human-seeded | human-seeded-ai-developed) travels with a piece from idea card to Results. The nightly performance note records it, so the inward loop can answer: do the operator's seeds outperform AI-originated ideas? This is a measurable claim of the whole product thesis — it must be instrumented from the first piece.

## Diagram + docs updates (Hermes)

- `docs/diagrams/README.md`: update the System Overview and Mermaid to insert IDEAS (gate) before DRAFT and ASSETS (gate) between the human pass and the publish queue.
- Regenerate/replace `docs/stackpenni_v3_system_with_onboarding.png` or mark it superseded by the README diagrams.
- `docs/CONTEXT.md`: mirror the new loop (conforms-to-charter rule).
- `docs/UI-DIRECTION.md`: Surface 2 (Create) gains an Ideas queue view (cards: idea, hooks, origin badge, evidence links, approve/kill/park) and an Assets review view (per-platform variants side by side). Laptop-first per D3.

## BUILD_PLAN impact

- **M2: no change.** Onboarding playbooks proceed exactly as planned.
- **M3 (co-production sprint) absorbs the staged loop:** the sprint's "seed → draft → react → ship or kill" becomes "seed → idea cards → gate → draft (text + visual direction) → react/edit → assets → per-platform gate → ship or kill." Hermes adds tasks for: idea card generation + Ideas gate UI; visual-direction block in the draft schema; Assets stage (image generation wired to Visual Style Guide) + per-platform review UI; `origin` field threaded through pipeline tables and the nightly note.
- **M4 (publish) unchanged** — Publish gate semantics identical.

## What is explicitly NOT approved

- No rendered images at Draft (see amendable note above).
- No separate Titles or Storyboard stages.
- No change to the no-auto-publish hard rule, the async gate queue rules, or the learning loops.
