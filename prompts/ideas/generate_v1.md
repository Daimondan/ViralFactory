<!-- version: 1.0 -->
# Idea Card Generation

You are generating idea cards for a content co-creation system. Each card is the first artifact in the staged pipeline — it carries the idea, hook options, and a full treatment block.

## Context
- Business: {business_name}
- Subjects: {subjects}
- Audience: {audience_description}
- Origin type: {origin_type}

## Source material (from the Source Bank and living modules)

{source_material}

## Available modules (consult these to ground ideas and treatments)

### Viral Patterns
{viral_patterns}

### Audience Insights
{audience_insights}

### Story Frameworks
{story_frameworks}

### Format Guide
{format_guide}

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
   - **rationale**: why this scope + format for this idea and audience, citing the modules consulted

4. **origin** — must be "{origin_type}"

5. **evidence_links** — list of {url, note} objects linking to the source material that grounds this idea

6. **seed_text** — (only for human_seeded or human_seeded_ai_developed) the original seed from the person

## Rules

- Ideas must be grounded in the source material and modules — never generic
- The treatment's format MUST come from the Format Guide (existing entry) OR be a new experimental format (experimental=true with full spec)
- capture_required tasks must be specific and actionable — not vague
- The rationale must cite which modules were consulted and why this format/scope fits
- For ai_originated: cross-reference Source Bank items with Viral Patterns, Audience Insights, Story Frameworks, and Format Guide
- For human_seeded: the idea IS the person's seed; don't change it — build the treatment around it
- For human_seeded_ai_developed: sharpen the seed — propose angle variants, attach supporting Source Bank material. The seed_text is the original; the idea is the sharpened version.
- Do not invent evidence links — use the URLs from the source material
- Each hook option must be different in approach (not just reworded)

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
      "evidence_links": [
        {"url": "string", "note": "string"}
      ],
      "seed_text": "string"
    }
  ]
}
```