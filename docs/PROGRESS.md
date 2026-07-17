# Build Progress — ViralFactory

> **Living document.** Updated every time a stage is started, completed,
> blocked, or changed. Any agent should be able to read this and know
> exactly where we are.

**Last Updated:** 2026-07-17
**Current Phase:** Assembler Full Upgrade — Phase 5 COMPLETE. VF-AU-501 through VF-AU-503 done. 1,307 tests passing. Next: Phase 6 (real proof + closeout) — VF-AU-601 through VF-AU-603.
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
| 4. Publish + metrics automation | ✅ | T4.1 Postiz adapter + API wiring. T4.2 Metrics collection + nightly cron. 471 tests. Postiz not yet installed on VPS — adapter ready. |
| 5. Inward learning loop | ✅ | T5.1–T5.3 done. Proposal store, weekly proposal cron, gate queue UI, superseding, bulk approve/reject, Voice Profile update path. 492 tests. |
| 6. Outward research loop | ⬜ | Continuous from v1 of this phase. |
| 7. Generalization proof | ⬜ | Real near-term but not blocking v1. |

## What's Done
- [x] 2026-07-17: VF-AU-003 — DIVERGENCE-013 APPROVED WITH CONDITIONS via AMENDMENT-009. Charter v3.5 → v3.6. Seven binding conditions: (1) capture policy approved with treatment at Gate 1, (2) capture_required blocks compliance not drafting, (3) legacy capture tasks not silently migrated, (4) hash-lock covers full Writer contract, (5) Media Planner translates intent not redefines it, (6) playbook_type metadata required and enforced, (7) process changes remain versioned and human-gated. All cross-references updated: CONTEXT, BUILD_PLAN, README, PROGRESS, CHANGELOG. M12 milestone added to BUILD_PLAN with 30 tasks.
- [x] 2026-07-17: VF-AU-001 — Baseline audit complete. All 10 drift claims from handoff verified against live code. 10/10 confirmed. Classification: 7 implementation compliance, 1 design change, 2 schema enrichment. 1,084 tests collected. Document at docs/reviews/ASSEMBLER-UPGRADE-BASELINE.md.
- [x] 2026-07-17: VF-AU-002 — DIVERGENCE-013 filed. Three boundary refinements: (A) capture semantics split, (B) Writer/Media Planner prompt ownership, (C) production playbook classification. Decisions D+E already ratified via AMENDMENT-008. Status: PENDING.
- [x] 2026-07-17: P0 — Committed all working-tree artifacts (11 modified + 2 untracked docs) to establish clean baseline before Assembler Full Upgrade Phase 0. 1,084 tests passing. Viral-patterns module v3.0 → v3.1 with five operator amendments: corpus-bias caveat (borrowed authority), StackPenni-accessible patterns note, polarization house rule near never-list, comment-ratio performance hypothesis, cross-tab contrast-set note in next-evidence-pass. Production playbook v1 amended with derived_ratios block in performance record schema and comment-ratio-based action validation in Analyst spec. Meta-analysis v2 amended with cross-tab contrast-set opportunity note.
- [x] 2026-07-11: Replaced deterministic format routing with affordance-based Format Guide v2. Idea generation now separates locked concepts from treatment selection, supports explicit open/platform/exact user constraints, chooses one primary destination, and treats cross-platform derivatives as optional. Migrated StackPenni guide, persisted structured JSON, left architect note, ran two real LLM experiments, and restarted the live service. 1,015 tests passing.
- [x] 2026-07-11: DIVERGENCE-012 RATIFIED via AMENDMENT-008. Charter v3.4 → v3.5. Architect approved final-output compliance contract + bounded remediation loop (max 3 rounds). Three conditions: (1) text-boundary firewall (SHA-256 hash lock on `platform_content`), (2) config-driven cost guard (`max_remediation_cost_usd`), (3) operator visibility (full remediation history in Assets UI). Retires keyword-based VO detection as compliance decision. Builder may implement.
- [x] 2026-07-11: Fixed VO extraction from JSON-encoded reel posts. The old parser swallowed frame labels and visual directions into TTS; real asset #2 now extracts only its five spoken lines (198 words). Added the production-shape regression test; 912 tests passing. Script/timeline completeness remains tracked in proposed DIVERGENCE-012.
- [x] 2026-07-10: Fixed a full-suite tenant-string regression in generic VO generation. `src/vo_generator.py` no longer supplies a tenant dialect as a fallback; an omitted style produces a neutral TTS instruction while the configured business style remains authoritative. 911 tests passing.
- [x] 2026-07-07: Fixed Assembler asset #1 wrong-video class. Edit plans now use only asset-scoped generated media and the idea card's own capture uploads; missing required visuals return `missing_media` instead of letting the LLM choose unrelated uploads. Stock missing-media results are registered as asset media. Reels without final cuts cannot be approved. 779 tests passing.
- [x] 2026-07-04: AI tells + voice deepening correction applied. Added `prompts/shared/ai_tells_v1.md`, loaded into `draft/generate_v3.md`, moved voice upstream into `ideas/generate_v1.md`, added cognitive Voice Profile dimensions to prompt + playbook, fixed T9.5 self-audit no-op so `fix_applied` changes real `platform_content`, restored full module context during AI-review revisions, and added 3 regression tests. 761 tests passing.
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
- [x] P0 FIX: duplicate `const playbookName` in session.html killed all JS (attach/send/gate buttons dead). Fixed + JS parse smoke test added (CORRECTION-onboarding-single-thread-v1.0 Item 1). 320 tests total.
- [ ] P1 REDESIGN: single-thread onboarding — one conversation, not eight chats (CORRECTION-onboarding-single-thread-v1.0 Item 2). GitHub issue #2. Scheduled for next review tag.
- [x] Session memory & materials fixes (CORRECTION-session-memory-and-materials-v1.1): F3 tail-slice + 12k budget, F1 file note in transcript, F2a materials in converse prompt, F2b docx extraction, F2c mp4/opus/aac/flac as audio, F5 anti-repeat guard. 347 tests total.
- [ ] F4: replace parallel-array transcript with single turn log (P1, deferred).
- [ ] F2c: audio transcription implementation — blocked on DIVERGENCE-005 (operator decision: faster-whisper vs hosted API).
- [x] Onboarding Orchestrator: single-thread onboarding — one conversation feeds all 8 playbooks. Coverage map, inline drafting, gate cards in chat, progress rail. 357 tests total.
### 2026-07-03 — Applied CORRECTION-orchestrator-drafting-and-ux-v1.0 (P0-1 through P2-2 + transcription)

