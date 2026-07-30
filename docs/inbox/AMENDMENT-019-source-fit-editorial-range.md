# AMENDMENT-019 — Source-fit editorial range and inspectable lens selection

**Filed:** 2026-07-30
**Filed by:** Architect
**Status:** APPROVED — ratifies DIVERGENCE-026
**Ratifies:** `docs/decisions/DIVERGENCE-026-idea-generation-source-fit-and-editorial-range.md`
**Type:** LOGIC / STRATEGIC / STRUCTURE

## Editorial ruling

For any tenant, identity is a point of view—not a compulsory wrapper. For StackPenni specifically:

- Caribbean perspective remains foundational, but the word “Caribbean” need not appear in every concept.
- AI, sou-sou, entrepreneurship, “the machine,” friction, and direct address to entrepreneurs are optional lenses. They require material support from the source or an explicit human seed.
- Policy, power, ownership, energy, trade, land, work, money, culture, memory, people, humour, and regional life are first-class editorial subjects.
- A source may remain on its natural stakes without being converted into advice, an AI comparison, or an entrepreneur callout.

## Contract

Each generated concept must persist:

```json
"editorial_fit": {
  "primary_lens": "configured_lens_id",
  "why_this_lens": "source-specific justification",
  "evidence_refs": [{"source_id": 111, "evidence": "specific fact/quote"}],
  "excluded_default_lenses": ["configured_lens_id"],
  "identity_expression": "how tenant perspective appears, including when implicit"
}
```

The lens catalogue and descriptions live in tenant config or a gated module—not Python. Lens choice is LLM judgment. The object travels into the stored idea card, Gate 1 UI, provenance, and later performance analysis.

## Validation boundary

1. **Mechanical Python checks:** schema completeness, configured lens IDs, resolvable source IDs, referenced source membership, duplicate IDs, configured numeric batch limits if any, persistence, and hash/provenance continuity.
2. **Editorial judgment:** a versioned Source-Fit Critic prompt + JSON schema evaluates whether the chosen lens and claims are materially supported, whether a default analogy was forced, and whether a batch has meaningful editorial range. No keyword or regex heuristic may decide source fit.
3. **Repair:** one bounded LLM repair pass receives card-specific critic findings. Cards still failing are omitted. The system returns fewer cards rather than bypassing the critic or padding.
4. **Recent balance:** mechanically computed counts from persisted `primary_lens` plus an LLM-authored, provenance-logged analysis of repeated framing families are prompt evidence. They are not a deterministic rejection gate. A current source may legitimately require an overrepresented lens.
5. **Empty source bank:** AI-originated generation returns no cards and a plain-language next action. Human seeds remain valid because the seed is registered as source evidence.

## Module changes are gated

The builder must not directly rewrite `business.yaml`, Voice Profile, or Audience Insights as if this amendment were exact copy approval. Prepare exact proposals for operator review:

- broaden business editorial remit and audience beyond entrepreneurs/AI;
- demote the AI/money/friction thesis from universal identity to one recurring lens;
- state explicitly that AI may be absent, sou-sou is specific rather than generic, and identity may be implicit in facts/place/cadence/stakes;
- retain every current Audience Insights assertion as a belief until observed audience evidence supports it;
- add alternative audience-interest hypotheses for policy, culture, work, people, humour, money, and regional life.

No proposal becomes module/config truth before the operator sees the exact diff and approves it.

## Existing queue

No destructive migration. Create a source-111 review view/set containing cards 81, 88, 92, and 97. Recommend parking the set pending operator review, then keeping at most one only if it carries a materially distinct and source-grounded claim. Record operator kill/park reasons normally. Review other AI/sou-sou/entrepreneur wrappers in bulk-capable UI; do not mass-delete by script.

## Definition of Done

- Configured lens catalogue, `editorial_fit` schema/persistence/UI/provenance, Source-Fit Critic, one repair pass, and fewer-card fallback are implemented.
- No AI/sou-sou/entrepreneur source-fit keyword classifier exists in Python.
- Fixed-source proof includes policy, person, culture, money, and AI sources; the policy source remains policy-grounded unless evidence supports another lens.
- At least three editorial lenses appear in the controlled set when source material supports them; diversity is not manufactured against evidence.
- Module/config proposals are operator-gated and versioned.
- Current repetitive queue receives human review, not a DB patch.
- Next controlled production run reports lens distribution and card-level critic evidence.
