# Architect review — inbox divergences 015 and 016

**Date:** 2026-07-19
**Reviewer:** Architect (vf-architect)
**Scope:** pending builder notes and divergences for soundtrack auto-apply and Inspiration Center; live code/config/templates; charter and Build Plan alignment
**Verdict:** both designs approved with binding conditions. DIVERGENCE-015's pre-ruling implementation is **not accepted** and requires blocking correction. DIVERGENCE-016 is design-only and enters M14 after M13 proof.

## Materials reviewed

Governance and playbooks:

- `README.md`
- `docs/CONTEXT.md`
- `docs/CHARTER-v3.7.md`
- `BUILD_PLAN.md`
- `docs/PROGRESS.md`
- `CHANGELOG.md`
- `docs/decisions/AMENDMENT-010-visual-soundtrack-pipeline.md`
- `docs/decisions/DIVERGENCE-007-source-review-queue-and-network.md`
- `playbooks/sources-engine.md`
- `playbooks/viral-patterns-starter.md`
- `docs/playbooks/viral-content-production-playbook-v1.md`

Inbox and decisions:

- `docs/inbox/BUILDER-NOTE-015-soundtrack-divergence.md`
- `docs/decisions/DIVERGENCE-015-soundtrack-discovery-ranking-auto-apply.md`
- `docs/inbox/BUILDER-NOTE-016-inspiration-center.md`
- `docs/decisions/DIVERGENCE-016-inspiration-center-and-trend-discovery.md`

Live implementation:

- `src/soundtrack_discovery.py`
- `src/soundtrack_ranking.py`
- `src/soundtrack_mix.py`
- `src/services/edit_planning.py`
- `src/services/render_review.py`
- `src/app.py`
- `src/templates/assets.html`
- `src/templates/_nav.html`
- `src/pipeline.py`
- `config/models.yaml`
- `config/soundtrack_review.yaml`

External rights evidence checked:

- Meta Music Guidelines and Help Center guidance: commercial/non-personal music use requires appropriate licences; access to platform music or an API does not itself grant synchronization/republication rights.
- Pixabay Content License summary: catalogue terms can support some commercial uses but still require a per-acquisition terms snapshot and compliance with prohibited-use/attribution rules.
- TikHub and Bundle documentation: useful discovery/API transport evidence; neither was found to grant production reuse rights merely because an endpoint exposes audio metadata or a URL.

## Decision summary

### DIVERGENCE-015

**Approved with conditions** as AMENDMENT-011.

Automatic soundtrack discovery and preview mixing may happen during Asset assembly. The operator approves the exact soundtrack-bearing artifact at Gate 3; no separate soundtrack micro-gate is required. Track switching creates a new asset version and invalidates earlier Gate 3 approval. Paid acquisition still needs fresh cost approval.

The proposed assumption that Instagram audio is “Meta-authorized commercial-safe” is rejected. Discovery metadata and usage rights are separate contracts. The proposed universal 80/20 popularity formula is also rejected; popularity may only break ties over current, comparable evidence after rights and creative fit.

### DIVERGENCE-016

**Approved with conditions** as AMENDMENT-012.

Inspiration becomes a top-level Researcher-owned workbench, not a fifth AI profile. It uses dedicated append-only trend evidence tables and never auto-feeds the Source Bank, modules, experiments, or production.

“Trending” and “Top” labels are evidence claims. A chart may support “Trending audio”; a recommendation/seed feed does not support “Top Trending Videos.” The v1 video section must use truthful wording such as “Video inspiration” until its evidence supports a trend claim.

## DIVERGENCE-015 implementation findings

### P0-1 — Pending design was implemented before architect approval

**Evidence:** DIVERGENCE-015 remained `Status: Requires architect decision`, while `src/soundtrack_discovery.py`, `src/soundtrack_ranking.py`, `src/soundtrack_mix.py`, and integration changes were already committed.

**Breach:** BUILD_PLAN “design questions go to divergences — never decided in code”; charter governance hierarchy.

**Required correction:** AMENDMENT-011 is now the decision. Existing code must be audited against VF-VS-510..516; no prior checkbox or test count is completion proof.

