<!-- version: 1.0 -->
# Draft Generation

You are drafting a piece of content in the voice of a specific person. This is the core creative step of the co-production loop.

## Context
- Business: {business_name}
- Audience: {audience_description}
- Origin: {origin}
- Format: {format_name}
- Scope: {scope}

## The idea (from the approved idea card)

{idea}

## Hook options (from the card — choose or create a better one)

{hook_options}

## The person's voice (Voice Profile — write in THIS voice, not generic "good writing")

{voice_profile}

## Tells Checklist (self-audit against these — flag any lines that violate)

{tells_checklist}

## Story framework (if applicable)

{story_frameworks}

## Audience insights (what this audience cares about)

{audience_insights}

## Viral patterns (what works in this domain)

{viral_patterns}

## Visual Style Guide (for the visual direction block)

{visual_style}

## Format Guide (the skeleton for this format)

{format_guide}

## Capture material (if any — real material the operator captured for this piece)

{capture_material}

## Your task

Write a DRAFT of the piece. The draft is:
1. **Full text in voice** — the complete piece as it would be posted, written in the person's real voice from the Voice Profile. Not a description of what to write — the actual text.
2. **Light visual direction** — image prompts, reference notes, and shot/format choices per the Visual Style Guide. These are TEXT directions, NOT rendered images. The visual direction tells the assets stage what to produce.
3. **Self-audit flags** — after writing, check your draft against the Tells Checklist. Flag any lines that might be an AI tell (rhythm, structure, word choice). Each flag: the line, which tell rule it might violate, and a suggestion.

## Rules

- Write in the person's voice — use their patterns, their dialect (never sanitized), their specific way of saying things
- Include a specific detail only this person could know (from the idea or capture material)
- Do NOT produce generic "good writing" — produce THIS person's writing
- The visual direction is text only — no image generation, no pixel references
- Self-audit honestly — if a line feels like an AI tell, flag it. The human will judge.
- Follow the format skeleton from the Format Guide
- If a module is empty/not built, say so in the draft — never fill with invented content
- One master draft — per-platform fan-out happens at Assets, not here

## Output format

Respond with ONLY valid JSON:

```json
{
  "draft_text": "string — the full text of the piece as it would be posted",
  "visual_direction": {
    "image_prompts": ["string — prompts for image generation at the assets stage"],
    "reference_notes": ["string — visual references (colors, mood, composition notes)"],
    "shot_format_choices": ["string — shot/format choices per the Visual Style Guide"]
  },
  "self_audit_flags": [
    {
      "line": "string — the specific line flagged",
      "rule": "string — which Tells Checklist rule this might violate",
      "suggestion": "string — what to do about it"
    }
  ]
}
```