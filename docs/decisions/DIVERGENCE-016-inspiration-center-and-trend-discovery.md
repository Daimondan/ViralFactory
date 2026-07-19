# DIVERGENCE-016 — Top-level Inspiration Center and evidence-led trend discovery

**Filed:** 2026-07-19
**Filed by:** Builder (vf-coder)
**Status:** RATIFIED WITH BINDING CONDITIONS — see `AMENDMENT-012-inspiration-evidence-workbench.md` (2026-07-19)
**Operator ruling:** Build Inspiration as a top-level operator surface, beginning with separate Top Trending Audio and Top Trending Videos sections
**Related:** Charter v3.8 §§2–4, §15, §20; M6 outward research loop; `playbooks/viral-patterns-starter.md`; DIVERGENCE-015
**Tracking issue:** https://github.com/Daimondan/ViralFactory/issues/4

## Summary

The operator approved a new top-level **Inspiration** surface that discovers current social audio and video examples before an idea enters Gate 1. The first slice is read-oriented and contains two distinct sections:

1. **Top Trending Audio**
2. **Top Trending Videos**

This is not a soundtrack picker and not a replacement for the Source Bank. It is an evidence-led creative discovery surface upstream of the existing idea queue. Audio records and video/example records remain separate but linkable.

> **Architect ruling:** Inspiration is a top-level Researcher-owned workbench, not a fifth profile. It uses scheduled collection and dedicated append-only evidence tables. Trend claims must match endpoint evidence: chart-backed audio may say “Trending audio”; recommendation/seed video feeds must say “Video inspiration,” not “Top Trending Videos.” The first slice is read-only and cannot feed ideation, modules, or production.

The requested top-level navigation item diverged from Charter v3.7 §3, which organized the working system around Researcher, Writer, Assembler, and Analyst roles, and from the prior five-group operator navigation. AMENDMENT-012 resolves the divergence: operator workbenches are not a one-to-one list of AI profiles, and M14 now defines the implementation.

## Operator problem

The current system can develop seeded or researched ideas, but it has no daily surface for seeing current social-native audio, video examples, and repeatable mechanics. The operator currently discovers those outside ViralFactory and manually carries them into production.

The desired flow begins:

```text
current audio or video evidence
        │
        ▼
Inspiration review
        │
        ▼
select or save a useful item
        │
        ▼
create/match an idea
        │
        ▼
existing Gate 1
```

This divergence covers only discovery and review. Trend-to-idea matching, Director's Room changes, and production-gate changes require later tasks or divergences.

## Live provider evidence

The builder tested existing and newly operator-supplied provider access against real endpoints on 2026-07-19. Credentials remain in `/etc/viralfactory/env` and are not recorded here.

### Bundle.social — Instagram audio

Validated live:

- HTTP 200
- 25 ranked music records
- 25 ranked original-sound records
- native Instagram audio IDs
- title, creator/artist, and duration
- no playable preview URL in the tested payload

Bundle.social therefore supports the first Instagram audio list, with a direct native-platform link where preview media is unavailable.

### Bundle.social — TikTok music

Validated live as unavailable for the current team:

- HTTP 400
- provider reports that the team has no connected TikTok account

Its documented TikTok Commercial Music Library is not equivalent to organic dialogue, meme, or creator audio and is not part of the first slice.

### TikHub — TikTok audio charts

Validated live:

- Top 50 endpoint: HTTP 200
- Viral 50 endpoint: HTTP 200
- music ID, title, artist, duration, usage count, chart context, commercial-music indicator, and media references

This is sufficient evidence for TikTok audio chart cards. It does not establish universal redistribution rights.

### TikHub — TikTok video discovery

Validated live:

- Barbados-region request: HTTP 200
- six video records returned
- video ID, caption, creator, creation time, views, likes, comments, shares, associated audio, thumbnail, and video references

The returned examples appeared substantially global rather than demonstrably Barbados-specific. The first UI must label these as provider-observed regional/recommendation results, not as a definitive Barbados chart.

### TikHub — Instagram recommended Reels

Validated live:

- HTTP 200
- two Reels returned when ten were requested
- native ID/code, caption, creator, creation time, likes, comments, video reference, and thumbnail
- no reliable view count in the tested records

