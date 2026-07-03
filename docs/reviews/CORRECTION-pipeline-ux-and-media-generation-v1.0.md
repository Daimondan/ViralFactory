# CORRECTION: Pipeline UX & Media Generation

**File:** CORRECTION-pipeline-ux-and-media-generation-v1.0.md
**Date:** 2026-07-03
**Repo state reviewed:** commit `372f81e`
**Status:** Approved by operator. Companion to DECISION-voice-cloning-vo-v1.0.md (same batch).

---

## F1 (P0): Busy states everywhere + server-side idempotency

### Diagnosis

Only `ideas.html` styles a `:disabled` button and only the onboarding send button ever disables. Every other action in the system — Ship forward, Revise, Send feedback, fan-out, analyze, store — is a bare `onclick` with no pending indication. The operator cannot tell the system is working, clicks again, and each click fires another full LLM call server-side. The content-hash cache dedupes identical *completed* calls but does nothing about two identical calls in flight simultaneously.

### Fix — both halves are required

**Client (shared, not per-page):** one small shared JS helper (`static/busy.js`, included by every template) wrapping all action calls: on invoke, the triggering button disables and its label swaps to a working state ("Generating…", "Storing…", with spinner); on completion or error it restores. Long-running actions (draft generation, fan-out, media jobs) additionally show an inline status line near the affected content. No action button in the system may remain clickable while its request is in flight — this is a blanket rule, verified surface-by-surface in the human UI test.

**Server:** an in-flight guard for every expensive endpoint (draft generate, asset fan-out, onboarding message, all analyze endpoints, media generation). Implementation: a `jobs` table in SQLite (`job_key`, `status`, `started_at`, `result_ref`) where `job_key` is derived from endpoint + entity id (+ input hash where inputs vary). A request arriving while a matching job is `running` does not fire a second LLM call — it returns HTTP 409 with the running job's status, and the client shows "already working on it." Stale `running` jobs older than a timeout are treated as dead and may be retried. This table is the same substrate the media/VO workers (F4, and the voice decision file) use for their async jobs — build it once.

---

## F2 (P1): Self-audit flags become actionable

### Diagnosis

The Tells Checklist self-audit renders each flag (line, rule, suggestion) as read-only decoration. There is no endpoint and no control to accept a suggestion into the draft text — the operator can see the AI caught its own tell and can do nothing about it except retype the draft by hand.

### Fix

Each flag gains **Apply** and **Dismiss**:
- **Apply** replaces the flagged line in `draft_text` with the suggestion, recorded as a **direct edit** (the existing highest-weight feedback class), bumping the draft version. Matching is exact-string against the flagged line; if the line no longer exists (already edited), the flag shows "line changed — review manually" instead of silently failing.
- **Dismiss** records the dismissal (flag + rule) so repeated dismissals of the same rule become signal for voice-profile refinement later; the flag collapses.
- **Apply all remaining** convenience button at the top of the flag list.
- Applied/dismissed state persists with the draft; a reload shows resolved flags as such.
- New endpoint `POST /api/draft/<draft_id>/audit-flag` with `{index, action}`; both actions respect F1 busy/idempotency rules.

---

## F3 (P1): Visual direction must actually exist, and must render

### Diagnosis

`DRAFT_SCHEMA` requires the `visual_direction` object but permits all three arrays inside it (`image_prompts`, `reference_notes`, `shot_format_choices`) to be empty; the template hides empty sections. The model can lawfully return nothing and the page lawfully shows nothing — which is what the operator saw.

### Fix

