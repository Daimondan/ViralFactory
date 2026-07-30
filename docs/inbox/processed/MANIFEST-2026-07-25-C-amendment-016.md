# MANIFEST-2026-07-25-C-amendment-016

**Date:** 2026-07-25
**From:** Architect
**To:** Builder
**Status:** Ready for processing
**Repo state reviewed:** `1208220` — "DOCS: request Bundle native-audio ruling"
**Note:** This is the **third** manifest dated 2026-07-25. The first (repo health + blueprint split)
and second (episode wiring) are separate batches and are not reopened by this one.

## Contents

| # | Inbox file | Destination | Action |
|---|---|---|---|
| 1 | `docs/inbox/AMENDMENT-016-platform-native-audio-attachment.md` | `docs/decisions/AMENDMENT-016-platform-native-audio-attachment.md` | ADD |

## Builder actions

1. File item 1 per the table above.

2. **Mark DIVERGENCE-024 as ratified.** Add a status line at the top of
   `docs/decisions/DIVERGENCE-024-bundle-native-instagram-audio.md` pointing to AMENDMENT-016. Do not
   rewrite the divergence body — it is the record of what was found and asked, and it stands.

3. **Move `BUILDER-NOTE-019-bundle-native-instagram-audio.md` to `docs/inbox/processed/`** in the
   filing commit, per inbox protocol §"Builder-to-architect notes" item 4. The architect response has
   now arrived.

4. Read AMENDMENT-016 in full before writing any code. Conditions C1 through C8 are binding and the
   Definition of Done is the acceptance test. Two conditions are not code changes and must not be
   folded silently into an implementation commit:

   - **C4** is a measurement. Publish one probe Reel with a native attachment over representative VO,
     retrieve the live Reel, and report the measured narration intelligibility and relative levels.
     Paste the measurement into the changelog. Until C4 is reported and passing, a VO-led piece must
     be **refused this role by code**, not by convention or comment.
   - **C5** requires a proven failure path. Demonstrate a deliberate mismatch between the approved
     `audio_id` and the live attachment, and show the failure surfacing with an unpublish route.

5. `BUILDER-NOTE-018-remaining-work-2026-07-25.md` and `DIVERGENCE-023-episode-format-guide-resolution.md`
   are **not** answered by this batch. They remain open and await a separate architect pass. Leave
   BUILDER-NOTE-018 in the inbox.

6. One `CHANGELOG.md` entry for this batch. Update `docs/PROGRESS.md`.

## APPLY — Definition of Done amendment (binding, effective immediately)

Add the following to `docs/PROCESS-definition-of-done-v1.0.md` and apply it to all future batches,
including the two already in flight:

> **Work is not reportable as complete until it is on `origin/main`.**
> A local commit is not a delivered commit. Every completion report must quote the `origin/main` SHA
> that contains the work, verified with `git log --oneline -1 origin/main` after pushing — not a
> local `HEAD` SHA. Before reporting any batch done, run `git log --oneline origin/main..HEAD` and
> confirm it returns nothing.

Rationale, recorded so it is not relitigated: on 2026-07-25 twenty-two commits — including the whole
of the episode-wiring batch and both 07-25 inbox filings — sat on the VPS local `main` with a clean
working tree while `origin/main` still pointed at an operator browser upload. Three consecutive
architect reviews were conducted against a repository that did not contain the work under review, and
each reported it missing. This is the third variant of the same failure: first documents in the
working tree, then documents committed locally, both reported as "in the repo." The gap is a missing
check, not a discipline problem, so the check goes in the process.

## APPLY — Reopen P1-5

`CORRECTION-repo-health-v1.0.md` item P1-5 was reported in the changelog alongside eleven completed
items, with "Remaining modules pending" as an inline qualifier. It is a partial item reported as a
finished one. Reopen it explicitly, naming the four outstanding migrations to the `src/db.py`
connection factory: `app.py`, `production_orchestrator.py`, `materials.py`, `jobs.py`.

Also outstanding from that batch's own recorded questions: the full test suite final run, ffprobe on a
rendered master, and the human UI walkthrough. The blueprint split does not begin until those close.

## Related

- AMENDMENT-011 — soundtrack discovery, rights evidence, and Gate 3 approval. AMENDMENT-016 amends its
  §2 "exact artifact" rule for the native-audio role only; the rest stands unchanged.
- AMENDMENT-010 — VO as master clock. The basis for condition C4.
- Reference asset registry — music beds remain a required owned asset class. AMENDMENT-016 explicitly
  does not supersede them and must not be cited as grounds for deferring bed work.
