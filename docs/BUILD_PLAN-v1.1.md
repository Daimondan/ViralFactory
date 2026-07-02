# BUILD_PLAN.md — ViralFactory

*Instructions to the builder agent (Hermes). Read `docs/CHARTER-v3.2.md` and all of `playbooks/` before writing any code. This file is the single source of truth for what to build and in what order. v1.2 — 2026-07-02 — updated per AMENDMENT-003 (staged content pipeline: four content gates, ideas stage, assets stage, provenance `origin` field).*

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
- trafilatura for extraction · **Postiz self-hosted** for publish/metrics · modules as markdown in `modules/{business}/` (system of record; OB1 mirror optional, later) · cron for scheduling.

## Milestones

### M0 — Foundations (est. week 1)
- [x] T0.1 Repo layout: `config/ prompts/ playbooks/ modules/ src/ tests/ docs/` — AC: matches charter; README maps folders to charter concepts; playbooks split into individual files under `playbooks/`
- [x] T0.2 Config loader: `business.yaml`, `models.yaml`, `sources.yaml` with schema validation — AC: bad config fails loudly; no hidden defaults in code
- [x] T0.3 LLM adapter — AC: backend switch via `models.yaml` only; retry-once on invalid JSON then flag "manual review"; temperature 0 default
- [x] T0.4 Validator: JSON-schema + allowlist checks — AC: unknown tag rejected in test; missing field rejected
- [x] T0.5 Provenance log — AC: every adapter call writes a row; test proves it
- [x] T0.6 Content-hash cache — AC: same input twice = one LLM call
- [x] T0.7 **v2 database backup**: scripted, verified copy of the v2 SQLite DB to storage outside the v2 app directory — AC: restore tested once; backup location documented in `docs/CONTEXT.md`. (Fresh start ≠ data destruction.)

### M1 — Onboarding engine: runner + Voice Profile (est. weeks 2–3)
- [x] T1.1 Generic playbook runner (procedure steps → console flows → gates) — AC: proven generic by running a trivial test playbook
- [x] T1.2 Materials intake UI per `docs/INTAKE-USER1.md` — AC: WhatsApp export, plain text, audio (transcribed) all ingest; other parties' text stripped
- [x] T1.3 Voice Profile playbook end-to-end — AC: schema-valid profile; every finding carries verbatim evidence (validator enforces); dialect preserved
- [x] T1.4 Calibration gate UI (3 samples → pick + react → revise, max 3 rounds) — AC: v1.0 stored with provenance only on confirmation; v0.9 fallback path works
- [x] T1.5 Interview fallback — AC: profile buildable from interview answers alone
- [ ] **Checkpoint:** operator onboards their own voice. Tag `review-w1`.

### M2 — Remaining playbooks wired (est. week 4)
- [ ] T2.1 Business Profile intake → `business.yaml` + brand-context module — AC: tenant values re-entered via console; zero tenant strings in code
- [ ] T2.2 Sources Engine Part A: seed sources → Source Criteria (human-readable, evidenced) → `sources.yaml` — AC: criteria editable at gate; nothing hardcoded. Include the **optional deferred v2 bulk-import path** (reads the T0.7 backup; ships disabled)
- [ ] T2.3 Viral Patterns starter + Audience Insights + Story Frameworks + Format Guide playbooks — AC: each produces a schema-valid v1 via runner + gate
- [ ] T2.4 Visual Style intake + shot-library index — AC: module stored; index updatable
- [ ] T2.5 Module store: versioning, schema-check on load, gate-only writes — AC: silent edit impossible via API; version history visible

### M3 — Co-production loop (est. weeks 5–6)
- [ ] T3.1 Seed intake: typed + audio with transcription — AC: a 30-second voice note becomes a stored seed
- [ ] T3.2 Drafter: seed + ALL modules → draft → self-audit vs Tells Checklist → flagged lines — AC: flags visible with the rule that fired; prompts in `prompts/draft/`
- [ ] T3.3 Human pass UI: per-line reaction chips + typed feedback **+ direct-edit mode** (editable draft; human text authoritative, overrides AI; logged to Feedback Log at highest weight with the draft version) — AC: reaction path and edit path both produce Feedback Log entries; revise honors both; ship/kill works
- [ ] T3.4 Manual publish handoff — AC: shipped pieces exportable per platform format from the Format Guide
- [ ] **Checkpoint:** 10-piece co-production sprint. **Drafter A/B:** same seeds through two configured backends; operator reacts blind; winner set in `models.yaml`. Tag `review-w6`.

### M4 — Publish + metrics (est. week 7)
- [ ] T4.1 Postiz self-hosted install + API wiring — AC: piece scheduled and posted from console **only after explicit per-piece approval**; failures alert; no data loss
- [ ] T4.2 Metrics collection (cron) — AC: nightly pull runs unattended 7 days

### M5 — Inward learning loop + async gate (est. week 8)
- [ ] T5.1 Proposal job (scheduled weekly): results + Feedback Log (direct edits weighted highest) → proposals with evidence + target module + exact diff — AC: specific and actionable, never vibes
- [ ] T5.2 **Gate as persistent async queue** — AC: proposals accumulate with visible age ("submitted N days ago"); pending counter across all types; approve = version bump with provenance; reject = quick-reason chips; **superseding**: newer proposal on the same module section marks the older superseded (visible, not deleted); no deadline/pressure mechanics anywhere
- [ ] T5.3 Voice Profile update path from Feedback Log per playbook — AC: an approved pattern lands as a versioned entry

### M6 — Outward research loop (est. weeks 9–10; charter: continuous from v1 of this phase)
- [ ] T6.1 Research job v1: YouTube Data API against `sources.yaml` — AC: scheduled pulls; nothing hardcoded
- [ ] T6.2 Analysis per winner (hook/structure/format/emotion/pacing; hypothesis-framed field required) → Source Bank — AC: validator enforces the hypothesis field
- [ ] T6.3 Proposals + Experiments Queue → gate; approved experiments appear as seed suggestions — AC: an approved experiment flows into Pick + seed
- [ ] T6.4 Sources Engine Part B: discovery + scoring + proposed additions/prunes + criteria-amendment proposals — AC: all through the gate; scraper service config-keyed and swappable

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
