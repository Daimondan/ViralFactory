# Operating Loop

*Repo location: `docs/OPERATING-LOOP.md`. How the three parties iterate. v1.0*

## Parties
- **Operator (Daimon):** directs in plain language, gathers materials, reacts, gates. Moves files between Claude and the repo. Never writes code.
- **Builder (Hermes agent):** works `BUILD_PLAN.md` top-down per its "How to work" rules. Commits per task, appends to `PROGRESS.md`, opens issues when blocked, tags `review-wN` weekly.
- **Architect (Claude):** reviews, analyzes, upgrades the design. Speaks only through files in this repo.

## Kickoff (once)
1. Operator loads the starter docs into the repo (README, BUILD_PLAN, CONTEXT, charter, playbooks, UI direction, intake, this file) + empty `PROGRESS.md`.
2. Operator to Hermes: *"Read README.md, follow the builder reading order (README → docs/CONTEXT.md → BUILD_PLAN.md → playbooks/), then start BUILD_PLAN.md at T0.1 per its How-to-work rules."*
3. In parallel: operator gathers everything in `docs/INTAKE-USER1.md`.

## Weekly cycle (architect review cadence)

> **Note:** This "weekly cycle" is the *build process* loop — Hermes builds, Claude reviews weekly. It is separate from the *product gate* (module update proposals → Daimon approves), which is **async** per `docs/decisions/DIVERGENCE-001-charter-amendments.md`. Do not confuse the two: the architect review is weekly; the product gate is a persistent queue Daimon clears when ready.

1. **Hermes** builds → checks boxes → `PROGRESS.md` lines → tags `review-wN`.
2. **Operator** brings to Claude: the repo link + their own thoughts (frustrations, ideas, change requests — operator reactions are design input).
3. **Claude** reviews commits/progress against the charter, folds in the operator's thoughts, returns files: `docs/reviews/review-wN.md` (corrections for Hermes) and any updated charter/playbooks/plan revisions.
4. **Operator** drops the files into the repo.
5. **Hermes** reads `docs/reviews/review-wN.md` FIRST and applies corrections before any new milestone work.

## Rules of the loop
- All architect direction arrives as versioned files in the repo — never as untracked instructions.
- Design changes go in the charter/playbooks (Claude writes), not improvised in code (Hermes never decides design).
- Blockers = GitHub issues; the weekly review answers them.
- This loop is the system's own pattern applied to building the system: builder proposes, humans + architect gate, corrections flow back as documents.
