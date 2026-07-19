# ViralFactory Full-Pipeline Operator Evaluation — Findings

Loop: `docs/loop-full-pipeline-evaluation.md` (adapted from ForwardFuture loop #010)

Each pass drives the staged pipeline end-to-end through the operator UI, produces one Reel video, sends Daimon a Drive link to inspect, and logs every issue here. Fixed entries get a commit ref.

---

## Pass 1 — (in progress)

Start: 2026-07-19

### F-006 — BLOCKER — Soundtrack not auto-discovered; pipeline blocks on vo_only gate
- **Surface:** `produce_chain._step_soundtrack_gate` → `awaiting_soundtrack_approval` / `RenderReviewService` soundtrack gate
- **Reproduction:** Card 49 reached the soundtrack gate with a `vo_only` plan. The pipeline blocked on `awaiting_soundtrack_approval` and required operator approval before render. The soundtrack discovery service (DIVERGENCE-015) was never wired into the production chain — the planner defaulted to vo_only because no music candidates were provided.
- **Expected:** The pipeline auto-discovers music (Bundle.social/Instagram + Pixabay), LLM-ranks candidates (mood/fit 80%, popularity 20%), auto-mixes the top pick into the render, and shows alternatives in the review UI for optional swapping. No gate-before-mix.
- **Actual:** `soundtrack_discovery.py`, `soundtrack_ranking.py`, `soundtrack_mix.py` did not exist. The soundtrack planner received no candidates and produced `vo_only`. The autonomous chain blocked at `awaiting_soundtrack_approval`.
- **Fix:** Built all three modules (VF-VS-510..515). Wired discovery → ranking → auto-mix into `edit_planning.py` before the soundtrack plan. Removed `awaiting_soundtrack_approval` blocking from `produce_chain.py`. `RenderReviewService` skips the gate when `soundtrack_ranking` is present on the plan. Added alternatives box to `assets.html` with preview links and switch buttons. Config block in `models.yaml`. 11 tests in `test_soundtrack_discovery.py`. Commit: `VF-VS-510..515`.

### F-001 — BLOCKER — Autonomous assembler produces no visuals when capture_required is empty
- **Surface:** `/api/draft/<id>/gate` (action=ship) → `produce_chain.run_assembler_chain` → `_step_media_plan` → `MediaPlanningService.generate_for_asset`
- **Reproduction:** Approve a Reel idea card whose treatment has `capture_required=[]`. Ship the draft. Assembler chain runs, VO generates, but `generated_images` stays `[]`. `_step_edit_plan` fails: "No usable visual media is available. Generate missing media or upload a capture before creating an edit plan." Card ends in `assembly_failed`.
- **Expected:** When `capture_required` is empty, the media step should still generate AI visuals from the asset's `image_prompts` (the same path the UI's "Generate visuals" button uses at `/api/assets/<id>/generate-images`), so the edit plan has render-ready ingredients.
- **Actual:** `MediaPlanningService.generate_for_asset` short-circuits with `{"status":"ok","message":"No missing captures — all fulfilled"}` and never calls image generation. `_step_media_exec` sees `results=[]` and `ready_to_render` unset → passes silently. Then edit_planning sees zero render-ready visuals → 409.
- **Root cause:** `src/services/media_planning.py:287-296` — the `missing = capture_required[len(uploads):]` guard treats "no captures required" as "nothing to do", ignoring that Reels still need generated B-roll.
- **Fix:** `src/services/media_planning.py` — when `capture_required` is empty/fulfilled but the asset has more `image_prompts` than `generated_images`, proceed to the LLM media-plan path and surface the Writer image_prompts as the media to generate (one AI image per beat). Commit `b2f5438`. Test: `tests/test_qa_loop_media_shortcircuit.py` (RED→GREEN). 112 existing tests still pass.

