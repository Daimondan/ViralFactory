# DIVERGENCE-022: Reel assets have no post caption — summary line ships as public caption

**Filed by:** Builder
**Date:** 2026-07-24
**Status:** APPROVED — architect ruling issued (2026-07-24). No charter amendment required (bug fix enforcing existing rule).
**Severity:** P1 — violates per-piece approval rule (charter §5)
**Type:** STRUCTURE / LOGIC
**Renumbered from:** DIVERGENCE-016 (collision with ratified DIVERGENCE-016-inspiration-center-and-trend-discovery → AMENDMENT-012)

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

1. **Violates per-piece approval (charter §5, hard business rule).** No code path may post without explicit human approval on that piece. The reel video is approved; the caption text that ships alongside it is not.
2. **The summary line is not a caption.** It was written as an internal summary, not as platform-native post copy. It lacks hooks, CTAs, hashtags, and the voice-profile tone that makes a caption read human.
3. **The operator can't catch a bad caption.** A misleading, off-brand, or empty summary ships to the public feed with no review.
4. **Same gap applies to `story_series`** — any video format where `posts` are frame objects rather than text strings.

## Architect ruling — 2026-07-24

The divergence is **APPROVED**. The proposed fix is correct in scope and approach. No charter amendment is needed — this is a bug fix that enforces the existing per-piece approval rule (§5). The caption is part of the piece; the charter already says every piece passes human approval. The fix adds the missing artifact and gate, it does not change the rule.

### Ruling on the three open questions

**Q1: Shape — `post_caption` as structured object `{text, hashtags[]}`, or single string with hashtags inline?**

**RULING: Structured object `{text, hashtags[]}`.**

- Hashtags are a distinct semantic element. Platforms handle them differently. A structured shape lets the validator check hashtags separately (format, count, length) and lets future platform adapters handle them as needed.
- Additive and backward-compatible — legacy assets have no `post_caption`, so the fallback to `content` is clean.
- The builder's proposed shape is correct. Use it as specified.

**Q2: Timing — Writer produces the caption in the same pass as the reel script, or a separate generation step after the video is finalized?**

**RULING: Same pass as the reel script.**

- The caption is part of the content, not the production. The Writer knows the idea, the treatment, the voice, and the platform. It should write the caption in the same pass as the frame script.
- A separate generation step after video finalization would add pipeline complexity, a new provenance record, and a new gate, for marginal gain. The caption doesn't need to reference what's in the rendered video — it accompanies the content the operator already approved at Gate 1 (idea + treatment) and Gate 2 (draft).
- The operator edits the caption at Gate 3 alongside the video preview. If the video changes the caption context, the operator edits it then. That's the human gate's job.
- Charter principle: the LLM does judgment, the human gates. Adding a second LLM pass for the caption is over-engineering.

**Q3: Gate 3 editing — inline edit or a separate modal?**

**RULING: Inline edit, same pattern as draft platform-content editing.**

- The charter says "expandable content" — review UIs need 300+ char previews, "Show more" toggle, and "Show full content" toggle. An inline editor with expandable preview is the established pattern.
- A separate modal adds UI complexity and breaks the operator's flow. The operator is already at Gate 3 reviewing the video — they should see and edit the caption right there.
- Consistency with the draft platform-content editing pattern reduces operator cognitive load.

### Additional ruling points

1. **The `content` field stays.** It remains the internal summary line. `post_caption` is additive — it doesn't replace `content`, it adds the caption artifact alongside it.

2. **Validator must require `post_caption` for reel and story_series variants only.** For text formats (thread, carousel, single_post, newsletter, poll), `post_caption` is NOT used — the `posts` array IS the post text. The builder's scope is correct.

3. **Self-audit required.** `post_caption.text` must be self-audited against the AI Tells Catalog, same as all other Writer output. The charter requires this for all LLM-generated content.

4. **Backward compatibility.** Legacy assets without `post_caption` fall back to `content` for publish. This is correct — we don't break existing assets.

5. **No charter amendment needed.** This is a bug fix, not a design change. No charter version bump.

6. **Renumber to DIVERGENCE-022.** The original filing used DIVERGENCE-016, which collided with the already-ratified DIVERGENCE-016 (inspiration center → AMENDMENT-012). Renumbered to DIVERGENCE-022 (last filed was DIVERGENCE-021).

### Related defect noted (not part of this divergence)

During verification, the architect identified a **related bug in the thread publish path** at `src/buffer_adapter.py:232-237`:

```python
post_text = content
if posts and len(posts) > 1:
    # Thread: join posts with newlines (Buffer handles thread posts as separate items)
    post_text = content if content else posts[0]
```

For threads (where `posts` is an array of text strings), the code sends `content` (the summary line) as the Buffer text, NOT the actual thread posts. The comment says "Buffer handles thread posts as separate items" but the code doesn't actually send them as separate items — it sends the summary line. This means threads also ship the wrong text to Buffer.

This is a separate bug from the reel caption issue. The builder should file it as a separate divergence or fix it as a bug fix with tests. It is NOT in scope for DIVERGENCE-022.

## Approved fix (for builder implementation)

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

Add a `post_caption` column to the `assets` table (additive migration). When assets are created from platform_content, extract `post_caption` from the platform_content entry and store it (as JSON).

### 3. Gate 3 — asset review (`src/app.py`, `src/templates/assets.html`)

Show the `post_caption` text alongside the video preview for reel/story_series assets. The operator can edit it inline before approving (same pattern as draft platform-content editing — expandable preview, "Show more", "Show full content"). Approval at Gate 3 approves both the video AND the caption.

### 4. Gate 4 — publish (`src/buffer_adapter.py`, `src/app.py`)

When publishing a reel/story_series asset, use `asset["post_caption"]` (parsed, `post_caption.text`) as the Buffer `text` field — NOT `asset["content"]`. Fall back to `asset["content"]` only for legacy assets without a post_caption (backward compat).

### 5. Schema + validator

Add `post_caption` to the Writer output JSON schema. Validator requires it for reel/story_series variant_types. Self-audit applies to `post_caption.text`.

### 6. Tests

- Writer output for a reel includes a non-empty `post_caption.text`
- Asset stores `post_caption` and it survives the pipeline
- Gate 3 shows the caption (inline edit available)
- Publish sends `post_caption.text` to Buffer, not `content`
- Legacy asset without `post_caption` falls back to `content` (no breakage)
- `post_caption.text` is self-audited (AI tells flagged and fixed)

## Scope

- Affects: reel and story_series variants only
- Does NOT affect: text formats (thread, carousel, single_post, newsletter, poll) — their `posts` array IS the post text, already shown and approved at Gate 3
- Backward compatible: legacy assets without `post_caption` fall back to `content`

## Charter compliance

- **Preserved:** Per-piece approval (§5) — the caption is now part of the piece, reviewed and approved at Gate 3.
- **Preserved:** No business values in code — hashtags come from the Writer prompt (voice-profile-driven), not hardcoded.
- **Preserved:** LLM does judgment — the Writer writes the caption, not a Python heuristic.
- **Preserved:** Self-audit — `post_caption.text` is self-audited against the AI Tells Catalog.
- **No charter amendment needed** — this enforces an existing rule, not a new one.