**Tasks completed:**
- P0-1: Drafting input starvation root cause fix (routed seeds persisted, per-doc drafting package, 8 v2 prompts, shot_library_summary, placeholder check)
- P0-2: Validation crash on next_focus null (schema, validator, retry, error copy)
- P1-1: Gate relocation to Library (draft-status modules, Library UI with approve/edit)
- P2-1: Conversational latency (converse backend in models.yaml)
- P2-2: Orchestrator prompt v2 (agency-intake posture)
- Transcription worker (faster-whisper daemon, transcription_status column, backfill)
- Inbox batch 2026-07-03 filed (3 documents processed)
- Definition of Done process added to CONTEXT.md
- 375 tests passing (18 new regression tests for P0-1/P0-2)

**Awaiting subagents:**
- P1-2: Conversation continuity (template changes)
- P1-4: Upload feedback (template changes)
- P1-3: Readback/message rendering (per-schema formatters)


### 2026-07-03 — Inbox batch -c + -d filed (pipeline UX, voice cloning, final assembly)

5 files filed: 2 corrections to `docs/reviews/`, 1 decision to `docs/decisions/`, 2 manifests to `docs/inbox/processed/`. Inbox empty. Scope: F1–F5 (busy states, jobs table, audit flags, visual direction, media gen via OpenRouter, publish preview), voice cloning (Chatterbox, voice reference set, VO flow), final assembly (Edit Plan schema + FFmpeg renderer + stock library + Materials Library). Build order per manifest -c note 1. New deps: OPENROUTER/PEXELS/PIXABAY keys, chatterbox-tts, moviepy v2, ffmpeg. Two operator-eared gates: cloned-voice listening test, publish-preview judgment. No charter conflicts.

### 2026-07-03 — Materials Library built (CORRECTION-final-assembly Part 2)

Materials Library — editable source materials. DB migrations: `excluded` column + `material_edits` table. Methods: `save_edit()`, `restore_to_raw()`, `toggle_exclude()`, `get_edit_history()`. `get_corpus` respects `excluded` flag. Flask routes: `/materials` (list + filters), `/materials/<id>` (detail), `/api/materials/<id>/edit|exclude|restore`. Templates: materials.html, material_detail.html, error.html. `raw_content` never modified — all edits write to `normalized_content` only. 19 new tests (394 total). Live server verified: edit/restore/exclude all work via curl against real data. Build order per manifest -c note 1: this is item 1 (independent, small).


### 2026-07-03 — Pipeline UX + Media Generation + Final Assembly built (CORRECTION-pipeline-ux + CORRECTION-final-assembly)

