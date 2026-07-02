<!-- version: 1.0 -->
# Asset Fan-out (per-platform variant)

You are producing a per-platform variant of a master draft. The human has already reviewed and approved the master draft. Now adapt it for a specific platform.

## Context
- Business: {business_name}
- Platform: {platform_name} ({platform_handle})
- Source format: {format}

## Master draft (approved by the human)

{draft_text}

## Visual direction (from the draft)

{visual_direction}

## Your task

Adapt the master draft for {platform_name}. Produce the platform-specific text/caption as it would be posted. This is NOT a new piece — it's the same content adapted for this platform's format, length, and audience expectations.

## Rules

- Preserve the voice and message — this is the SAME piece, not a new one
- Adapt length to platform norms (X threads = multiple posts, IG = caption, etc.)
- Include platform-specific formatting (hashtags, line breaks, etc.)
- Generate image prompts for this platform's aspect ratio and style
- Do NOT add new content the human didn't approve
- The variant_type should describe what this is (thread, single_post, carousel, reel_script, etc.)

## Output format

Respond with ONLY valid JSON:

```json
{
  "content": "string — the full platform-specific text as it would be posted",
  "variant_type": "string — thread | single_post | carousel | reel_script | etc.",
  "image_prompts": ["string — prompts for generating images for this platform"]
}
```