### F-002 — MINOR — Stale production_error persists after successful retry
- **Surface:** `idea_cards.production_error` column / `/api/ideas/<id>/retry-production`
- **Reproduction:** Card 49 failed at edit_plan (F-001). After retry succeeded and the card advanced to `awaiting_soundtrack_approval`, the `production_error` column still held the old `{"step":"edit_plan","error":"No usable visual media..."}` JSON.
- **Expected:** A successful retry (or any state advance past the failed step) should clear `production_error` so the UI doesn't show a stale error on a healthy card.
- **Actual:** `production_error` retains the failure record until overwritten by a new failure.
- **Fix:** `src/pipeline.py:update_card_state` — the `else` branch (normal state advance, no production_error arg) now sets `production_error = NULL`. Any successful transition clears the error. Test: `tests/test_qa_loop_minor_fixes.py::test_F002_*`. Commit (pending).

### F-003 — MINOR — Soundtrack decision API field name mismatch
- **Surface:** `/api/assets/<id>/soundtrack-decision`
- **Reproduction:** The endpoint reads `body.get("action")` but a natural operator/test call uses `"decision"`. Calling with `{"decision":"approved"}` returns `{"error":"Unsupported soundtrack decision"}` with no hint about the correct field.
- **Expected:** Either accept both `action` and `decision`, or return a clear error naming the expected field.
- **Actual:** Silent rejection — the operator sees an unhelpful error.
- **Fix:** `src/app.py:soundtrack_decision` — now reads `body.get("action") or body.get("decision")`. Test: `tests/test_qa_loop_minor_fixes.py::test_F003_*`. Commit (pending).

### F-004 — MINOR — /ideas page has no gate-stat summary cards
- **Surface:** `/ideas`
- **Reproduction:** The home page (`/`) shows Gate 1/2/3 stat cards with counts. The `/ideas` Pipeline page (where the operator actually works) shows only the nav-count badge and the card list — no at-a-glance gate summary.
- **Expected:** The page the operator lives on should surface the same gate counts as home, so they don't have to bounce back to see what's waiting.
- **Fix:** `src/app.py:ideas_queue` computes `gate_counts` (same logic as home) and passes to template; `ideas.html` renders the same `gate-stats` / `gate-stat-card` HTML. Tests: `tests/test_qa_loop_minor_fixes.py::test_F004_*`. Commit (pending).

### F-005 — BLOCKER — Final render is cut off at the end; last 2.5s of VO lost
- **Surface:** `/api/assets/<id>/render` → `src/assembly.py` xfade concat + `_mix_vo`
- **Reproduction:** Asset 11 (Card 49) rendered `final_1.mp4` at 36.9s. The approved VO is 39.4s. The last beat ("Next time you open ChatGPT, don't ask for an answer. Ask for a fight.") is truncated. ffprobe confirms 36.9s video + audio. Mechanical review flagged: "Duration mismatch: output is 36.9s, plan target is 39.4s (diff: 2.5s)."
- **Expected:** The final render duration must equal the VO (master timeline). No VO audio may be cut off.
- **Actual:** Two compounding bugs:
  1. `src/assembly.py:469` — `has_transitions = any(t in ("crossfade", "slide", "whip") for t in transition_types)` triggers the xfade path when ANY segment has a non-cut transition. The xfade path then applies `xfade_map.get(trans_type, "fade")` to ALL transitions, including "cut" ones — defaulting them to 0.5s fade. With 6 segments (5 transitions: 4 cuts + 1 crossfade), that's 5 × 0.5s = 2.5s eaten from the timeline: 39.4s → 36.9s.
  2. `src/assembly.py:1258` — `_mix_vo` trims the VO to the (already too-short) video duration: `[1:a]atrim=0:{duration}`. The last 2.5s of VO (the CTA) is silently discarded.
- **Fix:** `src/assembly.py:469-523` — cut transitions now use 0.001s xfade (negligible, ~5ms total) instead of 0.5s fade; only crossfade/slide/whip consume 0.5s. `src/assembly.py:_mix_vo` — VO is no longer trimmed to video duration; the video is extended via `tpad` to cover the full VO (master timeline). Added `_get_video_duration()` because `_get_duration()` reads the container duration (includes audio), which masked the xfade video stream being shorter than audio. Tests: `tests/test_qa_loop_render_cutoff.py` (2 RED→GREEN with real ffmpeg). Commits: `QA-loop F-005` + `F-005 (follow-up)`. **Re-render verified:** final_4.mp4 is 39.4s video + 39.4s audio (matches VO exactly), last CTA beat present and audible, frame at 38s extracts successfully.