**Completed:**
- F1: Jobs table (`src/jobs.py`) + shared `static/busy.js` — idempotency guard on all expensive endpoints (draft generate, fan-out, ideas generate, media generation, edit plan, render). Duplicate concurrent calls return 409, no second LLM/media call fires. Stale job detection + dead marking.
- F2: Self-audit flags actionable — Apply replaces flagged line in draft_text with suggestion, records as direct_edit (highest weight), bumps version. Dismiss records for voice-profile signal. "Apply all remaining" button. `POST /api/draft/<id>/audit-flag` endpoint. State persists with draft.
- F3: Visual direction elevated to required deliverable — `minItems: 1` on `image_prompts` + `shot_format_choices` in DRAFT_SCHEMA. Validator gains `minItems` support. Prompt v2 (`generate_v2.md`) with concrete, generation-ready image prompt requirements. Template always renders visual direction section (empty → "regenerate to produce one").
- F4: Media adapter (`src/media_adapter.py`) — OpenRouter Image + Video API integration. Config-driven model selection (`models.yaml` media block). Content-hash caching for images. Provenance logging with USD cost. `asset_media` table. Image generation synchronous-ish, video async (submit → poll → download). "Generate visuals" per asset, video generation with explicit cost confirmation dialog. Media served via `/media/<path>`. Fan-out failure surfacing fixed (no more silent `continue`).
- F5: Assets page rebuilt as publish preview — platform-specific preview cards with correct aspect-ratio media frames (9:16, 1:1, 16:9), generated images/video displayed in-frame, caption/copy below media, character count against platform limit, handle label. Gate 3 controls on the preview. Video cost confirmation dialog. `from_json` Jinja filter registered.
- Final Assembly Part 1: `EDIT_PLAN_SCHEMA` in pipeline.py. `prompts/assembly/edit_plan_v1.md` prompt. `src/assembly.py` — deterministic FFmpeg-based renderer (trim, concat, transitions, burn-in captions infrastructure). Readable cut list for operator review. `edit_plans` table in DB. `src/stock_adapter.py` — Pexels + Pixabay search + download + cache. Routes: `POST /api/assets/<id>/edit-plan`, `GET /api/assets/<id>/edit-plans`, `POST /api/assets/<id>/render`, `POST /api/stock/search`.

**New files:** `src/jobs.py`, `src/media_adapter.py`, `src/stock_adapter.py`, `src/assembly.py`, `src/static/busy.js`, `prompts/draft/generate_v2.md`, `prompts/assembly/edit_plan_v1.md`, `tests/test_pipeline_ux_and_assembly.py`
**New config:** `media` + `stock` blocks in `config/models.yaml`
**New deps needed:** `OPENROUTER_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY` env vars. ffmpeg already installed.
**Tests:** 440 passing (46 new). 0 failures.
**Service:** Restarted, health OK. All new routes verified live via curl.

**Awaiting operator:**
- Set `OPENROUTER_API_KEY` env var for media generation to work end-to-end
- Set `PEXELS_API_KEY` + `PIXABAY_API_KEY` for stock library
- Human UI test of publish preview at desktop + mobile widths
- Cloned-voice listening test (voice decision, criterion 4) — deferred to voice reference set build

**Completed (9 of 10 items):**
- P0-1: Drafting input starvation root cause fix
- P0-2: Validation crash on next_focus null
- P1-1: Gate relocation to Library (draft-status modules)
- P1-2: Conversation continuity (render history on load, back link, auto-save, draft acknowledgments)
- P1-3: Readback rendering (no raw dict text, omit empty sections)
- P1-4: Upload feedback (uploading indicator, error chip, never add failed to pendingFiles)
- P2-1: Conversational latency (converse backend)
- P2-2: Orchestrator prompt v2 (agency-intake posture)
- Transcription worker (faster-whisper daemon, transcription_status column, backfill)

**Pending:**
- End-to-end acceptance test (needs browser + real LLM calls — operator should run this)

**Test suite:** 375 tests passing, 0 failures. 18 new regression tests for P0-1/P0-2.
**Service:** Restarted, health check OK at 127.0.0.1:9121.
**UI checks (curl-based):** Onboarding page renders conversation history, back link, auto-save notice, draft acknowledgments, upload states. Library page shows status badges, approve/edit buttons, module cards.

### 2026-07-03 — M8 started: T8.1 + T8.2 (P0) done

**T8.1 — Kill remaining truncation:**
- Removed `source_material[:4000]` in `ideas_generate` — full source_material passed to ideas prompt (snapshot builder already has count bounds)
- Replaced `SNAPSHOT_CHAR_CAP = 4000` with `MAX_SNAPSHOT_ITEMS = 40` in `source_snapshot.py` — count-bounded, not character-sliced
- `build_snapshot_text` now takes most recent N items across all feeds, each with full summary (already bounded by `SUMMARY_CHAR_LIMIT`)
- New test: `test_build_snapshot_text_count_bounded` (6 feeds × 10 items = 60, capped to 40)

**T8.2 — Housekeeping:**
- Removed dead `response_data` block in `ideas_gate_decision` (series branch) — was built but never used; actual response built at line 4164 as `response`
- CONTEXT.md updated: Idea card definition now includes `source_refs` + auto-production trigger; new AI Profiles section; Core Loop diagram updated with auto-chain
- CONTEXT.md "Updated" date bumped

**Tests:** 584 passing (1 new). 0 failures.

### 2026-07-03 — T8.3 Source Bank table done (P1)

**T8.3 — Source Bank as addressable store:**
- New `sources` table in `pipeline.py` schema: id, business_slug, source_type, title, url, summary, content, origin, first_seen, content_hash, status
- `source_snapshot.py` now takes `business_slug` param, writes fetched items into `sources` as `source_type='rss_item'` (deduped on URL-hash), extracts full content via trafilatura
- `materials.py` `_store()` registers `source_type='operator_material'` rows on text ingestion (deduped on content_hash), with `CREATE TABLE IF NOT EXISTS sources` in init
- PipelineStore methods: `add_source`, `get_source`, `list_sources`, `resolve_source_refs`, `archive_source`
- Schema migration: `source_refs` + `production_error` columns added to `idea_cards` (idempotent ALTER TABLE)
- `update_card_state` gains `production_error` param for T8.6 failure handling
- 20 new tests: schema, CRUD, dedupe, business_slug scoping, snapshot→sources, materials→sources

