# MANIFEST — 2026-07-02 batch B (architect interim review + proposed amendment)

Per Inbox Protocol v1.0. File, then execute APPLY, then log one CHANGELOG entry.

## Files

| File | Destination | Action |
|---|---|---|
| REVIEW-M2-MIDPOINT.md | docs/reviews/REVIEW-M2-MIDPOINT.md | ADD (create docs/reviews/; also move docs/review-w1_1.md and docs/review-divergence-001.md into docs/reviews/, updating references) |
| AMENDMENT-004-treatment-block-PROPOSED.md | docs/decisions/AMENDMENT-004-treatment-block.md | ADD — **check the status line first.** If PROPOSED: file it, apply NOTHING from it, open a GitHub issue "AMENDMENT-004 awaiting operator approval". If APPROVED: file it and execute its charter/BUILD_PLAN impact (charter → v3.3). |
| MANIFEST-2026-07-02-B.md | docs/inbox/processed/ | (after filing) |

## APPLY

1. Treat R10 and R11 (see review) as blocking: land before T2.3 begins. For R10's repo-visibility item: the operator has chosen PUBLIC deliberately so the architect can read the repo — record this as a CHANGELOG decision and fix the stale "(private)" note in PROGRESS.md. The console-auth requirement in R10 stands unchanged.
2. Reorder BUILD_PLAN M2 per the review's "Revised M2 order" — T2.9 moves ahead of T2.3 with expanded scope (all module + config write paths).
3. Amend T2.7 AC per R16 item 4.
4. Extend the zero-tenant-strings test to `src/templates/` and `prompts/` (R12).
5. Clear the stale "Tag review-w1" checkbox in PROGRESS.md.
6. If AMENDMENT-004 arrives APPROVED: add the Format Guide schema enrichment to T2.3 BEFORE building it (time-sensitive), and fold the M3 additions into the plan per the amendment.
7. review-w2 remains the M2-completion tag; do not tag for this interim review.
