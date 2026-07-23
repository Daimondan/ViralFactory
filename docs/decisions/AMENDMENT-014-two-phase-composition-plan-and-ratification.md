# AMENDMENT-014 — Two-phase assembly: composition plan, per-element previews, and ratification before render

**Status:** RATIFIED
**Date:** 2026-07-23
**Ratifies:** DIVERGENCE-020
**Supersedes:** None (extends AMENDMENT-013)
**Charter effect:** v3.9 → v3.10
**Prior amendments in force:** All through AMENDMENT-013 remain in force. AMENDMENT-014 adds a composition ratification sub-gate between manifest freeze and render. It does not weaken component approval, manifest freeze, or Gate 3.

## Binding flow

```
Component Workbench (AMENDMENT-013)
  → manifest freeze (exact ingredient hashes locked)
    → CompositionPlan generation (structured per-element spec)
      → per-element previews (text/font/audio/visual/graphics/timing)
        → COMPOSITION RATIFICATION SUB-GATE (operator approves the plan)
          → RendererSpec v1 compilation (from ratified CompositionPlan)
            → provider adapter submission (Shotstack or configured fallback)
              → download / hash / probe / verify
                → GATE 3 (exact final artifact approval)
```

## What the CompositionPlan contains

The CompositionPlan is a structured, provider-neutral specification of every element in the final video. It is generated mechanically from the frozen manifest, the approved Writer contract, visual events, audio intents, and the edit plan. It contains:

### Text elements
- Every on-screen text role: hook, caption, emphasis words, lower-third, CTA, proof overlays, source citations.
- Exact wording per role (from the approved Writer contract — never re-generated).
- Font file hash, font family, weight, size, color, background/pill style, shadow/outline.
- Position on canvas (anchor + coordinates).
- Timing: in-point, out-point, and word-level timing if declared.
- Emphasis marks: which words are bolded/colored/scaled, and how.

### Audio elements
- VO track: source hash, trim in/out, gain curve, ducking points.
- Music track: source hash, start/stop, gain curve, ducking under VO, fade in/out.
- SFX list: each SFX with source hash, trigger timestamp, gain, and duration.
- Mix specification: overall loudness target (LUFS), true peak limit, stereo/surround.

### Visual elements
- Each video clip/still: source hash, trim in/out, crop/focal point, position on canvas, scale, aspect handling (contain/cover/fill).
- Motion: zoom/pan keyframes, easing, start/end values.
- Background: canvas color/image, safe zones, platform framing guides.

### Graphics elements
- Charts, graphs, emojis, overlays, lower-third graphics, watermark/logo.
- Each with: type, source/config hash, position, scale, timing in/out, animation type/duration/easing.

### Transitions
- Every transition between segments: type (cut/crossfade/wipe/slide/zoom), duration, easing.
- The exact beat boundary or timestamp each transition serves.

### Canvas
- Resolution, aspect ratio, frame rate, background, safe zones, platform-specific framing guides.

## Per-element previews

Previews are **low-cost**, generated locally, and sufficient for ratification — they are not full renders:

| Element type | Preview |
|---|---|
| Text role | Rendered specimen in the declared font, size, color, and position on a blank canvas frame |
| Audio mix | Waveform display with VO/music/SFX lanes, gain curves, ducking points, and LUFS target marker |
| Visual clip | Thumbnail showing the crop/framing/scale on the canvas, with safe-zone overlay |
| Graphics overlay | Static frame of the overlay on a representative background |
| Transition | Annotated timing diagram showing transition type/duration at each boundary |
| Full timeline | Horizontal timeline diagram showing all elements on their lanes with in/out points |

Previews are generated from the CompositionPlan using local FFmpeg/PIL/matplotlib — no provider API calls. They are evidence for ratification, not final artifacts.

## Composition ratification sub-gate

**RATIFICATION (between manifest freeze and render, per platform):** the operator reviews the per-element previews and the full timeline diagram, then ratifies or rejects the CompositionPlan. Ratification binds the exact composition spec hash. Any change after ratification creates a new spec and invalidates ratification.

Ratification answers: "Does this composition plan correctly represent how the approved ingredients should be combined?" It does not approve the final artifact — Gate 3 still does that. But it prevents the operator from discovering composition problems only after a full render.

Ratification is a **conditional sub-gate inside Assets**, not a fifth content stage. The four content stages remain Ideas, Draft, Assets, and Publish.

## What this does NOT change

- AMENDMENT-013's component approval, category completeness, manifest freeze, and Gate 3 remain fully in force.
- The operator still approves individual ingredients first.
- Gate 3 still approves the exact final artifact.
- The renderer is still provider-neutral behind RendererSpec v1.
- VF-RA-001..004 remain the render-layer tasks.
- The Writer still produces all audience-facing text; the Assembler never re-generates content.
- Capture policy, rights evidence, cost approval, and provenance requirements are unchanged.

## What this adds

1. A **CompositionPlan** schema declaring every element as structured data.
2. A **preview generator** producing low-cost per-element previews locally.
3. A **composition ratification sub-gate** between manifest freeze and render.
4. A **spec-hash binding** so any post-ratification change invalidates and forces re-ratification.
5. New state-machine transitions: `manifest_ready → composition_planning → composition_review_required → composition_ratified → assembling`.
6. Builder tasks for composition plan generation, preview rendering, ratification surface, and spec compilation from the ratified plan.

## Charter clauses added

- **The CompositionPlan declares every element of the final video.** Text, audio, visual, graphics, transitions, and canvas are each structured as typed elements with exact source hashes, timing, position, style, and animation. The plan is generated mechanically from the frozen manifest and approved Writer contract. It is provider-neutral and contains no vendor-specific fields. (AMENDMENT-014)
- **Per-element previews are generated locally before ratification.** Text specimens, audio waveforms, visual thumbnails, graphics frames, transition diagrams, and a full timeline diagram are produced from the CompositionPlan using local tools. Previews are evidence for ratification, not final artifacts. No provider API is called for preview generation. (AMENDMENT-014)
- **Composition ratification is a sub-gate between manifest freeze and render.** The operator reviews previews and ratifies or rejects the CompositionPlan. Ratification binds the spec hash. Any change after ratification creates a new spec and invalidates ratification. Ratification does not approve the final artifact — Gate 3 still does. (AMENDMENT-014)
- **Assembly consumes only a ratified CompositionPlan.** The RendererSpec is compiled from the ratified plan. An unratified, stale, rejected, or hash-mismatched plan fails closed. The provider renders only from the ratified spec. (AMENDMENT-014)

## State machine addition

The AMENDMENT-013 state machine gains two new transitions:

```
manifest_ready → composition_planning → composition_review_required → composition_ratified → assembling
```

With failure paths:
- `composition_planning → blocked` (spec generation failed)
- `composition_review_required → composition_planning` (operator requested changes)
- `composition_ratified → composition_planning` (post-ratification change detected)

## Implementation order

1. CompositionPlan schema (VF-CP-001)
2. Preview generator (VF-CP-002)
3. Composition ratification surface (VF-CP-003)
4. RendererSpec compilation from ratified plan (VF-CP-004)
5. State machine and orchestration integration (VF-CP-005)

These sit between VF-CW-010 (manifest freeze) and VF-RA-001 (RendererSpec) in the M15 sequence. See BUILD_PLAN for exact ordering.