# DIVERGENCE-007 — Source Bank review queue + source neural network

**Filed:** 2026-07-04
**Filed by:** Builder (Hermes)
**Status:** PARTIALLY RESOLVED — source review gate implemented; source-network design remains open (2026-07-19 clarification)

> **Status clarification:** Items 1 and 2 are now implemented and governed by the hard `status='new'` review gate described in Charter v3.8. Item 3, the source-connection network, remains an unresolved design question. AMENDMENT-012's Inspiration evidence tables do not implement or silently resolve that network.

## Context

The operator raised three requests about the Source Bank:

1. **Source Bank page** — a UI to view all sources in the bank. **DONE** — built `/sources` route with filter buttons (All/Active/Parked/Removed), per-source Keep/Park/Remove actions, and nav link added across all templates.

2. **Human review of newly added sources** — when the Analyst discovers and pulls new sources (via RSS feeds, search queries, or the Sources Engine Part B continuous loop), the operator wants a review section where a human can see what was newly added and decide if each source should be kept or removed. This is a **gate** — the Sources Engine playbook already specifies this (Part B, step 3: "Candidates above threshold → proposed source additions at the async gate"), but it's not implemented yet.

3. **Source neural network** — the operator wants a visualization/data structure that shows connections between sources, so the Researcher (ideation AI) can easily see which sources are connected to each other. This would help ideation by surfacing clusters of related sources and enabling cross-source synthesis.

## What's Built (Item 1)

- `/sources` route — lists all sources in the `sources` table with status badges
- Filter buttons with counts: All / Active / Parked / Removed
- Per-source actions: Keep (set active), Park (set parked), Remove (set removed)
- `/api/sources/<id>/status` API endpoint for status updates
- Nav link added across all 29 templates

## What Needs Architect Design (Items 2 + 3)

### Item 2: New source review queue

**Current state:** New sources from RSS feeds flow directly into the `sources` table with `status='active'`. There is no gate — sources are auto-active immediately after ingestion. The operator has no way to review newly added sources before they feed into ideation.

**Proposed approach (needs architect validation):**
- New sources from RSS/search ingestion enter with `status='new'` (not `active`)
- A "New sources" filter on the Source Bank page shows items with `status='new'`
- Operator reviews each new source: Keep (→ active), Park (→ parked), Remove (→ removed)
- Only `active` sources are sent to the idea generation prompt as source material
- Bulk actions: "Keep all new", "Remove all new" (operator preference: bulk ops from the start)

**Question for architect:** Should this be a hard gate (new sources block ideation until reviewed) or a soft gate (new sources are auto-active after a grace period if not reviewed)? The playbook says "proposed source additions at the async gate" — this implies a hard gate, but that could starve ideation if the operator doesn't review promptly.

### Item 3: Source neural network

**Current state:** The Obsidian Strongest Sources Export contains `concept_links` and `degree` data — sources are already connected via shared concepts. The `top-50-sources.csv` has columns like `concept_links` (semicolon-separated list of linked concepts) and `backlinks`/`outgoing` counts. This data exists but is not stored in the database or surfaced to the Researcher.

**Proposed approach (needs architect validation):**
- Add a `source_connections` table: `(source_id, connected_source_id, connection_type, weight)`
- Connection types: `shared_concept` (sources that share a concept tag), `citation` (one source cites another), `co_cited` (sources cited together by idea cards)
- During idea generation, the Researcher sees not just a flat list of sources but a network — "Source S14 is connected to S22 and S31 via the concept 'Caribbean wealth attitudes'"
- UI: a simple vertical-flow diagram showing source clusters (operator preference: vertical-flow, not boxed ASCII grids)
- This enables the Researcher to synthesize across connected sources — "Sources S14, S22, and S31 all touch on Caribbean financial attitudes — that composition is itself an idea"

**Question for architect:** Should the source network be built from the Obsidian export data (which already has concept_links), from LLM analysis of source content, or from co-citation patterns in existing idea cards? Or all three? This is a judgment task (understanding connections between sources) — per the charter, it should be LLM-driven, not keyword heuristics.

## Operator Quotes

> "is there a button for the sources bank i can see?"
> "also when analyst pulls new sources, it is still important to have a section where humans can review what was newly added and decide if it should be removed"
> "we also need to set up a neural network between sources so research can easily see connected sources which would help with ideation"
> "ensure all these changes for today documented for architect"