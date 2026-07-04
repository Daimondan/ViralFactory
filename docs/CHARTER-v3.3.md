# ViralFactory Charter — v3.3

*The constitution of the system. Any AI or collaborator reads this before working on it.*
*v3.3 — 2026-07-02 — supersedes v3.2. Incorporates AMENDMENT-004 (`docs/decisions/AMENDMENT-004-treatment-block.md`) — the treatment block on idea cards. All prior amendments (DIVERGENCE-001, DIVERGENCE-002, AMENDMENT-003) remain in force. Repo location: `docs/CHARTER-v3.3.md`.*

## What this is

**ViralFactory** is a generic content co-creation system for entrepreneurs who have ideas and domain experience but don't produce content themselves. **StackPenni** — a Caribbean AI + wealth brand (X / Instagram; sub-brands Island Futurist, Digital Sou-Sou, Caribbean Receipts) run by Daimon — is tenant #1. Paying customers are a real near-term plan; their timing is decided when they're real, not hypothesized now.

**The harness is code; the business lives entirely in config and modules.** Nothing business-specific is ever hardcoded. A second business onboards with zero code changes.

**Fresh start.** ViralFactory is a new app, new database, new repo. The prior StackPenni v2 pipeline keeps running at its own address until ViralFactory is production-ready; no v2 code, schema, or data is reused. **The v2 database is backed up before any decommission**, and the Sources Engine retains an optional deferred bulk-import path — "not migrated" never means "destroyed."

## North Star

A machine that co-creates viral-capable content with a person who supplies ideas and taste. Output must read — **and look** — as made by a specific human for a human, rooted in that person's lived domain, at a pace sustainable for a solo, non-developer operator.

## The human role: originate + react + edit + lived material

The system never *requires* the person to produce. It defaults to AI production and supports four input modes:

1. **Seeds** — ideas, opinions, stories, real numbers. Spoken or typed; a 30-second voice note is a perfect seed; messy is fine.
2. **Reactions** — taste as recognition. Plain-words feedback via typed text and tap/click chips where chips genuinely speed things up. The drafter self-audits against the Tells Checklist and presents suspect lines, so the person judges flagged items rather than hunting.
3. **Direct edits** — when the person writes or rewrites draft text themselves, their text is **authoritative** and overrides the AI draft. Direct edits are the strongest voice signal and enter the Feedback Log at the highest weight. The system supports and encourages this mode. (Patterns extracted from direct edits still reach the Voice Profile through the gate as proposals — evidence, not silent self-update.)
4. **Lived material** — phone footage, receipts, screenshots, real artifacts. No craft required.

## Interaction & interface principles

- **Laptop-first, mobile-friendly.** The primary operator works on a laptop (1280px+); every screen scales responsively to mobile. Mobile-friendliness is a hard requirement for future customers, not an afterthought — but it does not constrain the primary design.
- **Voice available everywhere, assumed nowhere.** Every input point offers recording; typed text and chips are equal citizens.
- **Evidence beside every AI claim.** Proposals, flags, and scores always show their supporting evidence.
- **One-go intake.** All human materials are gathered in a single onboarding session; afterward the system returns to the person only for reactions, edits, and gate decisions.

## The repeatability rule

**If an AI does something once in a chat, it must be written down as a playbook the system can run for user #2.** Onboarding is itself a pipeline with the same gates as everything else.

## The Onboarding Engine (playbooks)

For every module there is a **playbook**: procedure + prompt templates + output schema + gate, as text files in `playbooks/`, executed by a generic runner. Material-agnostic intake with fallbacks (e.g., guided spoken interview when a user has no corpus). Calibration closes every playbook — no module reaches v1 without the person's confirmation. The eight playbooks: Business Profile intake · Voice Profile builder · Sources Engine · Viral Patterns starter · Audience Insights · Story Frameworks · Format Guide · Visual Style intake.

## What makes content read and look human

1. **A specific detail only this person could know, in every piece** — the human seed; the single biggest lever.
2. **Voice from real samples, not adjectives** — natural speech weighted highest; dialect preserved, never sanitized; concrete patterns with verbatim evidence.
3. **A human pass** — reactions or direct edits against the drafter's self-audit. AI tells are rhythm and structure; the Tells Checklist lives in the Voice Profile.
4. **Real footage anchors visual trust** — generated video (Veo-class) is the supporting, preferably stylized layer; platform AI-disclosure rules followed.

