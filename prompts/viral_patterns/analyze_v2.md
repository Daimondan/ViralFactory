<!-- version: 2.0 -->
# Viral Patterns Analysis

You are analyzing content the operator admires (and anti-examples they dislike) to build a Viral Patterns Playbook module for a content co-creation system.

## Context
- Business name: {business_name}
- Business subjects: {subjects}
- Audience: {audience_description}

## Routed seeds (from onboarding conversation)

{routed_seeds}

## Full conversation transcript

{conversation_transcript}

## Uploaded materials (full content)

{materials_content}

## Admired examples (links the operator wishes they'd made)

{admired_examples}

## Anti-examples (content the operator considers slop they'd never make)

{anti_examples}

## Your task

Analyze the seeds, transcript, materials, admired examples, and anti-examples. For each admired item, identify:

1. **hook_type** — how it grabs attention in the first 3 seconds/lines
2. **structure** — the narrative/argument shape (problem→solution, listicle, story arc, contrarian take, data drop, etc.)
3. **emotional_beat** — what the viewer/reader feels and when
4. **format** — the content format (thread, reel, essay, carousel, video, etc.)
5. **pacing** — how fast or slow it moves, where it pauses
6. **why_it_likely_worked** — your hypothesis for why it resonated (framed as HYPOTHESIS, never as fact)
7. **cluster** — group items into named patterns (e.g., "Contrarian Truth Bomb", "Data-Driven Debunk", "Cultural Mirror")

Then build the anti-examples into a "never" list with reasons.

## Rules

- Every analysis is a HYPOTHESIS, not a fact. Use language like "appears to work because..." never "this works because..."
- Cite the specific example URL/name in the evidence field for each pattern
- Anti-examples must have a reason — what makes them slop for THIS business
- Patterns should be actionable: a drafter reading this should know what to emulate
- Do not invent patterns the operator's examples don't support
- Hook types should be named, not generic ("Contrarian opening", not "Good hook")
- Mine the conversation transcript and materials for any viral pattern references the admired_examples list doesn't capture

## Output format

Respond with ONLY valid JSON:

```json
{
  "patterns": [
    {
      "name": "string — named pattern",
      "hook_type": "string",
      "structure": "string",
      "emotional_beat": "string",
      "format": "string",
      "pacing": "string",
      "why_it_likely_worked": "string — hypothesis framed",
      "examples": [
        {"url": "string", "name": "string", "note": "string — what to emulate"}
      ]
    }
  ],
  "never_list": [
    {
      "pattern": "string — what to avoid",
      "reason": "string — why it's slop for this business",
      "evidence": "string — which anti-example informed this"
    }
  ],
  "summary": "string — one paragraph plain-language summary"
}
```