1. Schema: `image_prompts` and `shot_format_choices` get `minItems: 1` (validator must support minItems if it doesn't yet — add it). `reference_notes` may be empty.
2. `prompts/draft/generate_v1.md` → v2: visual direction is elevated from an afterthought to a required deliverable — concrete, shot-by-shot or image-by-image, written against the approved Visual Style module and the treatment's format (a talking-head reel gets shot/beat direction; a carousel gets per-slide image prompts). Image prompts must be generation-ready: subject, composition, style anchors from the Visual Style module, aspect ratio for the primary platform.
3. Template: the Visual Direction section always renders on the draft page; a legacy draft with an empty one shows "No visual direction on this draft — regenerate to produce one," never a silent blank.

---

## F4 (P0 for the operator's end-to-end): Media generation via OpenRouter

### Decision context

Operator directive: connect OpenRouter so the AI can generate the images and video the content needs. Verified against OpenRouter's current APIs (July 2026): a dedicated Image API (`POST /api/v1/images`, 30+ models including GPT Image 2, Gemini 3.1 Flash Image / Nano Banana 2, Seedream 4.5, FLUX; supports reference images and per-model discovery via `/api/v1/images/models`) and an asynchronous Video API (`POST /api/v1/videos` → job ID → poll → download; models include Veo 3.1 / Fast / Lite, Sora 2 Pro, Seedance, Kling, Wan; discovery via `/api/v1/videos/models`). Auth is a single `OPENROUTER_API_KEY` bearer token.

Note the ownership tradeoff explicitly in the changelog: unlike Whisper and the voice stack, media generation is a cloud dependency and prompts/outputs transit OpenRouter. Operator-accepted.

### Implementation

**New `src/media_adapter.py`**, mirroring `llm_adapter` discipline exactly: config-driven model selection, every call logged to provenance (including USD cost — the API returns it), content-hash caching for images (same prompt + model = cached file), backend always flows through a `backend` parameter (the BYO-AI forward-compatibility rule applies to media too).

**Config** (`models.yaml`):

```yaml
media:
  image_default: "google/gemini-3.1-flash-image"   # swap = config edit
  video_default: "google/veo-3.1-lite"             # cheap tier first; upgrade per-treatment later
  base_url: "https://openrouter.ai/api/v1"
```

Model choice is deliberately the cheap-and-good tier to start — Veo 3.1 Lite does 720p/1080p with native audio in 9:16 and 16:9 at less than half the cost of Fast; graduate per-format once the Format Guide's outward loop says a format earns it. The `/images/models` and `/videos/models` discovery endpoints should be fetched and cached so validation errors (unsupported aspect ratio, duration) are caught before spending money.

**Image generation is synchronous-ish** (seconds): runs behind the F1 busy state directly. **Video generation is an async job**: submit, store the job ID in the `jobs` table (F1), and the background worker (same framework as the Whisper worker) polls at a sane interval until complete, then downloads the file. Generated media lands in `data/media/<asset_id>/`, recorded in a new `asset_media` table (`asset_id`, `kind`, `path`, `model`, `prompt`, `cost_usd`, `created_at`).

**Where it hooks in:** each platform asset (post fan-out) gets a **Generate visuals** action that consumes that asset's `image_prompts` (from fan-out) and the draft's `visual_direction`. Video generation is per-treatment and operator-triggered (a button, not automatic — video costs real money per clip; the no-surprise-spend rule is: image generation may run automatically as part of Generate visuals, video generation always requires an explicit click showing the model and estimated cost first).

Failures are shown honestly on the asset card with a retry, never silently swallowed (the current fan-out loop's bare `continue` on exception is exactly the anti-pattern — fix that too while in the file: a failed platform variant must surface as failed).

---

## F5 (P1): Assets page becomes a publish preview

### Diagnosis

The assets page renders variant text as a plain dump. No visuals, no platform framing — the operator cannot judge "is this ready to publish" because it doesn't look like anything that would be published.

### Fix

Each platform variant renders as a **preview card approximating the destination**: correct aspect-ratio media frame (9:16, 1:1, 16:9 per Format Guide platform adjustments) showing the generated image/video (or an honest "no visuals generated yet" placeholder with the Generate visuals button), handle and platform label, caption/copy laid out below the media the way that platform shows it, character count against the platform limit, and the VO section (script + audio player) when VO exists (see voice decision file). The Gate 3 controls sit on this preview — the operator gates what the audience would actually see. Pixel-faithful platform chrome is explicitly not required; a recognizable approximation is. Operator-visible copy stays business-owner language.

---

## Acceptance criteria (per PROCESS-definition-of-done-v1.0)

1. Rapid-double-click every action button in the system: exactly one LLM/media call fires (verify via provenance log), and the button visibly shows a working state.
2. On a fresh draft: self-audit flags appear with Apply/Dismiss; Apply visibly rewrites the line, bumps the version, and survives reload.
3. Every new draft has non-empty visual direction rendered on the page; validation rejects a draft output without it.
4. Generate visuals on an asset produces a real image file, rendered inside the correct aspect-ratio frame on the preview card; cost appears in provenance.
5. Trigger one video generation end to end: explicit confirmation with cost shown → job queued → worker completes → video playable on the preview card. Force one failure (invalid duration for the model) and confirm it surfaces with retry.
6. Assets page for a shipped draft looks like a set of platform posts, not a text dump — judged by the human UI test at desktop and mobile widths.
