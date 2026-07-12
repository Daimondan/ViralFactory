<!-- version: 1.0 -->
# Idea Treatment Selection

The creative concepts below are locked. Choose how each one should be expressed without changing its claim, sources, or voice.

## Context
- Business: {business_name}
- Audience: {audience_description}

## User distribution intent

{distribution_intent}

Modes:
- `open`: choose one primary platform and one primary format per concept.
- `platform_constrained`: choose one format native to one of the allowed platforms.
- `exact_format`: use exactly the user's one platform and one format. Do not substitute.

## Locked concepts

{concept_cards}

## Descriptive Format Guide

{format_guide}

This guide describes audience experience, native mechanics, expressive strengths, limitations, production demands, and evidence. It is not a routing table. Never reduce selection to category mappings such as “hot take → Reel” or “explainer → Carousel.”

## Recent format usage

{format_usage}

Fit comes first. When two formats fit comparably well, recent underrepresentation may break the tie. Never force a poor fit for variety.

## Task

Return the same concepts as complete idea cards, adding a treatment while preserving `idea`, `hook_options`, `origin`, `source_refs`, `source_notes`, and `seed_text`.

For each treatment:

1. Choose scope: `one_off`, `series_of_n`, or `pillar_with_derivatives`. Do not default to derivatives merely because multiple platforms exist.
2. Choose exactly one `primary_platform` and one `format_name`.
3. Set `constraint_source` to `user_request` for platform-constrained or exact-format requests; otherwise use `llm_selected`.
4. Explain `selection_reason` through the particular idea's expressive needs, audience experience, native mechanics, evidence, limitations, and production feasibility.
5. In open mode, record up to two genuine `alternatives_considered`. In exact-format mode, use an empty list; the user already decided.
6. Add specific `capture_required` tasks only where the treatment actually needs them.
7. Keep `reuse` optional. There is no obligation to produce for both X and Instagram.
8. In `rationale`, explain scope and source contributions as well as the format decision.
9. Existing guide entries use `experimental: false`. A new format requires `experimental: true` and a complete `format_spec`.

If an exact requested format cannot express a concept strongly, omit that concept rather than silently changing the destination.

Respond with ONLY valid JSON matching this shape:

```json
{
  "cards": [
    {
      "idea": "string",
      "hook_options": ["string"],
      "treatment": {
        "scope": {"type": "one_off|series_of_n|pillar_with_derivatives", "n": 0, "cadence": "string"},
        "format": {
          "primary_platform": "string",
          "format_name": "string",
          "experimental": false,
          "constraint_source": "user_request|llm_selected",
          "selection_reason": "string",
          "alternatives_considered": [
            {"platform": "string", "format_name": "string", "reason_not_selected": "string"}
          ],
          "format_spec": "string"
        },
        "capture_required": ["string"],
        "reuse": {"derived_from": 0, "reuse_notes": "string"},
        "rationale": "string"
      },
      "origin": "string",
      "source_refs": [14],
      "source_notes": [{"source_id": 14, "note": "string"}],
      "seed_text": "string"
    }
  ]
}
```
