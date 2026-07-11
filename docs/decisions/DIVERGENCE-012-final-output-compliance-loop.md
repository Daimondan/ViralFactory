# DIVERGENCE-012 — Final-output compliance loop: approved script → plan → rendered media

**Date:** 2026-07-10  
**Filed by:** Builder, from operator direction  
**Status:** APPROVED — ratified via AMENDMENT-008, Charter v3.5 (2026-07-11)  
**Type:** STRUCTURE / LOGIC  

## Operator direction

The system must not merely report that a rendered asset is technically valid or that it matches its own edit plan. Before an operator sees the asset, it must judge the **final output against the approved script** and run an automated remediation loop, capped at **three rounds**, for problems it can correct safely.

The goal is general, not a biscuit-tin-specific patch:

> Every required element of the approved piece must be represented in the edit plan and final output, or the system must show exactly what cannot be satisfied and why.

## Failure that exposed the gap

A reel had an approved script containing substantially more VO than its 18-second edit plan could contain. Gemini TTS generated approximately 92 seconds of VO. The renderer correctly executed the 18-second plan and trimmed audio to the rendered duration.

The existing checks failed to stop this because:

1. Mechanical review compared final duration to the plan duration, and both were about 18 seconds.
2. Visual review sampled only frames inside the existing 18-second file.
3. Audio review checked stream/silence/transcription behavior, not whether all approved VO/script beats were represented.
4. Content alignment received the script and plan but had no structured completeness contract or required evidence mapping. It could treat the plan as authoritative even when the plan omitted most of the approved content.
5. The recent `VO:` marker check is an emergency narrow guard only. Deciding whether content requires VO or whether a plan faithfully represents a script is an LLM judgment, not a Python keyword heuristic.

## Conflict with current approved design

This proposal extends two currently approved rules:

- **AMENDMENT-007 / T9.5** already establishes a Writer-side AI review and revision loop with a hard three-round cap before Gate 2.
- **CORRECTION-final-output-review-and-audio-fix-v1.0** defines the Assembly-side review as advisory and explicitly says it does not auto-rerender.

An automatic final-output remediation loop changes the latter rule. It also must preserve AMENDMENT-007's boundary: the Assembler is media-only and must not silently rewrite human-approved script text after Gate 2.

Architect ruling is required before implementation.

**RULING: APPROVED 2026-07-11 via AMENDMENT-008 (`docs/decisions/AMENDMENT-008-final-output-compliance-loop.md`).** Three conditions: (1) Assembler text-boundary firewall — remediation loop must never modify `platform_content`, enforced by SHA-256 hash lock at loop entry; (2) config-driven cost guard — `max_remediation_cost_usd` in `models.yaml`, absent = review-only no auto-fix; (3) operator visibility — full remediation history (rounds, changes, verdict, provenance) shown in Assets UI. See AMENDMENT-008 for full conditions and implementation order.

## Proposed architecture

### 1. LLM-authored compliance contract at script → plan time

The plan-generation LLM receives the approved platform content and produces, alongside the edit plan, a structured **compliance contract**. This is a prompt + JSON-schema output, not judgment in Python.

For each required narrative beat, the contract includes:

```json
{
  "beat_id": "b1",
  "source_excerpt": "Your grandmother kept cash in a biscuit tin under the bed.",
  "requirement_type": "spoken_vo | on_screen_text | visual | cta | factual_claim",
  "required": true,
  "planned_segment_ids": ["s1"],
  "planned_time_range": {"start_s": 0, "end_s": 4},
  "verification_method": "audio_transcript | vision | caption_detection | combined"
}
```

The LLM also returns:

- whether spoken VO is required;
- the full intended VO transcript/order;
- required captions and CTA;
- an LLM judgment of whether the proposed pacing and duration can faithfully contain the approved piece;
- a `plan_verdict`: `compliant | revise_plan | needs_operator_decision`;
- specific remediation instructions when it is not compliant.

The schema validator mechanically requires every required beat to have a verification method and planned representation. It does **not** infer meaning with keyword matching.

### 2. Mechanical feasibility checks after TTS, before render

After TTS produces a real VO take, deterministic code measures facts:

- actual VO duration;
- planned timeline duration;
- final output duration when rendered;
- whether every contract beat has a plan mapping.

It does not decide whether the content is important. It proves whether the approved LLM plan is physically feasible.

Example: a 92-second generated VO and an 18-second locked timeline is an objective impossibility. The pre-render result is `needs_operator_decision`, with evidence, rather than silently truncating 74 seconds of approved dialogue.

### 3. Final-output LLM compliance review

After each render, a reviewer LLM receives:

- the full approved script/platform content;
- the compliance contract;
- the exact edit plan and final timeline;
- final-file duration and stream facts;
- the generated VO transcript/duration and rendered-audio transcript/timestamps where available;
- extracted final keyframes;
- visual/audio/mechanical findings from the existing review layer.

It returns a schema-validated verdict:

```json
{
  "verdict": "compliant | revise_plan | regenerate_media | rerender | needs_operator_decision",
  "coverage": [
    {
      "beat_id": "b1",
      "status": "verified | missing | partial | unverifiable",
      "evidence": "Rendered transcript covers this line at 0:00–0:04",
      "recommended_action": "..."
    }
  ],
  "issues": [],
  "safe_remediation_scope": "plan | media | render | none",
  "summary": "..."
}
```

`compliant` is impossible unless every contract beat is `verified` or the LLM explicitly documents an approved-equivalent representation.

### 4. Bounded automatic remediation loop — maximum three rounds

The Assembler gets the same QA pattern already approved for the Writer:

```
render
  ↓
LLM final-output compliance review
  ├── compliant → asset_ready for operator review
  ├── safely remediable → revise plan/media/render → rerender → re-review
  └── requires approved-script or treatment change → needs_operator_decision
```

