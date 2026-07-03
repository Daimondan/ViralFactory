# DECISION: Self-Hosted Whisper for Audio Transcription

**File:** DECISION-transcription-whisper-v1.0.md
**Date:** 2026-07-03
**Status:** Operator-approved. Closes the transcription hosting blocker from CORRECTION-session-memory-and-materials-v1.1. Unblocks Voice Profile.
**Repo state reviewed:** commit `372f81e`

---

## Decision

Transcription runs self-hosted on the VPS via **faster-whisper** (the CTranslate2 Whisper implementation), imported in-process. No external API, no per-minute cost, voice data never leaves the operator's infrastructure — consistent with the ownership posture behind the SQLite and Postiz choices.

## Rulings

1. **Library:** `faster-whisper` (pip). CPU inference with `compute_type="int8"` — the Hostinger VPS has no GPU and int8 is the right CPU mode.
2. **Model:** default `medium`, config-driven. Transcription is asynchronous, so fidelity beats speed — and Caribbean-accented English and dialect features are precisely what the smaller models mangle, which would poison the Voice Profile corpus at the source. `medium` int8 needs roughly 1.5 GB RAM while loaded. If the VPS can't carry that alongside the app, drop to `small` with a config edit and note the tradeoff in the changelog. Config block in `models.yaml`:

   ```yaml
   transcription:
     enabled: true
     model: "medium"        # tiny | base | small | medium | large-v3
     compute_type: "int8"
     language: "en"          # hint; Whisper still handles code-switching
   ```

3. **Execution model: background worker, not inline.** A voice note transcribed inside the upload request would time out and block the conversation. One daemon thread, started with the app, polls the materials table for pending audio, processes one file at a time, lazy-loads the model on first job and keeps it resident. No external queue, no new service — SQLite remains the only store (DIVERGENCE-002 holds).

## Implementation

**Schema:** add `transcription_status` to the materials table (`NULL` for non-audio; `pending` / `processing` / `done` / `failed` for audio), set to `pending` at audio ingest. Additive migration; existing rows with the pending marker in `raw_content` are backfilled to `pending` on worker start.

**Worker loop** (`src/transcription.py`, new):
1. Poll every few seconds for the oldest `pending` audio material. Mark `processing`.
2. Locate the file at `upload_dir/material_{id}.{ext}` (already copied there by `ingest_file`).
3. Transcribe with faster-whisper. Write the transcript to `normalized_content`, update `word_count`, set status `done`. Prefix nothing — the transcript is the content; provenance lives in `channel="voice_note"` and `material_type="audio"`.
4. On failure: status `failed`, write a short honest note to `normalized_content` (`[Transcription failed: <reason>]`), log to provenance. Never leave a file stuck in `processing` — wrap in try/finally.
5. Backfill: on startup, queue every audio material whose file exists and whose status is `pending` — this covers the operator's already-uploaded voice notes from today's run without re-upload.

`get_corpus` needs no change beyond its `[Audio` guard: once `normalized_content` holds a real transcript, the existing `normalized_content or raw_content` preference includes it and the word count becomes real. Verify with a test.

**Wiring into the orchestrator flow (depends on P0-1 of CORRECTION-orchestrator-drafting-and-ux-v1.0):**
- `_build_materials_summary` shows audio state honestly: "(transcribing — will be available shortly)" for pending/processing, transcript excerpt once done, failure note if failed. The orchestrator prompt should tell the model it may proceed and that transcripts arrive as the conversation continues.
- Voice Profile v2 corpus includes `done` audio transcripts alongside text materials. If audio exists but none is `done` yet, the draft says so in plain language rather than drafting a voice profile from nothing — and the coverage map should hold voice-profile at `collecting` until at least one transcript (or adequate text corpus) exists.
- When a transcript completes for an active run, no push mechanism is required in this batch: the next orchestrator turn naturally picks it up via the materials summary. A "your voice note finished transcribing" push is a nice-to-have, explicitly out of scope.

**Dependencies:** `pip install faster-whisper`. Decoding of m4a/opus/mp4 containers is handled by PyAV, which faster-whisper pulls in — no system ffmpeg required, but if PyAV fails on any WhatsApp-sourced container in testing, `apt install ffmpeg` and shelling out is the sanctioned fallback.

## Acceptance criteria (per PROCESS-definition-of-done-v1.0)

1. Upload a real voice note (m4a or opus, WhatsApp-style) through the onboarding UI: chip shows upload lifecycle; materials view shows transcribing state; transcript lands in `normalized_content` with correct word count.
2. Previously uploaded pending audio from existing runs transcribes on worker start without re-upload.
3. Voice Profile drafted after transcription completes shows dialect and voice patterns traceable to the spoken content — Hermes listens to (or reads) the source and spot-checks the transcript is substantially faithful.
4. Kill-test: an unreadable/corrupt audio file ends in `failed` with a visible honest message, and the worker continues to the next job.
5. Memory: app + resident medium model stay within VPS RAM with headroom; record the measured figure in the done report. If not, drop to `small`, note it, and re-verify dialect fidelity is still acceptable.
