# DIVERGENCE-014 — Visual + soundtrack pipeline upgrade and dual-path reconciliation

**Filed:** 2026-07-18
**Filed by:** Architect (vf-architect)
**Status:** FILED — awaiting ratification via AMENDMENT-010
**Trigger:** Builder note `BUILDER-NOTE-2026-07-18-draft8-visual-soundtrack-pipeline.md` + `REQUEST-architect-review-draft8-pipeline-upgrade-2026-07-18.md`

## What this divergence addresses

The builder filed a two-track proposal: (Track A) correct the Draft 8 Reel as a one-off artifact, then (Track B) promote proven visual and soundtrack lessons into the reusable pipeline. Track A is complete — the operator approved Reel v3 (`data/media/6/final_2.mp4`, hash `f94c4ad4…aa172a`) as the visual standard and chose to leave it VO-only. Track B now requires an architect ruling before implementation.

This divergence records three findings from the architect's live-code audit and proposes the charter amendment that follows.

## Architect's findings from the live code

### Finding 1 — The Assembler Full Upgrade built services the operator never reaches

VF-AU-001 through VF-AU-603 are all marked complete in `BUILD_PLAN.md`. The builder created real, substantive services:

- `src/services/media_planning.py` (9.3 KB)
- `src/services/media_inventory.py` (7.7 KB)
- `src/services/media_acquisition.py` (11.7 KB)
- `src/services/cue_compiler.py` (9.0 KB) — deterministic phrase captions, overlays, SFX, music events
- `src/services/edit_planning.py` (4.7 KB) — segments with IDs, transition reasons
- `src/services/render_review.py` (7.6 KB) — centralized render + compliance
- `src/production_contract.py` (22.9 KB) — stable IDs, capture policy, hash-lock
- `src/production_contract_validators.py` (10.1 KB)
- `src/contract_compat.py` (7.4 KB)
- `src/feasibility_checks.py` (8.4 KB)

The autonomous chain (`src/produce_chain.py:run_assembler_chain`) correctly calls these services: `_step_media_plan` → MediaPlanningService, `_step_edit_plan` → EditPlanningService + CueCompiler, `_step_render` → RenderReviewService.

**But the operator-facing manual route does not.** The live operator path is:

- `/api/assets/<id>/edit-plan` (`src/app.py:6660`) — builds ingredient inventory inline, calls `LLMAdapter` with `EDIT_PLAN_SCHEMA` directly, persists plan. ~250 lines of business logic.
- `/api/assets/<id>/render` (`src/app.py:6917`) — calls `AssemblyRenderer` directly, runs post-render review inline. ~220 lines.
- `/api/assets/<id>/generate-media` (`src/app.py:7538`) — builds media plan from missing captures inline, executes stock/AI acquisition. ~200+ lines.
- `/api/assets/<id>/produce-reel` (`src/app.py:6477`) → `src/reel_production_runner.py:run_reel_production` → `src/reel_production.py:build_reel_plan` — the OLD path that still does "5s motion clip + image fallback for remainder" and full-beat captions.

`src/app.py` contains **zero imports** of `EditPlanningService`, `CueCompiler`, `RenderReviewService`, or `MediaPlanningService`. The new services exist but the operator's UI routes around them. This is the same "route-bound implementation" drift that `ASSEMBLER-UPGRADE-BASELINE.md` Finding #2 flagged — and VF-AU-208 was supposed to fix it. VF-AU-208's tests only verify that `produce_chain.py` stubs are non-empty and reference the services by name; they never verify that the operator-facing routes call the services.

**Classification:** Implementation compliance defect. VF-AU-208's acceptance criterion ("UI route and chain call same service") is not met. The builder marked it complete because the tests pass, but the tests are structural-AST checks, not behavioral wiring tests.

### Finding 2 — VF-AU-302 and VF-AU-304 tests are tautological

VF-AU-302 ("Move tenant presentation from Python to module/config") is marked complete. Its acceptance criterion: "two tenant fixtures render different styles with zero Python edits."

