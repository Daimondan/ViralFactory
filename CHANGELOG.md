# CHANGELOG — ViralFactory

> **If you made a decision and it's not in the changelog, that is a bug.**

All decisions — tech, logic, structure, strategy, ops — logged here with type tag + rationale.

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

