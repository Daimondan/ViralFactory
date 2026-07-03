# BUILD_PLAN.md — ViralFactory

*Instructions to the builder agent (Hermes). Read `docs/CHARTER-v3.3.md` and all of `playbooks/` before writing any code. This file is the single source of truth for what to build and in what order. v1.4 — 2026-07-03 — updated per AMENDMENT-005 (processes are module compositions; process registry as 9th module; compose-and-run engine; T2.10 added; T3.2 reworded; M5/M6 targets widened).*

## How to work (non-negotiable)

1. **One task at a time, top-down.** Complete a task, check its box, commit with the task ID in the message, append one line to `docs/PROGRESS.md`. Never batch tasks in one commit.
2. **A task is done only when its acceptance criteria pass.** Can't meet them? Open a GitHub issue with the blocker; move to the next unblocked task. Never improvise around criteria.
3. **Review ritual.** At each milestone (or ~weekly), tag `review-wN`. Architect corrections arrive as `docs/reviews/`; read and apply them before new milestone work.
4. **Design questions go to `docs/decisions/` as divergence files** — never decided in code.

## Guardrails (violations are defects, even if the code "works")

- **No business values in code. Ever.** Brand names, topics, feeds, queries, taxonomies, limits, model names → `config/*.yaml`.
- **No judgment in code.** Understanding-tasks (tagging, titling, summarizing, voice analysis, quality calls) = prompt template in `prompts/` + JSON schema + validator. Never keyword heuristics — this rule exists because keyword matching once falsely tagged 65 of 80 sources.
- **Mechanics use boring libraries.** Extraction/boilerplate stripping = trafilatura or equivalent. No LLM calls for mechanical work.
- **Every LLM call logged** to provenance: input hash, prompt file + version, model, raw output, validated output, verdict.
- **Deterministic where possible:** temperature 0 for processing; content-hash cache — unchanged input is never re-judged.
- **Never invent module content.** Modules come from playbooks + user materials, updated only via the gate. Empty module → say so.
- **No patch scripts.** Wrong output → fix prompt/config/validator, versioned.
- **Small commits, tested.** Every task lands with at least one test; suite stays green.
- **Per-piece approval before publish is a hard business rule.** No code path may post without an explicit human approval on that piece.

## Stack (fixed unless the charter changes)

- **Fresh start:** new Flask app, new SQLite DB, new structure. No v2 code, schema, or data imports. v2 keeps running at its own address until cutover.
- Python + Flask, server-rendered, minimal JS; SQLite; systemd on the VPS.
- **UI: laptop-first (1280px+), responsive to mobile** per `docs/UI-DIRECTION.md` (patched per review). Multi-column layouts allowed on laptop.
- LLM adapter: `complete(prompt_file, variables, schema) -> validated JSON`; backend from `config/models.yaml` (Ollama local / Ollama Cloud / external API). Default: Ollama Cloud. Swap = config edit only.
- trafilatura for extraction · **Postiz self-hosted** for publish/metrics · modules as markdown in `modules/{business}/` (system of record — fully standalone, no OB1 dependency) · cron for scheduling.

## Milestones

### M0 — Foundations (est. week 1)
- [ ] T0.1 Repo layout: `config/ prompts/ playbooks/ modules/ src/ tests/ docs/` — AC: matches charter; README maps folders to charter concepts; playbooks split into individual files under `playbooks/`
- [ ] T0.2 Config loader: `business.yaml`, `models.yaml`, `sources.yaml` with schema validation — AC: bad config fails loudly; no hidden defaults in code
- [ ] T0.3 LLM adapter — AC: backend switch via `models.yaml` only; retry-once on invalid JSON then flag "manual review"; temperature 0 default
- [ ] T0.4 Validator: JSON-schema + allowlist checks — AC: unknown tag rejected in test; missing field rejected
- [ ] T0.5 Provenance log — AC: every adapter call writes a row; test proves it
- [ ] T0.6 Content-hash cache — AC: same input twice = one LLM call
- [ ] T0.7 **v2 database backup**: scripted, verified copy of the v2 SQLite DB to storage outside the v2 app directory — AC: restore tested once; backup location documented in `docs/CONTEXT.md`. (Fresh start ≠ data destruction.)

