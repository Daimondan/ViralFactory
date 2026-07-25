# MANIFEST-2026-07-24-reel-post-caption

**Date:** 2026-07-24
**From:** Architect
**To:** Builder
**Status:** Ready for processing

## Contents

1. `docs/inbox/ARCHITECT-NOTE-2026-07-24-reel-post-caption.md` — ruling on BUILDER-NOTE-017 / DIVERGENCE-022 (reel post caption missing)
2. `docs/decisions/DIVERGENCE-022-reel-post-caption-missing.md` — full divergence file with architect ruling (renumbered from DIVERGENCE-016 to resolve collision with ratified AMENDMENT-012)

## Builder actions

1. Read `docs/inbox/ARCHITECT-NOTE-2026-07-24-reel-post-caption.md` for the ruling.
2. Remove `docs/decisions/DIVERGENCE-016-reel-post-caption-missing.md` (reel-caption version — superseded by DIVERGENCE-022).
3. Implement DIVERGENCE-022 per the approved fix.
4. Separately fix or file the thread publish path bug at `buffer_adapter.py:232-237`.
5. Update PROGRESS.md and CHANGELOG.md.
6. Move this inbox batch to `docs/inbox/processed/` after reading and applying.

## Related

- BUILDER-NOTE-017-reel-post-caption-missing.md (the inbox item that triggered this ruling)
- Charter v3.10 §5 (per-piece approval, hard rule)
- Related defect: `buffer_adapter.py:232-237` (thread publish sends summary instead of posts — separate bug)