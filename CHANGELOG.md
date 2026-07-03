# CHANGELOG — ViralFactory

> **If you made a decision and it's not in the changelog, it is a bug.**

All decisions — tech, logic, structure, strategy, ops — logged here with type tag + rationale.

---

### 2026-07-03 FIX — T8.1: Kill remaining source truncation (P0)

**What:** Removed `source_material[:4000]` blind character slice in `ideas_generate` (app.py:4061). Replaced `SNAPSHOT_CHAR_CAP = 4000` in `source_snapshot.py` with `MAX_SNAPSHOT_ITEMS = 40` — count-bounded, not character-sliced. `build_snapshot_text` now takes the most recent N items across all feeds, each with its full summary (already bounded by `SUMMARY_CHAR_LIMIT` at extraction time).

**Why:** Same truncation disease CORRECTION-format-selection killed for modules — blind `[:4000]` character slicing silently drops source items mid-list as content grows. Count-bounded digest is the stage-appropriate injection doctrine: selection stage gets ID + title + summary per active source, bounded by count, not by character slicing.

**Rationale:** Per CORRECTION-source-grounding-and-auto-production-v1.0 Section 1.3 (P0, land immediately). AC: grep for `[:4000]`, `[:2000]`, `[:1500]` across `src/` returns none on module/source injection paths.

### 2026-07-03 OPS — T8.2: Dead code removal + CONTEXT.md update (P0)

**What:** Removed dead `response_data` block in `ideas_gate_decision` (series branch) — was built but never used; actual response built separately as `response`. Updated CONTEXT.md with three new lines per correction: (a) every idea cites sources by ID, one idea may compose multiple sources; (b) Gate 1 approval triggers production automatically, publishing is never automatic; (c) AI work runs under named profiles (Researcher/Drafter/Analyst) defined in `config/profiles.yaml`. Core Loop diagram updated with auto-chain. New "AI Profiles" section added to Shared Language.

**Why:** Per CORRECTION-source-grounding-and-auto-production-v1.0 Section 4 (P0 housekeeping). Dead code is a defect even if harmless. CONTEXT.md is the operational mirror — it must reflect the new architecture before the P1 tasks build it.

**Rationale:** The correction explicitly designated these as P0/quick — land immediately, before the P1 architecture tasks.

### 2026-07-03 STRUCTURE — CORRECTION-source-grounding-and-auto-production-v1.0 filed

**What:** Filed architect correction introducing three architectural changes: (1) Source Bank as addressable store (`sources` table, idea cards carry `source_refs` by ID, kill remaining blind truncation); (2) Approval is the production trigger — Gate 1 approval auto-produces through to asset review, new card states `producing`/`asset_ready`/`production_failed`, no manual Generate clicks between approval and asset review; (3) AI Profiles (Researcher/Drafter/Analyst) as named compositions in `config/profiles.yaml`, provenance gains `profile` column. No-auto-publish remains absolute.

**Priority split:** Section 1.3 (kill `source_material[:4000]` + `SNAPSHOT_CHAR_CAP`) and Section 4 (dead-code sweep, CONTEXT.md lines) are P0/quick — land immediately. Sections 1 (Source Bank + source_refs), 2 (auto-production chain), and 3.1 (profiles.yaml + provenance profile column) are P1 architecture — sequence after T3.13 S1+S3 (confirmed landed at M3 checkpoint). Section 3.2 (Analyst scraping) is M6 scope (already has landing zone via `sources` table).

**Why:** Operator feedback: (a) every idea must be grounded in listed sources, one idea may compose multiple sources; (b) approval is the production trigger — no manual Generate clicks between approval and asset review; (c) introduce AI profiles (Researcher/Drafter/Analyst). Architect confirmed via live repo walk-through: sources die at Gate 1 (draft prompt has no source variable), evidence_links are decorative (freeform, not addressable), blind truncation survives in ideation, post-approval dead air (3+ manual generation clicks).

**Sequencing:** Source plumbing (T8.3-T8.5) lands first or together so first auto-produced drafts are source-grounded. Auto-chain (T8.6) does NOT enable until T8.3-T8.5 land. Profiles (T8.7) may land in parallel. BUILD_PLAN tasks T8.1-T8.7 added under new M8 milestone.

**Rationale:** Ideas grounded in real source material produce better content. Auto-production eliminates operator friction at the most mechanical part of the pipeline. Profiles make model/temperature/prompt composition explicit and configurable rather than implicit in code.

### 2026-07-03 FIX — UI-REVIEW-002: 15 findings from deep operator walk-through

**What:** Deep UI inspection after CORRECTION-module-context-assembly + CORRECTION-feedback-plumbing. Operator explicitly asked for "slight confusion or grievances" — not just obvious issues.

**Findings filed:** `docs/reviews/UI-REVIEW-002-deep-walkthrough-2026-07-03.md` — 15 findings. All fixed in this session.

**Fixes applied:**
1. Draft page: shipped state locks editing controls (Edit/Regenerate/Kill/Revise/audit-apply/feedback hidden when shipped; only "Proceed to Assets" + "Reopen for revision" shown). Gate API accepts `reopen` to return a shipped draft to `draft_ready` without bumping the draft version.
2. Asset staleness: draft page shows warning when draft was edited after assets were generated
3. Ideas page: series children grouped under parent (sorted, not scattered)
4. Ideas page: old clone children still have identical text — noted for architect (legacy data)
5. Human-readable scope labels: "one_off" → "Single piece", "series_of_n" → "Series", "pillar_with_derivatives" → "Main + derivatives"
6. Create page: descriptive draft titles (idea text instead of "Draft #N"), deduplicated columns
7. Dashboard: activity grouped by idea with sub-events, human-readable timestamps
8. Published page: "Scheduled" badge shows "Draft schedule (Postiz not connected)" when Postiz unavailable
9. Metrics page: "Pull metrics now" button disabled when Postiz unavailable
10. Library page: module previews collapsed with "Show more" toggle
11. Fan-out prompt: explicit "Do NOT add emojis/hashtags not in source draft" rule
12. Draft page: version/state shown as visible badge instead of tiny grey text
13. Draft page: empty state "Generate draft" button centered under instruction text
14. Dashboard: relative timestamps instead of raw ISO
15. Create page: approved idea links no longer truncated mid-word

### 2026-07-03 STRUCTURE — T3.13 added to BUILD_PLAN per CORRECTION-generation-diversity-and-asset-continuity-v1.0

**What:** New task T3.13 covering four operator-reported failures: (S1) deterministic idea generation, (S2) format convergence, (S3) fan-out mutating approved text, (S4) orphaned draft previews. T3.7 AC annotated to note S3 makes the "per-platform variants from Format Guide" AC true as written (currently from business config loop).

**Why:** Operator confirmed 17 cards converging on same few ideas; fan-out paraphrasing Gate-2-approved text; draft preview images orphaned. Correction approved by operator, ready for implementation. Sequencing: S1a → S3 → S1b/S1c → S4 → S2. M3 sprint checkpoint blocked until S1+S3 land.

**Rationale:** Generative calls (ideas, drafts, fan-out) need real temperature, not the temp-0 guardrail which correctly covers judgment/extraction only. Per-piece approval semantics require native-platform packaging verbatim. Asset continuity prevents paying twice and orphaning judged previews.

