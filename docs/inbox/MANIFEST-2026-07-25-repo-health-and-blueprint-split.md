# MANIFEST-2026-07-25-repo-health-and-blueprint-split

**Date:** 2026-07-25
**From:** Architect
**To:** Builder
**Status:** Ready for processing
**Repo state reviewed:** `2b793f1` — "Thread publish fix: send actual thread posts to Buffer, not summary line"

## Contents

| # | Inbox file | Destination | Action |
|---|---|---|---|
| 1 | `docs/inbox/CORRECTION-repo-health-v1.0.md` | `docs/corrections/CORRECTION-repo-health-v1.0.md` | ADD |
| 2 | `docs/inbox/CORRECTION-app-blueprint-split-v1.0.md` | `docs/corrections/CORRECTION-app-blueprint-split-v1.0.md` | ADD |
| 3 | `docs/inbox/route_parity.py` | `scripts/route_parity.py` | ADD |

## Builder actions

1. File all three items to their destinations per the table above. Note that item 3 is
   executable tooling, not documentation — it belongs in `scripts/`, not `docs/`.
2. Read `CORRECTION-repo-health-v1.0.md` in full and execute it as **one batch**. Twelve
   items: P0-1 through P0-4 (deployment-blocking), P1-5 through P1-8, P2-9 through P2-12.
   Report per item by P-number.
3. **Before any code change in step 2**, capture the route baseline from the current tree —
   it is the contract for the later refactor and cannot be regenerated afterwards:
   ```bash
   PYTHONPATH=src python3 scripts/route_parity.py --write docs/reviews/route-baseline.json
   git add docs/reviews/route-baseline.json && git commit -m "Route baseline at 2b793f1 (pre-refactor contract)"
   ```
4. Two items in the repo-health batch require **investigation and a written finding before
   any code is changed**. Do not skip these or fold them silently into a fix:
   - **P1-8:** confirm on the VPS whether `insightface` and `onnxruntime` import and whether
     the ONNX model file exists on disk. Paste the actual command output into the changelog.
     If they are absent, Layer-2 identity QC has never run, and that is the finding.
   - **P2-12:** determine whether AMENDMENT-007's mechanical format parsers
     (`_get_platforms_from_format_entry`, `_get_variant_type_from_format_entry`, both
     currently unreferenced) were written but never wired in. If so this is a charter
     compliance gap, not dead code — file a divergence rather than deleting them.
5. Meet the repo-health Definition of Done, including the full human UI walkthrough and the
   pasted terminal transcript for the clean-environment install. Update `CHANGELOG.md` and
   `PROGRESS.md`.
6. **Only after step 5 is complete and green**, read
   `CORRECTION-app-blueprint-split-v1.0.md` and begin its commit sequence. Twenty-one
   commits, one domain per commit, route parity passing at every commit. Tag review
   checkpoints on GitHub at commits 8, 14, and 19 so the operator can bring the repo link
   back for an architect pass mid-refactor.
7. Log one CHANGELOG entry per batch (one for repo health, one for the blueprint split — not
   one for all twenty-one commits).
8. Move this manifest and the two correction files' inbox copies to `docs/inbox/processed/`
   in the filing commit.

## Sequencing constraint (binding)

The blueprint split moves roughly 10,000 lines and must not begin until the repo-health batch
is complete. Two reasons: it needs a known-good baseline underneath it, and interleaving a
behaviour-changing batch with a pure-move refactor makes any regression impossible to
attribute to one or the other.

## Scope constraint (binding)

`CORRECTION-app-blueprint-split-v1.0.md` changes **no behaviour**. If a defect is spotted
while moving code, file it and keep moving — do not fix it in a migration commit. A migration
commit that also changes behaviour cannot be cleanly reverted, which defeats the sequencing.

## Related

- Charter v3.10 — gate discipline; the module review gate is touched by blueprint commit 4
  (`library`) and warrants an unhurried walkthrough.
- AMENDMENT-007 — mechanical format metadata parsing; see builder action 4 above.
- AMENDMENT-010 Condition 3 — caption phrase bounds (3/6 words); repo-health P1-7 extends
  this with sentence-boundary awareness and does not alter the bounds themselves.
- `docs/reviews/REVIEW-assembly-quality-and-renderer-boundary-2026-07-22.md` — repo-health
  P1-6 completes the encode half of the four renderer QA findings; the loudnorm and caption
  chunking halves are confirmed already landed and need no further work.
- `deploy/viralfactory.service` — `--workers 2` is the condition that makes repo-health P0-3
  (duplicate transcription race) live rather than theoretical.