The test (`tests/test_vf_au_302_304_config_style.py:35`) verifies that `AssemblyRenderer.__init__` accepts a `models_config` parameter and that `_OVERLAY_STYLES` exists in source. It does not render two tenants. It does not check that config overrides the hardcoded dict. The hardcoded `_OVERLAY_STYLES` (hook/default/highlight/title) and `_SFX_PRESETS` (with `_SFX_PRESETS["pop"]` blanket fallback) at `src/assembly.py:624,817` are still the only style resolution path. `_resolve_overlay_style` checks `style_ref in self._OVERLAY_STYLES` and returns `self._OVERLAY_STYLES["default"]` — no config lookup.

VF-AU-304 ("Config-driven music and SFX") is the same pattern: the test asserts `_resolve_sfx_preset` exists and references `_SFX_PRESETS`, but never verifies config override.

**Classification:** Implementation compliance defect. The acceptance criteria are not met. The tests pass because they test the wrong thing.

### Finding 3 — The cue compiler does not do phrase-level caption chunking

The cue compiler (`src/services/cue_compiler.py:87-100`) creates one caption cue per `text_intent` with `function == "caption"`, spanning the full beat's VO timing (`start_sec=vo_timing.start_sec, end_sec=vo_timing.end_sec`). There is no phrase-level chunking (3–6 word segments), no word-timestamp input, no proportional timing distribution.

The only phrase-level chunking in the codebase is `src/episode_plan.py:392-455` (`_chunk_vo_text`), which chunks 3–5 words and distributes proportionally — but that's in the episode-format path, not the generic reel path. The Draft 8 correction ledger identifies full-beat captions as a root-cause defect (§7 cause #2, §8 quality bar, beat audit across all six beats). The cue compiler — the service that was supposed to fix this — reproduces the defect.

**Classification:** Implementation compliance defect. VF-AU-205's acceptance criterion ("exact-text preservation; timing arithmetic; collision/safe-zone validation") is met, but the underlying promise — phrase-level captions — is not.

### Finding 4 — No soundtrack_plan contract exists

The cue compiler handles `audio_intent` per beat (SFX events from `ai.get("sfx", [])`, music events from `ai.get("music", [])`). But there is no `soundtrack_plan` contract: no `mode` field (`vo_only` | `music_bed` | `source_sound`), no `music_bed_ref` with licence provenance, no VO-ducking envelope, no operator gate for soundtrack preview, no `vo_only_approved` evidence. The operator's observation that v3 is VO-only with no explicit soundtrack mode is a real gap: the system can silently produce VO-only Reels without an explicit approval.

**Classification:** Schema enrichment + new contract. This is genuinely new work, not a gap in completed tasks.

### Finding 5 — No semantic visual events

The production contract carries `visual_intent` per beat (subject/action/meaning) — a single semantic description per beat. The media planning service has no concept of multiple visual events within one beat. The Draft 8 correction proved that a 14-second beat needs multiple semantic visual events (the BUILD beat alone had 5 events). The current contract model is one-beat-one-visual.

**Classification:** Schema enrichment. Also genuinely new work.

### Finding 6 — `build_reel_plan` still forces `transition_in: "cut"` for every segment

`src/reel_production.py:246` hardcodes `"transition_in": "cut"` for every segment. The comment says "Cuts preserve the measured VO clock exactly. Crossfades shorten the assembled timeline unless their overlap is budgeted." This is mechanically safe but ignores Writer `transition_in` intent entirely. The new `EditPlanningService` has a `transition` field with a `transition_reason` — but it's only reachable through the autonomous chain, not the operator route (Finding 1).

**Classification:** Implementation compliance defect (the old path) + design enrichment (transition intent in the new path needs the operator route to reach it).

## What this means for the builder's proposal

The builder's Track B proposal (Phases B1–B9) is well-reasoned and charter-aligned. But a large portion of it is already **designed and built but not wired**. The builder proposed building new caption chunking, new transition handling, new style config, new false-green fixes — but the services for these already exist in `src/services/`. The real work is:

