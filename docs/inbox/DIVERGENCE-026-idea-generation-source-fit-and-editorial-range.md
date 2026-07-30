# DIVERGENCE-026 — Idea generation lacks a source-fit and editorial-range contract

**Filed:** 2026-07-30
**Filed by:** Architect, from `BUILDER-NOTE-021-idea-generation-thematic-range.md`
**Status:** RATIFIED by AMENDMENT-019
**Type:** LOGIC / STRATEGIC / STRUCTURE

## Evidence

The builder measured 103 StackPenni cards: 68 mention AI (66%), 90 mention Caribbean (87%), 37 mention entrepreneur(s) (36%), and 8 mention sou-sou (8%). Cards 81, 88, 92, and 97 repeatedly translate the same source-111 Guyana investment-forum evidence into the same foreign-capital/AI/entrepreneur frame.

The live architecture explains the pattern:

- `config/business.yaml` defines the brand and audience primarily through AI, wealth, and entrepreneurship.
- `modules/stackpenni/voice-profile.md` declares the money-system/AI-system/friction analogy as the universal identity line.
- `modules/stackpenni/audience-insights.md` contains only untested beliefs but presents the same intersection as the audience's dominant interest.
- `prompts/ideas/concepts_v1.md` says “voice is the frame” without requiring the model to justify a frame from source evidence.
- `IDEA_CONCEPT_SCHEMA` has no inspectable source-fit decision.

Source randomization and sentence-complete duplicate context improve source variety and duplicate visibility; they cannot correct a universal editorial premise.

## Conflict

The charter requires source-grounded, human-specific work and forbids judgment in code. The present prompt/module composition encourages unsupported framing. The builder's proposed keyword-based Python checks would correct one defect by creating another: determining whether a source “substantively supports AI” or whether sou-sou is a valid analogy is editorial judgment and cannot be implemented with keyword matching.

## Ruling requested and resolved

AMENDMENT-019 establishes:

1. Caribbean identity as an editorial point of view, not a compulsory word or wrapper.
2. AI, sou-sou, entrepreneurship, “the machine,” and friction as optional lenses that require material support.
3. A configurable editorial lens catalogue.
4. A required, persisted `editorial_fit` object on each concept.
5. A schema-validated LLM Source-Fit Critic for editorial judgment; Python validates structure, references, configured identifiers, and counts only.
6. Recent balance as prompt evidence, not a deterministic gate.
7. One bounded repair pass, followed by omission of still-invalid cards.
8. Human review—not destructive migration—for the existing repetitive queue.
