# BUILD_PLAN.md — ViralFactory

*Instructions to the builder agent (Hermes, open-source models). Read `docs/CONTEXT.md` and all of `playbooks/` before writing any code. This file is the single source of truth for what to build and in what order. v2.0 — 2026-07-02 — supersedes v1.0 (fresh start, no v2 extension).*

## How to work (non-negotiable)

1. **One task at a time, top-down.** Complete a task, check its box, commit with the task ID in the message, append one line to `docs/PROGRESS.md` (date · task ID · what changed · any open question). Never batch tasks in one commit.
2. **A task is done only when its acceptance criteria pass.** If criteria can't be met, do not improvise around them — open a GitHub issue describing the blocker and move to the next unblocked task.
3. **Weekly review ritual.** Every 7 days (or at each milestone), tag the repo `review-wN`. The operator shares the repo with Claude (the architect). Claude's review lands as `docs/reviews/review-wN.md` — read it and apply corrections before new milestone work.
4. **When uncertain, ask — in the repo.** Open an issue. Do not guess at design intent; `docs/CONTEXT.md` and playbooks are the intent.
5. **Log every decision in `CHANGELOG.md`.** If you made a decision and it's not in the changelog, that is a bug.

## Guardrails (violations are defects, even if the code "works")

- **No business values in code. Ever.** Brand names, topics, feeds, queries, tag taxonomies, limits, model names → `config/*.yaml`. If a string describes the business, it is config.
- **No judgment in code.** Anything requiring understanding (tagging, titling, summarizing, quality calls, voice analysis) is an LLM step: prompt template in `prompts/` + JSON output schema + validator. Never regex/keyword heuristics for judgment.
- **Mechanics use boring libraries.** Content extraction/boilerplate stripping = trafilatura. Do not spend LLM calls on mechanical work.
- **Every LLM call is logged** to the provenance store: input hash, prompt file + version, model (from config), raw output, validated output, validator verdict.
- **Deterministic where possible:** temperature 0 for processing steps; cache by content hash — an unchanged input is never re-judged.
- **Never invent module content.** Modules are built by playbooks from user materials and updated only via the gate. If a module is empty, the correct behavior is to say so, not to fill it.
- **No new patch scripts.** If output is wrong, the fix is in the prompt, config, or validator — committed and versioned — never a one-off fix.
- **Each task lands with at least one test.** Keep tests green.
- **Direct edits are authoritative.** When the user writes/edits draft text, it overrides the AI draft. The UI must support this.
- **Per-piece approval is non-negotiable.** No auto-publish, ever.
- **Gate is async.** Proposals accumulate in a persistent queue; the user clears when ready. No "weekly session" pressure.

## Stack (fixed unless the charter changes)

