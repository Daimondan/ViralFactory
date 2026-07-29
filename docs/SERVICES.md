# ViralFactory — External Services & API Inventory

> **Living document.** Update when a service is added, removed, or credentials change.
> Last updated: 2026-07-29

---

## Overview

ViralFactory depends on external services for LLM processing, media generation, voice cloning, content publishing, trend research, and infrastructure. All credentials live in environment variables — never in config files or code.

**Secrets are stored in:** `/etc/viralfactory/env` (systemd EnvironmentFile)
**Config references them by:** `api_key_env: "ENV_VAR_NAME"` in `config/models.yaml` and `config/inspiration.yaml`

---

## LLM Backends (content processing, drafting, judgment)

| Service | Purpose | Model(s) | Endpoint | Env Var | Status |
|---------|---------|----------|----------|---------|--------|
| **Ollama Cloud** | Default processing (temp 0), drafting (temp 0.9), ideation, conversation, vision QC | `glm-5.2`, `gpt-oss:120b`, `kimi-k2.6`, `gemma4:31b` (vision) | `https://ollama.com` | `OLLAMA_API_KEY` | ✅ Active |

### LLM Backend Roles (`config/models.yaml` → `active:`)
| Role | Backend | Model | Temperature |
|------|---------|-------|-------------|
| `default` (processing) | `ollama_glm52` | `glm-5.2` | 0 |
| `drafter` (content) | `ollama_glm52_creative` | `glm-5.2` | 0.9 |
| `ideator` (ideas) | `ollama_glm52_creative` | `glm-5.2` | 0.9 |
| `converse` (fast turns) | `ollama_gpt_oss_120b` | `gpt-oss:120b` | 0 |
| Asset review (vision) | `ollama_cloud` | `gemma4:31b` | 0 |

---

## Media Generation (images, video, music)

| Service | Purpose | Model/Endpoint | Env Var | Cost | Status |
|---------|---------|----------------|---------|------|--------|
| **fal.ai** | Image generation (characters, b-roll) + video generation (image-to-video) | `fal-ai/gemini-3.1-flash-image-preview` (nano-banana-2), `fal-ai/flux-2-pro`, `fal-ai/kling-video/v3/standard/image-to-video`, `fal-ai/veo3.1/fast/image-to-video` | `FAL_KEY` | $0.03–0.15/unit | ✅ Active |
| **OpenRouter** | Legacy image generation (non-default named backend) | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | — | ⚠️ Not set (legacy) |
| **xAI (Grok)** | Legacy video generation (non-default named backend) | `grok-imagine-video` @ `https://api.x.ai` | `XAI_API_KEY` | — | ⚠️ Not set (legacy) |
| **Google (Veo)** | Legacy video generation (non-default named backend) | `veo-3.1-fast-generate-preview` @ `https://generativelanguage.googleapis.com` | `GOOGLE_API_KEY` | — | ⚠️ Not set (legacy) |
| **ElevenLabs** | Music beds (licensed, commercial-safe registry tracks) | `eleven-music` | `ELEVENLABS_API_KEY` | — | ✅ Active |
| **Recraft** | Image generation (standalone tool, not pipeline-integrated) | — | `RECRAFT_API_TOKEN` | — | ✅ Active (scripts only) |

### Active Image Generators (config-driven, `config/models.yaml` → `media.image_generators`)
| Name | Endpoint | Best For | Cost/Image |
|------|----------|----------|------------|
| `nano-banana-2` | `fal-ai/gemini-3.1-flash-image-preview` | Recurring characters, identity-critical shots | $0.039 |
| `flux2-pro` | `fal-ai/flux-2-pro` | B-roll, non-character shots, photorealism | $0.03 |

**Default image generator:** `flux2-pro`

### Active Video Generators (config-driven, `config/models.yaml` → `media.video_generators`)
| Name | Endpoint | Mode | Cost/Sec | Clip Len |
|------|----------|------|----------|----------|
| `kling-3` | `fal-ai/kling-video/v3/standard/image-to-video` | image_to_video | $0.10 | 5s |
| `veo-3.1-fast` | `fal-ai/veo3.1/fast/image-to-video` | image_to_video | $0.15 | 5s |

**Default video generator:** `kling-3`

---

## Voice Cloning (VO generation)

