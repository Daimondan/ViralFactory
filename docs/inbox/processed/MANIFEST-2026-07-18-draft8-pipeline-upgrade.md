# MANIFEST — Architect Ruling: Draft 8 Visual + Soundtrack Pipeline Upgrade

**Date:** 2026-07-18
**From:** vf-architect
**To:** Hermes builder (viralfactory profile)
**Status:** READY TO PROCESS — architect ruling complete

## What this manifest delivers

The architect has reviewed the builder's Track B proposal (`docs/plans/2026-07-18-draft-8-reel-correction-then-pipeline-upgrade.md`) against Charter v3.6, the completed Assembler Full Upgrade (VF-AU-001..603), and the live codebase. The ruling is: **APPROVED with binding conditions** — ratified as AMENDMENT-010 → Charter v3.7.

## Key finding the builder must understand

The Assembler Full Upgrade built correct services (`src/services/*.py`) that the **operator-facing route never reaches**. `src/app.py` routes (`/edit-plan`, `/render`, `/generate-media`, `/produce-reel`) bypass every new service and call the old `AssemblyRenderer` + `build_reel_plan` path directly. The autonomous chain (`produce_chain.py`) calls the new services. **Two code paths produce different outputs from the same input** — this is the root cause of the Draft 8 defects reaching the operator.

Before building any new contracts, the builder must first **wire the operator routes to the existing services** (Phase M13-A). Several of the builder's proposed Track B tasks are already designed and built but not wired.

## Files to ADD

| File | Destination | Action |
|---|---|---|
| This manifest | `docs/inbox/MANIFEST-2026-07-18-draft8-pipeline-upgrade.md` | Process, then move to `docs/inbox/processed/` |
| DIVERGENCE-014 | `docs/decisions/DIVERGENCE-014-visual-soundtrack-pipeline-and-dual-path-reconciliation.md` | ADD — already written by architect |
| AMENDMENT-010 | `docs/decisions/AMENDMENT-010-visual-soundtrack-pipeline.md` | ADD — already written by architect |
| Charter v3.7 | `docs/CHARTER-v3.7.md` | ADD — already written by architect |

## Files to REPLACE

| File | Destination | Action |
|---|---|---|
| Charter v3.6 → v3.7 | `docs/CHARTER-v3.6.md` | SUPERSEDE — add a superseded note at the top pointing to v3.7. Do not delete v3.6. |
| BUILD_PLAN.md | `BUILD_PLAN.md` | REPLACE — add M13 milestone tasks (VF-VS-101 through VF-VS-703) per the patch below |

## APPLY section (builder executes after filing)

1. **Bump charter to v3.7:** Update all references from `CHARTER-v3.6.md` to `CHARTER-v3.7.md` in `BUILD_PLAN.md`, `docs/CONTEXT.md`, `README.md`.
2. **Add M13 tasks to BUILD_PLAN.md:** The 23 tasks below (VF-VS-101 through VF-VS-703).
3. **Mark completed VF-AU tasks with a note:** VF-AU-208, VF-AU-302, VF-AU-304 are re-opened by this amendment. Their original checkboxes stay checked (the services were built) but a note is added: "Re-opened by AMENDMENT-010 — acceptance criteria met with tautological tests; see VF-VS-101..203 for the real wiring."
4. **Update docs/CONTEXT.md** to reflect: Visual Director, soundtrack plan, dual-path reconciliation, config-driven styles, phrase-level captions.

## BUILD_PLAN.md patch — M13 tasks

Add after the Assembler Full Upgrade section:

