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
| 0. Foundation | ✅ | All T0.1–T0.7 done. 23 tests passing. Real config verified. Pushed. |
| 1. Onboarding engine: Voice Profile | ⬜ Next | 8 playbooks ready. Needs playbook runner + prompt templates. |
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
- [x] 23 tests all passing, real StackPenni config files verified

## What's Next
- [ ] M1: Playbook runner (T1.1) — generic, executes markdown procedures as console flows
- [ ] M1: Materials intake UI (T1.2)
- [ ] M1: Voice Profile playbook end-to-end (T1.3)
- [ ] Tag review-w1 when M0 is confirmed stable after Claude review