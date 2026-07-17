# Assembler Full Upgrade — Verified Baseline Audit

**Task:** VF-AU-001
**Audit date:** 2026-07-17
**Audited commit:** `7ab6d1b` (local main, pushed to origin/main)
**Test count:** 1,084 collected, 1,083 pass + 1 test-ordering flake (passes in isolation)
**Authority:** Live repository only. Handoff snapshots used for cross-reference but not trusted over live code.

## Purpose

Verify every drift claim from `09-VERIFIED-CODE-DRIFT.md` against the current live codebase. Classify each finding as design change, implementation compliance, or schema enrichment. Record exact paths and line numbers.

## Verified findings

### 1. Autonomous chain stubs — CONFIRMED

**File:** `src/produce_chain.py`

- `run_assembler_chain()` calls `_step_fanout`, `_step_vo`, `_step_media_plan`, `_step_media_exec`, `_step_edit_plan`, `_step_render` (lines 342–345).
- `_step_media_plan` (line 414): `pass` — stub.
- `_step_media_exec` (line 421): `pass` — stub.
- `_step_edit_plan` (line 425): `pass` — stub.
- `_step_render` (line 429): `pass` — stub.
- `_step_draft` (line 433) and `_step_vo` (line 359) are implemented.
- `_step_fanout` (line 594) is implemented.

**Classification:** Implementation compliance. The declared autonomous chain cannot complete the same path available through operator routes. Stubs must be implemented by reusing verified route logic.

### 2. Route-bound implementation — CONFIRMED

**File:** `src/app.py`

Substantial production logic embedded in HTTP route handlers:

- `/api/assets/<asset_id>/edit-plan` (line 6423): builds scoped inventory, calls edit-plan LLM, validates source IDs, persists plan. ~250 lines of business logic.
- `/api/assets/<asset_id>/render` (line 6680): VO generation, rendering, zero-byte check, post-render review (mechanical + visual + audio + alignment). ~220 lines.
- `/api/assets/<asset_id>/generate-media` (line 7191): builds media plan from missing captures, executes stock/AI acquisition. ~200+ lines.

**Classification:** Design change (refactor). Routes handle HTTP state; business logic must be extracted into shared services that both routes and ProductionChain call.

### 3. Process Registry drift — CONFIRMED

**File:** `config/processes.yaml`

- `draft_generate` (line ~70) points to `draft/generate_v2.md` — retired by AMENDMENT-007.
- `fan_out_adapt` points to `assets/fan_out_v2.md` — retired by AMENDMENT-007.
- `native_structure` points to `assets/structure_v1.md` — retired by AMENDMENT-007.
- No process entries for: media plan, edit plan, compliance contract/review, remediation, performance analysis.
- `produce_chain.py` line 438 calls `draft/generate_v3.md` directly, bypassing the registry.

**Classification:** Implementation compliance. AMENDMENT-005's declarative process composition is not enforced. Retired processes must be removed from active runtime; new production processes must be registered.

### 4. Identity mismatch — CONFIRMED

**File:** `src/pipeline.py`

- `COMPLIANCE_CONTRACT_SCHEMA` (line 603) uses `beat_id` (line 613, 621).
- `COMPLIANCE_REVIEW_SCHEMA` (line 669) uses `beat_id` (line 687).
- `REMEDIATION_INSTRUCTION_SCHEMA` (line 727) uses `beat_ids_affected` (line 753).
- Edit plans (`edit_plans` table): `plan_json` is free-form JSON. No `segment_id`, `beat_ids`, or `text_intent_id` columns. Identity is reconstructed from list position or prose matching.
- No `contract_id`, `platform_variant_id`, `media_recipe_id`, `ingredient_id` fields exist in any schema.

**Classification:** Schema enrichment. Stable identity chain must be added: `contract_id → platform_variant_id → beat_id → {text_intent_id, media_recipe_id, ingredient_id, segment_id}`.

### 5. Media-plan scope mismatch — CONFIRMED

**File:** `src/app.py` line 7191

The `generate-media` route begins from `capture_required` tasks (line ~7215) and builds plan items around missing captures. It does not guarantee every semantic beat receives intentional visual treatment.

**Classification:** Implementation compliance. Media planning must start from the Writer's semantic beats, not from missing-capture gaps.

### 6. Compliance wiring gap — CONFIRMED

**Files:** `src/asset_review.py`, `src/compliance_validators.py`, `src/feasibility_checks.py`

Existing components:
- `AssetReviewer` class with `review_render()`, `run_visual_inspection()`, `run_audio_inspection()`, `run_content_alignment()`.
- `COMPLIANCE_CONTRACT_SCHEMA`, `COMPLIANCE_REVIEW_SCHEMA`, `REMEDIATION_INSTRUCTION_SCHEMA` in `pipeline.py`.
- `compliance_validators.py` and `feasibility_checks.py` exist.

