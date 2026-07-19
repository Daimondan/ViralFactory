# AMENDMENT-012 — Inspiration evidence workbench

**Filed:** 2026-07-19
**Filed by:** Architect (vf-architect)
**Status:** APPROVED WITH BINDING CONDITIONS — ratifies DIVERGENCE-016; incorporated into Charter v3.8
**Ratifies:** `docs/decisions/DIVERGENCE-016-inspiration-center-and-trend-discovery.md`
**Related:** DIVERGENCE-007; AMENDMENT-011; M6 outward loop; `docs/reviews/REVIEW-inbox-divergences-015-016-2026-07-19.md`

## Decision

Approve **Inspiration** as a first-class, top-level operator workbench owned by the existing **Researcher** profile.

This is not a fifth AI role and not a new living module. It is an evidence surface: the operator and Researcher can inspect current public creative examples, preserve observations, and later choose which items should become bookmarks, Source Bank candidates, experiments, or evidence for a module proposal.

The operator surface is added to the primary navigation between Home and Pipeline:

`Home · Inspiration · Pipeline · Knowledge · Results · Setup`

Navigation groups are operator jobs, not a one-to-one rendering of AI profiles. The system still has Researcher, Writer, Assembler, and Analyst responsibilities.

## Truthful naming ruling

The page title is **Inspiration**. A section may use a trend claim only when its evidence supports that exact claim:

- **Trending audio** is permitted for a provider chart or clearly identified trend endpoint. Each card or group must show provider, platform, region, collection time, and the metric/rank used.
- A provider recommendation feed, seed feed, or regional discovery feed is labelled **Video inspiration** or **Provider recommendations**, not “Top Trending Videos.” Recommendation is not measured trend velocity.
- **Top** is permitted only when the provider supplies an ordered chart with a declared scope. First-seen items cannot show rising/falling labels because no prior observation exists.
- Once repeated observations establish a comparable time series, cards may show measured movement using the exact metric and window. The UI must not convert a recommendation count or one-time rank into a trend claim.

This partially rejects the proposed universal headings “Top Trending Audio” and “Top Trending Videos.” Card-level evidence labels are necessary but do not cure a false section heading.

## Binding conditions

### C1 — Scheduled evidence collection; database-read page

The `/inspiration` page reads persisted observations from ViralFactory's SQLite database. It does not synchronously call paid or rate-limited provider APIs during page render.

Collection runs through scheduled or operator-triggered jobs. Provider TTLs, regions, result caps, timeouts, budgets, and enablement live in config. A manual refresh queues a run and shows its progress; it never makes the web request wait on a provider.

The page remains useful when every provider is down: it shows the last successful snapshot, a visible evidence age, and a plain-language stale/error state.

### C2 — Dedicated append-only trend evidence model

Trend observations do not enter the Source Bank automatically. Use dedicated tables/contracts with tenant scoping:

1. **Collection run** — provider, configured endpoint key, platform, region, sanitized request parameters, start/end time, status, result count, response hash, adapter/config version, and redacted error class/message.
2. **Trend item** — stable provider-native identity, platform/content type, canonical URL, creator/title/description where available, safe preview/thumbnail references, availability state, and first/last seen.
3. **Observation** — collection-run link, item link, collected time, rank, exact metric names/values, provider evidence label, and immutable safe-payload hash.
4. **Bookmark/promotion record** — added later; records the operator action that promotes an observation without rewriting observation history.

Observations are append-only. Item metadata may gain a new version; history is not overwritten. Signed URLs, credentials, personal tokens, and secret-bearing raw payload fields are stripped before persistence. Store a redacted payload or hash, not an unsafe raw response.

Page-view cache is not provenance. A collection run is provenance.

### C3 — Provider adapters normalize mechanics, not meaning

Each provider adapter converts a documented response into the normalized evidence contract and preserves provider-specific metric names. Shared HTTP, retry, rate-limit, redaction, and cache primitives are encouraged.

Adapters must not relabel a recommendation feed as a trend chart or reinterpret unlike metrics as one score. Unknown response shapes fail visibly and retain a sanitized diagnostic; they do not emit empty “success.”

Credentials stay in environment variables. Provider names, endpoint keys, base URLs, regions, limits, TTLs, and enabled content types are config.

Tests use recorded, redacted fixtures and fake adapters. Live-provider proof is a separate deployed smoke test and must not make the automated suite network-dependent.