1. **Wire the operator-facing routes to the new services** (close Finding 1). This is not new design — it's completing VF-AU-208 properly.
2. **Fix the tautological tests** (Finding 2) and actually move overlay styles/SFX to config.
3. **Add phrase-level caption chunking to the cue compiler** (Finding 3) — reuse `episode_plan._chunk_vo_text` logic.
4. **Add the soundtrack_plan contract** (Finding 4) — genuinely new.
5. **Add semantic visual events to the production contract** (Finding 5) — genuinely new.
6. **Add transition intent to the cue compiler / edit planning** (Finding 6) — the new path has the field; it needs the operator route to reach it and the compiler to honor it.

The builder's proposed tasks map to this reality:

| Builder task | Status | Architect ruling |
|---|---|---|
| B1.1 Preserve structured text_on_screen | Already fixed in `reel_production.py:45` (the overlay dict extraction) | DONE — regression test only |
| B1.2 Preserve visual/transition structure | New services do this; old path doesn't | Wire old path to new services (VF-AU-208-real) |
| B2.1 Semantic visual events | Not in contract | NEW — add `visual_events[]` to production contract |
| B2.2 Coverage/freeze validation | Feasibility checks exist but don't cover multi-event | Extend `feasibility_checks.py` |
| B3.1 Caption chunking service | `episode_plan._chunk_vo_text` exists; cue compiler doesn't use it | Extract to `src/services/caption_timing.py`, wire cue compiler |
| B3.2 Alignment backend | Decision gate — deferred from T2.6-T2.8 | DEFERRED — proportional timing labeled approximate |
| B4.1 Wrapped text + safe zones | `assembly.py` centers unwrapped text; `_overlay_position_y` has no `bottom-third` | FIX in assembly.py |
| B4.2 Style presets to config | VF-AU-302 marked complete but not actually done | REDO — actually move `_OVERLAY_STYLES` to config |
| B4.3 Timed text animations | Not built | NEW — but low priority, declare unsupported for now |
| B5.1 Transition intent | New path has it; old path hardcodes `cut` | Wire old path to new services |
| B6.1 Source categories | `production_contract.py` has capture policy | VERIFY — check enforcement |
| B7.1-B7.4 False-green fixes | `asset_review.py` still has `skipped` verdicts → `ready_for_operator` | FIX — skipped must not become ready |
| B8.1 Loudness targets | `assembly.py` has loudnorm support | VERIFY config-driven target |
| B8.2 Soundtrack plan | NOT BUILT | NEW — `soundtrack_plan` contract |
| B8.3 Soundtrack mix review | NOT BUILT | NEW — extends render review |
| B9.1-B9.3 Regression + proof | Standard | REQUIRED |

## The nine architect decisions requested

1. **Semantic visual events: enrichment or new contract?** → New versioned field. Add `visual_events[]` to the beat in `PRODUCTION_CONTRACT_V2`. A beat carries one `visual_intent` (the semantic meaning) and zero-or-more `visual_events` (the concrete visual jobs within that beat's time range). Events have: `event_id`, `time_range`, `narrative_function`, `source_policy`, `required_text`, `capture_policy_ref`. This is additive — existing contracts with no `visual_events` degrade to one event per beat (the beat's `visual_intent`).

2. **Schema boundary: Writer intent vs Visual Director vs compiler vs renderer?** → The Writer produces `visual_intent` (semantic meaning) and `audio_intent` (mode + cues). A **Visual Director** LLM step (new, schema-validated, prompt-versioned) translates `visual_intent` + measured VO timings into `visual_events[]`. The deterministic cue compiler compiles events to renderer instructions. The renderer executes. **No LLM in the compiler.** The Visual Director is a new production process registered in the Process Registry, not a new onboarding playbook.

3. **Soundtrack plan: same contract or parallel?** → Parallel `soundtrack_plan` contract, referenced by `contract_id` from the production contract. Fields: `mode` (`vo_only` | `music_bed` | `source_sound` | `vo_plus_bed`), `music_bed_ref` (source ID, licence, cost), `ducking` (envelope), `sfx_cues[]` (event ID, source/preset, timestamp, gain, purpose), `vo_only_rationale` (required when mode is `vo_only`), `operator_approval` (gate token). The soundtrack plan is LLM-proposed (emotional register judgment) + Python-validated (references, timing, licence, gain bounds). **Generic code must not infer genre or add random effects.**

