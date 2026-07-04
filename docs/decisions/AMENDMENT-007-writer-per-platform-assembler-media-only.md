# AMENDMENT-007 — Writer produces per-platform content; Assembler is media-only; AI review loop before Gate 2

**Filed:** 2026-07-04
**Filed by:** Architect
**Status:** APPROVED — incorporates DIVERGENCE-010 into Charter v3.4
**Supersedes:** The Writer/Assembler boundary as defined in AMENDMENT-006 (refines the split, does not remove it)
**Ratifies:** DIVERGENCE-010 (originally filed as DIVERGENCE-009, renamed due to numbering collision with the webhook divergence)

## What this amends

DIVERGENCE-010 raised five connected design issues with the Writer/Assembler pipeline. The operator's mental model is simpler and more coherent than the current design. After reviewing the code (`produce_chain.py`, `app.py`, `prompts/draft/generate_v2.md`, `prompts/assets/fan_out_v2.md`, `prompts/assets/structure_v1.md`), the schemas (`DRAFT_SCHEMA`, `IDEA_CARD_SCHEMA`), and the Format Guide module, the architect approves all five changes with the design specifications below.

## Architect's findings before ruling

1. **The `_determine_variant_type` keyword heuristic is a confirmed charter violation.** `produce_chain.py:407-419` and `app.py:3904` both use `if "thread" in format_lower` / `if "carousel" in format_lower` — this is exactly the kind of keyword matching that the charter's Business Rule #2 prohibits. This was already flagged in prior reviews. It must be fixed regardless of the structural changes.

2. **The `_resolve_format_platforms` regex parser is also judgment-in-code.** `produce_chain.py:373-404` and `app.py:3878-3901` both parse Format Guide entry text with regex (`re.search(r"platforms?\s*[:\-]\s*(.+)")`) to extract platform names. This is fragile and is a judgment task done by code. The treatment already carries the format name; the Format Guide entry carries the platforms field. The platform set should be structured data, not regex-parsed text.

3. **The builder's finding on Source Bank loading is correct.** The draft prompt (`generate_v2.md`) loads 7 modules (voice_profile, tells_checklist, story_frameworks, audience_insights, viral_patterns, visual_style, format_guide) plus grounding sources as a separate `{grounding_sources}` variable. The Source Bank is NOT loaded as a module into the draft path. No redundancy exists. No change needed (DIVERGENCE-010 issue #3).

4. **The fan-out and structure prompts do LLM text generation in the Assembler.** `fan_out_v2.md` adapts the master draft per platform (full LLM call). `structure_v1.md` splits text into segments (structure-only LLM call). Both run in the Assembler stage. If the Writer produces per-platform text, both become unnecessary.

5. **The self-audit is passive.** The charter says the drafter "self-audits against the Tells Checklist and presents suspect lines, so the person judges flagged items." The current implementation flags lines and shows them to the human at Gate 2 — but does not auto-fix them or run a cross-check before the human sees the draft. The operator wants active remediation + a second-AI alignment check before Gate 2.

## Amendment 1: Writer produces complete per-platform content

### What changes

The Writer's output schema changes from a single `draft_text` to per-platform content. The Writer takes the approved idea + treatment (which already specifies the format and platforms) and fully writes complete content for every platform the treatment specifies — in one pass, in the person's voice, self-audited.

### New DRAFT_SCHEMA

The `draft_text` field is replaced by a `platform_content` array. Each entry is the complete, platform-native content for one platform:

```json
{
  "platform_content": [
    {
      "platform": "x",
      "variant_type": "thread",
      "content": "full text summary of the variant",
      "posts": ["tweet 1", "tweet 2", "..."],
      "image_prompts": ["prompt per post/slide, or 'none' for text-only"]
    },
    {
      "platform": "instagram",
      "variant_type": "carousel",
      "content": "summary line",
      "posts": ["slide 1 text", "slide 2 text", "..."],
      "image_prompts": ["prompt per slide"]
    }
  ],
  "visual_direction": {
    "image_prompts": ["generation-ready prompts (cross-platform master set)"],
    "reference_notes": ["visual references"],
    "shot_format_choices": ["shot/format choices per the Visual Style Guide"]
  },
  "self_audit_flags": [
    {"line": "...", "rule": "...", "suggestion": "...", "status": "active|applied|dismissed"}
  ]
}
```

### What the Writer receives

The Writer's prompt (`generate_v2.md` → v3) receives:
- The approved idea + hook options
- The treatment (format, scope, platforms — all locked from Gate 1)
- The Format Guide entry for the specified format (structure skeleton, platform rules)
- Grounding sources (full content of cited sources)
- All 7 modules (voice, tells, story, audience, viral, visual, format)
- Capture material (if any)
- Previous draft + revision feedback (if revising)

