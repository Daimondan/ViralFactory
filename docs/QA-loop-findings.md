# ViralFactory Full-Pipeline Operator Evaluation — Findings

Loop: `docs/loop-full-pipeline-evaluation.md` (adapted from ForwardFuture loop #010)

Each pass drives the staged pipeline end-to-end through the operator UI, produces one Reel video, sends Daimon a Drive link to inspect, and logs every issue here. Fixed entries get a commit ref.

---

## Pass 1 — (in progress)

Start: 2026-07-19

### F-001 — BLOCKER — Autonomous assembler produces no visuals when capture_required is empty
- **Surface:** `/api/draft/<id>/gate` (action=ship) → `produce_chain.run_assembler_chain` → `_step_media_plan` → `MediaPlanningService.generate_for_asset`
- **Reproduction:** Approve a Reel idea card whose treatment has `capture_required=[]`. Ship the draft. Assembler chain runs, VO generates, but `generated_images` stays `[]`. `_step_edit_plan` fails: "No usable visual media is available. Generate missing media or upload a capture before creating an edit plan." Card ends in `assembly_failed`.
- **Expected:** When `capture_required` is empty, the media step should still generate AI visuals from the asset's `image_prompts` (the same path the UI's "Generate visuals" button uses at `/api/assets/<id>/generate-images`), so the edit plan has render-ready ingredients.
- **Actual:** `MediaPlanningService.generate_for_asset` short-circuits with `{"status":"ok","message":"No missing captures — all fulfilled"}` and never calls image generation. `_step_media_exec` sees `results=[]` and `ready_to_render` unset → passes silently. Then edit_planning sees zero render-ready visuals → 409.
- **Root cause:** `src/services/media_planning.py:287-296` — the `missing = capture_required[len(uploads):]` guard treats "no captures required" as "nothing to do", ignoring that Reels still need generated B-roll.
- **Fix:** (pending)