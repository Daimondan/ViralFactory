# CORRECTION: Format Selection — Truncation Bug + Living Selection Architecture
**File:** `CORRECTION-format-selection-living-v1.0.md`
**Version:** 1.0
**Date:** 2026-07-03
**Status:** Approved for implementation
**Supersedes:** Nothing. Amends `prompts/ideas/generate_v1.md`, `prompts/assets/fan_out_v2.md`, `prompts/format_guide/analyze_v2.md`, and related code paths in `src/app.py`, `src/pipeline.py`, `src/module_store.py`.
**Depends on:** Nothing in the session-memory correction. This is pipeline-side and can land in the current batch.

---

## Part A — P0 bug: module truncation in idea generation

### A.1 The bug

Every idea-generation call site in `src/app.py` injects living modules truncated to 2,000 characters (1,500 at one site):

```python
"viral_patterns":    modules.get("viral-patterns", "(not built)")[:2000],
"audience_insights": modules.get("audience-insights", "(not built)")[:2000],
"story_frameworks":  modules.get("story-frameworks", "(not built)")[:2000],
"format_guide":      modules.get("format-guide", "(not built)")[:2000],
```

Call sites: `_generate_card_from_seed` (~line 3733), the ai_originated generation path (~3821), and two further sites (~4179, ~4956).

The Format Guide on disk (`modules/stackpenni/format-guide.md`) is **17,139 characters**. The first 2,000 characters contain the summary paragraph and roughly half of the X Thread entry. The LLM performing format selection **never sees**: the Reel entry, the capture requirements, the experimental formats, or the decision table. The summary opens with "deep explainers and how-tos become threads on X and carousels on Instagram," so the visible fragment actively biases toward threads/carousels. This — not decision-table weighting — is the proximate cause of video under-suggestion. The other three modules are silently degraded the same way.

### A.2 The fix is NOT raising the cap

Do not fix this by injecting the full 17KB guide. Skeletons and structure notes are drafter/fan-out concerns; they are noise at selection time. The fix is **stage-appropriate injection** (Part B.4): selection sees a compact digest of ALL formats; production sees the FULL entry of ONE format. The truncation constants are removed entirely — module content injected into prompts must never be blind-truncated. If size must be bounded, bound it by building purpose-specific digests, not by slicing markdown mid-sentence.

The same rule applies to the other three modules: audit each injection site and decide per-stage what representation that stage actually needs. For this correction, minimum scope is the Format Guide; flag the other three for a follow-up digest pass rather than leaving `[:2000]` in place — as an interim measure they may be injected whole (they are smaller), but no `[:N]` slicing survives this correction.

---

## Part B — Architecture: selection by affordance and evidence, not taxonomy

### B.1 Ruling and rationale

The decision table (message type × platform → format) is removed as selection authority. It is an authored taxonomy: both the message-type categories and the mappings were fixed at onboarding time. A living system cannot learn its way out of a hardcoded taxonomy — patching the table (mapping more types to Reel) just hardcodes a different bias.

Replacement model, three layers:

