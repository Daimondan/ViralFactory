# MANIFEST — 2026-07-02 batch D (operator UI review — intake console)

Per Inbox Protocol v1.0. File, execute APPLY, one CHANGELOG entry.

## Files

| File | Destination | Action |
|---|---|---|
| UI-REVIEW-001-intake-console.md | docs/reviews/UI-REVIEW-001-intake-console.md | ADD |
| MANIFEST-2026-07-02-D.md | docs/inbox/processed/ | (after filing) |

## APPLY

1. Treat UI-REVIEW-001 as **blocking for the operator end-to-end test**. The T2.6–T2.8 resequencing already gates `review-w2` on the operator review; this file is that review's output. The end-to-end test does not re-run until all seven acceptance checks in the review pass.
2. Update UI-DIRECTION to incorporate the session interaction model (F3) and the copy rule (F4). If UI-DIRECTION and this review ever conflict, this review wins — it comes from the operator using the real thing.
3. Add the "console renders sessions, not documentation" principle to CONTEXT.md verbatim from the review.
4. Extend the playbook step schema with optional `display_label` (operator-facing) and add `run_order` to playbook config. Backfill both for all eight playbooks. This is config/schema plumbing, not a charter change — no divergence file needed.
5. Voice input remains deferred per the existing T2.6–T2.8 record. Build the session component so the mic slots in later without rework, but ship it text+files only now.
6. Note in PROGRESS.md: operator UI review received 2026-07-02, findings F1–F4 accepted, end-to-end test blocked on UI-REVIEW-001 acceptance checks.
