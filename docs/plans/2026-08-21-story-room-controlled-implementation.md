# Story Room controlled implementation plan

**Date:** 2026-08-21
**Authority:** DIVERGENCE-028 / AMENDMENT-020 / Charter v3.12
**Builder source of truth:** M17 in `BUILD_PLAN.md`
**Mode:** additive experiment first; no destructive migration or default cutover

## Target invariant

One persistent Story Room carries a piece from unfinished thought to publish, while exact versioned artifact locks feed the existing production and gate machinery without audience-copy drift.

## Dependency order

```text
Legacy truthfulness baseline
        ↓
Story identity + append-only room ledger
        ↓
Artifact versions + locks + understanding map
        ↓
Context views + prompt-backed room turn service
        ↓
Desk + Story Room shell
        ↓
Brief → Idea → Shape
        ↓
Collaborative Draft + exact copy lock
        ↓
Asset Plan → existing production tool bench
        ↓
Three-piece comparison + deep UI proof
        ↓
Operator cutover decision
```

## Phase A — Preserve a truthful baseline

1. Close the mobile-overflow, truncated-VO, Buffer contract, and full-suite proof blockers already recorded under VF-PROOF-1618/issue #5.
2. Record the legacy pipeline path and timings as the comparison baseline.
3. Stop cosmetic expansion of the old pipeline. Only safety, truthfulness, shared-service, and proof defects continue.
4. Add config-owned Story Room experimental enablement per tenant. Default remains legacy until the operator cutover gate.

## Phase B — Story and event ledger

Add tenant-scoped additive storage with immutable/append-only semantics:

- `stories`: identity, descriptive title, active stage, status, current artifact pointers;
- `story_events`: messages, attachments, research/tool results, decisions, failures;
- `story_contributions`: typed human/source/Inspiration/research/import inputs;
- `story_artifacts`: stable lineage per artifact type;
- `story_artifact_versions`: canonical payload, hash, based-on refs, status;
- `story_artifact_decisions`: lock/reject/supersede decisions bound to exact versions;
- `story_understanding_entries`: known/assumed/missing/locked with supersession;
- `story_tool_runs`: tool input/output refs, job identity, status, retry lineage.

### Constraints

- Each writer owns its `CREATE TABLE IF NOT EXISTS` path.
- Tenant and story scope on every read/write.
- Idempotency key on message/tool/artifact-producing requests.
- Append-only history; current state is derived or pointer-based.
- Active stage is a navigation pointer, not a second production state machine.
- `ProductionSession` remains separate and is referenced only after Build handoff.

## Phase C — Artifact service and compatibility projections

Build one artifact service that:

1. validates strict per-type schemas;
2. writes monotonic immutable versions;
3. binds lock/reject decisions to hash/version;
4. calculates dependency staleness;
5. preserves unaffected artifacts;
6. exposes human-readable diffs;
7. compiles locked Story Map into the current idea/treatment shape;
8. compiles locked exact copy into the current Writer/Production Contract with byte-level drift checks;
9. compiles locked Asset Plan into existing component-requirement inputs.

Compatibility projections carry `story_id`, `artifact_id`, version, and hash. Legacy imports preserve current values and label missing historical conversation honestly. No reverse write from an old route may silently outrank a room lock.

## Phase D — Prompt-backed room intelligence

Register the processes defined in `playbooks/story-room-co-creation.md`.

The shared room-turn service receives:

- active stage and current artifact;
- room events since that artifact version;
- understanding map;
- exact locks and stale dependencies;
- declared module/context views;
- exact contribution/source excerpts;
- available stage tools and their capabilities/costs;
- prior failed tool results.

It returns schema-valid operations:

```yaml
response:
  message: plain-language response
  question:
    required: boolean
    material_reason: why the answer changes the piece
    choices: optional concrete alternatives
  assumptions:
    - statement: visible working assumption
      evidence_refs: []
  artifact_operation:
    type: none | create_version | local_revision | propose_lock
    artifact_type: optional
    base_version: optional
    changed_sections: []
    payload: optional schema-valid artifact
  tool_request:
    type: none | research | source_fetch | media_preview | production_handoff
    inputs: exact refs
```

Python validates allowed operation, refs, version freshness, stage permissions, idempotency, and hashes. It never uses keywords to pick a question, frame, hook, style, or tool.

## Phase E — Operator surfaces

### Desk

- “Start with a thought” composer.
- Stories ordered by next meaningful human decision, not raw update time.
- Descriptive titles and concise “what needs you” summaries.
- Honest working/failed/parked/published states.
- Recent activity as receipts, not pressure.

### Story Room laptop

- stage rail: Brief / Idea / Shape / Draft / Build;
- persistent conversation pane;
- live artifact pane with visible version and lock/stale state;
- visible understanding map;
- one primary action per current decision;
- attachments/research in composer;
- direct editing for artifacts that support it;
- technical details collapsed.

### Story Room mobile

- true 390px viewport with no horizontal overflow;
- compact stage rail;
- explicit Conversation / Artifact / Understanding views;
- composer remains reachable above keyboard;
- no critical map/version/action hidden;
- platform previews expand fullscreen.

### Primary navigation during experiment

Keep legacy default. With experiment enabled, offer Desk / Inspiration / Stories / Knowledge / Results and a clear “Legacy pipeline” utility link. Do not relabel an old queue as Stories without the room ledger.

## Phase F — Stage slices

### Slice 1: Brief → Idea

- arbitrary input or imported card;
- exact contribution storage;
- understanding map;
- two/three materially distinct directions;
- Source-Fit Critic integration;
- artifact review/lock/reject;
- restart continuity.

### Slice 2: Shape

- frame, movement, hook direction, ending;
- exact Format Guide, production binding, treatment, capture policy;
- Story Map lock;
- no legacy Writer enqueue in Story Room mode.

### Slice 3: Draft

- skeleton/opening/full/local revision passes;
- direct-edit authority;
- exact copy decomposition;
- AI review transparency without replacing dialogue;
- Gate 2 lock;
- deterministic compilation to current production contract.

### Slice 4: Build

- Asset Plan;
- existing Component Workbench and composition tools embedded/deep-linked with story context;
- tool results/failures returned to room ledger;
- exact final preview, Gate 3, Gate 4;
- Results links back to story/artifact decisions.

### Slice 5: Inspiration

- “Take to Story Room” binds exact item/observation/run IDs;
- asks what the operator sees or proposes concrete uses;
- no automatic Source Bank truth or prewritten treatment;
- compatibility `origin='inspiration'` remains for legacy records.

## Phase G — Proof

### Fixtures

1. Human-seeded carousel.
2. Source-led Reel.
3. Half-formed personal story.

### Injected failure

At least one piece must experience a failed research/media/render tool call. Verify room events, locks, and unaffected artifacts survive and retry locally.

### Measures

- operator recognition score and qualitative reason;
- elapsed operator time to first good draft;
- number of turns and questions;
- number and scope of revisions;
- claim/frame/exact-copy hash survival;
- stale/invalidation correctness;
- publishable completion;
- laptop and 390px UI evidence across all 10 dimensions;
- full suite and targeted process/storage/browser tests;
- no actual publish without explicit approval.

### Cutover gate

Present Story Room and legacy results without claiming a winner. Operator chooses:

- make Story Room default and keep legacy utility mode;
- iterate and rerun proof;
- retain legacy default.

No code path makes that decision automatically.