**Tests:** 604 passing (20 new). 0 failures.

### 2026-07-03 — T8.4 Idea cards carry source_refs done (P1)

**T8.4 — Idea cards carry source_refs:**
- `IDEA_CARD_SCHEMA` updated: `source_refs` (integer array, minItems=1) replaces `evidence_links` in required list; `source_notes` added (optional)
- `prompts/ideas/generate_v1.md` → v1.3: Source Bank section with `[S14] title — summary` format, cite-by-ID instructions, multi-source synthesis rule, new `source_criteria` variable
- `ideas_generate` route rebuilt: builds source digest from `sources` table (ID-prefixed), validates source_refs, derives evidence_links from resolved sources
- `_generate_card_from_seed` rebuilt: auto-registers seed as `manual` source, includes seed in source digest, ensures seed source always cited
- Ideas page template: renders resolved sources with title links + source_type badges (RSS=green, operator/manual=orange, scraped=blue, archival=gold)
- 15 new T8.4 tests; 3 existing test mock outputs updated from `evidence_links` → `source_refs`

**Tests:** 619 passing (15 new). 0 failures.

### 2026-07-03 — T8.5 Sources flow to production done (P1)

**T8.5 — Sources flow to production:**
- `prompts/draft/generate_v2.md` → v2.3: new `{grounding_sources}` section — full content of every cited source labeled with title + ID, explicit rule "facts, quotes, dates, statistics MUST come from these sources — do NOT fabricate specifics not present in them"
- `draft_generate` route: assembles `grounding_sources` by resolving `source_refs`; empty content degrades to summary with `(summary only)` marker (never silent)
- `prompts/assets/fan_out_v2.md` → v2.2: new `{source_titles}` section — titles only for attribution context, "do NOT re-write facts from these"
- `assets_fan_out` route: resolves source titles from card's `source_refs` and passes to fan-out prompt
- 10 new tests

### 2026-07-03 — T8.6 Auto-production chain done (P1)

**T8.6 — Auto-production chain:**
- New `src/produce_chain.py` module: `ProductionChain` class orchestrates draft generation → fan-out → (visual gen deferred to operator) in a background thread
- `ideas_gate_decision` on approve (no capture): enqueues `produce_chain` job, card state → `producing` → `asset_ready` (success) or `production_failed` (with error info)
- New `/api/ideas/<card_id>/retry-production` endpoint: retries chain from failed step (only if state=production_failed)
- Card schema gains `production_error` column (JSON: {step, error})
- `update_card_state` gains `production_error` parameter
- No-auto-publish absolute — chain terminates at asset review, no publish calls in produce_chain.py
- 8 new tests: state transitions, module import, enqueue thread, failure handling, retry endpoint, no-publish verification

### 2026-07-03 — T8.7 AI Profiles done (P1)

**T8.7 — AI Profiles:**
- New `config/profiles.yaml` with three profiles: Researcher (ideation, generative temp), Drafter (asset production, generative temp), Analyst (results analysis, judgment temp)
- `LLMAdapter.complete()` gains `profile` parameter — passed through to all `ProvenanceLog.log()` calls
- `ProvenanceLog.log()` gains `profile` parameter; provenance table gains `profile` column (idempotent migration)
- Pipeline LLM calls declare their profile: `ideas_generate` → `profile="researcher"`, `draft_generate` → `profile="drafter"`, `produce_chain._step_draft` → `profile="drafter"`
- 13 new tests: profiles.yaml existence + structure, provenance profile column, log with/without profile, adapter signature, pipeline calls

**Tests:** 650 passing (31 new across T8.5-T8.7). 0 failures.

### 2026-07-04 — Writer/Assembler UX overhaul + render crash fix (UI-REVIEW-003)

- Render crash fixed (_check_job_running stale_timeout_s forwarding)
- Writer page redesigned: unified card list + filter buttons with counts + provenance trail
- Assembler page split to /assemble route with its own unified list
- Redundant "Proceed to Assets" button removed — auto-redirect on ship
- Provenance trail (Idea → Script → Assets dots) on Writer, Assembler, draft, assets pages
- Render UX: background polling with status updates + /api/assets/<id>/render-status endpoint
- Nav links: /create#assembler → /assemble across all 29 templates
- Similar ideas root cause: source bank empty (2 junk sources, feeds: [], no seed sources) — operational gap
- **Tests:** 657 passing. 0 failures.

### 2026-07-04 — Source Bank page + seed source auto-extraction + DIVERGENCE-007

