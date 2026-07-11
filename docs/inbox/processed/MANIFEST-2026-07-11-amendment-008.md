# MANIFEST — 2026-07-11 AMENDMENT-008 Final-Output Compliance Loop

**Date:** 2026-07-11
**Architect:** vf-architect
**Batch:** Ratification of DIVERGENCE-012 — final-output compliance contract + bounded remediation loop

## Files

| File | Destination | Action |
|---|---|---|
| `AMENDMENT-008-final-output-compliance-loop.md` | `docs/decisions/` | ADD |
| `BUILD_PLAN-M10-addendum.md` | `docs/inbox/` (this is a BUILD_PLAN patch, not a standalone file — apply to `BUILD_PLAN.md`) | APPLY |
| `MANIFEST-2026-07-11-amendment-008.md` | `docs/inbox/processed/` | (this manifest — moved after filing) |

## Context

DIVERGENCE-012 (filed by builder 2026-07-10) proposed a final-output compliance loop: an LLM-authored compliance contract generated alongside the edit plan, mechanical feasibility checks after TTS, a final-output LLM compliance review after render, and a bounded auto-remediation loop (max 3 rounds). This is the Assembler-side counterpart to AMENDMENT-007 §3 (Writer-side AI review loop).

The architect has APPROVED DIVERGENCE-012 with three conditions:

1. **Text-boundary firewall** — the remediation loop must never modify `platform_content` (approved per-platform text from the Writer). SHA-256 hash of `platform_content` locked at loop entry. Any remediation action that would change it → rejected → `needs_operator_decision`.
2. **Config-driven cost guard** — `max_remediation_cost_usd` in `models.yaml` under `asset_review` block. If absent, remediation is disabled (review-only, no auto-fix). Safe default for new businesses.
3. **Operator visibility** — Assets UI shows: which round ran, what changed, why the loop stopped, per-beat coverage evidence, full provenance history.

This amendment supersedes the advisory-only rule from `CORRECTION-final-output-review-and-audio-fix-v1.0.md` Part 2. The existing ASSET-REVIEW-1 through ASSET-REVIEW-6 checks remain in force — the compliance loop builds on top of them.

This amendment retires the keyword-based VO/content detection in `asset_review.py:686-705` (`_output_should_have_audio`) as a compliance *decision*. It was judgment in code (charter violation). The `_extract_vo_lines` regex in `vo_generator.py:84-92` remains as mechanical extraction input only.

## Notes

1. **DIVERGENCE-012 status is already APPROVED** — the architect patched the divergence file directly. No action needed on that file.
2. **Charter v3.5 is already published** at `docs/CHARTER-v3.5.md`. The builder should update all internal references from `CHARTER-v3.4` to `CHARTER-v3.5`.
3. **BUILD_PLAN header** references `docs/CHARTER-v3.4.md` — update to v3.5.
4. **Implementation order is in AMENDMENT-008** §"Implementation order (for BUILD_PLAN)" — 9 steps. The BUILD_PLAN addendum below adds these as M10 tasks.

## APPLY

1. File `AMENDMENT-008-final-output-compliance-loop.md` to `docs/decisions/`.
2. Apply the BUILD_PLAN M10 addendum (below) to `BUILD_PLAN.md` — add the M10 section after M9, update the version header to v1.7 and the charter reference to v3.5.
3. Update `docs/CONTEXT.md` if it references the asset review layer as "advisory only" — it is now "advisory + bounded auto-remediation per AMENDMENT-008."
4. Log CHANGELOG entry (type: STRUCTURE / STRATEGIC).
5. Move this manifest to `docs/inbox/processed/`.

## BUILD_PLAN M10 Addendum (apply to BUILD_PLAN.md)

Add after M9, before the PROGRESS.md format section:

