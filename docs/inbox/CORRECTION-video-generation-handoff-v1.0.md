# CORRECTION — Video Generation → Assembly Handoff

**Version:** v1.0
**Date:** 2026-07-09
**From:** Architect
**Priority:** P0-blocking — the system cannot produce AI-generated video content
**Related review:** `docs/reviews/REVIEW-video-generation-handoff-2026-07-09.md`

---

## Context

The operator asked for a full audit of the video generation → assembly path. The audit found that both routes that submit video generation jobs are broken, the Google/Veo path has 5 independent bugs, and `asset_media` has 0 rows — no AI-generated video has ever been registered as an assembler ingredient. The FFmpeg stitcher itself is solid. The edit-plan prompt is conceptually right. The failure is entirely in the execution layer between "submit job" and "local file registered as ingredient."

**The system can stitch files it has, but it cannot reliably acquire AI-generated video files to stitch.**

---

## Tasks

### VH-1 (P0): Fix `generate-clip` — read `download_url`, call `download_video()`

**File:** `src/app.py:6605`

**Current (broken):**
```python
if status == "completed":
    video_path = poll_result.get("path", "")  # WRONG KEY — returns ""
    media_id = adapter._record_media(asset_id, "video", video_path, ...)  # poisons DB with path=""
```

**Required:** After `check_video_job()` returns `status="completed"`:
1. Read `download_url = poll_result.get("download_url", "")`
2. If empty, return error: "Job completed but no download URL returned"
3. Call `file_path = adapter.download_video(external_job_id, download_url, asset_id, submit_result.get("model", ""), prompt, poll_result.get("cost_usd", 0), business_slug)`
4. `download_video()` handles downloading the file AND calling `_record_media()` — it returns the local file path
5. Return `{status: "ok", path: file_path, ingredient_id: f"generated:{media_id}"}` where `media_id` is the row ID from `_record_media` (called inside `download_video`)

**Note:** `download_video()` at `src/media_adapter.py:510-529` already calls `_record_media` internally. Do NOT call `_record_media` separately — that would double-register. Use the return value of `download_video()` as the file path. The `media_id` needs to be returned from `download_video()` as well (currently it returns only the file path string).

**Additional fix needed:** `download_video()` should return a tuple or dict with both `file_path` and `media_id` so the caller can construct the `ingredient_id`.

**AC:**
- `generate-clip` route, when a video job completes, downloads the file to `data/media/<asset_id>/` and returns a valid `ingredient_id`
- `asset_media` row has a real file path (not `""`)
- The downloaded file exists on disk and is > 1KB
- Test: mock `check_video_job` to return `{status: "completed", download_url: "http://...", cost_usd: 0}`, mock `download_video` to write a real temp file, verify the response contains a valid `path` and `ingredient_id`

### VH-2 (P0): Fix `generate-media` — add poll/download/register loop for AI video jobs

**File:** `src/app.py:6860-6871` (fallback path), `6882-6893` (direct AI video path)

**Current (broken):** After `submit_video()`, sets `status="submitted"` and returns. No polling, no download, no registration.

**Required:** Two options — pick based on the route's UX constraints:

**Option A (synchronous, simpler):** After submitting, poll `check_video_job()` in a loop (5s intervals, max 60 polls = 5min timeout, same as `generate-clip`). On completion, call `download_video()`. On timeout, set `status="processing"` with `external_job_id` so the operator knows to check back. This blocks the HTTP request for up to 5 minutes per video segment, which may be too long if the media plan has multiple AI video items.

**Option B (async, better):** After submitting, write the `external_job_id` to a `video_jobs` table (or reuse the `jobs` table with a new job type). A background poller (systemd service or background thread in the app) checks pending video jobs every 30s, downloads completed ones, and calls `_record_media`. The `generate-media` route returns immediately with `status="submitted"` for each AI video item, and the operator sees a "Video processing — will be ready shortly" status that updates when the background poller completes.

**Recommendation:** Option B is the right architecture, but Option A is the faster fix. If the media plan typically has 1-2 AI video items, Option A with a 5-minute timeout is acceptable. If it can have 5+, Option B is required. Implement Option A now; file Option B as a future enhancement if needed.

**For either option:**
- The `item_result` must include `ingredient_id: "generated:{media_id}"` on success
- On failure, include a plain-language error message (not developer jargon)
- Provenance must log the full cycle: submit → poll → download → register