### M1 — Onboarding engine: runner + Voice Profile (est. weeks 2–3)
- [ ] T1.1 Generic playbook runner (procedure steps → console flows → gates) — AC: proven generic by running a trivial test playbook
- [ ] T1.2 Materials intake UI per `docs/INTAKE-USER1.md` — AC: WhatsApp export, plain text, audio (transcribed) all ingest; other parties' text stripped
- [ ] T1.3 Voice Profile playbook end-to-end — AC: schema-valid profile; every finding carries verbatim evidence (validator enforces); dialect preserved
- [ ] T1.4 Calibration gate UI (3 samples → pick + react → revise, max 3 rounds) — AC: v1.0 stored with provenance only on confirmation; v0.9 fallback path works
- [ ] T1.5 Interview fallback — AC: profile buildable from interview answers alone
- [ ] **Checkpoint:** operator onboards their own voice. Tag `review-w3`.

### M2 — Remaining playbooks wired (est. week 4)
*Revised order per REVIEW-M2-MIDPOINT R13: T2.9 pulled forward before T2.3.*

- [x] T2.1 Business Profile intake → `business.yaml` + brand-context module — AC: tenant values re-entered via console; zero tenant strings in code
- [x] T2.2 Sources Engine Part A: seed sources → Source Criteria (human-readable, evidenced) → `sources.yaml` — AC: criteria editable at gate; nothing hardcoded. Include the **optional deferred v2 bulk-import path** (reads the T0.7 backup; server-side env var switch)
- [x] T2.9 R7/R13 — Gate-token enforcement (ALL write paths): `ModuleStore.store()` requires a verified `gate_token`/approval record ID before writing; both config-yaml write paths (business.yaml, sources.yaml) require same; all playbook store endpoints require valid approval record — AC: call to `store()` without valid approval record raises; config write without approval raises; silent edit impossible via API; no `modules/unknown/` orphan possible (return 500 on missing slug)
- [x] T2.3 Viral Patterns starter + Audience Insights + Story Frameworks + Format Guide playbooks — AC: each produces a schema-valid v1 via runner + gate. **Format Guide schema enriched per AMENDMENT-004:** `requires_human_capture`, `effort_level`, `best_for`, `platforms`, `reuse_pathways`, `status` (proven | experimental | retired), `provenance`
- [x] T2.4 Visual Style intake + shot-library index — AC: module stored; index updatable
- [x] T2.5 Module store remaining: schema-check on load, version history visible — AC: invalid module can't be loaded by drafter; version history visible in console (gate enforcement absorbed by T2.9)
- [x] T2.10 R8 — Minor security fixes: (a) `materials._update_field()` column name allowlist; (b) `llm_adapter._render_prompt()` single-pass regex substitution to prevent double-substitution — AC: both fixed with tests
- [x] T2.11 R9 — Provenance gains `business_slug`: add column, thread through `LLMAdapter.complete()` and `ProvenanceLog.log()` — AC: every provenance row attributable to a tenant; guardrail note in BUILD_PLAN that no route/playbook/job references a model name directly
- [x] R15 — Derive gate step numbers from parsed playbook (not hardcoded in routes) — AC: gate step index derived from playbook markdown, not literal strings
- [ ] T2.6 Audio transcription — wire faster-whisper into MaterialsIntake; audio files transcribed on upload; model from config — AC: a 30-second voice note uploaded through the console produces transcribed text in the materials store — **DEFERRED: resequenced after operator UI review per architect batch C directive**
- [ ] T2.8 Voice sample management — store reference audio clips during onboarding; clips stored per-business in `modules/{business}/voice-samples/` — AC: at least 3 reference clips stored after onboarding; clips usable by the voice cloning adapter — **DEFERRED: resequenced after operator UI review per architect batch C directive**
- [ ] T2.7 Voice cloning adapter — `synthesize(text, reference_audio) -> audio_file`; model from config; reference audio from voice-samples directory — AC: given reference audio clips, the adapter produces an audio file of the text spoken in that voice on the production VPS within an acceptable batch window (operator defines acceptable; record measured time in PROGRESS.md) — **DEFERRED: resequenced after operator UI review per architect batch C directive**
- [x] T2.12 **AMENDMENT-005** — Extract hardcoded module→prompt mappings into `config/processes.yaml` + compose-and-run engine — AC: ideas and draft routes contain zero inline module wiring; magic truncation slices (`[:2000]`, `[:1500]`) gone; every provenance row records registry version; process registry is versioned data with gate-only writes (the 9th module)
- [ ] **Checkpoint:** operator end-to-end test (review-w1_1.md checklist, with R10 deployment posture in place). Tag `review-w2`. **NOTE: review-w2 must NOT be tagged until T2.6–T2.8 land (or a divergence re-scopes M2).** The operator end-to-end test may run without the speak-a-sample path in the interim; the full test re-runs when audio lands.

