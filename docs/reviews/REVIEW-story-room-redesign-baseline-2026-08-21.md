# Architect Review — Story Room redesign baseline

**Date:** 2026-08-21
**Reviewer:** Hermes (`vf-architect`)
**Repository:** `/home/daimon/ViralFactory`, `main` at `4363900` with pre-existing builder worktree changes preserved
**Scope:** current operator interaction model, current storage/routing boundaries, Story Room prototype, DIVERGENCE-017, and reusable backstage production services
**Verdict:** Product direction approved by operator; controlled Story Room experiment required. Current pipeline remains a baseline/fallback, not the target creative experience.

## Executive finding

The system has accumulated strong production governance but a weak creative boundary. It reliably models many downstream facts—sources, contracts, candidate versions, manifests, composition specs, render evidence, publish records—but it does not persist the shared-understanding conversation that makes a good story. The operator is asked to approve a card, then inspect a large generated draft on another page. Direct agent collaboration performs better because it preserves intent, offers concrete alternatives, asks targeted questions, and supports localized revisions.

This is a product-boundary failure, not only another orchestration bug. The correct response is to put one persistent Story Room in front of the existing harness, not to discard the harness or add more pipeline buttons.

## Findings

### P0-1 — Gate 1 automates away the next creative conversation

`src/app.py:5694-5802` persists the treatment and immediately calls `enqueue_writer_chain()` after approval. The current Ideas UI promises “Approve → drafts & assets run” at `src/templates/ideas.html:251-255`. This turns approval of an initial card into authorization for a large creative call before the person and LLM have collaboratively settled the lived stake, claim, frame, narrative movement, ending, or per-piece style.

**Required correction:** In Story Room mode, locking a Story Map is Gate 1. It may compile the approved treatment, but it must not auto-cross new creative judgments. Drafting begins inside the room from the locked Story Map.

### P0-2 — The creative entity is fragmented instead of versioned as one story

`src/pipeline.py:69-145` stores ideas, drafts, and assets in separate tables with separate state fields. Production then adds another per-platform state aggregate at `src/services/production_orchestrator.py:140-180`. This is appropriate for production execution, but there is no story identity, append-only room history, human-readable artifact lineage, or explicit Known / Assumed / Missing / Locked record.

**Impact:** A correction to the frame has no first-class identity separate from editing an idea row or regenerating a draft. The operator has to reconstruct “what we decided” from several screens and hidden JSON fields.

**Required correction:** Add a tenant-scoped Story aggregate with append-only room events, artifact versions, decisions, and understanding entries. Keep `ProductionSession` separate and reuse it after Build handoff.

### P0-3 — Current Inspiration handoff decides the idea before the person explains the connection

The pending DIVERGENCE-017 path is already implemented locally. `src/app.py:1030-1189` builds a seed string, promotes the observation into a source row, runs the full concept+treatment pipeline, and creates an `origin="inspiration"` idea card. This is explicit rather than autonomous, but it still skips the most valuable human step: what the operator saw and why it matters.

**Required correction:** “Take to Story Room” carries exact observation evidence into a room and asks what the person sees—or offers a few concrete possible uses. Do not manufacture the completed idea/treatment first. DIVERGENCE-017 is superseded by DIVERGENCE-028/AMENDMENT-020.

### P0-4 — No reusable production-conversation ledger exists

Onboarding proves that conversational interaction is already a valid product pattern, but it stores `session_messages` and `ai_replies` as parallel arrays and reconstructs turns by index (`src/app.py:1235-1244`, `1455-1463`). That representation has already been documented as fragile and cannot be copied into production.

**Required correction:** Story Room uses one append-only event table with actor, event type, immutable payload/reference, timestamps, idempotency key, and exact artifact/tool links. Files and research results are first-class events, not prose notes embedded in message strings.

### P1-1 — Navigation still teaches “operate a pipeline”

`src/templates/_nav.html:8-15` exposes Home, Inspiration, Pipeline, Knowledge, Results, Upload, Setup, and Treatments. `src/templates/create.html:31-45` and `src/templates/ideas.html:45-76` reinforce separate queues and gates. The useful lower-level surfaces are visible as destinations rather than tools within a story.

**Required correction:** Target primary navigation is Desk, Inspiration, Stories, Knowledge, Results. Upload belongs in the room composer and utility areas; Treatments belong under Knowledge/Setup. Component Workbench and Composition remain directly inspectable from Build, not top-level destinations.

### P1-2 — The prototype mobile behavior is directionally right but not acceptance-ready

`docs/mockups/story-room-experience-v1.html:198-224` collapses the layout, but at 650px it hides the Understanding map. The approved concept is a product direction, not literal production acceptance.

**Required correction:** Mobile must preserve access to Conversation, Artifact, and Understanding through explicit tabs/drawers. Nothing critical disappears. The 390px proof must verify actual viewport width, horizontal overflow, focus order, composer behavior, and artifact readability.

### P1-3 — The current system has the right backstage tools and must not be rebuilt

The Component Workbench route exists at `src/app.py:10617-10738`, and the ProductionSession contract carries durable human-wait states and exact pointers at `src/services/production_orchestrator.py:140-180`. M15 already supplies candidate decisions, manifest freeze, CompositionPlan, ratification, RendererSpec, and exact Gate 3 boundaries.

**Ruling:** Reuse these services as atomic Build tools. Story Room owns creative shared understanding and human-readable artifact locks; existing services own production execution after exact handoff.

### P1-4 — Existing origin is too narrow for multi-source co-creation

A story may begin with a human thought, carry an Inspiration observation, add Source Bank research, and be sharpened by the AI. One mutually exclusive `origin` value cannot express that lineage.

**Required correction:** New rooms use append-only typed contributions. Preserve a derived primary origin only for compatibility/performance reporting. Existing `origin='inspiration'` records remain valid history and are not destructively migrated.

### P2-1 — Schema-first creative surfaces would repeat the present problem

The current draft page renders per-platform schema fields, audit flags, review-loop rounds, visual direction, and production metadata (`src/templates/draft.html`). This information is useful for transparency, but it is not a shared story-shaping workspace.

**Required correction:** Creative Brief, Idea Map, Story Map, exact copy, and Asset Plan are human-readable live artifacts. Machine contracts are derived after lock and available under technical details/provenance.

## What remains binding

AMENDMENT-020 does not weaken:

- config/module ownership of business values;
- LLM judgment vs deterministic mechanics;
- prompt/schema/validator/provenance requirements;
- exact source and rights evidence;
- direct-edit authority;
- immutable candidate/manifest/composition lineage;
- Gate 3 exact final-artifact approval;
- Gate 4 go/hold and no auto-publish;
- gated learning.

## Implementation order

1. Finish the truthfulness/safety blockers already exposed by VF-PROOF-1618; record the current pipeline as the comparison baseline. Do not begin another legacy-UI polish cycle.
2. Add the Story Room ledger and artifact/lock contracts.
3. Add prompt-backed room orchestration and context views.
4. Build Desk and the two-pane/three-view Story Room shell.
5. Implement Brief → Idea → Shape → Draft collaboration.
6. Compile locked artifacts into current production contracts and hand off Build to existing services.
7. Replace the implemented Inspiration→idea shortcut with exact evidence→room contribution behavior in Story Room mode.
8. Run the three-piece controlled comparison and deep UI review.
9. Ask the operator for the cutover decision; only then change the default navigation/mode.

## Review boundary

No production code or tests were changed or run in this architect pass. The review inspected the live working tree and governing documents. Builder changes already present in the dirty worktree remain untouched and must not be swept into the architect documentation commit.
