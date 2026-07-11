# AMENDMENT-008 — Final-output compliance loop: approved script → plan → rendered media

**Filed:** 2026-07-11
**Filed by:** Architect (vf-architect)
**Status:** APPROVED — ratifies DIVERGENCE-012, incorporates into Charter v3.5
**Ratifies:** `docs/decisions/DIVERGENCE-012-final-output-compliance-loop.md`
**Supersedes:** The "advisory only — does not auto-re-render" rule in `docs/reviews/CORRECTION-final-output-review-and-audio-fix-v1.0.md` Part 2. The mechanical, visual, audio, and content-alignment checks (ASSET-REVIEW-1 through ASSET-REVIEW-6) remain in force; this amendment adds a compliance contract and bounded remediation loop on top of them.
**Related:** AMENDMENT-007 §3 (Writer-side AI review loop — this is the Assembler-side counterpart)

## What this amends

DIVERGENCE-012 identifies a real failure class: the system can produce a rendered asset that is technically valid and matches its own edit plan, but does not faithfully contain the approved script's content. The existing asset review layer (ASSET-REVIEW-1 through ASSET-REVIEW-6) catches mechanical, visual, and audio defects but was explicitly advisory — "does not auto-re-render on issues found. The operator decides."

The operator's direction: before an operator sees a rendered asset, the system must judge the final output against the approved script and run an automated remediation loop (capped at three rounds) for problems it can correct safely. This is the Assembler-side counterpart to the Writer's AI review loop (AMENDMENT-007 §3).

## Architect's findings before ruling

1. **The failure case is real and reproducible.** A reel with 92 seconds of generated VO and an 18-second edit plan was silently trimmed to 18 seconds, losing 74 seconds of approved dialogue. The existing checks passed because they compared the output to the plan (both 18s) and not to the approved script. This is not a hypothetical — it happened.

2. **The existing keyword-based VO detection is a confirmed charter violation.** `asset_review.py:686-705` uses keyword matching (`vo_markers`, `speech_markers`, `"audio:"` line detection) to decide whether the output "should have audio." This is judgment in code — exactly what the charter's design rule "Nothing hardcoded: judgment → playbooks/prompts" prohibits. DIVERGENCE-012 correctly identifies this and proposes replacing it with an LLM-authored compliance contract.

3. **The `_extract_vo_lines` regex in `vo_generator.py:84-92` is mechanical extraction, not judgment.** It pulls VO text from the script to feed to TTS. DIVERGENCE-012 correctly preserves this as a mechanical input and only retires the keyword pattern as a compliance *decision*. The line between extraction (mechanical) and compliance judgment (LLM) is the right line.

4. **The advisory-only rule was a deliberate first-step design, not a permanent principle.** The correction that established it (`CORRECTION-final-output-review-and-audio-fix-v1.0`) said the review layer "does not auto-re-render" and the operator "decides whether to re-render, fix, or kill." This was correct for the initial review layer — get the checks working, prove the pattern, keep the human in full control. DIVERGENCE-012 extends this to the next step: bounded auto-remediation with the human still as the final gate. This is the same pattern already approved for the Writer side (AMENDMENT-007 §3). The asymmetry — Writer auto-remediates, Assembler doesn't — was always temporary.

5. **The compliance contract architecture is charter-aligned.** LLM-authored contract at plan time → mechanical feasibility checks after TTS → LLM compliance review after render → bounded remediation. This moves judgment to prompts + schemas + validators, keeps mechanical checks deterministic, and preserves the human gate. It is exactly what the charter demands.

## Ruling: APPROVED with three conditions

### Condition 1 — Assembler text-boundary firewall

The remediation loop must never modify `platform_content` — the approved per-platform text from the Writer. "Generation prompts" in the safe-remediation scope means **media generation prompts** (image/video descriptions for the media adapter), never content text. "Captions" means caption rendering/styling (font, position, burn-in), never rewriting caption text. The approved `platform_content` hash is locked at loop entry. Any remediation action that would change approved text is rejected and escalated to `needs_operator_decision`.

**Rationale:** AMENDMENT-007 says "the Assembler does no text generation." The remediation loop must not become a backdoor for text editing. If the approved content cannot fit the format/timeline, the system must escalate — never silently shorten, delete, paraphrase, or invent approved script/VO text. This preserves the Writer/Assembler boundary.

**Implementation:** The builder must implement a mechanical guard: compute SHA-256 of the `platform_content` JSON at loop entry. Before each remediation action, verify the hash is unchanged. If a remediation instruction from the LLM would modify `platform_content`, reject it and set the verdict to `needs_operator_decision`.

### Condition 2 — Config-driven cost guard

Each remediation round may involve AI image/video regeneration, which costs real money. The loop must have a configurable per-asset cost cap in `models.yaml`:

