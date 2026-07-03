# Context: ViralFactory

> **This is an operational mirror of `docs/CHARTER-v3.3.md`.** It captures
> current shared language, workflows, and implementation state. It conforms
> to the charter and BUILD_PLAN; where it conflicts, that conflict is a bug
> or a new divergence to file — never a silent override.
>
> **Change triggers:** stage added/removed/renamed, rules changed, new
> automation, paths changed, interface changed, workflow changed,
> terminology changed.
>
> **On change:** bump `updated_at` date, add/update a decision note in
> `docs/decisions/` if the change is non-obvious.

**Updated:** 2026-07-03
**Conforms to:** `docs/CHARTER-v3.3.md` (v3.3 — incorporates DIVERGENCE-001, DIVERGENCE-002, AMENDMENT-003 staged content pipeline, and AMENDMENT-004 treatment block on idea cards)

---

## Purpose

ViralFactory is a **generic content co-creation system** that turns a person's ideas and taste into published content that reads and looks human — made by a specific person for a human, rooted in their lived domain. The person supplies seeds (spoken or typed ideas), reactions (taste), and lived material. The system drafts in their real voice, publishes, measures, researches what goes viral in their domain, and proposes its own improvements — every improvement passing a human gate.

The system is generic: **the harness is code, the business lives entirely in config and modules.** A second business onboards with zero code changes.

**StackPenni** (Caribbean AI + wealth brand on X/IG, run by Daimon) is user #1. Paying customers are a real near-term plan.

## Users

- **Primary user (v1):** Daimon, operating StackPenni. Laptop-primary. Not a developer. Supplies seeds and taste; sometimes writes/edits directly.
- **Future users (near-term):** Paying customers — other entrepreneurs who have ideas and domain experience but don't produce content themselves. These users may be mobile-primary. The system must be mobile-friendly for them.
- **Architect (Claude):** Designs the system, writes/updates the charter, playbooks, and build plan. Reviews builder work. Not a daily user.
- **Builder (Hermes agent):** Implements the build plan task by task. Open-source models on the VPS.

## North Star

A machine that co-creates viral-capable content with a person who supplies ideas and taste but does not produce. Output must read — and look — as made by a specific human for a human, rooted in that person's lived domain, at a pace sustainable for a solo, non-creator, non-developer operator.

## The Human Role: Originate + React + Edit + Lived Material

The system does not assume the person can write, design, or edit. But it **supports and encourages** direct editing when they choose to. Four input modes:

1. **Seeds** — ideas, opinions, stories, real numbers. Spoken preferred (30-second voice note is a perfect seed); typed accepted. The system builds the finished piece around the seed.
2. **Reactions** — taste as recognition, not creation. The person doesn't fix drafts; they react in plain words ("that word isn't me", "too polished", "ending is weak") via typed text or tap chips where it makes sense. Reactions feed the Feedback Log.
3. **Direct edits** — when the user writes or rewrites draft text themselves, the system treats this as authoritative. Human text overrides AI draft. Direct edits are the strongest voice signal and feed the Feedback Log with higher weight than chip reactions.
4. **Lived material** — phone footage, receipts, screenshots, real artifacts. No craft required.

## Shared Language

### ViralFactory
The generic content co-creation system (the harness/code). Not specific to any business.

### StackPenni
The first business using ViralFactory. All StackPenni-specific values (brand name, topics, feeds, queries, voice, audience) live in config and modules, never in code.

### Seed
A spoken or typed idea/take/story from the user. In the staged pipeline, a seed becomes a **human-seeded** idea card (or a **human-seeded-ai-developed** card when the AI sharpens it). A seed can produce multiple pieces (different platforms/formats).

### Idea card
The first artifact in the staged pipeline. Each card carries: the idea, hook/title options, a **treatment** (scope: one-off | series-of-N | pillar-with-derivatives; format from the Format Guide — including experimental formats debuting on the card; capture-required tasks; reuse links; rationale), origin tag (`ai-originated` | `human-seeded` | `human-seeded-ai-developed`), and evidence links. Treatment is approved WITH the idea at Gate 1 — not developed after. Cards approved with outstanding capture tasks enter **awaiting-capture** until the human supplies material through the materials intake. Gate 1 (rigorous: approve/kill/park) decides which cards proceed to Draft.

