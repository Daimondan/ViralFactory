# Inspiration Center + Human Creative Gates — Proposed Build Plan

> **For Hermes:** This is a planning proposal, not an approved architecture. Before implementation, file the accepted product changes as a divergence and obtain architect review. Then execute the resulting `BUILD_PLAN.md` tasks top-down, one task per tested commit.

**Goal:** Add an operator-facing Inspiration Center for current TikTok/Instagram audio and format mechanics, support trend-first and idea-first ideation without forcing matches, and improve the human creative-direction pass before expensive generation while preserving per-piece approval.

**Architecture:** Trends are ephemeral, evidenced inputs upstream of Idea Cards—not permanent Format Guide entries by default. The Inspiration Center feeds the existing Researcher/Idea Gate through three paths: trend → ideas, idea/research → compatible trends, and browse/save → later use. Short humorous trend pieces and longer character-universe explainers diverge at treatment selection, then converge on Writer, human creative approval, Assembler, final asset review, and Publish approval.

**Tech Stack:** Existing Flask/server-rendered UI, SQLite, config-driven providers, existing LLM adapter/provenance, Bundle.social Instagram audio integration, current Source Bank/Idea Cards/Production Contract/Storyboard/Soundtrack/Assembler services.

---

## 1. Current Reality

- `/research` currently discovers and analyzes configured YouTube sources; it is not a social trend browser.
- `src/soundtrack_discovery.py` can search Bundle.social Instagram audio and Pixabay for a known mood/query. It does not yet prove a current TikTok/Instagram “Trending Now” feed or trajectory history.
- `src/soundtrack_ranking.py` ranks soundtrack candidates for an existing draft. It is downstream production music selection, not upstream trend ideation.
- `/ideas` supports raw seeds, AI-developed seeds, and exact-format constraints, but Idea Cards do not yet carry a trend/audio/format-mechanic reference.
- The charter fixes four content gates. A Director’s Room or linked creative-direction pass must be reconciled through a divergence rather than silently added.
- Existing storyboard, measured-VO, visual-event, soundtrack, cost, compliance, and final-review services should be reused rather than rebuilt.
- `DIVERGENCE-015` already proposes soundtrack discovery/ranking/auto-apply and is pending architect review. Inspiration Center work must not silently settle that divergence.

## 2. Product Model

Keep these concepts separate:

1. **Trend audio** — exact platform audio, creator/source, preview, platform identifier, usage/right status.
2. **Trend format mechanic** — the reusable creative grammar: setup, reversal, performance, text pattern, cut pattern, typical duration.
3. **Trend example** — an actual TikTok/Instagram post evidencing the audio/mechanic.
4. **Trend snapshot** — observed metrics and collection time used to infer lifecycle/trajectory.
5. **Idea or research seed** — the truth, observation, source material, or operator spark.
6. **Trend–idea match** — LLM judgment on whether the trend naturally serves the idea, including “no fit.”
7. **Saved inspiration** — operator bookmark/shortlist; not an approved idea.
8. **Creative treatment** — one selected primary destination combining idea, format/show, trend mechanic if any, character role, platform/container, and production approach.

A trend is evidence-backed and temporary. It is not automatically promoted into the durable Format Guide or character canon.

## 3. Unified Content Flow

```text
INSPIRATION / RESEARCH / OPERATOR SEED
        │
        ▼
MATCH OR GENERATE
trend-first · idea-first · no-trend long-form
        │
        ▼
GATE 1 — CONCEPT + PRIMARY TREATMENT
approve · kill · park
        │
        ▼
WRITER + PERFORMANCE PLAN
short native-audio/dialogue/text OR deep character-led script
        │
        ▼
GATE 2A — WORDS / PERFORMANCE
approve · revise · direct edit · kill
        │
        ▼
DIRECTOR'S ROOM (linked Gate 2B)
measured audio · storyboard · visual events · text map · soundtrack · cost
        │
        ▼
ASSEMBLER EXECUTES LOCKED PACKAGE
        │
        ▼
GATE 3 — FINAL ASSET
approve · fix · kill
        │
        ▼
GATE 4 — PUBLISH
post/hold + timing; never automatic
```

This preserves the four top-level gates while making Gate 2 a deliberate two-part human pass. Architect approval is required because the current charter describes Gate 2 and treatment locking more narrowly.

## 4. Content Paths

### A. Trend-first short-form

