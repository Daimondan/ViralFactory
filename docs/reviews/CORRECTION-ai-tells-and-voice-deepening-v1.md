# CORRECTION — AI tells, voice-first ideation, and cognitive voice deepening v1

**Date:** 2026-07-04  
**Filed by:** Architect  
**Status:** APPLIED in this pass; builder must preserve these constraints in future prompt/schema work  
**Applies to:** AMENDMENT-007 / T9.5 AI review loop, Voice Profile playbook, idea generation, draft generation

---

## Why this correction exists

The operator correctly challenged the prior design: avoiding AI writing cannot be a post-processing “humanizer” that swaps a few words after the text is already AI-shaped. The system must make the AI **think human before it writes human**.

The relevant external reference is Wikipedia’s **Signs of AI writing** page and its linked one-level-down references, especially the AI-cleanup guidance and the Tropes.fyi AI Writing Pattern Directory. The most operator-salient tell discussed was negative parallelism — “it’s not X, it’s Y” — but the system needs a broader catalog with confidence levels so the AI review loop can fix high-confidence tells automatically and leave context-dependent flags visible.

This correction keeps the charter rule intact:

> **Humanness is built in, not sprayed on. No bolt-on humanizer step, ever.**

---

## Review findings against builder work

### F1 — Voice Profile module is still effectively empty

**File:** `modules/stackpenni/voice-profile.md`  
**Finding:** The StackPenni Voice Profile still states that the corpus was not provided, so voice patterns cannot be extracted. The prompt/playbook can now extract better voice data, but tenant #1 still needs a real corpus or interview fallback + calibration.

**Charter impact:** Voice Profile is “the first module built and the last thing compromised.” Running the Writer with an empty Voice Profile keeps output generic.

**Correction:** Prompt/playbook now support cognitive patterns and AI-tell cross-reference. Operator still needs to complete voice onboarding with real materials or interview fallback.

---

### F2 — Idea generation was AI-shaped at conception

**Files:**
- `prompts/views.yaml`
- `prompts/ideas/generate_v1.md`

**Finding:** `ideas/generate_v1.md` previously loaded viral/audience/story/format modules but not the Voice Profile. Ideas were mechanically born from Source Bank × modules, then voice was applied only later in drafting. That is exactly the “write text then humanize it” trap.

**Correction applied:**
- Added `voice_profile` to `ideas/generate_v1.md` context in `prompts/views.yaml`.
- Bumped `prompts/ideas/generate_v1.md` to v1.4.
- Added a voice-first ideation instruction: ideas must be born in the person’s mental shape, with the person’s frame deciding which angles are worth generating.
- Added explicit idea-stage anti-AI guardrails: avoid negative parallelism, grandiose stakes, promotional tone, vague attributions, and other catalogued tells.

**Acceptance criteria:**
- Idea prompt has `{voice_profile}` before source/material crossing.
- Prompt says sources are material and voice is the frame.
- Prompt rejects AI-shaped idea descriptions before drafting begins.

---

### F3 — The AI tells checklist was too vague

**Files:**
- `prompts/shared/ai_tells_v1.md`
- `prompts/views.yaml`
- `prompts/draft/generate_v3.md`
- `src/context_assembly.py`
- `tests/test_module_context_assembly.py`

**Finding:** `generate_v3.md` said only: “Flag any lines that might be an AI tell.” This is a vibe check, not an enforceable checklist. It did not encode the Wikipedia/Tropes tell catalog or confidence levels.

**Correction applied:**
- Created `prompts/shared/ai_tells_v1.md`: canonical 53-tell catalog with `HIGH`, `MEDIUM`, `LOW` confidence levels.
- Added `ai_tells` to `prompts/views.yaml` for `draft/generate_v3.md`.
- Extended `context_assembly.py` to load raw shared prompt files referenced by views.yaml (`{file: shared/ai_tells_v1.md}`), with provenance labels.
- Added regression coverage in `tests/test_module_context_assembly.py`.
- Rewrote `generate_v3.md` self-audit into a concrete 6-category scan:
  1. word choice
  2. sentence structure
  3. paragraph rhythm
  4. tone
  5. formatting
  6. composition

**Design rule:** High-confidence tells are auto-fix candidates. Medium tells are context-dependent. Low tells are transparency-only.

---

### F4 — T9.5 self-audit fix was a no-op

**File:** `src/produce_chain.py`  
**Former behavior:** `_run_ai_review_loop()` marked every active self-audit flag as `applied` and recorded `fix = suggestion`, but never changed `platform_content`. The operator would still see the original AI-tell line while review history falsely claimed it had been fixed.

