# DIVERGENCE-003 — Audio transcription + voice cloning (R6 + operator direction)

*Repo location: `docs/decisions/DIVERGENCE-003-audio-transcription-voice-cloning.md` · Proposed by operator (Daimon), 2026-07-02 · Status: APPROVED by operator — Hermes implements in M2*

## Context

Architect review R6 (review-w1_1.md) flagged that T1.2 AC ("audio (transcribed) all ingest") is not met — audio files are stored with a "transcription pending" stub. The architect offered two options: implement local Whisper in M2, or defer to T3.1 with a divergence entry.

The operator directed: implement in M2, AND add open-source voice cloning so the system can produce audio in the person's own voice.

## What changes

### 1. Audio transcription (R6 fix)

**Tool:** faster-whisper (CTranslate2-based Whisper reimplementation)
- 4x faster than original Whisper, same quality
- Runs on CPU (our VPS has no GPU); int8 quantization on CPU is usable for offline batch transcription of short voice notes
- Model name in `config/models.yaml` under a `transcription` block — no hardcoding
- Audio files uploaded during intake are transcribed and the text replaces the "transcription pending" stub

**VPS constraints:** 8 GB RAM, 2 CPU cores, no GPU. Use the `small` or `base` model with int8 quantization. A 30-second voice note transcribes in seconds. This is batch, not real-time — acceptable for onboarding and seed intake.

**Config block:**
```yaml
transcription:
  engine: "faster_whisper"
  model: "small"       # tiny | base | small | medium | large-v3
  compute_type: "int8" # CPU-only VPS
  language: "en"       # can be "auto" for auto-detect
```

### 2. Voice cloning (operator addition)

**Tool:** Open-source voice cloning model, self-hosted, Apache 2.0 licensed (commercially usable)

**Candidate models (all Apache 2.0, all support zero-shot voice cloning from a few seconds of reference audio):**

| Model | License | Cloning | Notes |
|---|---|---|---|
| **Qwen3-TTS** | Apache 2.0 | 3-second zero-shot | 1.7B params, 101ms first-packet latency, multilingual, voice design + cloning |
| **MOSS-TTS v1.5** | Apache 2.0 | Zero-shot, long-reference | 48kHz stereo, stable cloning, multilingual, vLLM-Omni serving |
| **VoxFlash-TTS** | Apache 2.0 | Zero-shot, Chinese + English | Fastest inference, ~600MB ONNX, consumer GPU, edge-deployable |

**Selection:** Qwen3-TTS is the primary candidate — Apache 2.0 (commercially safe for paying customers), 3-second cloning, multilingual, and the VoiceDesign variant supports both cloning and custom voice design. Final selection after a smoke test on the VPS.

**NOT selected:** XTTS-v2 / Coqui TTS — CPML license is non-commercial. Coqui org shut down January 2024; no commercial license can be purchased. Ruled out for a product with paying customers.

**How it fits the system:**
- During onboarding, the person's voice samples (uploaded audio, interview answers) become the reference audio for voice cloning
- When the system produces content, it can generate an audio version (e.g., a reel voiceover, an X audio post) in the person's cloned voice
- This is an OUTPUT capability, not an input — transcription is input (speech→text), voice cloning is output (text→speech in the person's voice)
- Model name and settings in `config/models.yaml` under a `voice_cloning` block — no hardcoding

**Config block:**
```yaml
voice_cloning:
  engine: "qwen3_tts"        # qwen3_tts | moss_tts | voxflash_tts
  model: "Qwen3-TTS-12Hz-1.7B-VoiceDesign"
  reference_audio_dir: "modules/{business}/voice-samples/"
  sample_rate: 24000
```

### 3. BUILD_PLAN impact

- T2.6 (new): Audio transcription — wire faster-whisper into MaterialsIntake; audio files transcribed on upload; model from config. AC: a 30-second voice note uploaded through the console produces transcribed text in the materials store.
- T2.7 (new): Voice cloning adapter — `synthesize(text, reference_audio) -> audio_file`; model from config; reference audio from the business's voice-samples directory. AC: given reference audio clips, the adapter produces an audio file of the text spoken in that voice.
- T2.8 (new): Voice sample management — store reference audio clips during onboarding (from uploaded materials + interview); clips stored per-business in `modules/{business}/voice-samples/`. AC: at least 3 reference clips stored after onboarding; clips usable by the voice cloning adapter.

### 4. Charter impact

This is a capability addition, not a charter amendment. The charter already says:
- "Voice available everywhere, assumed nowhere" (interaction principle)
- "Real footage anchors visual trust" (content design rule) — voice cloning extends this to audio: the person's real voice anchors audio trust
- Nothing business-specific in code — model names in config (already the pattern)

No charter text changes. The `transcription` and `voice_cloning` config blocks follow the existing "all values in config" rule.

### 5. VPS resource note

The VPS has 8 GB RAM, 2 CPU cores, no GPU. faster-whisper with the `small` model + int8 uses ~4 GB RAM and transcribes a 30-second clip in seconds — fine for batch.

Voice cloning models are larger (1.7B params). Qwen3-TTS on CPU will be slow (not real-time). This is acceptable for the current use case: generating a voiceover for a reel or audio post is a batch operation, not interactive. If GPU is needed later, the adapter's backend is swappable via config — same pattern as the LLM adapter.

### 6. What is explicitly NOT approved

- No cloud TTS / transcription APIs (OpenAI, ElevenLabs, AssemblyAI) — self-hosted only, same data-sovereignty principle as the rest of the system
- No auto-generating audio for every piece — audio is opt-in per piece, like visual assets
- No voice cloning without the person's explicit reference audio — no synthetic default voices
- No XTTS-v2 or any non-commercial-licensed model — paying customers are a near-term plan