Operator selects an audio or format mechanic, then requests ideas grounded in current sources, audience, characters, humor, and voice. The system returns one recommended concept plus up to two meaningfully different alternatives. The operator selects one primary treatment before writing begins.

### B. Idea/research-first short-form

Operator chooses or enters a research-backed idea. The system searches current trends and judges semantic fit, character fit, comedic premise, platform-native fit, freshness, feasibility, factual integrity, brand safety, and rights risk. It may return “no natural trend fit” and recommend an original short-form format instead.

### C. Character-universe long-form

Research/seed selects an ownable recurring show or deeper narrative treatment. Trends are optional and normally secondary. The character universe carries the explanation through dialogue, conflict, parable, mock news, investigation, or visual essay rather than generic B-roll. This path may have measured VO/dialogue and more scenes, but uses the same creative-direction and approval machinery.

## 5. Delivery Sequence

### Step 0 — Approve the architecture change

**Objective:** Convert the accepted product behavior into an architect-readable divergence before code.

**Likely files:**
- Create: `docs/decisions/DIVERGENCE-016-inspiration-center-and-directors-room.md`
- Modify after architect review: `docs/CHARTER-v3.7.md` or successor
- Modify after architect review: `BUILD_PLAN.md`
- Modify after architect review: `docs/CONTEXT.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/PROGRESS.md`

**Decisions to ratify:**
- Inspiration Center position in the navigation.
- Trends as ephemeral evidence records, separate from durable Format Guide entries.
- Three bidirectional ideation paths.
- Gate 2A + linked Gate 2B Director’s Room without adding a fifth top-level gate.
- Which treatment fields lock at Gate 1 and which creative-production choices lock at Gate 2B.
- Relationship with pending `DIVERGENCE-015` soundtrack auto-apply.

**Acceptance:** Architect provides approved/refined/rejected verdicts and updates the active charter/build plan. No implementation starts before this.

### Step 1 — Build one thin end-to-end trend slice first

**Objective:** Prove that a real, evidenced trend can become a reviewable Idea Card before building a broad trend crawler.

Use the already verified “program I’m running isn’t too strict” example as test data through a generic import path—not hardcoded StackPenni code.

**Operator flow:**
1. Import exact trend URL/audio metadata.
2. See a Trend Card with playable audio, exact source, examples, format grammar, freshness, rights caveat, and confidence.
3. Click **Use with an idea**.
4. Enter the restaurant/family seed.
5. Receive a fit judgment and one primary treatment recommendation.
6. Accept the recommendation to create a normal Idea Card carrying trend provenance.
7. Review it at Gate 1 using the existing approval semantics.

**Likely files:**
- Modify: `src/pipeline.py`
- Create: `src/services/inspiration_store.py`
- Create: `src/services/trend_import.py`
- Create: `prompts/inspiration/analyze_trend_v1.md`
- Create: `prompts/inspiration/match_idea_v1.md`
- Create: `src/templates/inspiration.html`
- Modify: `src/app.py`
- Modify: `src/templates/_nav.html`
- Modify: `src/templates/ideas.html`
- Create: `tests/test_inspiration_vertical_slice.py`

**Acceptance:** A real trend record creates a correctly grounded Idea Card without DB patching, without keyword heuristics, and with full LLM provenance. The existing Idea Gate still owns approval.

### Step 2 — Establish trustworthy trend collection

**Objective:** Collect current audio and format evidence without claiming unsupported popularity.

**Work:**
- Audit what Bundle.social can actually provide for Instagram: search, previews, identifiers, example URLs, usage metrics, and regional availability.
- Audit an approved TikTok data route. Until proven, support operator-supplied TikTok links/IDs instead of pretending full Trending coverage exists.
- Add provider adapters configured in `config/inspiration.yaml`.
- Capture snapshots over time so rising/saturated/fading is based on evidence, not one observation.
- Keep platform-specific rights/availability separate.
- Store source URL, provider, retrieval time, raw evidence hash, first/last seen, and confidence.
- Schedule collection through systemd/cron only after one manual run succeeds with real data.

**Likely files:**
- Create: `config/inspiration.yaml`
- Create: `src/services/trend_discovery.py`
- Create: `src/services/trend_snapshot.py`
- Reuse/modify: `src/soundtrack_discovery.py`
- Create: `prompts/inspiration/interpret_format_v1.md`
- Create: `tests/test_trend_discovery.py`
- Create: `tests/test_trend_snapshot.py`