| Service | Purpose | Model | Env Var | Status |
|---------|---------|-------|---------|--------|
| **Chatterbox** (self-hosted) | Zero-shot voice cloning for VO — Bajan accent reference | `chatterbox_turbo_tts` (350M, CPU) | None (local, MIT license) | ✅ Active |
| **Gemini TTS** (cloud fallback) | Preset voices only (no cloning) — fallback if Chatterbox unavailable | `gemini-3.1-flash-tts-preview` | `GEMINI_API_KEY` | ⚠️ Not set (fallback) |

**Voice reference:** `modules/stackpenni/voice-samples/penni-bajan-accent-reference.wav` (36s, Bajan strong, operator A/B/C test winner 2026-07-18)

**Architecture note:** Chatterbox runs in a subprocess (`src/vo_subprocess.py`) not in gunicorn — ~900MB RAM, would OOM-kill if in-process. Subprocess timeout = 840s.

---

## Transcription

| Service | Purpose | Model | Status |
|---------|---------|-------|--------|
| **faster-whisper** (self-hosted) | Speech-to-text for uploaded audio/video | `medium`, CPU int8 | ✅ Active |

No external API — runs locally on CPU.

---

## Publishing & Analytics

| Service | Purpose | Endpoint | Env Var | Status |
|---------|---------|----------|---------|--------|
| **Buffer** | Social media publishing (X, Instagram) + post analytics | `https://api.buffer.com` (GraphQL) | `BUFFER_API_KEY` | ✅ Active |

### Buffer Channels
| Platform | Channel ID | Handle |
|----------|-----------|--------|
| X (Twitter) | `6a4169425ab6d2f10680f68e` | @StackPenni |
| Instagram | `6a4168f95ab6d2f10680f598` | @stackwellpennifold |

**Buffer organization ID:** `6a4167fbd0bf4334f895780b`
**Public media URL:** `https://vf.glenbeu.com/media/` (traefik route, no auth, HTTPS — Buffer fetches video/image assets from here)

**API notes:**
- Buffer has **no file upload endpoint** — media is passed as public HTTPS URLs in the `assets` array
- Instagram Reels require `metadata.instagram.type: "reel"` + `metadata.instagram.shouldShareToFeed: true`
- Video thumbnail: `metadata.thumbnailOffset` (milliseconds into video)

---

## Trend Research & Inspiration

| Service | Purpose | Endpoint | Env Var | Status |
|---------|---------|----------|---------|--------|
| **Bundle.social** | Instagram trending audio charts + original sounds | `https://api.bundle.social/api/v1/misc/instagram/audio` | `BUNDLE_SOCIAL_API_KEY` + `BUNDLE_TEAM_ID` | ✅ Active |
| **TikHub** | TikTok Top 50 / Viral 50 audio charts + TikTok video feed + Instagram Reels search | `https://api.tikhub.io` | `TIKHUB_API_KEY` | ✅ Active |
| **Pixabay** | Stock music beds (licensed, commercial-safe) + audio catalog | `https://pixabay.com/api/audio/` | `PIXABAY_API_KEY` | ⚠️ Not set |
| **Pexels** | Stock video/images (free, commercial-safe) | — | `PEXELS_API_KEY` | ⚠️ Not set |

---

## Stock Libraries

| Service | Purpose | Env Var | Status |
|---------|---------|---------|--------|
| **Pexels** | Stock video/images for b-roll | `PEXELS_API_KEY` | ⚠️ Not set |
| **Pixabay** | Stock music beds + audio catalog | `PIXABAY_API_KEY` | ⚠️ Not set |

---

## Infrastructure (self-hosted on VPS)

| Component | Purpose | Technology | Status |
|-----------|---------|------------|--------|
| **Flask app** | Web UI (operator interface, Gates 1–4) | Python + Flask, server-rendered, minimal JS | ✅ Running |
| **Gunicorn** | WSGI server | 2 workers, 900s timeout, port 9121 | ✅ Running (systemd) |
| **SQLite** | Database | `data/viralfactory.db` (~272 MB) | ✅ Active |
| **Traefik** | Reverse proxy + TLS | Docker container, ports 80/443, Let's Encrypt | ✅ Running |
| **Reel Worker** | Async video rendering jobs | Python subprocess, systemd service | ✅ Running (systemd) |
| **Inspiration Collector** | Scheduled trend collection | Python, systemd timer | ✅ Running (systemd) |
| **FFmpeg** | Video encoding, compositing, loudness normalization | System binary | ✅ Installed |
| **PIL/Pillow** | Text overlay rendering (captions, graphics) | Python package | ✅ Installed |
| **faster-whisper** | Audio transcription (CPU int8) | Python package, model: medium | ✅ Installed |
| **Chatterbox TTS** | Voice cloning (CPU, subprocess) | Python package, model: turbo (350M) | ✅ Installed |
| **InsightFace** | Face identity check (ONNX, CPU) | Python package, model: buffalo_l | ✅ Installed |

