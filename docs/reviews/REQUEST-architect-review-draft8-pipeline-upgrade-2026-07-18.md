# REQUEST — Architect Review: Draft 8 Reel → Reusable Visual + Soundtrack Pipeline

**Date:** 2026-07-18
**From:** Hermes builder
**To:** vf-architect
**Status:** AWAITING ARCHITECT RULING
**Operator ruling:** Corrected Reel v3 approved as the visual standard; leave v3 VO-only; promote the proven visual lessons and the newly identified soundtrack requirements into the reusable pipeline only after architect ratification.

## Review package

1. Implementation proposal: `docs/plans/2026-07-18-draft-8-reel-correction-then-pipeline-upgrade.md`
2. Evidence and decision ledger: `docs/reviews/2026-07-18-draft-8-reel-correction-ledger.md`
3. Prior verified assembler audit: `docs/reviews/ASSEMBLER-UPGRADE-BASELINE.md`
4. Approved production artifact: asset 6, media ID 42, `data/media/6/final_2.mp4`
5. Approved artifact SHA-256: `f94c4ad44d94b4054b9cd267ee45b878239cbd012042ed3c35bf176c57aa172a`
6. Operator review proxy: `https://drive.google.com/file/d/1Wl6mGxBRYRMVZEhyHNkkqbrJcXgE6x5p/view?usp=sharing`

## What the approved experiment proved

The old Reel pipeline failed despite completing mechanically. It used unrelated generated presenters, froze short motion clips while VO continued, converted structured text intent to dictionary representations, clipped whole-beat captions, underused information graphics, and falsely green-lit missing visual evidence.

The approved correction succeeded by using:

- VO as the measured master clock;
- semantic visual events inside broad narrative beats;
- human footage for relationship/emotion/planning;
- deterministic editorial graphics for definitions, comparisons, reframes, and CTA;
- exact phrase captions reconstructed from the approved VO;
- separate renderer-owned text roles;
- an exclusive caption lane;
- source provenance and cultural-fit review;
- operator approval of sources and style frames;
- event-aware post-render evidence;
- versioned final registration without publication.

The operator subsequently identified one remaining standard gap: the approved v3 is VO-only, with no music bed or semantic SFX. The operator chose not to revise v3, but requires the reusable upgrade to make soundtrack intent explicit rather than silently omit it.

## Builder recommendation requiring ratification

Promote the **decision process**, not Draft 8's exact scenes, into the generic system:

1. Writer intent remains structured and exact.
2. A Visual Director LLM creates schema-validated semantic events.
3. Deterministic compilers preserve approved text, timing, source identity, and soundtrack intent.
4. Source planning distinguishes real capture, stock, reference, generated still/motion, and renderer graphic.
5. Operator gates cover storyboard, source/provenance/cost, style frames, soundtrack preview, and final artifact.
6. Renderer roles and safe regions come from format/tenant configuration.
7. Required review evidence fails closed when skipped or incomplete.
8. Every Reel has an explicit soundtrack mode; VO-only requires approval.
9. Music/SFX sources, licences, costs, cue purposes, ducking, and rendered audibility are persisted and reviewed.
10. Per-piece publication approval remains separate and mandatory.

## Architect decisions requested

Please rule on:

1. Whether semantic visual events are an enrichment of the existing beat/edit-plan model or require a new versioned contract.
2. The authoritative schema boundary between Writer intent, Visual Director judgment, deterministic compiler output, and renderer instructions.
3. Whether soundtrack planning belongs in the same visual-event contract or a parallel `soundtrack_plan` contract.
4. How this proposal merges with completed M10 compliance work, M11 episode-format/reference-assets work, and the assembler-upgrade baseline without duplicating systems.
5. Whether style-frame and soundtrack-preview approvals are new hard gates, conditional gates reused from approved presets, or both.
6. The required provenance contract for stock licences, generated media, music beds, and SFX.
7. The exact evidence completeness rule for visual semantics, captions, source provenance, music/SFX audibility, and mix quality.
8. Whether any proposed rule conflicts with Charter v3.5 and therefore requires a versioned amendment/divergence ruling.
9. The implementation order and milestone boundary for `BUILD_PLAN.md`.

## Constraints that must survive review

- No StackPenni strings or business values in generic code.
- Judgment lives in versioned prompts + schemas + validators, never keyword heuristics.
- Mechanical rendering/extraction remains deterministic.
- No paid generation, music, SFX, or licensing action without a fresh operator-approved estimate.
- Generated media cannot satisfy real-capture requirements.
- Style previews cannot become production graphic layers with baked sample captions.
- Caption, emphasis, information, CTA, and brand roles remain separately composited and collision-checked.
- VO remains the master clock for VO-led pieces.
- Missing review evidence cannot pass.
- Synthetic placeholder tones cannot be presented as finished sound design.
- VO-only delivery must be explicit and approved.
- No publication without explicit approval on that piece.

## Requested architect response format

Please return through `docs/inbox/` with a `MANIFEST-*.md` that:

1. adds or supersedes the appropriate correction/decision document;
2. patches `BUILD_PLAN.md` with ordered task IDs and acceptance criteria;
3. identifies any charter amendment or divergence ruling;
4. states what existing M10/M11/assembler tasks are reused, replaced, or superseded;
5. preserves the approved artifact as the regression reference but does not hardcode its treatment.

Until that response is processed, the builder will not implement the proposed reusable runtime changes.
