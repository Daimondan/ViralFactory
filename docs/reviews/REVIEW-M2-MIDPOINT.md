# Architect Interim Review — M2 midpoint (T2.1–T2.2)

*Destination: `docs/reviews/REVIEW-M2-MIDPOINT.md` · Claude architect · 2026-07-02 · Reviewed at head after T2.2 commit. Suite run by architect: 133 tests pass.*

**Verdict: T2.1 and T2.2 approved with corrections. R10 and R11 land before T2.3 begins. R12–R15 land during M2 (R13 changes M2 task ordering). R16 is a binding constraint on T2.6–T2.8. This is not a tagged review; review-w2 remains the M2-completion checkpoint.**

Confirmed aligned: R1–R5 landed before M2 work began; review-w1 tag exists; AMENDMENT-003 applied faithfully across charter v3.2, CONTEXT.md, UI-DIRECTION.md, and BUILD_PLAN M3; the no-auto-publish hard rule is intact; DIVERGENCE-003 filed with correct license diligence (XTTS-v2/Coqui CPML exclusion is right); inbox protocol executed correctly on its first batch; T2.1/T2.2 follow the R1 gate pattern (writes only on approval, parked writes nothing — verified in tests); v2 bulk-import routes imported sources through the gate rather than auto-writing.

---

## R10 — MUST FIX — Repo visibility mismatch + console has no auth

- The GitHub API reports the repo as **public**; PROGRESS.md says "(private)". The charter, business strategy, sub-brand roadmap, and commercial plans are world-readable. No secrets are exposed (keys are env vars — correct), but this is either an unintended flip or a stale doc. **Fix: flip the repo private (or, if open is a deliberate choice, record it in the CHANGELOG and correct PROGRESS.md).**
- The Flask console has zero authentication. Its endpoints trigger paid LLM calls, overwrite `config/business.yaml` and `config/sources.yaml`, and read server filesystem paths (`V2_BACKUP_PATH`). **Fix (deployment baseline, before the M2 operator end-to-end test on the VPS): bind to localhost/VPN only, or add auth. Document the chosen posture in CONTEXT.md.**

## R11 — MUST FIX — v2 bulk-import enable switch is client-controlled

`/api/run/<id>/v2-bulk-import` gates on `request.json["enabled"]`. Any client can flip it per-call; "ships disabled by default" is decorative. **Fix:** server-side switch — env var `V2_IMPORT_ENABLED=true` (or a config flag) checked before anything else; remove the request parameter. Two defects in the same endpoint:

- `db_files[0]` opens an arbitrary glob match. Select the newest backup by mtime, or require an explicit filename.
- `SELECT * FROM sources LIMIT 100` silently truncates the 1,531-source backup. Either paginate, or return `truncated: true` with `total_available` so the operator knows what was left behind.

Tests: enabled=false-equivalent server state → endpoint refuses regardless of request body; truncation reported.

## R12 — MUST FIX (before review-w2) — Tenant strings in templates and prompts

The zero-tenant-strings check evidently scans only `.py`. Leaks:

- `src/templates/business_profile.html` — every placeholder is a StackPenni/Caribbean example. These bias every future tenant's intake answers. Genericize (e.g. "We help [audience] do [outcome]…").
- `src/templates/sources_engine.html` — "the old StackPenni v2 pipeline" → "a previous pipeline backup".
- `prompts/sources_engine/analyze_v1.md` criterion 6 hardcodes "Caribbean/regional" in a **generic harness prompt**. Parameterize: "does the source need to be specific to {business_region}, or is global fine if the insight transfers?" — region supplied from `business.yaml`.
- `prompts/voice_profile/analyze_v1.md` "Bajan, Caribbean English" — defensible as illustrative examples of the dialect-preservation rule; acceptable to keep as "e.g." examples, but preferable to draw examples from the business's declared dialects. Lower priority.

**Extend the zero-tenant-strings test to `src/templates/` and `prompts/`.**

## R13 — MUST FIX (ordering change) — Pull T2.9 forward, before T2.3

R7 flagged `ModuleStore.store()` as honor-system. Since then the honor-system surface grew: `store-business` and `store-sources` both take `approved` from the request body, and both also write config yaml outside the module store. T2.3–T2.4 will add four more store endpoints. **Reorder M2: T2.9 (gate-token enforcement) lands before T2.3**, and its scope covers: `ModuleStore.store()`, both config-yaml write paths, and all playbook store endpoints — a verified approval record ID required by the write layer itself, not the route. Enforce three paths now instead of retrofitting seven later.

Also in `store_sources`: on ConfigError the code falls back to `business_slug = criteria.get("business_slug", "unknown")` and writes `modules/unknown/…`. A module with no tenant is an orphan. Return 500 instead.

## R14 — SHOULD FIX — Config yaml writes are destructive

`business.yaml` and `sources.yaml` are overwritten in place. Modules auto-archive; config does not. One bad gate approval destroys a working config unless git happens to have it committed. **Fix:** before overwrite, copy the existing file to `config/archive/{name}-{timestamp}.yaml` (or route config writes through the same archiving pattern ModuleStore uses). Test: two successive approvals → prior version present in archive.

## R15 — MINOR — Hardcoded gate step numbers in routes

`set_gate_result(run_id, "4", …)` / `"5"` in `store_business` / `store_sources`. If a playbook's markdown reorders steps, gate records mislabel silently. Derive the gate step index from the parsed playbook.

## R16 — BINDING CONSTRAINT on T2.6–T2.8 — VPS audio resource plan

8 GB RAM / 2 CPU cores / no GPU. faster-whisper `small` int8 is fine. Qwen3-TTS at 1.7B params on 2 CPU cores will be slow (plausibly minutes of compute per minute of audio) and several GB resident. Requirements:

1. **Never hold both models in memory simultaneously.** Lazy-load, use, unload; transcription and synthesis are sequential jobs.
2. **Synthesis runs as a background job**, never inside a request-blocking Flask handler.
3. **Smoke-test Qwen3-TTS on the actual VPS before building T2.7's architecture around it.** If the batch window is unusable, evaluate the fallbacks (MOSS/VoxFlash) or record a divergence accepting GPU-later via the swappable adapter.
4. **Amend T2.7 AC to:** "given reference audio clips, the adapter produces an audio file of the text spoken in that voice **on the production VPS within an acceptable batch window** (operator defines acceptable; record the measured time in PROGRESS.md)."

## Process corrections

1. PROGRESS.md "What's Next" still lists "Tag review-w1" unchecked — the tag exists. Clear it.
2. Record the repo-visibility decision (R10) in the CHANGELOG whichever way it goes.

---

## Revised M2 order

T2.9 (pulled forward, expanded scope per R13) → R10/R11/R12/R14/R15 corrections → T2.3 → T2.4 → T2.5 (now largely absorbed by T2.9; verify remaining scope: schema-check on load, version history visible) → T2.6 → T2.8 → T2.7 (smoke test first per R16) → T2.10 → T2.11 → operator end-to-end test (review-w1_1.md checklist, with R10 deployment posture in place) → tag `review-w2`.