### M3 — Co-production loop (staged pipeline per AMENDMENT-003 + treatment block per AMENDMENT-004; est. weeks 5–6)
- [x] T3.1 Idea card generation (with treatment block per AMENDMENT-004): AI-originated ideas from Source Bank × modules; human-seeded and human-seeded-ai-developed paths. Each card: idea, hook/title options, **treatment** (scope: one_off | series_of_n | pillar_with_derivatives; format from Format Guide; capture_required tasks; reuse links; rationale), `origin` tag, evidence links — AC: cards from all 3 origins producible; origin + treatment present on every card
- [x] T3.2 Ideas gate UI (Gate 1 — rigorous): card queue with origin badge, hook options, evidence links, compact treatment line (scope · format · capture flag), expandable full treatment (all editable per D1 direct-edit authority); approve / kill / park per card; kill reasons → Feedback Log — AC: kill reason logged; approved cards flow to Draft (or awaiting-capture if capture_required ≠ none); parked cards retrievable. **Per AMENDMENT-005:** seed + modules **per the draft process spec** → draft; implementation goes through the compose-and-run engine.
- [x] T3.3 Awaiting-capture state: cards approved with capture_required ≠ none enter awaiting-capture; capture task list shown; uploads flow through existing materials intake; audio transcribed via T2.6; transcript becomes draft input — AC: awaiting-capture card with outstanding tasks shown separately; fulfilled capture triggers flow to Draft
- [x] T3.4 Seed intake: typed + audio with transcription — AC: a 30-second voice note becomes a stored seed and generates a human-seeded idea card with treatment
- [x] T3.5 Drafter: approved idea card + ALL modules → draft (full text in voice + light visual direction block: image prompts, reference notes, shot/format choices) → self-audit vs Tells Checklist → flagged lines — AC: flags visible with the rule that fired; visual direction block present in draft schema; NO rendered images; prompts in `prompts/draft/`
- [x] T3.6 Human pass UI (Gate 2): per-line reaction chips + typed feedback **+ direct-edit mode** (editable draft; human text authoritative, overrides AI; logged to Feedback Log at highest weight with the draft version) — AC: reaction path and edit path both produce Feedback Log entries; revise honors both; ship-forward/kill works
- [x] T3.7 Assets stage: for ship-forward drafts — real images generated per visual direction + Visual Style Guide; captions rendered; per-platform fan-out (X thread, IG carousel/reel, …) — AC: images generated from visual direction block; per-platform variants produced from Format Guide **(S3 correction: platform set resolved from treatment format's Format Guide entry, not blanket business config loop; native platform packaged verbatim)**
- [x] T3.8 Assets gate UI (Gate 3 — quick, per platform): per-platform variants shown side by side; approve / fix / kill per variant — AC: per-variant approve/fix/kill works; approved variants flow to Publish
- [x] T3.9 `origin` + `format` + `scope` threaded through pipeline: idea card → draft → assets → results tables; nightly performance note records all three — AC: tags travel end-to-end; nightly note includes origin + format + scope breakdown
- [x] T3.10 Series spawning: approval of a `series_of_n` treatment spawns linked child cards sharing `parent_id` + cadence — AC: child cards created with parent link; cadence hands scheduled dates to Publish gate
- [x] T3.11 Experimental-format debut: card approval with `experimental: true` format auto-writes the Format Guide entry with provenance pointing at the debut card — AC: approving a card with experimental format creates the guide entry; no separate format-approval queue
- [x] T3.12 Manual publish handoff (Gate 4 — go/hold + timing) — AC: shipped pieces exportable per platform format from the Format Guide
- [x] T3.13 Generation diversity & fan-out fidelity (per CORRECTION-generation-diversity-and-asset-continuity-v1.0): (S1) ideator backend with real temperature + existing-ideas/kill-lessons context + mechanical source snapshot; (S2) format-usage feedback into treatments; (S3) fan-out platform set from Format Guide entry, native platform verbatim; (S4) draft previews carried into assets — AC: consecutive idea runs non-identical with novelty context in provenance; native-platform asset text byte-equal to approved draft; draft previews carried into assets; format-usage variable present with real counts
- [x] **Checkpoint:** 10-piece co-production sprint through the full staged pipeline. **Drafter A/B:** same seeds through two configured backends; operator reacts blind; winner set in `models.yaml`. Tag `review-w6`. **NOTE: do NOT run until T3.13 (S1+S3) lands — would measure a broken generator.** *(Sprint run 2026-07-03: 10 cards generated with ideator backend, 0 overlap between batches, native fan-out verbatim verified. Drafter A/B deferred — ab_candidate is null.)*

### M4 — Publish + metrics (est. week 7)
- [x] T4.1 Postiz self-hosted install + API wiring — AC: piece scheduled and posted from console **only after explicit per-piece approval**; failures alert; no data loss
- [x] T4.2 Metrics collection (cron) — AC: nightly pull runs unattended 7 days

### M8 — Source grounding + auto-production chain + AI profiles (per CORRECTION-source-grounding-and-auto-production-v1.0)
- [x] T8.1 Kill remaining truncation (P0): remove `source_material[:4000]` in `ideas_generate`; replace with count-bounded digest view (most recent N active sources, ID + title + summary per item, recency-ordered); retire `SNAPSHOT_CHAR_CAP` in favor of per-item summary limits + item-count bounds — AC: grep for `[:4000]`, `[:2000]`, `[:1500]` across `src/` returns none on module/source injection paths; ideas prompt receives digest view bounded by count, not character slicing
- [x] T8.2 Housekeeping (P0): remove dead `response_data` block in `ideas_gate_decision` (series branch); add CONTEXT.md lines: (a) every idea cites sources by ID, one idea may compose multiple sources; (b) Gate 1 approval triggers production automatically, publishing is never automatic; (c) AI work runs under named profiles defined in config/profiles.yaml — AC: dead code removed; CONTEXT.md updated with three new lines
- [ ] T8.3 Source Bank table (P1): new `sources` table (id, business_slug, source_type, title, url, summary, content, origin, first_seen, content_hash, status); `source_snapshot.py` writes fetched items into this table (dedupe on content_hash) as `source_type='rss_item'`; materials intake registers `source_type='operator_material'` rows; `business_slug` scoping everywhere — AC: snapshot items appear as `sources` rows; operator materials appear as `sources` rows; dedupe on content_hash works
- [ ] T8.4 Idea cards carry source_refs (P1): new `source_refs` column (JSON list of sources.id, one or more); `evidence_links` becomes derived display field; `prompts/ideas/generate_v1.md` rebuilt — source material section shows `[S14] title — summary` per active source; card schema replaces free `evidence_links` with `source_refs: [14, 22]` + optional per-ref note; new rule: "Every idea MUST cite at least one source by ID; ideas synthesizing ≥2 sources are encouraged"; validation rejects/quarantines cards with unresolved source_refs; human seeds auto-register as `manual` source; ideas page renders resolved source list (title as link, source_type badge) — AC: unresolved source_refs rejected; every rendered card lists sources with links + type badges; at least one multi-source card cites ≥2 sources with per-source rationale
- [ ] T8.5 Sources flow to production (P1): `prompts/draft/generate_v2.md` → v2.3 adds `{grounding_sources}` section — full content of every source in card's `source_refs`, labeled with title + ID, instruction that facts/quotes/dates/specifics must come from these sources and fabricating specifics not in them is prohibited; `draft_generate` resolves `source_refs` to assemble this variable; empty content degrades to summary with `(summary only)` marker (never silent); fan-out and visual prompts receive source titles/notes only — AC: draft prompt payload for auto-produced draft contains full content of every cited source (inspectable via provenance)
- [ ] T8.6 Auto-production chain (P1): Gate 1 approval starts production — `ideas_gate_decision` on approve: if capture_required → awaiting_capture (chain fires on capture completion), else → approved + enqueue `produce_chain(card_id)` job; card state advances through `producing` → `asset_ready` (new states); `produce_chain` steps: (1) draft generation with grounding sources, (2) fan-out, (3) visual generation for image-required formats; failure → `production_failed` with step name + error surfaced in plain language + "Retry from failed step" control; series parent approval spawns children as today (state new, each child's own approval triggers its own chain); Create page restructured — "Approved ideas (ready to draft)" replaced by "In production" + "Ready for review"; concurrency: serialize per business (single worker queue); **DO NOT ENABLE until T8.3-T8.5 land** — AC: approving a capture-free idea produces, with zero further clicks, a reviewable asset (draft text + per-platform variants + previews) or plain-language failure with retry; verified end-to-end on console
- [ ] T8.7 AI Profiles (P1): new `config/profiles.yaml` (Researcher: ideation + source scouting, generative temp; Drafter: produces final asset from approved idea, generative temp; Analyst: reads results, drives loops, temp-0 class); each pipeline LLM call declares profile; `llm_adapter` resolves model/temperature through profile → `models.yaml` roles; provenance rows gain `profile` column; operator-visible copy may name profiles — AC: provenance rows carry producing profile; profile resolution test covers all three profiles

### M5 — Inward learning loop + async gate (est. week 8)
- [x] T5.1 Proposal job (scheduled weekly): results + Feedback Log (direct edits weighted highest) → proposals with evidence + target module + exact diff — AC: specific and actionable, never vibes. **Per AMENDMENT-005:** proposal targets widen to include the process registry alongside the eight modules.
- [x] T5.2 **Gate as persistent async queue** — AC: proposals accumulate with visible age ("submitted N days ago"); pending counter across all types; approve = version bump with provenance; reject = quick-reason chips; **superseding**: newer proposal on the same module section marks the older superseded (visible, not deleted); no deadline/pressure mechanics anywhere. **Per AMENDMENT-005:** gate queue handles mapping proposals identically (evidence + exact diff).
- [x] T5.3 Voice Profile update path from Feedback Log per playbook — AC: an approved pattern lands as a versioned entry

### M6 — Outward research loop (est. weeks 9–10; charter: continuous from v1 of this phase)
- [x] T6.1 Research job v1: YouTube RSS feeds against `sources.yaml` — AC: scheduled pulls; nothing hardcoded *(uses YouTube RSS feeds instead of Data API — no API key required, feedparser-based)*
- [x] T6.2 Analysis per winner (hook/structure/format/emotion/pacing; hypothesis-framed field required) → Source Bank — AC: validator enforces the hypothesis field
- [x] T6.3 Proposals + Experiments Queue → gate; approved experiments appear as seed suggestions — AC: an approved experiment flows into Pick + seed
- [x] T6.4 Sources Engine Part B: discovery + scoring + proposed additions/prunes + criteria-amendment proposals — AC: all through the gate; scraper service config-keyed and swappable. **Per AMENDMENT-005:** outward-loop proposals may also target mappings (e.g. "load visual-style into ideation for this domain").

### M7 — Generalization proof (when a real business #2 exists)
- [ ] T7.1 Onboard business #2 entirely through the console — AC: **zero code changes**
- [ ] T7.2 `docs/OPERATOR.md` — end-user manual, no technical steps
- [ ] **Checkpoint:** tag `review-final`; full architect review against the charter.

## PROGRESS.md format
```
2026-07-08 · T0.3 · LLM adapter done, Ollama Cloud + local tested, retry path covered · Q: none
```

## Definition of system-level done
A person with ideas but no content skills, no coding, and no Claude account can: log in → upload/speak their materials in one session → get a calibrated voice → co-create pieces (reacting, or editing directly when they choose) → approve each piece → have the system publish, measure, research the domain, and queue its own improvement proposals — every one passing their asynchronous approval. And a second such person can do the same with zero code changes.
