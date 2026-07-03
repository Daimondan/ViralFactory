# DECISION: Voice Cloning & Voiceover Stack

**File:** DECISION-voice-cloning-vo-v1.0.md
**Date:** 2026-07-03
**Status:** Operator-approved direction. Companion to CORRECTION-pipeline-ux-and-media-generation-v1.0.md and DECISION-transcription-whisper-v1.0.md (shared worker framework).

---

## Decision

Voiceover for produced content uses **self-hosted, open-source voice cloning**, with the operator's cloned voice as the default VO voice and a registry that lets the operator select between the cloned voice and stock voices per asset.

**Engine: Chatterbox (Resemble AI).** Rationale:

- **MIT license — commercially safe.** This disqualified the otherwise-obvious pick: XTTS-v2 is under the Coqui Public Model License, which restricts commercial use, and Coqui itself shut down in 2024. Fish Audio's current models are open-weights but require a paid license for commercial self-hosted use. Chatterbox is genuinely permissive.
- **Quality.** In independent blind testing Chatterbox output was preferred over ElevenLabs and is repeatedly cited as the first local model whose cloned output doesn't read as synthetic. Zero-shot cloning from short reference audio — no training run required.
- **Known caveats, accepted:** English-only (fine — the VO is Caribbean-accented English; see verification below). All output carries Resemble's inaudible PerTh watermark — acceptable, arguably useful for AI-disclosure compliance, but the operator should know it's there.
- **Hardware honesty:** Chatterbox comfortably wants a GPU (~4–6 GB VRAM class). On the CPU-only VPS it will be slow. VO generation is asynchronous (same job/worker framework as Whisper transcription and video generation), so slow is tolerable — but Hermes must **measure real-time factor on the VPS** and record it in the done report. If a 60-second VO takes longer than ~15 minutes to render, escalate to the operator with the two sanctioned fallbacks: (a) OpenRouter's TTS endpoint (`/api/v1/audio/speech`) for **stock voices only** as an interim, and (b) a small on-demand GPU box for the voice service later. The cloned voice itself is never sent to a third-party cloning service — that's the line.

**Critical verification (blocking for "done"):** zero-shot cloning quality on Bajan/Caribbean-accented English is unproven until tested on the operator's actual reference clips. The acceptance run is the operator listening to a cloned VO of a real script and judging whether it sounds like him. If Chatterbox flattens the accent, report honestly and evaluate GPT-SoVITS (MIT, few-shot fine-tuning — more setup, better speaker fidelity) as the fallback before considering anything closed.

---

## Voice Reference Set — new onboarding section

Operator directive: the audio already uploaded was for *learning how he writes/speaks* (Voice Profile corpus). Cloning needs its own dedicated, higher-bar input. These are different artifacts and must not be conflated.

1. **A ninth coverage item joins the onboarding thread: `voice-reference-set`.** The orchestrator introduces it in plain language: "Separate from learning how you write — I need your best recordings to clone your voice for voiceovers. Upload your **5 best audio or video clips**: clean single-speaker audio, no music or crosstalk, natural delivery, ideally 30 seconds to a few minutes each. Quality matters far more than quantity here."
2. Uploads to this section are tagged `channel="voice_reference"` in the materials table. Video files get their audio track extracted (PyAV/ffmpeg — same dependency posture as transcription) and stored alongside.
3. The section reaches `ready` when ≥3 usable clips exist (5 requested; 3 is the floor), with basic automated checks: duration, single dominant speaker heuristic optional, but at minimum "is this decodable audio of reasonable length." Coverage chip behaves like the other eight.
4. On approval (Library surface, like all living docs), the system builds the **reference profile**: selected best segments assembled per Chatterbox's reference-input requirements. Store the chosen segments and their source material IDs — provenance for the voice, same as provenance for text.
5. Existing audio already uploaded for the Voice Profile corpus may be *offered* as candidates ("you uploaded these earlier — want any of them in your voice reference set?") but never auto-enrolled.

---

## Voice registry & selection

New `voices` table: `id`, `name`, `kind` (`cloned` | `stock`), `engine` (`chatterbox` | `openrouter_tts`), `reference_ref` (for cloned: pointer to the reference profile), `is_default`.

- Seeded with the operator's clone (default) once the reference set is approved, plus a small curated list of stock voices.
- **Selection UI at the asset/VO stage:** each asset's preview card (F5 of the companion correction) carries a voice dropdown defaulting to the operator's clone; changing it and regenerating produces a new VO take. Takes are kept, not overwritten — the operator compares and picks.
- Future tenants get their own cloned voices through the same registry — nothing StackPenni-specific in the schema (platform-generic principle holds).

---

## VO generation flow

1. VO script: the per-platform asset content is the script source; a light LLM pass (existing adapter, `converse` backend) may adapt written copy to spoken form (contractions, breath points) — shown to the operator as the script before or alongside the audio.
2. Generation is an async job in the shared `jobs` table; the worker loads Chatterbox lazily and keeps it resident (same lifecycle pattern as the Whisper model — note combined RAM budget: Whisper medium + Chatterbox resident simultaneously may not fit; the worker may need load/unload-per-job on the VPS. Measure, decide, record).
3. Output `wav/mp3` stored in `data/media/<asset_id>/vo_<take>.mp3`, row in `asset_media` (`kind="vo"`, voice id, engine). Rendered on the asset preview card with an audio player per take.
4. Hard rule unchanged: VO, like everything else, publishes nowhere without the operator's gate.

---

## Acceptance criteria (per PROCESS-definition-of-done-v1.0)

1. Onboarding thread presents the voice-reference-set section with the plain-language ask; uploading 5 clips (including at least one video whose audio gets extracted) drives the chip to ready; approval in the Library builds the reference profile.
2. Generate a VO on a real asset with the cloned voice: job queues with visible working state, completes, plays on the preview card. Record the measured render time and RTF in the done report.
3. Switch the voice dropdown to a stock voice, regenerate: second take appears alongside the first; both playable and selectable.
4. **Operator listening test:** a cloned VO of a real script, judged by the operator for voice and accent fidelity. This criterion cannot be self-certified by Hermes — it is the one gate in this batch that requires the operator's ear. Everything up to it must be fully working before asking for that ear.
5. Kill-test: corrupt/too-short reference audio produces an honest visible failure, not a hung job.