```markdown
### M10 — Final-output compliance loop (per AMENDMENT-008 / DIVERGENCE-012)
*The Assembler-side counterpart to AMENDMENT-007 §3. A compliance contract, final-output LLM review, and bounded remediation loop ensure every rendered asset faithfully contains the approved script — or the system surfaces exactly what it cannot satisfy and why.*

- [ ] T10.1 **Compliance contract prompts + schemas (P0):** Create versioned prompts and JSON schemas for: (a) script-to-plan compliance contract — the plan-generation LLM produces a structured compliance contract alongside the edit plan, with one entry per required narrative beat (beat_id, source_excerpt, requirement_type, required, planned_segment_ids, planned_time_range, verification_method); (b) final-output compliance review — post-render LLM receives approved script + contract + edit plan + final-file facts + VO transcript + keyframes + prior review findings, returns schema-validated verdict (compliant | revise_plan | regenerate_media | rerender | needs_operator_decision) + per-beat coverage array + issues + safe_remediation_scope + summary; (c) bounded assembler remediation instruction — the LLM produces specific remediation actions within the safe scope — AC: all three prompts versioned in `prompts/assembly/`, schemas in `src/`, validator rejects contracts missing required beats or verification methods
- [ ] T10.2 **Edit-plan record extension (P0):** Extend the `edit_plans` table to persist: the compliance contract (JSON), the source approved-draft version/hash, and review-round history (array of round numbers, verdicts, actions taken, artifact hashes) — AC: edit plan records carry the contract; round history is append-only; provenance entries link to the contract version
- [ ] T10.3 **Pre-render feasibility checks (P0):** After TTS generates VO, deterministic code measures: actual VO duration vs planned timeline duration; whether every contract beat has a plan mapping. If VO duration exceeds timeline duration beyond a configurable tolerance → `needs_operator_decision` with the exact mismatch (no silent truncation). If any required beat has no plan mapping → `needs_operator_decision` — AC: the 92s VO + 18s plan failure case is caught before render; the operator sees the mismatch, not a silently truncated video
- [ ] T10.4 **Final-output LLM compliance review (P0):** After the existing ASSET-REVIEW-1 through 6 layers run, a new LLM compliance review runs: receives approved script, compliance contract, edit plan, final-file duration/stream facts, generated VO transcript/duration, extracted keyframes, and all prior review findings. Returns schema-validated verdict + per-beat coverage (verified | missing | partial | unverifiable with evidence). `compliant` is impossible unless every contract beat is `verified` or the LLM explicitly documents an approved-equivalent representation — AC: a final video cannot be marked compliant without explicit per-beat reviewer evidence
- [ ] T10.5 **Bounded remediation loop (P0):** Implement the render → review → remediate → re-render loop, max 3 rounds. **Condition 1 (text-boundary firewall):** compute SHA-256 of `platform_content` JSON at loop entry; before each remediation action, verify the hash is unchanged; if a remediation instruction would modify `platform_content`, reject it and set verdict to `needs_operator_decision`. **Condition 2 (cost guard):** read `asset_review.max_remediation_cost_usd` from `models.yaml`; track cumulative remediation cost; if exceeded, stop with `needs_operator_decision` + full cost summary; if the config key is absent, remediation is disabled (review-only). Safe remediation scope: edit-plan timing/segment selection, media generation prompts, replacement media, caption rendering/styling, audio mixing, renderer mechanics — AC: a remediable visual/audio failure produces at most 3 render/review rounds; a non-convergent asset stops with full provenance history; the text-boundary firewall rejects any remediation that would change approved text; the cost guard stops the loop when the cap is exceeded
- [ ] T10.6 **Asset-review state model extension (P1):** Extend the asset-review state to record: `reviewing`, `remediating`, `compliant`, `non_convergent`, `needs_operator_decision`. None of these are publication approval. The operator can still approve, fix, or kill regardless of the compliance verdict — AC: state transitions are logged; no state implies publication approval
- [ ] T10.7 **Assets UI — remediation history + coverage (P0):** The Assets UI shows plain-language coverage: what was verified, what is missing, which round ran, what changed per round, why the loop stopped (compliant / non_convergent / cost_cap / needs_operator_decision), and the full provenance history. Per-beat coverage evidence is visible (each beat's status + evidence text). No technical jargon — AC: the operator can see the full remediation history without reading JSON; per-beat coverage is human-readable; the stop reason is plain language
- [ ] T10.8 **Retire keyword-based compliance detection (P1):** Remove `_output_should_have_audio` keyword heuristic from `asset_review.py` as a compliance decision. The compliance contract (LLM-authored) is the authoritative source for "what should be in the output." The `_extract_vo_lines` regex in `vo_generator.py` remains as mechanical extraction input only — AC: grep for `vo_markers` and `speech_markers` in `asset_review.py` returns zero hits in compliance-decision paths; the keyword pattern may remain only if the LLM contract explicitly requires it as mechanical extraction input
- [ ] T10.9 **Config: remediation cost cap (P0):** Add `max_remediation_cost_usd` and `max_remediation_rounds` to the `asset_review` block in `config/models.yaml`. Defaults: `max_remediation_cost_usd` absent (review-only, safe default); `max_remediation_rounds: 3` — AC: config-driven; a second business can set different caps with zero code changes; absent cost cap disables remediation
- [ ] T10.10 **Tests (P0):** Real failure regression (92s VO + 18s plan → stopped, not silently truncated); coverage proof (no compliant without every beat verified); generic content corpus (VO-heavy reels, caption-only reels, silent visual pieces, carousels, image posts — no tenant strings in generic code); three-round cap; cost cap; text-boundary firewall (remediation that would change approved text → rejected → needs_operator_decision); approval integrity (never changes approved text, never publishes automatically); at least one real rendered asset validates video duration, VO duration, transcript/coverage evidence, and the operator-facing review panel — AC: all tests pass; the 92s/18s regression test is in the suite
- [ ] **Checkpoint:** operator end-to-end test with a VO-heavy reel. Tag `review-w8`.
```

Update BUILD_PLAN header to:
```
v1.7 — 2026-07-11 — AMENDMENT-008 final-output compliance loop added as M10 tasks. Charter reference updated to v3.5.
```