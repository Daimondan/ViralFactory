# Architect Review — review-w1 (M1 complete, pre-M2)

*Repo location: `docs/reviews/review-w1.md` · Claude architect · 2026-07-02 · Reviewed at commit cf1050d ("M1 complete: PROGRESS.md updated, 92 tests passing")*

**Verdict: M1 approved with corrections. Items R1–R5 must land before any M2 task begins. R6–R8 land during M2. The suite (92 tests) was run by the architect and passes.**

M1 is solid work. The generic runner is genuinely generic, no business values leaked into `src/`, the validator enforces evidence, and the materials intake preserves dialect. The corrections below are not redesigns — they are defects against acceptance criteria already agreed.

---

## R1 — MUST FIX — Gate bypass in `/api/run/<id>/store-voice` (charter violation)

`src/app.py` `store_voice()` calls `ModuleStore.store()` unconditionally, then checks `approved` only to set run status. A parked or rejected profile is still written to `modules/{slug}/voice-profile.md`.

This violates T1.4 AC ("v1.0 stored with provenance only on confirmation") and the charter rule that modules are written only via the gate.

**Fix:** move the `store.store()` call inside `if approved:`. On park/reject, the profile remains only in `playbook_runs.llm_outputs` (run state), nothing touches `modules/`. Add a test: POST with `approved: false` → assert the module file does not exist.

## R2 — MUST FIX — Provenance log is not append-only

`src/provenance.py`: the table declares `UNIQUE(input_hash, prompt_file, prompt_version, model)` and `log()` uses `INSERT OR REPLACE`. Consequences:

- A cache hit logs `raw_output="(cached)"` and **replaces** the original row containing the real raw output.
- A retry replaces the row for the first attempt.
- Any repeated call erases prior history.

An audit trail must be append-only. **Fix:** drop the UNIQUE constraint (migration or fresh-DB recreate — DB is dev-only, recreate is fine), change to plain `INSERT`. Add a test: same call twice → two rows, original raw output intact.

## R3 — MUST FIX — First failed validation attempt is never logged

`src/llm_adapter.py` `complete()`: when attempt 1 fails validation and attempt 2 succeeds, only the success is logged. The failed raw output vanishes. Guardrail: *every* LLM call logged.

**Fix:** log a `verdict="invalid"` row for the failed attempt before retrying. Test: mock invalid-then-valid → assert two provenance rows.

## R4 — MUST FIX — Adapter untested against real backend; Ollama Cloud auth missing

- `_call_ollama()` sends no `Authorization` header. Ollama Cloud requires an API key. The default backend will 401 in production.
- `config/models.yaml` `base_url` points to a Cloudflare URL containing what appears to be an account/gateway ID, which does not match the `/api/chat` path the adapter constructs. Verify this is the intended endpoint; if the ID is account-identifying, move it to an env var referenced from config.
- All 92 tests mock the LLM. That is correct for the suite, but M1 cannot be called done without one live round-trip.

**Fix:** read API key from env (e.g. `OLLAMA_API_KEY`), send `Authorization: Bearer` when present; correct `base_url`; run one real smoke call (`prompts/voice_profile/analyze_v1.md` with a tiny corpus) and paste the provenance row ID into PROGRESS.md as evidence.

## R5 — MUST FIX — WhatsApp export detection fails on 24-hour and iOS formats

`src/materials.py`: `_is_whatsapp_export()` and `normalize_whatsapp()` require `[AP]M`. Real-world failures:

- Android non-US locale (incl. Barbados): `31/12/2023, 23:45 - Name: msg` — 24-hour, no AM/PM → not detected → treated as plain text → **other parties' messages are NOT stripped** → contaminated voice corpus.
- iOS: `[31/12/2023, 11:45:23 PM] Name: msg` — seconds present → regex fails.

**Fix:** widen the pattern to optional seconds and optional AM/PM (24-hour accepted). Add fixtures for all three formats (US 12h, non-US 24h Android, iOS with seconds) asserting other-party stripping in each. The operator's own phone export is the real acceptance test.

## R6 — M2 SCOPE — Audio transcription (T1.2 AC not met)

