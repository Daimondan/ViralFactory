# AMENDMENT-011 — Soundtrack discovery, rights evidence, and Asset-gate approval

**Filed:** 2026-07-19
**Filed by:** Architect (vf-architect)
**Status:** APPROVED WITH BINDING CONDITIONS — ratifies DIVERGENCE-015; incorporated into Charter v3.8
**Ratifies:** `docs/decisions/DIVERGENCE-015-soundtrack-discovery-ranking-auto-apply.md`
**Related:** AMENDMENT-010; `docs/reviews/REVIEW-inbox-divergences-015-016-2026-07-19.md`

## Decision

Approve automatic soundtrack discovery, ranking, acquisition, and preview mixing **as part of Asset assembly**, with the exact selected soundtrack approved together with the finished per-platform asset at Gate 3.

This replaces a duplicate soundtrack micro-gate. It does **not** weaken human approval:

1. The system may automatically prepare a suggested, rights-valid soundtrack and a small set of alternatives before Gate 3.
2. Gate 3 is the first and only approval of the soundtrack-bearing asset. The operator sees and plays the actual mixed asset, the active track, its rights evidence, and any alternatives.
3. Switching the track creates a new asset version, re-renders the preview, invalidates any prior Gate 3 approval, and requires approval of the new exact artifact.
4. Gate 4 remains mandatory. No soundtrack selection, ranking, or asset approval can publish a piece.
5. A VO-only asset must show the planner's rationale at Gate 3. Approving that exact VO-only asset is the required explicit human approval.

The divergence is therefore approved **in principle**, but the implementation that landed before approval is not accepted as proof. The corrective tasks in `BUILD_PLAN.md` are binding.

## Why the earlier preview gate changes

AMENDMENT-010 correctly required the operator to know whether a Reel uses VO, source sound, or music and prohibited silent fallbacks. Its separate pre-acquisition preview gate duplicated the later decision once the system could cheaply discover and mix previewable candidates automatically.

The constitutional requirement is approval of the **exact audience-facing media artifact and audio choice**, not an extra click before that artifact exists. Gate 3 is the stronger checkpoint because it lets the operator judge the soundtrack against the real VO, pacing, visuals, captions, and mix.

Paid acquisition still requires an explicit fresh cost approval before spend. Cost approval is not content approval and cannot be reused as Gate 3 approval.

## Binding conditions

### C1 — Discovery evidence is not usage rights

A provider returning a playable or downloadable audio URL does not prove commercial reuse rights. Social-platform trend APIs and API wrappers expose discovery metadata; they do not grant a licence to download, remix, synchronize, or republish that audio.

No provider may be labelled `commercial_safe` by code or provider name. In particular, an Instagram-audio discovery result is not automatically licensed for commercial use. Meta's published music guidance says use of music for commercial or non-personal purposes is prohibited unless appropriate licences have been obtained; API access does not alter that rule.

A candidate is render-eligible only when it carries a persisted rights record with:

- `rights_status`: `verified | restricted | unknown | expired`;
- `rights_source` and stable `terms_url`;
- `terms_retrieved_at` and immutable `terms_evidence_hash`;
- `commercial_use_allowed` and `synchronization_allowed` as evidence-backed values, never provider assumptions;
- platform, territory, account-type, and expiry constraints when applicable;
- attribution requirements;
- `download_authorized` and the authorized acquisition method;
- any cost estimate and the approval record authorizing that cost.

`unknown`, missing, stale, or contradictory rights evidence fails closed. The candidate may remain visible as trend inspiration but cannot be mixed into production.

Rights evidence is a snapshot, not a permanent truth. A cached asset keeps the snapshot that authorized its acquisition; a new acquisition re-checks current terms.

### C2 — Separate trend discovery from production acquisition

The soundtrack pipeline has three explicit contracts:

1. **Discovery observation** — what a provider reported, where, when, and with what metric.
2. **Rights resolution** — whether this business may acquire and synchronize this exact recording for this exact use.
3. **Local media artifact** — a non-empty local file with content hash, measured duration, source observation, rights snapshot, and acquisition provenance.

Only contract 3 enters FFmpeg. A remote preview URL, social sound ID, or popularity metric is not an asset.

The Inspiration Center introduced by AMENDMENT-012 may show social audio with unknown production rights. It must not silently route that audio into soundtrack acquisition. Shared transport, retry, redaction, and caching primitives are allowed; shared trust conclusions are not.

### C3 — The planner supplies search intent; scripts execute it

Mood, genre, narrative role, and query formulation are judgment tasks. The schema-validated soundtrack planner must emit bounded `search_queries[]` and fit constraints from the approved Writer contract, soundtrack mode, visual events, and Visual Style Guide.

Python may normalize, deduplicate, cap, cache, and execute those queries. It may not infer mood or invent queries through keyword or substring rules.

