# CORRECTION: Final Assembly Engine & Editable Source Materials

**File:** CORRECTION-final-assembly-and-materials-editing-v1.0.md
**Date:** 2026-07-03
**Status:** Approved by operator. Extends CORRECTION-pipeline-ux-and-media-generation-v1.0.md (F4/F5) — media generation produces ingredients; this correction produces the finished dish.
**Depends on:** the shared `jobs` table + worker framework (F1 of the companion correction).

---

## Part 1 — Final Assembly Engine

### The principle

Generated images and clips are ingredients, not deliverables. The system must output **finished, publish-ready content pieces**: cut, sequenced, captioned, overlaid, transitioned, VO-mixed, and paced for virality per the treatment's format. The architecture that achieves this without pretending an LLM can operate a video editor:

**The LLM produces an Edit Plan — a structured timeline spec — and a deterministic renderer executes it.**

This is the existing ViralFactory pattern (LLM proposes structured output → schema validates → deterministic code executes → human gates) applied to editing. Nothing about it is freeform: the Edit Plan is JSON against a schema, validated by the existing validator, logged to provenance, and rendered identically every time.

### The Edit Plan schema (`EDIT_PLAN_SCHEMA`, new in `pipeline.py`)

A timeline of ordered segments plus global tracks:

- **segments[]**: each with `source` (ref to an ingredient: `generated:<media_id>`, `upload:<material_id>`, `stock:<stock_id>`), `in`/`out` trim points (seconds), optional `speed`, optional `transition_in` (from a fixed vocabulary: `cut`, `crossfade`, `slide`, `whip` — the renderer supports exactly what the vocabulary names, nothing else), and per-segment `overlays[]`.
- **overlays[]**: typed — `caption` (text, start, end, style ref), `text_card` (full-frame text beat), `sticker/logo` (asset ref, position), `highlight` (zoom/punch-in on a region). Styles come from a **caption/overlay style sheet derived from the approved Visual Style module** (font, colors, safe areas, position) — the AI picks *which* style and *when*, never invents new styling per render.
- **audio**: `vo` track (asset_media VO take id, with per-segment ducking of other audio), optional `music` (stock audio ref, volume), original clip audio on/off per segment.
- **captions**: burned-in by default for short-form (Format Guide rule), generated from the VO script with word/phrase timing (Whisper alignment on the rendered VO gives timestamps — the transcription worker gains an alignment mode; this is a small extension, faster-whisper returns word timestamps natively).
- **canvas**: aspect ratio, resolution, duration target — taken from the Format Guide's platform adjustment for the target platform, not chosen freely.

### The renderer (`src/assembly.py`, new)

Deterministic, FFmpeg-based. Implementation choice for Hermes: **MoviePy v2** (pip, wraps ffmpeg, handles compositing/text/transitions in Python and keeps the code readable) with direct ffmpeg filter-graph escape hatch where MoviePy is too slow or limited; burned-in captions via ASS subtitles (proper styling control) rather than per-frame drawtext. System dependency: `apt install ffmpeg` on the VPS — now unavoidable and fine.

Rendering runs as an async job on the shared jobs framework (it will take minutes on CPU for 1080p short-form — acceptable, and the busy/status pattern from F1 shows progress states: `planning → rendering → done/failed`). Output lands in `data/media/<asset_id>/final_<version>.mp4`, an `asset_media` row with `kind="final_cut"`, and renders on the publish-preview card (F5) in the platform frame, replacing the raw-ingredient view.

### The edit-plan prompt (`prompts/assembly/edit_plan_v1.md`, new)

Inputs: the treatment and format, the asset's copy/script, the VO take and its duration, the **inventory of available ingredients** (each with id, kind, duration, a one-line content description — for generated media the generation prompt serves; for uploads, the material description; for stock, the search result title), the Viral Patterns module (hook mechanics, pacing rules), the Format Guide entry for the platform, and the Visual Style caption sheet. Output: one Edit Plan. The prompt's standing orders encode the virality mechanics as hard structure: the hook lands inside the first 2 seconds; no segment exceeds N seconds without a visual change (N from Format Guide, default 3); captions on by default; end-card/CTA per the format's convention.

