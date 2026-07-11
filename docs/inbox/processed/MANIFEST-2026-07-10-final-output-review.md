# MANIFEST — 2026-07-10 Final Output Review Layer + Audio Bed Fix

**Date:** 2026-07-10
**Architect:** vf-architect
**Batch:** Final output review layer + audio bed fix for the assembly path

## Files

| File | Destination | Action |
|---|---|---|
| `CORRECTION-final-output-review-and-audio-fix-v1.0.md` | `docs/reviews/` | ADD |
| `MANIFEST-2026-07-10-final-output-review.md` | `docs/inbox/processed/` | (this manifest — moved after filing) |

## Context

The operator has been working with the builder on generating a proper video for asset 2 (draft 3). The builder made improvements (video generation now works end-to-end after the VH fixes), but two problems remain:

1. **Audio loops nonsensically** — the renderer's post-concat audio bed takes the first video clip's ambient audio and loops it to fill the entire output duration. The operator hears the same 6-second ambient sound repeated 3 times across an 18-second video. Root cause: `src/assembly.py` lines 454–518 apply a heuristic audio bed that ignores the edit plan's `audio` block.

2. **No final-output review layer** — the renderer produces output and marks it "done" with no AI checking that the output is coherent. The operator wants a "human AI" layer that inspects the final video/images before they're marked complete — similar to how the Writer has a T9.5 AI review loop, and similar to the UI review methodology the architect uses.

## Notes

1. **AUDIO-1 is the immediate fix.** The audio bed heuristic in `assembly.py` lines 454–518 should be removed and replaced with audio-block-driven mixing. This is a charter violation (judgment in code — the code decides to loop audio without the LLM's direction). The edit plan already has an `audio` block with `original_audio`, `music`, and `vo` fields — the renderer just doesn't read it.

2. **The asset review loop mirrors T9.5.** The Writer chain has: draft → self-audit → alignment check → revise → re-check → draft_ready. The assembler chain should have: render → mechanical checks → visual inspection → audio inspection → content alignment → review summary displayed to operator. The operator is still the final gate — the AI review is advisory.

3. **Vision model is needed.** The visual inspection step requires a vision-capable LLM. The system already uses OpenRouter for image generation — a model like `google/gemini-3.1-flash` can examine extracted keyframes. This is config-driven in `models.yaml` under a new `asset_review` block.

4. **Audio inspection uses existing infrastructure.** faster-whisper is already configured in `models.yaml` for transcription. The audio review step extracts the audio track, transcribes it, and checks for looping/incoherence. This catches the exact bug the operator is seeing.

5. **The review is advisory, not blocking.** It runs async after render completes. The operator sees the video AND the AI review summary. The operator can approve, fix, or kill regardless of the AI verdict. This matches "AI proposes, human gates."

6. **ASSET-REVIEW-6 extends the pattern to images.** Each generated image gets a lightweight vision check: does the image match the prompt that generated it? This catches "AI generated the wrong thing" before the operator sees it.

## Implementation Priority

1. **AUDIO-1 + AUDIO-2** — fix the audio bed (P0, immediate)
2. **ASSET-REVIEW-1** — mechanical post-render checks (P0, no LLM needed)
3. **ASSET-REVIEW-2** — vision-based visual inspection (P0, requires vision model config)
4. **ASSET-REVIEW-5** — UI integration (P0, operator needs to see the review)
5. **ASSET-REVIEW-3** — audio inspection via whisper (P1)
6. **ASSET-REVIEW-4** — content alignment aggregation (P1)
7. **ASSET-REVIEW-6** — image review (P1)

## APPLY

- After filing, update `docs/PROGRESS.md` with the correction tag `correction-final-output-review-2026-07-10`
- Log CHANGELOG entry for this batch (type: FIX for audio, STRUCTURE for review layer)
- The builder should implement AUDIO-1 first — it's a focused fix to `src/assembly.py` that stops the looping audio immediately