### P0-2 — The implementation fabricates commercial-safety evidence

**Evidence:** `src/soundtrack_discovery.py:148-155` sets every Bundle/Instagram result to `commercial_safe=True` and uses the discovery endpoint URL as `license_url`.

**Impact:** The renderer may treat a social audio observation as a commercial synchronization licence. That is legally and operationally unsafe.

**Breach:** Charter §16 failure tolerance/honesty; AMENDMENT-010 licence provenance rule; no invented facts.

**Required correction:** implement AMENDMENT-011's rights record. Provider name never implies rights. Trend-only audio cannot enter production.

### P0-3 — `soundtrack_auto_processed` can become a false green

**Evidence:** `src/services/edit_planning.py:784-854` wraps discovery/ranking/mix in a broad exception, silently continues on error, and then unconditionally sets `plan["soundtrack_auto_processed"] = True`.

**Impact:** no candidates, an invalid rank, a failed download, or a failed mix can all be recorded as processed. `src/services/render_review.py:336-343` then treats that Boolean as enough to skip the soundtrack gate.

**Breach:** Charter rule “skipped evidence is not pass”; false-green UI rule.

**Required correction:** delete Boolean proof. Readiness derives mechanically from a complete versioned contract: rights-valid local track, validated mix artifact, active version, and exact evidence hashes. Errors become explicit state.

### P0-4 — Two soundtrack contracts can disagree

**Evidence:** `src/services/edit_planning.py:800-845` discovers and mixes a track before `_plan_soundtrack(...)` runs at `src/services/edit_planning.py:867`.

**Impact:** the mixed audio may reflect one inferred mode/track while the persisted planner contract declares another. The later planner is no longer the source of search intent.

**Breach:** AMENDMENT-010's explicit soundtrack contract; deterministic contract lineage.

**Required correction:** one planner contract emits mode, rationale, and search queries; discovery and mix advance versions of that contract.

### P0-5 — UI and backend state machines contradict each other

**Evidence:**

- `src/services/render_review.py:336-343` says auto-processed soundtracks need no separate gate.
- `src/templates/assets.html:568-584` still disables rendering whenever a soundtrack plan exists but lacks `soundtrack_approved`.
- `src/templates/assets.html:499-504` renders **Use this track** buttons that call `switchSoundtrack(...)`; no matching route or function exists in `src/app.py` or the template JavaScript.

**Impact:** the operator can be blocked from rendering while the backend claims the gate was bypassed; visible controls are dead.

**Breach:** state dissonance, false controls, and shared-path equivalence.

**Required correction:** VF-VS-515 must define one Gate 3 state machine and browser-test every transition.

### P0-6 — Ranking does not receive the popularity evidence it claims to use

**Evidence:** `src/soundtrack_ranking.py:19-31` serializes candidate ID/title/artist/source/preview/licence fields but omits `usage_count`, provider rank, region, observation time, and comparable metric metadata. The prompt claims an 80/20 fit/popularity decision.

**Impact:** the model cannot execute the claimed policy; any popularity rationale is invented or ignored.

**Breach:** every judgment must be evidence-backed and schema-validated.

**Required correction:** AMENDMENT-011 C4 and VF-VS-513.

### P1-1 — Query derivation puts judgment in Python

**Evidence:** `src/soundtrack_discovery.py:45-63` derives search queries with lowercase substring/word operations and invents a generic `instrumental` fallback.

**Impact:** business/domain interpretation lives in code and cannot learn through prompts/modules.

**Breach:** no judgment in code; no hardcoded business values.

**Required correction:** the soundtrack planner emits `search_queries[]`; scripts only normalize and execute.

### P1-2 — Provider and licence policy is hardcoded

**Evidence:** `src/soundtrack_discovery.py` hardcodes API base URLs, provider branches, source labels, default queries, and licence conclusions. `config/models.yaml` carries some soundtrack values, but the source contract is not genuinely config-driven.

**Required correction:** provider adapters plus schema-validated config for endpoint keys, regions, limits, budgets, and capability flags. Rights conclusions still require evidence, not config assertion.