- Source Bank page (/sources) — filter buttons with counts, Keep/Park/Remove per source
- Source status API (/api/sources/<id>/status)
- Seed source auto-extraction from uploaded CSV/JSON materials (_extract_seed_sources_from_materials)
- Fixes root cause: Obsidian source uploads during onboarding now auto-populate seed_sources
- DIVERGENCE-007 filed: source review gate (new sources need human approval?) + source neural network (connections between sources for ideation)
- Source Bank nav link added across all 29 templates
- **Tests:** 661 passing. 0 failures.
- FIX: FFmpeg concat crash when source files are audio-only (WhatsApp voice memos saved as .mp4 with no video stream). Renderer now probes each source and synthesizes black video for audio-only sources, silent audio for video-only sources. 4 new regression tests. **Tests: 665 passing.**

### 2026-07-04 — Architect corrections applied (CORRECTION-jargon-timestamps-cleanup-v1.0 + DIVERGENCE-007 + DIVERGENCE-008)

**P1-1: Jargon cleanup** — Raw state strings (`asset_ready`, `assembling`, `awaiting_capture`, `writer_failed`, `production_failed`) no longer appear as visible text in operator-facing templates. State-label mappings added to `ideas.html`, `create.html`, `assemble.html`. All state badges show human-readable labels.

**P1-2: Relative timestamps** — `relative_time` Jinja filter added to `create_app()`. Cards on Ideas, Writer, and Assembler pages now show relative timestamps ("2 hours ago", "3 days ago") instead of raw ISO timestamps. `state_changed_at` field added to Writer/Assembler card dicts.

**P2-1: Config-driven platform fallback** — `produce_chain._resolve_format_platforms` no longer falls back to hardcoded `["X", "Instagram"]`. Falls back to business config's platform list (`config/business.yaml`). Charter-compliant — no business values in code.

**P2-2: Awaiting-capture deprecation** — Per AMENDMENT-006, `awaiting_capture` is deprecated as a blocking state. Removed separate "Awaiting" tab from Ideas page. Cards with `awaiting_capture` state now display under "Approved" tab with a "Manage capture" button (visible only when capture tasks exist). Removed `awaiting` from `state_map` in app.py. `pipeline.py` schema comment updated to note deprecation.

**P2-3: Postiz dead code removed** — `src/postiz_adapter.py` deleted. `cron_pull_metrics.py` updated to use `BufferAdapter`. `buffer_adapter.py` docstring updated to note backward-compat column name. No `postiz:` config block in `models.yaml`.

**DIVERGENCE-007 Item 1: Source review gate** — RSS sources now enter the Source Bank with `status='new'` (not `active`). Only `status='active'` sources feed idea generation. Dedup check now looks at any status (prevents re-adding reviewed/removed sources). Source Bank page (`/sources`) has "New" filter button with count, `st-new` CSS class for new badge, and bulk actions bar ("Keep all new →" / "Remove all new") with `/api/sources/bulk-status` endpoint. Operator materials still enter as `active` (intentionally created).

**Tests:** 711 passing (46 new). 0 failures. New test file: `tests/test_architect_corrections.py` (38 tests). Existing `test_t8_3_source_bank.py` updated for `status='new'` change.

### 2026-07-04 — DIVERGENCE-010 ratified via AMENDMENT-007 (Charter v3.4)

- DIVERGENCE-010 (originally filed as DIVERGENCE-009, renamed due to numbering collision with webhook DIVERGENCE-009) — architect APPROVED all 5 design changes:
  1. Format + platforms locked from treatment — no code re-derives them (removes `_determine_variant_type` keyword heuristic + `_resolve_format_platforms` regex parser — both charter violations)
  2. Writer produces complete per-platform text in one pass (DRAFT_SCHEMA gains `platform_content` array, replaces `draft_text`)
  3. Source Bank not loaded into draft prompt — confirmed no redundancy, no change needed
  4. AI review loop before Gate 2 — self-audit auto-fix + second-AI alignment check, max 3 rounds
  5. Assembler is media-only — no LLM text calls, `fan_out_v2.md` and `structure_v1.md` retired from Assembler path
- AMENDMENT-007 filed: `docs/decisions/AMENDMENT-007-writer-per-platform-assembler-media-only.md`
- Charter v3.3 → v3.4: `docs/CHARTER-v3.4.md`
- Charter v3.4 → v3.5: `docs/CHARTER-v3.5.md`

### 2026-07-04 — M9 implemented (T9.1–T9.6)

