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
- [ ] T2.12 **AMENDMENT-005** — Extract hardcoded module→prompt mappings into `config/processes.yaml` + compose-and-run engine — AC: ideas and draft routes contain zero inline module wiring; magic truncation slices (`[:2000]`, `[:1500]`) gone; every provenance row records registry version; process registry is versioned data with gate-only writes (the 9th module)
- [ ] **Checkpoint:** operator end-to-end test (review-w1_1.md checklist, with R10 deployment posture in place). Tag `review-w2`. **NOTE: review-w2 must NOT be tagged until T2.6–T2.8 land (or a divergence re-scopes M2).** The operator end-to-end test may run without the speak-a-sample path in the interim; the full test re-runs when audio lands.

### M3 — Co-production loop (staged pipeline per AMENDMENT-003 + treatment block per AMENDMENT-004; est. weeks 5–6)
- [x] T3.1 Idea card generation (with treatment block per AMENDMENT-004): AI-originated ideas from Source Bank × modules; human-seeded and human-seeded-ai-developed paths. Each card: idea, hook/title options, **treatment** (scope: one_off | series_of_n | pillar_with_derivatives; format from Format Guide; capture_required tasks; reuse links; rationale), `origin` tag, evidence links — AC: cards from all 3 origins producible; origin + treatment present on every card
- [x] T3.2 Ideas gate UI (Gate 1 — rigorous): card queue with origin badge, hook options, evidence links, compact treatment line (scope · format · capture flag), expandable full treatment (all editable per D1 direct-edit authority); approve / kill / park per card; kill reasons → Feedback Log — AC: kill reason logged; approved cards flow to Draft (or awaiting-capture if capture_required ≠ none); parked cards retrievable. **Per AMENDMENT-005:** seed + modules **per the draft process spec** → draft; implementation goes through the compose-and-run engine.
- [x] T3.3 Awaiting-capture state: cards approved with capture_required ≠ none enter awaiting-capture; capture task list shown; uploads flow through existing materials intake; audio transcribed via T2.6; transcript becomes draft input — AC: awaiting-capture card with outstanding tasks shown separately; fulfilled capture triggers flow to Draft
- [x] T3.4 Seed intake: typed + audio with transcription — AC: a 30-second voice note becomes a stored seed and generates a human-seeded idea card with treatment
- [x] T3.5 Drafter: approved idea card + ALL modules → draft (full text in voice + light visual direction block: image prompts, reference notes, shot/format choices) → self-audit vs Tells Checklist → flagged lines — AC: flags visible with the rule that fired; visual direction block present in draft schema; NO rendered images; prompts in `prompts/draft/`
- [x] T3.6 Human pass UI (Gate 2): per-line reaction chips + typed feedback **+ direct-edit mode** (editable draft; human text authoritative, overrides AI; logged to Feedback Log at highest weight with the draft version) — AC: reaction path and edit path both produce Feedback Log entries; revise honors both; ship-forward/kill works
- [x] T3.7 Assets stage: for ship-forward drafts — real images generated per visual direction + Visual Style Guide; captions rendered; per-platform fan-out (X thread, IG carousel/reel, …) — AC: images generated from visual direction block; per-platform variants produced from Format Guide
- [x] T3.8 Assets gate UI (Gate 3 — quick, per platform): per-platform variants shown side by side; approve / fix / kill per variant — AC: per-variant approve/fix/kill works; approved variants flow to Publish
- [x] T3.9 `origin` + `format` + `scope` threaded through pipeline: idea card → draft → assets → results tables; nightly performance note records all three — AC: tags travel end-to-end; nightly note includes origin + format + scope breakdown
- [x] T3.10 Series spawning: approval of a `series_of_n` treatment spawns linked child cards sharing `parent_id` + cadence — AC: child cards created with parent link; cadence hands scheduled dates to Publish gate
- [x] T3.11 Experimental-format debut: card approval with `experimental: true` format auto-writes the Format Guide entry with provenance pointing at the debut card — AC: approving a card with experimental format creates the guide entry; no separate format-approval queue
- [x] T3.12 Manual publish handoff (Gate 4 — go/hold + timing) — AC: shipped pieces exportable per platform format from the Format Guide
- [ ] **Checkpoint:** 10-piece co-production sprint through the full staged pipeline. **Drafter A/B:** same seeds through two configured backends; operator reacts blind; winner set in `models.yaml`. Tag `review-w6`.

### M4 — Publish + metrics (est. week 7)
- [ ] T4.1 Postiz self-hosted install + API wiring — AC: piece scheduled and posted from console **only after explicit per-piece approval**; failures alert; no data loss
- [ ] T4.2 Metrics collection (cron) — AC: nightly pull runs unattended 7 days

### M5 — Inward learning loop + async gate (est. week 8)
- [ ] T5.1 Proposal job (scheduled weekly): results + Feedback Log (direct edits weighted highest) → proposals with evidence + target module + exact diff — AC: specific and actionable, never vibes. **Per AMENDMENT-005:** proposal targets widen to include the process registry alongside the eight modules.
- [ ] T5.2 **Gate as persistent async queue** — AC: proposals accumulate with visible age ("submitted N days ago"); pending counter across all types; approve = version bump with provenance; reject = quick-reason chips; **superseding**: newer proposal on the same module section marks the older superseded (visible, not deleted); no deadline/pressure mechanics anywhere. **Per AMENDMENT-005:** gate queue handles mapping proposals identically (evidence + exact diff).
- [ ] T5.3 Voice Profile update path from Feedback Log per playbook — AC: an approved pattern lands as a versioned entry

### M6 — Outward research loop (est. weeks 9–10; charter: continuous from v1 of this phase)
- [ ] T6.1 Research job v1: YouTube Data API against `sources.yaml` — AC: scheduled pulls; nothing hardcoded
- [ ] T6.2 Analysis per winner (hook/structure/format/emotion/pacing; hypothesis-framed field required) → Source Bank — AC: validator enforces the hypothesis field
- [ ] T6.3 Proposals + Experiments Queue → gate; approved experiments appear as seed suggestions — AC: an approved experiment flows into Pick + seed
- [ ] T6.4 Sources Engine Part B: discovery + scoring + proposed additions/prunes + criteria-amendment proposals — AC: all through the gate; scraper service config-keyed and swappable. **Per AMENDMENT-005:** outward-loop proposals may also target mappings (e.g. "load visual-style into ideation for this domain").

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
