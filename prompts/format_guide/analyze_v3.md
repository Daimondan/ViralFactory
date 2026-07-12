<!-- version: 3.0 -->
# Format Guide Analysis

You are building a descriptive Format Guide for a content co-creation system. The guide explains what each medium enables so a later LLM can make a contextual choice. It is not a routing table and must not assign categories of messages to predetermined formats.

## Context
- Business name: {business_name}
- Platforms: {platforms}
- Business subjects: {subjects}

## Routed seeds (from onboarding conversation)

{routed_seeds}

## Full conversation transcript

{conversation_transcript}

## Uploaded materials (full content)

{materials_content}

## Format observations from analyzed winners

{format_observations}

## Platform norms

{platform_norms}

## Your task

Produce a Format Guide as JSON. Cover the formats available on the business's declared platforms. Describe each format through its native audience experience, mechanics, expressive strengths, limitations, production demands, and current evidence.

For every format include:

1. **format_name** — a clear human-readable name.
2. **platforms** — platforms where this format is native.
3. **variant_type** — structural packaging type used by production: `thread`, `carousel`, `reel`, `single_post`, `story_series`, `poll`, `newsletter`, or a new experimental type.
4. **audience_experience** — what consuming this format feels like and what the audience does.
5. **native_mechanics** — 2–6 medium-level capabilities such as sequential swiping, moving image, spoken voice, threaded reading, or structured response.
6. **expressive_strengths** — 2–6 things the medium can communicate especially well. Describe affordances, not topic categories.
7. **limitations** — 2–5 ways the format can weaken or distort an idea.
8. **production_demands** — actual media, capture, design, writing, editing, or audio requirements.
9. **length** — useful native range, not an inflexible target.
10. **structure_notes** and **skeleton** — production guidance used only after selection.
11. **requires_human_capture** and **capture_tasks** — `none`, `optional`, or `required`, with specific tasks when relevant.
12. **effort_level** — `low`, `medium`, or `high`.
13. **reuse_pathways** — optional later adaptations. Do not imply that every piece must publish on every platform.
14. **status** — `proven`, `experimental`, or `retired`.
15. **performance_evidence** — `{source, notes, last_updated}` where source is `platform_prior` or `tenant_data`. Be honest when tenant evidence does not yet exist.
16. **aspect_ratio** — native ratio or `not_applicable`.
17. **provenance** — how the entry was established.

## Rules

- Do not produce a decision table.
- Do not use `best_for` lists of message or subject categories.
- Do not encode mappings such as “hot take → Reel” or “explainer → Carousel.”
- Describe affordances in medium-level language: “carries sequential visual logic” is valid; “financial literacy explainer” is a topic category and is not valid.
- Cover only platforms declared by the business.
- A later selection LLM chooses one primary destination based on the particular idea, source material, audience experience, constraints, and production feasibility.
- Skeletons must be practical but cannot become selection authority.
- General platform knowledge starts as `platform_prior`; only observed business results qualify as `tenant_data`.
- Mine the transcript and materials for real constraints and observed evidence. Do not fabricate performance.

## Output format

Respond with ONLY valid JSON:

```json
{
  "formats": [
    {
      "format_name": "string",
      "platforms": ["string"],
      "variant_type": "string",
      "audience_experience": "string",
      "native_mechanics": ["string"],
      "expressive_strengths": ["string"],
      "limitations": ["string"],
      "production_demands": ["string"],
      "length": "string",
      "structure_notes": "string",
      "skeleton": "string",
      "requires_human_capture": "none|optional|required",
      "capture_tasks": ["string"],
      "effort_level": "low|medium|high",
      "reuse_pathways": ["string"],
      "status": "proven|experimental|retired",
      "performance_evidence": {
        "source": "platform_prior|tenant_data",
        "notes": "string",
        "last_updated": "YYYY-MM-DD"
      },
      "aspect_ratio": "string",
      "provenance": "string"
    }
  ],
  "summary": "string"
}
```
