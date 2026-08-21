# DIVERGENCE-028 — Pipeline-first creative workflow vs persistent Story Room

**Filed:** 2026-08-21
**Filed by:** Architect from operator direction given 2026-08-02 and confirmed 2026-08-21
**Status:** RATIFIED WITH CONTROLLED-CUTOVER CONDITIONS by AMENDMENT-020
**Type:** STRATEGIC / STRUCTURE / LOGIC
**Related:** AMENDMENT-003, AMENDMENT-006, AMENDMENT-007, AMENDMENT-012, AMENDMENT-013, AMENDMENT-014, DIVERGENCE-017, `docs/mockups/story-room-experience-v1.html`

## Operator evidence

The operator reported that direct collaboration with the builder repeatedly produces better work than the staged ViralFactory pipeline, which regularly breaks and asks for judgment too late. The requested return to first principles was:

- help a person tell a story rather than operate a pipeline;
- use a chat-like experience at each stage;
- arm the LLM with the skills and approved insight developed with the human;
- break creation into intelligible elements such as input, lens, frame, style, and hook;
- ask only the questions needed to build shared understanding;
- preserve Inspiration as the place where observations can be carried into a story.

The architect produced an interactive Desk → Inspiration → Story Room → Knowledge → Results concept. On 2026-08-21 the operator reviewed it and ruled: **“yes this direction is good.”**

## Current conflict

Charter v3.11 and the implementation organize creative work as separate queues and pages. Gate 1 approval automatically enqueues the Writer; the operator receives a large generated draft later. The creative entity is split across `idea_cards`, `drafts`, `assets`, production sessions, component decisions, composition plans, and publish records. The useful production contracts are strong, but the human experience automates away the conversation that establishes the claim, frame, lived stake, and taste.

The approved direction conflicts with current constitutional language that makes the staged pipeline the primary operator-facing core loop and with the current navigation contract (`Home · Inspiration · Pipeline · Knowledge · Results · Setup`). It therefore cannot be implemented as a template redesign or route alias without an amendment.

## Ruling

AMENDMENT-020 ratifies a **controlled Story Room redesign**:

1. One persistent Story Room becomes the target primary creative workspace for each piece.
2. Conversation is the control surface; versioned artifacts and explicit locks are the durable truth.
3. The front-stage creative progression is **Brief → Idea → Shape → Draft → Build**.
4. Existing Source Bank, modules, provenance, component workbench, immutable manifest, CompositionPlan, RendererSpec, Gate 3, Gate 4, Buffer, metrics, and gated learning remain the backstage tool bench.
5. Creative automation may not cross a new judgment boundary after the last human lock. Mechanical work may continue; new creative choices pause or appear as explicit assumptions.
6. The legacy pipeline remains available until a controlled three-piece comparison and deep UI review prove the Story Room better. No destructive migration or big-bang cutover is approved.

## DIVERGENCE-017 resolution

DIVERGENCE-017 is **superseded by this ruling**.

- “Take to Story Room” is approved as the Inspiration action.
- The exact Inspiration item and observation must be linked by typed IDs and retained as evidence.
- The action creates a room/input record and asks what the operator sees in the observation. It must not immediately generate a polished idea and treatment before the human establishes why the observation matters.
- `inspiration` remains valid compatibility provenance for existing idea cards, but new Story Rooms use append-only contribution provenance because one story can combine a human seed, an Inspiration observation, research, and AI development.
- Format/mechanic learning remains an explicit proposal into the existing gated Format Guide/process system.

## Non-goals

- No deletion of legacy tables or routes in the first slice.
- No new global chat spanning every piece.
- No separate chat per stage.
- No schema-first creative UI.
- No replacement of the production/approval harness.
- No weakening of per-piece publish approval.

## Proof required before primary cutover

Compare three real pieces in Story Room mode against the current pipeline baseline:

1. a human-seeded carousel;
2. a source-led Reel;
3. a half-formed personal story.

Record human recognition, time to first good draft, number and locality of corrections, intent survival, recovery from one failed tool, operator comprehension, final publishable completion, and all 10 UI dimensions. The operator—not automated metrics—decides whether Story Room becomes the default and whether legacy batch mode remains.
