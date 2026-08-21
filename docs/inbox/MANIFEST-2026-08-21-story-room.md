# MANIFEST — Story Room conversational co-creation

**Date:** 2026-08-21
**From:** Architect (`vf-architect`)
**Status:** APPLY IN ORDER

## Canonical files already filed by architect

Read in this order:

1. `docs/decisions/DIVERGENCE-028-story-room-conversational-co-creation.md`
2. `docs/decisions/AMENDMENT-020-story-room-conversational-co-creation.md`
3. `docs/CHARTER-v3.12.md`
4. `docs/reviews/REVIEW-story-room-redesign-baseline-2026-08-21.md`
5. `playbooks/story-room-co-creation.md`
6. `docs/plans/2026-08-21-story-room-controlled-implementation.md`
7. `BUILD_PLAN.md` M17

The architect also aligned README, CONTEXT, UI-DIRECTION, PROGRESS, and CHANGELOG.

## APPLY

1. Finish the open VF-PROOF-1618 blockers and capture the legacy baseline. This remains P0 because Story Room reuses the production tool bench.
2. Work M17 top-down, one task per commit.
3. Do not write UI first. Storage/event/artifact/lock/context contracts precede Desk and Story Room surfaces.
4. Do not delete or silently mutate legacy pipeline data/routes.
5. Do not enqueue the legacy Writer chain after a Story Room Gate 1 lock.
6. Do not create a second production state machine. Room stage is a navigation/artifact pointer; `ProductionSession` remains the Build execution state.
7. Every LLM process uses prompt + schema + validator + cache + provenance. Python validates mechanics only.
8. Existing M15 production services are reused behind atomic Story Room tools.
9. Primary navigation remains legacy-default until the three-piece proof and operator cutover decision.

## DIVERGENCE-017

Treat `docs/decisions/DIVERGENCE-017-inspiration-to-idea-flow.md` as superseded by DIVERGENCE-028 / AMENDMENT-020. New Story Room mode carries exact Inspiration evidence into a room rather than immediately generating a full idea/treatment. Existing compatibility records remain intact.

## Existing unrelated inbox item

`BUILDER-NOTE-022-carousel-native-audio.md` is pre-existing builder work marked superseded and is not part of this architect batch. Process it under its own history; do not mix it into M17.

## Required proof

Before checking the M17 checkpoint:

- human-seeded carousel;
- source-led Reel;
- half-formed personal story;
- one injected recoverable tool failure;
- laptop + true 390px deep 10-dimension UI review;
- targeted and full automated suite;
- exact gate/provenance/staleness evidence;
- no publish without explicit piece approval;
- operator cutover decision.

## Inbox processing

After reading and beginning APPLY:

1. move this manifest and `ARCHITECT-NOTE-2026-08-21-story-room.md` to `docs/inbox/processed/` with `git mv`;
2. append the normal builder consumption entry to PROGRESS and CHANGELOG;
3. leave canonical decision/review/playbook/plan files in place.