```yaml
asset_review:
  max_remediation_cost_usd: 2.00  # cumulative cap per asset
  max_remediation_rounds: 3       # hard cap (already in divergence)
```

If cumulative remediation cost exceeds `max_remediation_cost_usd`, the loop stops with `needs_operator_decision` and the full cost summary visible to the operator. If `max_remediation_cost_usd` is absent, remediation is disabled (review-only, no auto-fix) — a safe default for new businesses.

**Rationale:** The charter says "add complexity only when real volume forces it" and "config-driven, not hardcoded." A cost explosion guard is not complexity — it is a safety rail. Without it, a 3-round loop that regenerates Veo video each round could spend $10+ on a single asset without the operator knowing.

### Condition 3 — Operator visibility during remediation

Even though the operator does not interact with the loop, they must be able to see what happened. The Assets UI must show:
- Which round ran (1, 2, or 3)
- What changed in each round (plan revision, media regeneration, re-render)
- Why the loop stopped: `compliant` / `non_convergent` (3-round cap) / `cost_cap` / `needs_operator_decision`
- The full provenance history (each LLM call, each artifact revision, each verdict)
- The compliance contract and per-beat coverage evidence

**Rationale:** The charter says "evidence beside every AI claim" and "every LLM step = provenance log." The remediation loop is a series of AI claims (the system claims the output is compliant; the system claims a specific fix is safe). Each claim must be visible. This matches the transparency already established for the Writer's review loop in AMENDMENT-007: "the human sees the original flagged lines AND the fixes applied."

## What this does NOT change

- **Gate 3 is still the human gate.** The compliance loop runs before Gate 3 and never replaces human approval. The operator still approves, fixes, or kills per platform.
- **No auto-publish.** The compliance loop never publishes. Hard rule, unchanged.
- **Per-piece approval before publish is absolute.** Unchanged.
- **The four content gates** — Ideas (rigorous), Draft (deep human pass), Assets (quick per-platform), Publish (go/hold). All remain.
- **The Writer/Assembler boundary** — the Writer produces all text, the Assembler produces media only. The remediation loop respects this (Condition 1).
- **The existing ASSET-REVIEW-1 through ASSET-REVIEW-6 checks** — these remain as the mechanical/visual/audio/alignment layers. The compliance contract and final-output compliance review build on top of them, not replace them.
- **The existing edit-plan prompt and schema** — these are extended (compliance contract added to plan output), not replaced.

## What this retires

1. **The keyword-based VO/content detection in `asset_review.py:686-705`** (`_output_should_have_audio`) is retired as a compliance *decision*. It may remain as a mechanical extraction input if the LLM contract requires it, but it cannot determine compliance verdicts. The compliance contract (LLM-authored, schema-validated) is the authoritative source for "what should be in the output."

2. **The advisory-only rule from CORRECTION-final-output-review-and-audio-fix-v1.0** is superseded. The asset review layer is no longer purely advisory — it can trigger bounded auto-remediation per the conditions above. The operator still sees the review summary, but the system attempts to fix safe-to-fix problems first.

## Architecture summary (for the builder)

```
Script approved (Gate 2 ship)
  ↓
Edit plan generation (LLM)
  ├── produces edit plan
  └── produces compliance contract (new):
      { beat_id, source_excerpt, requirement_type, required,
        planned_segment_ids, planned_time_range, verification_method }
  ↓
Plan + contract validated (mechanical schema check)
  ↓
TTS generates VO (if required)
  ↓
Pre-render feasibility checks (new, mechanical):
  - actual VO duration vs planned timeline duration
  - every contract beat has a plan mapping
  → infeasible → needs_operator_decision (no silent truncation)
  ↓
Render (FFmpeg)
  ↓
Existing asset review layer (ASSET-REVIEW-1 through 6):
  mechanical → visual → audio → alignment
  ↓
Final-output compliance review (new, LLM):
  receives: approved script, compliance contract, edit plan,
           final-file facts, VO transcript, keyframes, prior findings
  returns: { verdict, coverage[], issues[], safe_remediation_scope, summary }
  ↓
  ├── compliant → asset_ready for operator (Gate 3)
  ├── safely remediable (within scope + cost cap) → remediate → re-render → re-review (max 3 rounds)
  └── needs approved-script/treatment change → needs_operator_decision
  ↓
Round 3 without compliance → stop, surface full history → needs_operator_decision
```

## Charter text to update

In CHARTER-v3.5, the Assets stage (core loop §4):

**Before (v3.4):**
> **Assets** — for surviving drafts only: real images/video generated per the visual direction, media stitched with the approved per-platform text. **The Assembler does no text generation** — it receives finished per-platform text from the Writer and produces media + assembles. The format and platform set are locked from the treatment; the Assembler does not re-derive them.

