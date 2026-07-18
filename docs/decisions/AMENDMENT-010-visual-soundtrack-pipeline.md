# AMENDMENT-010 — Visual + soundtrack pipeline and dual-path reconciliation

**Filed:** 2026-07-18
**Filed by:** Architect (vf-architect)
**Status:** APPROVED — ratifies DIVERGENCE-014, incorporates into Charter v3.7
**Ratifies:** `docs/decisions/DIVERGENCE-014-visual-soundtrack-pipeline-and-dual-path-reconciliation.md`
**Related:** AMENDMENT-008 (compliance loop), AMENDMENT-009 (production-contract boundaries)

## What this amends

DIVERGENCE-014 identifies that the Assembler Full Upgrade (VF-AU-001..603) built correct services that the operator-facing route never reaches, that several acceptance criteria were met with tautological tests, and that two genuinely new contracts are needed: semantic visual events and the soundtrack plan. This amendment ratifies the divergence and sets binding conditions for the M13 milestone.

## Architect's findings (from DIVERGENCE-014)

1. **Dual-path gap:** `src/app.py` operator routes (`/api/assets/<id>/edit-plan`, `/render`, `/generate-media`, `/produce-reel`) bypass every new service. The autonomous chain (`produce_chain.py`) calls them. VF-AU-208 is marked complete but its acceptance criterion ("UI route and chain call same service") is not met — the tests are AST structural checks, not behavioral wiring tests.

2. **Tautological config tests:** VF-AU-302 and VF-AU-304 tests verify that `_OVERLAY_STYLES` and `models_config` exist in source, not that config actually overrides hardcoded styles. `_OVERLAY_STYLES` and `_SFX_PRESETS` are still the only resolution path in `assembly.py`.

3. **No phrase-level captions in the cue compiler:** The cue compiler creates one caption per beat (full VO span). The only phrase chunking is in `episode_plan.py`, unreachable from the generic reel path. This reproduces the Draft 8 defect.

4. **No soundtrack plan:** No `mode`, no `music_bed_ref`, no ducking, no `vo_only_approved` evidence. The system can silently produce VO-only Reels.

