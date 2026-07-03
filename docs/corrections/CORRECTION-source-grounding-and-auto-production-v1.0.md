# CORRECTION — Source Grounding, Auto-Production Chain, and AI Profiles — v1.0

**Date:** 2026-07-03
**Author:** Architect (Claude)
**Status:** Approved by operator (verbal, this session)
**Supersedes:** Nothing. Extends CORRECTION-format-selection-living-v1.0 (truncation doctrine) and AMENDMENT-005 (processes are module compositions).
**Priority:** P1 architecture — sequence after T3.13 (S1+S3) lands. Section 1.3 truncation fix and Section 4 cleanup are P0/quick and may land immediately.

---

## Operator feedback driving this correction (verbatim intent)

1. Ideas are strong as-is (treatment, scope included) — but **every idea must be grounded in listed sources**, and an idea may draw on **more than one source** (different sources composed to tell one story).
2. Once an idea is approved, it should **not** go to a draft page where the operator clicks Generate, then an asset page where the operator clicks Generate again. **Approval is the production trigger.** The approved card's full information — idea, hooks, treatment, sources, all modules — is used to produce the asset automatically. The operator's next touchpoint is reviewing the finished asset.
3. Introduce **AI profiles**: a **Researcher** (ideation, source scouting, social-media-native, knows how to tell a story and which format tells it best), a **Drafter** (takes the detailed idea and produces the final asset as specified by the Researcher), and an **Analyst** (reads results, drives the inward and outward loops, and scrapes current and hard-to-find archival news into the Source Bank for the Researcher to ponder).

## Architect findings confirming the feedback (live repo walk-through, app run locally)

- **F-A: Sources die at Gate 1.** `prompts/draft/generate_v2.md` has no evidence/source variable. `draft_generate` in `src/app.py` assembles idea, hooks, and module views — never `evidence_links`, never the underlying source content. The drafter writes from a one-line idea. This silently violates "AI-originated ideas must be grounded in living modules" at the production stage.
- **F-B: `evidence_links` are decorative.** They are freeform `{url, note}` objects emitted by the LLM, not references to stored source records. Nothing verifies they correspond to real Source Bank material. The "Source Bank" today is the source-criteria module plus a 4KB-capped RSS snapshot — there is no addressable store of sources.
- **F-C: Blind truncation survives in ideation.** `source_material[:4000]` in `ideas_generate` (src/app.py ~line 4061) and `SNAPSHOT_CHAR_CAP = 4000` in `source_snapshot.py`. Same disease CORRECTION-format-selection killed for modules.
- **F-D: Post-approval dead air.** Confirmed by operator simulation: approve → card sits in "Approved ideas (ready to draft)" → operator must click Generate draft, gate, proceed, Generate variants, Generate images. Three-plus manual generation clicks after the decision was made.
- **F-E: Dead code.** `ideas_gate_decision` contains an unused `response_data` construction inside the series branch.

---

## Section 1 — Source Bank as an addressable store

### 1.1 New table: `sources`

```sql
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_slug TEXT NOT NULL,
    source_type TEXT NOT NULL,        -- 'rss_item' | 'scraped_article' | 'operator_material' | 'archival' | 'manual'
    title TEXT NOT NULL,
    url TEXT,                          -- nullable (operator materials may have none)
    summary TEXT,                      -- short extract for selection-stage injection
    content TEXT,                      -- full extracted text for production-stage injection
    origin TEXT NOT NULL DEFAULT 'system',  -- 'system' (snapshot/scraper) | 'operator' | 'analyst'
    first_seen TEXT NOT NULL,
    content_hash TEXT,                 -- dedupe
    status TEXT NOT NULL DEFAULT 'active'   -- 'active' | 'archived'
);
```

- `source_snapshot.py` writes its fetched items **into this table** (dedupe on content_hash) instead of only into its private snapshot blob. The snapshot table may remain as cache; `sources` is the system of record.
- Ingested operator materials (`src/materials.py`) register a `sources` row (`source_type='operator_material'`) pointing at the extracted content. Do not duplicate content — a reference/join to the materials store is acceptable; the row must exist so ideas can cite it by ID.
- Add `business_slug` scoping everywhere, consistent with the provenance table pattern.

### 1.2 Idea cards carry `source_refs`

