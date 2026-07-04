# DIVERGENCE-010 — Writer produces complete per-platform content; Assembler assembles media only

Proposed by operator (Daimon) · Filed by builder · 2026-07-04 · Status: **APPROVED — ratified via AMENDMENT-007 (Charter v3.4)**

> **Numbering note:** Originally filed as DIVERGENCE-009, but that number was already taken by the webhook notification loop divergence. Renamed to DIVERGENCE-010 by the architect during review. The webhook DIVERGENCE-009 remains as-is.

## What the operator asked for

Five connected design changes to the Writer/Assembler boundary:

### 1. The treatment already decides format + platforms — Assembler should not re-decide them

The approved idea card's treatment block contains `format.format_name` and the Format Guide entry resolves which platforms that format maps to. The Assembler currently:
- Calls `_resolve_format_platforms()` — parses Format Guide entry text with regex to find platform names
- Calls `_determine_variant_type()` — uses keyword heuristics (`if "thread" in format_lower`) to decide variant type

**This is a charter violation** (Business Rule #2: "No judgment in code... Never keyword heuristics"). The format and platform set are already approved in the treatment. The Assembler should read them from the locked treatment, not re-derive them with keyword matching.

### 2. Writer produces complete per-platform text — one write fully develops the approved idea

Currently the Writer produces one master draft, and the Assembler does LLM fan-out calls (`fan_out_v2.md`, `structure_v1.md`) to adapt/split it per platform. The operator says: **one write should fully develop the approved idea into complete content for every platform the treatment specifies.** The Assembler should not need to do any text generation — it receives finished text and just produces media + assembles.

This means the Writer's output schema would change from one `draft_text` to per-platform content (e.g., `platform_content: [{platform: "x", variant_type: "thread", posts: [...], content: "..."}, ...]`).

### 3. Why pass the entire Source Bank as a module when grounding sources already cover it?

**Builder finding:** The draft prompt (`views.yaml` for `draft/generate_v2.md`) does NOT load the Source Bank as a module. It loads: voice_profile, tells_checklist, story_frameworks, audience_insights, viral_patterns, visual_style, format_guide. Grounding sources (full content of only cited sources) are passed separately as `{grounding_sources}`. The redundancy the operator is concerned about does not exist in the draft path — the draft already gets only cited sources. The Source Bank feeds ideation (as a digest of all active sources), not drafting. No change needed here.

### 4. AI review loop before human review (max 3 rounds)

Currently: Writer produces draft + self_audit_flags → draft goes straight to human (Gate 2).

The operator wants an automated QA loop BEFORE the human sees the draft:

1. Writer produces draft + self_audit_flags
2. Self-audit issues are **fixed** (Writer revises its own draft to resolve flagged items)
3. A **second AI** reviews the draft against the approved idea — checks alignment, logical sense, that the draft doesn't drift from what was approved
4. If issues found, revisions sent back to Writer
5. Loop repeats, **max 3 rounds**
6. Only THEN does the human see the draft at Gate 2

This is a new pipeline stage. The charter currently has no automated cross-check between Writer output and human review. AMENDMENT-003 says "AI, all modules loaded, self-audited against the Tells Checklist" — the self-audit exists but is passive (flags are shown to human, not auto-fixed). The operator wants active auto-fixing + a second-AI alignment check.

### 5. Assembler should only gather/make media and stitch — no text output

Currently the Assembler:
- Calls `fan_out_v2.md` (LLM adapts text per platform)
- Calls `structure_v1.md` (LLM splits text into segments)

If the Writer produces complete per-platform text (change #2), the Assembler needs **zero LLM text calls**. It should:
- Take the approved draft's visual direction (image prompts, shot direction)
- Generate images/video per platform
- Stitch media + text into the final piece

This makes the Assembler a mechanical assembly stage, not a creative writing stage. The fan-out and structure prompts would be retired or repurposed.

## What this conflicts with in the current charter/design

### AMENDMENT-006 — Writer/Assembler split

AMENDMENT-006 defines:
- Writer chain: draft generation (full text + visual direction) → stops at `draft_ready`
- Assembler chain: per-platform fan-out → visual generation → stops at `asset_ready`

Changes #2 and #5 restructure this boundary: the Writer produces per-platform content (not just one master draft), and the Assembler does media generation + assembly (not text fan-out). The fan-out step moves from Assembler to Writer.

### AMENDMENT-003 — Staged content pipeline

AMENDMENT-003 says "Draft = full text in voice + light visual direction. No rendered images at this stage." If the Writer now produces per-platform text, the draft schema changes. The "one master draft, fan-out at assets" model becomes "per-platform content at draft, media at assets."

### Business Rule #2 — No judgment in code

The `_determine_variant_type` keyword heuristic is already a violation. This is fixable regardless of the architect's decision on the structural changes.

### Charter self-audit model

The charter says the drafter "self-audits against the Tells Checklist and presents suspect lines, so the person judges flagged items." Change #4 adds an automated fix + second-AI review loop before the human. This changes the self-audit from passive flagging to active remediation.

## What the builder can do now (no charter change needed)

- **Fix the `_determine_variant_type` keyword heuristic** — replace with Format Guide / treatment lookup. This is a charter violation fix, not a design change. The variant type should come from the Format Guide entry's structural metadata or the treatment, not from keyword matching.

## What the builder cannot do without architect decision

- Restructure the Writer to produce per-platform text (changes the draft schema, the draft prompt, and the Writer/Assembler boundary)
- Remove LLM text calls from the Assembler (changes what the Assembler does per AMENDMENT-006)
- Add the AI review loop (new pipeline stage not in the charter)
- Retire the fan-out and structure prompts

## Builder's recommendation

The operator's mental model is coherent and simpler than the current design:

1. **Researcher** — finds ideas, assigns treatment (format + platforms)
2. **Writer** — takes the approved idea + treatment and fully writes complete content for every platform specified. Self-audits, fixes, gets cross-checked by a second AI, max 3 rounds. Human reviews at Gate 2.
3. **Assembler** — takes the approved, fully-written content and just generates media + assembles. No text decisions. Format and platforms are locked from the treatment.
4. **Analyst** — publishes, measures, learns

This eliminates:
- The fan-out LLM calls (text is already per-platform from the Writer)
- The format/platform re-derivation in the Assembler (locked from treatment)
- The keyword heuristic charter violation
- Unreviewed text reaching the human (AI review loop catches issues first)

I recommend the architect:
1. **Approve the keyword heuristic fix immediately** — it's a charter violation regardless
2. **Approve the Writer-produces-per-platform-content model** — the Writer's draft schema gains a `platform_content` array; the Assembler's fan-out LLM calls are removed
3. **Approve the AI review loop** — self-audit fix + second-AI alignment check, max 3 rounds, before Gate 2
4. **Approve the Assembler as media-only** — format/platform locked from treatment, no text LLM calls

This divergence does not block any current BUILD_PLAN task. The keyword heuristic fix can proceed as a charter violation fix.