**After (v3.5):**
> **Assets** — for surviving drafts only: real images/video generated per the visual direction, media stitched with the approved per-platform text. **The Assembler does no text generation** — it receives finished per-platform text from the Writer and produces media + assembles. The format and platform set are locked from the treatment; the Assembler does not re-derive them. A **compliance contract** (LLM-authored alongside the edit plan) defines every required narrative beat and its planned representation. After render, a **final-output compliance review** checks the rendered asset against the approved script and contract. **A bounded remediation loop (max 3 rounds, config-driven cost cap) automatically fixes safe-to-fix defects** (plan timing, media prompts, audio mixing, render mechanics) — but never modifies approved text. If the approved content cannot fit the format, the system escalates to `needs_operator_decision` rather than silently truncating. The operator sees the full remediation history: what changed, why the loop stopped, and per-beat coverage evidence. (AMENDMENT-008)

In the design rules section, add:

> - **A compliance contract and bounded final-output remediation loop (max 3 rounds, config-driven cost cap) runs on the Assembler side.** It can fix media/plan/render defects but never modifies approved `platform_content` text. If approved content cannot fit the format, it escalates to `needs_operator_decision`. The operator sees the full remediation history. (AMENDMENT-008)

## Implementation order (for BUILD_PLAN)

1. **Create versioned prompts and JSON schemas** for: (a) script-to-plan compliance contract, (b) final-output compliance review, (c) bounded assembler remediation instruction.
2. **Extend the edit-plan record** to persist the compliance contract, its source approved-draft version/hash, and review-round history.
3. **Add pre-render VO/timeline feasibility checks** — deterministic code that measures actual VO duration vs planned timeline duration and verifies every contract beat has a plan mapping. Infeasible → `needs_operator_decision`.
4. **Add the final-output LLM compliance review** — runs after the existing ASSET-REVIEW-1 through 6 layers. Receives approved script, contract, plan, final-file facts, prior findings. Returns schema-validated verdict + per-beat coverage.
5. **Implement the bounded remediation loop** — render → review → remediate → re-render, max 3 rounds. Condition 1 (text-boundary firewall): lock `platform_content` hash at entry, reject any remediation that would change it. Condition 2 (cost guard): config-driven `max_remediation_cost_usd` in `models.yaml`. Condition 3 (visibility): log every round, every change, every verdict to provenance.
6. **Extend the asset-review state model** to record `reviewing`, `remediating`, `compliant`, `non_convergent`, `needs_operator_decision` — none of which are publication approval.
7. **Update the Assets UI** to show plain-language coverage: what was verified, what is missing, which round ran, what changed, why the loop stopped.
8. **Retire the keyword-based `_output_should_have_audio`** as a compliance decision. It may remain as mechanical extraction input only.
9. **Tests:** real failure regression (92s VO + 18s plan must be stopped), coverage proof (no compliant without every beat verified), generic content (VO-heavy reels, caption-only, silent, carousels, images — no tenant strings), three-round cap, cost cap, text-boundary firewall, approval integrity (never changes approved text, never publishes automatically), real output verification.

## Acceptance criteria (from DIVERGENCE-012, unchanged)

1. **Real failure regression:** A script whose generated VO is approximately 92 seconds and whose plan is 18 seconds is stopped before final acceptance. It must not receive `compliant` or `ready_for_operator`; it must identify the duration/content mismatch and require an operator decision unless a compliant plan can be generated without changing approved text.
2. **Coverage proof:** A final video cannot be marked compliant unless every required compliance-contract beat has explicit reviewer evidence.
3. **Generic content:** The test corpus includes VO-heavy reels, caption-only reels, silent visual pieces, carousels, and image posts; no tenant/topic/marker strings in generic code determine the result.
4. **Three-round cap:** A remediable visual/audio failure produces at most three render/review rounds; a non-convergent asset stops with the full provenance history visible to the operator.
5. **Approval integrity:** The system never changes approved script text without returning it to the human-authority path. It never publishes automatically.
6. **Real output verification:** Tests plus at least one real rendered asset validate video duration, VO duration, multi-timestamp audio, transcript/coverage evidence, and the operator-facing review panel.

## External workflow audit note

DIVERGENCE-012 includes a detailed audit of a reference n8n short-form workflow. The architect reviewed the "Adopt" and "Do not adopt" lists and confirms they are charter-aligned. Specifically:

- **Adopt:** timed script before TTS (with actual post-TTS measurement, not prompt-only), explicit production manifest (schema-validated, beat/segment IDs not positional merging), provider task lifecycle (poll not fixed waits), template-driven assembly, cost/artifact telemetry.
- **Do not adopt:** blind positional merging (join by persistent IDs), fixed scene count/timing as universal rule (LLM plan + config constraints), fixed waits as completion proof (poll until bounded deadline), prompt-only duration compliance (measure, don't ask), automatic publishing (hard rule violation), business/model/provider constants in workflow code (config-driven).

These patterns should inform the builder's implementation of the compliance contract and remediation loop, not be copied wholesale.