<!-- version: 1.0 -->
# Format-Neutral Idea Concept Generation

Generate source-grounded content concepts before making production or distribution decisions.

## Context
- Business: {business_name}
- Subjects: {subjects}
- Audience: {audience_description}
- Origin: {origin_type}

## User distribution intent

{distribution_intent}

When mode is `open` or `platform_constrained`, do not invent the concept by matching it to a familiar format. Establish the idea's claim, audience value, narrative shape, and evidence first. When mode is `exact_format`, the user's chosen medium is a real constraint: propose only concepts that can be expressed strongly in it, but do not design the treatment yet.

## Voice

{voice_profile}

Ideas must be born in this person's mental shape and stated in their voice. Sources are material; voice is the frame.

## Source Bank

{source_material}

## Source Criteria

{source_criteria}

## Viral Patterns

{viral_patterns}

## Audience Insights

{audience_insights}

## Story Frameworks

{story_frameworks}

## Existing ideas

{existing_ideas}

## Kill lessons

{kill_lessons}

## Task

Generate up to {num_cards} materially distinct concepts. Each concept includes:

- `idea`: the concept in 1-3 sentences.
- `hook_options`: 2-3 genuinely different openings.
- `concept_basis.core_claim`: the proposition the piece earns.
- `concept_basis.audience_value`: why this audience would care.
- `concept_basis.narrative_shape`: the natural movement of the idea, described without naming a social format.
- `concept_basis.available_evidence`: concrete evidence, scenes, data, examples, voice, or visual material actually available.
- `origin`: exactly `{origin_type}`.
- `source_refs` and `source_notes`: real Source Bank IDs and what each contributes.
- `seed_text`: preserve the original seed where applicable.

Do not output a treatment, platform choice, format choice, capture plan, derivative plan, or scope. Those decisions happen in the next stage after the concept is locked.

For human-seeded work, preserve the seed's intent. For `human_seeded`, the idea is the seed. For `human_seeded_ai_developed`, sharpen without replacing it.

Return fewer concepts rather than padding weak or duplicate ideas.

Respond with ONLY valid JSON:

```json
{
  "cards": [
    {
      "idea": "string",
      "hook_options": ["string", "string"],
      "concept_basis": {
        "core_claim": "string",
        "audience_value": "string",
        "narrative_shape": "string",
        "available_evidence": ["string"]
      },
      "origin": "ai_originated|human_seeded|human_seeded_ai_developed",
      "source_refs": [14],
      "source_notes": [{"source_id": 14, "note": "string"}],
      "seed_text": "string"
    }
  ]
}
```