- Python + Flask console (new app, fresh start — NOT extending v2)
- SQLite (new database, no v2 schema reuse)
- systemd on the VPS (Restart=always)
- LLM adapter: one function, backend from config — Ollama local / Ollama Cloud / external API. Model swap = config edit, zero code change.
- trafilatura for content extraction
- Postiz (self-hosted or cloud — TBD) for publish/metrics
- Module storage: repo markdown in `modules/{business}/` (OB1 as optional mirror for user #1 — TBD)
- Scheduling: cron (keep it boring)

## Open questions (resolve before the noted milestone)

| # | Question | Blocks by | Recommendation |
|---|---|---|---|
| 1 | Module storage: repo markdown vs OB1 | M2 | Repo markdown as source of truth |
| 2 | Postiz self-host vs cloud | M4 | Cloud initially, self-host when customer #2 |
| 3 | LLM backend default | M0 | Ollama Cloud (existing subscription) |
| 4 | 8 modules in context window — all at once or essential 4 + on-demand | M3 | Claude architect to advise |
| 5 | Video generation scope in v1 | M3 | Text/image first, video in M3+ |

## Milestones

### M0 — Foundations (est. week 1)
**Goal:** Repo structure, config system, swappable LLM adapter, validator, provenance, cache. No business logic, no UI.

- [ ] T0.1 Repo layout: `config/ prompts/ playbooks/ modules/ docs/ src/ tests/` — AC: matches CONTEXT.md structure; README maps folders to concepts; existing docs moved into `docs/`
- [ ] T0.2 Config loader: `business.yaml`, `models.yaml`, `sources.yaml` with schema validation — AC: bad config fails loudly with a clear message; no defaults hidden in code; all StackPenni values in config, none in code
- [ ] T0.3 LLM adapter: `complete(prompt_file, variables, schema) -> validated JSON` — AC: backend switch via `models.yaml` only; retry-once on invalid JSON then flag "manual review"; temperature 0 default
- [ ] T0.4 Validator: JSON-schema check + allowlist checks (e.g., topics only from taxonomy) — AC: unknown tag rejected in test; missing field rejected
- [ ] T0.5 Provenance log (SQLite table) — AC: every adapter call writes a row; test proves it
- [ ] T0.6 Content-hash cache — AC: same input twice = one LLM call

### M1 — Onboarding engine: runner + Voice Profile (est. weeks 2–3)
**Goal:** A user can upload materials and get a calibrated Voice Profile through the console.

- [ ] T1.1 Playbook runner: executes a playbook's steps (intake → LLM steps → gate) as console flows — AC: playbook = markdown + prompts, runner is generic (proven by running a trivial test playbook)
- [ ] T1.2 Materials intake UI: upload/paste, type + date + audience tags per sample — AC: WhatsApp export, plain text, and transcript all ingest; other parties' text stripped per playbook Step 2
- [ ] T1.3 Voice Profile playbook end-to-end — AC: from real materials to draft profile matching the output schema; every finding carries verbatim evidence (validator enforces)
- [ ] T1.4 Calibration gate UI: 3 samples → pick + react → revise loop (max 3) — AC: v1.0 stored with provenance only after user confirmation; v0.9 path works
- [ ] T1.5 Interview fallback: guided Q&A flow producing a corpus — AC: profile buildable from interview answers alone
- [ ] T1.6 Direct-edit support in calibration: user can edit sample text directly — AC: edited text stored as authoritative; edit logged in Feedback Log with higher weight than chip reactions
- [ ] **Checkpoint:** operator (user #1) onboards their own voice through the console. Tag `review-w3`.

### M2 — Remaining playbooks wired (est. week 4)
**Goal:** All 8 modules buildable through the console.

- [ ] T2.1 Source discovery playbook: business.yaml + user Q&A → proposed feeds/accounts/channels/queries → gate → `sources.yaml` + Source Bank — AC: zero StackPenni-specific queries in code
- [ ] T2.2 Audience Insights + Story Frameworks + Format Guide starter playbooks — AC: each produces a schema-valid v1 module via the runner + gate
- [ ] T2.3 Visual Style intake: brand look Q&A + shot-library index — AC: module stored; index updatable
- [ ] T2.4 Module store: versioning, schema check on load, gate-only writes — AC: silent edit impossible via API; version history visible in console
- [ ] T2.5 Library UI: read-only browse of all modules with version history and provenance — AC: user can see what the machine believes and why
- [ ] **Resolve open question #1** (module storage) before T2.4

### M3 — Co-production loop (est. weeks 5–6)
**Goal:** A user can go from seed to approved piece through the console.

- [ ] T3.1 Seed intake: text + audio upload with transcription — AC: a 30-second voice note becomes a stored seed
- [ ] T3.2 Drafter: seed + ALL current modules → draft → self-audit pass against Tells Checklist → draft + flagged lines — AC: flagged lines visible in console; prompt in `prompts/draft/`
- [ ] T3.3 Reaction UI: per-line reactions via typed text OR tap chips → Feedback Log; revise → ship/kill — AC: every reaction stored with the draft version it applied to
- [ ] T3.4 Direct-edit mode: user can edit draft text directly in the draft view — AC: edited text overrides AI draft; edit logged as authoritative; Feedback Log records the edit with higher weight
- [ ] T3.5 Manual publish handoff (copy/queue) — AC: shipped pieces exportable per platform format from Format Guide
- [ ] **Resolve open questions #4 and #5** before T3.2
- [ ] **Checkpoint:** 10-piece co-production sprint by the operator (~15–20 min each). Tag `review-w6`.

### M4 — Publish + metrics automation (est. week 7)
**Goal:** Approved pieces auto-publish via Postiz; metrics flow back.

- [ ] T4.1 Postiz install + API wiring; scheduled posting from the shipped queue — AC: piece scheduled and posted from console; failures alert, never lose data
- [ ] T4.2 Metrics collection job (cron): per-piece results into SQLite — AC: nightly pull runs unattended for 7 days
- [ ] **Resolve open question #2** (Postiz self-host vs cloud) before T4.1

### M5 — Inward learning loop (est. week 8)
**Goal:** System proposes module updates; user approves via async queue.

- [ ] T5.1 Weekly proposal job: results + Feedback Log → LLM analysis → proposed module updates, each with evidence + target module + exact diff — AC: proposals are specific and actionable, not vibes
- [ ] T5.2 Async gate queue UI: persistent queue, "N pending" counter, approve/reject per proposal, bulk actions for low-risk proposals, "submitted N days ago" staleness indicator — AC: queue persists across sessions; no weekly reset; one-sitting clear possible but not required
- [ ] T5.3 Voice Profile update path from Feedback Log — AC: an approved reaction pattern or direct-edit pattern lands in the profile as a new versioned entry

### M6 — Outward research loop (est. weeks 9–10)
**Goal:** System continuously researches what goes viral in the domain; findings feed modules.

- [ ] T6.1 Research job v1: YouTube Data API against monitored channels/queries from `sources.yaml` — AC: top performers pulled on schedule; nothing hardcoded
- [ ] T6.2 Analysis step: hook/structure/format/emotion/pacing per winner (prompt + schema) → Source Bank entries — AC: entries carry the "hypothesis, not fact" framing field
- [ ] T6.3 Proposals + Experiments Queue: untried formats become proposed experiments in the async gate; approved experiments appear as seed suggestions — AC: an approved experiment flows into Pick + seed
- [ ] T6.4 Scraper layer for TikTok/IG/X via a scraping service (config-keyed) — AC: service swap is config-only; rate limits respected

### M7 — Generalization proof (est. week 11+, when a real customer is ready)
**Goal:** A second business onboards with zero code changes.

- [ ] T7.1 Onboard a second business entirely through the console — AC: **zero code changes**; all differences live in config + modules
- [ ] T7.2 Document the operator manual: `docs/OPERATOR.md` — what a new user does, start to finish, no technical steps
- [ ] **Checkpoint:** tag `review-final`; Claude review of the whole system against the charter.

## PROGRESS.md format
```
2026-07-08 · T0.3 · LLM adapter done, Ollama Cloud + local tested, retry path covered · Q: none
```

## Definition of system-level done

A person with ideas but no content skills, no coding, and no Claude account can: log in → upload/speak their materials → get a calibrated voice → co-create posts in ~15–20 min each (with the option to write/edit directly) → have the system publish, measure, research outward, and propose its own improvements — with every improvement passing through their async approval. And a second such person can do the same with zero code changes.