### P1-3 — Mixed media identity and provenance are insufficient

**Evidence:** `src/soundtrack_mix.py:139-171` writes a fixed `mixed_audio.aac`; `src/services/edit_planning.py:833-838` mutates `vo_track_path` and constructs `stock_ref` with a Bundle prefix regardless of actual provider.

**Impact:** retries/alternatives can overwrite one another; exact artifact identity, provider, and rights lineage can drift.

**Required correction:** each mix is an immutable asset version with local track hash, rights version, config version, measured duration, output hash, and active-state transition.

### P1-4 — Ranking output validation is too weak

**Evidence:** the ranking schema does not require the important fields on each child object, and code validates only that returned IDs belong to the candidate set.

**Impact:** missing rationale/fit/rights data can pass; malformed alternatives can reach the UI.

**Required correction:** strict child schemas, `additionalProperties: false` where appropriate, semantic validator for active/alternative uniqueness and rights eligibility.

### P2-1 — Early green presentation

**Evidence:** `src/templates/assets.html:467-468` labels the AI top pick with a green-style `Approved` badge before human approval.

**Required correction:** use “Suggested” or “Top match”; reserve approval/pass green for a recorded human decision on the exact artifact.

## DIVERGENCE-016 architecture findings

### A1 — A top-level workbench is compatible with four AI profiles

`src/templates/_nav.html:8-12` already organizes operator jobs (Home, Pipeline, Knowledge, Results, Setup), not one link per profile. Adding Inspiration does not create a fifth role. The Researcher owns collection interpretation and creative analysis; mechanics remain adapter/job work.

### A2 — Existing Source Bank is the wrong raw trend store

`src/pipeline.py:72-84` defines durable source records with one current row and a content status. `PipelineStore.add_source()` at `src/pipeline.py:2002-2037` deduplicates content and inserts active rows. That shape cannot preserve repeated rank/metric observations without overwriting or proliferating source rows.

Dedicated collection/item/observation tables are required. Explicit later promotion protects the Source Bank's grounding semantics and DIVERGENCE-007 review gate.

### A3 — Collection must not happen on page render

The builder's first-slice requirement correctly asks for real credentials and rendered cards, but a synchronous live provider call would create rate-limit, latency, false-empty, and island-bandwidth failures. M14 therefore separates collection jobs from the read-only page and makes tests fixture-driven.

### A4 — Provider semantics must survive normalization

The researched endpoints represent different things: charts, recommendations, seeded discovery, and public search. A generic `engagement_count` or `trending=true` field would erase meaning. The normalized contract must preserve exact metric names and endpoint evidence labels.

### A5 — DIVERGENCE-015 and DIVERGENCE-016 share mechanics, not trust

HTTP clients, retries, redaction, cache storage, and provider health can be shared. Trend audio observations cannot be transferred into FFmpeg without AMENDMENT-011's independent rights and local-artifact contracts.

## Documentation findings

### D1 — CHANGELOG is stale

`CHANGELOG.md` ends at the 2026-07-09 video-handoff audit while `docs/PROGRESS.md` records substantial M13 work and two later divergences through 2026-07-19.

**Breach:** README rule “if you made a decision and it's not in CHANGELOG, that is a bug.”

This review adds the current architect decisions to CHANGELOG. The builder must backfill any omitted implementation decisions when applying this handoff; routine task execution need not be duplicated, but every actual TECH/LOGIC/STRUCTURE/STRATEGIC/OPS/FIX decision must be recorded.

### D2 — DIVERGENCE-007 status is stale

DIVERGENCE-007 still says the source-review queue requires design even though CONTEXT and BUILD_PLAN describe `status='new'` and bulk review as implemented. Its source-network question remains unresolved. The decision file must be marked partially resolved without implying that Inspiration implements the network.

## Required order

1. Apply the documentation/ruling handoff.
2. Complete VF-VS-510..516.
3. Complete the existing fresh Reel proof VF-VS-702/703.
4. Begin M14 VF-INSP-001..005 in order.
5. Deep-browser review the changed Gate 3 soundtrack UI and Inspiration UI before claiming either milestone complete.

No production code was changed in this architect pass.
