# DIVERGENCE-017 — Inspiration-to-Idea flow and idea origin tags

**Filed:** 2026-07-20
**Filed by:** Builder (vf-coder)
**Status:** PENDING — operator-directed; awaiting architect ratification
**Related:** AMENDMENT-012 (Inspiration evidence workbench); DIVERGENCE-016; Charter v3.8

## Summary

The operator approved two changes to the Inspiration Center and Ideas pipeline:

1. **"Let's work on an idea now" button on Inspiration cards** — creates an idea card directly from a trending inspiration item, with provenance linking back to the observation.
2. **Idea origin tags** — extend the `origin` field on idea_cards so the operator can see at a glance which ideas came from: the LLM, their own seed, or the Inspiration Center.
3. **Format/mechanic grouping (future)** — a "formats" concept distinct from sources, which the ideator uses to match the best format to a story/idea. Sources stay as sources (content only).

## Operator problem

The Inspiration Center shows trending audio and video, but there is no path from "I see a trending format/sound I like" to "let's create an idea for this." The operator must manually switch to the Ideas page and re-enter what they saw. The origin of ideas is not visible in the Ideas queue — there's no way to tell at a glance whether an idea came from the LLM, the operator's seed, or an Inspiration observation.

## Proposed changes

### 1. "Create idea from this" button on Inspiration cards

Add a button to each Inspiration card that:
- Creates an idea card with `origin='inspiration'`
- Links the idea card to the observation (via `evidence_links` or a new `inspiration_ref` field)
- Pre-fills the idea text with a reference to the trending item (e.g. "Inspired by: [title] by [creator] — [platform]")
- Does NOT bypass Gate 1 — the idea enters as `card_state='new'` and goes through the normal approval flow

### 2. Extended origin values on idea_cards

Current: `ai_originated | human_seeded | human_seeded_ai_developed`
Proposed: add `inspiration` as a fourth origin value.

The Ideas page should display the origin as a visible tag so the operator can filter/sort by source.

### 3. Format/mechanic grouping (design note, not this divergence's build)

A future divergence will propose a "formats" concept — a curated set of video/audio formats and mechanics (trending sounds, Reel structures, skit templates) that the ideator uses to match the best format to a story/idea. This is distinct from the Source Bank, which remains content-only (articles, feeds, research). The Inspiration Center's "Propose pattern" action (VF-INSP-005) already creates the record; the future divergence will wire it to a reviewable formats queue.

## Charter compliance

- Per-piece approval before publish remains unchanged — ideas from Inspiration still go through Gate 1.
- No business values in code — the origin tag is a schema value, not a business-specific label.
- No judgment in code — the LLM still does ideation; the operator still gates.
- The Inspiration Center remains read-only for collection; the "Create idea" button is an explicit operator action, not autonomous promotion.

## Request

Architect review requested on:
1. Is `inspiration` a valid fourth origin value, or should it be `inspiration_seeded`?
2. Should the idea card carry an `inspiration_ref` FK to the observation, or is `evidence_links` JSON sufficient?
3. Is the formats/mechanic concept a separate divergence or part of this one?