# DIVERGENCE-011: Missing-media generation (LLM-driven prescriptive media plan)

**Date:** 2026-07-07
**Filed by:** Builder
**Status:** Proposed — awaiting architect review
**Type:** FEATURE / STRATEGIC

## Context

The Assembler's video generation path (edit plan → render) was producing garbage output because reel formats require human-captured footage that the operator hasn't uploaded. The system had no guard — it let you click "Generate video" with no real ingredients, producing a 30s video of two static images alternating with no audio.

A first attempt added per-capture "Generate with AI" / "Search stock" buttons that sent the raw capture task description directly to a generator. The operator correctly pushed back: **this is deterministic and produces visual inconsistency** — if you mix Grok-generated clips with Pexels stock footage, each model has a different art style, and the result is a jarring collage.

## Revised proposal — LLM-driven prescriptive media plan

The LLM should be the **creative director**. Instead of mechanically sending capture task text to generators, the system calls the LLM with:

1. The full reel script
2. The Visual Style module (palette, stylization, blend rules)
3. The list of missing captures
4. The available generators (AI video, stock search, existing media)

The LLM produces a **media generation plan** — a JSON array specifying per segment:

```json
{
  "media_plan": [
    {
      "segment_index": 0,
      "source_type": "stock",
      "search_query": "Caribbean street market Bridgetown Barbados busy daytime",
      "style_directive": "Warm natural lighting, slight handheld movement, teal-and-cream color grade to match brand palette",
      "fallback_type": "ai_video",
      "fallback_prompt": "Caribbean street market scene, warm sand cream tones, moderate stylization, 9:16 vertical, 5 seconds"
    },
    {
      "segment_index": 1,
      "source_type": "ai_video",
      "generation_prompt": "Screen recording of ChatGPT conversation explaining compound interest, phone screen, Deep Ocean Teal UI accents, warm sand cream background glow, 9:16 vertical, 5 seconds",
      "style_directive": "Match the teal/cream brand palette, moderate stylization"
    }
  ]
}
```

Key principles:
- **LLM decides generator per segment** — stock for real-world footage (streets, people), AI for conceptual/abstract segments
- **LLM writes style-consistent prompts** — every prompt includes palette anchors, stylization level, and visual language from the Visual Style module so all clips share a cohesive look
- **Fallback chain** — if stock search returns nothing, fall back to AI generation with a style-matched prompt
- **One click, not per-segment** — the operator clicks "Generate missing media" once; the LLM plans, the system executes

## Generator logic

**Available generators (config-driven, from `config/models.yaml`):**

| Generator | Provider | Best for | Config key |
|-----------|----------|---------|------------|
| AI video | xAI Grok Imagine | Conceptual, abstract, stylized clips | `media.video_default` |
| Stock video | Pexels + Pixabay | Real-world footage, people, locations | `stock.providers` |
| Static images | Gemini 3.1 Flash (OpenRouter) | Cover frames, data cards, text overlays | `media.image_default` |
| Voice/narration | Qwen3 TTS | VO from script | `voice_cloning.engine` |
| Assembly | FFmpeg | Stitch segments + burn captions | (local) |

**No Blender needed.** Blender is a 3D animation/compositing tool — wrong fit:
- We need real-looking B-roll + style-consistent AI clips, not 3D animation
- Blender requires GPU compute and significant render time
- Island bandwidth makes large tool downloads impractical
- FFmpeg already handles compositing (captions, transitions, audio mixing)

The LLM chooses which generator to use per segment and writes prompts that maintain visual consistency across all generated/downloaded clips.

## Implementation plan

### 1. New prompt: `prompts/assembly/media_plan_v1.md`
LLM prompt that takes script + visual style + missing captures + available generators → produces a media generation plan (JSON).

### 2. New endpoint: `POST /api/assets/<id>/generate-media`
- Calls LLM with the media plan prompt
- Executes the plan: for each segment, calls the chosen generator with the LLM-written prompt
- Registers all generated/downloaded clips as `generated:` or `stock:` ingredients
- Returns the completed ingredient list

### 3. Assembler UI
- Replace per-capture buttons with a single "Generate missing media" button
- Shows progress as each segment is generated
- After all media is ready, the "Generate video" button works normally (edit plan sees real ingredients)

### 4. Edit plan prompt update
- `edit_plan_v1.md` receives the completed media plan ingredients
- The LLM sees real ingredients and produces an edit plan that uses them consistently

## Charter compliance

- **LLM does judgment**: The LLM is the creative director — it decides generator choice, writes style-consistent prompts, maintains visual coherence
- **Config-driven**: Generator providers stay in `config/models.yaml`
- **Mechanics use boring libraries**: FFmpeg for assembly, HTTP clients for API calls
- **Per-piece approval**: Operator clicks "Generate missing media" — no auto-generation without consent
- **No business values in code**: All prompts, queries, style directives are LLM-produced from the script + Visual Style module