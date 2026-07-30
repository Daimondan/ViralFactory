# DIVERGENCE-025: Operator requests a 2D vector Fitzroy treatment

**Status:** RATIFIED by AMENDMENT-018 (`docs/decisions/AMENDMENT-018-versioned-visual-treatments.md`)
**Filed by:** Builder
**Date:** 2026-07-26
**Severity:** P1 — visual-direction conflict; no production implementation may proceed
**Type:** STRATEGIC / STRUCTURE

## Operator direction

After reviewing a standalone Fitzroy portrait in cinematic painted realism, the operator asked for it to be "more like the 2d vector."

## Conflict with current ratified direction

`docs/decisions/AMENDMENT-015-shots-per-beat-and-two-tier-render.md` §3 ratifies painterly cinematic realism for the footage/world layer and flat vector for the renderer-drawn graphic tier only. It explicitly prohibits a tier-2 rendering of a tier-1 subject: a flat vector Fitzroy as the on-screen performer is forbidden under the current rule.

The request therefore cannot be silently implemented as a change to the StackPenni episode or character-generation path.

## Builder action taken

- Preserved the currently ratified cinematic treatment and all canonical reference assets unchanged.
- Treating any requested vector image as an isolated **operator comparison render**, not an approved production asset and not evidence to alter the module.
- Did not alter `modules/stackpenni/visual-style.md`, the Character Bible, render configuration, reference registry, prompts, or code.

## Requested ruling

Please specify one of:

1. **Retain current two-tier rule:** vector Fitzroy may be produced only as a comparison/graphic exploration, never footage-layer content.
2. **Amend the visual system:** allow a 2D-vector character treatment in a defined scope (which formats, whether it replaces or coexists with cinematic realism, reference/continuity rules, and Gate 3 presentation).
3. **Clarify a narrower request:** retain cinematic characters but adopt selected vector characteristics (for example simpler shapes, flatter composition, or a graphic background treatment).

No production-path change should be made until that ruling is ratified.

## 2026-07-26 operator comparison specification

The operator supplied a concrete palette-lock specification for a flat-vector room, isolated Fitzroy, isolated Stacks, blank newspaper, and black controller. The shared generation block requires exactly: outline `#1D1C21`, cream `#FCF8E4`, deep navy `#0E1A2F`, gold `#D9A93F`, warm wood brown `#8A5A2B`, and warm-brown skin tones; it excludes teal, turquoise, coral, pink, gradients, texture, grain, and all text/signage.

This detailed brief makes the requested direction testable, but does not ratify it into the footage layer. The five requested renders remain non-production comparison assets until the requested ruling resolves the Tier-1 character-style conflict.

The comparison outputs were mechanically palette-locked after generation. Each final PNG contains only the declared outline, cream, navy, gold, wood, warm-brown skin, and newspaper-grey swatches; validation found zero out-of-palette raster colours. This makes the requested shared palette technically identical across the five comparison assets without changing the production renderer or canonical modules.
