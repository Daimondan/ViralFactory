# AMENDMENT-006 — Writer/Assembler pipeline split + four-role nav (ratifies DIVERGENCE-006)

**Filed:** 2026-07-04
**Filed by:** Architect
**Status:** APPROVED — incorporates DIVERGENCE-006 into Charter v3.3
**Supersedes:** The awaiting-capture blocking semantics in AMENDMENT-003 (refines, does not remove)

## What this amends

DIVERGENCE-006 proposed a four-role operator mental model (Researcher → Writer → Assembler → Analyst) and the removal of awaiting-capture as a blocking state. The builder implemented it. This amendment formalizes the changes into the charter.

## Amendment 1: Four-role operator navigation

The operator-facing navigation is organized by four roles, mapping to the existing AI Profiles:

| Role | Nav label | Route | AI Profile | What happens here |
|---|---|---|---|---|
| Researcher | Researcher (Ideas) | `/ideas` | researcher | Gate 1: approve/kill/park idea cards |
| Writer | Writer (Script) | `/create` | drafter | Gate 2: review draft, edit, ship or kill |
| Assembler | Assembler (Studio) | `/assemble` | drafter | Gate 3: review per-platform assets, approve/fix/kill |
| Analyst | Analyst (Learnings) | `/published` | analyst | Gate 4: publish, metrics, learning loops |

Setup/admin pages (Onboard, Module Health, Library, Materials, Source Bank, Gate Queue) are secondary nav, grouped separately.

**This is a relabel of existing routes, not a structural change to the pipeline.** The four gates (Ideas → Draft → Assets → Publish) remain. The role labels are the operator's mental model; the gates are the system's control flow.

## Amendment 2: Awaiting-capture becomes non-blocking

AMENDMENT-003 defined awaiting-capture as a blocking state: "Cards approved with outstanding capture tasks enter awaiting-capture until the human supplies material through the materials intake."

**Refined:** Capture tasks are now a **non-blocking flag on the card**. The card flows through Writer → Assembler regardless of capture status. The Assembler produces the asset with whatever media it can generate (generated/placeholder for missing real photos). Capture tasks remain visible on the card ("real photo needed: [description]") so the operator knows what to capture — but they no longer block the pipeline.

This resolves the conflict with AMENDMENT-003 by refining it rather than removing it. AMENDMENT-003's awaiting-capture state is deprecated as a blocking state; capture tasks persist as a visible card property.

## Amendment 3: Writer and Assembler are separate production stages

The production chain (T8.6) is split into two stages:

1. **Writer chain** — triggered by Gate 1 approval. Generates the draft (full text + visual direction). Stops at `draft_ready` for Gate 2 human review. Card state: `writing → draft_ready | writer_failed`.

2. **Assembler chain** — triggered by Gate 2 ship. Runs per-platform fan-out → visual generation. Stops at `asset_ready` for Gate 3 human review. Card state: `assembling → asset_ready | assembly_failed`.

This restores Gate 2 (the human pass) which T8.6's original auto-chain bypassed. The operator reviews the draft before the assembler creates assets — no more auto-shipping drafts without human review.

**The Drafter AI profile covers both stages.** Writer and Assembler are pipeline stages, not separate AI profiles. The profile split (if needed) is a future config change via the gate, not a code change.

## Amendment 4: Analyst owns the publish surface

The Analyst role page (`/published`) is where the operator manages publishing and views metrics. This consolidates Gate 4 (Publish — go/hold + timing) and the Learn stage under one operator surface. The Analyst does NOT auto-publish — per-piece approval remains a hard rule. The Analyst page surfaces "ready to publish — approve?" for Gate 4.

## What this does NOT change

- **Four content gates** — Ideas (rigorous), Draft (deep human pass), Assets (quick per-platform), Publish (go/hold). All remain.
- **Per-piece approval before publish** — hard rule, unchanged.
- **No auto-publish** — hard rule, unchanged.
- **AI Profiles** — Researcher, Drafter, Analyst. Unchanged. The four-role nav maps to these three profiles (Writer + Assembler both use Drafter).
- **The charter's pipeline diagram** — the stages are the same; only the operator-facing labels change.

## Charter text to update

In CHARTER-v3.3, the core loop section:

- "Approved pieces flow to Postiz" → "Approved pieces flow to Buffer" (per DIVERGENCE-008)
- The gate descriptions remain unchanged
- Add: "The operator-facing navigation is organized by four roles (Researcher, Writer, Assembler, Analyst) that map to the pipeline gates and AI profiles."

In CONTEXT.md:

- Update the Core Loop diagram to show the Writer/Assembler split
- Update all "Postiz" references to "Buffer"
- Add the four-role nav mapping table
- Note awaiting-capture as non-blocking flag, not blocking state