### Treatment
The decision of how an idea becomes a piece — scope, format, capture needs, reuse, and rationale. Lives ON the card, approved AT Gate 1. The human may edit any part at the gate (direct-edit authority). Compact treatment line (scope · format · capture flag) shown on cards for fast kills; full treatment expands on demand. Not a new stage or gate — it's a property of the card.

### Origin
The provenance tag that travels with a piece from idea card to Results: `ai-originated`, `human-seeded`, or `human-seeded-ai-developed`. Along with `format` and `scope`, the nightly performance note records them so the inward loop can answer: do the operator's seeds outperform AI-originated ideas? Do certain formats or scopes perform better? Instrumented from the first piece.

### Piece
A single content output — one post, one thread, one reel script, or one caption. A seed can produce multiple pieces.

### Module
One of 8 living knowledge documents (see below). Markdown files, versioned, gate-only writes. Not code.

### Gate
A human approval checkpoint. Three types:
- **Content gates (four, in the staged pipeline):** Gate 1 (Ideas — rigorous: approve/kill/park per card), Gate 2 (Draft — the human pass: chips + text + direct edits; ship-forward or kill), Gate 3 (Assets — quick, per-platform: approve/fix/kill), Gate 4 (Publish — go/hold + timing only). Gate intensity tapers: Ideas is rigorous, Draft is deep, Assets is quick, Publish is go/hold.
- **Async proposal queue:** Module updates, source proposals, experiments accumulate in a persistent queue. Daimon clears them when ready — not on a schedule. Every card shows age ("submitted N days ago"). Newer proposals on the same module section supersede older ones (marked, not deleted). No deadline or pressure mechanics. If the queue grows faster than it clears, the proposals are too weak or too many — fix the proposal prompt, never pressure the person.

### Ship
A piece Daimon approves goes to the publish queue (Postiz). Does NOT mean immediately posted — Postiz schedules per the Format Guide's timing rules.

### Playbook
A written procedure (markdown) + prompt templates + output schema that the system's AI executes for any user. The generic playbook runner reads and executes these. Playbooks are text files in `playbooks/`, not code.

### Onboarding
The one-time setup that builds all 8 modules from the user's materials. Not a single session — it's a flow with multiple gates (calibration, confirmation). Realistic estimate: 1–2 sessions over a few days.

### Direct edit
When the user writes or rewrites draft text themselves. The system treats this as authoritative — the human's text overrides the AI draft, and the edit feeds the Feedback Log as a strong voice signal.

## The 8 Living Modules

Every business has 8 versioned knowledge documents, stored as markdown in `modules/{business}/`, loaded into every draft, updated only through the human gate:

1. **Voice Profile** (incl. Tells Checklist) — how this person sounds
2. **Viral Patterns Playbook** — what works in this domain (hypotheses, not facts)
3. **Story Frameworks** — how to tell a story per subject type
4. **Format Guide** — which format fits which message on which platform
5. **Audience Insights** — who the content is for and what they respond to
6. **Feedback Log** — accumulated reactions and direct edits (voice signal)
7. **Visual Style Guide** — brand look + real-vs-generated blend rules
8. **Source Bank** — trusted sources, self-growing, self-pruning

Every module has: a fixed schema, a version number, a provenance note, and an update path through the gate.

## Core Workflows