- New column on idea cards: `source_refs` — JSON list of `sources.id`, **one or more**. `evidence_links` becomes a derived display field (url + note resolved from the referenced rows plus any LLM annotation), not the grounding mechanism.
- `prompts/ideas/generate_v1.md` changes:
  - Source material section is rebuilt from `sources` rows, each item prefixed with its ID: `[S14] title — summary`.
  - The card schema replaces free `evidence_links` with `source_refs: [14, 22]` plus optional per-ref `note`.
  - **New rule, verbatim:** "Every idea MUST cite at least one source by ID. Ideas that synthesize two or more sources into a single story are encouraged — when multiple sources together reveal a pattern, contrast, or arc that no single source shows, that composition is itself the idea. State in the rationale what each cited source contributes."
- Validation in `ideas_generate` / `ideas_seed`: reject (or flag and quarantine) any card whose `source_refs` don't resolve to real `sources` rows. Human seeds auto-register the seed as a `manual` source so seeded cards are grounded too.
- Ideas page: render the resolved source list on every card — title as link where url exists, source_type badge. This is the operator-visible answer to "list sources."

### 1.3 Kill remaining truncation (P0, land immediately)

- Remove `source_material[:4000]` in `ideas_generate`. Selection stage receives the **digest view** (ID + title + summary per active source, recency-ordered, bounded by *count* — e.g. most recent 40 — not by blind character slicing). Production stage receives **full content** of only the cited sources. Same stage-appropriate-injection doctrine as format selection.
- Retire `SNAPSHOT_CHAR_CAP` in favor of per-item summary limits + item-count bounds.

### 1.4 Sources flow to production

- `prompts/draft/generate_v2.md` → v2.3: add a `{grounding_sources}` section — full content (or generous extracts) of every source in the card's `source_refs`, each labeled with title and ID, with the instruction that facts, quotes, dates, and specifics in the draft must come from these sources, and that fabricating specifics not present in them is prohibited.
- `draft_generate` assembles this variable by resolving `source_refs`. If a referenced source has `content` empty, degrade to summary with a visible `(summary only)` marker — never silently.
- Fan-out and visual prompts receive the source *titles/notes* only (they must not re-write facts; the draft is authoritative per T3.13 S3).

---

## Section 2 — Approval is the production trigger (auto-chain)

### 2.1 Ruling

Gate 1 approval **starts production**. The chain: draft generation → per-platform fan-out → visual/asset previews, executed as a background job (extend `src/jobs.py`), landing the operator at the **asset review stage** with everything already produced. No "Generate" clicks between approval and asset review.

The draft does **not** disappear — it becomes an internal, versioned artifact produced en route. Gate 2 becomes a *passive* gate: the asset page shows the draft text (editable, reopenable exactly as the current shipped-state controls allow), and editing the draft invalidates and regenerates downstream assets (the staleness warning from UI-REVIEW-002 already exists — wire it to a one-click regenerate). The consolidated human decision point is the asset stage. This is consistent with the charter's tapering gate intensity: brutal at Ideas, lighter downstream — the operator asked for exactly this consolidation.

**The no-auto-publish rule is untouched and absolute.** The chain terminates at asset review. Publish remains a human gate, per piece.

### 2.2 Mechanics

- `ideas_gate_decision` on `approve`:
  - If `capture_required` non-empty → state `awaiting_capture` as today; the chain fires automatically when the final capture upload completes.
  - Else → state `approved` + enqueue `produce_chain(card_id)` job. Card state advances through `producing` → `asset_ready` (new states; update state machine + UI badges).
- `produce_chain` steps: (1) draft generation with grounding sources per Section 1.4; (2) fan-out; (3) visual generation for image-required formats. Each step records provenance as today.
- **Failure handling:** the chain halts at the failed step, card state → `production_failed` with the step name and error surfaced in plain language on the Create page, with a "Retry from failed step" control. Never silently stall, never retry-loop unattended.
- Series: parent approval spawns children as today (state `new`, per F3); each child's own approval triggers its own chain. Bulk-approve-children enqueues chains for all.
- Create page restructure: "Approved ideas (ready to draft)" section is replaced by "In production" (spinner/state per card) and "Ready for review" (asset stage). Draft page remains reachable from the asset page for reopen/edit, not as a mandatory waypoint.
- Concurrency: serialize chains per business (single worker queue) for M2/M3 — no parallel LLM storms on the VPS.