**Rationale:** Operator caught that the first UI inspection was superficial — only checked for obvious presence/absence of buttons. Deep walk-through found state-locked mode missing, stale assets, scattered series children, jargon labels, and more.

### 2026-07-03 STRUCTURE + LOGIC — CORRECTION-module-context-assembly + CORRECTION-feedback-plumbing-and-pipeline-fixes

**Module Context Assembly (STRUCTURE):** New subsystem — section-addressable module reads (`get_section`, `get_entry`, `get_index` on ModuleStore) + per-prompt view map (`prompts/views.yaml`) + assembler (`src/context_assembly.py`). All inline `[:2000]`-style module slices removed from `src/app.py` pipeline routes. `_extract_tells_checklist()` deleted — replaced by the `tells_checklist` view entry. Prompt bumps: `draft/generate_v2.md` → v2.2 (revision block + Format Guide wording), `assets/fan_out_v2.md` → v2.1 (adds `{visual_style}`). CONTEXT.md updated with "rules vs material" paragraph. Rationale: positional truncation degrades silently as modules grow; different prompts need different projections of the same module.

**F1 Direct edits → draft_text authoritative (LOGIC):** New `/api/draft/<id>/edit-text` endpoint writes `draft_text` directly via `save_edited_text()` (bumps version, logs weight-3 diff as feedback, invalidates stale audit flags). Old `direct_edit` via `/feedback` returns 400. UI: "Edit draft" toggle replaces freeform "Submit as direct edit" button. Rationale: direct edits were stored in `human_edits` column but nothing ever read it — downstream reads `draft_text`.

**F2 Revision feeds previous draft + feedback (LOGIC):** `draft_generate` route now assembles `previous_draft` (current draft_text, cap 6000 chars) and `revision_feedback` (weight-tagged feedback log entries, cap 3000 chars, highest-weight kept when trimming) into the prompt variables. First-time generation carries `(first draft — no previous version)` marker. Rationale: revise was a blind re-roll with identical inputs.

**F3 Series breakdown (LOGIC):** Series children now spawn via LLM breakdown call (`prompts/ideas/series_breakdown_v1.md`) with per-part ideas/hooks. Children enter state `new` (not `approved`) — operator gates each part. New `/api/ideas/<parent_id>/bulk-approve-children` endpoint. Fallback to clones in state `new` on LLM failure with surfaced warning. Rationale: n-1 pieces of AI content were advancing past Gate 1 without operator seeing per-part content.

**F4 owner_type column (STRUCTURE):** `asset_media` table gains `owner_type` column (default `'asset'`). Draft visuals use `owner_type='draft'` with the real `draft_id` — replaces the synthetic `draft_id + 100000` scheme. Legacy rows migrated idempotently in `_init_tables`. `generate_image`, `_record_media`, `list_asset_media` all accept `owner_type` parameter. Rationale: magic number breaks silently when real asset IDs cross 100000.

**F5 ffprobe real durations (LOGIC):** `probe_duration()` module-level function in `assembly.py` called in the edit-plan inventory loop for generated videos and uploaded video/audio. Images keep 3.0s (plan intent, not file property). On probe failure, falls back to default with `(duration unverified)` marker. Rationale: LLM planned trims against fictional durations.

### 2026-07-03 STRUCTURE — Inbox batch 2026-07-03-e + format-selection filed: AMENDMENT-005 (processes are module compositions) + CORRECTION-format-selection-living-v1.0

**What:**
- Filed `docs/decisions/AMENDMENT-005-processes-are-module-compositions.md` — architecture doctrine: processes (ideation, drafting, treatment) are compositions of modules, not hardcoded route handlers. Process Registry (`config/processes.yaml`) is the 9th module — versioned, gate-only writes, AI-improvable through the gate. One compose-and-run engine replaces per-process module wiring. BUILD_PLAN updated to v1.4: T2.12 added (registry extraction), T3.2 reworded, M5/M6 targets widened.
- Filed `docs/corrections/CORRECTION-format-selection-living-v1.0.md` — P0 bug: module truncation (`[:2000]`, `[:1500]`) in idea generation routes means the LLM never sees most of the Format Guide (17KB, only first 2KB injected). Fix: remove all blind truncation; stage-appropriate injection (selection sees compact digest, production sees full entry). Architecture: format selection by affordances + evidence + distribution feedback, not decision table. Format Guide schema gains `affordances`, `performance_evidence`, `variant_type`, `aspect_ratio`; loses `decision_table`. Governing principle added to CONTEXT.md: "Prompts carry procedures; modules carry knowledge."

**Rationale:** Architect direction via inbox protocol (MANIFEST-2026-07-03-e, MANIFEST-2026-07-03-format-selection). AMENDMENT-005 stops process-first drift before M3 pipeline work accretes more hardcoded route handlers. The format-selection correction addresses the proximate cause of video under-suggestion: not decision-table weighting, but blind truncation hiding most formats from the LLM.

**Manifests:** `docs/inbox/processed/MANIFEST-2026-07-03-e.md`, `docs/inbox/processed/MANIFEST-2026-07-03-format-selection.md`

---

### 2026-07-03 TECH — T4.1 + T4.2: Postiz adapter + metrics collection (M4)

**What:**
- `src/postiz_adapter.py` — Postiz Public API adapter: publish pieces (after per-piece approval), pull post-level analytics, store metrics. Config-driven (base_url, api_key, integration_ids from `config/models.yaml`). Graceful fallback when Postiz not available — asset stays in 'approved' state, no data loss.
- Publish route updated: `/api/assets/<id>/schedule` now calls Postiz to actually post. Returns 502 with helpful hint when Postiz not configured. Retry endpoint for failed publishes.
- `/metrics` page + `/api/metrics/pull` endpoint — view metrics for published pieces, manually trigger pulls.
- `/api/postiz/status` — check Postiz availability + list connected integrations.
- `cron_pull_metrics.py` — nightly cron script for unattended metrics collection (T4.2).
- `publish_log` + `post_metrics` tables in SQLite.
- 29 new tests (471 total). Postiz config block added to `models.yaml`.

**Rationale:** T4.1 + T4.2 of BUILD_PLAN. Postiz not yet installed on VPS — Docker available but no container running. Adapter is ready; set `POSTIZ_API_KEY` env var and configure Postiz to enable end-to-end publishing. Per-piece approval enforced in code (asset_state must be 'approved').

---

### 2026-07-03 LOGIC — T5.1 + T5.2 + T5.3: Inward learning loop + async gate (M5)