### The Core Loop (staged pipeline — four content gates)
```
GATHER (automated — configured by onboarding)
Sources Engine scouts per the person's seed sources + anti-examples
ingests + scores every item against Source Criteria
        │
        ▼
IDEAS  ◄── living modules ground idea generation
cards from 3 origins: ai-originated · human-seeded · human-seeded-ai-developed
ai-originated = Source Bank × Viral/Audience/Story/Format modules
each card: idea + hook options + format + origin tag + evidence links
        │
        ▼
■ GATE 1 — RIGOROUS: approve / kill / park per card
  the funnel kills most here, by design — kill reasons → Feedback Log
        │
        ▼
DRAFT
AI, all modules loaded, self-audits against Tells Checklist
= full text in voice + LIGHT VISUAL DIRECTION (prompts, refs, format)
  NO rendered images at this stage
        │
        ▼
■ GATE 2 — HUMAN PASS: chips + text + DIRECT EDITS (authoritative)
  AI revises → ship-forward or kill · edits → Feedback Log (highest weight)
        │
        ▼
ASSETS (survivors only)
real images generated per Visual Style Guide · captions rendered
fan-out to per-platform variants (X thread · IG carousel/reel · …)
        │
        ▼
■ GATE 3 — QUICK, PER PLATFORM: approve / fix / kill, side by side
        │
        ▼
■ GATE 4 — PUBLISH: go / hold + timing only
  NO AUTO-PUBLISH, EVER, AT ANY TRUST LEVEL — HARD RULE
        │
        ▼
SHIP → Postiz publish queue → posted → metrics
        │
        ▼
LEARN
inward loop (weekly proposals) + outward loop (continuous research)
origin tag travels idea → nightly note: do human seeds outperform?
        │
        ▼
IMPROVE
proposals land in async gate queue
user clears when ready → approved = module version bump
```

### Onboarding Flow
```
BUSINESS PROFILE Q&A
        │
        ▼
VOICE PROFILE (from materials or interview fallback)
        │
        ▼
CALIBRATION GATE (3 samples → pick → react → revise)
        │
        ▼
SOURCES ENGINE (seed sources → criteria → monitoring plan)
        │
        ▼
VIRAL PATTERNS STARTER
        │
        ▼
AUDIENCE INSIGHTS
        │
        ▼
STORY FRAMEWORKS
        │
        ▼
FORMAT GUIDE
        │
        ▼
VISUAL STYLE
        │
        ▼
ALL 8 MODULES AT v1 — ONBOARDING COMPLETE
```

### Learning System (two loops, one async gate)

**Inward loop — weekly (proposals generated on schedule, cleared async):**
AI reads published results + Feedback Log → proposes specific module updates with evidence → proposals land in async gate queue → Daimon approves/rejects when ready.

**Outward loop — continuous (runs from v1):**
Scheduled research of what works in the wild: monitors top accounts/hashtags/channels → analyzes hook/structure/format/emotion/pacing → findings flow to Source Bank (self-growing), proposed module updates, and Experiments Queue.

**Honesty rules:** External virality is observable, its cause is inference — findings enter as hypotheses. Own-account data is small and noisy — no automatic optimization. Autonomy is earned as proposals prove out, never assumed.

## Business Rules

1. **Nothing business-specific in code.** Brand names, topics, feeds, queries, taxonomies, model names → `config/`. If a string describes the business, it is config.
2. **No judgment in code.** Understanding-tasks (tagging, titling, voice analysis, quality) = prompt template + JSON schema + validator. Never keyword heuristics.
3. **AI proposes, human gates — everywhere.** Modules are never edited silently. No gate, no write.
4. **Per-piece approval.** Every piece passes Daimon's approval before publishing. No exceptions, no auto-publish (even after trust is built).
5. **Direct edits are authoritative.** Human text overrides AI draft. Direct edits feed the Feedback Log as the strongest voice signal.
6. **If an AI does something clever once, it becomes a playbook.** Ad-hoc judgment that isn't captured is a defect.
7. **No patch scripts.** Wrong output → fix the prompt, config, or validator (committed and versioned). Never a one-off fix.
8. **Mechanics use boring libraries.** Content extraction = trafilatura. Don't spend LLM calls on mechanical work.
9. **Every LLM call is logged** to provenance: input hash, prompt file + version, model, raw output, validated output, validator verdict.
10. **Deterministic where possible.** Temperature 0 for processing steps; cache by content hash — unchanged input is never re-judged.
11. **Never invent module content.** Modules are built by playbooks from user materials and updated only via the gate.
12. **Prompts carry procedures; modules carry knowledge.** Any domain taxonomy embedded in a prompt file (message types, format structures, platform mappings) is a defect: baked-in taxonomy cannot learn. Prompts describe how to reason; living modules supply what is currently believed, and the loops update the modules. (Per AMENDMENT-005 + CORRECTION-format-selection-living-v1.0)

## Edge Cases

