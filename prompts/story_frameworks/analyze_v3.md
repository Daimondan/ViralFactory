<!-- version: 3.0 -->
# Story Frameworks Analysis

You are building a Story Frameworks module for a content co-creation system — how to tell a story per subject type for this business.

## Context
- Business name: {business_name}
- Business subjects (tag taxonomy): {subjects}
- Audience: {audience_description}

## Available narrative patterns

The following narrative patterns are available. For each subject type, SELECT the pattern that best fits the topic and audience — or propose a custom pattern if none fit (set structure_name to "custom" and define your own beats).

{narrative_patterns}

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
2. **structure_name** — name of the narrative pattern you selected (from the Available patterns above), or "custom" if you propose a new one
3. **beats** — array of {name, content} objects, one per beat in the selected pattern. Each beat's name must match the pattern's beat labels. For custom patterns, define your own beat names.
4. **grounded_in_example** — which admired example informs this framework
5. **grounded_in_story** — which of the operator's own stories informs this
6. **voice_compatible** — boolean: does this framework fit the Voice Profile?
7. **voice_note** — if not fully compatible, what to adjust

## Rules

- One framework per subject type — no more, no less
- SELECT the narrative pattern that best fits the subject matter and audience — do not default to the same pattern for every subject
- Beat content must be specific, not generic ("Start with a contrarian claim about AI adoption in Caribbean SMEs" not "Start with a hook")
- Grounding in admired examples: cite the specific URL/name
- Grounding in operator stories: use the operator's actual story, not an invented one
- Voice compatibility: if the framework requires a pattern the Voice Profile says to avoid, mark voice_compatible=false and explain in voice_note
- Frameworks should be actionable: a drafter reading this should know exactly how to structure content for that subject type
- Mine the conversation transcript and materials for story references the operator_stories list doesn't capture
- If operator stories or admired examples are empty, say so honestly in the grounding fields rather than pretending they exist

## Output format

Respond with ONLY valid JSON:

```json
{
  "frameworks": [
    {
      "subject_type": "string — from taxonomy",
      "structure_name": "string — pattern name or 'custom'",
      "beats": [
        {"name": "string — beat label", "content": "string — specific guidance"}
      ],
      "grounded_in_example": "string — admired example URL/name, or '(none provided)'",
      "grounded_in_story": "string — operator's story reference, or '(none provided)'",
      "voice_compatible": true,
      "voice_note": "string — empty if compatible, adjustment guidance if not"
    }
  ],
  "summary": "string — one paragraph plain-language summary"
}
```