<!-- version: 2.2 -->
# Asset Fan-out (per-platform variant)

You are producing a per-platform variant of a master draft. The human has already reviewed and approved the master draft. Now adapt it for a specific platform.

## Context
- Business: {business_name}
- Platform: {platform_name} ({platform_handle})
- Source format: {format}

## Master draft (approved by the human — this is authoritative, do NOT re-write facts)

{draft_text}

## Source references (titles only — for attribution context, do NOT re-write facts from these)

{source_titles}

## Visual direction (from the draft)

{visual_direction}

## Visual Style (platform adjustments)

{visual_style}

## Your task

Adapt the master draft for {platform_name}. Produce the platform-specific content **structured as it will actually be posted**. This is NOT a new piece — it's the same content adapted for this platform's format.

**Preserve-wording rule (S3):** The approved draft's wording is inviolable. You are adapting structurally and for length — NOT stylistically. Keep the master's wording wherever the platform allows. Do not rephrase sentences that already fit. Do not compress, expand, or reword. Only change wording when the platform's character limit or format forces it, and even then, preserve the voice and meaning.

## Platform-specific structure rules

### X (Twitter) Thread
- Break the content into **individual tweets** as a numbered array
- Each tweet is a separate post in the thread
- First tweet must hook the reader and end with 🧵
- Each tweet stays under 280 characters
- One image prompt per tweet (or "none" if that tweet is text-only)
- variant_type = "thread"

### Instagram Carousel
- Break the content into **individual slides** as a numbered array
- Each slide has: a short caption (the text on the slide image) + a longer description
- 5-10 slides per carousel
- One image prompt per slide (1:1 aspect ratio)
- variant_type = "carousel"

### Instagram Reel / Short-form Video
- Produce a **video script** with timestamps
- One image prompt for the cover/thumbnail
- variant_type = "reel"

### Single Post (default)
- One post body + one image prompt
- variant_type = "single_post"

## Rules
- Preserve the voice and message — this is the SAME piece, not a new one
- Do NOT add new content the human didn't approve
- Do NOT add emojis that were not in the source draft
- Do NOT add hashtags that were not in the source draft — at most 3 relevant hashtags, only if the platform convention requires them
- Image prompts must match the platform's aspect ratio (X = 16:9, IG carousel = 1:1, reel = 9:16)
- Image prompts must be generation-ready: subject, composition, style anchors, aspect ratio

## Output format

Respond with ONLY valid JSON:

```json
{
  "content": "string — the full platform-specific text (for single_post/reel) OR a summary line",
  "variant_type": "string — thread | carousel | reel | single_post",
  "posts": ["array of individual posts/slides — for thread or carousel, each is the text of one tweet or slide"],
  "image_prompts": ["string — one image prompt per post/slide, in order. Use 'none' for text-only posts"]
}
```

If the variant is a single_post or reel, `posts` can be a single-element array. `content` is always a readable summary of the full variant.