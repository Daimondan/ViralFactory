# MANIFEST — 2026-07-03-d (addendum)

Fourth delivery of the day, following manifests -a, -b, -c. Final assembly engine (edit plans → deterministic render), stock library access, and the editable Materials Library.

| File | Destination | Action |
|---|---|---|
| CORRECTION-final-assembly-and-materials-editing-v1.0.md | docs/reviews/CORRECTION-final-assembly-and-materials-editing-v1.0.md | ADD |
| MANIFEST-2026-07-03-d.md | docs/inbox/processed/MANIFEST-2026-07-03-d.md | (move after processing) |

## Notes for Hermes

1. **Sequencing relative to the day's batch:** the Materials Library (Part 2) is independent and can be built any time after the manifest -a P0 fixes — do it early; it's small and the operator needs it to correct transcripts as soon as Whisper lands. The Assembly Engine (Part 1) is the **last** major item in the whole batch: it depends on the jobs framework (-c F1), media generation (-c F4), the publish preview (-c F5), VO takes (-c voice decision), and Whisper word-timestamps (-b, small extension). Do not start assembly before those are green.
2. **New dependencies:** `apt install ffmpeg` (now a hard system dependency); pip `moviepy` (v2); env `PEXELS_API_KEY`, `PIXABAY_API_KEY` (free-tier keys — the operator creates the accounts; request them when reaching the stock adapter, not before).
3. **Whisper extension:** the transcription worker gains an alignment mode returning word timestamps (faster-whisper supports this natively) — used to time burned-in captions against rendered VO. Small, but it lives in the transcription module, so implement it there, not inside assembly.
4. **Amend prior spec:** in -c F5, the publish-preview card's media slot now prefers `kind="final_cut"` when one exists, falling back to raw generated media. One-line change to that spec; noted here rather than reissuing the file.
5. **CPU rendering reality check** is acceptance criterion 6 — measure and report, don't silently accept a 40-minute render.
6. Update the changelog and move this manifest to processed when filed.