Rules:

1. **Hard cap: three total render/review rounds.** On round three without compliance, stop and surface the complete review history.
2. **Safe automatic changes are limited to Assembler scope:** edit-plan timing/segment selection, generation prompts, replacement media, captions, audio mixing, and renderer mechanics.
3. **The loop must never silently shorten, delete, paraphrase, or invent approved script/VO text.** If the approved content cannot fit the locked format/timeline, it becomes `needs_operator_decision` with the exact mismatch and options (for example: approve a longer format, revise the approved script at Gate 2, or split into a series).
4. **No auto-publish.** The compliance loop happens before Gate 3 and never replaces human approval.
5. **No automatic cost explosion.** Round count, eligible remediation scope, and provider/model choices are config-driven. Each generated media action remains attributable to the original asset and review round.
6. **Every LLM call and artifact is logged.** Contract, each reviewer judgment, each plan/media revision, output hashes, and final non-convergence result are append-only provenance records.

## Required changes if approved

1. Retire the Python keyword-based `VO:` / `Narrator:` content judgment as the primary review decision. It may remain only as mechanical extraction input if the LLM contract requires it; it cannot determine compliance.
2. Create versioned prompts and JSON schemas for:
   - script-to-plan compliance contract;
   - final-output compliance review;
   - bounded assembler remediation instruction.
3. Extend the edit-plan record to persist the contract, its source approved-draft version/hash, and review-round history.
4. Extend the asset-review state model to record `reviewing`, `remediating`, `compliant`, `non_convergent`, and `needs_operator_decision` without treating any of those as publication approval.
5. Make the Assets UI show plain-language coverage: what was verified, what is missing, which round ran, what changed, and why the loop stopped.
6. Add pre-render VO/timeline feasibility checks and post-render transcript/coverage verification.

## Acceptance criteria

1. **Real failure regression:** A script whose generated VO is approximately 92 seconds and whose plan is 18 seconds is stopped before final acceptance. It must not receive `compliant` or `ready_for_operator`; it must identify the duration/content mismatch and require an operator decision unless a compliant plan can be generated without changing approved text.
2. **Coverage proof:** A final video cannot be marked compliant unless every required compliance-contract beat has explicit reviewer evidence.
3. **Generic content:** The test corpus includes VO-heavy reels, caption-only reels, silent visual pieces, carousels, and image posts; no tenant/topic/marker strings in generic code determine the result.
4. **Three-round cap:** A remediable visual/audio failure produces at most three render/review rounds; a non-convergent asset stops with the full provenance history visible to the operator.
5. **Approval integrity:** The system never changes approved script text without returning it to the human-authority path. It never publishes automatically.
6. **Real output verification:** Tests plus at least one real rendered asset validate video duration, VO duration, multi-timestamp audio, transcript/coverage evidence, and the operator-facing review panel.

## External workflow audit — reusable patterns and rejected patterns

The supplied n8n short-form workflow has several useful production-mechanics patterns. They should inform this proposal, not be copied wholesale.

### Adopt

1. **Timed script before TTS.** Its script prompt constrains narration to the supplied scene budget. ViralFactory should improve this with the LLM compliance contract and actual post-TTS duration measurement, rather than trusting a prompt instruction.
2. **Explicit production manifest.** It carries an ordered set of captions, images, clips, audio, and template slots. ViralFactory should persist a generic, schema-validated asset manifest so segment/beat/media associations cannot be lost or combined by accident.
3. **Provider task lifecycle.** Submit → poll status → retry failure is the right mechanical shape for asynchronous image, video, and render providers. ViralFactory should use jobs and explicit task states, bounded retries, and status polling rather than fixed sleep-only assumptions.
4. **Template-driven assembly.** Passing named media, text, and audio fields into a rendering template makes assembly deterministic once the LLM-approved plan exists. ViralFactory's FFmpeg plan is the equivalent and should retain named segment/track mappings.
5. **Cost and artifact telemetry.** Capturing model, token use, provider task IDs, media URLs, duration, and output metadata is useful provenance and cost control.

### Do not adopt

1. **Blind positional merging.** Combining captions, videos, and audio "by position" can silently mispair assets. ViralFactory must join by persistent beat/segment IDs and validate one-to-one coverage.
2. **Fixed scene count and timing as a universal rule.** Five scenes / five-second clips is a template choice, not a generic content decision. Duration, segment count, and media choice must come from the LLM plan plus configured format constraints.
3. **Fixed waits as completion proof.** Waiting three or ten minutes then assuming completion is unreliable. Poll provider state until a bounded deadline, record failures, and surface an honest state.
4. **Prompt-only duration compliance.** Asking an LLM to write "about 15 seconds" is not verification. Measure generated VO and final media, then compare them to the approved contract.
5. **Automatic publishing.** Its direct upload-to-social flow conflicts with ViralFactory's hard per-piece human approval rule. Final-output compliance may automate bounded remediation, but it never publishes.
6. **Business/model/provider constants embedded in workflow code.** Provider keys, hardcoded voices, audience tone, scene count, and model identifiers must remain tenant/config/prompt data, never generic logic.

### Net lesson

The reference workflow gets the **assembly mechanics** mostly right: create a manifest, run asynchronous provider jobs, assemble known slots, and record costs. It does not prove that the final piece faithfully contains the approved script. The proposed compliance contract and final LLM review supply that missing control layer.

## Builder recommendation

Approve this as an **Assembler-side counterpart to AMENDMENT-007 §3**: an LLM-driven, contract-based final-output compliance loop, bounded to three rounds and constrained so it can repair media/plan/render defects but cannot silently rewrite human-approved content.
