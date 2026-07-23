# DIVERGENCE-020 — Two-phase assembly: composition plan with per-element previews and ratification before render

**Filed:** 2026-07-23
**Filed by:** Architect (operator-directed)
**Status:** RATIFIED by AMENDMENT-014
**Supersedes:** None (extends AMENDMENT-013)
**Affects:** Charter v3.9 → v3.10, BUILD_PLAN M15 phases, assembly pipeline, Component Workbench

## Problem

AMENDMENT-013's Component Workbench lets the operator approve **individual ingredients** (this VO take, this image, this soundtrack). But it does not let the operator see or ratify **how those ingredients combine** before the renderer runs. The operator cannot currently preview:

- which words get emphasis in the caption and where the caption appears on screen;
- which font/style/size is used for each text role (hook, emphasis, lower-third, CTA);
- where charts, graphs, emojis, and graphics overlays appear on the timeline and on the canvas;
- where the soundtrack starts/stops, its volume curve, and where SFX fire;
- which transitions occur at which beat boundaries and their duration/easing;
- the visual framing/crop/focal point of each clip in its timeline slot.

The operator is asked to approve ingredients in isolation, then trust that the assembler composes them correctly. The bake-off (DIVERGENCE-019) proved the renderer faithfully executes whatever spec it receives — but the spec itself is invisible to the operator until the final artifact appears at Gate 3.

## Operator direction

Split assembly into **two phases**:

### Phase 1 — Composition Plan + Per-Element Previews + Ratification

After component approval and manifest freeze, produce a **CompositionPlan** that declares every element of the final video as a structured, previewable specification:

- **Text elements**: every on-screen text role (hook, caption, emphasis words, lower-third, CTA), with exact wording, font file, size, color, position, timing in/out, emphasis marks, and word-level timing if available.
- **Audio elements**: VO track with timing and gain curve; music track with start/stop, gain curve, and ducking points; SFX list with trigger timestamps and gain.
- **Visual elements**: each video clip/still with source hash, trim in/out, crop/focal point, position on canvas, scale, and any motion (zoom/pan/keyframes).
- **Graphics elements**: charts, graphs, emojis, overlays, lower-third graphics — each with type, source/config hash, position, scale, timing in/out, and animation.
- **Transitions**: every transition between segments with type (cut/crossfade/wipe/slide), duration, easing, and the exact beat boundary it serves.
- **Canvas**: resolution, aspect ratio, background, safe zones, and platform-specific framing guides.

The operator gets **per-element previews**: a text preview of each text role rendered in its declared font; a waveform/level preview of the audio mix; a thumbnail of each visual clip showing its crop/framing; a static frame of each graphics overlay; a timing diagram showing the full timeline. These are **low-cost previews** — not full renders, but enough to see and ratify every element.

The operator **ratifies the CompositionPlan** as a whole. Ratification is a new sub-gate between manifest freeze and render. It binds the exact composition spec hash. Any change after ratification creates a new spec and invalidates ratification.

### Phase 2 — Shotstack Assembly

Only after ratification, the CompositionPlan is compiled to a RendererSpec and submitted to Shotstack (or the configured provider). The provider assembles the final video mechanically from the ratified spec. The output is downloaded, hashed, probed, and verified against the ratified spec. Gate 3 then approves the exact final artifact.

## Proposed flow

```
Component Workbench (AMENDMENT-013)
  → manifest freeze (exact ingredient hashes)
    → CompositionPlan generation (structured per-element spec)
      → per-element previews (text/font/audio/visual/graphics/timing)
        → COMPOSITION RATIFICATION SUB-GATE (operator approves the plan)
          → RendererSpec v1 compilation (from ratified CompositionPlan)
            → Shotstack adapter submission
              → download / hash / probe / verify
                → GATE 3 (exact final artifact approval)
```

## What this does NOT change

- AMENDMENT-013's component approval, category completeness, manifest freeze, and Gate 3 remain intact.
- The operator still approves individual ingredients first.
- Gate 3 still approves the exact final artifact.
- The renderer is still provider-neutral behind RendererSpec v1.
- VF-RA-001..004 (RendererSpec, adapters, bake-off, production integration) still govern the render layer.

## What this adds

- A **CompositionPlan** schema that declares every element of the video as structured data.
- A **preview generator** that produces low-cost per-element previews from the plan.
- A **composition ratification sub-gate** between manifest freeze and render.
- A **spec-hash binding** so any post-ratification change invalidates and forces re-ratification.
- Builder tasks for the composition plan, previews, ratification surface, and spec compilation.

## Decision

Ratify as AMENDMENT-014. Bump charter to v3.10. The composition ratification sub-gate is a conditional sub-gate inside Assets, between manifest freeze and assembly — not a fifth content stage. The four content stages remain Ideas, Draft, Assets, and Publish.