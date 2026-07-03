# MANIFEST — 2026-07-03-g

Hermes: file the following, update the changelog, then move this manifest to `docs/inbox/processed/`.

| File | Destination | Action |
|---|---|---|
| `CORRECTION-source-grounding-and-auto-production-v1.0.md` | `docs/corrections/CORRECTION-source-grounding-and-auto-production-v1.0.md` | ADD |

## Notes for Hermes

- **Priority split:** Section 1.3 (kill `source_material[:4000]` + snapshot cap) and Section 4 (dead-code sweep, CONTEXT.md lines) are quick and may land immediately. Sections 1 (Source Bank + source_refs), 2 (auto-production chain), and 3.1 (profiles.yaml + provenance profile column) are P1 architecture — sequence **after** T3.13 S1+S3 are confirmed landed. Do not enable the auto-chain before S1+S3.
- Section 3.2 Analyst scraping is M6 scope — do not build now; the `sources` table is its landing zone.
- BUILD_PLAN: add tasks for Source Bank table + source_refs, auto-production chain (new card states `producing`, `asset_ready`, `production_failed`), and profiles config. Architect defers exact task numbering to you; log in changelog.
- No-auto-publish remains absolute; the chain terminates at asset review.