This is usable as one evidence source, but not sufficient by itself to establish global momentum.

### TikHub — Instagram Explore

Validated live as unavailable:

- HTTP 400

The first slice must not call this endpoint or invent replacement data.

## Proposed first-slice source matrix

```text
Top Trending Audio
├── Instagram — Bundle.social ranked music + original sounds
└── TikTok — TikHub Top 50 + Viral 50

Top Trending Videos
├── TikTok — TikHub regional/recommendation feed
└── Instagram — TikHub recommended Reels
```

Provider labels must remain visible. TikTok and Instagram records must not be silently merged into one platform-neutral popularity claim.

## Proposed data boundary

The provider payload is evidence, not a product model. The first implementation should normalize into two separate record types.

### Trend audio record

- business/tenant owner
- platform
- provider and provider endpoint/source type
- native audio ID
- title and creator/artist
- duration
- chart name and source rank where available
- provider-reported usage count where available
- original/commercial indicator where available
- preview reference where available
- native platform URL
- first observed and last observed
- observation count
- current collection timestamp
- rights/availability note
- raw provider payload retained for audit, never rendered directly

### Trend video example record

- business/tenant owner
- platform
- provider and provider endpoint/source type
- native video ID
- creator
- caption
- posted timestamp
- views, likes, comments, and shares when supplied
- linked native audio ID when supplied
- thumbnail and short-lived media reference when permitted
- native platform URL
- source rank in the observed response
- first observed and last observed
- observation count
- current collection timestamp
- rights/availability note
- raw provider payload retained for audit, never rendered directly

### Snapshot evidence

Each collection stores immutable observation evidence for the metrics and source rank seen at that time. ViralFactory may calculate freshness and numeric deltas mechanically from repeated observations. It must not label momentum, cultural fit, format mechanics, or confidence through Python heuristics.

## Judgment boundary

The first slice contains no judgment code.

Mechanical code may:

- call configured endpoints
- validate response shape
- normalize IDs, timestamps, URLs, and numeric metrics
- cache responses
- deduplicate by provider/platform/native ID
- compare repeated numeric observations
- display explicit missing-data and stale-source states

Mechanical code may not infer:

- why a post works
- trend momentum from one observation
- cultural relevance
- humor potential
- StackPenni fit
- reusable video mechanic
- likely shelf life
- rights clearance beyond provider-supplied facts

Those understanding tasks require a later versioned prompt, JSON schema, validator, cache, and provenance record.

## Operator UI contract for the first slice

The proposed `/inspiration` page is server-rendered Flask with minimal JavaScript and uses the existing cream editorial design system.

Each section must show:

- platform and provider/source label
- native title/caption and creator
- playable preview only when the provider supplies a permitted media reference
- direct “Open on TikTok/Instagram” action
- available engagement or usage metrics without substituting zeros for missing values
- source rank when present
- collected time and posted time when present
- observation count
- explicit “observed now” language before repeated snapshots establish movement
- stale/unavailable provider state instead of an empty false-success page
- at least a 300-character caption preview with expandable full content when the source text is longer

The first slice is read-only. It does not create idea cards, save inspiration, publish, download creator media, or trigger paid generation.

## Source, preview, and rights rules

- Native platform links are the canonical review action.
- Short-lived provider media references may be used for in-console preview when supplied, but are not proof of redistribution rights.
- ViralFactory does not download or republish creator videos in this task.
- Instagram audio without a provider preview remains a link-out card; the UI must not fabricate audio.
- Every card identifies its provider and collection timestamp.
- API failure preserves the last successful snapshot and marks it stale; it never generates plausible replacement content.
- API secrets live only in protected environment configuration.

## Configuration boundary

All business and deployment values belong in a dedicated config file, including:

- enabled providers and sections
- secret environment-variable names
- source region
- endpoint paths/base URLs
- request timeout
- cache TTL
- item limits
- chart selections
- platform URL templates
- rights/availability display notes

Provider parsing mechanics remain generic Python. No StackPenni names, topics, regions, limits, credentials, or labels belong in source code.

## Proposed task sequence for BUILD_PLAN

### VF-INSP-001 — Read-only Inspiration vertical slice

**Purpose:** Prove real provider data can be normalized, cached, and reviewed on a top-level operator page without making unsupported trend claims.