The plan is shown to the operator **as a readable cut list** (plain language: "0:00–0:02 — your clip from the beach walk, caption: '…', hard cut to…") on the preview card before or alongside the render — the operator can regenerate the plan with feedback ("slower pacing", "use my footage for the open, not the generated clip") exactly like draft feedback. Direct authority stays with the human; the renderer never runs on an unseen plan unless the operator has chosen an "auto-render first cut" preference.

### Stock library access (`src/stock_adapter.py`, new)

- **Pexels (primary), Pixabay (secondary)** — both free APIs, photos and video, licenses permit commercial use without attribution. API keys via env (`PEXELS_API_KEY`, `PIXABAY_API_KEY`); config block in `models.yaml` under `stock:` for provider order and defaults.
- The edit-plan flow may request stock: the LLM emits stock *needs* ("aerial Caribbean coastline, 5–8s, vertical") as part of planning; the adapter searches, downloads candidates to `data/media/stock/`, records id, provider, source URL, and license string per item (provenance for media, same discipline as text). Candidate stock appears in the ingredient inventory for the plan's final version; the operator sees which segments are stock in the cut list.
- Cache stock downloads by provider+id; never re-download.
- Music: Pixabay's audio catalog is the starting source for background tracks, same adapter, same license recording. If it proves too thin, that's a future decision, not scope creep now.

### What is explicitly out of scope in v1

No generative video editing (inpainting, object removal), no multi-scene AI continuity management, no timeline GUI editor. The operator's edit lever is feedback on the cut list and regeneration — the same lever they use on drafts. A visual timeline editor is a someday-item, only if cut-list feedback proves insufficient in practice.

---

## Part 2 — Editable Source Materials (the Materials Library)

### The principle

Everything the operator has shared with the system — uploads, transcripts, pasted text — is reviewable and editable, exactly like the living documents. Transcripts contain errors; docx extraction picks up junk; a WhatsApp export includes the other party. The operator must be able to see what the system will actually read, and correct it — because these texts feed the Voice Profile corpus and every drafting package, an uncorrected transcription error becomes a "voice pattern."

### Implementation

1. **Materials page** (`/materials`, linked from the console): lists all materials with filename, type, channel, run association, word count, transcription status, and an excerpt. Filterable by run and channel.
2. **Detail view per material**: shows `normalized_content` (falling back to `raw_content`) in an editable text area. **Save** writes to `normalized_content` — the layer every downstream consumer (corpus, materials summary, drafting package) already reads first — and `raw_content` remains untouched forever as the original. Edits recorded in a `material_edits` log (material id, timestamp, before-hash) — lightweight versioning consistent with the versioned-living-documents principle; full diff history is not required, restore-to-original is (one button: re-copy raw → normalized, or re-run extraction/transcription).
3. **Exclude toggle** per material: an `excluded` flag; excluded materials drop out of corpus, summaries, and drafting packages but are never deleted. This is the "that upload wasn't representative, don't learn from it" control.
4. Audio materials show the transcript as the editable text (post-Whisper) with a "re-transcribe" action; the voice-reference-set clips (voice decision file) show playback, not text editing.
5. All controls obey the F1 busy/idempotency rules; all operator-visible copy is business-owner language.

### Downstream consistency

The content-hash cache means an edited material naturally changes the variables hash on the next drafting call — no cache invalidation machinery needed, but Hermes should add a test proving an edit to a material changes what a subsequent draft call receives.

---

## Acceptance criteria (per PROCESS-definition-of-done-v1.0)

1. End-to-end assembly: a shipped draft with a VO take, one generated image, one operator-uploaded clip, and one stock clip renders to a finished vertical MP4 with burned-in styled captions, at least two transition types, hook inside 2 seconds, VO ducking clip audio — playable on the publish-preview card. Hermes watches the actual output video before declaring done.
2. The cut list is readable by a business owner; feedback ("open with my clip") regenerates a plan that reflects it.
3. Stock search returns candidates, license strings recorded; the rendered piece's provenance lists every ingredient and its source.
4. Render failure (corrupt source clip) surfaces honestly with retry; the job never hangs.
5. Materials page: edit a transcript typo, save, re-run a draft — the corrected text appears in the drafting package (test-verified). Exclude a material — it disappears from the corpus word count. Restore-to-original works.
6. CPU render time for a 30–60s 1080p vertical piece measured and recorded in the done report; if beyond roughly 20 minutes, flag to the operator with options rather than silently accepting.
