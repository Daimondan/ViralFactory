<!-- version: 2.3 -->
# Draft Generation v2

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

## Grounding sources (facts, quotes, dates, specifics MUST come from these)

The following sources ground this idea. Facts, quotes, dates, statistics, and specific details in the draft MUST come from these sources. Do NOT fabricate specifics that are not present in them. If a source is marked "(summary only)", use its summary-level information with appropriate caution.

{grounding_sources}

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

## Visual Style Guide (for the visual direction block — you MUST produce visual direction here)

{visual_style}

## Format Guide (the full entry for the chosen format — structure, platform adjustments, skeleton)

{format_guide}

## Capture material (if any — real material the operator captured for this piece)

{capture_material}

## Previous draft (if revising)

{previous_draft}

## Operator feedback on the previous draft (weight 3 = authoritative edits; treat as law)

{revision_feedback}

If a previous draft exists: this is a REVISION. Preserve everything the feedback did not criticize — same hook unless criticized, same structure unless criticized. Apply weight-3 edits exactly. Do not re-imagine the piece.

## Your task

Write a DRAFT of the piece. The draft has THREE required deliverables — all three are mandatory:

### 1. Full text in voice
The complete piece as it would be posted, written in the person's real voice from the Voice Profile. Not a description of what to write — the actual text. One master draft; per-platform fan-out happens at Assets.

### 2. Visual direction (REQUIRED — not optional)
Elevated from an afterthought to a required deliverable. This must be concrete, shot-by-shot or image-by-image, written against the approved Visual Style module and the treatment's format:

- **image_prompts** (at least 1, required): generation-ready prompts for the assets stage. Each prompt must include: subject, composition, style anchors from the Visual Style module, and aspect ratio for the primary platform. A talking-head reel gets shot/beat direction; a carousel gets per-slide image prompts. Write prompts that an image generator can execute directly.
- **reference_notes** (may be empty): visual references — colors, mood, composition notes, existing brand visuals to match.
- **shot_format_choices** (at least 1, required): concrete shot or format choices per the Visual Style Guide — camera angle, movement, transition style, text overlay position, etc.

Do NOT leave these empty. If the format calls for images, produce image prompts. If it's a talking-head video, produce shot/beat direction. If it's a carousel, produce per-slide visual prompts.

### 3. Self-audit flags
After writing, check your draft against the Tells Checklist. Flag any lines that might be an AI tell (rhythm, structure, word choice). Each flag: the line, which tell rule it might violate, and a suggestion for fixing it.

## Rules

- Write in the person's voice — use their patterns, their dialect (never sanitized), their specific way of saying things
- Include a specific detail only this person could know (from the idea or capture material)
- Facts, quotes, dates, statistics, and specific details MUST come from the grounding sources — do NOT fabricate specifics not present in them
- Do NOT produce generic "good writing" — produce THIS person's writing
- The visual direction is text only — no image generation, no pixel references. But it must be concrete and actionable.
- Self-audit honestly — if a line feels like an AI tell, flag it. The human will judge.
- Follow the format skeleton from the Format Guide
- If a module is empty/not built, say so in the draft — never fill with invented content
- image_prompts and shot_format_choices must each have at least one entry — do not return empty arrays

## Output format

Respond with ONLY valid JSON:

```json
{
  "draft_text": "string — the full text of the piece as it would be posted",
  "visual_direction": {
    "image_prompts": ["string — generation-ready prompts: subject, composition, style anchors, aspect ratio"],
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