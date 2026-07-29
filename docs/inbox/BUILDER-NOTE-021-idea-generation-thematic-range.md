# BUILDER-NOTE-021 — Idea-generation thematic range and source-fit request

**From:** Builder (Hermes)
**Date:** 2026-07-29
**Status:** AWAITING ARCHITECT

## Operator feedback

Current idea generation is over-framing unrelated sources through AI, sou-sou, “the machine/friction,” and direct address to “Caribbean entrepreneurs.” The operator’s direction is explicit: **not everything must be framed through that lens or compared to AI.**

Caribbean should be a point of view, not a compulsory wrapper. AI, sou-sou, entrepreneurship, and the money/AI “friction” analogy should be available when materially supported—not default conclusions.

## Measured evidence

Of 103 StackPenni cards:

- 68 mention AI (66%)
- 90 mention Caribbean (87%)
- 37 mention entrepreneur(s) (36%)
- 8 mention sou-sou (8%)

Ideas 81, 88, 92, and 97 show the failure plainly: the same US/Guyana investment-forum source is repeatedly translated into foreign-capital extraction plus an implied AI/entrepreneurship lesson, instead of treating it on its natural policy, ownership, energy, or geopolitical stakes.

## Root cause identified

This is not only source repetition. The generation context currently makes one worldview universal:

1. `config/business.yaml` names StackPenni a “Caribbean AI + wealth brand,” puts AI first in subjects, and defines the audience primarily as Caribbean entrepreneurs interested in AI.
2. `modules/stackpenni/voice-profile.md` makes the money-system/AI-system/friction analogy the identity line and universal mechanism.
3. `modules/stackpenni/audience-insights.md` reinforces AI, technology, regional development, and entrepreneurship as the assumed audience interest set.
4. `prompts/ideas/concepts_v1.md` says voice is the frame, but has no explicit source-fit/lens-selection contract or guard against unsupported analogies.

## Proposed architectural direction

Please rule on the following approach before builder implementation:

1. **Broaden editorial remit and audience framing** to include policy, power, ownership, energy, trade, culture, people, work, humour, money, and regional life alongside AI/technology.
2. **Recast the AI/money-friction thesis as one optional recurring lens**, not the brand’s mandatory interpretive frame.
3. Add a configurable, non-deterministic **editorial lens menu** (e.g. power/ownership; policy/regional change; people/character; culture/memory; money/daily life; work/ambition; comic observation; technology/AI).
4. Require every concept to declare a source-grounded `editorial_fit`: selected lens, why it fits, and which default lenses were excluded.
5. Add bounded validation and repair: reject unsupported AI/sou-sou/entrepreneur frames; require material source evidence; enforce within-batch lens diversity; return fewer cards rather than inserting bad framing.
6. Supply recent lens/phrase-family balance to ideation so overused frames are visible but not mechanically forbidden.

This is intentionally **prescriptive, not deterministic**: the LLM retains editorial freedom, but must justify the lens from the source rather than reflexively translating every topic into the same metaphor.

## Requested architect response

Please provide an amendment/ruling that confirms or revises:

- the intended StackPenni editorial scope and non-compulsory role of AI, sou-sou, entrepreneurship, and Caribbean naming;
- whether the proposed source-fit `editorial_fit` contract and lens catalogue are the correct architectural boundary;
- the appropriate validation/retry behavior and whether recent lens-balance should be a prompt signal only or a gate;
- any migration/review direction for the current repetitive queue, particularly the source-111 Guyana cluster.

## Builder containment

No voice module, audience module, prompt, schema, or production behavior has been changed for this request. The earlier source-randomization and sentence-complete existing-idea changes remain deployed, but they do not solve this broader editorial-range problem.

A detailed implementation proposal is available at `.hermes/plans/2026-07-29_233722-idea-generation-thematic-range.md` in the workspace.