**Humanness is built in, not sprayed on.** No bolt-on humanizer step, ever.

## The living modules (the accumulating intelligence)

Eight versioned markdown documents per business in `modules/{business}/` — the system of record, gate-only writes, schema-checked on load, provenance per entry. Fully standalone — ViralFactory has its own database; no OB1 dependency. Loaded into every draft:

1. **Voice Profile** (incl. Tells Checklist) · 2. **Viral Patterns Playbook** · 3. **Story Frameworks** · 4. **Format Guide** · 5. **Audience Insights** · 6. **Feedback Log** · 7. **Visual Style Guide** · 8. **Source Bank** (+ its Source Criteria)

## The core loop

1. **Gather** — automated, **configured by onboarding**: the person's onboarding inputs (seed sources, anti-examples) produce the Source Criteria and `sources.yaml`, which dictate what the AI scouts from then on. The Sources Engine ingests and scores every item against those criteria; the continuous loop proposes new sources and criteria amendments through the gate.
2. **Ideas** — generation is **grounded in the living modules**, not just raw source material: AI-originated ideas are produced by crossing Source Bank items with the Viral Patterns, Audience Insights, Story Frameworks, and Format Guide modules. Cards come from three origins, each tagged with provenance:
   - **ai-originated:** AI proposes from the Source Bank × modules
   - **human-seeded:** the person's raw seed (spoken or typed; messy is fine)
   - **human-seeded, ai-developed:** the person's seed sharpened by AI — angle variants proposed, supporting Source Bank material attached. This is the primary path; the person supplies sparks, never finished ideas.
   Each card carries: the idea, its hook/title options, a **treatment** (scope, format from the Format Guide — including experimental formats debuting on the card, capture-required tasks, reuse links, rationale), origin, and evidence links. Cards approved with outstanding capture tasks wait in **awaiting-capture** until the human supplies the material through the materials intake; only then do they flow to Draft.
   **GATE (rigorous):** approve / kill / park per card. The funnel kills most here — by design. Kill reasons logged to the Feedback Log.