### C4 — Separate evidence from creative judgment

Mechanical collection preserves what the provider reported. Any interpretation of hook, pacing, structure, visual treatment, emotion, or reusable pattern is a Researcher judgment task and therefore requires:

- a versioned prompt and JSON schema;
- the referenced observation IDs and evidence snapshot;
- hypothesis language, not causal certainty;
- full LLM provenance and content-hash caching;
- an operator gate before updating a module, experiment, or process mapping.

No keyword rules or hardcoded domain taxonomy may decide why an item works.

### C5 — Source Bank promotion is explicit and later

The first slice is read-only. Later actions are deliberately distinct:

- **Bookmark** keeps an inspiration reference without making it grounding material.
- **Add to Source Bank** creates a source candidate with `status='new'`, linked to its observation and collection provenance. It does not immediately feed ideation.
- **Propose experiment** creates an async-gate proposal with evidence.
- **Propose pattern** creates a module proposal; approval is still required before a module version bump.

A trend clip is creative evidence, not automatically factual grounding. The existing Source Bank hard gate remains intact. DIVERGENCE-007's source-network question is not silently resolved by this amendment and remains a separate design item.

### C6 — No silent production-soundtrack bridge

Trend audio displayed in Inspiration is not a production soundtrack candidate merely because it is playable. AMENDMENT-011's separate rights-resolution and local-artifact contracts are mandatory before any observation can enter production.

The two features may share transport infrastructure. They must not share inferred licence status or automatically transfer an audio result from discovery to FFmpeg.

### C7 — Human UI contract

The first slice must provide, at minimum:

- top-level Inspiration navigation on every primary screen;
- responsive laptop-first and mobile layouts in the cream editorial theme;
- distinct audio and video sections with truthful evidence headings;
- platform and region filters whose current scope is visible;
- playable media only when a current safe preview exists; an unavailable state otherwise;
- creator/title, platform, provider, rank/metric label, region, evidence age, and collection time;
- relative time plus a friendly exact timestamp on demand, never raw ISO as primary copy;
- loading, first-run, empty, stale, partial-provider-failure, all-provider-failure, and unavailable-media states with a clear next action;
- no green success state for a failed or stale collection;
- long descriptions/previews expandable rather than silently truncated;
- no API keys, signed secret parameters, or raw provider jargon rendered to the operator.

The page must distinguish “we fetched data successfully” from “this item is trending.” A successful job is operational health, not creative evidence.

## Answers to DIVERGENCE-016's questions

1. **Architecture:** approved as a first-class top-level workbench owned by Researcher, not a fifth profile and not buried inside Knowledge.
2. **Data model:** dedicated append-only trend evidence tables. Explicit later promotion to Source Bank or other queues.
3. **Naming:** evidence-conditional. “Trending audio” is valid for a real chart. “Top Trending Videos” is rejected for recommendation/seed feeds; use “Video inspiration” until evidence supports a trend claim.
4. **Provider abstraction:** normalized adapter contract with preserved provider semantics, scheduled collection, config-driven endpoints/regions/TTLs, redacted fixtures, and no network-bound tests.
5. **First slice:** contracts/config/fixtures → collection jobs/store → read-only `/inspiration` UI and deployed live smoke. Bookmarking, analysis, and promotions follow as separate tasks.
6. **DIVERGENCE-015 relationship:** share only generic mechanics. Trend observations have no production rights by default; AMENDMENT-011 must separately resolve rights and acquire a local artifact.
7. **Build-plan placement:** new M14, after M13's fresh end-to-end proof. Design is ratified now; implementation does not pre-empt the currently open VF-VS-510..516 and VF-VS-702/703 corrections.

## First-slice acceptance boundary

The first slice is complete only when:

- the automated suite passes entirely against fixtures/fakes;
- a deployed collection run succeeds with each enabled live provider without exposing secrets;
- the database contains tenant-scoped collection, item, and observation rows with truthful metric labels;
- `/inspiration` loads from the database with provider network calls disabled;
- browser testing covers every state in C7 at laptop and mobile widths;
- the operator can play available items and can tell exactly why and when each item appears;
- no action can yet feed an observation into ideation, a module, or production.

## Charter effect

Charter v3.8 adds Inspiration as a Researcher-owned observatory and makes external evidence semantics constitutional: provider, time, region, endpoint meaning, and exact metric travel with every claim; recommendation, popularity, trend, rights, and causal interpretation remain distinct.
