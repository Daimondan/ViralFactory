# MANIFEST-2026-07-25-B-episode-wiring

**Date:** 2026-07-25
**From:** Architect
**To:** Builder
**Status:** Ready for processing
**Repo state reviewed:** `da1d3b4` — "FIX: Nav counter not updating when ideas move to draft"
**Note:** This is the **second** manifest dated 2026-07-25. The first
(`MANIFEST-2026-07-25-repo-health-and-blueprint-split`) is a separate batch. Do not conflate
them, and do not begin this batch until that one's Definition of Done is met and green.

## Contents

| # | Inbox file | Destination | Action |
|---|---|---|---|
| 1 | `docs/inbox/AMENDMENT-015-shots-per-beat-and-two-tier-render.md` | `docs/decisions/AMENDMENT-015-shots-per-beat-and-two-tier-render.md` | ADD |
| 2 | `docs/inbox/CORRECTION-episode-wiring-and-source-diversity-v1.0.md` | `docs/corrections/CORRECTION-episode-wiring-and-source-diversity-v1.0.md` | ADD |

## Builder actions

1. File both items per the table above.

2. **Read `AMENDMENT-015` before the correction.** It amends
   `CORRECTION-episode-format-and-reference-assets-v1.0` §3.2 — the "one shot per beat by
   construction" rule is withdrawn. That rule caused the eleven-second holds in the reviewed
   render; the error was the architect's. The amendment also clarifies the realism/vector
   boundary as a two-tier layer model rather than a style choice. Both rulings are ratified
   by the operator, so treat them as settled and inherit them forward.

3. Execute `CORRECTION-episode-wiring-and-source-diversity-v1.0.md` as **one batch**. Ten
   items: P0-1 through P0-4 (blocking), P1-5 through P1-8, P2-9 through P2-11. Report per
   item by P-number with evidence.

4. **P0-1 is a hard precondition and includes a task that is not a code change.** Commit the
   character bible, then surface `world_canon.md` (DRAFT) and
   `visual-style-amendment-proposed.md` (PROPOSED) on the module review gate for operator
   decision. Do not self-approve either. Then audit the VPS working tree against `main` and
   paste `git status --porcelain` — this is the third recurrence of foundational documents
   living only in the working tree, and I want the full list this time, not just the two we
   already know about.

5. Two items require **investigation and a written finding before any code changes**:
   - **P0-3:** run the extended bidirectional validator across the entire process registry
     and report every process it flags on first run. The `media_plan_v2` mismatch is the one
     I found by hand; assume there are others and report them rather than fixing quietly.
   - **P1-7:** verify each candidate feed URL parses and each YouTube channel ID resolves
     before committing any of them. Report per-source status. Two channels currently share
     the malformed ID `UC9bFRvRiGR8xKDhK3xq+Phg`, which cannot be valid.

6. **P0-4 is the one item where I want the measurement, not the diff.** The clipping is
   caused by `loudnorm` sitting behind the `if not all_sfx: return None` guard in the SFX
   function, so VO-only pieces receive no normalization at all. Extract it into an
   unconditional final stage after all mixing, add an explicit `alimiter`, and paste the
   `ebur128` summary from a fresh VO-only render as proof.

7. **The registry work is split into two items, and the split is deliberate — do not
   recombine them.** The registry currently holds nine files: one realism character
   reference, zero location plates, zero music beds.
   - **P2-10 is the only place in this batch where generation happens.** One Stackwell
     candidate at a time, presented paired with the gated Fitzroy render so resemblance and
     style match can be judged side by side, iterated on operator feedback until approved.
     No grid of candidates, no multi-select, no bulk approve. Cost surfaced per iteration.
     Blocked on P0-1.
   - **P2-11 generates nothing** — written plan and cost surface for the remaining fifteen
     renders only. Blocked on P0-1 and on P2-10, because there is no standard to plan the
     fan-out against until Stackwell is locked.

   These were one sixteen-image item in my first draft and that was wrong. Extending a
   character who already has a gated standard is matching work. Establishing Stackwell, who
   has no realism precedent and has to read as Fitzroy's grandson, is not — it is the render
   most likely to need several attempts, and it must not be approved on the same click as
   fifteen others. If Stackwell is still awaiting operator decision when everything else is
   green, report that as awaiting decision. It is not incomplete work and it does not block
   the batch from being reported done.

8. Meet the Definition of Done in full, including the human UI walkthrough — every button on
   the module review gate, the soundtrack gate, the Stackwell iteration gate, the cost
   confirmation surface, and a complete idea → draft → asset → media plan → render pass.
   Report what you clicked and what happened. A passing test suite is not a walkthrough.

9. Tag a review checkpoint on GitHub once P0-1 through P0-4 are complete and before starting
   P1-5, so the operator can bring the repo link back for an architect pass mid-batch.

10. One `CHANGELOG.md` entry for the batch. Update `PROGRESS.md`. Move this manifest and both
    inbox copies to `docs/inbox/processed/` in the filing commit.

## Out of scope for this batch

Restated here because the instinct will be to reach for these:

- Do not rewrite `media_plan_v1.md`. Wire v2; leave v1 for non-episode assets.
- Do not touch `prompts/ideas/generate_v1.md`. The diversity defect is in `config/sources.yaml`.
- Do not change the encode tiers. The 3.33 Mbps measurement is correct CRF behaviour.
- Do not add bulk-approve or approve-all to any gate.
- Do not generate any of the fifteen fan-out renders under P2-11, and do not start them early
  because Stackwell's approval came in quickly. P2-11 is a plan in this batch regardless.