**Charter impact:** This violated AMENDMENT-007: “Writer revises its own draft to resolve each flagged line.” It also created a false-green QA state.

**Correction applied:**
- Added `_apply_self_audit_fixes()`.
- The method mechanically replaces the exact flagged line in `platform_content[].content` and `platform_content[].posts` only when the Writer provides concrete `fix_applied` text.
- A flag is marked `applied` only if the content actually changed.
- Flags without concrete fixes remain active for the alignment check/human.
- Added two regression tests in `tests/test_t9_5_ai_review_loop.py`.

**Acceptance criteria:**
- A flag with `fix_applied` changes real platform text.
- A flag without concrete revised text is not marked applied.
- Review history’s “fix” field contains the actual revised text, not merely the suggestion.

---

### F5 — Alignment check incorrectly ignored AI tells

**File:** `prompts/draft/alignment_check_v1.md`

**Finding:** The prompt said: “Do NOT flag AI tells — the self-audit already checked those.” That was wrong once the self-audit fix was a no-op, and still too weak after the fix. AMENDMENT-007’s second AI review loop should catch high-confidence tells that survived the first pass.

**Correction applied:**
- Bumped `alignment_check_v1.md` to v1.1.
- Added `ai_tell_survived` as an issue type.
- Added a second-pass scan for surviving HIGH-confidence AI tells:
  - high-confidence vocabulary tells
  - repeated negative parallelism
  - em dash overuse
  - signposted conclusions
  - false suspense
  - grandiose stakes
  - promotional tone
  - “despite challenges” formula

**Acceptance criteria:**
- Alignment check still focuses on drift, unapproved claims, logic, missing/added elements.
- It also reports surviving HIGH-confidence AI tells as `ai_tell_survived` with severity `medium`.
- It does not flood the operator with medium/low tells.

---

### F6 — AI-review revision stripped the modules and voice context

**File:** `src/produce_chain.py`

**Former behavior:** `_revise_draft_with_recommendations()` called `draft/generate_v3.md` but passed placeholder module values such as `(use same voice as previous draft)` and `(same as previous)`. This stripped the real Voice Profile, Tells Checklist, Story Frameworks, Audience Insights, Viral Patterns, Visual Style, and Format Guide from revision rounds.

**Correction applied:**
- Revision calls now assemble the same module context via `assemble_module_context("draft/generate_v3.md", ...)`.
- The Writer receives the real `voice_profile`, `tells_checklist`, `ai_tells`, and other module views during AI-review revisions.

**Acceptance criteria:**
- Revision passes use the same prompt context family as first draft generation.
- No placeholder module text is passed for voice/tells/story/audience/viral/visual/format context.

---

### F7 — Voice Profile playbook did not extract cognitive dimensions

**Files:**
- `playbooks/voice-profile-builder.md`
- `prompts/voice_profile/analyze_v2.md`

**Finding:** The voice playbook and analysis prompt extracted expression patterns — lexicon, rhythm, connectors, stance — but not cognitive patterns. That helps “write like the person” but not “think like the person.”

**Correction applied:**
- Voice analysis prompt bumped to v2.1.
- Playbook bumped to v1.1.
- Added cognitive dimensions:
  - mental models
  - obsessions
  - contrarian takes
  - story instincts
  - frame
- Added cross-reference against the AI tells catalog so user-specific tells and positive human patterns are extracted with evidence.

**Acceptance criteria:**
- Voice Profile output schema includes `cognitive_patterns`.
- Every cognitive pattern requires verbatim evidence.
- Ideas use the Voice Profile so cognitive patterns influence ideation.

---

## High-confidence tells policy

The operator approved the following policy:

1. Keep the broad catalog; do not overfit to one tell.
2. Every tell has a confidence level.
3. The Writer self-audit may flag more than the operator sees.
4. High-confidence tells are fixed automatically inside the AI review loop.
5. Medium/low-confidence tells are visible only when useful; they should not generate a noisy operator burden.
6. The alignment check acts as the second pass for high-confidence tells that survived the Writer’s self-audit.

---

## Verification

Commands run:

```bash
cd /home/daimon/ViralFactory && source .venv/bin/activate && python3 -m pytest tests/test_module_context_assembly.py tests/test_t9_5_ai_review_loop.py -q
# 43 passed
```

Full suite must pass before final commit.

---

## Remaining non-code requirement

StackPenni’s `modules/stackpenni/voice-profile.md` is still not a real voice profile because the corpus was not available when it was generated. The prompts and playbook are now correct, but tenant #1 must run voice onboarding with:

- real corpus uploads, or
- the interview fallback, followed by
- calibration gate.

Until then, the system can avoid generic AI tells better, but it still cannot fully sound and think like Daimon.