**AC:**
- After `generate-media` runs for an AI video plan item, `asset_media` has a new row with a real file path
- The file exists on disk and is > 1KB
- The edit planner can see the ingredient as `generated:<id>` in the inventory
- Test: mock the full cycle, verify `asset_media` row is created with a valid path

### VH-3 (P0): Fix Google/Veo — 5 bugs

**File:** `src/media_adapter.py`

1. **Aspect ratio (line 355):** Remove `.replace(":", "x")`. Send `aspect_ratio` as-is. The Veo API expects `"9:16"`, not `"9x16"`.

2. **Response parsing (lines 466-470):** Change from:
   ```python
   result = data.get("response", {})
   generated_samples = result.get("generatedSamples", [])
   ```
   to:
   ```python
   result = data.get("response", {})
   generate_video_response = result.get("generateVideoResponse", {})
   generated_samples = generate_video_response.get("generatedSamples", [])
   ```
   Verify against current Veo API docs — the nesting may differ by model version. Log the raw response to provenance so mismatches are debuggable.

3. **Download URL API key (line 519):** When `video_provider == "google"`, append `?key={api_key}` to the download URL before downloading:
   ```python
   if video_provider == "google" or "googleapis" in download_url:
       api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
       if api_key and "?" not in download_url:
           download_url = download_url + f"?key={api_key}"
   ```
   Also add a sanity check: downloaded file size > 1KB. If smaller, log a warning and treat as failure (Google error blobs are typically a few hundred bytes of JSON).

4. **API key env var (line 345):** Check both `GEMINI_API_KEY` and `GOOGLE_API_KEY`:
   ```python
   api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
   ```

5. **Duration hardcoded (lines 6862, 6884 in app.py):** Read `plan_item.get("duration", 5)` instead of hardcoding 5. If the provider only supports specific durations (e.g., 5/10/15), document the constraint in the media plan prompt.

**AC:**
- A Veo video job can be submitted, polled, downloaded, and registered in `asset_media` end-to-end (with a real `GEMINI_API_KEY`)
- Aspect ratio `9:16` is sent as `9:16` (not `9x16`)
- Downloaded file is > 1KB (not a Google error blob)
- Provenance logs the raw Veo response so response-shape mismatches are debuggable
- Tests: mock the Veo API responses with correct nesting, verify download_url extraction, verify API key appended to download

### VH-4 (P1): Remove 0-byte render files and add output size validation

**File:** `src/assembly.py` (render path), `src/app.py` (render route)

**Current:** Three 0-byte files exist in `data/media/3/` (`final_1.mp4`, `final_2.mp4`, `final_3.mp4`). These are failed renders that produced empty files and were not cleaned up.

**Required:**
1. Delete existing 0-byte `final_*.mp4` files in all `data/media/*/` directories
2. In the render route, after FFmpeg finishes, check the output file size. If size == 0, delete the file, mark the job as failed with a clear error message, and surface the failure to the operator (not a silent "done" status)
3. The job result should not say "done" if the output file is 0 bytes

**AC:**
- No 0-byte `final_*.mp4` files exist in any `data/media/*/` directory
- Render route checks output size and marks job as failed if 0 bytes
- Test: mock a render that produces a 0-byte file, verify the job is marked failed and the file is deleted

### VH-5 (P1): Duration from plan_item, not hardcoded

**File:** `src/app.py:6862`, `6884`

**Current:** Both AI video paths hardcode `duration=5`.

**Required:** Read `plan_item.get("duration", 5)`. The media plan LLM should be able to specify duration. If the configured video provider only supports specific durations, document this in `prompts/assembly/media_plan_v1.md` so the LLM knows the constraint.

**AC:**
- `duration` in the `submit_video` call comes from `plan_item`, not a hardcoded literal
- If the provider doesn't support the requested duration, the error message is clear
- Test: plan_item with `duration=10` results in `submit_video` being called with `duration=10`

### VH-6 (P2): Document current render capability limits in CONTEXT.md

**File:** `docs/CONTEXT.md`

**Required:** Add a "Current Render Capability" section to CONTEXT.md stating:
- The FFmpeg stitcher produces valid MP4s via simple clip concatenation (cut transitions only)
- Transitions (crossfade, slide, whip) are not implemented — planned future enhancement
- Overlays/captions are read for the cut list but not burned into the rendered video
- Audio plan (VO, music, ducking) is not implemented — segments use their own audio streams only
- VO info is a placeholder string — voice pipeline (T2.6-T2.8) is deferred

**AC:** CONTEXT.md has a "Current Render Capability" section that accurately describes what the stitcher does and does not do.