- T9.1: Removed `_determine_variant_type` keyword heuristic + `_resolve_format_platforms` regex parser from `produce_chain.py` and `app.py`. Replaced with mechanical parsers of Format Guide entry's structured `- **Platforms:**` and `- **Variant type:**` fields · Q: none
- T9.2: Added `variant_type` field to FORMAT_GUIDE_SCHEMA, `format_guide_to_markdown` converter, `analyze_v2.md` prompt (v2.1), and all 8 entries in `modules/stackpenni/format-guide.md` · Q: none
- T9.3: Writer produces per-platform content — DRAFT_SCHEMA replaces `draft_text` with `platform_content` array. New prompt `generate_v3.md`. Drafts table gains `platform_content`, `review_history`, `review_converged` columns. `draft.html` shows per-platform content · Q: none
- T9.4: Assembler is media-only — `_step_fanout` and `assets_fan_out` route rewritten to read `platform_content` directly and create assets with zero LLM text calls. `fan_out_v2.md` and `structure_v1.md` retired from Assembler path (files kept for provenance) · Q: none
- T9.5: AI review loop — new `alignment_check_v1.md` prompt + `ALIGNMENT_CHECK_SCHEMA`. Loop logic in `run_writer_chain`: self-audit auto-fix → alignment check → revise if issues, max 3 rounds. Card state: `writing → reviewing → draft_ready`. Review history shown in `draft.html` with convergence status · Q: none
- T9.6: All tests updated — 746 passed (726 baseline + 20 new) · Q: none
- BUILD_PLAN v1.5 → v1.6: M9 tasks added (T9.1-T9.6)
- CONTEXT.md updated: core loop diagram, idea card definition, business rules 13-15
- All `CHARTER-v3.3` references updated to `CHARTER-v3.4`
- All `CHARTER-v3.4` references updated to `CHARTER-v3.5` (AMENDMENT-008)
- DIVERGENCE-010 file renamed from DIVERGENCE-009-writer... to DIVERGENCE-010-writer...
- **Tests:** 711 passing. 0 failures. Q: none — builder to implement M9 tasks

### 2026-07-04 — Full UI review fixes (Writer/Assembler/platform_content)

- Fixed 15 operator-reported UI walkthrough issues: full single-post Reel scripts display on Draft review; Asset review reads approved scripts from `platform_content`; Story Series shows all frames/images; Researcher Generate button shows loading state; Writer/Assembler cards use 3-line titles; AI review notes no longer imply replacements; shipped drafts hide mutating self-audit controls; Reel video step starts at 1; asset card uses script excerpt instead of duplicate summary; capture reminders show on Asset review; Gate 3 keeps "Needs work" label with internal `fix` mapping documented.
- xAI media adapter wired for `video_provider: xai`, `/v1/videos/generations`, `request_id`, polling, and clear `XAI_API_KEY` errors.
- Attempted key copy from default Hermes env → `/home/daimon/.viralfactory.env`; blocker: `/home/daimon/.hermes/.env` does not contain `XAI_API_KEY`, so no secret was written.
- **Tests:** 758 passed via `pytest -q` (non-fatal worker cleanup message: `no such table: materials`) · Q: real `XAI_API_KEY` still needed in env for live xAI video.

### 2026-07-06 — FIX: variant_type mislabeling hid images on Assembler page

- Root cause: Writer prompt told the LLM to copy `variant_type` from the Format Guide entry's single `Variant type` field. For cross-platform formats like "Newsletter Section" (X→thread, Instagram→carousel), this produced `variant_type="newsletter_section"` for both — the format name, not the structural type.
- Impact: Assembler page classified both as `is_text_only` (because "newsletter" matched), hiding the Instagram carousel's 8 image prompts and the "Generate images" button behind a "Text-only format — ready for review" label. The X thread rendered as a newsletter mock instead of numbered tweets.
- Fix at 3 layers: (1) DB: corrected existing assets 1+2 to `thread`/`carousel` and updated draft `platform_content`. (2) Prompt: `generate_v3.md` v3.0→v3.1 — variant_type now described as per-platform structural type matching the posts array, not a copy of the Format Guide field. (3) Template: `assets.html` safety net — auto-detects thread/carousel from content description + platform + post count when variant_type is the format name; `is_text_only` now checks for active image prompts, so a newsletter with image prompts is not text-only.

### 2026-07-07 — FIX: ffmpeg concat "Invalid argument" on mismatched SAR

- Root cause: Image segments with different native aspect ratios produce different SAR (Sample Aspect Ratio) values after `scale+pad`. The ffmpeg concat filter requires all inputs to have matching SAR — mismatched SAR crashes with "Error while filtering: Invalid argument".
- Fix: Added `setsar=1` to the `-vf` chain in all four segment preparation branches (image, audio-only, video+audio, video-only) in `src/assembly.py`.
- Regression test: `test_render_concat_mismatched_sar_images` — wide (1280x720) + tall (720x1280) images concatenated, verifies SAR 1:1 output.
- **Tests:** 60 passing in assembly test file (was 59). 0 failures.

### 2026-07-09 — REVIEW: Video generation → assembly handoff audit

**Architect review filed:** `docs/reviews/REVIEW-video-generation-handoff-2026-07-09.md`
**Correction filed:** `docs/inbox/CORRECTION-video-generation-handoff-v1.0.md` (via `MANIFEST-2026-07-09-video-handoff.md`)

**Findings:** 5 P0 blocking bugs, 2 P1 defects, 2 P2 deficiencies.

