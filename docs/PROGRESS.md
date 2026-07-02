# Build Progress — ViralFactory

> **Living document.** Updated every time a stage is started, completed,
> blocked, or changed. Any agent should be able to read this and know
> exactly where we are.

**Last Updated:** 2026-07-02
**Current Phase:** M3 complete (T3.1–T3.12). 310 tests passing. Co-production loop fully built: idea cards, Ideas gate, awaiting-capture, drafter, human pass, assets, per-platform gate, publish handoff, series spawning, experimental format debut, origin threading. M2 audio/voice tasks (T2.6–T2.8) still deferred.
**Operator review URL (Tailscale):** http://100.96.184.48:9121
**Public URL (vf.glenbeu.com):** Basicauth middleware live. DNS A record pending operator creation. Credentials: user `daimon`, password set by operator in `/docker/traefik/dynamic/vf-users.txt`.

---

## Overall Status

| Stage | Status | Notes |
|---|---|---|
| 0. Foundation | ✅ | All T0.1–T0.7 done. 28 tests passing. Real config verified. Pushed. |
| 1. Onboarding engine: Voice Profile | ✅ | T1.1–T1.5 all done. 92 tests. Runner, intake, analysis, calibration, interview fallback. |
| 2. Remaining playbooks wired | 🔧 | All playbooks done (T2.1–T2.4) + gate enforcement (T2.9) + schema-check (T2.5) + security fixes (T2.10) + provenance business_slug (T2.11) + gate step derivation (R15). 254 tests. T2.6–T2.8 (audio/voice) **deferred after operator UI review** (architect batch C). Deployed: Tailscale URL live, basicauth on public route. |
| 3. Co-production loop | ✅ | T3.1–T3.12 all done. Idea cards, Ideas gate, awaiting-capture, drafter, human pass (chips+direct edit), assets fan-out, Gate 3, publish handoff, series spawning, experimental format debut, origin/format/scope threading. 310 tests. |
| 4. Publish + metrics automation | ⬜ | Postiz self-hosted confirmed. |
| 5. Inward learning loop | ⬜ | Async gate queue (superseding, age, no pressure). |
| 6. Outward research loop | ⬜ | Continuous from v1 of this phase. |
| 7. Generalization proof | ⬜ | Real near-term but not blocking v1. |

## What's Done
- [x] Repo created: https://github.com/Daimondan/ViralFactory (public — deliberate, so architect can read without auth)
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

- [x] T1.4: Calibration gate UI + store-voice API (11 tests)
  - Calibration page: presents 3 voice samples, approve/park/reject controls
  - store-voice API: writes module only on approval (R1 fix: gate enforced)
  - Version history: v1.0 on approve, v0.9 on 3-round fallback, archived versions visible

- [x] T1.5: Interview fallback — guided Q&A for users with no materials (7 tests)
  - 5-question guided interview produces a synthetic corpus
  - Flask API + interview UI page

- [x] Review-w1 corrections (R1–R5): gate bypass fix, provenance append-only,
  failed-attempt logging, Ollama auth + base_url, WhatsApp 24h/iOS format support (9 new tests, 101 total)
- [x] R4 live smoke test: real Ollama Cloud round-trip, model=gpt-oss:120b, latency=27.9s, provenance row #1, verdict=valid

## What's Next
- [x] Tag review-w1 (exists at commit d24c0c5)
- [x] Review-w2 interim review corrections R10–R16 applied (R10: repo public decision, R11: v2 import server-side switch, R12: tenant strings in templates/prompts, R13: T2.9 pulled forward, R14: config archiving, R15: queued, R16: VPS constraint on T2.6–T2.8)
- [x] T2.1: Business Profile intake — Q&A UI, AI analysis prompt, schema, gate enforcement, business.yaml + brand-context module (15 new tests, 116 total)
- [x] T2.2: Sources Engine Part A — seed sources + anti-examples → AI criteria → sources.yaml + source-criteria module; v2 bulk-import path (server-side env var switch) (17 new tests, 133 total)
- [x] T2.9: Gate-token enforcement — all write paths (ModuleStore.store, business.yaml, sources.yaml) require verified gate token from approved run (12 new tests, 154 total)
- [x] T2.3: Viral Patterns + Audience Insights + Story Frameworks + Format Guide playbooks — 4 prompt templates, 4 schemas, 4 markdown converters, 4 sets of API endpoints (input + analyze + store), 4 HTML intake pages, Format Guide with AMENDMENT-004 enrichment (requires_human_capture, effort_level, best_for, platforms, reuse_pathways, status, provenance), 47 new tests, 201 total
- [x] R15: Gate step numbers derived from parsed playbook — parser now handles numbered-list format (N. Description) in addition to ### Step N format; get_gate_step_number() replaces all hardcoded gate step strings in 7 store endpoints; create_app() defaults to absolute playbooks path (16 new tests, 217 total)
- [x] T2.4: Visual Style intake + shot-library index — 2 prompt templates (item indexing + style guide analysis), VISUAL_STYLE_SCHEMA + SHOT_LIBRARY_ITEM_SCHEMA, 2 markdown converters, 5 API endpoints (shot-library item, visual-style input, index-shot-library, analyze-visual-style, store-visual-style), HTML intake page with palette swatches + shot library display, gate-enforced writes both visual-style + shot-library modules (23 new tests, 240 total)
- [x] T2.5: Module store schema-check on load + version history visible in console (14 new tests, 254 total)
- [x] T2.10: Security fixes — materials._update_field() column allowlist + llm_adapter._render_prompt() single-pass substitution
- [x] T2.11: Provenance gains business_slug — column added, threaded through LLMAdapter.complete() and ProvenanceLog.log()
- [x] R15: Gate step numbers derived from parsed playbook
- [x] Deployment: Gunicorn + systemd + Traefik with basicauth middleware. Tailscale URL live for operator review.
- [ ] T2.6–T2.8 (audio/voice): **DEFERRED — resequenced after operator UI review per architect batch C directive.** review-w2 must NOT be tagged until these land. Operator end-to-end test may run without speak-a-sample path; full test re-runs when audio lands.
- [ ] After UI review: T2.6 (faster-whisper transcription) → T2.8 (voice samples) → T2.7 (voice cloning smoke test) → operator end-to-end test → tag review-w2