# AMENDMENT-020 — Persistent Story Room conversational co-creation

**Filed:** 2026-08-21
**Filed by:** Architect
**Status:** APPROVED — ratifies DIVERGENCE-028 with controlled-cutover conditions
**Ratifies:** `docs/decisions/DIVERGENCE-028-story-room-conversational-co-creation.md`
**Supersedes:** DIVERGENCE-017 and pipeline-first operator interaction where specifically stated
**Charter effect:** Charter v3.11 → v3.12
**Type:** STRATEGIC / STRUCTURE / LOGIC

## Constitutional ruling

ViralFactory remains a generic content co-creation system, but the operator-facing creative center changes from a set of pipeline queues to **one persistent Story Room per piece**.

The room does not replace the harness. It makes the existing Source Bank, modules, prompts, research, Writer, component workbench, renderers, publishing, metrics, and learning services available as controlled backstage tools. The person and the LLM establish shared understanding and lock human-readable artifacts before those tools compile or execute production contracts.

## C1 — One room per piece

Each content piece has one tenant-scoped Story Room from first input through publish and learning. A room may begin from a typed or spoken thought, an uploaded file, an Inspiration observation, a source, an existing idea card, or an imported legacy piece.

- Not one global chat: cross-piece contamination is forbidden.
- Not one chat per stage: stage changes do not discard or silo the conversation.
- Browser close, service restart, and tool failure do not erase room history or artifact locks.

## C2 — Conversation controls; artifacts govern

Chat is the operator control surface. It accepts text, files, sources, voice when available, direct instructions, reactions, and “you decide.” The durable truth is an append-only ledger of:

- room events and attachments;
- contribution/source references;
- understanding entries;
- artifact versions;
- artifact locks/rejections;
- tool invocations and results;
- exact downstream lineage.

Conversation text alone never counts as an approval. A server-minted decision binds the operator action to the exact artifact version and content hash.

## C3 — Human-readable artifact progression

The front-stage progression is:

1. **Brief** → `creative_brief`: why this matters, human stake, audience, desired effect, evidence available, red lines.
2. **Idea** → `idea_map`: core claim, source-grounded lens, tension, audience promise, evidence, emotional job.
3. **Shape** → `story_map`: point of view, frame, narrative movement, hook direction, ending, format, exact production binding, visual treatment, capture policy.
4. **Draft** → exact copy artifacts: main text, spoken text, on-screen text, post caption, hashtags, title, evidence notes, and platform variants where applicable.
5. **Build** → `asset_plan`, then the existing Component Workbench, immutable manifest, CompositionPlan, renderer execution, final review, and publish handoff.

The operator sees these artifacts in plain language beside the conversation. Machine schemas are compiled after the relevant human-readable artifact is locked; they are not the creative surface.

## C4 — Understanding map

Each room maintains visible entries in four states:

- **Known:** stated by the human or directly supported by linked evidence.
- **Assumed:** an AI working interpretation, visibly labeled and revisable.
- **Missing:** information whose answer would materially change the piece.
- **Locked:** an explicitly approved decision bound to an artifact version.

Every entry carries scope, source/event references, author, time, and—when locked—the binding decision ID. AI text cannot relabel an assumption as known or locked. A superseding human correction preserves history and becomes current.

## C5 — Question policy

The LLM does not run a questionnaire and does not always ask a question.

1. Read current room history, locks, approved modules, attachments, and exact sources before asking.
2. Research factual gaps itself when permitted and evidence can answer them.
3. Ask the human about lived experience, belief, boundaries, and taste.
4. Show two or three concrete alternatives for taste decisions rather than asking abstractly.
5. Ask one meaningful decision at a time.
6. Permit “you decide” for low-risk choices; record the result as an assumption until the relevant artifact lock.
7. Never re-ask an answered question.
8. If a safe working assumption exists, label it and proceed to a preview rather than blocking.

Question selection is LLM judgment implemented through a versioned prompt, schema, validator, cache, and provenance—not Python keywords.

## C6 — Creative locks and autonomy boundary

Each artifact version is immutable. Revision creates a new version and preserves the prior one. The operator may lock, reject with feedback, or continue shaping.

- Locking the Story Map is the Gate 1 meaning/treatment decision.
- Locking exact copy is Gate 2.
- Exact component decisions and manifest freeze remain the Assets component sub-gate.
- Gate 3 still approves the exact final artifact.
- Gate 4 still approves publish timing/go-hold.

After a lock, deterministic compilation and already-authorized mechanical work may continue. The system must pause before any new unapproved creative judgment. An upstream revision marks every dependent artifact and approval stale through exact hash lineage; unaffected artifacts remain valid.

## C7 — One creative ledger; separate production state

The Story Room uses one active-stage pointer plus artifact locks and derived readiness. It must not create a second giant hand-built workflow state machine. Existing `ProductionSession` remains authoritative for per-platform production after Build handoff.