### 2.3 Sequencing constraint

Do not enable the auto-chain until T3.13 S1 (generation diversity) and S3 (fan-out verbatim packaging) are confirmed landed — an auto-chain amplifies any generation defect by running it unattended. The Section 1 source plumbing should land first or together, so the first auto-produced drafts are already source-grounded.

---

## Section 3 — AI Profiles (Researcher / Drafter / Analyst)

### 3.1 Ruling

Profiles are **named compositions, not code classes** — the direct application of AMENDMENT-005. New config file `config/profiles.yaml`, versioned, gate-only writes:

```yaml
profiles:
  researcher:
    description: >
      Ideation and source scouting. Social-media-native: selects the story,
      the format that tells it, and the treatment. Owns Gate-1-facing output.
    model: <from models.yaml roles>
    temperature: generative        # per T3.13 S1 temperature doctrine
    prompts: [ideas/generate, ideas/series_breakdown]
    module_views: [viral_patterns, audience_insights, story_frameworks, format_guide_digest, source_bank_digest]
  drafter:
    description: >
      Takes the approved, fully-specified idea (treatment + grounding sources)
      and produces the final asset exactly as the Researcher specified.
    temperature: generative
    prompts: [draft/generate, assets/fan_out]
    module_views: [voice_profile, tells_checklist, visual_style, format_guide_full_entry, grounding_sources_full]
  analyst:
    description: >
      Reads performance results; drives the inward loop (own-format/scope
      performance into Format Guide evidence) and outward loop (decomposing
      viral mechanics in the domain); scrapes current and archival news into
      the Source Bank for the Researcher.
    temperature: judgment          # temp-0 class
    prompts: [analysis/*, proposals/*]
    module_views: [format_guide_full, metrics_views, source_criteria]
```

- Each pipeline LLM call declares the profile it runs under; `llm_adapter` resolves model/temperature through the profile, which resolves through `models.yaml` roles. **Backend selection continues to flow through the adapter's `backend` parameter** (BYO-AI hook, unchanged).
- Provenance rows gain a `profile` column so every artifact records which profile produced it.
- Operator-visible copy may name the profiles ("Researcher proposed 6 ideas", "Drafter produced the asset") — this is good plain-language readback, not decoration.

### 3.2 Scope discipline

- Researcher and Drafter are **relabelings plus view-map hygiene** of existing prompts — cheap, land in M2/M3.
- Analyst's *loop* duties attach to existing metrics/proposal machinery (M4/M5 as planned).
- Analyst's *scraping* duty ("current and old news hard to find or uncover") is **M6 scope** — but it now has a defined landing zone: it writes `sources` rows (`origin='analyst'`, `source_type='scraped_article'|'archival'`) into the Section 1 table, where the Researcher's digest picks them up. Nothing in M6 needs to invent storage; the substrate exists. Analyst never writes modules directly — its module updates remain proposals through the gate, as everything does.

---

## Section 4 — Housekeeping (land with any batch)

- Remove the dead `response_data` block in `ideas_gate_decision` (series branch).
- CONTEXT.md additions:
  - "Every idea cites sources by ID from the Source Bank; one idea may compose multiple sources into a single story; cited source content travels with the idea through production."
  - "Gate 1 approval triggers production automatically through to asset review. Publishing is never automatic."
  - "AI work runs under named profiles (Researcher, Drafter, Analyst) defined in config/profiles.yaml — compositions of prompts, module views, and model settings, per AMENDMENT-005."

## Acceptance criteria

1. A generated idea card with unresolved `source_refs` is rejected/quarantined; every rendered card lists its sources with links and type badges; at least one multi-source card demonstrably cites ≥2 sources with per-source rationale.
2. Approving a capture-free idea produces, with zero further clicks, a reviewable asset (draft text visible + per-platform variants + previews where applicable) or a plain-language failure with retry — verified end-to-end on the Tailscale console.
3. Draft prompt payload for an auto-produced draft contains the full content of every cited source (inspectable via provenance).
4. No `[:N]` character slicing remains on source material paths; grep for `[:4000]`, `[:2000]`, `[:1500]` across `src/` returns none on module/source injection paths.
5. Provenance rows carry the producing profile.
6. All existing tests pass; new tests cover source_refs validation, chain state transitions (including `production_failed` + retry), and profile resolution.