No search call runs when the approved mode is `vo_only` or `source_sound` unless the operator explicitly changes the mode.

### C4 — Ranking is rights-first and evidence-honest

Ranking runs only over render-eligible candidates. The ranking prompt receives the candidate's fit metadata and observation evidence, including metric name, value, provider, region, collection time, and provider rank where available.

The decision hierarchy is:

1. rights and acquisition validity — hard requirement;
2. fidelity to the approved audio/narrative intent;
3. compatibility with VO, edit pacing, visual events, duration, and platform;
4. measured popularity as a bounded tie-breaker among genuinely comparable observations;
5. audio quality and mix feasibility.

A universal `80% fit / 20% popularity` claim is rejected unless the inputs are actually normalized, current, and comparable and the policy is configured. Cross-provider counts, chart ranks, and stock-library metadata must not be treated as one scale. When popularity is unavailable, the UI and provenance say so; the system does not manufacture a neutral score.

The LLM performs qualitative judgment through a versioned prompt and schema. Deterministic code validates IDs, rights eligibility, metric types, and required fields; it does not recreate ranking judgment with arithmetic or keywords.

### C5 — One soundtrack contract, one active artifact

The auto-selection path must not produce one mix and then run a second planner that can select a different mode or track. The versioned soundtrack contract is the single source of truth and identifies:

- approved Writer contract/hash;
- soundtrack mode and rationale;
- planner prompt/version and search intent;
- candidate set/version;
- active track and rights-record version;
- local track artifact hash;
- mix settings/config version;
- mixed asset hash/version;
- active alternatives;
- Gate 3 approval status.

Fallbacks are explicit state transitions. A provider error, empty candidate set, failed rights check, failed download, zero-byte file, or failed mix must not set an `auto_processed` or ready flag. It yields plain-language `needs_operator_decision` or a retryable production failure.

### C6 — Mix and alternatives are real artifacts

FFmpeg remains the boring mechanical renderer. Mix policy values live in config/modules, not Python. Every generated preview is persisted as an asset version with measured duration and content hash; fixed temporary filenames are never treated as identity.

The Gate 3 UI must provide:

- the actual finished video/audio preview;
- an **Active soundtrack** card with title, creator/source, fit rationale, rights status, and evidence age;
- up to three playable alternatives mixed against the same approved VO/content;
- one functional **Use this track** action per alternative;
- loading, unavailable, stale-rights, mix-failed, and no-rights-valid-candidate states in plain language;
- no green `Approved`/`Passed` badge before human Gate 3 approval.

A switch is atomic: set candidate → create and validate a new mix → activate the new asset version → invalidate prior Gate 3 approval. A failed switch leaves the prior valid version active and reports the failure.

### C7 — Cost, rate, cache, and credential discipline

Provider credentials remain environment variables. Endpoints, provider enablement, region, result caps, refresh TTLs, request budgets, mix policy, and feature rollout are configuration. Credentials, signed query strings, and secret-bearing provider payloads are never persisted or logged.

Tests use recorded, redacted fixtures and fake adapters. A separate deployed smoke test verifies live credentials without printing or storing them.

## Answers to DIVERGENCE-015's questions

1. **Source priority:** no fixed provider trust hierarchy. Query configured enabled providers; filter by evidence-backed rights and acquisition capability before ranking. A stock catalogue may be production-eligible while a social trend source remains inspiration-only.
2. **Popularity weight:** accepted only as a bounded tie-breaker over comparable evidence. The proposed universal 20% weight is rejected.
3. **Fallbacks:** provider failure may fall back to another configured provider; no rights-valid candidate yields visible `needs_operator_decision`, not silent VO-only. VO-only proceeds only when the soundtrack contract declares it and Gate 3 shows the rationale.
4. **Alternative count:** three is the default presentation cap, configurable as a mechanical UI limit. All displayed alternatives must be playable and rights-valid.
5. **Licence policy:** rights evidence is mandatory and versioned. API availability is never licence evidence.
6. **Build-plan tasks:** the divergence's proposed VF-VS-510..515 are superseded by the corrective VF-VS-510..516 tasks written into `BUILD_PLAN.md` with stricter rights, state, and proof criteria.

## Charter effect

Charter v3.8 changes the soundtrack rule from “preview approval before acquisition” to:

> Discovery and preview assembly may run automatically, but only rights-valid local media may enter the renderer. Gate 3 approves the exact soundtrack-bearing asset. Track changes create a new asset version and invalidate prior approval. Paid acquisition still requires fresh cost approval before spend. Discovery evidence never implies usage rights.

## Implementation order

VF-VS-510 through VF-VS-516 are blocking corrections inside M13 and must land before VF-VS-702/703 can be accepted. Existing code is evidence to audit, not a completed task set.
