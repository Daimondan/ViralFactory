# ARCHITECT-NOTE-2026-07-24: DIVERGENCE-022 ruling — reel post caption

**From:** Architect
**Date:** 2026-07-24
**Status:** RULING ISSUED — builder may implement
**Severity:** P1 — violates per-piece approval (charter §5)
**Inbox item:** BUILDER-NOTE-017-reel-post-caption-missing.md

## What I reviewed

BUILDER-NOTE-017 filed a P1 defect: IG reel assets have no post-caption artifact. The internal `content` summary line ships to Buffer as the public Instagram caption without operator review. Same gap for `story_series`.

I verified every claim against live code:

- `src/buffer_adapter.py:233` — `post_text = content` sent as Buffer `text` field ✓
- `src/app.py:8152` — `content=asset["content"]` passes the summary line ✓
- `src/pipeline.py:114` — assets table has `content` column, no `post_caption` ✓
- `prompts/draft/generate_v4.md:120` — `content` = "summary line or full text for single-post formats" ✓
- `src/templates/assets.html` — Gate 3 shows video + `content`, no caption field ✓
- `src/templates/publish.html:53` — shows `{{ asset.content[:500] }}` as the text to post ✓
- Charter v3.10 §5: "every piece passes human approval before posting... Hard rule" ✓

The builder's analysis is **accurate**. This is a real charter violation.

## Ruling

**APPROVED.** The proposed fix is correct in scope and approach. No charter amendment needed — this is a bug fix enforcing the existing per-piece approval rule (§5). The caption is part of the piece; the charter already says every piece passes human approval. The fix adds the missing artifact and gate; it doesn't change the rule.

### Three questions answered

1. **Shape:** Structured object `{text, hashtags[]}` — not a single string. Hashtags are a distinct semantic element; structured shape lets the validator check them separately and lets future platform adapters handle them as needed.

2. **Timing:** Same pass as the reel script — not a separate generation step. The caption is content, not production. The Writer knows the idea, treatment, voice, and platform. The operator edits at Gate 3 if the video changes the caption context. Adding a second LLM pass is over-engineering.

3. **Gate 3 editing:** Inline edit — same pattern as draft platform-content editing. Not a separate modal. Expandable preview, "Show more", "Show full content". The operator is already at Gate 3 reviewing the video — they should see and edit the caption right there.

### Additional binding points

- The `content` field stays as the internal summary. `post_caption` is additive.
- Validator requires `post_caption` for reel and story_series only. Text formats (thread, carousel, single_post, newsletter, poll) don't use it — their `posts` array IS the post text.
- `post_caption.text` must be self-audited against the AI Tells Catalog.
- Legacy assets without `post_caption` fall back to `content` for publish (backward compat).
- No charter version bump.

## Renumbering

The original filing used DIVERGENCE-016, which collided with the already-ratified DIVERGENCE-016 (inspiration center → AMENDMENT-012). Renumbered to **DIVERGENCE-022** (last filed was DIVERGENCE-021).

The old `docs/decisions/DIVERGENCE-016-inspiration-center-and-trend-discovery.md` stays as-is (already ratified under AMENDMENT-012).

The new divergence file is `docs/decisions/DIVERGENCE-022-reel-post-caption-missing.md` (I created it with the full ruling).

**Builder action:** Remove the old `docs/decisions/DIVERGENCE-016-reel-post-caption-missing.md` file (the one with the reel caption content). The renumbered DIVERGENCE-022 file is already in place.

## Related defect noted (NOT in scope for DIVERGENCE-022)

During verification I found a **related bug in the thread publish path** at `src/buffer_adapter.py:232-237`:

```python
post_text = content
if posts and len(posts) > 1:
    # Thread: join posts with newlines
    post_text = content if content else posts[0]
```

For threads, `posts` is an array of text strings (the actual thread content). But the code sends `content` (the summary line) as the Buffer text, NOT the thread posts. The comment says "Buffer handles thread posts as separate items" but the code doesn't actually do that — it sends the summary line.

This means **threads also ship the wrong text to Buffer**. The operator approved the thread posts at Gate 2 and Gate 3, but the publish path sends the summary line instead.

This is a separate bug. The builder should either:
- File it as a separate divergence, OR
- Fix it as a bug fix with tests (preferable — it's a clear plumbing error, not a design question)

It is **NOT** in scope for DIVERGENCE-022. Do not bundle them.

## What the builder should do

1. **Remove** `docs/decisions/DIVERGENCE-016-reel-post-caption-missing.md` (the reel-caption one — the renumbered DIVERGENCE-022 file is already in place with the full ruling).
2. **Implement** DIVERGENCE-022 per the approved fix in `docs/decisions/DIVERGENCE-022-reel-post-caption-missing.md`.
3. **Separately** fix or file the thread publish path bug at `buffer_adapter.py:232-237`.
4. **Update** PROGRESS.md and CHANGELOG.md when done.
5. **Move** this inbox note to `docs/inbox/processed/` after reading and applying.