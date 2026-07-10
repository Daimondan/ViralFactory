# REVIEW — Video Generation → Assembly Handoff

**Date:** 2026-07-09
**Reviewer:** Architect
**Scope:** End-to-end audit of the video generation → local media → edit plan → FFmpeg assembly path
**Method:** Live code verification against `src/media_adapter.py`, `src/app.py`, `src/assembly.py`, DB inspection, rendered file inspection
**Status:** FINDINGS — 5 P0 bugs, 2 P1 defects, 2 P2 deficiencies

---

## Executive Summary

The system has a working FFmpeg stitcher that can produce valid 1080×1920 H264/AAC MP4s, and the edit-plan prompt gives the LLM the right context. **But no AI-generated video can reliably reach the assembler.** Both routes that submit video generation jobs (`generate-clip` and `generate-media`) are broken in different ways. The Google/Veo path has 5 independent bugs. The `asset_media` table has 0 rows — no generated media has ever been registered as an ingredient. The system has never stitched AI-generated video.

---

## P0 — Blocking Bugs (the handoff is broken)

### P0-1: `generate-clip` reads wrong key, never downloads, poisons `asset_media`

**File:** `src/app.py:6605`
**Code:**
```python
video_path = poll_result.get("path", "")
```

`check_video_job()` returns `{status, download_url, cost_usd}` — there is no `path` key. So `video_path` is always `""`, even when the job completes successfully.

The code then calls:
```python
media_id = adapter._record_media(asset_id, "video", video_path, ...)  # path = ""
```

This inserts a row into `asset_media` with `path=""`. The edit planner would see `generated:<id>` in the ingredient inventory, but the file doesn't exist. The assembler would try to resolve it and fail.

**`download_video()` is never called.** The method exists at `src/media_adapter.py:510-529` and works correctly — it downloads the file and calls `_record_media`. But `generate-clip` doesn't use it.

**Fix:** After `check_video_job` returns `status="completed"`, read `download_url` from the result, call `adapter.download_video(external_job_id, download_url, asset_id, model, prompt, cost_usd, business_slug)`, which returns the local file path. Use that path for the response.

### P0-2: `generate-media` submits and walks away — no poll/download/register loop

**File:** `src/app.py:6860-6871` (fallback path), `6882-6893` (direct AI video path)

After `submit_video()`, both paths set `item_result["status"] = "submitted"` and store `external_job_id`. There is no poll loop, no download, and no `_record_media` call. The job floats indefinitely. The operator sees "submitted" and nothing ever comes back.

**Fix:** After submitting, poll `check_video_job()` in a loop (with timeout), then call `download_video()` on completion, which records the media in `asset_media`. Return `ingredient_id: "generated:{media_id}"` in the result. Alternatively, if synchronous polling is too slow for this route (the LLM media plan may submit multiple jobs), write the `external_job_id` to a jobs-table row and add a background poller that downloads and registers on completion — but the operator must see clear status: "submitted → processing → downloaded (ingredient ready)."

### P0-3: Google/Veo aspect ratio transformation is wrong

**File:** `src/media_adapter.py:355`
**Code:**
```python
"aspectRatio": aspect_ratio.replace(":", "x")
```

This sends `"9x16"` to the Veo API. The Veo API expects `"9:16"` (colon, not x).

**Fix:** Pass `aspect_ratio` directly without transformation. If the upstream format uses `9:16`, send `9:16`.

### P0-4: Google/Veo response parsing misses a nesting level

**File:** `src/media_adapter.py:466-470`
**Code:**
```python
result = data.get("response", {})
generated_samples = result.get("generatedSamples", [])
```

The actual Veo long-running operation response nests the generated samples under `response.generateVideoResponse.generatedSamples`, not `response.generatedSamples`. The code is reading one level too shallow.

**Fix:** Navigate to the correct nesting: `data.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])`. Verify against current Veo API docs — the response shape may vary by model version. Add a provenance log of the raw response so mismatches are debuggable.

### P0-5: Google/Veo video download omits API key

**File:** `src/media_adapter.py:519`
**Code:**
```python
response = requests.get(download_url, timeout=120)
```

Google Veo video URIs (GCS URIs from the Generative Language API) require the API key as a query parameter (`?key=...`) for download. Without it, the response is a tiny error blob, not the MP4. The downloaded file would be garbage, but `response.raise_for_status()` wouldn't catch it because the error comes as a 200 with a small JSON body.

**Fix:** When `video_provider == "google"`, append `?key={api_key}` to the download URL. Verify the downloaded file size is > 1KB as a sanity check before recording.

---

## P1 — Significant Defects

### P1-1: Duration hardcoded to 5 seconds — ignores LLM creative direction

**File:** `src/app.py:6862` (fallback), `6884` (direct AI video)

Both the fallback path and the direct AI video path hardcode `duration=5`:
```python
submit = media_adapter.submit_video(
    prompt=prompt, asset_id=asset_id,
    aspect_ratio="9:16", duration=5,
    ...
)
```

The media plan LLM may write a prompt saying "Cinematic 15-second clip..." but the API call always sends 5. The LLM's creative direction is silently overridden. The `duration` from `plan_item` is never read.

