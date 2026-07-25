# BUILDER-NOTE-017: Reel post caption missing — DIVERGENCE-016

**From:** Builder
**Date:** 2026-07-24
**Status:** AWAITING ARCHITECT
**Severity:** P1 — violates per-piece approval (charter §4)

## What I found

IG reel assets have no post-caption artifact. When a reel is published, `buffer_adapter.py:233` sends `asset["content"]` as the Buffer `text` field — that becomes the public Instagram caption. But `content` is an internal summary line from the Writer (`prompts/draft/generate_v4.md:120`: "a summary line or the full text for single-post formats"), not caption copy. The operator never sees, reviews, edits, or approves the text that ships under the reel.

Same gap applies to `story_series`.

Full analysis and proposed fix: `docs/decisions/DIVERGENCE-016-reel-post-caption-missing.md`

## What I need from you

Three open questions before I implement:

1. **Shape** — `post_caption` as a structured object `{text, hashtags[]}`, or a single string with hashtags inline?
2. **Timing** — Writer produces the caption in the same pass as the reel script, or a separate generation step after the video is finalized (so the caption can reference what's actually in the rendered video)?
3. **Gate 3 editing** — inline edit (same pattern as draft platform-content editing) or a separate modal?

## Proposed scope (for ruling)

- Writer prompt + schema: add `post_caption` for reel/story_series, required, self-audited
- Asset storage: additive `post_caption` column on assets table
- Gate 3: show caption alongside video preview, operator can edit before approving
- Gate 4: use `post_caption.text` for Buffer publish, not `content`
- Backward compat: legacy assets without `post_caption` fall back to `content`
- Tests: writer output, storage, Gate 3 display, publish path, fallback

No code written yet — waiting on your ruling.