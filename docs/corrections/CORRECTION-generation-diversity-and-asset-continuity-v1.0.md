# CORRECTION: Generation Diversity & Asset Continuity — Idea Convergence, Fan-Out Fidelity, Preview Carry-Forward

**Version:** 1.0
**Status:** Approved by operator — ready for implementation
**Supersedes:** Nothing. Touches the same routes as CORRECTION-module-context-assembly-v1.1 (T2.12) — see §6 coordination.
**Priority:** S1/S3 are P1 (operator-visible failures blocking the 10-piece M3 sprint: repeated ideas; approved text mutated post-approval). S2 P2. S4 P2 (cost + trust).

Operator-reported symptoms, all confirmed in code at HEAD (2026-07-03, `ce307a3`):
17 cards converging on the same few ideas; format suggestions converging; fan-out generating X + IG for every draft regardless of approved treatment, with the approved text paraphrased; draft-stage preview images orphaned when assets regenerate.

---

## S1 (P1): Idea generation is structurally deterministic — give it variance, memory, and real sources

### Root cause (three compounding)
1. `ideas_generate` calls `backend="default"` → temperature 0 (`models.yaml`: every backend is temp 0 — the "temp 0 for processing" guardrail correctly covers judgment/extraction but wrongly swept in *generative* calls).
2. Input is static: `source-criteria` module text + first 5 feed names from `sources.yaml`. No actual source content exists yet (Source Bank is M6), so "Source Bank × modules" is currently "business description × modules", identical every run.
3. The prompt is told nothing about existing cards or kill reasons — it cannot avoid repeating itself even in principle.

### Implementation
**S1a — Generative backend alias.** In `config/models.yaml`: add backend alias `ideator` and a backend entry with real temperature (suggest a copy of the GLM entry with `temperature: 0.9`; exact value is config, not code). `ideas_generate` and `_generate_card_from_seed` switch to `backend="ideator"`. `drafter` should also get non-zero temperature — drafting is generative too; the comment at `models.yaml:15` already says "uses backend's temperature" but the backend it points at is temp 0. **Guardrail clarification for BUILD_PLAN:** temp 0 + cache applies to *judgment and extraction* calls; generative calls (ideas, drafts, fan-out adaptation) use configured creative temperature. (Cache note: with S1c/S1b the input varies per run, so the content-hash cache no longer pins outputs; no cache change needed.)

**S1b — Novelty context.** Two new prompt variables, built in the route from existing tables:
- `existing_ideas`: the most recent ~40 idea cards (all states), one line each: `[state] idea (format)`. Cap 3000 chars.
- `kill_lessons`: kill-reason feedback entries for idea cards, one line each, newest last. Cap 1500 chars.

`prompts/ideas/generate_v1.md` → **v1.2** (see §6 versioning): add both blocks with the instruction — every generated card must be materially distinct from every listed existing idea (different angle, not synonym-swapped); treat kill lessons as anti-patterns; if the source material cannot support `num_cards` distinct ideas, return fewer and say so in the rationale rather than padding with near-duplicates.

