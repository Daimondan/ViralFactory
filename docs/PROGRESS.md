# Build Progress — ViralFactory

> **Living document.** Updated every time a stage is started, completed,
> blocked, or changed. Any agent should be able to read this and know
> exactly where we are.

**Last Updated:** 2026-07-04
**Current Phase:** FIX — ffmpeg concat crash + fan-out duplicate platform assets fixed. Assembly renderer now validates in/out against source duration (clamps impossible seeks). Edit plan prompt clarifies in/out are per-source positions. Fan-out endpoint skips platforms with existing assets (no more duplicate IG cards). Error messages strip ffmpeg banner. 722 tests passing.
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
