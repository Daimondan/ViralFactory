# DIVERGENCE-007 Design — Source review gate + source neural network

**Architect:** Hermes (vf-architect profile)
**Date:** 2026-07-04
**Status:** Design complete — ready for builder implementation (Item 1) + deferred (Item 2)

---

## Item 1: Source Review Gate (APPROVED for implementation)

### Problem

New sources from RSS feeds and the outward research loop flow directly into the `sources` table with `status='active'`. The operator has no way to review newly added sources before they feed into idea generation. Daimon: "when analyst pulls new sources, it is still important to have a section where humans can review what was newly added and decide if it should be removed."

### Design

**Soft gate, not hard gate.** New sources enter with `status='new'` (not `active`). Only `active` sources feed into the idea generation prompt. The operator reviews new sources at their own pace — no deadline, no pressure mechanics (same async-gate philosophy as the proposal queue).

#### Status flow

```
RSS/search ingestion → status='new'
                         │
                    operator reviews
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
          'active'   'parked'  'removed'
```

- `new` — freshly ingested, not yet reviewed. Visible on Source Bank page under "New" filter. Does NOT feed ideation.
- `active` — operator-approved. Feeds ideation.
- `parked` — operator deferred. Does not feed ideation, but preserved.
- `removed` — operator rejected. Does not feed ideation.

#### What changes in code

1. **`source_snapshot.py`** — RSS items enter with `status='new'` instead of `status='active'`
2. **`research_job.py`** — outward loop research items enter with `status='new'`
3. **`materials.py`** — operator materials (typed/uploaded) still enter as `active` (the operator created them intentionally)
4. **`pipeline.py` / `app.py`** — `ideas_generate` route: source digest only includes `status='active'` sources (not `new`)
5. **Source Bank page** — add "New" filter button with count. New sources show a "Review" action (Keep → active, Park → parked, Remove → removed)
6. **Bulk actions** — "Keep all new" and "Remove all new" buttons (Daimon's rule: bulk ops from the start, any queue with 50+ items needs checkbox + select-all + bulk approve/reject)

#### Soft gate rationale

A hard gate (new sources block ideation until reviewed) would starve ideation if the operator doesn't review promptly. A soft gate means: new sources are visible but don't feed ideation until reviewed. If the operator doesn't review, ideation degrades to using only previously-approved active sources — which is better than feeding unreviewed junk into idea generation. The operator sees the "New" count in the filter button and can clear it when ready.

This is consistent with the charter's async gate philosophy: "No deadlines, no pressure mechanics. If the queue grows faster than it clears, the proposals are too weak or too many — fix the proposal prompt, never pressure the person."

#### What does NOT change

- The Sources Engine playbook's Part B step 3 ("proposed source additions at the async gate") — this is already the gate. The `status='new'` flow IS the gate implementation.
- Operator materials from intake — these are intentionally created by the operator, they enter as `active` immediately.
- Seed sources from onboarding — these are reviewed during onboarding, they enter as `active`.

---

## Item 2: Source Neural Network (DEFERRED)

### Problem

Daimon: "we also need to set up a neural network between sources so research can easily see connected sources which would help with ideation."

### Why deferred

The source neural network is a judgment-heavy feature that needs proper design:
- How are connections determined? (shared concepts via LLM analysis? co-citation patterns? Obsidian export data?)
- What does "neural network" mean in practice? (A graph visualization? A data structure that feeds the Researcher prompt? Both?)
- How does it integrate with ideation without making the prompt unbounded?

This is too complex to design and build in the current session. It needs its own architect design pass with input from the operator on what "connected sources" means in practice.

### Design direction (for future architect pass)

1. **Connection types** — `shared_concept` (LLM determines sources share a concept), `co_cited` (sources cited together by idea cards), `temporal` (sources from the same event/timeframe)
2. **LLM-driven, not keyword** — per charter, understanding connections between sources is a judgment task. The LLM analyzes source content and proposes connections. Not keyword matching.
3. **Feed the Researcher, not the operator** — connections surface in the idea generation prompt as context ("Source S14 is connected to S22 and S31 via the concept 'Caribbean wealth attitudes'"). The operator doesn't need to see a graph; the Researcher uses the connections to synthesize across sources.
4. **Vertical-flow display** — if the operator ever sees connections, it's a simple vertical-flow list ("S14 ← connects to → S22, S31"), not a boxed ASCII grid.

### What the builder should NOT do now

Do not build the source_connections table or any neural network feature. Wait for the architect's full design.

---

## Builder implementation order

1. **Item 1 only:** Change new source ingestion to `status='new'`, add "New" filter to Source Bank page, add bulk actions, restrict ideation to `active` sources only.
2. File a CHANGELOG entry for the source review gate.
3. Update CONTEXT.md Source Bank definition to include the `new` status and the review flow.
4. Do NOT implement Item 2.