### systemd Services
| Service | Purpose | Config |
|---------|---------|--------|
| `viralfactory.service` | Flask app (gunicorn) | `/etc/systemd/system/viralfactory.service` |
| `viralfactory-reel-worker.service` | Async reel rendering | `/etc/systemd/system/viralfactory-reel-worker.service` |
| `viralfactory-inspiration-collect.service` | Trend collection | `/etc/systemd/system/viralfactory-inspiration-collect.service` |
| `viralfactory-inspiration-collect.timer` | Scheduled trigger | `/etc/systemd/system/viralfactory-inspiration-collect.timer` |

### Traefik Routes
| Domain | Route | Auth | Purpose |
|--------|-------|------|---------|
| `vf.glenbeu.com` | Main app | Basic auth (`vf-users.txt`) | Operator UI |
| `vf.glenbeu.com/media/` | Media files | **None** (public) | Buffer fetches video/image assets |
| `stackpenni.glenbeu.com` | Source Bank app | None | StackPenni standalone |
| `dashboard.glenbeu.com` | Hermes dashboard | None | Hermes Agent UI |

### Environment File
**Path:** `/etc/viralfactory/env` (systemd EnvironmentFile)

| Variable | Service | Set? |
|----------|---------|------|
| `OLLAMA_API_KEY` | Ollama Cloud (LLM) | ✅ |
| `FAL_KEY` | fal.ai (image/video) | ✅ |
| `ELEVENLABS_API_KEY` | ElevenLabs (music) | ✅ |
| `BUNDLE_SOCIAL_API_KEY` | Bundle.social (trend audio) | ✅ |
| `BUNDLE_TEAM_ID` | Bundle.social (team ID) | ✅ |
| `TIKHUB_API_KEY` | TikHub (TikTok/IG trends) | ✅ |
| `RECRAFT_API_TOKEN` | Recraft (standalone image gen) | ✅ |
| `BUFFER_API_KEY` | Buffer (publishing) | ✅ |
| `GEMINI_API_KEY` | Google Gemini (TTS fallback) | ❌ Not set |
| `GOOGLE_API_KEY` | Google Veo (legacy video) | ❌ Not set |
| `XAI_API_KEY` | xAI Grok (legacy video) | ❌ Not set |
| `OPENROUTER_API_KEY` | OpenRouter (legacy image) | ❌ Not set |
| `PEXELS_API_KEY` | Pexels (stock video) | ❌ Not set |
| `PIXABAY_API_KEY` | Pixabay (stock music) | ❌ Not set |

---

## Summary: What's Active vs What's Configured-But-Unset

### ✅ Active (8 services)
1. **Ollama Cloud** — LLM processing, drafting, vision QC
2. **fal.ai** — Image + video generation
3. **Chatterbox** (self-hosted) — Voice cloning
4. **faster-whisper** (self-hosted) — Transcription
5. **Buffer** — Social media publishing + analytics
6. **Bundle.social** — Instagram trending audio
7. **TikHub** — TikTok/Instagram trend research
8. **ElevenLabs** — Licensed music beds

### ⚠️ Configured but env var not set (6 services — legacy/fallback/optional)
1. **Google Gemini TTS** — voice cloning fallback (Chatterbox is primary)
2. **Google Veo** — legacy video generator (kling-3 is default)
3. **xAI Grok** — legacy video generator (kling-3 is default)
4. **OpenRouter** — legacy image generator (fal.ai is default)
5. **Pexels** — stock video (not yet wired into pipeline)
6. **Pixabay** — stock music (not yet wired into pipeline)

### 🔧 Self-hosted infrastructure (no external API)
1. **Flask + Gunicorn** — web UI
2. **SQLite** — database
3. **Traefik** — reverse proxy + TLS
4. **FFmpeg** — video encoding
5. **PIL/Pillow** — text overlay rendering
6. **InsightFace** — face identity checking