The room may project locked artifacts into compatibility records (`idea_cards`, `drafts`, `assets`) during the experiment, but projections must carry `story_id`, source artifact version, and content hash. A compatibility row may not silently mutate or outrank the Story Room artifact.

## C8 — Backstage tool bench is preserved

The redesign reuses rather than rebuilds:

- Source Bank and Inspiration evidence contracts;
- all eight living modules and the Process Registry;
- LLM adapter, schema validation, cache, and provenance;
- Writer and production prompts where their responsibility still applies;
- Component Workbench, candidate decisions, rights/cost evidence, and manifest freeze;
- CompositionPlan, local previews, ratification, RendererSpec, and adapters;
- final compliance, Gate 3, Gate 4, Buffer, metrics, and learning proposals.

Capabilities are invoked as atomic room tools. A failed tool call creates a visible local failure event and retry path; it cannot erase the conversation, locks, or unaffected artifacts.

## C9 — Inspiration enters as evidence, not a prewritten idea

“Take to Story Room” creates or appends a contribution referencing the exact Inspiration item, observation, collection run, and immutable evidence semantics. The room first asks what the person notices or presents concrete possible uses. It does not silently promote the observation to Source Bank truth, a Format Guide rule, a soundtrack right, or a completed idea/treatment.

A later Source Bank, Format Guide, experiment, or module change uses its existing explicit gate.

## C10 — Operator information architecture

The target primary navigation is:

`Desk · Inspiration · Stories · Knowledge · Results`

- **Desk:** stories ordered by the next meaningful human decision, plus “start with a thought.”
- **Inspiration:** evidence workbench with “Take to Story Room.”
- **Stories:** persistent rooms.
- **Knowledge:** modules, sources, treatments, and proposals with version/evidence visibility.
- **Results:** exact publish records, metrics, and learning linked back to the room.

Setup, upload, and technical utilities remain reachable but do not compete as primary creative destinations. The Story Room laptop layout uses a stage rail, conversation pane, artifact pane, and understanding map. Mobile uses a stage rail plus explicit Conversation / Artifact / Understanding views; none may disappear.

## C11 — Controlled coexistence, not big-bang migration

The legacy pipeline remains available behind a config/feature flag while Story Room is experimental. No legacy record is destructively migrated. Existing pieces may be imported into a room with preserved IDs/hashes and visibly labeled missing history.

Do not make Story Room the sole default until the proof in C12 passes and the operator chooses the cutover. Do not spend time cosmetically extending the old pipeline except for safety, truthfulness, and shared-backstage defects.

## C12 — Comparative proof and cutover gate

The first proof set is:

1. human-seeded carousel;
2. source-led Reel;
3. half-formed personal story.

For each, compare Story Room with the current baseline on:

- recognition: “this is the story I meant”;
- time to first good draft;
- number and locality of corrections;
- survival of claim, frame, lived detail, and exact copy;
- recovery from one injected tool failure;
- operator comprehension and navigation;
- completion to a publishable, exactly gated piece;
- all 10 UI dimensions at laptop and 390px mobile.

The operator selects Story Room as default, requests another iteration, or retains legacy mode. Automated scores cannot make this decision.

## Data contract minimum

The builder may choose normalized table names, but the persisted meaning is fixed:

```yaml
story:
  story_id: stable tenant-scoped identity
  business_slug: tenant owner
  title: descriptive, versioned display title
  active_stage: brief | idea | shape | draft | build
  status: active | parked | killed | published | archived
  current_artifact_refs: exact version/hash pointers

room_event:
  event_id: append-only identity
  story_id: owner
  actor: operator | ai | system | tool
  event_type: message | attachment | research_result | tool_result | decision | failure
  content_or_artifact_ref: exact payload or immutable reference
  created_at: timestamp

artifact_version:
  artifact_id: stable lineage
  artifact_type: creative_brief | idea_map | story_map | exact_copy | asset_plan
  version: monotonic
  content: schema-valid payload
  content_hash: canonical hash
  based_on: exact upstream artifact/event/source refs
  status: working | ready_for_review | locked | rejected | stale

understanding_entry:
  entry_id: stable identity
  kind: known | assumed | missing | locked
  statement: plain language
  evidence_refs: exact event/source/artifact refs
  current: boolean derived from append-only supersession
```

Every writer initializes its own tables defensively. All reads/writes are tenant-scoped. Every LLM turn and tool call records prompt/process version, input hash, model/profile, raw output, validated output, cache verdict, artifact refs, and failure truthfully.

## Definition of Done

AMENDMENT-020 is implemented only when:

- the Story Room ledger, artifact locks, understanding map, context policy, and room UI exist;
- locked artifacts compile into the existing production contracts without copy drift;
- one tool failure is locally recoverable without losing the room;
- Inspiration carries exact evidence into a room;
- all four gates remain exact and per-piece;
- the three-piece controlled comparison and deep 10-dimension review are filed;
- the operator makes an explicit cutover decision.
