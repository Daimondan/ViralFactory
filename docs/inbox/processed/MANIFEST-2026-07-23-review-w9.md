# MANIFEST — 2026-07-23 — Review-w9 M15 corrections

**Batch:** review-w9
**Architect files (do not move until consumed):**

## APPLY order

1. Read `docs/reviews/review-w9-2026-07-23.md` — the full review
2. Read `docs/inbox/ARCHITECT-NOTE-2026-07-23-review-w9.md` — this note with actionable P0/P1/P2 tasks
3. Read `docs/CHARTER-v3.10.md` — current charter (constitution)
4. Read `BUILD_PLAN.md` — M15 tasks (all checked, but P0 fixes below must complete before M15 is genuinely done)

## Files created by architect

| File | Purpose |
|---|---|
| `docs/reviews/review-w9-2026-07-23.md` | Full review — all findings, 10-dimension UI walkthrough, charter violations, doc defects |
| `docs/inbox/ARCHITECT-NOTE-2026-07-23-review-w9.md` | Builder handoff note with P0/P1/P2 task list |
| `docs/inbox/MANIFEST-2026-07-23-review-w9.md` | This file |
| `docs/PROGRESS.md` | Updated: "Current Phase" v3.9→v3.10, M15 status ⬜→🔧, review-w9 entry |
| `CHANGELOG.md` | Updated: REVIEW-w9 entry |
| `docs/CONTEXT.md` | Updated: diagram note v3.9→v3.10, binding flow includes composition plan + ratification |
| `README.md` | Updated: repo map adds AMENDMENT-014, DIVERGENCE-020 files; status references review-w9 |
| `docs/reviews/.last-reviewed-commit` | Updated to 0f4ad57 |

## Task order for builder

```
P0-1: Wire composition route to CompositionPlanGenerator + PreviewGenerator
P0-2: Add navigation links to workbench + composition surfaces
P0-3: Fix workbench back-link (wrong asset ID)
P0-4: Move MAX_CLIP_DURATION + max_segment_seconds to config
P0-5: Renumber DIVERGENCE-020 (operator visual engagement) → DIVERGENCE-021
  → P1-1..P1-5 (state dissonance, false greens, stale ratify, raw paths, raw JSON)
  → P2-1..P2-5 (jargon, timestamps, titles, version badges, empty state)
```

## Expected proof

- Composition route produces a real plan with text/audio/visual/graphics/transition elements (not empty arrays)
- Per-element previews are generated and visible on the composition page
- Asset page links to Component Workbench; Workbench links to Composition after manifest freeze
- Workbench back-link goes to the correct asset
- `MAX_CLIP_DURATION` and `max_segment_seconds` read from config (no hardcoded Python constants)
- DIVERGENCE-020 numbering collision resolved (operator visual engagement = DIVERGENCE-021)
- Full automated suite passes
- Hands-on UI walkthrough confirms the operator can navigate to and use both new surfaces

## Inbox processing

After reading and applying this batch, move these files to `docs/inbox/processed/`:
- `ARCHITECT-NOTE-2026-07-23-review-w9.md`
- `MANIFEST-2026-07-23-review-w9.md`