**Acceptance:** Every item labeled “trending” displays source evidence and collection time. Missing trajectory data displays “observed” or “confidence low,” never a fabricated trend claim.

### Step 3 — Build the full Inspiration Center browse surface

**Objective:** Give the operator a useful laptop-first trend workspace, not a link dump.

**Recommended sections:**
- **Trending Now** — mixed feed with filters for TikTok/Instagram, audio/format, lifecycle, age, humor/education, character fit, and feasibility.
- **Audio** — playable exact sound, creator, platform ID, examples, rights/availability, observed momentum.
- **Formats** — setup/payoff grammar, typical text/performance, duration, examples, ideas that fit, uses that feel forced.
- **Saved** — operator shortlist with notes and expiry warnings.

**Card actions:**
- Use with an idea.
- Generate ideas from this trend.
- Find research that fits.
- Save/ignore.
- Open examples/source evidence.

Cards must show 300+ character detail, expandable full analysis, platform provenance, first/last seen, lifecycle confidence, production needs, rights risk, and examples. If the queue reaches 50+, include checkboxes, select-all, and bulk save/ignore.

**Likely files:**
- Modify: `src/templates/inspiration.html`
- Create: `src/static/inspiration.js` only if existing minimal-JS patterns cannot cover interactions
- Modify: `src/static/vf.css`
- Modify: `src/app.py`
- Create: `tests/test_inspiration_ui.py`

**Acceptance:** Operator can browse real records, preview audio, inspect evidence, filter, save, ignore, and start any of the three ideation actions. Browser test and curl test run against the deployed server with real records.

### Step 4 — Add bidirectional trend/idea judgment

**Objective:** Make trends useful for ideation while preventing forced matches.

**LLM judgment fields:**
- semantic fit;
- character/show fit;
- comedic premise;
- research/factual integrity;
- audience relevance;
- platform-native fit;
- freshness/shelf life;
- production feasibility/cost;
- brand safety/disclosure;
- rights/availability risk;
- verdict: `strong_fit | possible_with_changes | forced | no_fit`;
- explanation and proposed treatment.

**Rules:**
- No keyword routing in Python.
- “No fit” is a successful result.
- Research claims cannot be altered to satisfy a joke.
- Fictional interviews/skits cannot be represented as evidence.
- One recommendation becomes the primary treatment only after operator selection.
- Up to two alternatives may be shown, but derivatives are not generated automatically.

**Likely files:**
- Create: `src/services/trend_idea_matching.py`
- Create: `prompts/inspiration/match_idea_v1.md`
- Create: `prompts/inspiration/generate_from_trend_v1.md`
- Create: `prompts/inspiration/find_research_fit_v1.md`
- Modify: `src/app.py`
- Modify: `src/pipeline.py`
- Create: `tests/test_trend_idea_matching.py`

**Acceptance:** Real examples prove trend → ideas, idea → trends, research → trend/no-fit, and no-fit → original-format fallback. All calls are schema-validated, cached, and logged.

### Step 5 — Improve the human development gate with a Director’s Room

**Objective:** Move meaningful taste decisions before expensive generation while keeping the operator out of timeline-editing minutiae.

**Gate 2A — Words/performance:**
- complete text/dialogue/native-audio excerpt;
- character assignment and emotional register;
- direct edits and reaction chips;
- measured VO or selected native audio before timing decisions;
- approve/revise/kill.

**Linked Gate 2B — Creative direction:**
- one recommended creative package;
- timed beats and emotional arc;
- storyboard/style frames;
- one or more visual events per beat;
- media type and character continuity references;
- text map and safe-zone preview;
- exact soundtrack/audio excerpt and energy curve;
- production/cost summary;
- two alternatives only for uncertain, expensive, or identity-critical choices;
- approve-all-recommended plus per-event overrides.

Reuse the existing Production Contract, measured-VO, Visual Director, storyboard, reference assets, soundtrack ranking/mixing, cost guard, and compliance services. Do not build a parallel production path.

**Likely files:**
- Modify: `src/templates/draft.html`
- Create or modify: `src/templates/directors_room.html`
- Modify: `src/services/edit_planning.py`
- Modify: `src/services/media_planning.py`
- Modify: `src/services/cue_compiler.py`
- Modify: `src/produce_chain.py`
- Modify: `src/pipeline.py`
- Create: `tests/test_directors_room.py`
- Extend: `tests/test_production_chain.py` or current shared-path parity tests

