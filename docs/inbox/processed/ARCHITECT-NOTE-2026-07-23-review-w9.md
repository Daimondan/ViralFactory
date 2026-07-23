# ARCHITECT-NOTE-2026-07-23-review-w9.md

**From:** Architect (vf-architect profile)
**To:** Builder (viralfactory profile)
**Date:** 2026-07-23
**Subject:** Review-w9 findings — M15 route wiring P0 fixes required before M15 is genuinely complete

## Read first

1. `docs/reviews/review-w9-2026-07-23.md` — the full review (all findings, dimensions, verdicts)
2. `docs/CHARTER-v3.10.md` — current charter (your constitution)
3. `BUILD_PLAN.md` — your task list (M15 tasks are all checked, but the P0 fixes below must be done)

## Summary

M15 service layer is APPROVED — 14 service files are architecturally sound, charter-compliant, 351 tests pass. But the M15-D composition surfaces are NOT wired into the Flask routes, and the Component Workbench + Composition Ratification are orphaned from navigation. The builder must apply P0 fixes before M15 is genuinely complete.

DIVERGENCE-020 (operator visual engagement) was implemented without architect ratification and uses the same number as the already-ratified composition plan divergence. It is APPROVED WITH CONDITIONS (renumber to DIVERGENCE-021, move hardcoded values to config).

## P0 — Blocking (do these first, in order)

### P0-1: Wire composition route to CompositionPlanGenerator + PreviewGenerator

**File:** `src/app.py` — `composition_ratification` route (~line 9771)

**Problem:** The route builds an empty inline plan:
```python
plan = {
    "schema_version": "1.0",
    "manifest_hash": manifest_data.get("manifest_hash", ""),
    "canvas": {"width": 1080, "height": 1920, "fps": 30.0, "aspect_ratio": "9:16"},
    "text_elements": [],
    "audio_elements": [],
    "visual_elements": [],
    "graphics_elements": [],
    "transitions": [],
}
```

It does NOT import or call `CompositionPlanGenerator` (built in VF-CP-001) or `CompositionPreviewGenerator` (built in VF-CP-002). The operator sees no plan elements, no previews — just a status badge and a hash.

**Fix:**
- Import `CompositionPlanGenerator` from `src/services/composition_plan.py`
- Call `generator.generate(manifest, writer_contract, cue_timeline, ...)` to produce a real plan with text/audio/visual/graphics/transition elements
- Import and call the preview generator to produce per-element previews
- Pass the real plan + previews to the template
- Canvas dimensions must come from the format/config, NOT hardcoded 1080×1920/30fps

### P0-2: Add navigation links to Component Workbench and Composition Ratification

**Problem:** No page in the UI links to `/workbench/<asset_id>` or `/composition/<asset_id>`. Verified: 0 links on asset page, assemble page, home page, ideas page.

**Fix:**
- Asset page (`/create/assets/<id>`): add a "Component Workbench" button/link that appears for assets in pre-Gate-3 states
- Workbench page: add a "Composition Plan" link that appears after manifest freeze (links to `/composition/<asset_id>`)
- Assemble page (`/assemble`): add a workbench link per asset card
- Composition page: ensure "Back to Workbench" link works correctly

### P0-3: Fix workbench back-link (wrong asset ID)

**File:** `src/app.py` — workbench route template render

**Problem:** The workbench for asset 22 shows `← Back to asset 22 (Instagram)` but the href is `/create/assets/26` — it uses `draft_id` instead of `asset_id`.

**Fix:** Change the back link to use `asset_id`, not `draft_id`. The URL should be `/create/assets/{asset_id}`.

### P0-4: Move MAX_CLIP_DURATION and max_segment_seconds to config

**Files:** `src/services/edit_planning.py:1347` and `:249-254`

**Problem:** Two charter violations:
1. `MAX_CLIP_DURATION = 4.0` hardcoded Python constant (line 1347) — charter rule: "values → config"
2. `max_segment_seconds` variant-type mapping uses string matching on `variant_type` (lines 249-254) — charter rule: "no judgment in code"

