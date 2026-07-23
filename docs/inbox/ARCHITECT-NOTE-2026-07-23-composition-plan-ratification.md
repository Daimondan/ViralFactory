# ARCHITECT-NOTE — 2026-07-23 — Two-phase assembly: composition plan + ratification

**To:** Builder
**From:** Architect (operator-directed)
**Date:** 2026-07-23
**Decisions:** AMENDMENT-014 + DIVERGENCE-020
**Charter:** v3.9 → v3.10

## What happened

The operator reviewed the Creatomate vs Shotstack bake-off results and directed a new architecture: split assembly into **two phases** so the operator can see and ratify **every element** of the video before the renderer runs.

**The problem:** AMENDMENT-013 lets the operator approve individual ingredients (this VO take, this image, this soundtrack), but the operator cannot currently preview *how those ingredients combine* — which words get emphasis, which font, where graphics appear, when SFX fire, which transitions occur where — until the final render appears at Gate 3. That's too late.

**The fix:** Add a CompositionPlan between manifest freeze and render. The plan declares every element as structured data. Per-element previews are generated locally (no provider API). The operator ratifies the plan. Only then does the RendererSpec compile and the provider render.

## New flow

```
manifest freeze
  → CompositionPlan generation (structured per-element spec)
    → per-element previews (text/font/audio/visual/graphics/timing — all local)
      → COMPOSITION RATIFICATION (operator approves the plan)
        → RendererSpec v1 compilation (from ratified plan)
          → provider render (Shotstack or configured fallback)
            → download / hash / probe / verify
              → GATE 3 (final artifact approval)
```

## New state machine transitions

```
manifest_ready → composition_planning → composition_review_required → composition_ratified → assembling
```

Failure paths:
- `composition_planning → blocked`
- `composition_review_required → composition_planning` (operator requested changes)
- `composition_ratified → composition_planning` (post-ratification change detected)

## New tasks (dependency order)

| Task | Title | Depends on |
|---|---|---|
| VF-CP-001 | CompositionPlan schema + generator | VF-CW-010 |
| VF-CP-002 | Per-element preview generator | VF-CP-001 |
| VF-CP-003 | Composition ratification surface | VF-CP-002 |
| VF-CP-004 | RendererSpec compilation from ratified plan | VF-CP-003 |

VF-RA-001 now depends on VF-CP-004 (not VF-CW-010 directly).

## What the CompositionPlan contains

**Text elements:** every on-screen text role (hook, caption, emphasis words, lower-third, CTA, proof, citations) with exact wording from the Writer contract, font file hash, family, weight, size, color, position, timing in/out, word-level timing, emphasis marks.

**Audio elements:** VO track (source hash, trim, gain curve, ducking); music track (start/stop, gain, ducking, fade); SFX list (trigger timestamps, gain, duration); mix spec (LUFS target, true peak limit).

**Visual elements:** each clip/still with source hash, trim, crop/focal, canvas position, scale, motion keyframes.

**Graphics elements:** charts, graphs, emojis, overlays, lower-thirds — type, config hash, position, scale, timing, animation.

**Transitions:** type (cut/crossfade/wipe/slide/zoom), duration, easing, beat boundary.

**Canvas:** resolution, aspect ratio, fps, background, safe zones, platform framing.

## Previews (all local, no provider API)

| Element | Preview |
|---|---|
| Text role | Font specimen in declared font/size/color/position |
| Audio mix | Waveform with VO/music/SFX lanes, gain curves, LUFS target |
| Visual clip | Thumbnail with crop/framing/safe-zone overlay |
| Graphics overlay | Static frame on representative background |
| Transition | Annotated timing diagram |
| Full timeline | Horizontal multi-lane timeline with all elements |

## What does NOT change

- AMENDMENT-013 component approval, manifest freeze, and Gate 3 are fully preserved.
- The operator still approves individual ingredients first.
- Gate 3 still approves the exact final artifact.
- The renderer is still provider-neutral behind RendererSpec v1.
- The Writer still produces all audience-facing text.
- VF-RA-001..004 still govern the render layer.

## Files to read

1. `docs/decisions/DIVERGENCE-020-two-phase-composition-plan-and-ratification.md`
2. `docs/decisions/AMENDMENT-014-two-phase-composition-plan-and-ratification.md`
3. `docs/CHARTER-v3.10.md`
4. `BUILD_PLAN.md` (Phase M15-D)
5. `docs/decisions/DIVERGENCE-019-provider-neutral-render-execution-boundary.md`
6. `docs/reviews/REVIEW-reference-video-renderer-bakeoff-2026-07-23.md`

## Hard stops

- Do not build the ratification UI before the CompositionPlan schema exists (VF-CP-001 → VF-CP-002 → VF-CP-003).
- Do not put vendor-specific fields in the CompositionPlan.
- Do not call any provider API for preview generation.
- Do not allow assembly without a ratified CompositionPlan.
- Do not weaken AMENDMENT-013's manifest freeze or Gate 3.