5. **No semantic visual events:** The contract has one `visual_intent` per beat. Multi-event beats (like Draft 8's 14-second BUILD with 5 events) cannot be represented.

6. **Forced `transition_in: "cut"`** in the old `build_reel_plan` path.

## Conditions (binding)

### Condition 1 — The operator-facing route must use the same services as the autonomous chain

The manual routes in `src/app.py` (`/edit-plan`, `/render`, `/generate-media`, `/produce-reel`) must call `MediaPlanningService`, `EditPlanningService`, `CueCompiler`, `RenderReviewService`, and `MediaInventoryService` — the same services `produce_chain.py` calls. The old `build_reel_plan` path in `reel_production.py` and `reel_production_runner.py` is retired for VO-led Reels. Routes handle HTTP state only; business logic lives in services.

**Rationale:** VF-AU-208's acceptance criterion is "UI route and chain call same service." The builder marked it complete with tests that don't verify this. Two code paths producing different outputs from the same input is the root cause of the Draft 8 defects reaching the operator.

**Implementation:** Extract the inline business logic from `app.py` routes into the existing services. The routes become thin HTTP handlers: parse request → call service → return JSON. Delete or gate the old `build_reel_plan` path. **The acceptance test must render the same input through both the UI route and the autonomous chain and assert byte-identical edit plans** (or contract-equivalent if timestamps differ).

### Condition 2 — Overlay styles and SFX presets must actually move to config

`_OVERLAY_STYLES` and `_SFX_PRESETS` in `assembly.py` are replaced by config/module-driven resolution. The renderer reads styles from the Visual Style module (tenant markdown) with a config fallback. Two different tenant configs must produce different render parameters with zero Python edits — verified by a test that actually loads two configs and asserts different resolved styles, not a source-inspection test.

**Rationale:** VF-AU-302's acceptance criterion is "two tenant fixtures render different styles with zero Python edits." The current test does not verify this. Hardcoded styles are a charter violation ("no business values in code") when they carry brand-specific colors/fonts.

**Implementation:** Move `_OVERLAY_STYLES` to `config/render_styles.yaml` (generic defaults) and the Visual Style module (tenant overrides). Move `_SFX_PRESETS` to `config/render_styles.yaml`. The renderer's `_resolve_overlay_style` and `_resolve_sfx_preset` check config → module → safe fallback. **No brand colors, fonts, or SFX types in Python.**

### Condition 3 — The cue compiler must do phrase-level caption chunking

The cue compiler chunks caption text into 3–6 word phrases, timed proportionally within the beat's VO span (or by word timestamps when available). The chunking logic is extracted from `episode_plan._chunk_vo_text` to `src/services/caption_timing.py` (shared service). The cue compiler calls it. Exact-text reconstruction is verified: joining chunks after punctuation normalization equals the approved VO text.

**Rationale:** Full-beat captions are a confirmed Draft 8 defect (ledger §7 cause #2, §8 quality bar). The cue compiler was supposed to fix this but reproduces the defect.

**Implementation:** `src/services/caption_timing.py` with `chunk_captions(vo_text, duration, word_timestamps=None) -> list[CaptionPhrase]`. The cue compiler calls it. `episode_plan.py` imports it instead of duplicating. Word-timestamp alignment is deferred (T2.6-T2.8); proportional timing is labeled `approximate: true` in the cue metadata.

### Condition 4 — A soundtrack_plan contract is added

The production contract gains a `soundtrack_plan` reference. The plan is a parallel contract:

```
{
  "contract_id": "...",
  "mode": "vo_only" | "music_bed" | "source_sound" | "vo_plus_bed",
  "music_bed_ref": { "source_id": "...", "licence": {...}, "cost_usd": 0 } | null,
  "ducking": { "attenuation_db": -12, "envelope": [...] } | null,
  "sfx_cues": [{ "event_id": "...", "source": "...", "timestamp": 0, "gain": 0, "purpose": "..." }],
  "vo_only_rationale": "..." | null,
  "operator_approval": null  // gate token, null until approved
}
```

- `vo_only` requires a `vo_only_rationale` and explicit operator approval. Silent VO-only is not valid.
- `music_bed` / `vo_plus_bed` requires `music_bed_ref` with licence provenance and a fresh operator-approved cost estimate.
- The LLM proposes the soundtrack mode and emotional register (prompt + schema). Python validates references, timing, licence, gain bounds, and timeline coverage. **Generic code must not infer genre or add random effects.**
- A soundtrack preview gate: the operator hears the proposed bed and representative SFX separately and under the VO before approval. VO-only delivery is explicitly approved, not defaulted.
- Synthetic placeholder tones are mechanics, not finished sound design. They may not be presented as SFX without operator approval.

**Rationale:** The operator identified that v3 is VO-only with no explicit mode. The system must make soundtrack intent explicit rather than silently omitting it.

### Condition 5 — Semantic visual events are added to the production contract

The beat in `PRODUCTION_CONTRACT_V2` gains `visual_events[]`:

```
{
  "event_id": "ev_b01_1",
  "time_range": { "start": 0.0, "end": 4.5 },
  "narrative_function": "hook_contrast" | "context" | "proof" | "explanation" | "reframe" | "action" | "landing" | "relationship" | "conflict",
  "source_policy": "operator_capture" | "licensed_stock" | "approved_reference" | "generated_still" | "generated_motion" | "renderer_graphic",
  "required_text": "..." | null,
  "capture_policy_ref": "..." | null
}
```

A beat carries one `visual_intent` (the semantic meaning) and zero-or-more `visual_events` (concrete visual jobs within the beat's time range). Existing contracts with no `visual_events` degrade to one event per beat (the beat's `visual_intent`). A **Visual Director** LLM step (new production process, registered in the Process Registry) translates `visual_intent` + measured VO timings into `visual_events[]`. The Visual Director is an Assembler-side process — it produces production planning, not audience copy (same boundary as the Media Planner per AMENDMENT-009 Condition 5).

**Rationale:** Draft 8's BUILD beat (14s) had 5 visual events. The current one-beat-one-visual model cannot represent this. The Visual Director moves visual planning judgment to a prompt + schema + validator, not keyword heuristics or arbitrary cadence rules.

### Condition 6 — Skipped evidence is not pass

`asset_review.py` must not set `ready_for_operator` when any required evidence is `skipped`. `skipped` creates a saved evidence row with `verdict: skipped` and a plain-language reason. The aggregate readiness check counts `skipped` as `needs_operator_decision`. Visual inspection must be beat-aware (first/middle/last frame per beat, frames before/after every cut), not 5 generic keyframes. A deterministic text-integrity check (OCR-free: forbidden debug tokens via pattern, safe-zone bounds via geometry, caption reconstruction via text join) runs alongside the LLM visual review.

**Rationale:** The Draft 8 ledger (§7 false-green causes) shows `skipped` visual inspection became `ready_for_operator`. This is a false green. The charter's "evidence beside every AI claim" rule requires absence of evidence to be visible, not silent.

### Condition 7 — Transition intent is honored, not hardcoded

The edit planning service and cue compiler honor Writer `transition_in` intent where feasible. Hard cuts, crossfades, and holds have explicit narrative jobs. Crossfade overlap is budgeted against the VO clock — if a crossfade would shorten the timeline, the compiler either budgets the overlap or falls back to a cut with a logged warning. Unsupported transitions fail visibly, not silently.

**Rationale:** `build_reel_plan` hardcodes `transition_in: "cut"` for every segment. The new `EditPlanningService` has a `transition` field — but the operator route doesn't reach it (Condition 1).

## What this does NOT change

- The four content gates, per-piece publish approval, no auto-publish — unchanged.
- The Writer/Assembler boundary — the Visual Director is Assembler-side production planning, not audience copy.
- The eight living modules, Process Registry, provenance, determinism — unchanged.
- AMENDMENT-008's compliance loop and AMENDMENT-009's contract boundaries — this amendment extends them, does not override them.
- The approved Draft 8 Reel v3 — regression evidence, not a hardcoded template.

## What this retires

1. **The old `build_reel_plan` path** (`src/reel_production.py:build_reel_plan` + `src/reel_production_runner.py`) for VO-led Reels — replaced by the service-based path. The function may remain as a compatibility shim only if the services call it internally; the operator route must not call it directly.

2. **The tautological VF-AU-302 and VF-AU-304 tests** — replaced with behavioral tests that actually render two tenant configs and assert different resolved styles.

3. **The AST-structural VF-AU-208 test** — replaced with a behavioral test that renders the same input through both the UI route and the autonomous chain and asserts equivalent plans.

4. **The `skipped → ready_for_operator` path** in `asset_review.py`.

## Implementation order (for BUILD_PLAN — M13 milestone)

### Phase M13-A — Dual-path reconciliation (close Finding 1)

1. **VF-VS-101 Wire operator routes to services:** `/api/assets/<id>/edit-plan`, `/render`, `/generate-media` call `EditPlanningService`, `RenderReviewService`, `MediaPlanningService`. Routes handle HTTP only. — AC: same input through UI route and autonomous chain produces equivalent edit plans.
2. **VF-VS-102 Retire old build_reel_plan path:** Delete or gate `reel_production_runner.run_reel_production` for VO-led Reels. — AC: no operator route calls `build_reel_plan` directly.
3. **VF-VS-103 Behavioral VF-AU-208 test:** Render same input through both paths, assert equivalence. — AC: test fails if routes diverge from chain.

### Phase M13-B — Config-driven styles (close Finding 2)

4. **VF-VS-201 Move overlay styles to config:** `config/render_styles.yaml` + Visual Style module overrides. `_resolve_overlay_style` checks config → module → fallback. — AC: two tenant configs, different resolved styles, zero Python edits.
5. **VF-VS-202 Move SFX presets to config:** Same path for `_SFX_PRESETS`. — AC: two tenant configs, different SFX, zero Python edits.
6. **VF-VS-203 Replace tautological tests:** Delete `test_vf_au_302_304_config_style.py` structural tests. Write behavioral tests that load two configs and assert different resolved parameters.

### Phase M13-C — Caption timing (close Finding 3)

7. **VF-VS-301 Extract caption timing service:** `src/services/caption_timing.py` with `chunk_captions()`. Reuse `episode_plan._chunk_vo_text` logic. — AC: 3–6 word phrases, no dangling fragments, exact-text reconstruction.
8. **VF-VS-302 Wire cue compiler to caption timing:** The cue compiler chunks captions via the new service. — AC: cue compiler produces multiple caption cues per beat, not one full-beat caption.
9. **VF-VS-303 Update episode_plan to import shared service:** No duplication. — AC: `episode_plan._chunk_vo_text` delegates to `caption_timing.py`.

### Phase M13-D — Semantic visual events (close Finding 5)

10. **VF-VS-401 Add visual_events to production contract:** `PRODUCTION_CONTRACT_V2` beat schema gains `visual_events[]`. Compatibility: no events → one event from `visual_intent`. — AC: contract validates multi-event beats; old contracts degrade gracefully.
11. **VF-VS-402 Visual Director process:** `prompts/assembly/visual_director_v1.md` + JSON schema + validator. Translates `visual_intent` + VO timings → `visual_events[]`. Registered in Process Registry with `playbook_type: production`. — AC: schema-validated, provenance-logged, no audience copy, no tenant strings.
12. **VF-VS-403 Extend feasibility checks:** Multi-event coverage validation. Missing event coverage → block. Talking-head intent + shorter motion than speech → block or require explicit cutaway. — AC: Draft 8 Artifact A's 5s-motion + still fallback is caught and blocked.

### Phase M13-E — Soundtrack plan (close Finding 4)

13. **VF-VS-501 Soundtrack plan contract:** `src/soundtrack_plan.py` with the schema in Condition 4. Parallel contract referenced by `contract_id`. — AC: `vo_only` requires rationale + approval; `music_bed` requires licence + cost; validation rejects silent VO-only.
14. **VF-VS-502 Soundtrack planning prompt:** `prompts/assembly/soundtrack_plan_v1.md`. LLM proposes mode + emotional register. Python validates. — AC: no genre inference in code; no random effects; provenance logged.
15. **VF-VS-503 Soundtrack preview gate:** Operator hears bed + SFX separately and under VO. Approves, rejects, replaces, or explicitly approves VO-only. — AC: no soundtrack mode change without gate token; synthetic tones not presented as finished design.
16. **VF-VS-504 Soundtrack mix review:** Extends `RenderReviewService`. Expected vs rendered music/SFX, audibility windows, VO-to-bed level, clipping, silence. — AC: missing approved music/SFX fails; unapproved VO-only yields `needs_operator_decision`.

### Phase M13-F — False-green fixes (close Finding 6 + Condition 6)

17. **VF-VS-601 Skipped evidence blocks readiness:** `asset_review.py` — `skipped` → `needs_operator_decision`, never `ready_for_operator`. — AC: skipped visual/transcript creates saved row and blocks readiness.
18. **VF-VS-602 Beat-aware visual inspection:** First/middle/last frame per beat, frames before/after cuts. Replace 5 generic keyframes. — AC: review frame selection derives from plan timing.
19. **VF-VS-603 Deterministic text-integrity check:** Forbidden debug tokens (`{`, `}`, `position`, `style`, `prompt`, JSON/dict fragments), safe-zone bounds, caption reconstruction, overlap/collision. — AC: Artifact A's leaked dict text and clipped captions fail in a regression fixture.
20. **VF-VS-604 Transition intent in cue compiler:** Honor `transition_in` from the Writer. Budget crossfade overlap against VO clock. Unsupported → visible warning or hard failure. — AC: hard cuts, crossfades, holds have explicit jobs; no silent `cut` override.

### Phase M13-G — Regression and proof

21. **VF-VS-701 Artifact A regression fixtures:** Tests that prove detection of: dict metadata as audience text, long unwrapped captions, missing `bottom-third`, still fallback after motion, skipped evidence false-green, missing capture provenance. — AC: all defect classes caught.
22. **VF-VS-702 Real fresh Reel through upgraded path:** One new real Reel through the service-based path. Complete evidence. Operator review. — AC: working artifact, complete evidence, operator approval, no false-green.
23. **VF-VS-703 Full suite + verification:** `pytest -q` green. FFprobe/EBU R128/transcript/OCR/beat-frame on real artifact. Live server smoke test. — AC: tests + real artifact evidence pass.

## Charter text to update

In CHARTER-v3.7, the following sections change:

### Core loop §4 (Assets) — add after the AMENDMENT-008 paragraph:

> A **Visual Director** step (Assembler-side, schema-validated LLM) translates the Writer's `visual_intent` + measured VO timings into `visual_events[]` — concrete visual jobs within each beat. A **soundtrack plan** (parallel contract) makes audio intent explicit: every Reel has a `mode` (`vo_only`, `music_bed`, `source_sound`, `vo_plus_bed`); VO-only requires a rationale and explicit operator approval. The operator gates the soundtrack preview before any music/SFX acquisition. (AMENDMENT-010)

### Design rules — add:

> - **The operator-facing route and the autonomous chain must call the same services.** Two code paths producing different outputs from the same input is a defect. (AMENDMENT-010)
> - **Skipped evidence is not pass.** `ready_for_operator` requires all required evidence present and non-skipped. Missing evidence → `needs_operator_decision`. (AMENDMENT-010)
> - **Every Reel has an explicit soundtrack mode.** VO-only requires a rationale and operator approval. Silent VO-only is not valid. (AMENDMENT-010)
> - **Renderer styles, fonts, colors, and SFX presets come from config/modules, not Python.** Two tenants must render differently with zero Python edits. (AMENDMENT-010)
> - **Captions are phrase-level (3–6 words), timed within the beat.** Full-beat captions are a defect. (AMENDMENT-010)

### The Onboarding Engine / Process Registry — add:

> The Visual Director and Soundtrack Planner are production processes registered in the Process Registry with `playbook_type: production`. They are Assembler-side planning steps, not audience-copy generators. (AMENDMENT-010)