**S1c — Source snapshot (interim real material, pre-M6).** New mechanical fetcher `src/source_snapshot.py`: for each feed in `sources.yaml`, pull the latest ~10 item titles + first-paragraph summaries (feedparser + trafilatura — boring-library mechanics, no LLM), content-hash cached per feed URL with a 6-hour TTL, stored in a small `source_snapshot` table. `ideas_generate` replaces the feed-name listing with actual snapshot items (cap 4000 chars, newest first, each item carrying its source name + URL as the card's evidence link). Failures degrade to the current criteria-only behavior with a `(snapshot unavailable)` marker. **Scope guard:** this is not M6 — no YouTube API, no analysis, no scoring, no proposals; it is a dumb fetch that makes the ideation input vary with the world. M6 T6.1/T6.2 supersede it when they land.

### Acceptance
- Two consecutive generate calls (no module edits between) produce non-identical card sets; prompt variables contain the existing-ideas list (sentinel test).
- A card whose idea matches an existing line verbatim fails a similarity smoke test (normalized string containment) — test-level check, not a runtime validator.
- Snapshot table populated from a fixture feed; feed failure degrades gracefully with marker.

## S2 (P2): Format convergence — feed usage back into treatment selection

`SELECT format, COUNT(*) ... GROUP BY format` across idea_cards (or drafts — format is threaded per T3.9) → new prompt variable `format_usage`, e.g. `street-receipt: 9 · explainer-carousel: 5 · talking-head: 3`. Prompt v1.2 instruction: the treatment rationale must weigh recent usage — default to spreading across **proven** formats; choosing a heavily-used format requires the rationale to say why this idea demands it; experimental formats remain allowed per AMENDMENT-004.

### Acceptance
- Variable present with real counts; a fixture with one dominant format yields cards whose rationales reference usage (sentinel: the counts string appears in the rendered prompt; rationale behavior spot-checked in the A/B sprint, not unit-asserted).

## S3 (P1): Fan-out must respect the treatment and never rewrite approved text

### Root cause
`assets_fan_out` loops `business.yaml` platforms unconditionally; every platform — including the format's native one — gets an LLM adaptation pass over the Gate-2-approved `draft_text`. The approved artifact mutates after approval, violating per-piece approval semantics in spirit: what ships is not what was approved.

### Ruling
The approved draft text is inviolable on its native platform. Adaptation is for *other* platforms only, and the platform set comes from the treatment's format, not a blanket config loop.

### Implementation
1. **Platform set:** resolve the card's treatment format → Format Guide entry → its `platforms` field (via `module_store.get_entry`); intersect with configured business platforms. Request body may pass an explicit `platforms: [...]` override (UI: checkboxes on the fan-out control, pre-checked to the resolved set). Empty resolution (format missing/no platforms declared) falls back to configured platforms **with a warning in the response** — never silently.
2. **Native platform, verbatim packaging:** the first/native platform of the format produces its asset **without a rewrite**. If the format's structure requires segmentation (thread → posts[], carousel → slides[]), one LLM call is permitted in *structuring mode*: new prompt `prompts/assets/structure_v1.md` whose contract is — split/arrange the provided text into the platform structure **reusing the wording verbatim**; you may only add platform furniture (numbering like "1/7", slide labels); you may not rephrase, compress, or extend. If no segmentation is needed (single post), no LLM call at all: `content = draft_text`, mechanically truncation-checked against platform limits (over-limit → asset created in state `fix` with a note, operator decides).
3. **Non-native platforms:** existing `fan_out_v2` adaptation path, with one added instruction (bump per §6): preserve the master's wording wherever the platform allows; adaptation is structural and length-driven, not stylistic.
4. Asset rows record `native: true/false` (new column, idempotent migration) so Gate 3 can badge the verbatim one.

### Acceptance
- Draft with format platforms `[X]` and business platforms `[X, Instagram]`, no override → one asset, platform X, `native=1`, content byte-identical to `draft_text` (single-post fixture).
- Thread-format fixture → posts[] whose concatenation (minus added numbering tokens) equals the draft text normalized for whitespace.
- Override body `platforms: ["Instagram"]` → IG asset only, adapted path, `native=0`.
- Unresolvable format → configured platforms + warning key in response.

## S4 (P2): Carry draft-stage previews into assets — stop paying twice and orphaning what was judged

### Root cause
Asset image generation reads only the asset's fan-out `image_prompts` (new text → new hash → new generation); draft-owned media rows are never linked or shown at Gate 3.

### Implementation
1. At fan-out, after creating each asset: copy the draft's media rows (`owner_type='draft'`, this draft_id) as new `asset_media` rows — `owner_type='asset'`, the new asset_id, **same file path** (link, don't re-render; no file copy), provenance/context noted `carried from draft preview (draft {id})`.
2. `generate_visuals` (asset images) first counts carried media; it generates only for fan-out prompts beyond what's carried (or all, if the operator passes `regenerate: true`). Response distinguishes `carried` vs `generated`.
3. Gate 3 UI shows carried images with a "from draft preview" badge alongside any newly generated ones.
4. Draft-media deletion (if/when a delete path exists) must check for asset references before removing files; if none exists yet, add a code comment at the file-write site noting the shared-path invariant.

### Acceptance
- Fan-out on a draft with 2 preview images → each spawned asset lists 2 carried media rows pointing at the existing files; no new generation calls (assert media adapter call count).
- `generate-images` afterward generates only uncovered prompts; `regenerate: true` forces fresh ones without deleting carried rows.

## 5. Explicitly deferred
- Real Source Bank ingestion/analysis (M6 T6.1–T6.4) — S1c is a placeholder it will supersede.
- Embedding/similarity-based novelty checking on ideas — revisit only if the prompt-level distinctness instruction proves insufficient across a full sprint; keep the no-retrieval-for-modules ruling untouched (this would be about *outputs*, a different question).
- Per-platform scheduling/cadence interaction with series children — untouched here.

## 6. Coordination & versioning
- **Prompt bumps:** `ideas/generate_v1.md` → v1.2 (S1b + S2 blocks). `assets/fan_out_v2.md` is already due for v2.1 (visual_style, module-context correction); fold the S3.3 preserve-wording instruction into the **same v2.1** — one bump. New file `assets/structure_v1.md`.
- **T2.12 registry:** the interim `context_assembly` shim is live in these routes; when `config/processes.yaml` lands (CORRECTION-module-context-assembly-v1.1), the new variables (`existing_ideas`, `kill_lessons`, `format_usage`) join the `inputs` lists of `ideas_generate`, and `assets_structure` becomes its own process spec (backend: default, temp 0 — structuring is mechanical-adjacent, not generative). Nothing here blocks or is blocked by T2.12; whichever lands second folds the other in.
- **Sequencing within this file:** S1a (config only, 5 minutes) → S3 (approval integrity) → S1b/S1c → S4 → S2.

## 7. BUILD_PLAN impact
- Add under M3: **T3.13 Generation diversity & fan-out fidelity (this correction)** — AC: consecutive idea runs non-identical with novelty context in provenance; native-platform asset text byte-equal to approved draft; draft previews carried into assets.
- Annotate T3.7's AC ("per-platform variants produced from Format Guide") — currently produced from *business config*, not the Format Guide; S3 makes the AC true as written.
- The 10-piece M3 sprint checkpoint should not run until S1 and S3 land — its A/B results would measure a broken generator.
