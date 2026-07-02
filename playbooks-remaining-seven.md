# Playbooks — Remaining Seven

*Split these into individual files under `playbooks/` in the repo. Each follows the same anatomy as `voice-profile-builder.md`: purpose → inputs → procedure → output schema → gate. All are executed by the system's AI through the console. All end at a human gate. v1.0*

---

## Playbook 1: Business Profile Intake

**Purpose:** Build `config/business.yaml` and the brand context the drafter loads. This runs FIRST — every other playbook reads its output.
**Inputs:** Guided Q&A (spoken or typed): what the business is, brands/sub-brands, core subjects, platforms, goals, who the person thinks the audience is, tone red-lines (topics/stances never to take).
**Procedure:** (1) Q&A through console. (2) AI drafts: business summary, brand list, subject taxonomy (the tag allowlist the validator enforces), platform list, red-lines. (3) Present draft back in plain language: "Here's what I understood — correct anything." (4) Gate → write `business.yaml` + `modules/{biz}/brand-context.md`.
**Output:** `business.yaml` (machine) + brand-context module (drafter-readable).
**Gate:** User confirms the understanding. Nothing downstream runs until this passes.

---

## Playbook 2: Sources Engine

*The most important playbook after Voice. Two parts: onboarding discovery (runs once) and the continuous learning loop (runs forever). This is an engine, not a one-time setup.*

**Purpose:** Turn the user's trusted sources into explicit, learnable criteria for what a good source is for THIS business — then continuously find, score, propose, and prune sources against those criteria.

