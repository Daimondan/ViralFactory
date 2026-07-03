# MANIFEST — 2026-07-03-c (addendum)

Third delivery of the day, following MANIFEST-2026-07-03 and -b. From the operator's second hands-on review round: pipeline UX defects, media generation, and the voice cloning stack.

| File | Destination | Action |
|---|---|---|
| CORRECTION-pipeline-ux-and-media-generation-v1.0.md | docs/reviews/CORRECTION-pipeline-ux-and-media-generation-v1.0.md | ADD |
| DECISION-voice-cloning-vo-v1.0.md | docs/decisions/DECISION-voice-cloning-vo-v1.0.md | ADD |
| MANIFEST-2026-07-03-c.md | docs/inbox/processed/MANIFEST-2026-07-03-c.md | (move after processing) |

## Notes for Hermes

1. **Build order across the whole day's batch:** (1) onboarding drafting-input package + validation fixes (manifest -a, P0-1/P0-2) → (2) F1 busy states + jobs table from this correction — the jobs table is shared infrastructure for everything async → (3) Whisper worker (manifest -b) on that jobs framework → (4) gate relocation to Library + continuity fixes (manifest -a P1) → (5) F2/F3 (audit flags, visual direction) → (6) F4/F5 media generation + publish preview → (7) voice reference set + Chatterbox VO. Items 3, 5 and 6 can interleave; nothing in 6–7 lands before the jobs/worker framework exists.
2. **New external dependencies introduced this batch:** `OPENROUTER_API_KEY` env var (media, and TTS fallback); pip: `chatterbox-tts` (verify current package name at install time). Both go in the deployment notes.
3. **RAM budget:** Whisper medium + Chatterbox both resident may exceed the VPS. The worker may need load/unload-per-job. Measure both, record figures, decide, and state the decision in the done report.
4. **Two operator-eared gates in this batch** that Hermes cannot self-certify: the cloned-voice listening test (voice decision, criterion 4) and the publish-preview "does this look like a post" judgment (correction F5, criterion 6 is Hermes's approximation; the operator confirms). Request the operator's review only after everything mechanical passes.
5. Update the changelog and move this manifest to processed when filed.