**What:**
- `src/proposal_store.py` — ProposalStore: async gate queue for module improvement proposals. Superseding (newer proposal on same module+section marks older as superseded, visible not deleted), age tracking, pending counter, bulk approve/reject, summary stats. Per AMENDMENT-005: process-registry is a valid proposal target; mapping_change is a valid proposal type.
- `prompts/learning/generate_proposals_v1.md` — LLM prompt for weekly proposal generation. Reads published results + Feedback Log (direct edits weighted highest) + performance notes + module versions → produces specific, evidence-backed proposals with exact diffs. Never vibes — evidence required.
- `cron_generate_proposals.py` — weekly cron script. Gathers inputs, calls LLM via adapter (temperature 0), stores proposals in the gate queue.
- `/proposals` page + `/api/proposals/<id>/approve` + `/api/proposals/<id>/reject` + bulk approve/reject endpoints. Gate queue UI with: pending counter, age per proposal ("submitted N days ago"), evidence display, exact diff, quick-reason reject chips, bulk select-all bar.
- T5.3: Voice Profile update path — approved voice-profile proposals trigger version bump via ModuleStore (approval is the gate; the operator's approval is the human gate per the charter).
- 21 new tests (492 total). `proposals` table in SQLite.

**Rationale:** T5.1–T5.3 of BUILD_PLAN. The inward learning loop reads what the operator did (feedback + direct edits + performance data) and proposes specific module updates — the system gets better at the operator's voice and content quality over time, but every change passes the human gate. No deadline or pressure mechanics anywhere.

---

### 2026-07-03 OPS — Inbox batch 2026-07-03 filed: orchestrator correction, definition-of-done process, whisper transcription decision

**What:**
- Filed `docs/reviews/CORRECTION-orchestrator-drafting-and-ux-v1.0.md` — correction from architect review of commit `372f81e` following operator's first end-to-end onboarding run. Covers P0-1 (drafting input starvation — root cause of all thin/empty documents), P0-2 (validation crash on `next_focus: null`), P1-1 (gate relocation to Library — draft-status modules), P1-2 (conversation continuity/resume), P1-3 (readback rendering), P1-4 (upload feedback), P2-1 (conversational latency — `converse` backend role), P2-2 (orchestrator prompt v2 — agency-intake posture).
- Filed `docs/PROCESS-definition-of-done-v1.0.md` — operator ruling: Hermes does not report work as done until automated suite + human UI test + end-to-end pass + done report. Binding on all work from 2026-07-03. Reference added to `docs/CONTEXT.md` under new "Working Agreements" section.
- Filed `docs/decisions/DECISION-transcription-whisper-v1.0.md` — operator approved self-hosted Whisper via `faster-whisper` (CTranslate2, int8, medium model, CPU). Background worker in-process. Closes the transcription hosting blocker from CORRECTION-session-memory-and-materials-v1.1. Unblocks Voice Profile end-to-end.

**Rationale:** Architect direction via inbox protocol (MANIFEST-2026-07-03 + MANIFEST-2026-07-03-b). Implementation order specified: P0-1 → P0-2 → P1-1 → P1-2 → P1-3/P1-4 → P2, with transcription worker buildable in parallel but wired after P0-1. Session-storage refactor from CORRECTION-session-memory-and-materials-v1.1 is required by P1-2 and is folded into this batch.

**Manifests:** `docs/inbox/processed/MANIFEST-2026-07-03.md`, `docs/inbox/processed/MANIFEST-2026-07-03-b.md`

---

**What:**
- **P0 bug fix:** Removed duplicate `const playbookName` declaration in `src/templates/session.html` (line 467). The second declaration, introduced when the gate-actions routing block was appended, caused a `SyntaxError: Identifier 'playbookName' has already been declared` — which prevents the browser from executing the entire `<script>` block. All interactive JS (attach button, send button, gate approve/park/reject buttons) was dead.
- **Guardrail:** New `tests/test_template_js_parse.py` — extracts `<script>` blocks from session.html, renders Jinja placeholders with dummy values, and runs `node --check` to validate syntax. Catches the entire class of "template edit silently kills page JS" bugs. Verified: reintroducing the duplicate correctly fails the test with the exact SyntaxError.

**Rationale:** CORRECTION-onboarding-single-thread-v1.0 Item 1 (P0). The architect identified this as a regression that blocks all onboarding use. This is the second time a template edit silently killed page JS; the parse check ends the category.

**Corrections filed:** `docs/reviews/CORRECTION-onboarding-single-thread-v1.0.md` — arrived without manifest (inbox protocol rule 5). Filed as architect direction to `docs/reviews/` since it is a correction/review document. Item 2 (architectural redesign: single-thread onboarding) tracked as GitHub issue #2, scheduled for next review tag.

---

### 2026-07-03 FIX — Validator strips markdown code fences from LLM JSON output

**What:**
- **Validator fix:** `validate_llm_output()` in `src/validator.py` now strips markdown code fences (```json ... ```, ``` ... ```, ```javascript ... ```) before `json.loads()`. GLM-5.2 wraps JSON output in ` ```json ` fences; `json.loads()` choked on the leading backticks — both initial attempt and retry failed identically with "Expecting value: line 1 column 1 (char 0)".
- **9 new tests** (`tests/test_validator_code_fences.py`): fence stripping (json/plain/js variants), multiline JSON in fences, real provenance #5 output from run 24, and negative tests (garbage still rejected, invalid JSON in fence still rejected). 329 tests total.

**Rationale:** Operator reported error when uploading a zip to voice-profile-builder session run 24. Provenance rows #4 and #5 showed both LLM attempts returned valid JSON wrapped in ` ```json ... ``` ` — the validator rejected them as non-JSON because it didn't strip the fence wrapper. This is a mechanical parsing issue, not an LLM quality issue — the model produced correct JSON, the validator just couldn't see past the markdown wrapper.

**Root cause:** Many LLMs (GLM-5.2, Claude, GPT) wrap structured output in markdown code fences despite instructions to return raw JSON. The retry prompt ("respond with ONLY valid JSON") doesn't help because the model considers the fence to BE "only JSON." The fix is in the validator, not the prompt — stripping fences is mechanical, not judgment.

**Corrections filed:** `docs/reviews/CORRECTION-session-memory-and-materials-v1.1.md` — arrived without manifest. Filed as architect direction. 5 findings (F1–F5) covering: file-only turns invisible to AI, materials not injected into converse prompt, history truncation keeping oldest/not newest, parallel-array transcript fragility, no anti-repeat guard. Fixes in priority order starting with F3 + F1.

---

### 2026-07-03 FIX — Session memory & materials (F1, F2a, F2b, F2c, F3, F5)

**What:**
- **F3 (P0):** History truncation was a head slice (`[:4000]`) — kept the OLDEST turns, dropped the NEWEST. Changed to tail slice (`[-12000:]`) + raised budget from 4k to 12k chars. This was the root cause of the AI repeating earlier questions verbatim: from its perspective, the conversation was still at that earlier point.
- **F1 (P0):** File-only turns (uploads with no text) were invisible to the AI. The file note was stored only in `business_qa`, which `_build_conversation_history` excludes for session messages. Now `session_messages` stores `[Operator attached files: ...]` so the AI can see uploads in the transcript.
- **F2a (P0):** Uploaded material content never reached the converse LLM. Added `_build_materials_summary(run_id)` — queries materials for the run, builds a capped summary (1,500 chars/material, 6,000 total), and injects it as `{materials_summary}` into the converse prompt (v3.0). The AI now sees document excerpts and audio status.
- **F2b (P0):** No `.docx` extraction existed. Added `_extract_docx_text()` using python-docx. `.docx` files now extract paragraph text, same as PDF.
- **F2c (P0, blocks voice profile):** `.mp4`, `.opus`, `.aac`, `.flac` not recognized as audio — stored as binary garbage. Added to audio extension list. Transcription itself needs a decision (DIVERGENCE-005 filed) — interim: materials summary says "transcription pending" so the AI acknowledges receipt.
- **F5 (P1):** No anti-repeat guard. Added prompt section ("Questions you have already asked") + server-side `_is_near_duplicate()` using difflib SequenceMatcher (threshold 0.9). On near-duplicate, regenerates once with the same prompt (the anti-repeat section now visible in context).
- **18 new tests** (`tests/test_session_memory_fixes.py`). 347 total.
- **Prompt bumped to v3.0:** materials section, anti-repeat section, "reference uploaded materials" rules.
- **python-docx added to requirements-prod.txt.**
- **DIVERGENCE-005 filed:** audio transcription implementation decision (self-hosted faster-whisper vs hosted API) — operator gate required.

**Rationale:** CORRECTION-session-memory-and-materials-v1.1 traced the operator's exact field report: AI asked "what kind of stuff did you send?" after receiving a zip, re-asked "what's the business?" after receiving the Brand Report, then repeated an earlier reply word-for-word. Four compounding bugs (F1–F3, F5) made every intake session degrade into a loop. These fixes address the P0 items; F4 (turn log restructure) deferred to this tag or next.

**Not done:** F4 (replace parallel arrays with single turn log) — P1, deferred. F3 rolling summary — P1, with orchestrator. F2c transcription implementation — blocked on DIVERGENCE-005 operator decision.

---

### 2026-07-02 BUILD — Session component: LLM-driven conversation, all playbooks, run reuse

**What:**
- **LLM-driven conversation (not template questions):** Every message goes through `prompts/session/generic_converse_v1.md` — the AI reasons about what it knows and what it still needs, asks smart follow-ups referencing what was said, and decides when it has enough to trigger analysis. No hardcoded question list. The AI is present at every stage; the operator is never handed a form.
- **Run reuse:** Visiting a playbook page reuses the latest incomplete run instead of creating a new one every visit. Dashboard shows only the latest run per playbook, not the full history of dead runs.
- **All playbooks use session component:** Voice Profile, Sources, Viral Patterns, Audience, Story, Format, Visual Style — all now render the same chat interface. Gate buttons route to the correct store endpoint per playbook. No more seeing raw procedure markdown.
- **Readback shows after analysis:** When the AI says `ready_to_draft`, it triggers the playbook-specific analysis (correct prompt + schema for each of the 7 playbooks via a playbook→prompt/schema/output-key map), stores the result, reloads the page, and shows the readback with Edit / Approve / Park / Start over gate buttons.
- **Generic readback:** `_build_readback()` formats any playbook's output for display. Business Profile gets a custom format; others get a generic key-value listing.
- **PYTHONPATH fix:** Added `PYTHONPATH=/home/daimon/ViralFactory/src` to systemd service so nested `from module_store import...` calls work under gunicorn, not just in tests.
- **Graceful JS error handling:** Session frontend checks `content-type` before parsing JSON; shows human-readable error messages for 401/500/502/504 instead of raw HTML parse failure.
- **Technical details behind disclosure:** No file paths in default operator view — just playbook name + gate step behind a `<details>` element (F4 compliance).

**Rationale:** UI-REVIEW-001 F3 is structural — the console must be a conversational AI session, not a document viewer. Template questions were the first attempt; the operator correctly identified that the AI should reason about what it knows and ask smart follow-ups, not recite a fixed list. Run spam was caused by creating a new run on every page visit. All playbooks needed the session component, not just Business Profile. These changes address acceptance checks 1, 3, 4, 5, 6, 7 from UI-REVIEW-001.

---

### 2026-07-02 BUILD — Zip file support + PDF/image intake (DIVERGENCE-004)

**What:**
- `MaterialsIntake.ingest_zip()`: extracts zip archives to a temp directory, ingests each file recursively through the existing intake pipeline. Handles nested directories, skips hidden files and __MACOSX junk, cleans up temp dir. Failed files logged as error-channel materials — zip doesn't fail if one file is broken.
- `ingest_file()` extended: `.zip` delegates to `ingest_zip()`. PDF text extraction (pdfplumber → PyPDF2 → graceful fallback). Image files (.png/.jpg/.jpeg/.gif/.bmp/.webp) stored as visual references with file copied to upload dir. Binary files get graceful placeholder instead of crashing.
- Works through both `/api/run/<id>/upload` and `/api/session/<id>/upload` (session component).
- DIVERGENCE-004 filed for architect awareness.
- 9 new tests (319 total).

**Rationale:** Operator needs to upload a zip of mixed materials (chats, docs, photos, audio) in one shot. Without zip support, the file fell through to "unknown type" and tried to read binary as text. This enables true one-go intake per the charter. No charter conflict — capability extension, not a design change.

**What filed:**
- `UI-REVIEW-001-intake-console.md` → `docs/reviews/UI-REVIEW-001-intake-console.md` (ADD)
- `MANIFEST-2026-07-02-D.md` → `docs/inbox/processed/` (after filing)

**APPLY executed:**
1. UI-REVIEW-001 marked as **blocking for the operator end-to-end test**. The 7 acceptance checks must all pass before the end-to-end test re-runs.
2. UI-DIRECTION.md bumped to v1.3: added Principle 9 (console renders sessions, not documentation — F3) and Principle 10 (operator-facing copy rule — F4). Surface 1 (Onboard) rewritten to describe the session interaction model: chat transcript pane, input box, file upload, readback→gate, progress rail.
3. CONTEXT.md: added "The console renders sessions, not documentation" principle verbatim from the review.
4. Playbook step schema extended: `run_order` (integer) and `display_label` (operator-facing label) added as HTML comment metadata in all 8 playbooks. PlaybookParser reads both. Onboard route sorts playbooks by `run_order` and passes `display_label` to template. Business Profile Intake = run_order 1 (first), Visual Style = 8 (last).
5. Voice input deferred per existing T2.6–T2.8 record — session component to be built text+files only, mic slots in later.
6. PROGRESS.md updated: operator UI review received, findings accepted, end-to-end blocked on UI-REVIEW-001 acceptance checks.

**Rationale:** Architect batch D. The operator (Daimon) walked the live console and found the intake page renders playbook markdown as static text — no input, no upload, no session. F3 is structural: the console must be a conversational AI session, not a document viewer. This blocks the M2 end-to-end test until the session component is built and all 7 acceptance checks pass.

---

### 2026-07-02 BUILD T3.5–T3.12 — Co-production loop complete (M3 done)

**What:**
- **T3.5 Drafter:** prompt template (draft/generate_v1.md), DRAFT_SCHEMA (draft_text + visual_direction + self_audit_flags), Flask route loads ALL 8 modules + capture material → LLM → draft stored. Visual direction is text only (no renders). Self-audit flags shown with rule + suggestion. Uses drafter backend from models.yaml.
- **T3.6 Human pass (Gate 2):** reaction chips + typed feedback + direct-edit mode. Direct edits saved as authoritative (highest weight=3 in Feedback Log). Gate decisions: ship-forward, kill (with reason→feedback), revise (version increment).
- **T3.7 Assets stage:** prompt template (assets/fan_out_v1.md), per-platform variant generation via LLM. Image prompts generated per platform. Fan-out only on shipped drafts.
- **T3.8 Assets gate (Gate 3):** per-variant approve/fix/kill. Approved assets flow to publish.
- **T3.9 Origin threading:** origin + format + scope carried from idea card → draft → assets → nightly stats (get_pipeline_stats: origin/format/scope breakdown).
- **T3.12 Publish handoff (Gate 4):** go/hold + timing. Schedule sets publish_scheduled_at and transitions to 'published'. Non-approved assets can't be scheduled. Hard rule: no auto-publish.
- **Create surface:** dashboard at /create showing pipeline state (approved ideas, drafts in progress, shipped).
- **Templates:** draft.html (full draft display + feedback + gate), assets.html (per-platform grid), publish.html (go/hold + scheduling), create.html (pipeline overview).
- 28 new tests (310 total).

**Rationale:** M3 BUILD_PLAN T3.5–T3.12 — the full staged pipeline from approved idea to publishable asset. The co-production loop is now complete: Ideas → Draft → Assets → Publish, with all four gates operational, origin/format/scope threaded end-to-end, series spawning and experimental format debut working. No hardcoded business values — all from config and modules.

---

### 2026-07-02 BUILD T3.1–T3.3 — Idea cards, Ideas gate, awaiting-capture
**What:** 2 prompt templates (per-item indexing + style guide analysis), VISUAL_STYLE_SCHEMA (palette with hex codes, typography feel, stylization level, blend rules with real/generated/disclosure split, platform adjustments), SHOT_LIBRARY_ITEM_SCHEMA (description, tags, mood, best_for, platforms), 2 markdown converters, 5 API endpoints including per-item LLM indexing of shot library items, HTML intake page with palette swatches and shot library display. Gate-enforced write writes both visual-style and shot-library modules. 23 new tests (240 total).
**Rationale:** M2 BUILD_PLAN T2.4 — the visual identity module and shot library that feed the drafter's visual direction blocks. Blend rules enforce the charter principle: real footage anchors trust, generated is supporting.

---

### 2026-07-02 BUILD R15 — Gate step derived from parsed playbook, not hardcoded
**What:** PlaybookParser now handles numbered-list procedure format (N. Description) in addition to ### Step N format. Added get_gate_step_number() to PlaybookRunner. All 7 store endpoints (voice, business, sources, viral-patterns, audience-insights, story-frameworks, format-guide) now derive the gate step from the parsed playbook instead of hardcoded strings. create_app() defaults to absolute playbooks path so CWD changes don't break file resolution. 16 new tests (217 total).
**Rationale:** R15 correction — hardcoded gate step strings are fragile. If a playbook's procedure changes (step renumbered), the store endpoint would record the gate result on the wrong step. Deriving from the playbook makes the system self-correcting.

---

### 2026-07-02 BUILD T2.3 — Viral Patterns + Audience Insights + Story Frameworks + Format Guide playbooks
**What:** 4 playbooks fully wired with prompt templates, JSON schemas, markdown converters, API endpoints (input + analyze + store), and HTML intake pages. Format Guide schema includes AMENDMENT-004 enrichment: `requires_human_capture`, `capture_tasks`, `effort_level`, `best_for`, `platforms`, `reuse_pathways`, `status` (proven|experimental|retired), `provenance`. All 4 store endpoints enforce gate tokens (T2.9). 47 new tests (201 total).
**Rationale:** M2 BUILD_PLAN T2.3 — the remaining onboarding playbooks that feed the co-production loop. Format Guide enrichment enables the treatment block on idea cards (AMENDMENT-004).

---

### 2026-07-02 BUILD T2.9 — Gate-token enforcement on all write paths
**What:** ModuleStore.store(), business.yaml writes, and sources.yaml writes now require a verified gate token from an approved run. No more honor-system writes. Orphan prevention: "unknown" or empty business slug raises immediately. 12 new tests (154 total at that point).
**Rationale:** R13 correction — pull gate enforcement forward before building more store endpoints, so enforcement is baked in from the start rather than retrofitted.

---

### 2026-07-02 STRATEGIC — ViralFactory is a generic system, StackPenni is user #1
**Rationale:** Daimon confirmed the system is named ViralFactory — a generic content co-creation system. StackPenni is the first tenant. Paying customers are a real near-term plan. The harness is code; the business lives entirely in config and modules. This was established during the grill session and aligns with Charter v3's original design.

### 2026-07-02 STRATEGIC — Fresh start, no v2 migration
**Rationale:** Daimon said "fresh start for now." The old StackPenni v2 pipeline (Flask app, ~1,545 sources, 68 tests) stays running at stackpenni.glenbeu.com until ViralFactory is production-ready. No v2 code, data, or schema is reused. StackPenni config will be re-entered through the onboarding flow. BUILD_PLAN's reference to "extend the existing Flask app" is stale and must be updated. (Divergence 5 from Charter.)

### 2026-07-02 STRATEGIC — Human role includes direct edit, not just originate + react
**Rationale:** Daimon said "yes sometimes i should be able to write edit directly myself and the system respect and encourage that." The Charter's "never produce" framing was too restrictive. The system defaults to AI production but supports and encourages human direct editing. Direct edits are authoritative (override AI draft) and feed the Feedback Log as the strongest voice signal. (Divergence 1 from Charter.)

### 2026-07-02 OPS — Async gate queue, not weekly sitting
**Rationale:** Daimon said "a queue i clear." The Charter's "one sitting per week" gate model doesn't match Daimon's actual rhythm. Proposals accumulate in a persistent queue; Daimon clears when ready. The inward loop can still generate proposals on a weekly schedule, but human review is asynchronous. (Divergence 2 from Charter.)

### 2026-07-02 STRUCTURE — Laptop-first UI, mobile-friendly for future users
**Rationale:** Daimon said "laptop primary I am, but it should be mobile friendly esp for other people." UI-DIRECTION.md's "mobile-first, operator runs from phone" was wrong for the primary user. Design for laptop (1280px+), scale down responsively. Mobile-friendly is required for paying customers but doesn't constrain the primary design. (Divergence 3 from Charter.)

### 2026-07-02 STRATEGIC — Generalization is real but not blocking v1
**Rationale:** Daimon confirmed paying customers are a near-term plan, but "suggestive for now, when we get there we can decide." Keep "nothing business-specific in code" as architecture. Build for StackPenni first. Don't let generalization block v1 delivery. (Divergence 4 from Charter.)

### 2026-07-02 TECH — Postiz for publishing (not Buffer)
**Rationale:** Daimon asked "does Postiz make it easier to post?" Research confirmed yes: Postiz has direct media upload via API (Buffer requires hosted URLs — the exact pain Daimon identified), per-post analytics on all plans, 32 platform integrations, an MCP server for AI agent integration, self-hosting (free, AGPL-3.0), and OAuth 2.0 "Direct Integration" flow for onboarding paying customers. Buffer's GraphQL API is more complex and its media handling is a dealbreaker for a system that produces text + images + video. Postiz self-host vs cloud deployment TBD (open question).

### 2026-07-02 TECH — Flask + SQLite + systemd on VPS
**Rationale:** Carried from Charter v3. Flask is boring, fast on island bandwidth, server-rendered. SQLite is sufficient for a single-tenant system and easy to deploy. systemd ensures the app survives session boundaries. Fresh start = new Flask app, new SQLite DB, no v2 reuse.

### 2026-07-02 TECH — LLM adapter swappable in config
**Rationale:** Carried from Charter v3. One function: `complete(prompt_file, variables, schema) -> validated JSON`. Backend from `models.yaml` — Ollama local, Ollama Cloud, or external API. Model swap = config edit, zero code change. If open-source drafting quality underwhelms, swap without touching code. Default: Ollama Cloud (Daimon's existing $20/mo subscription). Final choice is an open question.

### 2026-07-02 LOGIC — Per-piece approval, no auto-publish
**Rationale:** Daimon said "yes need to approve every piece before posting." Every piece passes human approval before shipping to Postiz. No exceptions, no auto-publish even after trust is built. This is a hard business rule.

### 2026-07-02 LOGIC — Outward research loop continuous from v1
**Rationale:** Daimon said "system to do it continuously from v1." The outward loop (monitoring top performers, analyzing viral patterns in the domain) runs from day one, not deferred to a later phase.

### 2026-07-02 LOGIC — Feedback via typed text + tap chips
**Rationale:** Daimon said "feedback via type text and tap chips where it makes sense to do so." Not voice-only (UI-DIRECTION assumed voice + chips). Typed text is always available; chips are offered for common reactions where they speed things up.

### 2026-07-02 STRUCTURE — Generic playbook engine
**Rationale:** Daimon confirmed the playbook runner should be generic — it executes markdown procedures for any user, not purpose-built for StackPenni onboarding. Same effort as purpose-built, but enables customer #2 with zero code changes.

### 2026-07-02 STRUCTURE — 8 modules as v1 reality
**Rationale:** Daimon confirmed all 8 living modules (Voice, Viral, Story, Format, Audience, Feedback, Visual, Sources) are v1 reality, not final-state vision. All built during onboarding, all loaded into drafts.

### 2026-07-02 STRUCTURE — GitHub for code AND docs
**Rationale:** Carried from Charter v3. One repo, no split between code and documentation. All agents read the same source of truth.

### 2026-07-02 OPS — All divergences logged for Claude architect awareness
**Rationale:** Daimon said "ensure any divergence from the charter is noted so Claude who is the architect is aware and updates plan going forward." DIVERGENCE-001 written to docs/decisions/. Claude must review and incorporate into Charter v3.1.

### 2026-07-02 OPS — Operating loop doc reviewed and patched
**Rationale:** Daimon added docs/OPERATING-LOOP.md (written by Claude architect). Reviewed against charter + grill amendments. Two patches applied: (1) kickoff step updated to reference docs/CONTEXT.md as primary domain doc, (2) "Weekly cycle" renamed to "Weekly cycle (architect review cadence)" with a note clarifying it's the build-process loop, NOT the product gate (which is async per DIVERGENCE-001). The operating loop complies with the charter and grill amendments — no conflicts found, just the naming clarification needed to avoid confusion between the two loops.

### 2026-07-02 STRATEGIC — Claude architect review: all 5 divergences APPROVED
**Rationale:** Claude reviewed DIVERGENCE-001 and approved all 5 amendments. D1 (direct edit): approved, direct edits are evidence — patterns still reach Voice Profile through gate, no silent self-update. D2 (async gate): approved with refinements — superseding (newer proposal on same section marks older superseded, not deleted), principle rewritten as "if queue grows faster than it clears, fix the proposal prompt, never pressure the person." D3 (laptop-first): approved. D4 (generalization): approved — costs nothing, config isolation was always the architecture. D5 (fresh start): approved with one flag — v2 database must be backed up before decommission; Sources Engine retains optional deferred bulk-import path. "Not migrated" never means "destroyed."

### 2026-07-02 STRUCTURE — Document hierarchy established
**Rationale:** Claude ruled that CONTEXT.md was claiming "source of truth" / "supersedes charter" — two documents claiming primacy causes agents to build against different understandings. New hierarchy: (1) Charter — principles and design rules, amended only via docs/decisions/ → architect review → version bump; (2) BUILD_PLAN — conforms to charter; (3) CONTEXT.md — operational mirror, conforms to charter and plan, conflicts are bugs or divergences; (4) CHANGELOG/decisions/ — the record, feeds charter revisions. CONTEXT.md header patched to reflect this.

### 2026-07-02 TECH — Open questions resolved by architect
**Rationale:** Claude resolved 3 of 5 open questions: (1) Module storage = repo markdown as system of record, OB1 is read-only mirror (optional, later); (2) Postiz = self-hosted on VPS (ownership, AGPL, no per-seat cost); (3) LLM backend = Ollama Cloud default for processing, drafter A/B at M3 checkpoint (same seeds, two backends, Daimon reacts blind). Remaining 2 (context window strategy, video scope) are genuinely deferrable.

### 2026-07-02 STRUCTURE — 8 playbooks split into individual files
**Rationale:** Per architect action item 5. docs/playbooks-remaining-seven.md split into 7 individual files in playbooks/. Combined with the existing voice-profile-builder.md, all 8 playbooks now live as individual files: business-profile-intake, voice-profile-builder, sources-engine, viral-patterns-starter, audience-insights-builder, story-frameworks-starter, format-guide-starter, visual-style-intake.

### 2026-07-02 STRUCTURE — UI-DIRECTION.md patched to v1.1
**Rationale:** Per architect action item 3. Principle 1 → laptop-first (1280px+), responsive to mobile. Principle 2 → verbs now include "type" and "edit" (direct edit supported). Principle 4 → async queue, not weekly sitting. Principle 5 → voice available everywhere, assumed nowhere. Surface 2 (Create) → two input modes: reaction mode (chips + text) and direct-edit mode (editable draft, human text authoritative, logged at highest weight). Surface 4 (Gate) → async queue with age, superseding, no pressure.

### 2026-07-02 OPS — v2 database backup task added (T0.7)
**Rationale:** Per architect action item 6. Fresh start ≠ data destruction. T0.7 added to M0: scripted, verified backup of v2 SQLite database to storage outside v2 app directory. AC: restore tested once; backup location documented in CONTEXT.md. The Sources Engine playbook retains an optional deferred bulk-import path — the 1,545 sources remain importable forever at near-zero cost.

### 2026-07-02 STRATEGIC — ViralFactory is fully standalone, no OB1 dependency (DIVERGENCE-002)
**Rationale:** Daimon said "please dont mess up my ob1 brain, this should be a separate system its own database." Claude's recommendation of OB1 as a read-only mirror is overruled. ViralFactory has its own SQLite database — no OB1 Supabase connection, no OB1 MCP tools, no OB1 dependency whatsoever. Every user onboards the same way: upload materials, share docs, connect Obsidian. OB1 is Daimon's personal knowledge system; ViralFactory is a product. They don't touch. All OB1 references removed from charter, BUILD_PLAN, CONTEXT.md, playbooks, and intake checklist.

### 2026-07-02 FIX — Review-w1 corrections R1–R5 applied
**Rationale:** Claude architect review (review-w1_1.md) identified 5 must-fix defects against M1 acceptance criteria. All 5 fixed:
- **R1 (gate bypass):** `store_voice()` now only writes to `modules/` when `approved=true`. Parked/rejected profiles stay in run state only. 2 new tests.
- **R2 (provenance append-only):** Dropped `UNIQUE` constraint + changed `INSERT OR REPLACE` to `INSERT`. Cache hits and retries no longer overwrite original rows. 1 new test.
- **R3 (failed attempt logging):** First failed validation attempt is now logged to provenance before retry. Every LLM call is logged. 1 new test.
- **R4 (Ollama auth + base_url):** Adapter now sends `Authorization: Bearer $OLLAMA_API_KEY` when env var is set. `base_url` corrected from Cloudflare URL to `https://ollama.com`. 2 new tests. Live smoke test pending `OLLAMA_API_KEY` env var.
- **R5 (WhatsApp format coverage):** Regex widened to support 24-hour format (no AM/PM), iOS bracket format with seconds, and iOS 24h. 3 new test fixtures.
- Process: PROGRESS.md header fixed, BUILD_PLAN checkboxes checked, tag reference corrected to `review-w1`.
- 101 tests passing (92 original + 9 new).

### 2026-07-02 STRUCTURE — Inbox Protocol established (first batch)
**Rationale:** Architect→builder filing standardized. All architect files land in `docs/inbox/`; Hermes files them per the manifest. `docs/inbox/README.md` carries the binding rules. First batch processed: INBOX-README → `docs/inbox/README.md`, AMENDMENT-003 → `docs/decisions/`, diagrams-README → `docs/diagrams/README.md` (replaced), system-overview-v3.2.svg → `docs/diagrams/`, manifest → `docs/inbox/processed/`.

### 2026-07-02 STRATEGIC — Charter bumped to v3.2 (AMENDMENT-003: staged content pipeline)
**Rationale:** AMENDMENT-003 (approved by operator) expands the core loop from a single Draft → React step into a staged funnel with four content gates: Ideas (rigorous: approve/kill/park) → Draft (text + visual direction, no renders; human pass) → Assets (real images + per-platform fan-out; quick gate) → Publish (go/hold). Weak ideas die at the cheapest point. `origin` field (ai-originated | human-seeded | human-seeded-ai-developed) travels end-to-end and is recorded in the nightly performance note. Charter renamed from `CHARTER-v3.1.md` to `CHARTER-v3.2.md`; all references updated (README, CONTEXT.md, BUILD_PLAN header). CONTEXT.md core loop + system diagram mirrored. UI-DIRECTION.md Surface 2 gained Ideas queue + Assets review views. BUILD_PLAN M3 expanded with 9 tasks (idea cards, Gate 1 UI, visual-direction block, Assets stage, Gate 3 UI, origin threading). M2 unchanged. Diagrams README replaced with v3.2 system overview + Mermaid. `stackpenni_v3_system_with_onboarding.png` superseded (left in place).

### 2026-07-02 STRATEGIC — Audio transcription + voice cloning (DIVERGENCE-003)
**Rationale:** Daimon directed: implement audio transcription in M2 (resolving R6), AND add open-source voice cloning so content audio (reel voiceovers, X audio posts) is produced in the person's own voice. DIVERGENCE-003 filed with full rationale. Transcription: faster-whisper (CTranslate2, int8, CPU — our VPS has no GPU), model in config. Voice cloning: Apache 2.0 models only (commercially safe for paying customers). Qwen3-TTS primary candidate (3-second zero-shot cloning, 1.7B params). XTTS-v2/Coqui explicitly ruled out (CPML non-commercial license, Coqui org shut down). No cloud TTS APIs — self-hosted only, same data-sovereignty principle. Three new M2 tasks added: T2.6 (transcription), T2.7 (voice cloning adapter), T2.8 (voice sample management). R7–R9 also added as T2.9–T2.11.

### 2026-07-02 OPS — Repo visibility decision (R10)
**Rationale:** Architect flagged that the GitHub repo is public while PROGRESS.md said "(private)." Daimon confirmed PUBLIC is deliberate — the architect (Claude) needs to read the repo without auth. PROGRESS.md corrected. Console auth: the Flask console has no authentication in M0–M2; deployment posture documented in CONTEXT.md (bind to localhost/VPN or add auth before operator end-to-end test).

### 2026-07-02 FIX — Review-M2-midpoint corrections R10–R16 applied
**Rationale:** Architect interim review of T2.1–T2.2 identified blocking and non-blocking defects. All applied:
- **R10:** Repo visibility decision recorded (public, deliberate); console auth posture documented in CONTEXT.md.
- **R11:** v2 bulk-import enable switch moved from client-controlled request param to server-side env var `V2_IMPORT_ENABLED`; glob fix (select newest backup by mtime); truncation reporting (COUNT + paginated fetch, `truncated: true` + `total_available`). 3 new tests.
- **R12:** Tenant strings genericized in `src/templates/business_profile.html` (placeholders), `src/templates/sources_engine.html` ("a previous pipeline backup"), `prompts/sources_engine/analyze_v1.md` (parameterized `{business_region}`), `prompts/voice_profile/analyze_v1.md` ("e.g. regional dialects"). Zero-tenant-strings test extended to templates + prompts. 3 new tests.
- **R13:** BUILD_PLAN M2 reordered — T2.9 (gate-token enforcement) pulled forward before T2.3, scope expanded to cover ModuleStore.store() + both config-yaml write paths + all playbook store endpoints.
- **R14:** Config yaml writes now archive before overwrite (`config/archive/{name}-{timestamp}.yaml`). 3 new tests.
- **R15:** Queued (derive gate step from parsed playbook, land during M2).
- **R16:** Binding constraint on T2.6–T2.8: VPS audio resource plan (never hold both models in memory, synthesis as background job, smoke-test Qwen3-TTS on VPS first, T2.7 AC amended with batch-window requirement).
- 142 tests passing (133 + 9 new).

### 2026-07-02 STRUCTURE — Inbox batch B filed + AMENDMENT-004 PROPOSED (awaiting operator)
**Rationale:** Second inbox batch filed per Inbox Protocol. REVIEW-M2-MIDPOINT → `docs/reviews/`; AMENDMENT-004 (treatment block on idea cards) → `docs/decisions/` with status PROPOSED — filed but NOT applied. GitHub issue opened for operator approval. Existing reviews moved into `docs/reviews/`. Manifest → `docs/inbox/processed/`.

### 2026-07-02 STRATEGIC — Charter bumped to v3.3 (AMENDMENT-004: treatment block on idea cards)
**Rationale:** Daimon approved AMENDMENT-004. Charter v3.2 → v3.3. Idea cards now carry a **treatment** (scope, format from Format Guide, capture-required tasks, reuse links, rationale) approved WITH the idea at Gate 1 — not developed after. Format experimentation mechanism: new formats debut inside treatments, one approval admits the format to the guide. Awaiting-capture state for cards with outstanding capture tasks. Provenance requirement expanded: `format` and `scope` travel alongside `origin` to the nightly note. Charter renamed from `CHARTER-v3.2.md` to `CHARTER-v3.3.md`; all references updated. CONTEXT.md: idea-card + treatment + origin definitions updated. BUILD_PLAN M3 expanded to 12 tasks (treatment block, awaiting-capture, series spawning, experimental-format debut, format+scope threading). T2.3 Format Guide schema enrichment noted. GitHub issue #1 closed.

### 2026-07-02 BUILD — T2.5 + T2.10 + T2.11 + R15 applied; 254 tests; deployment live
**Rationale:** T2.5 (module store schema-check on load + version history visible in console), T2.10 (security fixes: materials column allowlist + llm_adapter single-pass substitution), T2.11 (provenance business_slug column + threading), R15 (gate step derivation from parsed playbook) all landed. 254 tests passing. Deployed to VPS: gunicorn + systemd + Traefik reverse proxy. Basicauth middleware on public route (per architect R10 posture). Tailscale URL (http://100.96.184.48:9121) is the approved operator review URL.

### 2026-07-02 INBOX — Batch C filed (diagram v3.3 + ops flags)
**Rationale:** Third inbox batch from architect. `system-overview-v3.3.svg` → `docs/diagrams/` (v3.2 left in place, superseded). `diagrams-README_2.md` → `docs/diagrams/README.md` (REPLACE). Manifest → `docs/inbox/processed/`. APPLY: (1) CONTEXT.md diagram pointer updated v3.2 → v3.3 with new flow (Gather → Ideas+Treatment → Awaiting-Capture → Draft → Assets → Publish → Learn). (2) BLOCKING OPS: no public DNS until Traefik basicauth — basicauth middleware added via usersFile approach, tested 401 without auth + 200 with auth. Deployment artifacts committed to `deploy/` (traefik config, systemd service, env example). (3) T2.6–T2.8 deferral recorded formally in BUILD_PLAN + PROGRESS.md — review-w2 must NOT be tagged until audio/voice tasks land. (4) Tailscale URL confirmed as operator review URL.
---

### 2026-07-03 TECH/FIX/LOGIC — CORRECTION-orchestrator-drafting-and-ux-v1.0 fully implemented

**What:**
- **P0-1 (FIX):** Drafting input starvation root cause — routed_seeds persisted, per-doc drafting package (seeds + transcript + 24k materials), 8 v2 prompts, shot_library_summary from real materials, unresolved-placeholder check in _render_prompt.
- **P0-2 (FIX):** Validation crash on next_focus null — removed from required, validator coerces None→"", retry includes actual error text, friendly operator error copy.
- **P1-1 (STRUCTURE):** Gate relocation to Library — ModuleStore.store gains status param, draft/approved badges, inline edit, approve action with gate token, drafts stored immediately on orchestration.
- **P1-2 (FIX):** Conversation continuity — structured conversation_turns passed to template, full history rendered on page load, "← Console" back link, auto-save notice, gate cards replaced with draft acknowledgments linking to /library.
- **P1-3 (FIX):** Readback rendering — no raw str(dict)[:60], unknown dicts render key:value untruncated, empty sections omitted, nested dicts handled.
- **P1-4 (FIX):** Upload feedback — immediate "uploading…" chip with spinner, error chip with retry on failure, failed uploads never added to pendingFiles.
- **P2-1 (OPS):** Conversational latency — active.converse backend role (ollama_gpt_oss_120b), adapter falls back to default if not configured.
- **P2-2 (LOGIC):** Orchestrator prompt v2 — agency-intake posture, one-line doc definitions, mine materials before asking, aggressive verbatim seed extraction, never end without question.
- **Transcription (TECH):** faster-whisper background daemon, transcription_status column (additive migration), backfill on startup, get_corpus excludes pending/failed audio, wired into create_app.

**Rationale:** CORRECTION-orchestrator-drafting-and-ux-v1.0.md from architect review of commit 372f81e following operator's first end-to-end onboarding run. All thin/empty documents shared one root cause (P0-1) — fixed first. Definition of Done (PROCESS-definition-of-done-v1.0.md) now binding.

**Test suite:** 375 passing (18 new regression tests). Service restarted, health OK.

---

### 2026-07-03 OPS — Inbox batch -c + -d filed (pipeline UX, voice cloning, final assembly)

**What:** Two manifests (-c, -d) delivering 5 files filed per instructions:
- `CORRECTION-pipeline-ux-and-media-generation-v1.0.md` → `docs/reviews/`
- `DECISION-voice-cloning-vo-v1.0.md` → `docs/decisions/`
- `CORRECTION-final-assembly-and-materials-editing-v1.0.md` → `docs/reviews/`
- Manifests -c and -d → `docs/inbox/processed/`

**Scope of the batch (build order per manifest -c note 1):**
1. Pipeline UX: shared `static/busy.js` + server-side `jobs` table with in-flight idempotency (F1). Self-audit flags become actionable with Apply/Dismiss (F2). Visual direction required in DRAFT_SCHEMA with minItems:1 and prompt v2 (F3). Media generation via OpenRouter — `src/media_adapter.py`, config in `models.yaml`, `asset_media` table (F4). Assets page becomes publish-preview card with platform framing (F5).
2. Voice cloning: Chatterbox (MIT, self-hosted), voice reference set as 9th onboarding coverage item, `voices` table, VO generation as async job on shared `jobs` framework. Operator listening test is the one non-self-certifiable gate.
3. Final assembly engine: LLM produces Edit Plan (JSON schema) → deterministic FFmpeg/MoviePy v2 renderer. Stock library via Pexels/Pixabay. Editable Materials Library (`/materials`, normalize-content editing, exclude toggle). Whisper gains word-timestamp alignment mode.

**New dependencies (noted for deployment):** `OPENROUTER_API_KEY`, `PEXELS_API_KEY`, `PIXABAY_API_KEY` env vars; pip `chatterbox-tts`, `moviepy` v2; apt `ffmpeg`. RAM budget: Whisper medium + Chatterbox may not co-reside on VPS — measure, decide, record.

**Build order:** Materials Library (Part 2, independent) → jobs table + busy states (F1, shared infra) → Whisper worker (already built, gains alignment mode) → gate/continuity fixes already done → F2/F3 → F4/F5 media + preview → voice reference set + Chatterbox VO → assembly engine (last, depends on all). Two operator-eared gates: cloned-voice listening test, publish-preview "does this look like a post" judgment.

**Rationale:** Architect batch following operator's second hands-on review round. Filed before any new milestone work per inbox protocol. No charter conflicts identified.

---

### 2026-07-03 BUILD — Materials Library (CORRECTION-final-assembly Part 2)

**What:**
- DB migrations: `excluded` INTEGER column on `materials` + `material_edits` table (material_id, edited_at, before_hash). Additive, backward-compatible.
- `MaterialsIntake.save_edit()` — writes to `normalized_content` only, logs before-hash to `material_edits`, recomputes `word_count`. `raw_content` is never touched.
- `MaterialsIntake.restore_to_raw()` — re-copies `raw_content` → `normalized_content`, logged as an edit.
- `MaterialsIntake.toggle_exclude()` — sets `excluded` flag; `get_corpus()` skips excluded materials. Excluded ≠ deleted.
- Flask routes: `GET /materials` (list with run/channel filters), `GET /materials/<id>` (detail), `POST /api/materials/<id>/edit`, `/exclude`, `/restore`.
- Templates: `materials.html` (list with excerpts, excluded badges, filters), `material_detail.html` (editable textarea, raw read-only section, exclude/restore buttons, edit history), `error.html`.
- Nav: Materials link added to `index.html` and `library.html`.
- 19 new tests (394 total). Live server verified via curl: edit, restore, exclude all work against real data.

**Rationale:** CORRECTION-final-assembly-and-materials-editing-v1.0 Part 2. Everything the operator shared is reviewable and editable. Transcripts contain errors; extraction picks up junk; an uncorrected transcription error becomes a "voice pattern." The content-hash cache means an edited material naturally changes the variables hash on the next drafting call — no cache invalidation machinery needed. Built first per manifest -c note 1 (independent, small, operator needs it to correct transcripts as soon as Whisper lands).

