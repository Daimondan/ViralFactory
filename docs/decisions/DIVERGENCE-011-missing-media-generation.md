# DIVERGENCE-011: Missing-media generation (Option C — per-segment choice)

**Date:** 2026-07-07
**Filed by:** Builder
**Status:** Proposed — awaiting architect review
**Type:** FEATURE / STRATEGIC

## Context

The Assembler's video generation path (edit plan → render) was producing garbage output because:

1. Reel formats require human-captured footage (street scenes, screen recordings)
2. The operator often hasn't uploaded those captures
3. The system had no guard — it let you click "Generate video" with no real ingredients
4. The LLM cobbled together a plan using 2 static cover images, producing a 30s video of two frames alternating with no audio

A hard capture guard was added (block video generation when capture_required tasks are unfulfilled). The operator pushed back: **the guard should let the user choose to have the system generate the missing media**, not just block.

## Proposal

**Option C — Per-segment choice:** When required captures are missing, the system offers two AI-generation paths per segment instead of hard-blocking:

1. **Generate with AI (Grok)** — Use `grok-imagine-video` (xAI, already configured) to generate each missing B-roll segment as a 5-second video clip. The edit plan generates a video prompt per segment, the system submits to xAI, polls until done, registers the result as `generated:` media, then renders.

2. **Search stock (Pexels/Pixabay)** — Wire up stock API keys. The system searches stock libraries for each segment's description, downloads matching clips, caches them, and uses those as `stock:` ingredients.

The operator picks per segment which approach to use. The existing "Upload captures" path remains.

## Generator logic

**Current generators available:**

| Generator | Provider | What it produces | Config key | Status |
|-----------|----------|------------------|------------|--------|
| Image generation | OpenRouter (Gemini 3.1 Flash) | Static images from prompts | `media.image_default` | ✅ Working |
| Video generation | xAI (Grok Imagine Video) | 5-second video clips from prompts | `media.video_default` | ⚠️ Configured, needs XAI_API_KEY |
| Stock footage | Pexels, Pixabay | Real video clips by search query | `stock.providers` | ❌ API keys not set |
| Voice cloning | Qwen3 TTS | Narration from script | `voice_cloning.engine` | ⚠️ Configured, untested |
| Assembly renderer | FFmpeg | Stitches segments + burns captions | (local) | ✅ Working |

**Do we need Blender or other services?**

No. Blender is a 3D animation/compositing tool — wrong fit for this use case:
- We need real-looking B-roll footage, not 3D animation
- Blender requires GPU compute and significant render time
- Island bandwidth makes large tool downloads impractical
- The existing FFmpeg renderer already handles compositing (captions, transitions, audio mixing)

The two generators we need (Grok for AI video, Pexels/Pixabay for stock) are already wired in the codebase. The missing piece is the orchestration logic that generates per-segment prompts and submits them.

## Implementation plan

### 1. Change capture guard (app.py)
- From hard-block (return 400) to soft warning
- Return the missing capture tasks + available generation options
- Let the operator proceed with AI generation if they choose

### 2. New endpoint: `/api/assets/<id>/generate-segment`
- Input: `{segment_index, method: "ai"|"stock", prompt}`
- If `method=ai`: submit to Grok video API, poll, register as generated media
- If `method=stock`: search Pexels/Pixabay, download, cache, register as stock media
- Returns the ingredient ID for the generated/downloaded clip

### 3. New endpoint: `/api/assets/<id>/search-stock`
- Input: `{query, kind: "video"}`
- Searches Pexels/Pixabay, returns cached results
- Operator picks a clip, it gets registered as `stock:` ingredient

### 4. Assembler UI update (assets.html)
- When captures are missing, show a panel listing each missing capture task
- Per task: "Upload" button + "Generate with AI" button + "Search stock" button
- After generation completes, the ingredient appears in the inventory

### 5. Edit plan prompt update (edit_plan_v1.md)
- When ingredients include AI-generated clips, use them
- When stock clips are cached, use them
- Generate per-segment video prompts when the operator chooses AI generation

## Charter compliance

- **Config-driven**: Generator choice stays in `config/models.yaml` — no hardcoded provider names
- **LLM does judgment**: The edit plan LLM decides how to use available ingredients; generation prompts are LLM-produced
- **Mechanics use boring libraries**: FFmpeg for assembly, HTTP clients for API calls
- **Per-piece approval**: The operator chooses per segment whether to generate or search stock — no auto-generation without consent
- **No business values in code**: All prompts, queries, descriptions are LLM-generated from the script content

## Open questions for architect

1. Should the system auto-generate ALL missing segments with one click, or require per-segment approval?
2. Should stock footage search be automatic (search per segment description) or manual (operator types query)?
3. Should the generated clips replace the need for human capture entirely, or should the system still recommend human capture as the preferred path?