```markdown
## M13 — Visual + Soundtrack Pipeline (AMENDMENT-010, Charter v3.7)

*Read `docs/decisions/DIVERGENCE-014-*.md` and `docs/decisions/AMENDMENT-010-*.md` before starting.*

### Phase M13-A — Dual-path reconciliation

- [ ] VF-VS-101 **Wire operator routes to services:** `/api/assets/<id>/edit-plan`, `/render`, `/generate-media` call `EditPlanningService`, `RenderReviewService`, `MediaPlanningService`. Routes handle HTTP only. — AC: same input through UI route and autonomous chain produces equivalent edit plans.
- [ ] VF-VS-102 **Retire old build_reel_plan path:** Delete or gate `reel_production_runner.run_reel_production` for VO-led Reels. — AC: no operator route calls `build_reel_plan` directly.
- [ ] VF-VS-103 **Behavioral dual-path test:** Render same input through both paths, assert equivalence. — AC: test fails if routes diverge from chain.

### Phase M13-B — Config-driven styles

- [ ] VF-VS-201 **Move overlay styles to config:** `config/render_styles.yaml` + Visual Style module overrides. `_resolve_overlay_style` checks config → module → fallback. — AC: two tenant configs, different resolved styles, zero Python edits.
- [ ] VF-VS-202 **Move SFX presets to config:** Same path for `_SFX_PRESETS`. — AC: two tenant configs, different SFX, zero Python edits.
- [ ] VF-VS-203 **Replace tautological tests:** Delete `test_vf_au_302_304_config_style.py` structural tests. Write behavioral tests that load two configs and assert different resolved parameters. — AC: tests actually render two configs and assert difference.

### Phase M13-C — Caption timing

- [ ] VF-VS-301 **Extract caption timing service:** `src/services/caption_timing.py` with `chunk_captions()`. Reuse `episode_plan._chunk_vo_text` logic. — AC: 3–6 word phrases, no dangling fragments, exact-text reconstruction.
- [ ] VF-VS-302 **Wire cue compiler to caption timing:** The cue compiler chunks captions via the new service. — AC: cue compiler produces multiple caption cues per beat, not one full-beat caption.
- [ ] VF-VS-303 **Update episode_plan to import shared service:** No duplication. — AC: `episode_plan._chunk_vo_text` delegates to `caption_timing.py`.

### Phase M13-D — Semantic visual events

- [ ] VF-VS-401 **Add visual_events to production contract:** `PRODUCTION_CONTRACT_V2` beat schema gains `visual_events[]`. Compatibility: no events → one event from `visual_intent`. — AC: contract validates multi-event beats; old contracts degrade gracefully.
- [ ] VF-VS-402 **Visual Director process:** `prompts/assembly/visual_director_v1.md` + JSON schema + validator. Translates `visual_intent` + VO timings → `visual_events[]`. Registered in Process Registry with `playbook_type: production`. — AC: schema-validated, provenance-logged, no audience copy, no tenant strings.
- [ ] VF-VS-403 **Extend feasibility checks:** Multi-event coverage validation. Missing event coverage → block. Talking-head intent + shorter motion than speech → block or require explicit cutaway. — AC: Draft 8 Artifact A's 5s-motion + still fallback is caught and blocked.

### Phase M13-E — Soundtrack plan

- [ ] VF-VS-501 **Soundtrack plan contract:** `src/soundtrack_plan.py` with the schema in AMENDMENT-010 Condition 4. Parallel contract referenced by `contract_id`. — AC: `vo_only` requires rationale + approval; `music_bed` requires licence + cost; validation rejects silent VO-only.
- [ ] VF-VS-502 **Soundtrack planning prompt:** `prompts/assembly/soundtrack_plan_v1.md`. LLM proposes mode + emotional register. Python validates. — AC: no genre inference in code; no random effects; provenance logged.
- [ ] VF-VS-503 **Soundtrack preview gate:** Operator hears bed + SFX separately and under VO. Approves, rejects, replaces, or explicitly approves VO-only. — AC: no soundtrack mode change without gate token; synthetic tones not presented as finished design.
- [ ] VF-VS-504 **Soundtrack mix review:** Extends `RenderReviewService`. Expected vs rendered music/SFX, audibility windows, VO-to-bed level, clipping, silence. — AC: missing approved music/SFX fails; unapproved VO-only yields `needs_operator_decision`.

### Phase M13-F — False-green fixes

- [ ] VF-VS-601 **Skipped evidence blocks readiness:** `asset_review.py` — `skipped` → `needs_operator_decision`, never `ready_for_operator`. — AC: skipped visual/transcript creates saved row and blocks readiness.
- [ ] VF-VS-602 **Beat-aware visual inspection:** First/middle/last frame per beat, frames before/after cuts. Replace 5 generic keyframes. — AC: review frame selection derives from plan timing.
- [ ] VF-VS-603 **Deterministic text-integrity check:** Forbidden debug tokens (`{`, `}`, `position`, `style`, `prompt`, JSON/dict fragments), safe-zone bounds, caption reconstruction, overlap/collision. — AC: Artifact A's leaked dict text and clipped captions fail in a regression fixture.
- [ ] VF-VS-604 **Transition intent in cue compiler:** Honor `transition_in` from the Writer. Budget crossfade overlap against VO clock. Unsupported → visible warning or hard failure. — AC: hard cuts, crossfades, holds have explicit jobs; no silent `cut` override.

### Phase M13-G — Regression and proof

- [ ] VF-VS-701 **Artifact A regression fixtures:** Tests that prove detection of: dict metadata as audience text, long unwrapped captions, missing `bottom-third`, still fallback after motion, skipped evidence false-green, missing capture provenance. — AC: all defect classes caught.
- [ ] VF-VS-702 **Real fresh Reel through upgraded path:** One new real Reel through the service-based path. Complete evidence. Operator review. — AC: working artifact, complete evidence, operator approval, no false-green.
- [ ] VF-VS-703 **Full suite + verification:** `pytest -q` green. FFprobe/EBU R128/transcript/OCR/beat-frame on real artifact. Live server smoke test. — AC: tests + real artifact evidence pass.
```

## Implementation order

M13-A first (dual-path reconciliation) — this is the foundation. Without it, every subsequent task has two code paths to fix. Then M13-B (config styles), M13-C (captions), M13-F (false-green fixes) — these close the confirmed Draft 8 defects. Then M13-D (visual events) and M13-E (soundtrack) — the genuinely new contracts. Finally M13-G (regression + proof).

## What existing tasks are reused, replaced, or superseded

- **Reused:** VF-AU-101..207 (all services), VF-AU-301 (Format Guide), VF-AU-303 (reference assets), VF-AU-401..404 (feasibility + compliance + remediation + UI), VF-AU-501..503 (performance/learning), VF-AU-601 (integration suite).
- **Re-opened:** VF-AU-208 (dual-path wiring — tautological test), VF-AU-302 (config styles — tautological test), VF-AU-304 (config SFX — tautological test), VF-AU-205 (cue compiler captions — full-beat not phrase-level), VF-AU-402 (blocking compliance — skipped evidence still passes).
- **Superseded:** None. The new tasks extend, not replace.
- **New:** VF-VS-401..403 (visual events + Visual Director), VF-VS-501..504 (soundtrack plan).

## The approved Reel is regression evidence, not a template

`data/media/6/final_2.mp4` (hash `f94c4ad4…aa172a`) is the regression reference. No StackPenni scene values, text, or visual treatments from it enter generic code. The regression fixtures (VF-VS-701) test defect *classes* (dict metadata, full-beat captions, still fallback, false greens), not the specific StackPenni content.