Wiring gap: The render route (line 6795–6880) explicitly describes review as **advisory**: "The review is advisory — it doesn't block the operator from seeing the video." The full blocking compliance contract/remediation path from AMENDMENT-008 is not wired. No `ready_for_operator` state is gated on compliance. No feasibility checks are invoked before rendering. Remediation schemas exist but are not executed.

**Classification:** Implementation compliance. AMENDMENT-008 requires blocking compliance before `ready_for_operator`. The advisory-only review must be upgraded to blocking with bounded remediation.

### 7. Renderer configuration gap — CONFIRMED

**File:** `src/assembly.py`

- `_OVERLAY_STYLES` (line 624): hardcoded style presets keyed by `style_ref`. FFmpeg drawtext parameters.
- `_SFX_PRESETS` (line 817): hardcoded SFX presets (frequency, duration, volume) per type.
- Default SFX fallback: `_SFX_PRESETS["pop"]` (line 828) — blanket default.
- No config/module loading for overlay styles, SFX, fonts, colors, safe zones, or grade tokens.

**Classification:** Implementation compliance. Tenant presentation must move to config/modules per the charter's "no business values in code" rule.

### 8. Reference-asset injection gap — CONFIRMED

**File:** `src/reference_assets.py` exists with `ReferenceAssetStore` class (propose/approve/retire lifecycle, `get_generation_context()`).

Wiring gap: `reference_assets` table exists in the DB. `src/reference_assets.py` exists. But `pipeline.py` has zero references to `reference_asset` (grep returned 0). The reference-assets registry is not injected into media planning, edit planning, or generation provenance.

**Classification:** Implementation compliance. Approved reference assets must be injected into planning and generation with versioned provenance.

### 9. Post-publish learning loop gap — CONFIRMED

**DB tables:** `post_metrics` (columns: metric_label, metric_value, metric_date, percentage_change, pulled_at). No `creative_fingerprint`, `contract_version`, `process_version`, `comment_to_like`, `share_to_like`, `save_to_like`, `operator_edits`, `compliance_history`, or `remediation_history` columns.

No performance record schema, Analyst process, or learning proposal path exists in code or config.

**Classification:** Schema enrichment + implementation. Performance records, creative fingerprints, and human-gated learning proposals must be built.

### 10. Text/audio deterministic compilation gap — CONFIRMED

No deterministic compiler exists. Frame `text_on_screen` values are passed to the edit-plan LLM as context; the LLM may omit or reinterpret them. Audio intents (music/SFX) in frames use different shapes from edit-plan audio cues. No translation layer.

**Classification:** Implementation compliance. Deterministic compilers must preserve exact approved text, timing, and audio intent.

## Existing strengths to preserve

- LLM adapter with retry-once, cache, provenance logging.
- MediaAdapter provider abstraction (FAL, stock).
- Inventory source validation rejects invented IDs (edit-plan route, line ~6520).
- Generated and linked-upload inventory is asset-scoped (not business-wide).
- Session uploads excluded from assembly inventory (privacy guard, line ~6515).
- VO generation with TTS + voice cloning.
- FFmpeg rendering with zero-byte check, Ken Burns, xfade transitions, text overlays, SFX.
- Compliance schemas and storage groundwork (compliance_contract_json, source_draft_hash, review_round_history in edit_plans table).
- Reference-assets table and ReferenceAssetStore with full lifecycle.
- Gate-token enforcement (idea gate, draft gate, asset gate, publish gate).

## Test baseline

- **1,084 tests collected** via `python3 -m pytest --co -q`.
- **1,083 pass** in full suite run (1 flaky test: `test_video_handoff_vh.py::TestVH2GenerateMediaVideo::test_generate_media_fallback_ai_video_polls_and_downloads` — fails in full suite due to SQLite DB file contention, passes in isolation). This is a pre-existing test isolation issue, not introduced by any assembler-upgrade work.

## Classification summary

| # | Finding | Classification |
|---|---------|---------------|
| 1 | Chain stubs | Implementation compliance |
| 2 | Route-bound logic | Design change (refactor) |
| 3 | Process registry drift | Implementation compliance |
| 4 | Identity mismatch | Schema enrichment |
| 5 | Media-plan scope | Implementation compliance |
| 6 | Compliance wiring | Implementation compliance |
| 7 | Renderer config | Implementation compliance |
| 8 | Reference-asset injection | Implementation compliance |
| 9 | Learning loop | Schema enrichment + implementation |
| 10 | Deterministic compilation | Implementation compliance |

## No behavior changes made

This audit made zero runtime behavior changes. All findings are documented for the implementation plan.