**Fix:**
- Add `max_segment_seconds` to `config/render_styles.yaml` (with per-format overrides if needed)
- The validator reads from config, not a Python constant
- The variant-type → pacing mapping should come from config or the Format Guide, not an if/elif chain with string matching

### P0-5: Renumber DIVERGENCE-020 (operator visual engagement) to DIVERGENCE-021

**Files:**
- `docs/decisions/DIVERGENCE-020-operator-visual-engagement-criteria.md` → rename to `DIVERGENCE-021-operator-visual-engagement-criteria.md`
- `CHANGELOG.md` — update the "DIVERGENCE-020 — Operator visual engagement criteria" entry to "DIVERGENCE-021"
- `docs/PROGRESS.md` — update the review-w9 entry reference
- `src/services/edit_planning.py:1362` — update the comment from `(DIVERGENCE-020)` to `(DIVERGENCE-021)`

**Context:** The architect filed `DIVERGENCE-020-two-phase-composition-plan-and-ratification.md` first (at 02:58 UTC, ratified as AMENDMENT-014). The builder/operator filed `DIVERGENCE-020-operator-visual-engagement-criteria.md` later (at 14:01 UTC) using the same number. AMENDMENT-014's "Ratifies: DIVERGENCE-020" correctly refers to the composition plan divergence (filed first). The operator visual engagement divergence must take the next number: DIVERGENCE-021.

**DIVERGENCE-021 is APPROVED WITH CONDITIONS:**
1. Move MAX_CLIP_DURATION to config (P0-4 above)
2. Move max_segment_seconds variant-type mapping to config (P0-4 above)
3. Prompt-level directives only — confirm no Python heuristics were added for caption emphasis, supporting visuals, VO-only visual life, video-over-stills, motion vocabulary, or scene coherence
4. Renumber from DIVERGENCE-020 (this task)

## P1 — Should fix (after P0)

### P1-1: Fix state dissonance on workbench
- Session badge shows "Planning components…" when all components are approved — badge should reflect actual state
- "Generate Component Requirements" button appears when requirements already exist — hide it

### P1-2: Fix false green on workbench
- "✅ All required components approved. Ready to freeze." shows when session is in `planning_components` state
- Freeze button is enabled when session state doesn't allow it
- Readiness summary and button state must match the session's actual state

### P1-3: Fix stale plan Ratify button
- Composition page shows "Stale" warning but Ratify button is enabled
- Disable Ratify when plan is stale; require re-review first

### P1-4: Remove raw file paths from workbench UI
- Replace `📎 data/media/22/vo_take_1784808293.wav` with human-readable labels ("Voice recording — 32 seconds")
- Replace `📎 data/media/22/image_e996ded6178f85c8.png` with ("Generated image — beat 1")

### P1-5: Remove raw JSON dict from asset page
- Writer beats are rendered as raw Python dict repr: `{'label': 'HOOK', 'vo_text': '...', ...}`
- Format as readable cards, not dict dump

## P2 — Fix when convenient

- P2-1: Composition page — short hash display (first 8 chars + tooltip), relative time, "ratified" not "ratify at"
- P2-2: Asset page — ISO timestamp in source citation → relative/friendly format
- P2-3: Workbench/composition page titles — include idea title and platform
- P2-4: Candidate version — make visible badge, not tiny grey text
- P2-5: Composition empty state — "No frozen manifest" should be a proper page with navigation, not bare 400 string

## What was NOT changed by the architect

No `src/*.py` files were modified. No config files were modified. No templates were modified. Only markdown documentation files were changed:
- `docs/reviews/review-w9-2026-07-23.md` (new)
- `docs/reviews/.last-reviewed-commit` (updated)
- `docs/PROGRESS.md` (updated)
- `CHANGELOG.md` (updated)
- `docs/CONTEXT.md` (updated)
- `README.md` (updated)

## Verification

351 M15 + DIVERGENCE-020 tests pass (126.10s). Full 2459-test suite was not run (exceeds foreground timeout on this VPS). Builder should run the full suite after applying P0 fixes.