3. **Draft** — AI, all modules loaded, self-audited against the Tells Checklist. A draft is: **full text in voice + light visual direction** (image prompts, reference notes, shot/format choices per the Visual Style Guide). **No rendered images at this stage** — visual direction is text; render cost is only spent on survivors. *(Amendable: if co-production evidence shows drafts can't be judged without pixels, a single rough reference render per draft may be added via a future amendment — evidence first.)*
   **GATE (the human pass, unchanged from v3.1):** react via chips + text and/or direct edits (authoritative, highest Feedback Log weight); AI revises; **ship-forward or kill.**
4. **Assets** — for surviving drafts only: real images generated per the visual direction, captions rendered, the piece fanned out into per-platform variants (X thread, IG carousel/reel, …).
   **GATE (quick, per platform):** approve / fix / kill per variant, side by side.
5. **Publish** — **every piece passes human approval before posting. No auto-publish, ever, at any trust level. Hard rule.** Go/hold + timing only; everything upstream is already approved. Approved pieces flow to Buffer for scheduling, posting, and metrics. *(Postiz→Buffer swap per DIVERGENCE-008, operator confirmed.)*
6. **Learn** — two loops (below)
7. **Improve** — gate-approved proposals update modules; every future draft inherits them

Gate intensity tapers: Ideas is rigorous, Draft is the deep human pass, Assets is quick, Publish is go/hold. All four feed the same async gate queue (DIVERGENCE-001 rules apply: age visible, superseding, no pressure mechanics).

## Provenance requirement

`origin` (ai-originated | human-seeded | human-seeded-ai-developed), `format`, and `scope` travel with a piece from idea card to Results. The nightly performance note records them, so the inward loop can answer: do the operator's seeds outperform AI-originated ideas? Do certain formats or scopes perform better? These are measurable claims of the whole product thesis — they must be instrumented from the first piece.

## The learning system (two loops, one asynchronous gate)

**Inward loop** — generated on a schedule (weekly): results + Feedback Log (direct edits weighted highest) → specific proposed module updates with evidence and exact diffs.

**Outward loop — continuous from v1, not deferred.** Scheduled research of the domain: monitors the sources/channels/queries the Sources Engine maintains, pulls top performers, analyzes hook/structure/format/emotion/pacing — **as hypotheses, never facts**. Findings flow to the Source Bank (self-growing), proposed module updates, and the **Experiments Queue** (untried formats become deliberate experiments; results feed the inward loop — exploration built in, the cure for the convergence trap).

**The Gate is a persistent asynchronous queue,** not a scheduled sitting. Proposals accumulate; the person clears them when ready. Rules:
- Every card shows its age; staleness is always visible.
- A newer proposal touching the same module section supersedes the older one (marked, not deleted).
- No deadlines, no pressure mechanics. If the queue grows faster than it clears, the proposals are too weak or too many — **fix the proposal prompt, never pressure the person.**
- Own-account data is small and noisy: no automatic optimization; autonomy is earned as proposals prove out, never assumed.

## Build architecture

- **Claude = architect**: designs, documents, reviews; speaks only through versioned files in the repo.
- **Hermes agent (open-source models, VPS) = builder**: works BUILD_PLAN top-down under its guardrails; never decides design.
- **GitHub = the channel**: one repo for code and docs; divergences filed in `docs/decisions/`; architect reviews land in `docs/reviews/`.
- **LLM backend swappable in config** (`models.yaml`): Ollama local/cloud or external API; processing at temperature 0; the drafter backend chosen by blind A/B on voice quality at the M3 checkpoint.
- **The operator directs in plain language and gates. Never writes code.**

## Document hierarchy (conflicts are divergences, never silent overrides)

1. **Charter** (this file) — principles and design rules. Amended only via `docs/decisions/` → architect review → version bump.
2. **BUILD_PLAN.md** — tasks, order, guardrails. Conforms to the charter.
3. **docs/CONTEXT.md** — the operational mirror: shared language and current implementation state. Conforms to charter and plan; a conflict is a bug or a divergence to file.
4. **CHANGELOG / docs/decisions/** — the record. Feeds charter revisions; does not govern alone.

## Design rules (durable — amend only via a filed divergence)

- Human originates, reacts, edits when they choose; AI produces by default; production is never required of the person.
- Nothing hardcoded: judgment → playbooks/prompts; values → config; mechanics → deterministic libraries; taste → the person.
- One drafter, no model mixture. No bolt-on humanizer. No hand-built distributed state machine.
- AI proposes, human gates — everywhere, including onboarding. Per-piece approval before publish is absolute.
- Every LLM step = prompt template (in repo) + output schema + validator + provenance log. Content-hash caching; unchanged input is never re-judged.
- No patch scripts: wrong output → fix prompt, config, or validator, versioned.
- The Voice Profile is the first module built and the last thing compromised.
- Add complexity only when real volume forces it.

## Phases

**Phase 0 — Foundations.** Fresh repo scaffolding, config system, LLM adapter, validator, provenance, cache, v2 database backup.
**Phase 1 — Onboarding engine.** Generic playbook runner; Voice Profile end-to-end with calibration; then the remaining playbooks. Tenant #1's config re-entered through onboarding (no v2 migration).
**Phase 2 — Co-production sprint.** ~10 pieces: seed → draft → self-audit → react/edit → ship or kill. Feedback Log grows.
**Phase 3 — Publish + metrics.** Postiz self-hosted; per-piece approval enforced in the flow; nightly metrics.
**Phase 4 — Learning loops.** Inward proposals + async gate queue; outward research + Source Bank + Experiments Queue (outward runs from v1 of this phase).
**Phase 5 — Generalization proof.** Onboard business #2 through the console with zero code changes — executed when a real second business exists; the architecture for it is enforced from Phase 0 regardless.

---

*Test for any decision: does it improve the voice, the lived detail, the person's taste signal, or the system's gated learning — for ANY user, not just tenant #1? If not, it is plumbing: keep it simple or automate it away. If an AI just did something clever ad hoc: stop and write the playbook. If reality disagrees with this charter: file a divergence.*
