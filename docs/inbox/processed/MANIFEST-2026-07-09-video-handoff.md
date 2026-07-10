# MANIFEST — 2026-07-09 Video Generation Handoff

**Date:** 2026-07-09
**Architect:** vf-architect
**Batch:** Video generation → assembly handoff audit

## Files

| File | Destination | Action |
|---|---|---|
| `CORRECTION-video-generation-handoff-v1.0.md` | `docs/reviews/` | ADD |
| `REVIEW-video-generation-handoff-2026-07-09.md` | (already in `docs/reviews/`) | — |

## Notes

1. **Apply the correction before any new milestone work.** The 5 P0 bugs block the entire video generation path. No AI-generated video can reach the assembler until they're fixed.

2. **Task VH-1 and VH-2 are the critical path.** VH-1 fixes the synchronous clip generator (broken key read + missing download). VH-2 fixes the media-plan-driven generator (no poll/download loop). Both must land before "Generate video" can produce usable ingredients.

3. **VH-3 (Google/Veo) may be lower priority if xAI is the primary provider.** If the operator is using xAI for video generation, the Veo bugs are not blocking. But they should still be fixed — the system is config-driven and any business could configure either provider.

4. **VH-4 (0-byte cleanup) is quick.** Delete the 3 existing 0-byte files and add the size check. 10 minutes of work.

5. **VH-6 (CONTEXT.md documentation) is important for operator expectations.** The operator needs to know that the current render produces a clip concat, not a finished social video with captions and transitions.

## APPLY

- After filing, update `docs/PROGRESS.md` with the review tag `review-video-handoff-2026-07-09` and note the 5 P0 bugs as blocking
- Update `docs/CONTEXT.md` with current render capability section (VH-6)
- Log CHANGELOG entry for this batch