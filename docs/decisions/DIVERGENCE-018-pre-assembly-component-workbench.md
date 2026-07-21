# DIVERGENCE-018 — Pre-assembly Component Workbench and manifest-locked assembly

**Filed:** 2026-07-21
**Filed by:** Architect from direct operator instruction
**Status:** RATIFIED by AMENDMENT-013
**Related:** AMENDMENT-003, AMENDMENT-009, AMENDMENT-010, AMENDMENT-011; `docs/reviews/REVIEW-pipeline-runtime-and-component-workbench-2026-07-21.md`

## Operator instruction

The current video pipeline is not giving the operator enough control before final assembly. The operator requires the system to generate and present the constituent parts of a video in separate categories — clips, soundtrack, voice-over, typography, graphics, and other declared elements — for human selection and approval before the assembler stitches the final artifact.

## Divergence from Charter v3.8

Charter v3.8 sends approved Writer work into an automated Media Planner/Assembler and relies primarily on Gate 3 approval of the exact assembled asset. AMENDMENT-011 deliberately removed the separate soundtrack micro-gate in favor of exact-artifact Gate 3 approval.

That boundary is no longer sufficient. It lets the system auto-select ingredients that express taste, identity, pacing, and voice before the operator can compare alternatives. It also couples generation to assembly, making failures difficult to resume and making it impossible to prove that the assembler used only human-approved ingredients.

## Decision questions

1. Should the existing Gate 3 be replaced? **No.** Final-artifact Gate 3 remains mandatory.
2. Is component review a fifth content stage? **No.** It is a conditional sub-gate within the existing Assets stage for composited media.
3. What enters assembly? **Only an immutable manifest of exact approved component versions.**
4. Does approval attach to a category name or an artifact? **An exact artifact/version/hash.** Category completeness is computed separately.
5. Can defaults remain hidden? **No, when they materially affect the piece.** Fonts, caption styles, overlays, transitions, and audio modes must be visible as specimens or previews and replaceable before freeze.
6. Can regeneration inherit approval? **No.** A regenerated or edited component is a new version and invalidates that role's completeness.
7. Can the assembler look up “latest” media? **No.** It accepts a frozen `assembly_manifest_id` and resolves only the listed versions.

## Resolution

Ratified by AMENDMENT-013. The binding flow becomes:

`approved Writer contract → generate component candidates → review/select by category → freeze exact manifest → deterministic assembly → Gate 3 exact-artifact review → Gate 4 publish decision`

AMENDMENT-011's rights, local-artifact, and exact-final-asset rules remain in force. Its “first and only soundtrack approval at Gate 3” rule is superseded: soundtrack **selection** now occurs in the Component Workbench, while Gate 3 still approves the exact final mix.