Audio files are stored with a "transcription pending" stub. T1.2 AC said "audio (transcribed) all ingest." Speaking materials/seeds is core to the operator's workflow and T3.1 depends on it.

**Decision required (divergence file if re-scoped):** implement now via local Whisper (faster-whisper on the VPS; model name in `config/models.yaml` under a `transcription` block — no hardcoding), OR formally defer to T3.1 with a divergence entry. Recommendation: implement in M2 — the operator's end-to-end test should include a spoken sample.

## R7 — M2 SCOPE — Module store gate enforcement moves from honor-system to enforced

`ModuleStore.store()` currently trusts the caller ("should only be called AFTER gate approval"). This is acknowledged as T2.5. Note that R1 shows the honor system already failed once. T2.5 AC stands: silent edit impossible via API — recommend `store()` require a `gate_token`/approval record ID that it verifies against the runs table before writing.

## R8 — MINOR (fix opportunistically during M2)

- `materials._update_field()` interpolates the column name via f-string. Callers are internal today; restrict with an allowlist of column names to keep it that way.
- `llm_adapter._render_prompt()` does sequential `str.replace`; a variable value containing `{other_key}` gets double-substituted. Use a single-pass regex substitution over `\{(\w+)\}`.

## R9 — M2 SCOPE — Forward-compatibility for multi-tenant AI (do NOT build BYO now)

Context: an open product question is whether future customers run on the operator's Ollama subscription (bundled) or bring their own model/keys (BYO). That decision is deferred to M7 per charter — **do not build per-tenant credentials, per-tenant model config, or key storage now.** Two cheap hooks land in M2 so neither option requires surgery later:

1. **Provenance gains `business_slug`** — add the column (DB is dev-only; recreate is fine) and thread it through `LLMAdapter.complete()` and `ProvenanceLog.log()`. Every call is attributable to a tenant from day one, which is required for cost metering under bundled pricing and harmless under BYO. Callers in `src/app.py` already load the business config; pass the slug.
2. **Backend selection stays funneled** — the adapter's `backend` parameter remains the ONLY mechanism by which any code selects a model. No route, playbook step, or job may reference a model name directly. This keeps "tenant-scoped backend resolution" a future config-lookup change, not a refactor. Add a guardrail note to BUILD_PLAN if not already implied by "no model names in code."

---

## Process corrections

1. **PROGRESS.md header is stale** — says "M0 complete, ready for M1" while the table shows M1 done. The header must be updated in the same commit as the milestone claim. Also add T1.4/T1.5 lines to "What's Done."
2. **No tag exists in the repo.** BUILD_PLAN requires `review-w3` at the M1 checkpoint; PROGRESS says "tag review-w1." Convention ruling: tags are `review-wN` where N increments per review, independent of the estimated week — so this review is `review-w1`. Tag commit cf1050d as `review-w1` after landing R1–R5, BUILD_PLAN's "review-w3" reference updated to match.
3. BUILD_PLAN checkboxes for completed M0/M1 tasks are still unchecked. Check them.

---

## M2 acceptance checkpoint (operator end-to-end test)

M2 is done when the operator (user #1) completes this, through the console only, zero code edits:

1. Business Profile intake → `business.yaml` re-entered via console + `brand-context.md` module exists.
2. Voice material uploaded: at least one real WhatsApp export from the operator's phone (R5 proof), one pasted sample, one spoken sample (R6 decision applies).
3. Sources Engine Part A: operator provides 10–30 real seed sources + 3–5 anti-examples → Source Criteria module generated with per-criterion evidence → operator edits criteria at the gate → `sources.yaml` populated. Nothing hardcoded.
4. Remaining playbooks (Viral Patterns, Audience, Story, Format, Visual) each produce a schema-valid v1 module through runner + gate.
5. All modules visible in the library with version history; a parked module verifiably does NOT exist on disk (R1 proof).
6. Tag `review-w2`.

Out of scope for this test (do not attempt, set operator expectations): publishing/IG/X (M4 via Postiz), continuous source discovery and the yes/no/park source-addition queue (Part B, M6), async proposal queue (M5).