**Charter concern:** This is judgment in code — the LLM decided the duration, code overrides it. Per charter §"No judgment in code," the LLM's plan should be honored.

**Fix:** Read `plan_item.get("duration", 5)` instead of hardcoding 5. If the provider doesn't support arbitrary durations, document the constraint in the media plan prompt so the LLM knows the valid range.

### P1-2: Google API key env var name may be wrong

**File:** `src/media_adapter.py:345`
**Code:**
```python
api_key = os.environ.get("GOOGLE_API_KEY", "")
```

Current Google Veo access via the Generative Language API typically uses `GEMINI_API_KEY`. The env var `GOOGLE_API_KEY` may not be set even if a valid key exists under a different name.

**Fix:** Check both `GEMINI_API_KEY` and `GOOGLE_API_KEY` with fallback. Or standardize on one name and document it in the deployment env file. Confirm which env var name the operator has set.

---

## P2 — Known Deficiencies (not bugs, but limits to document)

### P2-1: VO info is a dead string — no voiceover timing reaches the assembler

**File:** `src/app.py:6325`
```python
"vo_info": "(no VO take yet)"
```

The edit-plan prompt receives a hardcoded placeholder for voiceover info. The assembler cannot time segments to VO or mix audio layers. This is expected — the voice pipeline (T2.6-T2.8) is deferred. But it should be documented as a known limitation, not left as a silent dead string.

### P2-2: FFmpeg stitcher ignores transitions, overlays, captions, audio plan

**File:** `src/assembly.py:414`

The renderer does simple concat (cut transitions only). The edit plan supports `transition_in` (crossfade, slide, whip), `overlays` (captions), and `audio` (VO, music, ducking), but none of these are implemented in the render path. The code is honest about it: "Crossfade/slide/whip are future enhancements."

Overlays/captions are read in `_build_cut_list()` for the human-readable cut list description but not burned into the rendered video.

**Current capability:** basic clip concatenation → valid MP4.
**Not yet capable:** the "finished social video" the edit plan describes.

**Fix:** Document the current render capability explicitly in CONTEXT.md so the operator knows what to expect. Plan future tasks for caption burning (ASS subtitles via FFmpeg), transitions (xfade filter), and audio mixing.

---

## P2+ — Silent Render Failures (0-byte output files)

**File:** `data/media/3/final_1.mp4`, `data/media/3/final_2.mp4`, `data/media/3/final_3.mp4`

Three 0-byte "final" files exist in `data/media/3/`. These are failed renders that produced empty files and were not cleaned up. `final_4.mp4` in the same directory is 852KB and valid.

**Risk:** If anything reads the media directory and serves these as "rendered outputs," the operator sees a broken video player with no error message.

**Fix:** The render route should check output file size after rendering. If size == 0, delete the file, mark the job as failed with a clear error, and surface the failure to the operator. Do not leave 0-byte files as false greens.

---

## What Works (confirmed)

- **FFmpeg stitcher** (`src/assembly.py`): resolves `generated:`, `upload:`, `stock:` refs; rejects `session_upload`; probes streams; handles image→video, audio-only→black+audio, video-only→silent; normalizes to target resolution; adds `setsar=1`; produces valid 1080×1920 H264/AAC MP4s. Verified: `data/media/3/final_4.mp4` — h264, 1080×1920, SAR 1:1, 24.1s.
- **Edit-plan prompt** (`prompts/assembly/edit_plan_v1.md`): explicitly constrains the LLM to listed ingredient IDs, prohibits invented IDs, clarifies in/out are source-file timestamps. Context is comprehensive (business, platform, format, scope, asset content, ingredient inventory, modules).
- **xAI submit path** (`src/media_adapter.py:384-398`): uses `/v1/videos/generations`, `request_id`, `XAI_API_KEY`. Matches test expectations.
- **Media plan prompt** (`prompts/assembly/media_plan_v1.md`): gives the LLM the right context — missing captures, available generators, style modules, platform, format.
- **Stock path** (`src/app.py:6822-6848`): searches, downloads, registers as `asset_media` with `generated:<id>`. This path works end-to-end (if stock returns results).

---

## Architecture Assessment (three layers)

### Layer A — Creative Planning: conceptually right

The media-plan and edit-plan prompts give the LLM the right context. The VO gap is real but expected (voice pipeline deferred). The duration override (P1-1) is a config-vs-prompt disconnect that silently breaks creative direction.

### Layer B — Video Generation Execution: broken

There is no working end-to-end path from "Generate video" to "local MP4 registered in `asset_media`." Both routes are broken:
- `generate-clip`: polls but reads the wrong key, never downloads, poisons `asset_media` with empty paths
- `generate-media`: submits and walks away, no poll/download/register at all
- Google/Veo: 5 separate bugs that each independently prevent it from working
- `asset_media` has 0 rows — confirmed

### Layer C — FFmpeg Stitcher: solid foundation, incomplete creative

Produces valid MP4s. Honest about its limits (transitions/overlays/captions/audio are future work). The 0-byte file issue is a cleanup defect, not a stitcher defect.

---

## Corrective Tasks

See `docs/inbox/CORRECTION-video-generation-handoff-v1.0.md` for the full task list with acceptance criteria. Filed via `MANIFEST-2026-07-09-video-handoff.md`.