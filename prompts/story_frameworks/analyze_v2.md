<!-- version: 2.0 -->
# Story Frameworks Analysis

You are building a Story Frameworks module for a content co-creation system — how to tell a story per subject type for this business.

## Context
- Business name: {business_name}
- Business subjects (tag taxonomy): {subjects}
- Audience: {audience_description}

## Routed seeds (from onboarding conversation)

{routed_seeds}

## Full conversation transcript

{conversation_transcript}

## Uploaded materials (full content)

{materials_content}

## Admired examples (from Viral Patterns intake — for grounding)

{admired_examples}

## The operator's own stories (spoken or typed — stories they tell often)

{operator_stories}

## Voice Profile summary (for voice-compatibility checking)

{voice_summary}

## Your task

For each core subject type in the taxonomy, draft a story framework as JSON. Each framework must have:

1. **subject_type** — from the business's subject taxonomy
2. **entry_point** — how the story opens (the hook, grounded in an admired example)
3. **tension** — the conflict, question, or stakes
4. **turn** — the shift, revelation, or pivot
5. **landing** — how it lands (the takeaway, the call, the punch)
6. **grounded_in_example** — which admired example informs this framework
7. **grounded_in_story** — which of the operator's own stories informs this
8. **voice_compatible** — boolean: does this framework fit the Voice Profile?
9. **voice_note** — if not fully compatible, what to adjust

## Rules

- One framework per subject type — no more, no less
- Entry points must be specific, not generic ("Start with a contrarian claim about AI" not "Start with a hook")
- Grounding in admired examples: cite the specific URL/name
- Grounding in operator stories: use the operator's actual story, not an invented one
- Voice compatibility: if the framework requires a pattern the Voice Profile says to avoid, mark voice_compatible=false and explain in voice_note
- Frameworks should be actionable: a drafter reading this should know exactly how to structure content for that subject type
- Mine the conversation transcript and materials for story references the operator_stories list doesn't capture

## Output format

Respond with ONLY valid JSON:

```json
{
  "frameworks": [
    {
      "subject_type": "string — from taxonomy",
      "entry_point": "string — specific hook approach",
      "tension": "string — the conflict or stakes",
      "turn": "string — the shift or revelation",
      "landing": "string — the takeaway",
      "grounded_in_example": "string — admired example URL/name",
      "grounded_in_story": "string — operator's story reference",
      "voice_compatible": true,
      "voice_note": "string — empty if compatible, adjustment guidance if not"
    }
  ],
  "summary": "string — one paragraph plain-language summary"
}
```