The Writer produces ALL platform variants in one LLM call. The format and platform set come from the locked treatment — the Writer does not decide them.

### What this eliminates

- The Assembler's `fan_out_v2.md` LLM call (text is already per-platform)
- The Assembler's `structure_v1.md` LLM call (posts/slides are already structured)
- The `_determine_variant_type` keyword heuristic (variant_type comes from the Format Guide / treatment, not keyword matching)
- The `_resolve_format_platforms` regex parser (platforms come from the treatment, not regex-parsed Format Guide text)

### Migration concern: one large LLM call vs several small ones

Producing all platform variants in one call increases the output size. The drafter backend must handle this. If the output exceeds the model's context/output limits, the builder may split the Writer into per-platform calls — but this is an implementation detail, not a design decision. The design is: the Writer produces all text, the Assembler produces no text. Whether that's one call or N calls is the builder's call, logged in provenance either way.

## Amendment 2: Assembler is media-only

### What changes

The Assembler receives the approved, fully-written per-platform content from the Writer and:
1. Takes the visual direction (image prompts, shot direction) from the approved draft
2. Generates images/video per platform (using the media adapter)
3. Stitches media + text into the final piece (assembly/render)

The Assembler makes **zero LLM text calls**. It is a mechanical assembly stage. `fan_out_v2.md` and `structure_v1.md` are retired from the Assembler path.

### What the Assembler reads from the locked draft

- `platform_content` array (the per-platform text — already structured into posts/slides)
- `visual_direction` (image prompts, shot direction)
- The treatment's format + platforms (locked, not re-derived)

### What the Assembler does NOT do

