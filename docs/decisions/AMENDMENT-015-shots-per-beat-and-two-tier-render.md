# AMENDMENT-015 — Shots per beat, and the two-tier render model

**Status:** RATIFIED by operator, 2026-07-25
**Amends:** `CORRECTION-episode-format-and-reference-assets-v1.0` §3.2; `assets/reference/stackpenni/grade_token/world_canon.md` (rendering style ruling)
**Supersedes:** the "one shot per beat by construction" rule
**Applies forward only.** Pieces already rendered are not re-cut.

---

## 1. Why this amendment exists

`CORRECTION-episode-format-and-reference-assets-v1.0` §3.2 established **one shot per
beat by construction**. That rule is wrong, and the error is the architect's, not the
builder's.

Beats are sized by the Writer as units of *meaning*, and their durations are set by
measured VO. In the 2026-07-25 review piece, beats averaged roughly eleven seconds. One
shot per beat therefore guaranteed eleven-second holds on a single generated image with
only image-to-video micro-motion on top. Frame-level scene analysis of that render
confirmed the pattern: change clusters at 3s, 6s, 9s, 11s, 12s, then dead zones of ten to
thirteen seconds with no visual change at all. Irregular slow is worse than uniformly
slow — the viewer learns to expect nothing.

No rendering-style change fixes this. No prompt rewrite fixes this. The rule itself
produced the defect.

## 2. Ruling — shots per beat

**One *staged action* per beat. N *shots* per beat.**

- `N = ceil(beat_duration_ms / 4000)`, minimum 1.
- All N shots for a beat share the same `character_block`, the same `location_block`, and
  the same `grade_token`. The beat's meaning does not change across its shots.
- Shots within a beat differ on exactly two axes: **framing** and **motion prompt**.
- Framing is drawn in order from the cycle `wide → medium → close → insert`, restarting
  as needed. The Assembler does not choose framing; it is mechanical.
- The motion prompt remains the only LLM-authored field, now one per shot rather than one
  per beat.
- Shot durations within a beat divide the beat's measured VO duration as evenly as
  possible, remainder to the final shot. VO remains the master clock. Beat boundaries are
  never crossed by a shot.

Consequence: roughly 2.5× the image generations per piece, no change to video generation
count per second of output, and no change to approved text. Image generation is the
cheapest thing in the chain. This is the correct place to spend.

## 3. Ruling — the two-tier render model

The world canon's rendering ruling stands: **painterly cinematic realism for the film
layer, flat vector for the graphic tier.** This amendment clarifies the boundary, because
the boundary was being read as a style conflict rather than a layer separation.

**Tier 1 — the footage layer (realism).** Everything that is part of the world: the
characters, the locations, the light, the grade. Generated from the gated reference
registry, animated by image-to-video, never carrying text or numbers.

**Tier 2 — the graphic tier (vector).** Everything composited *over* the world by the
renderer: caption pills, `number_card_v1`, `quote_card_v1`, lower thirds, the trident
watermark, the end card. Flat, deterministic, renderer-drawn, resolution-independent.

The two tiers coexist in the same frame by design. The prohibition is narrower than it
has been read: **no tier-2 rendering of a tier-1 subject.** A flat vector Fitzroy standing
in a realistic porch is forbidden. A flat gold number card composited over a realistic
porch shot is correct and expected — it is the same convention every broadcast and
documentary uses, and the flatness is precisely what signals "this is information about
the world, not part of it."

The caption pills already shipping in the production renderer are tier 2 working
correctly. They are the existence proof.

**The end card is the single permitted full-frame tier-2 surface.** After the story
closes, the frame belongs to the brand.

**Consequence for the character-animation work.** The SVG-plus-parametric-motion effort
was heading toward a vector character as the on-screen performer, which would have forced
a choice between the two tiers. That work is reassigned to tier 2 — card animation,
lower-third motion, end-card build. The craft carries over; the conflict disappears; no
work is discarded.

## 4. What does not change

- VO is the master clock. Shot durations derive from measured VO, never from estimates.
- All text and numbers are renderer-drawn. The banned-token list in the shot-spec prompt
  stands unchanged.
- Reference images are always canonical registry files, never chained outputs.
- No character appears in any episode until a gated face reference set exists for that
  character.
- Stills gate before animation spend, with explicit cost confirmation.
- AI proposes; the operator gates.
