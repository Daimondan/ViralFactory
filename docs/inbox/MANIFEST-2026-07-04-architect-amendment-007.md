# MANIFEST-2026-07-04-architect-amendment-007.md

**Filed by:** Architect (vf-architect profile)
**Date:** 2026-07-04
**Purpose:** Notify builder of DIVERGENCE-010 ratification via AMENDMENT-007 — Writer/Assembler boundary redesign. Charter v3.3 → v3.4. BUILD_PLAN v1.5 → v1.6. M9 tasks added.

## What happened

The operator raised 5 design issues with the Writer/Assembler pipeline (filed as DIVERGENCE-010, originally numbered DIVERGENCE-009 but renamed due to collision with the webhook DIVERGENCE-009). The architect has reviewed the code, the prompts, the schemas, and the charter, and **APPROVED all 5 changes**.

## Files already committed by the architect

These files are already in the repo (commits `58fafe1` + `c22cb3c`). The builder does NOT need to file these — they are already in place. This manifest is for notification only.

| File | Action | Notes |
|---|---|---|
| `docs/decisions/AMENDMENT-007-writer-per-platform-assembler-media-only.md` | ADD (already committed) | Full amendment with design specs, schema definitions, implementation order |
| `docs/CHARTER-v3.4.md` | ADD (already committed) | New charter — supersedes v3.3. Incorporates AMENDMENT-006 + AMENDMENT-007 + DIVERGENCE-008 |
| `docs/decisions/DIVERGENCE-010-writer-produces-per-platform-assembler-assembles-only.md` | RENAMED (already committed) | Was DIVERGENCE-009-writer..., renamed to DIVERGENCE-010-writer... to avoid collision with webhook DIVERGENCE-009. Architect decision section appended. |
| `BUILD_PLAN.md` | REPLACE (already committed) | v1.5 → v1.6. M9 tasks T9.1–T9.6 added with acceptance criteria |
| `docs/CONTEXT.md` | REPLACE (already committed) | Core loop diagram, idea card definition, business rules 13–15 updated |
| `docs/PROGRESS.md` | REPLACE (already committed) | DIVERGENCE-010 ratification entry added |
| `CHANGELOG.md` | REPLACE (already committed) | AMENDMENT-007 entry added at top |
| `README.md` | REPLACE (already committed) | Charter version + status updated |

## What the builder needs to do

### Read first (before any M9 work)

1. `docs/CHARTER-v3.4.md` — the new charter. Read it fully. This is your constitution now.
2. `docs/decisions/AMENDMENT-007-writer-per-platform-assembler-media-only.md` — the full amendment with design specs. This is your design document for M9.
3. `docs/decisions/DIVERGENCE-010-writer-produces-per-platform-assembler-assembles-only.md` — the original divergence + architect's ruling.
4. `BUILD_PLAN.md` — M9 section (T9.1–T9.6) with acceptance criteria.

### M9 implementation tasks (from BUILD_PLAN v1.6)

**T9.1 (P0 — charter violation fix, do this first):** Remove `_determine_variant_type` keyword heuristic from `produce_chain.py:407-419` and `app.py:3904`. Remove `_resolve_format_platforms` regex parser from `produce_chain.py:373-404` and `app.py:3878-3901`. The variant type and platform set come from the treatment + Format Guide entry metadata, not keyword matching or regex parsing.

**T9.2 (P1):** Add `variant_type` field to each Format Guide entry. This is a module schema change — gate it normally.

**T9.3 (P0):** Change `DRAFT_SCHEMA` in `pipeline.py` — replace `draft_text` with `platform_content` array (platform, variant_type, content, posts, image_prompts per entry). Update `prompts/draft/generate_v2.md` → v3. Update `produce_chain._step_draft` and the `draft_generate` route in `app.py`.

**T9.4 (P0):** Remove `fan_out_v2.md` and `structure_v1.md` LLM calls from `produce_chain._step_fanout` and the `assets_fan_out` route in `app.py`. The Assembler reads `platform_content` from the approved draft and produces media + assembles only. Zero LLM text calls.

**T9.5 (P0):** New `prompts/draft/alignment_check_v1.md` prompt + JSON schema. Loop logic in `produce_chain.run_writer_chain` — self-audit auto-fix + second-AI alignment check, max 3 rounds. Card state: `writing → reviewing → draft_ready | writer_failed`. Self-audit flags + fixes shown to the human at Gate 2.

**T9.6 (P0):** Update all tests covering the draft schema, the assembler fan-out path, and add tests for the AI review loop.

### Key design decisions the builder must follow

1. **The Writer produces ALL per-platform text in one pass.** The format and platforms come from the locked treatment — the Writer does not decide them. If the output exceeds model limits, the builder may split into per-platform calls, but the design is: Writer = all text, Assembler = no text.

2. **The Assembler makes ZERO LLM text calls.** It reads `platform_content` from the approved draft and produces media + assembles. `fan_out_v2.md` and `structure_v1.md` are retired from the Assembler path (keep the files for provenance history but do not call them).

3. **The AI review loop is NOT a gate.** It runs between `writing` and `draft_ready`. The human does not interact with it. Max 3 rounds. If it doesn't converge, the draft goes to the human with a "AI review did not converge" flag. The human is always the final gate.

4. **Self-audit flags + fixes are shown to the human at Gate 2** for transparency. The operator can see what the AI caught and what it changed before they saw it.

5. **Format + platforms are locked from the treatment at Gate 1.** No code in the pipeline re-derives them. The `_determine_variant_type` keyword heuristic and `_resolve_format_platforms` regex parser are both charter violations (Business Rule #2) and must be removed.

### Charter references

- The charter is now `docs/CHARTER-v3.4.md`. All references to `CHARTER-v3.3` have been updated.
- `docs/CHARTER-v3.3.md` is kept for history but is no longer the governing document.

## What the builder does NOT need to do

- File any of the documents listed above — they are already committed by the architect.
- Update CHANGELOG, PROGRESS, CONTEXT, README, or BUILD_PLAN for the ratification — already done.
- Make any design decisions about the Writer/Assembler boundary — the design is fully specified in AMENDMENT-007.

## Questions?

If anything in AMENDMENT-007 or the M9 tasks is unclear, file a divergence. Do not improvise around acceptance criteria.