- Does NOT call any LLM for text generation or adaptation
- Does NOT re-derive format or platforms (locked from treatment)
- Does NOT determine variant type (comes from the draft's `platform_content[].variant_type`)
- Does NOT call `_resolve_format_platforms` or `_determine_variant_type`

### Card state transitions (unchanged from AMENDMENT-006)

- Writer: `approved → writing → draft_ready | writer_failed`
- Assembler: `shipped → assembling → asset_ready | assembly_failed`

## Amendment 3: AI review loop before Gate 2

### What changes

A new automated QA stage runs between the Writer producing the draft and the human seeing it at Gate 2. The loop:

1. Writer produces draft + self_audit_flags
2. **Self-audit fix:** flagged items are auto-fixed — the Writer revises its own draft to resolve each flagged line. The fix is logged (original line, fix applied, which tell rule).
3. **Second-AI alignment check:** a separate LLM call (different prompt, same or different profile — config-driven) reviews the draft against the approved idea. Checks: does the draft align with what was approved? Does it drift from the idea? Does it introduce unapproved claims? Is it logically coherent?
4. If the alignment check finds issues, the issues are sent back to the Writer for revision.
5. Loop repeats, **max 3 rounds**.
6. Only after the loop completes (or hits the 3-round cap) does the draft reach `draft_ready` for Gate 2.

### Design specifications

- **Self-audit fix is not silent.** The human sees the original flagged lines AND the fixes applied. Transparency: the operator can see what the AI changed before they saw it. This is provenance, not a black box.
- **The second-AI alignment check is a new prompt.** The builder creates `prompts/draft/alignment_check_v1.md` with a JSON schema for its output: `{aligned: bool, issues: [{type, description, severity}], recommendations: [str]}`.
- **Max 3 rounds is a hard cap.** If the loop doesn't converge in 3 rounds, the draft goes to the human with a flag: "AI review did not converge — please review carefully." The human is the final gate, always.
- **The loop is NOT a gate.** It is automated QA. The human does not interact with it. It runs between `writing` and `draft_ready`. The card state during the loop: `writing → reviewing → draft_ready | writer_failed`.
- **Provenance:** every round of the loop is logged — self-audit fix, alignment check, revision. The operator can see the draft's QA history.
- **Profile:** the alignment check runs under the `drafter` profile (or a new `reviewer` profile if the builder proposes one via the gate — but for now, drafter is sufficient). The key is that it's a different prompt, not a different model.

### What this does NOT change

- **Gate 2 is still the human pass.** The AI review loop is before the human, not instead of the human. The human still sees the draft, reacts with chips + text, makes direct edits, ships or kills.
- **Self-audit flags still reach the human.** The flags + fixes are shown at Gate 2 so the operator can see what the AI caught and what it changed.
- **The charter's self-audit model is refined, not removed.** The charter says the drafter "self-audits against the Tells Checklist and presents suspect lines, so the person judges flagged items." This amendment adds: the drafter also **fixes** flagged items before the human sees them, and a second AI checks alignment. The human still judges — but they judge a draft that has already been through one round of AI remediation.

## Amendment 4: Format and platforms are locked from the treatment

### What changes

The format name and platform set are approved at Gate 1 in the treatment block. They travel with the card → Writer → Assembler as locked values. No code in the pipeline re-derives them.

### What this means in practice

- The Writer reads `treatment.format.format_name` and the Format Guide entry's `platforms` field to know which platforms to write for.
- The Assembler reads the same locked values to know which platforms to produce media for.
- `_resolve_format_platforms` (regex parser) is **removed**. The platforms come from the Format Guide entry's structured metadata, not from regex-parsed text.
- `_determine_variant_type` (keyword heuristic) is **removed**. The variant type comes from the Format Guide entry's structural metadata or the treatment, not from keyword matching.

### Format Guide entry structure (what the builder should rely on)

The Format Guide module already has structured entries. Each format entry has:
- `- **Platforms:** X` (or `X, Instagram`)
- `- **Status:** proven | experimental`
- A skeleton with structural information

The builder should add a `variant_type` field to the Format Guide entry schema (or derive it from the format name via the Format Guide's own metadata, not keyword heuristics in code). This is a module change, gated through the normal module update path — but the schema enrichment can proceed as a charter compliance fix (it's fixing a Business Rule #2 violation, not a design change).

## Amendment 5: Source Bank not loaded into draft (no change — confirmed)

The builder's finding is correct: the draft prompt does NOT load the Source Bank as a module. It loads grounding sources (full content of only cited sources) as a separate `{grounding_sources}` variable. The Source Bank feeds ideation (as a digest), not drafting. No redundancy exists. No change needed.

## What this does NOT change

- **Four content gates** — Ideas (rigorous), Draft (deep human pass), Assets (quick per-platform), Publish (go/hold). All remain.
- **Per-piece approval before publish** — hard rule, unchanged.
- **No auto-publish** — hard rule, unchanged.
- **AI Profiles** — Researcher, Drafter, Analyst. Unchanged. The Writer and Assembler both use the Drafter profile. The AI review loop uses the Drafter profile (or a future reviewer profile via config).
- **The treatment block** — still approved at Gate 1, still carries format + scope + capture + reuse + rationale. The platforms are derived from the Format Guide entry for the treatment's format.
- **Provenance** — every LLM call still logged: input hash, prompt file + version, model, raw output, validated output, verdict, profile.
- **Determinism** — temperature 0 for processing, content-hash caching.

## Implementation order (for BUILD_PLAN)

1. **Fix the charter violation immediately** — remove `_determine_variant_type` keyword heuristic and `_resolve_format_platforms` regex parser. The variant type and platform set come from the treatment + Format Guide entry metadata. This is a charter compliance fix, not a design change.
2. **Enrich the Format Guide schema** — add `variant_type` to each format entry (or a mapping from format name → variant type in the Format Guide's metadata). This is a module schema change, gated normally.
3. **Restructure the Writer** — change DRAFT_SCHEMA to `platform_content` array, update `generate_v2.md` → v3, update `produce_chain._step_draft` and the `draft_generate` route.
4. **Restructure the Assembler** — remove `fan_out_v2.md` and `structure_v1.md` calls from `_step_fanout` and `assets_fan_out`. The Assembler reads `platform_content` from the draft and produces media only.
5. **Add the AI review loop** — new `alignment_check_v1.md` prompt, new schema, loop logic in `produce_chain.run_writer_chain` (between draft generation and `draft_ready`).
6. **Update all tests** — the draft schema change, the assembler change, and the review loop all need test coverage.

## Charter text to update

In CHARTER-v3.4, the core loop section:

- **Draft stage:** "AI, all modules loaded, self-audited against the Tells Checklist" → "AI, all modules loaded, self-audited against the Tells Checklist, auto-fixes flagged items, and passes a second-AI alignment check (max 3 rounds) before the human sees it at Gate 2."
- **Draft output:** "full text in voice + light visual direction" → "complete per-platform text in voice + light visual direction. The Writer produces all platform variants in one pass; the Assembler does no text generation."
- **Assets stage:** "the piece fanned out into per-platform variants" → "media generated per the visual direction and stitched with the approved per-platform text. The Assembler does no text generation — it receives finished text from the Writer."
- **Design rules:** add "The format and platform set are locked from the treatment at Gate 1. No code in the pipeline re-derives them."

In CONTEXT.md:

- Update the Core Loop diagram to show: Writer produces per-platform content → AI review loop → Gate 2 → Assembler (media-only)
- Update the DRAFT_SCHEMA description
- Update the Assembler description (media-only, no LLM text calls)
- Add the AI review loop description
- Note the retirement of fan_out_v2.md and structure_v1.md from the Assembler path