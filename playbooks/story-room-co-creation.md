# Story Room Co-Creation Playbook v1.0

<!-- playbook_type: production -->
<!-- display_label: Story Room -->

**Purpose:** help a person turn an unfinished thought, source, observation, or lived moment into one exact, publishable piece through persistent conversation and versioned artifacts—without requiring the person to write, design, or operate a pipeline.

**Constitution:** AMENDMENT-020. This playbook is the front-stage creative procedure. `docs/playbooks/viral-content-production-playbook-v1.md` and the M15 services remain the backstage production procedure after creative locks.

## Invariants

1. One Story Room per piece.
2. Conversation controls; versioned artifacts govern.
3. Read before asking: room history, locks, attachments, exact sources, relevant module views.
4. Ask only when an answer materially changes the piece.
5. One meaningful decision at a time.
6. Direct edits are authoritative.
7. New creative judgment pauses after the last human lock.
8. Tool failures are local and resumable.
9. Every LLM turn and tool call is provenance-logged and cache-aware.
10. Nothing publishes without Gate 3 and Gate 4 decisions on the exact piece.

## Inputs

A room may begin with any combination of:

- typed or spoken thought;
- rant, question, opinion, memory, or rough story;
- link, Source Bank row, exact source passage, or Inspiration observation;
- uploaded document, image, video, audio, screenshot, receipt, or previous content;
- imported idea card/draft/asset;
- an instruction such as “research this,” “show me directions,” or “you decide.”

Each input becomes a typed contribution with exact source/event identity. Do not flatten all input into one seed string.

## Context views

### Always present

- current artifact version;
- current understanding map;
- locked decisions and exact human edits;
- unresolved Missing entries;
- room turns since the current artifact version;
- relevant Voice Profile cognitive/expression entries;
- recent piece-specific feedback;
- current stage and allowed tools.

### Retrieved on demand

- exact source passages and observation evidence;
- relevant Audience, Story Framework, Format Guide, Visual Style/treatment, Viral Pattern, and Source Criteria entries;
- similar prior pieces and performance hypotheses;
- production capability and cost facts.

No blind “load all modules into every turn.” Context views are declared in the Process Registry and retain module/version provenance. Call-time LLM summaries may not replace approved module text.

## Understanding map contract

Every meaningful statement is typed:

```yaml
entry:
  entry_id: stable
  kind: known | assumed | missing | locked
  statement: plain language
  scope: brief | idea | shape | draft | build | global_piece
  evidence_refs: [event/source/artifact IDs]
  created_by: operator | ai | tool
  supersedes: optional entry_id
  current: derived, never manually overwritten
```

- Human corrections supersede; they do not erase.
- AI may create Known only from exact linked evidence and may create Locked only after a server-verified operator decision.
- Missing is reserved for answers that materially change the piece.
- Assumptions are useful: label them and make them easy to correct.

## Stage 1 — Brief

### Goal

Establish why this piece should exist before optimizing format or hook.

### Procedure

1. Reflect the strongest working understanding in one short readback.
2. Mine provided material and approved modules before asking.
3. Identify the human stake or honestly state that none is known.
4. Identify evidence available and evidence gaps.
5. Ask at most one high-leverage question at a time.
6. Offer a safe assumption or research action when the human need not decide.
7. Produce a working Creative Brief.

### Artifact

```yaml
creative_brief:
  purpose: why this story matters now
  human_stake: specific lived belief/moment or honestly unknown
  audience: who needs it and why
  desired_effect: what should change for them
  available_evidence: exact refs
  evidence_gaps: exact missing facts
  red_lines: what this must not become
  distribution_intent: open | platform_constrained | exact_format
  understanding_snapshot: exact current entry refs
```

### Exit

Operator locks the brief or continues shaping. Locking the brief does not trigger drafting.

## Stage 2 — Idea

### Goal

Settle the story worth telling.

### Procedure

1. Develop the brief into two or three materially different directions—not paraphrases.
2. Each direction states claim, lens, tension, human stake, evidence, audience promise, and emotional job.
3. Source-Fit Critic verifies material support through the existing LLM boundary.
4. Explain the meaningful difference in plain language.
5. Ask the operator to choose, combine, reject, or say “you decide.”
6. Produce the Idea Map from the chosen direction.

### Artifact

```yaml
idea_map:
  core_claim: one proposition the piece earns
  editorial_fit: exact configured lens + critic evidence
  tension: what is unresolved or costly
  human_stake: exact known/assumed/missing status
  evidence_refs: exact source/contribution refs
  audience_promise: what the person gets
  emotional_job: recognition | tension | relief | wonder | amusement | conviction | hope
  rejected_directions: refs with reasons
```

### Exit

Operator language: “That is the story I want to tell.” Lock creates the Gate 1 idea meaning, but treatment is completed in Shape before production compatibility projection.

## Stage 3 — Shape

### Goal

Decide how the meaning unfolds.

### Order

`claim → frame → narrative movement → hook direction → ending → format → per-piece style`

Never optimize a hook before the claim and frame exist.