**Inputs (onboarding):**
- **Seed sources from the user:** 10–30 URLs, RSS feeds, YouTube channels, newsletters, social accounts they already trust and read
- **Seed content:** documents, notes, saved articles (e.g., OB1 exports) that represent "the kind of material we work from"
- **Anti-examples (optional but valuable):** 3–5 sources or pieces the user considers junk for this business
- Existing source bank, if any (user #1: the ~1,545 ingested sources)

**Procedure — Part A, onboarding discovery:**
1. Ingest seed sources; extract clean content (deterministic extractor, not LLM).
2. AI analyzes the seed set and writes the **Source Criteria** — an explicit, human-readable document: subjects covered, formats favored, freshness expectations, quality signals (original data? practitioner-written? regional relevance?), and disqualifiers (drawn from anti-examples). Every criterion cites which seed sources evidence it. **Criteria are text the user can read and edit at the gate — never hidden weights.**
3. From the criteria, AI generates the monitoring plan: search queries, feed subscriptions, channels/accounts to watch → proposed `sources.yaml`.
4. If a prior source bank exists: re-score every entry against the criteria; propose keep / park / drop in bulk (grouped, one sitting — not 1,545 individual decisions).
5. Gate → criteria stored as the **Source Criteria module**; `sources.yaml` written; bank re-scored.

**Procedure — Part B, continuous loop (scheduled):**
1. Monitor everything in `sources.yaml`; ingest new items into the Source Bank (scored against criteria; low scores auto-parked, never silently deleted).
2. **Discover:** run the monitoring queries + follow citation/link trails from high-scoring items to find candidate NEW sources not yet in `sources.yaml`.
3. Score candidates against the criteria. Candidates above threshold → **proposed source additions** at the weekly gate, each with evidence ("found via X, matches criteria A/C/D, sample item attached").
4. **Prune:** sources dormant or persistently low-scoring → proposed removals at the gate.
5. **Criteria learning:** when the user's approvals/rejections at the source gate contradict the criteria (they keep rejecting a type the criteria likes), AI proposes a criteria amendment — through the gate, versioned, with the contradicting decisions as evidence.

**Output:** Source Criteria module (versioned) · `sources.yaml` (versioned) · self-growing, self-pruning Source Bank.
**Gate:** New sources, removals, and criteria changes all pass the weekly gate. Item-level ingestion inside approved sources does not (that's the existing approve/reject/park review queue).

---

## Playbook 3: Viral Patterns Starter

**Purpose:** Seed the Viral Patterns Playbook module at onboarding so the outward loop starts from a v1, not from empty.
**Inputs:** 5–10 links the user admires in their domain ("I wish we'd made this") + 3–5 anti-examples ("this is the slop we never make") + top performers pulled from the monitored channels (Sources Engine output).
**Procedure:** (1) Pull/transcribe each example. (2) AI analyzes per item: hook type, structure, emotional beat, format, pacing, why it likely worked — **framed as hypothesis, never fact**. (3) Cluster into named patterns with examples. (4) Anti-examples become the "never" list. (5) Gate → module v1.
**Output:** Viral Patterns Playbook v1 (patterns + evidence + hypothesis framing + never-list).
**Gate:** User confirms patterns ring true for their taste. Updated forever after by the two learning loops.

---

## Playbook 4: Audience Insights Builder

**Purpose:** A plain-language picture of who the content is for and what they respond to.
**Inputs:** The user's own description (from Business Profile Q&A) + any existing audience data (platform analytics exports, comments/DMs the user shares) + audience signals visible on the admired examples (what commenters say).
**Procedure:** (1) Draft from user description alone (v0). (2) Enrich with whatever data exists — clearly marking "user's belief" vs "observed evidence." (3) Gate → v1.
**Output:** Audience Insights module: who they are, what they care about, language they use, what they reward, what turns them off.
**Gate:** User confirms. The inward loop upgrades beliefs to evidence over time.

---

## Playbook 5: Story Frameworks Starter

**Purpose:** How to tell a story per subject type for this business (e.g., money lesson, tech explainer, cultural observation).
**Inputs:** Subject taxonomy (from Business Profile) + admired examples (from Viral Patterns intake) + 2–3 stories the user tells often (spoken, from the Voice interview or seed voice notes).
**Procedure:** (1) For each core subject type, AI drafts a framework: entry point, tension, turn, landing — grounded in one admired example and one of the user's own told stories. (2) Frameworks must be voice-compatible (checked against Voice Profile). (3) Gate → v1.
**Output:** Story Frameworks module: one compact framework per subject type, each with a real example.
**Gate:** User picks/rejects per framework.

---

## Playbook 6: Format Guide Starter

**Purpose:** Which output format fits which message on which platform (thread / single post / reel script / carousel / caption).
**Inputs:** Platform list (Business Profile) + format observations from analyzed winners (Viral Patterns) + platform norms.
**Procedure:** (1) AI drafts a decision table: message type × platform → format, length, structure notes. (2) Include per-format skeletons the drafter follows. (3) Gate → v1.
**Output:** Format Guide module (decision table + skeletons).
**Gate:** User confirms. Experiments Queue is the main updater — untried formats enter as experiments, results update the guide.

---

## Playbook 7: Visual Style Intake

**Purpose:** Establish the visual identity and the real-vs-generated blend rules.
**Inputs:** 20+ phone photos/clips from the user's world (the shot-library seed) + any brand assets (logo, colors) + 3–5 visual examples the user likes + platform list.
**Procedure:** (1) Index the shot library (AI describes + tags each item so the drafter can reference "use a market receipt shot here"). (2) AI drafts the brand look (palette, type feel, stylization level for generated material) from assets + liked examples. (3) Write the blend rules from the charter (real anchors lived claims; generated is supporting, stylized; platform disclosure). (4) Gate → v1.
**Output:** Visual Style Guide module + indexed shot library.
**Gate:** User confirms the look. Shot library grows continuously; the module learns which blends perform via the inward loop.

---

## Execution order at onboarding

Business Profile → Voice Profile → Sources Engine (Part A) → Viral Patterns starter → Audience Insights → Story Frameworks → Format Guide → Visual Style. One console session end to end (see `docs/INTAKE-USER1.md` — all human materials are collected up front, so the chain runs without coming back to the user until the gates).
