# ARCHITECT NOTE — 2026-07-21/22 — Component Workbench + renderer boundary are the blocking production correction

**To:** Builder (`viralfactory` / vf-coder profile)
**From:** Architect (`vf-architect`)
**Status:** APPLY NOW, top-down; documentation-only architect batch

## Operator decision

Do not continue patching the current Reel buttons or implement old VF-VS-515. The operator requires the system to generate the parts first and let the human review/approve them by category before stitching the final video.

Charter v3.9 / AMENDMENT-013 now governs:

`generate exact candidates → human component decisions → completeness → immutable manifest → RendererSpec v1 → selected/local renderer → local artifact evidence → separate exact-artifact Gate 3`

This applies to narration, clips/stills/captures, soundtrack, SFX/source sound, fonts/typography, graphics/overlays/transitions, and any format-declared elements. Category and role definitions are config/prompt-driven, not StackPenni code.

The 2026-07-22 assembly review adds DIVERGENCE-019 without changing Charter v3.9. Do not keep patching FFmpeg/PIL as the sole finish layer and do not hand the script to Vizard. After exact manifest freeze, mechanically compile a provider-neutral `RendererSpec v1`; render the same frozen fixtures through local FFmpeg/PIL, Creatomate, and Shotstack; let the operator judge A/B/C blind; then integrate only the selected provider behind the shared adapter. Every external output returns locally for hash/probe/evidence before Gate 3. The provider cannot select/regenerate ingredients, rewrite text, transcribe as authority, publish, or silently degrade unsupported features.

## Why this is blocking

The 2026-07-21 runtime audit found:

- card 59 / asset 18 stayed at `awaiting_soundtrack_approval` / pending for 25 minutes with no final artifact;
- recent jobs repeatedly advanced then failed on absent visual/VO prerequisites;
- mutable inventory enters edit planning with no exact component approvals;
- VO, stock/generated media, fonts, graphics, and SFX are auto-selected or hidden;
- multi-platform production calls `get_asset_by_draft()` and reduces the draft to one child asset;
- Gate 3's API can write approval without proving current final artifact + manifest + blocking evidence;
- service health and component tests are therefore not end-to-end proof.

Read the review for exact current code and DB evidence.

## Immediate work order

1. VF-CW-001 — preserve behavioral RED fixtures and correlation evidence.
2. VF-CW-002..004 — production session, requirement contract, immutable candidate/decision identity.
3. VF-CW-005..008 — candidate sets for narration, visuals, soundtrack/SFX, typography/graphics.
4. VF-CW-009 — deep human workbench UI.
5. VF-CW-010 — deterministic completeness and manifest freeze.
6. VF-RA-001 — RendererSpec v1, capability checks, and local conformance adapter.
7. VF-RA-002 — isolated Creatomate/Shotstack bake-off over identical frozen fixtures.
8. VF-RA-003 — blind operator selection plus cost/reliability/terms evidence.
9. VF-RA-004 — selected durable production adapter and verified local artifact import.
10. VF-CW-011 — manifest/spec-only assembly and hardened Gate 3 service.
11. VF-CW-012 — resumable multi-platform/local-provider orchestration and fresh deployed proof.

Creatomate testing has a hard 50-credit trial ceiling. Use the DIVERGENCE-019 staged plan: no-credit local validation first, at most 34 planned credits across smoke/previews/quality proofs, and preserve 16 credits for failures or retries. Do not burn credits debugging payload syntax, inaccessible media URLs, duplicate submissions, or speculative cosmetic changes.

Do not start with the UI. Candidate identity, decision binding, completeness, and manifest semantics come first.

## Hard stops

- Do not remove or weaken final-artifact Gate 3.
- Do not add authoritative approval Booleans.
- Do not let the assembler query “latest” inventory or silently substitute media.
- Do not infer approval for old/regenerated artifacts.
- Do not preserve legacy and manifest paths as competing production routes.
- Do not use keyword heuristics for creative role requirements.
- Do not count a human wait as a running job.
- Do not put provider-specific fields in the component manifest or call a vendor directly from Flask routes.
- Do not enable provider stock/generation/transcription/publishing or open-ended editing after manifest freeze.
- Do not show provider success as green before local download, hash, probe, blocking evidence, and current manifest/spec lineage pass.
- Do not silently drop unsupported transitions, captions, fonts, graphics, or audio roles; capability gaps block.
- Do not close VF-VS-516/702/703 with reused media, skipped connection failures, or port 5000.

## Required completion handoff

After VF-CW-012, leave one builder note in `docs/inbox/` with:

- commits/task IDs and exact files;
- automated test results;
- fresh deployed session/asset/manifest/render IDs and hashes (no secrets);
- restart-resume evidence;
- alternative/regeneration invalidation evidence;
- canonical spec hash, selected provider ruling, local/provider lowering evidence, actual bake-off cost/latency, and explicit fallback result;
- laptop + mobile walkthrough URL/evidence;
- every known remaining defect or deferred state.

Move this note and its manifest to `docs/inbox/processed/` only after you have read and begun applying the work order. The architect intentionally leaves them top-level as the handoff signal.