**Acceptance criteria:**

1. A top-level Inspiration navigation link opens `/inspiration`.
2. The page has visibly separate Top Trending Audio and Top Trending Videos sections.
3. Instagram audio comes from the validated Bundle.social path; TikTok chart audio comes from validated TikHub paths.
4. TikTok video examples and Instagram recommended Reels come from validated TikHub paths; Instagram Explore is not called.
5. Provider-specific payloads normalize into separate audio and video record contracts.
6. Each successful collection persists first/last observed timestamps, observation count, source rank/metrics, provider identity, and immutable snapshot evidence.
7. Unchanged cached data is reused within the configured TTL.
8. A failed provider leaves cached evidence visible with a stale/error label; no fabricated fallback is shown.
9. Missing metrics render as unavailable, not zero.
10. Audio/video previews appear only when a provider supplies a reference; every record has a native-platform review link where derivable.
11. The UI explains that first observations do not prove momentum and that availability does not establish reuse rights.
12. No LLM or keyword heuristic decides trend status, mechanics, fit, rights, or cultural relevance.
13. Provider, region, endpoints, limits, labels, URLs, timeout, TTL, and environment-variable names are config-driven.
14. Unit and route tests cover normalization, deduplication, caching, stale fallback, missing metrics, HTML escaping, and no-secret rendering.
15. A real running Flask server is exercised with protected live credentials and returns non-empty audio/video sections or an honest source error.
16. No idea creation, paid generation, publishing, or media download occurs.

### VF-INSP-002 — Repeat observations and mechanical movement evidence

Persist scheduled snapshots and expose numeric rank/engagement changes without assigning semantic momentum labels in Python.

### VF-INSP-003 — LLM format-mechanic analysis

Add a versioned prompt, schema, validator, content-hash cache, and provenance logging to identify setup/payoff, performance structure, edit rhythm, linked audio, and reusable mechanic. Provider evidence remains separate from LLM analysis.

### VF-INSP-004 — Save and send inspiration to Gate 1

Add explicit operator actions to save an item or request an idea/match. Any idea produced enters the existing Gate 1 with source evidence and may return “no natural fit.”

## Charter compliance analysis

### Preserved

- Per-piece approval before publish remains unchanged.
- The first slice performs no publication or generation.
- No business values or credentials enter code.
- Provider facts remain distinct from LLM judgment.
- Mechanical extraction uses normal HTTP/SQLite libraries.
- Later LLM understanding work must use the standard prompt/schema/validator/provenance contract.
- Tenant ownership scopes every persisted record.
- Missing evidence fails honestly rather than false-greening.

### Divergence requiring architect ruling

1. **Top-level navigation:** Is Inspiration a fifth conceptual role/surface, a sub-surface owned by the Researcher, or a cross-role operator workbench that may appear in top-level navigation without changing the four-agent model?
2. **Persistence ownership:** Should trend evidence live in new dedicated tables, extend the existing Source Bank, or use dedicated records that can later register selected items into the Source Bank?
3. **Terminology:** May the operator heading remain “Top Trending Videos” if individual cards explicitly distinguish provider recommendation/chart evidence from measured momentum?
4. **Build Plan placement:** Should VF-INSP tasks form a new milestone after M13 repair, extend M6 outward research, or run as a separately bounded operator-requested vertical slice?
5. **DIVERGENCE-015 relationship:** Trend-audio discovery is upstream creative inspiration, while soundtrack discovery is production acquisition. Should their provider adapters share only mechanical transport/normalization utilities while retaining separate rights and selection contracts?

## Recommended architect ruling

The builder recommends:

- Keep the four agents unchanged.
- Define Inspiration as a top-level **operator workbench owned by the Researcher**, not a fifth agent.
- Use dedicated audio/video/snapshot records because transient social metrics and platform-native identifiers do not fit the durable Source Bank contract.
- Register an item into Source Bank only after an explicit operator save or idea action.
- Preserve the requested “Top Trending” section names while cards state the exact evidence level.
- Add VF-INSP-001 as a bounded post-M13 slice; do not alter current production gates in this milestone.

## Request

Architect review is requested on the five questions above and on the VF-INSP-001 acceptance criteria. Implementation should not silently settle these architecture questions in Flask routes or SQLite schema.