**Acceptance:** Expensive generation cannot start until the exact current creative package is approved. Any edit invalidates only affected approvals. Operator and autonomous entrypoints call the same services. Final publish still requires explicit per-piece approval.

### Step 6 — Formalize short-form and character-universe repertoires

**Objective:** Prevent the system from collapsing into generic Reels or using trends for every idea.

**Work:**
- Treat platform/container, format family, original show, trend mechanic, treatment, tone, and production mode as separate fields.
- Update the tenant Format Guide as an affordance catalogue, not a routing table.
- Add approved recurring shows/character relationships through existing module/reference-asset gates.
- Support native-audio/lip-sync, dialogue, text-led, no-VO, reaction, sketch, street-interview fiction with disclosure, mock news, visual essay, and deeper character-led episodes.
- Let long-form ideas explicitly choose `no_trend` when depth is the better treatment.
- Lock one approved visual translation per recurring show while permitting deliberately named treatments across different shows after operator approval.

**Likely files:**
- Gate-approved updates under `modules/{business}/format-guide.md`
- Gate-approved updates under `modules/{business}/episode-format.md`
- Gate-approved character/reference assets under `data/media/reference/{business}/`
- Modify Writer/production schemas only after architecture approval
- Add golden short-form and long-form fixtures under `tests/fixtures/golden/`

**Acceptance:** One 6–12 second humorous trend piece and one deeper character-universe piece both traverse the same gates without being forced into the same script or visual grammar.

### Step 7 — Close the learning loop

**Objective:** Learn whether trend use, formats, characters, and treatments work without auto-writing brand rules from noisy data.

**Work:**
- Persist trend/audio/format/show/treatment identifiers through publication and metrics.
- Record saves, shares, comments, completion/retention where available, cost, operator edits, and trend age at publish time.
- Compare against matched baselines rather than raw views alone.
- Analyst proposes changes to Format Guide, Viral Patterns, character/show rubrics, or process registry through the existing async gate.
- Expired trends remain in history but leave the active Inspiration feed.
- One post never creates a durable rule automatically.

**Likely files:**
- Modify: `src/performance_records.py` or current performance-record service
- Modify: Analyst prompts/process registry
- Modify: `src/templates/published.html`
- Create: `tests/test_inspiration_learning_loop.py`

**Acceptance:** Published performance can be traced back to the exact trend snapshot and creative treatment; learning outputs are evidence-bounded proposals requiring operator approval.

## 6. Recommended Starting Point

Start with **Step 0 followed immediately by Step 1: one evidenced trend → one fit judgment → one normal Gate 1 Idea Card**.

Do **not** start by building a giant scraper or a polished trend dashboard. The biggest product risk is not collecting links; it is whether an operator can turn one real trend into a strong, grounded, approvable concept without forcing the idea or breaking the existing content gates. The Stackwell restaurant proof gives us a real test case and known expected result.

Once that vertical slice feels right to the operator, broaden collection, then add the Director’s Room using the same piece as the first end-to-end creative-direction proof.

## 7. Real-World Validation

Before each phase is marked complete:

- Run focused tests, then full `pytest`.
- Exercise the actual deployed Flask surface in a browser as the operator.
- Curl the real server routes and verify persisted records.
- Use real TikTok/Instagram examples, not fabricated fixtures alone.
- Confirm audio previews play and exact provenance links open.
- Confirm expired/unsupported/low-confidence records are labeled honestly.
- Confirm no paid generation occurs before the correct approval.
- Confirm no code path can publish without explicit per-piece approval.
- Confirm a second tenant can use the feature through config/modules only.

## 8. Decisions Needed From Daimon Before Step 0 Is Filed

1. Should **Inspiration** be a new top-level navigation item, or a section inside **Researcher**?
2. At Gate 1, should the operator lock only the primary treatment, with scene/storyboard/sound choices deferred to Gate 2B? This is the recommended split.
3. Should the first vertical slice use the already proven Stackwell restaurant trend as the canonical acceptance case? Recommended: yes.
4. Should the first Inspiration Center version permit manual URL import alongside provider discovery? Recommended: yes, because TikTok data availability is not yet proven and manual import prevents fake “Trending Now” coverage.
