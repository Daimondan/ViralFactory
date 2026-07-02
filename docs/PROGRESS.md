# Build Progress — ViralFactory

> **Living document.** Updated every time a stage is started, completed,
> blocked, or changed. Any agent should be able to read this and know
> exactly where we are.

**Last Updated:** 2026-07-02
**Current Phase:** M0 — Foundations complete. Ready for M1 (Onboarding engine).

---

## Overall Status

| Stage | Status | Notes |
|---|---|---|
| 0. Foundation | ✅ | All T0.1–T0.7 done. 28 tests passing. Real config verified. Pushed. |
| 1. Onboarding engine: Voice Profile | 🔄 | T1.1 done. T1.2 done. T1.3 done (schema+store+prompts). T1.4–T1.5 next. |
| 2. Remaining playbooks wired | ⬜ | Playbooks split. Awaits M1. |
| 3. Co-production loop | ⬜ | Direct-edit mode in BUILD_PLAN (T3.3). Drafter A/B at checkpoint. |
| 4. Publish + metrics automation | ⬜ | Postiz self-hosted confirmed. |
| 5. Inward learning loop | ⬜ | Async gate queue (superseding, age, no pressure). |
| 6. Outward research loop | ⬜ | Continuous from v1 of this phase. |
| 7. Generalization proof | ⬜ | Real near-term but not blocking v1. |

## What's Done
- [x] Repo created: https://github.com/Daimondan/ViralFactory (private)
- [x] Charter v3 grilled and amended (5 divergences → DIVERGENCE-001)
- [x] Claude architect reviewed all 5 divergences — all APPROVED
- [x] Charter v3.1 in place. BUILD_PLAN v1.1. UI-DIRECTION v1.1. CONTEXT.md patched.
- [x] DIVERGENCE-002: ViralFactory fully standalone, no OB1 dependency
- [x] 8 playbooks split into individual files in playbooks/
- [x] T0.7: v2 database backed up to /home/daimon/v2-backups/ (6.3MB, 1531 sources, verified restore)
- [x] T0.1: Repo layout verified — config/, prompts/, playbooks/, modules/, src/, tests/, docs/
- [x] T0.2: Config loader — business.yaml, models.yaml, sources.yaml with schema validation (8 tests)
- [x] T0.3: LLM adapter — complete(prompt_file, variables, schema) → validated JSON, Ollama Cloud/OpenAI-compatible, retry-once
- [x] T0.4: Validator — JSON-schema + allowlist, nested validation, unknown tag rejected (8 tests)
- [x] T0.5: Provenance log — SQLite, every call writes input_hash + prompt + model + output + verdict (3 tests)
- [x] T0.6: Content-hash cache — SHA-256, same input twice = one call, deterministic (4 tests)
- [x] 28 tests all passing, real StackPenni config files verified
- [x] T1.1: Generic playbook runner — parser + runner + Flask console (15 tests)
  - PlaybookParser parses markdown into structured Playbook object
  - PlaybookRunner persists state to SQLite (start, input, LLM output, gate, complete)
  - Flask app: dashboard, onboard, playbook run pages, API endpoints, health check
  - Proven generic: trivial test playbook run end-to-end (parse → start → input → gate → done)
  - Real voice-profile-builder.md parses correctly (7 steps, intake + gate identified)
  - 6 web integration tests (Flask test client + real config)

- [x] T1.2: Materials intake — WhatsApp export, plain text, audio, paste with normalization (14 tests)
  - WhatsApp: strips other parties' messages, preserves user's multi-line messages
  - Text: strips email sigs, forwarded headers, >quotes; preserves dialect (tested Bajan)
  - Audio: stores metadata, marks for transcription
  - Corpus: word count, sample listing, run-scoped retrieval
  - Flask API + intake UI with live corpus display

- [x] T1.3: Voice Profile schema + module store + prompt templates (17 tests)
  - VOICE_PROFILE_SCHEMA: validates identity, patterns with evidence, dialect with do_not_sanitize
  - Validator upgrade: array items now enforce required fields + property types (evidence enforcement)
  - voice_profile_to_markdown: JSON → fixed markdown schema (drafter-ready)
  - ModuleStore: versioned storage, auto-archive, provenance, list/search
  - Prompt templates: analyze_v1.md (corpus → profile) + calibrate_v1.md (profile → 3 samples)
  - Flask API: POST /api/run/<id>/analyze-voice

## What's Next
- [ ] T1.4: Calibration gate UI — 3 samples, pick + react, revise loop
- [ ] T1.5: Interview fallback — guided Q&A produces corpus from nothing