4. **Merge with M10/M11/assembler baseline?** → The new services (VF-AU-101..207) are the foundation. This amendment does not duplicate them — it (a) wires the operator route to them, (b) extends the contract with `visual_events` and `soundtrack_plan`, (c) adds the Visual Director process. M10 compliance work and M11 episode-format work are preserved. The episode-format `_chunk_vo_text` logic is extracted to a shared service, not duplicated.

5. **Style-frame and soundtrack-preview approvals: new gates or reused?** → Both are **conditional hard gates**: required when the soundtrack mode is not `vo_only` (soundtrack preview) or when `visual_events` include generated motion (style frames). VO-only with text-card visuals requires no style-frame gate. The operator may approve a preset once and reuse it (config-driven `approved_presets`).

6. **Provenance contract for stock/music/generated?** → Every ingredient carries: `source_type` (`operator_capture` | `licensed_stock` | `approved_reference` | `generated_still` | `generated_motion` | `renderer_graphic`), `source_ref` (URL/ID/path), `licence` (type, holder, expiry), `cost_usd`, `provenance_hash`. The production contract's hash-lock covers ingredient provenance — swapping a licensed clip for an unlicensed one is a contract change, not a silent substitution.

7. **Evidence completeness rule?** → For VO-led Reels, `ready_for_operator` requires: mechanical + audio signal + transcript coverage + visual inspection (beat-aware, not 5 keyframes) + text/OCR integrity (forbidden debug tokens, safe-zone bounds, caption reconstruction) + beat semantic coverage + alignment aggregation + soundtrack completeness (mode, music/SFX audibility if approved, VO intelligibility). **`skipped` is not `pass`.** Missing required evidence → `needs_operator_decision`.

8. **Charter conflict?** → Yes. The charter (v3.6) §4 says "The Assembler does no audience-copy generation." The Visual Director LLM produces `visual_events[]` which describe visual jobs — this is not audience-copy (it's production planning judgment, same as the Media Planner per AMENDMENT-009 Condition 5). But the charter does not mention a Visual Director role. This requires a versioned amendment (AMENDMENT-010). The soundtrack plan's LLM-proposed emotional register is also production judgment, not audience copy — same justification.

9. **Implementation order and milestone boundary?** → See AMENDMENT-010 §Implementation order. The milestone is M13 (Visual + Soundtrack Pipeline). It follows the completed Assembler Full Upgrade (M10–M12 work) and closes the dual-path gap.

## Constraints that survive (from the builder's request, confirmed)

All 13 constraints listed in `REQUEST-architect-review-draft8-pipeline-upgrade-2026-07-18.md` are confirmed as binding. No StackPenni strings in generic code. Judgment in prompts + schemas + validators. Mechanical rendering deterministic. No paid action without fresh operator-approved estimate. Generated media cannot satisfy real-capture. Style previews are not production layers. Caption/emphasis/info/CTA/brand roles separately composited and collision-checked. VO is master clock. Missing evidence cannot pass. Synthetic placeholder tones are not finished sound design. VO-only must be explicit and approved. No publication without per-piece approval.

## What this divergence does NOT change

- The four content gates, per-piece publish approval, no auto-publish — all unchanged.
- The Writer/Assembler boundary — the Visual Director is an Assembler-side process, same as the Media Planner. It produces production planning, not audience copy.
- The eight living modules, the Process Registry, provenance, determinism — all unchanged.
- The approved Draft 8 Reel v3 — it is regression evidence, not a hardcoded template. No StackPenni scene values enter generic code.

## Ratification path

This divergence is ratified by AMENDMENT-010 → Charter v3.7. The amendment adds:
- The Visual Director as an Assembler-side production process.
- The `soundtrack_plan` contract.
- The `visual_events[]` beat enrichment.
- The dual-path reconciliation requirement (operator route must use the same services as the autonomous chain).
- The evidence-completeness rule (skipped ≠ pass).