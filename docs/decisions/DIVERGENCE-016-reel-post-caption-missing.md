# DIVERGENCE-016: Reel assets have no post caption — summary line ships as public caption

**Filed by:** Builder
**Date:** 2026-07-24
**Status:** PROPOSED — awaiting architect review
**Severity:** P1 — violates per-piece approval rule (charter §4)
**Type:** STRUCTURE / LOGIC

## The gap

When an IG reel asset is published, the Buffer adapter sends `asset["content"]` as the post's `text` field (`src/buffer_adapter.py:233`). That `content` field is populated from `platform_content[0].get("content")` (`src/pipeline.py:1278`), which the Writer prompt (`prompts/draft/generate_v4.md:120`) defines as:

> `content`: a summary line or the full text for single-post formats

For reel format, `posts` = frame objects (the video script: `vo_text`, `text_on_screen`, `visual`, etc.). The `content` field is a one-line internal summary — **not** the caption that appears under the reel in the Instagram feed.

There is no distinct post-caption artifact anywhere in the pipeline:
- The Writer prompt has no field for "caption text that accompanies the reel when posted"
- Gate 3 (asset review) shows and approves the video — never a caption
- Gate 4 (publish) sends the summary line to Buffer as the public caption
- The operator never sees, reviews, edits, or approves the text that will appear under the reel

## Why this is a defect

1. **Violates per-piece approval (charter §4, hard business rule).** No code path may post without explicit human approval on that piece. The reel video is approved; the caption text that ships alongside it is not.
2. **The summary line is not a caption.** It was written as an internal summary, not as platform-native post copy. It lacks hooks, CTAs, hashtags, and the voice-profile tone that makes a caption read human.
3. **The operator can't catch a bad caption.** A misleading, off-brand, or empty summary ships to the public feed with no review.
4. **Same gap applies to `story_series`** — any video format where `posts` are frame objects rather than text strings.

## Proposed fix

### 1. Writer prompt (`prompts/draft/generate_v4.md`)

Add a `post_caption` field to `platform_content` entries for video formats (reel, story_series):

```json
{
  "platform": "instagram",
  "variant_type": "reel",
  "content": "summary line (internal, unchanged)",
  "post_caption": {
    "text": "The full caption text that appears under the reel when posted — hook, context, CTA, hashtags. Written in the person's voice from the Voice Profile. Platform-native.",
    "hashtags": ["#stackpenni", "#caribbeanwealth"]
  },
  "posts": [ ... frame objects ... ]
}
```

Rules for the Writer:
- `post_caption` is REQUIRED for reel and story_series variants
- `post_caption.text` is the actual text that will be posted under the video — not a description of it
- Written in the person's voice, platform-native, self-audited against the AI Tells Catalog
- `post_caption.hashtags` is an array of hashtags (may be empty)
- For text formats (thread, carousel, single_post, newsletter, poll), `post_caption` is NOT used — the `posts` array IS the post text

### 2. Asset storage (`src/pipeline.py`)

Add a `post_caption` column to the `assets` table (additive migration). When assets are created from platform_content, extract `post_caption` from the platform_content entry and store it.

### 3. Gate 3 — asset review (`src/app.py`, asset review template)

Show the `post_caption` text alongside the video preview for reel/story_series assets. The operator can edit it inline before approving (same pattern as draft platform-content editing). Approval at Gate 3 approves both the video AND the caption.

### 4. Gate 4 — publish (`src/buffer_adapter.py`, `src/app.py`)

When publishing a reel/story_series asset, use `asset["post_caption"]` (parsed) as the Buffer `text` field — NOT `asset["content"]`. Fall back to `asset["content"]` only for legacy assets without a post_caption (backward compat).

### 5. Schema + validator

Add `post_caption` to the Writer output JSON schema. Validator requires it for reel/story_series variant_types.

### 6. Tests

- Writer output for a reel includes a non-empty `post_caption.text`
- Asset stores `post_caption` and it survives the pipeline
- Gate 3 shows the caption
- Publish sends `post_caption.text` to Buffer, not `content`
- Legacy asset without `post_caption` falls back to `content` (no breakage)
- `post_caption` is self-audited (AI tells flagged and fixed)

## Scope

- Affects: reel and story_series variants only
- Does NOT affect: text formats (thread, carousel, single_post, newsletter, poll) — their `posts` array IS the post text, already shown and approved at Gate 3
- Backward compatible: legacy assets without `post_caption` fall back to `content`

## What needs architect ruling

1. Is `post_caption` as a structured object (`text` + `hashtags`) the right shape, or should it be a single string (hashtags inline)?
2. Should the Writer produce the caption in the same pass as the reel script, or should it be a separate generation step (so the caption can reference the final video)?
3. Should Gate 3 caption editing be inline (like draft platform-content editing) or a separate modal?