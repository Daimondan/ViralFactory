# MANIFEST — 2026-07-03-b (addendum)

Follows MANIFEST-2026-07-03 in the same batch. The operator approved self-hosted Whisper, closing the transcription hosting blocker.

| File | Destination | Action |
|---|---|---|
| DECISION-transcription-whisper-v1.0.md | docs/decisions/DECISION-transcription-whisper-v1.0.md | ADD |
| MANIFEST-2026-07-03-b.md | docs/inbox/processed/MANIFEST-2026-07-03-b.md | (move after processing) |

## Notes for Hermes

1. **Sequencing:** implement the transcription worker after P0-1/P0-2 of CORRECTION-orchestrator-drafting-and-ux-v1.0 (it plugs into the drafting input package) but it can be built in parallel — the worker itself has no dependency on the orchestrator changes, only its wiring into the materials summary and Voice Profile corpus does.
2. This decision supersedes the "hard-blocking stub" status of audio transcription noted in CORRECTION-session-memory-and-materials-v1.1. Update the changelog accordingly.
3. Voice Profile end-to-end (the operator's audio-heavy use case) becomes fully testable only when both this and P0-1 land — treat that combined path as the acceptance run.
