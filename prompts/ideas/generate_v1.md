<!-- version: 1.3 -->
# Idea Card Generation

You are generating idea cards for a content co-creation system. Each card is the first artifact in the staged pipeline — it carries the idea, hook options, and a full treatment block.

## Context
- Business: {business_name}
- Subjects: {subjects}
- Audience: {audience_description}
- Origin type: {origin_type}

## Source Bank (addressable sources — cite by ID)

The following sources are available. Each is prefixed with its ID in brackets, e.g. [S14]. You MUST cite at least one source by ID in every card's `source_refs`. Ideas that synthesize two or more sources into a single story are encouraged — when multiple sources together reveal a pattern, contrast, or arc that no single source shows, that composition is itself the idea. State in the rationale what each cited source contributes.

{source_material}

## Source Criteria (rules for evaluating sources)

{source_criteria}

## Available modules (consult these to ground ideas and treatments)

### Viral Patterns
{viral_patterns}

### Audience Insights
{audience_insights}

### Story Frameworks
{story_frameworks}

### Format Guide
{format_guide}

## Existing ideas (avoid repetition)

The following idea cards already exist. Every card you generate MUST be materially distinct from every listed idea — different angle, not synonym-swapped. If the source material cannot support {num_cards} distinct ideas, return fewer and say so in the rationale rather than padding with near-duplicates.

{existing_ideas}

## Kill lessons (anti-patterns to avoid)

The following idea cards were killed by the operator. Treat these as anti-patterns — do not generate ideas that repeat the same mistakes.

{kill_lessons}

## Format usage (recent history)

The following shows how often each format has been used recently. Use this to spread across formats — default to proven formats, but choosing a heavily-used format requires the rationale to say why this idea demands it. Experimental formats remain allowed.

{format_usage}

## Your task

Generate {num_cards} idea card(s) as JSON. Each card MUST include:

1. **idea** — the core concept, stated in 1-3 sentences. Grounded in the source material and modules. Not generic — specific to this business and audience.

2. **hook_options** — 2-3 alternative hooks/titles for the piece. Each hook is a single line that would stop the scroll.

3. **treatment** — the production decision:
   - **scope.type**: "one_off" | "series_of_n" | "pillar_with_derivatives"
     - If series_of_n: include "n" (number of pieces) and "cadence" (e.g. "weekly", "daily")
   - **format.format_name**: a format from the Format Guide above
   - **format.experimental**: true if this is a new format debuting on this card, false if it's an existing Format Guide entry
   - **format.format_spec**: (only if experimental=true) the full format specification — what it is, structural mechanics, capture needs, effort
   - **capture_required**: list of human capture tasks (e.g. "Record 15s of street footage in Bridgetown"). Empty list if none.
   - **reuse.derived_from**: (optional) parent card ID if this is a derivative
   - **reuse.reuse_notes**: (optional) how this piece can be reused
   - **rationale**: why this scope + format for this idea and audience, citing the modules consulted. If choosing a heavily-used format, the rationale must say why this idea demands it specifically. State what each cited source contributes.

4. **origin** — must be "{origin_type}"

5. **source_refs** — list of source IDs (integers) from the Source Bank above, e.g. [14, 22]. Every idea MUST cite at least one source by ID. One idea may cite multiple sources when they compose into a single story. Each ID must correspond to a real source listed above.

6. **source_notes** — (optional) list of {source_id, note} objects giving a short per-source annotation explaining what that source contributes to this idea.

7. **seed_text** — (only for human_seeded or human_seeded_ai_developed) the original seed from the person

## Rules

- Ideas must be grounded in the source material and modules — never generic
- Every idea MUST cite at least one source by ID from the Source Bank — no exceptions
- Ideas that synthesize two or more sources into a single story are encouraged — when multiple sources together reveal a pattern, contrast, or arc that no single source shows, that composition is itself the idea
- State in the rationale what each cited source contributes to the idea
- Every idea MUST be materially distinct from the existing ideas listed above — different angle, not synonym-swapped
- Do not repeat patterns that led to killed cards (see kill lessons above)
- The treatment's format MUST come from the Format Guide (existing entry) OR be a new experimental format (experimental=true with full spec)
- capture_required tasks must be specific and actionable — not vague
- The rationale must cite which modules were consulted and why this format/scope fits
- For ai_originated: cross-reference Source Bank items with Viral Patterns, Audience Insights, Story Frameworks, and Format Guide
- For human_seeded: the idea IS the person's seed; don't change it — build the treatment around it
- For human_seeded_ai_developed: sharpen the seed — propose angle variants, attach supporting Source Bank material. The seed_text is the original; the idea is the sharpened version.
- Each hook option must be different in approach (not just reworded)
- If the source material cannot support {num_cards} distinct ideas, return fewer cards rather than padding with near-duplicates

## Output format

Respond with ONLY valid JSON:

```json
{
  "cards": [
    {
      "idea": "string",
      "hook_options": ["string", "string"],
      "treatment": {
        "scope": {
          "type": "one_off|series_of_n|pillar_with_derivatives",
          "n": 0,
          "cadence": "string"
        },
        "format": {
          "format_name": "string",
          "experimental": false,
          "format_spec": "string"
        },
        "capture_required": ["string"],
        "reuse": {
          "derived_from": 0,
          "reuse_notes": "string"
        },
        "rationale": "string"
      },
      "origin": "ai_originated|human_seeded|human_seeded_ai_developed",
      "source_refs": [14, 22],
      "source_notes": [
        {"source_id": 14, "note": "string"}
      ],
      "seed_text": "string"
    }
  ]
}
```