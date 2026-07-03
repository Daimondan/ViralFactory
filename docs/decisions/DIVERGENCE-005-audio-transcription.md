# DIVERGENCE-005: Audio Transcription Implementation

**Date:** 2026-07-03
**Status:** DECISION NEEDED — operator gate required
**Raised by:** Hermes (builder), per CORRECTION-session-memory-and-materials-v1.1 F2c
**Blocks:** Voice Profile playbook (its entire input is voice notes)

## Context

DIVERGENCE-003 approved audio transcription + voice cloning but it was never implemented. The voice-profile-builder session run 24 had 10+ `.mp4` voice notes (WhatsApp format) that were stored as binary garbage — zero words extracted. The Voice Profile playbook is structurally unable to work without transcription.

## Options

### Option A: Self-hosted faster-whisper on VPS
- **Pros:** No per-minute cost, data stays on VPS, DIVERGENCE-003 already approved this path
- **Cons:** CPU-intensive (no GPU on VPS), could be slow for many files, adds a service to maintain
- **Effort:** Medium — install faster-whisper, add a transcription queue/worker, wire to materials intake

### Option B: Hosted Whisper API (OpenAI / Groq)
- **Pros:** Fast, no VPS load, reliable
- **Cons:** Per-minute cost, data leaves the VPS, API dependency
- **Effort:** Small — API call in the ingest path

### Option C: Hybrid — Groq Whisper (free tier) with faster-whisper fallback
- **Pros:** Free for moderate use, fast, fallback for resilience
- **Cons:** Groq has rate limits, two code paths

## Recommendation

Option A (self-hosted faster-whisper) — aligns with DIVERGENCE-003, no recurring cost, data residency kept. The VPS can handle it; voice notes are typically 30s–2min each.

## What's needed from operator

Pick A, B, or C. Then I implement the transcription path: on audio ingest → enqueue → transcribe → update material content → next converse turn picks it up via the materials summary.

## What's shipped now (interim)

- `.mp4`, `.opus`, `.aac`, `.flac` recognized as audio (no longer stored as binary garbage)
- Materials summary tells the AI "transcription pending" so it acknowledges receipt
- The AI will say "I see your voice notes — transcription is being set up" instead of asking what was sent
