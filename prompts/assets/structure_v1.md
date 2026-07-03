<!-- version: 1.0 -->
# Structure — split approved draft into platform-native segments

You are structuring an **already-approved** draft into the segments required by its native platform format. The text is inviolable — you are NOT rewriting, adapting, or improving it. You are only splitting/arranging it into the platform structure.

## Context
- Platform: {platform_name}
- Format: {format_name}
- Variant type: {variant_type}

## Approved draft text (DO NOT REWRITE)

{draft_text}

## Your task

Split the approved draft text into the structural segments this platform format requires. You may ONLY:

1. **Split** the text at natural sentence/paragraph boundaries into posts[] or slides[]
2. **Add platform furniture**: numbering tokens like "1/7", "2/7", or slide labels like "Slide 1 (cover):"
3. **Preserve every word** from the original text — do not rephrase, compress, expand, summarize, or reword anything

You may NOT:
- Change any words
- Add new content
- Remove content
- Reorder ideas
- Add emojis or hashtags not in the source

## Output format

Respond with ONLY valid JSON:

```json
{
  "content": "string — a one-line summary of the variant",
  "variant_type": "string — thread | carousel | reel | single_post",
  "posts": ["array of segments — each is the exact text of one tweet/slide/post, with only numbering furniture added"],
  "image_prompts": ["string — one image prompt per segment, or 'none' for text-only segments"]
}
```

For single_post format: `posts` is a single-element array containing the draft text verbatim. No LLM call is needed — use the draft text directly.