1. **Affordances** (what a format is structurally good at) — descriptive, medium-level, per format entry.
2. **Evidence** (why we believe it) — starts as platform priors, is overwritten by tenant performance data via the inward loop. Human-gated amendments per AMENDMENT-004.
3. **Distribution feedback** (what we've actually been producing) — injected at selection time so monoculture is visible and self-correcting.

Selection is a reasoning task: *what does this idea need to land, which format's affordances supply that, what does the evidence say, and what does the portfolio need.* The rationale field cites affordances, evidence, and (when relevant) distribution — never table rows.

Governing principle, to be added to `CONTEXT.md`:

> **Prompts carry procedures; modules carry knowledge.** Any domain taxonomy embedded in a prompt file (message types, format structures, platform mappings) is a defect: baked-in taxonomy cannot learn. Prompts describe how to reason; living modules supply what is currently believed, and the loops update the modules.

### B.2 Format Guide schema changes (`FORMAT_GUIDE_SCHEMA`, `format_guide/analyze_v3.md`, `format_guide_to_markdown`)

Per-format entry changes:

- **ADD `affordances`** — list of 3–6 strings describing what the format structurally delivers, in medium-level language. Examples: `"shows a human face and voice"`, `"demonstrates a process visually in motion"`, `"carries sequential multi-step logic"`, `"lands one idea with maximum punch"`, `"ephemeral / low-polish authenticity"`, `"invites structured audience response"`. These are NOT message types. `best_for` is retained for human readability but is advisory; selection reasons over `affordances`.
- **ADD `performance_evidence`** — object: `{"source": "platform_prior" | "tenant_data", "notes": "string", "last_updated": "ISO date"}`. All entries initialize as `platform_prior` with the general-knowledge rationale. The inward loop replaces `notes` and flips `source` to `tenant_data` as engagement data lands (see B.7).
- **ADD `variant_type`** — string enum consumed by fan-out and the assets table: `thread | carousel | reel | single_post | story_series | poll | newsletter | <new>`. New experimental formats must declare their variant_type in the format_spec.
- **ADD `aspect_ratio`** — string (e.g. `"9:16"`, `"1:1"`, `"16:9"`), so fan-out image-prompt rules come from the entry, not the prompt.
- **REMOVE `decision_table`** from the schema and from `analyze_v3.md`'s required output. The analyze prompt's task statement changes from "produce a decision table" to "produce format entries with affordances and evidence priors."

Migration for the existing StackPenni guide: regenerate is NOT required. Hermes performs a one-time mechanical migration of `modules/stackpenni/format-guide.md` → v1.1: derive `affordances` from each entry's existing `best_for` + structure notes (rewritten in medium-level language, no message-type nouns), add `performance_evidence` as platform_prior citing the existing Provenance line, add `variant_type` and `aspect_ratio`, delete the Decision table section, bump version, store via ModuleStore (versioned, so v1.0 archives normally). This migration is a module amendment and goes through the normal human gate: Daimon approves the migrated guide before it becomes the selection source.

### B.3 Persist guide JSON alongside markdown

`ModuleStore.store()` currently persists markdown only; `load_json` works only if a ```json block leads the file (it doesn't for the guide). Amend the format-guide store path to also write the validated JSON next to the markdown (`format-guide.json`, versioned identically to the provenance file pattern already used at `module_store.py` ~line 168). The selection digest (B.4) and fan-out entry injection (B.6) build from JSON, not from markdown parsing. Backfill: the v1.1 migration in B.2 is authored as JSON first, rendered to markdown second.

### B.4 Stage-appropriate injection

**Selection stage (idea generation, treatment revision):** inject `{format_digest}` — built from the guide JSON, one compact block per format:

```
- Instagram Reel Script | IG | status: proven | effort: high | capture: REQUIRED
  affordances: shows a human face and voice; demonstrates a process visually; personality-forward delivery
  evidence: [platform_prior] Reels favor personality-driven, high-energy delivery on IG
```

All formats, ~5 lines each, no skeletons, no structure notes. This replaces `{format_guide}` in `generate_v1.md` → `generate_v2.md`.

**Production stages (draft, fan-out):** inject `{format_entry}` — the FULL entry (skeleton, structure notes, length, variant_type, aspect_ratio, capture tasks) for the ONE format chosen at Gate 1. Nothing about other formats.

### B.5 Distribution feedback into selection

Add `get_format_distribution(business_slug, window=30)` to `pipeline.py`: counts of `treatment.format.format_name` over the last N idea cards (all states) AND the shipped `format_breakdown` that `get_pipeline_stats` already computes. Inject as `{format_distribution}` into `generate_v2.md`:

```
Recent treatment proposals (last 30 cards): X Thread 14, Instagram Carousel 9, X Single Post 6, Instagram Reel 1, others 0
Shipped drafts to date: X Thread 5, Instagram Carousel 3
```

Prompt rule (in `generate_v2.md`, Rules section):

> **Portfolio balance:** Consult the format distribution. If a format's affordances fit this idea well but the format is absent or heavily underrepresented in recent output, prefer it and say so in the rationale. Do not converge on the same two formats by default. Never force a poorly-fitting format for variety alone — fit first, then balance.

No format is privileged by name. Video recovers because a near-zero Reel share is visible at every selection, and the same mechanism protects any future format from drought.

### B.6 Fan-out v3 (`prompts/assets/fan_out_v3.md`)

Delete the four hardcoded "Platform-specific structure rules" blocks. They contradict AMENDMENT-004: an experimental format approved at Gate 1 currently has no fan-out path. Replace with:

- Inject `{format_entry}` (full entry per B.4, including skeleton, structure notes, `variant_type`, `aspect_ratio`).
- Task instruction: "Structure the variant according to the format entry below. `variant_type` and image-prompt aspect ratio come from the entry."
- For experimental formats, the entry is the `format_spec` carried on the approved idea card (which must declare variant_type and aspect_ratio — enforce in `IDEA_CARD_SCHEMA`: when `experimental=true`, `format_spec` is required and must contain both).
- Output schema unchanged except `variant_type` is no longer a closed four-value enum in prose; validation accepts the value from the entry.

### B.7 Capture enforcement is code, not prompt

After card generation, before persisting: load the chosen format's entry. If `requires_human_capture == "required"` and `treatment.capture_required` is empty → reject, retry the LLM call ONCE with the violation appended ("The chosen format requires human capture; the card must include specific capture tasks"), and if it fails again, persist the card in a `needs_repair` state surfaced to the operator rather than silently passing. The prompt keeps its capture instructions, but correctness no longer depends on the LLM remembering.

This also implements the awaiting-capture flag correctly: any card whose format requires capture enters the existing capture-task flow with concrete tasks attached.

### B.8 The learning loop seam (wire now, fill later)

Engagement ingestion does not exist yet (Postiz/Buffer analytics are future work). This correction wires the seam only:

- `performance_evidence` field exists on every entry (B.2).
- Define the amendment path: when engagement data lands, the inward loop drafts a **module amendment proposal** — e.g. "Reels carrying process-demonstration affordances outperform carousels for the same subjects; update Reel evidence to tenant_data, propose status confirmation" — presented to the operator as a gated module update, identical in mechanics to any other module amendment. Status transitions (experimental → proven, proven → retired) ride the same path, per AMENDMENT-004.
- The outward loop (viral decomposition) feeds the same seam from the other side: decomposed winners in the domain propose new affordance language or new experimental entries.
- No auto-application of any of this. AI proposes, human gates.

### B.9 Out of scope

- Engagement metric ingestion itself (future milestone).
- Digest construction for Viral Patterns / Audience Insights / Story Frameworks (flagged follow-up; interim: inject whole, no slicing).
- Any change to Gate 1 mechanics.

---

## Implementation checklist (suggested order)

1. **A.1/A.2** Remove all `[:2000]` / `[:1500]` module slices in `src/app.py`. Interim: inject non-guide modules whole.
2. **B.3** ModuleStore: persist format-guide JSON alongside markdown.
3. **B.2** Migrate StackPenni guide to v1.1 (affordances, evidence, variant_type, aspect_ratio; table removed) — gate with operator before use.
4. **B.4/B.5** `get_format_distribution` in pipeline; digest builder; `generate_v2.md` with `{format_digest}` + `{format_distribution}` + portfolio-balance rule; update all four call sites.
5. **B.7** Capture validation with single retry + `needs_repair` state.
6. **B.6** `fan_out_v3.md` with `{format_entry}` injection; schema tweak for experimental format_spec.
7. **B.2** `format_guide/analyze_v3.md` (no decision table; affordances + evidence priors) for future onboarding runs.
8. **CONTEXT.md**: add the "prompts carry procedures; modules carry knowledge" principle.
9. Tests: truncation regression (assert full digest reaches prompt), capture-enforcement path, fan-out of an experimental format, distribution query.