- **Missing voice materials:** Interview fallback runs a 10–12 question guided spoken interview to produce a corpus from nothing.
- **Two sources disagree:** The source with higher trust score wins; both are preserved in the Source Bank with their scores.
- **Draft doesn't sound like the user:** The Tells Checklist flags it; the user reacts; the system revises. If 3 revise rounds don't converge, the piece is killed and the failure feeds the Feedback Log.
- **User directly rewrites most of a draft:** The rewrite is stored as authoritative; the AI's draft is preserved in provenance for comparison; the rewrite patterns feed the Voice Profile update queue.
- **Postiz is down:** Pieces stay in the publish queue. The system alerts but never loses data. Retries are automatic.
- **Module is empty at draft time:** The drafter says so explicitly ("Voice Profile not yet built — draft will be generic"). Never fills empty modules with invented content.
- **Proposal queue gets large (>50 pending):** Group by module, show oldest first, allow bulk approve/reject for low-risk proposals (source additions, criteria amendments).
- **Generalization (customer #2):** Same playbooks run with different config. No code changes. The playbook engine handles it.

## Working Agreements

- **Definition of Done** (`docs/PROCESS-definition-of-done-v1.0.md`): Hermes does not report work as done until (1) the automated suite passes, (2) a hands-on human-style UI test in the browser exercises the changed surface as the operator would, (3) an end-to-end pass runs for flow changes, and (4) the done report states what was tested and how. "Tests pass" alone is not a done report.

## Open Questions

1. ~~**Module storage:**~~ **RESOLVED** (Divergence-002): Repo markdown (`modules/{business}/`) is the system of record — fully standalone. No OB1 dependency whatsoever. ViralFactory has its own SQLite database. Every user onboards the same way (upload materials, share docs, connect Obsidian). OB1 is not involved.
2. ~~**Postiz deployment:**~~ **RESOLVED** (Claude review): Self-host on the VPS (ownership, AGPL, no per-seat cost, API identical to cloud). Revisit only if maintenance burden bites.
3. ~~**LLM backend:**~~ **RESOLVED** (Claude review): Default Ollama Cloud for processing at temperature 0. For the drafter specifically, run an A/B at the M3 checkpoint — same seeds through two configured backends, Daimon reacts blind. Voice quality is the product; the config swap makes this a measurement, not a debate.
4. **8 modules in context window:** Load all 8 every draft (may exceed smaller model limits), or load essential 4 (Voice, Viral, Story, Format) always and pull others on demand? — *Genuinely deferrable; resolve at M3 when drafter is built.*
5. **Video generation scope:** xAI Grok for generated video, or text/image only for v1? — *Genuinely deferrable; bounded by the charter's hybrid rules (real anchors for lived claims, generated is supporting layer).*

## Architecture

- **Python + Flask** console (new, not extending v2)
- **SQLite** for provenance, cache, source bank, queues
- **Postiz** (self-hosted or cloud) for publishing + analytics
- **LLM adapter:** one function, backend from config — swappable without code changes
- **trafilatura** for content extraction
- **systemd** on the VPS for deployment
- **GitHub** for code AND docs (one repo, public — deliberate so architect can read without auth)
- **Console auth (R10):** the Flask console has no authentication in M0–M2 code. Deployment posture: bind to localhost/VPN only on the VPS, or add auth before the operator end-to-end test. Endpoints trigger paid LLM calls and overwrite config files — not safe to expose publicly.
- **Claude = architect** | **Hermes = builder** | **Daimon = operator**
- **LLM backend swappable in config** — Ollama local/cloud, external APIs
- **The console renders sessions, not documentation.** Playbook markdown is the machine's script. The operator's surface is always: AI asks → operator gives anything (text, paste, files) → AI clarifies → AI drafts → plain-language readback → gate. The AI is present at every stage; the operator is never handed a form or a procedure to execute manually.

## System Diagram

See `docs/diagrams/README.md` for the authoritative system overview (vertical-flow text + Mermaid + SVG), current as of Charter v3.3. The diagram reflects the staged pipeline: Gather → Ideas+Treatment (Gate 1, debut) → Awaiting-Capture → Draft (Gate 2) → Assets (Gate 3) → Publish (Gate 4) → Learn.