### Procedure

1. Present two or three frames only when the choice materially changes the piece.
2. Build narrative movement with named jobs, not arbitrary section counts.
3. Propose hook directions after movement exists.
4. Decide the ending and audience action.
5. Resolve Format Guide entry, platform set, production binding, capture policy, and exact visual treatment from approved modules/config.
6. Show assumptions and missing items visibly.
7. Produce the Story Map.

### Artifact

```yaml
story_map:
  point_of_view: specific stance
  frame: human-readable framing choice
  narrative_movement:
    - movement_id: stable
      job: semantic purpose
      content: what changes here
      evidence_refs: exact refs
  hook_direction: purpose and candidate language, not final copy
  ending: meaning and optional action
  format_ref: exact approved Format Guide entry/version
  platforms: locked set
  production_binding: exact approved binding
  visual_treatment_ref: exact approved treatment/version/hash
  capture_policy: exact tasks and allowed source policies
  style_for_this_piece: piece-scoped directives
  red_lines: inherited + new
```

### Gate 1 lock

Locking the Story Map binds the Idea Map + treatment meaning. It may create/update a compatibility `idea_card`, but it must not enqueue the legacy Writer chain in Story Room mode.

## Stage 4 — Draft

### Goal

Produce exact words collaboratively without turning the machine schema into the workspace.

### Passes

1. Skeleton: section/beat jobs only.
2. Opening options: materially different starts tied to the approved frame.
3. Full draft.
4. Local revision through conversation or direct edit.
5. Internal review against Voice Profile, AI Tells, source fidelity, and locked Story Map.
6. Exact copy lock.

### Exact copy artifact

```yaml
exact_copy:
  primary_text: exact canonical text
  spoken_text: exact words spoken, if any
  on_screen_text: exact role-tagged text, if any
  platform_variants:
    - platform: exact destination
      variant_type: approved structure
      content: exact text
      posts_or_slides: exact ordered parts
  post_caption:
    text: exact public caption
    hashtags: exact approved list
  title: exact title if applicable
  evidence_notes: claim-to-source refs
  self_audit: findings + actual applied changes
  direct_edit_events: exact room event refs
```

Direct edit writes a new artifact version immediately and outranks AI wording. “Revise this paragraph” changes only the affected artifact region unless the operator requests broader revision.

### Gate 2 lock

A server-minted decision binds the exact copy version/hash. Then—and only then—the system compiles the existing Writer/Production Contract. Compilation is deterministic and must prove no audience-copy drift.

## Stage 5 — Build

### Goal

Translate locked creative intent into exact approved ingredients and a final piece.

### Asset Plan

Before candidates, produce a human-readable plan appropriate to format:

- carousel: cover, slide jobs, swipe movement, receipts, close, caption, optional audio note;
- Reel: spoken beats, pauses, text roles, shots, real/generated policy, B-roll, music/SFX, caption;
- thread: opening, sequence, receipts, transitions, close, media placement;
- other formats: driven by exact Format Guide production binding.

The Asset Plan may not rewrite locked exact copy.

### Backstage sequence

`locked Asset Plan → Production Contract → component requirements → candidate workbench → exact decisions → immutable manifest → CompositionPlan + previews → composition ratification → RendererSpec → renderer → local verification → Gate 3 → Gate 4`

Existing M15 services remain authoritative. The room embeds or deep-links these tools with story context and returns results/failures into the event ledger.

### Failure behavior

- A failed VO does not invalidate approved visuals.
- A failed render does not unlock exact copy.
- A changed component creates a new manifest/composition/render and invalidates Gate 3, not the Story Map.
- A changed Story Map makes exact copy and all dependent production artifacts stale.
- A changed exact copy makes production contracts and downstream production stale while preserving the previous versions.

## Final review and publish

Gate 3 shows the exact artifact in platform-real context with caption/audio/evidence/manifest/spec lineage. Gate 4 is go/hold + timing. Buffer/API configuration failures remain visible and cannot produce green Scheduled/Published states.

## Learn

After publication, the room record receives metrics and operator reaction. The Analyst may propose exact updates to modules/processes. No room conversation or single result silently edits a living module.

## Prompt/process implementation

The builder creates versioned processes for at least:

1. `story_room_turn_v1` — chooses next response, question, assumption, tool, and artifact operation.
2. `creative_brief_v1` — drafts/revises the brief.
3. `idea_map_v1` — develops materially distinct directions and selected map.
4. `story_map_v1` — develops frame/movement/hook/ending/treatment.
5. `collaborative_draft_v1` — drafts or locally revises exact copy.
6. `asset_plan_v1` — produces a format-specific human-readable asset plan.

Every output names exact input refs and returns structured operations. Python validates schema, refs, current versions, stage permissions, hashes, and idempotency. It does not choose the question, frame, hook, style, or revision scope by keywords.

## Comparative proof

Run one human-seeded carousel, one source-led Reel, and one half-formed personal story. For each inject one recoverable tool failure and record the measures required by AMENDMENT-020 C12. The operator decides cutover.