- **P0-1:** `generate-clip` route reads `poll_result.get("path")` but `check_video_job()` returns `download_url`, not `path`. Video path is always `""`. Never calls `download_video()`. Poisons `asset_media` with empty paths.
- **P0-2:** `generate-media` route submits AI video jobs and walks away — no poll/download/register loop. Jobs float indefinitely.
- **P0-3:** Google/Veo sends `aspect_ratio.replace(":", "x")` → `"9x16"` instead of `"9:16"`.
- **P0-4:** Google/Veo response parsing misses a nesting level (`response.generatedSamples` vs `response.generateVideoResponse.generatedSamples`).
- **P0-5:** Google/Veo video download omits API key query param → downloads error blob, not MP4.
- **P1-1:** Duration hardcoded to 5 in both AI video paths — ignores LLM creative direction.
- **P1-2:** Google API key env var may be wrong (`GOOGLE_API_KEY` vs `GEMINI_API_KEY`).
- **P2-1:** VO info is a dead placeholder string — voice pipeline deferred.
- **P2-2:** FFmpeg stitcher ignores transitions, overlays, captions, audio plan (honest about it).
- **Additional:** Three 0-byte `final_*.mp4` files in `data/media/3/` — silent render failures not cleaned up.
- **DB state:** `asset_media` has 0 rows. No AI-generated video has ever been registered as an assembler ingredient.

**Correction tasks:** VH-1 through VH-6 in `docs/inbox/CORRECTION-video-generation-handoff-v1.0.md`.
**Status:** Blocking. The system can stitch files it has, but cannot reliably acquire AI-generated video files to stitch.

### 2026-07-10 — VH-1 through VH-6 applied (review-video-handoff-2026-07-09)

**Architect correction applied:** `docs/inbox/CORRECTION-video-generation-handoff-v1.0.md` (6 tasks)

**Completed:**
- [x] VH-1 (P0): `generate-clip` route now reads `download_url` from `check_video_job()` result, calls `download_video()` to download + register in `asset_media`, returns valid `ingredient_id` with real file path. No longer reads nonexistent `path` key or calls `_record_media` separately (which poisoned DB with path="").
- [x] VH-2 (P0): `generate-media` route now polls, downloads, and registers AI video jobs via `_poll_download_register_video()` helper. Both the direct `ai_video` path and the stock-fallback-to-AI path use it. Timeout returns `status="processing"` with `external_job_id` so the operator knows to check back.
- [x] VH-3 (P0): Google/Veo — 5 bugs fixed: (1) aspect ratio sent as-is `9:16` not `9x16`; (2) response parsing navigates `response.generateVideoResponse.generatedSamples` with shallow fallback; (3) `download_video()` appends `?key={api_key}` for Google download URLs + rejects <1KB files (error blobs); (4) API key env var checks both `GEMINI_API_KEY` and `GOOGLE_API_KEY`; (5) duration from plan_item (VH-5).
- [x] VH-4 (P1): Deleted 3 existing 0-byte `final_*.mp4` files from `data/media/3/`. Render route now checks output file size after FFmpeg — 0 bytes = job failed, file deleted, operator notified. No more false greens.
- [x] VH-5 (P1): Duration read from `plan_item.get("duration", 5)` in both AI video paths — no longer hardcoded to 5. LLM creative direction honored.
- [x] VH-6 (P2): CONTEXT.md "Current Render Capability" section updated with video generation handoff status.
- [x] `download_video()` return type changed from `str` to `dict {file_path, media_id}` so callers can construct `ingredient_id`.
- [x] `_summarize_media_generation_results` updated to track `processing_count` (timeout jobs).

**Review tag:** `review-video-handoff-2026-07-09`
**Tests:** 795 passing (16 new in `tests/test_video_handoff_vh.py`). 0 failures.

- [x] Edit plan source validator: post-LLM mechanical check rejects plans with hallucinated stock: IDs not in ingredient inventory. 4 tests. 812 total passing.
- [x] Orphaned media cleanup: removed 13 stale PNGs + old final cut from data/media/2/ (left by pipeline archive/reset). Generated 5 new images for asset 2 (biscuit tin reel). Rendered 18s final cut with valid edit plan (1 video + 5 images, no hallucinated sources).

### 2026-07-10 — Final Output Review Layer + Audio Bed Fix (correction-final-output-review-2026-07-10)

**Architect correction applied:** `docs/reviews/CORRECTION-final-output-review-and-audio-fix-v1.0.md` (8 tasks)

**Completed:**
- [x] AUDIO-1 (P0): Removed looping audio bed heuristic (lines 454–518 in assembly.py — charter violation: judgment in code). Replaced with plan-audio-block-driven mixing: renderer reads `plan["audio"]` and executes the LLM's strategy. Silent/original/music/VO strategies. 14 tests in `test_audio_strategy.py`.
- [x] AUDIO-2 (P0): Edit plan prompt bumped to v1.2 with Audio Strategy guidance section. LLM now told: no VO + no music → silent (better than nonsense); music available → use stock ref; renderer will NOT invent audio.
- [x] ASSET-REVIEW-1 (P0): Mechanical post-render checks via new `asset_review.py` module. ffprobe-based: file size, duration, stream presence, resolution, SAR. Duration mismatch > 2s flagged, missing/unexpected audio flagged, resolution mismatch flagged. Results saved to `asset_reviews` table + provenance. 15 tests.
- [x] ASSET-REVIEW-2 (P0): Vision-based visual inspection. Keyframes extracted at 20/40/60/80% + first frame via ffmpeg. Vision LLM (config-driven in `models.yaml` `asset_review` block) examines frames vs content. New prompt `asset_review_v1.md`. Graceful degradation when not configured. 10 tests.
- [x] ASSET-REVIEW-3 (P1): Audio inspection via faster-whisper transcription. Looping detection (same 5+ word phrase 3+ times → flagged). Unexpected audio when plan says silent → flagged. No speech when non-silent → flagged (catches ambient/looping). 12 tests.
- [x] ASSET-REVIEW-4 (P1): Content alignment aggregation. Combines mechanical + visual + audio into single advisory verdict: `ready_for_operator` / `needs_operator_decision` / `needs_rerender`. Pure aggregation, no LLM. 6 tests.
- [x] ASSET-REVIEW-5 (P0): UI integration. AI Review Summary panel below video player in assets.html. ✓/⚠/✗ indicators per check. Verdict badge. Expandable detailed review. Advisory only — does not block operator. CSS + JS parse tests pass.
- [x] ASSET-REVIEW-6 (P1): Image review. Lightweight vision check on standalone images: mechanical (file exists, size > 10KB) + visual (image vs prompt). 8 tests.
- [x] Config: `asset_review` block added to `config/models.yaml` (vision_model, max_keyframes, enabled — config-driven, swappable).

