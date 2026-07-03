<!-- version: 2.0 -->
# Visual Style Guide Analysis

You are building a Visual Style Guide module for a content co-creation system — establishing the visual identity and the real-vs-generated blend rules.

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

## Brand assets the operator provided (logo, colors, type preferences)

{brand_assets}

## Visual examples the operator likes (3–5 references with notes)

{visual_examples}

## Shot library summary (indexed items the operator uploaded)

{shot_library_summary}

## Your task

Produce a structured Visual Style Guide as JSON with:

1. **palette** — color scheme: primary, secondary, accent, background (hex codes + descriptive names)
2. **typography** — type feel: font family suggestions, weight, sizing philosophy (not specific fonts — the feel)
3. **stylization_level** — how stylized should generated visuals be? (minimal | moderate | heavy) with rationale
4. **blend_rules** — how real footage and generated visuals combine:
   - real_anchors: what kinds of claims/living detail require real footage
   - generated_supporting: what generated visuals are for (supporting, stylized layer)
   - disclosure: platform AI-disclosure rules to follow
5. **platform_adjustments** — per-platform visual tweaks (aspect ratios, caption styling, etc.)
6. **shot_library_usage** — how the indexed shot library should be used in drafts

## Rules

- Palette must be actionable: hex codes, not just "blue"
- Blend rules must align with the charter: real footage anchors trust; generated is supporting, never the primary visual
- Stylization level is a hypothesis, not a permanent rule — the inward loop updates it
- Platform adjustments must cover all platforms the business publishes on
- Do not invent brand assets the operator didn't provide — work from what they gave
- Typography describes the FEEL, not specific font files (the operator picks the actual fonts)
- Mine the conversation transcript and materials for visual style references the brand_assets and visual_examples lists don't capture
- The shot_library_summary contains actual uploaded materials — reference them by name

## Output format

Respond with ONLY valid JSON:

```json
{
  "palette": {
    "primary": {"hex": "#XXXXXX", "name": "string"},
    "secondary": {"hex": "#XXXXXX", "name": "string"},
    "accent": {"hex": "#XXXXXX", "name": "string"},
    "background": {"hex": "#XXXXXX", "name": "string"}
  },
  "typography": {
    "feel": "string — the type personality",
    "weight": "string — light/regular/bold preference",
    "sizing": "string — hierarchy philosophy"
  },
  "stylization_level": "minimal|moderate|heavy",
  "stylization_rationale": "string",
  "blend_rules": {
    "real_anchors": ["string — what requires real footage"],
    "generated_supporting": ["string — what generated visuals are for"],
    "disclosure": ["string — platform AI-disclosure rules"]
  },
  "platform_adjustments": [
    {"platform": "string", "aspect_ratio": "string", "notes": "string"}
  ],
  "shot_library_usage": "string"
}
```