**New files:** `src/asset_review.py`, `prompts/assembly/asset_review_v1.md`, `tests/test_audio_strategy.py`, `tests/test_asset_review_mechanical.py`, `tests/test_asset_review_visual.py`, `tests/test_asset_review_audio_alignment.py`, `tests/test_asset_review_image.py`
**New DB table:** `asset_reviews`
**New API endpoints:** `/api/assets/<id>/reviews`
**Tests:** 69 new tests across 5 test files. All existing tests pass.
2026-07-11 · T10.1 · Compliance contract prompts + schemas + validators done (3 prompts, 3 schemas, domain validators, union+enum support in generic validator, 37 tests) · Q: none
2026-07-11 · T10.2 · Edit-plan record extension done (compliance_contract_json, source_draft_hash, review_round_history columns + append_review_round + get_compliance_contract methods, migration from old schema, 9 tests) · Q: none
2026-07-11 · T10.3 · Pre-render feasibility checks done (VO duration vs plan timeline, beat mapping, 92s/18s regression test caught, 19 tests) · Q: none
2026-07-11 · T10.4 · Final-output LLM compliance review done (run_compliance_review method, domain-specific validation, fallback on LLM failure, 6 tests) · Q: none
2026-07-11 · T10.5 · Bounded remediation loop done (text-boundary firewall, cost guard, max 3 rounds, 21 tests) · Q: none
2026-07-11 · T10.6 + T10.8 + T10.9 · State model extended, keyword heuristic retired, config cost cap added, existing tests updated for contract-based behavior · Q: none
2026-07-11 · OPS · Pipeline cleanup: wiped all idea_cards/drafts/assets/edit_plans/asset_media/jobs (150 rows total), deleted 7 old backup DBs (~1.8GB freed), VACUUM'd main DB, cleaned orphaned media files. Infrastructure preserved (sources, provenance, caches, materials). System ready for fresh video generation.
2026-07-11 · RESEARCH · Viral content mechanics research compiled: hooks, retention, emotional triggers, platform differences, MrBeast production analysis, AI tool landscape. Doc at docs/research/viral-content-mechanics-2026-07-11.md. Identifies 4-phase upgrade path: text overlays/captions → sound design → pacing/structure → format templates.
2026-07-11 · FEATURE · Text overlay burn-in + SFX mixing implemented in renderer. _burn_overlays() burns drawtext overlays with cumulative timeline positions, style presets (hook/default/highlight/title), config-driven font. _mix_sfx() generates synthetic tones (whoosh/pop/hit/riser) and mixes at correct positions. Edit plan prompt v1.4 mandates overlays + SFX + pacing. Viral patterns module v2.0 with research-backed patterns. 14 new tests, 1,040 total passing.
2026-07-14 · T11.1 · Sora retired (API discontinued 2026-09-24). models.yaml media block restructured per correction §5.2: image_generators (nano-banana-2, flux2-pro) with cost_per_image_usd + supports_reference_images, video_generators (kling-3, veo-3.1-fast) with cost_per_second_usd + mode + native_audio:false, music_generators (eleven-music). Legacy grok/veo kept as named backends. UI cost estimate now config-driven. media_plan_v1.md prompt updated. 1,042 tests passing · Q: none
2026-07-14 · T11.3 · Reference asset registry built: `reference_assets` DB table (schema per §2.1), `src/reference_assets.py` store module (propose→approve→retire lifecycle, version management, locked approved payloads), `/setup/reference-assets` UI with per-asset cards, inline payload editing for proposed assets, approve/retire/new-version actions, reference image thumbnails with lightbox, stats dashboard. 7 Pennifold canon assets seeded from operator-provided Drive folder (grade token, Fitzroy + Stackwell character refs with face/wardrobe canon blocks, 4 lockup SVGs) — all in 'proposed' status pending operator gate. `get_generation_context()` method provides approved assets to content creation pipeline. 35 new tests, 1,077 total passing · Q: operator needs to approve the 7 seeded assets via /setup/reference-assets
