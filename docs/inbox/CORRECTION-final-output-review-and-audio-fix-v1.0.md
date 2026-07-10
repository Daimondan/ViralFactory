# CORRECTION — Final Output Review Layer + Audio Bed Fix

**Version:** 1.0
**Date:** 2026-07-10
**Architect:** vf-architect
**Scope:** Two problems on the assets/assembly path:
1. **Audio bed logic** produces looping nonsense audio on rendered videos
2. **No final-output review layer** — the renderer marks a video "done" without any AI checking that the output is coherent, captions are present, audio makes sense, and visuals match the content

**Priority:** P0 (audio) + P0 (review layer) — the current rendered output is unusable and there is no guard against shipping incoherent media

---

## Part 1: Audio Bed Fix (P0)

### Root Cause

`src/assembly.py` lines 454–518 implement a "post-concat audio pass" that:

1. Scans segments for video sources that have an audio stream
2. Takes the **first** such source's audio
3. Loops it via `aloop=loop=-1:size=2e9` to fill the entire output duration
4. Mixes it at 0.4 volume under the concat audio

**Why this produces nonsense:**

For asset 2 (draft 3), the edit plan has 6 segments: one 6-second generated video (Veo clip of hands opening a biscuit tin) and five 3-second generated images. The renderer:

- Trims the video to 3s (in=0, out=3.0) — captures only the ambient sound of the tin opening
- Creates 3s silent clips for each image
- Concatenates → 18s total
- Post-concat: extracts the 6s audio from the video source file, loops it to 18s, mixes at 0.4

The result: the operator hears the same 6-second ambient sound clip (tin opening, kitchen ambiance) looped three times across an 18-second video about biscuit tins vs digital wallets. It makes no sense narratively. The edit plan says `audio.original_audio: false` but the code adds original audio anyway.

### The Fix

**Principle: respect the edit plan's audio block. The LLM decided the audio strategy; code must not override it.**

The edit plan schema has an `audio` block:
```json
"audio": {
  "vo": { "take_id": "", "ducking": true },
  "music": { "stock_ref": "stock:123", "volume": 0.3 },
  "original_audio": false
}
```

The renderer currently ignores this entirely and applies its own audio bed heuristic. This is judgment in code — a charter violation.

**Task AUDIO-1: Implement audio-block-driven audio mixing**

The renderer must read `plan["audio"]` and apply it:

| `audio.original_audio` | `audio.music` | Behavior |
|---|---|---|
| `false` | absent | **Silent video.** No audio bed, no looping. Output has a silent AAC track (for player compatibility). |
| `false` | present (`stock:<id>`) | Music only. Resolve the stock audio, trim/loop to output duration, normalize loudness. No clip audio. |
| `true` | absent | Original clip audio only. Each segment keeps its source audio (current concat behavior — no post-pass needed). |
| `true` | present | Original + music. Mix clip audio with music bed at the specified volume. |
| (VO take_id present) | (any) | VO is the primary audio. Duck clip/music under VO. *(VO pipeline deferred — handle gracefully: if no VO file exists for take_id, proceed as if take_id was empty.)* |

**Acceptance criteria:**
- [ ] When `audio.original_audio == false` and no music ref: output video has a silent audio track, no looping ambient sound
- [ ] When `audio.original_audio == true` and no music: output preserves each segment's source audio (no post-concat bed mix)
- [ ] When `audio.music.stock_ref` is present: music track is resolved, trimmed/looped to output duration, mixed at the specified volume
- [ ] The post-concat audio bed heuristic (lines 454–518) is **removed**. It was a workaround, not a design.
- [ ] `audio.vo.take_id` is read but handled gracefully when no VO file exists (deferred pipeline)
- [ ] Provenance log entry for audio mixing decision: "audio strategy: {strategy}, source: {plan audio block}"

**Task AUDIO-2: Update edit_plan_v1.md prompt to clarify audio constraints**

The prompt must tell the LLM:
- If no VO take and no music stock ref are available, set `original_audio: false` → the output will be silent (better than nonsense)
- If the video clip's ambient sound is meaningful (e.g., the sound of the tin opening is part of the storytelling), set `original_audio: true` for that segment's contribution only — but this requires the segment to have audio, which images don't
- Music is the preferred audio layer when available — add a `stock:<id>` for a background track from the stock library
- Be explicit: the renderer will NOT invent audio. What you specify is what plays.

**Acceptance criteria:**
- [ ] Prompt updated with audio strategy guidance
- [ ] Prompt version bumped to 1.2
- [ ] Provenance log records prompt version

---

## Part 2: Final Output Review Layer (P0)

### The Problem

The current pipeline:
1. LLM generates edit plan → saved
2. FFmpeg renders → output file produced → recorded as `final_cut` in `asset_media`
3. **Operator sees the video. That's it.**

There is no check between "render complete" and "operator review" that validates the output is actually coherent. This is unlike the Writer chain, which has a T9.5 AI review loop (self-audit + alignment check) before the draft reaches `draft_ready`.

The operator is asking for the same pattern on the assembly side: **an AI "viewer" that watches the final video / looks at the final image and flags problems before the operator ever sees it.**

### What Can Go Wrong (and currently goes unchecked)

| Failure | Current behavior | With review layer |
|---|---|---|
| Audio loops nonsensically | Operator hears it, has to file a bug | AI flags "audio is looping ambient sound, not coherent with content" |
| Captions not burned in (edit plan says `burned_in: true` but renderer doesn't implement it) | Operator sees a video with no captions, no warning | AI flags "captions specified but not present in output" |
| Video is 0 bytes / corrupt | 0-byte check catches this (VH-4 fix) | Already handled — but AI also verifies playability |
| Visuals don't match content (e.g., an infographic image where a person should be) | Operator spots the mismatch | AI compares final frames to the asset content and flags mismatches |
| Duration mismatch (edit plan says 30s, output is 18s) | Silent | AI flags "output duration differs from plan target" |
| Stale media (image from a previous topic reused) | Operator catches it | AI flags "visual content doesn't match the described scene" |
| Image quality issues (garbled AI art, wrong aspect ratio) | Operator catches it | AI flags visible quality issues |

### Design: The Asset Review Loop

This mirrors the Writer's T9.5 AI review loop. After the renderer produces a final cut, an AI "viewer" inspects the output and either approves it or flags issues. The operator sees the AI's review alongside the video, so they can verify faster.

**Architecture:**

```
Render complete
    ↓
Asset Review Loop (AI viewer)
    ├── Step 1: Mechanical checks (ffprobe, file size, duration match)
    ├── Step 2: Visual inspection (vision-capable LLM examines final frames)
    ├── Step 3: Audio inspection (if audio is present, transcribe + check coherence)
    ├── Step 4: Content alignment (does the video match the asset content/script?)
    ↓
Review verdict: pass | issues_found
    ├── pass → asset stays "rendered", operator sees video + AI review summary
    └── issues_found → operator sees video + flagged issues + recommended actions
```

**Key design decisions:**

1. **Vision-capable LLM for visual inspection.** The system already uses OpenRouter for image generation. A vision model (e.g., `google/gemini-3.1-flash` or similar) can examine extracted frames from the rendered video. The model sees 3-5 keyframes + the asset content and judges: do the visuals match the script?

2. **Audio inspection via transcription.** If the output has an audio stream, extract it, run it through faster-whisper (already configured), and check: does the transcribed audio make sense? Is it looping? Is it silent where it should have speech? This catches the looping audio bug and any future VO issues.

3. **Mechanical checks first, AI second.** Don't waste an LLM call on a 0-byte file. Run ffprobe checks (duration, resolution, stream presence, file size) first. Only if mechanical checks pass does the AI review run.

4. **The review is advisory, not blocking.** The AI review doesn't block the operator from seeing the video. It runs async after render completes and its findings appear alongside the video. The operator is the final gate — the AI review just helps them spot problems faster. This matches the charter: "AI proposes, human gates."

5. **Provenance on every review step.** Each AI review call is logged: input (frames/audio), prompt file + version, model, output (findings), verdict. Same as every other LLM call in the system.

### Task ASSET-REVIEW-1: Mechanical post-render checks

After `renderer.render()` returns, before the response is sent:

```python
# Mechanical checks (no LLM, deterministic)
checks = {
    "file_exists": os.path.exists(output_path),
    "file_size_kb": os.path.getsize(output_path) / 1024,
    "duration_s": probe_duration(output_path),
    "has_video_stream": has_stream(output_path, "video"),
    "has_audio_stream": has_stream(output_path, "audio"),
    "resolution": get_resolution(output_path),
    "sar": get_sar(output_path),
}

# Compare to plan
plan_duration = plan.get("canvas", {}).get("duration_target", 0)
duration_match = abs(checks["duration_s"] - plan_duration) <= 2.0  # 2s tolerance

# Compare to audio block
plan_audio = plan.get("audio", {})
audio_expects_sound = plan_audio.get("original_audio", False) or plan_audio.get("music", {})
audio_has_sound = checks["has_audio_stream"] and not is_silent(output_path)
```

**Acceptance criteria:**
- [ ] Mechanical checks run after every render
- [ ] Results saved to `asset_review` table (new) or `edit_plans.feedback` column
- [ ] Duration mismatch > 2s flagged as a warning
- [ ] Missing audio stream when audio expected → flagged
- [ ] Resolution mismatch with canvas → flagged
- [ ] 0-byte file → already handled by VH-4, but mechanical check is defense in depth

### Task ASSET-REVIEW-2: Vision-based visual inspection

**New prompt file:** `prompts/assembly/asset_review_v1.md`

The prompt receives:
- 3-5 keyframes extracted from the final video (via ffmpeg: `ffmpeg -ss <t> -i final.mp4 -frames:v 1 frame_N.jpg`)
- The asset content (the script/copy)
- The edit plan's segment descriptions and captions
- The visual style guide (for style conformance check)

The LLM is asked to check:
1. **Content alignment:** Do the visuals show what the script describes? (e.g., if the script says "biscuit tin" and the video shows a phone, flag it)
2. **Caption presence:** The edit plan says captions are burned in. Are they visible in the frames? (This catches the known gap where the renderer doesn't burn captions yet)
3. **Visual quality:** Are there obvious AI generation artifacts, garbled text, wrong aspect ratios?
4. **Style conformance:** Do the visuals match the Visual Style Guide (colors, mood, composition)?

**Output schema:**
```json
{
  "verdict": "pass" | "issues_found",
  "issues": [
    {
      "severity": "high" | "medium" | "low",
      "category": "content_mismatch" | "missing_captions" | "quality" | "style",
      "description": "Frame 2 shows a phone but the script describes hands opening a biscuit tin",
      "frame_index": 2,
      "recommended_action": "Regenerate image for segment 2 with a prompt that includes the biscuit tin"
    }
  ],
  "summary": "3 of 5 frames match the script. Frame 2 has a content mismatch. Captions are not visible in any frame."
}
```

**Acceptance criteria:**
- [ ] Keyframes extracted via ffmpeg at 20%, 40%, 60%, 80% of duration (plus first frame)
- [ ] Vision-capable LLM called with keyframes + asset content + plan
- [ ] Results saved to provenance with full input/output
- [ ] Results displayed to operator in the assets UI alongside the video
- [ ] If the vision model is not configured, degrade gracefully (skip visual inspection, note it in the review summary)
- [ ] Prompt file versioned (`asset_review_v1.md`), logged in provenance

### Task ASSET-REVIEW-3: Audio inspection

If the output has an audio stream:

1. Extract audio: `ffmpeg -i final.mp4 -vn -ac 1 -ar 16000 audio_review.wav`
2. Transcribe via faster-whisper (already configured in `models.yaml`)
3. Check coherence:
   - If transcription is empty/inaudible but audio is not silent → flag "audio present but no speech detected — likely ambient/looping"
   - If transcription contains repeated phrases → flag "audio appears to loop"
   - If `audio.original_audio == false` in the plan but audio has content → flag "unexpected audio in output"
   - If transcription matches the asset content/script → pass
4. If audio is silent (all zeros) and `original_audio: false` → expected, pass

**Acceptance criteria:**
- [ ] Audio extracted and transcribed when audio stream present
- [ ] Looping detection: if the same 5+ word phrase appears 3+ times, flag as looping
- [ ] Unexpected audio: if plan says `original_audio: false` and no music ref, but audio has non-silent content → flag
- [ ] Results saved to provenance
- [ ] Graceful degradation if whisper is not available

### Task ASSET-REVIEW-4: Content alignment check

**New prompt file:** `prompts/assembly/asset_alignment_v1.md`

The prompt receives:
- The asset content (full text/script)
- The edit plan (segments, captions, audio strategy)
- The mechanical check results
- The visual inspection results (if available)
- The audio inspection results (if available)

The LLM is asked to judge:
1. Does the final output, as described by the checks, represent a coherent piece of content?
2. Are there any silent failures (plan says X, output shows Y)?
3. Is this ready for the operator to review, or should it be auto-flagged for re-render?

**Output schema:**
```json
{
  "verdict": "ready_for_operator" | "needs_rerender" | "needs_operator_decision",
  "confidence": "high" | "medium" | "low",
  "issues": [
    {
      "severity": "high" | "medium" | "low",
      "description": "Captions specified as burned_in but not detected in any frame",
      "source": "visual_inspection",
      "recommended_action": "Caption burning not yet implemented in renderer — operator should be aware this is a known limitation, not a render bug"
    }
  ],
  "summary": "Video renders correctly but captions are not burned in (known renderer limitation). Audio is silent as specified. Visuals match content in 4 of 5 frames."
}
```

**Acceptance criteria:**
- [ ] Alignment check runs after mechanical + visual + audio checks
- [ ] Results aggregated and saved
- [ ] Operator sees a single "AI Review Summary" panel in the assets UI
- [ ] `needs_rerender` verdict highlights the specific re-render action
- [ ] `ready_for_operator` verdict still shows — the operator is always the final gate

### Task ASSET-REVIEW-5: UI integration

In `src/templates/assets.html`, below the final-cut video player:

**New panel: "AI Review Summary"**

```
┌─────────────────────────────────────────────┐
│ AI Review Summary                           │
│                                             │
│ ✓ Render: 18.1s, 1080×1920, 2.1MB          │
│ ✓ Duration matches plan target (18s)        │
│ ✗ Captions: specified but not detected      │
│   (known limitation — caption burning       │
│   not yet implemented in renderer)          │
│ ✓ Visuals: 4/5 frames match script          │
│   Frame 2 mismatch: shows phone, script     │
│   describes biscuit tin                     │
│ ✓ Audio: silent as specified (no looping)   │
│                                             │
│ Verdict: Ready for your review              │
│                                             │
│ [View detailed review]                      │
└─────────────────────────────────────────────┘
```

**Acceptance criteria:**
- [ ] Review summary appears below the video player in the assets UI
- [ ] Each check has a ✓/✗ indicator
- [ ] Issues are expandable for detail
- [ ] "View detailed review" shows the full AI review JSON (for transparency)
- [ ] If no review has been run yet, show "AI review in progress…" with a poll
- [ ] The panel does not block the operator from approving/fixing/killing — it's advisory
- [ ] Review state visible: `pending` | `running` | `complete` | `failed`
- [ ] No technical jargon — plain language for the operator

### Task ASSET-REVIEW-6: Review for images too

The same pattern applies to standalone generated images (not just rendered videos). When an image is generated for an asset:

1. **Mechanical:** file exists, size > 10KB, correct aspect ratio
2. **Visual:** vision LLM examines the image vs the prompt that generated it — does it match?
3. **Content:** does the image match the asset content (e.g., if the script mentions a biscuit tin, is there a biscuit tin)?

This is lighter-weight (single image, no audio) but catches the "AI generated the wrong thing" problem before the operator sees it.

**Acceptance criteria:**
- [ ] Image generation triggers a lightweight review (1 vision call)
- [ ] Results shown in the media gallery alongside each image
- [ ] Mismatch flagged with the original prompt + what the AI sees

---

## Implementation Order

1. **AUDIO-1** (P0) — fix the audio bed. This is a code fix in `assembly.py`. Stops the looping nonsense immediately.
2. **AUDIO-2** (P0) — update the edit plan prompt so the LLM specifies a coherent audio strategy.
3. **ASSET-REVIEW-1** (P0) — mechanical post-render checks. No LLM needed, deterministic. Catches duration mismatches, missing streams, etc.
4. **ASSET-REVIEW-2** (P0) — vision-based visual inspection. Requires a vision-capable model in `models.yaml`. This is the "human AI" layer the operator is asking for.
5. **ASSET-REVIEW-3** (P1) — audio inspection. Uses existing whisper config. Catches looping/incoherent audio.
6. **ASSET-REVIEW-4** (P1) — content alignment. Aggregates all checks into a single verdict.
7. **ASSET-REVIEW-5** (P0) — UI integration. The operator needs to SEE the review results.
8. **ASSET-REVIEW-6** (P1) — image review. Extends the pattern to standalone images.

## Config Requirements

**New config block in `models.yaml`:**

```yaml
# ── Asset review (AI viewer) ──
# Vision-capable model for inspecting rendered videos and generated images.
# The model receives extracted keyframes + the asset content and judges
# whether the output is coherent before the operator reviews it.
asset_review:
  vision_model: "google/gemini-3.1-flash"  # or any vision-capable model
  vision_provider: "openrouter"
  vision_api_key_env: "OPENROUTER_API_KEY"
  max_keyframes: 5                          # frames extracted per video
  enabled: true                             # set false to skip AI review (mechanical checks still run)
```

This is config-driven — a second business could use a different vision model with zero code changes.

## Charter Compliance

- **No judgment in code:** The audio bed heuristic (lines 454–518) IS judgment in code — it decides to loop ambient audio without the LLM's direction. Removing it and deferring to the edit plan's audio block is charter-compliant.
- **Every LLM call logged:** The asset review loop's vision and alignment calls must go through the LLM adapter with full provenance. No raw API calls.
- **Config-driven:** Vision model, keyframe count, and enabled flag are in `models.yaml`, not hardcoded.
- **Mechanics use boring libraries:** ffprobe for mechanical checks, faster-whisper for audio transcription. No LLM for mechanical work.
- **No patch scripts:** The audio fix is a proper code change to the renderer, not a one-off patch.
- **Per-piece approval:** The AI review is advisory — it does not approve or reject. The operator is always the final gate. This matches "AI proposes, human gates."

## What This Does NOT Do

- Does not auto-re-render on issues found. The operator decides whether to re-render, fix, or kill.
- Does not block the operator from seeing the video. The review runs async and appears alongside.
- Does not replace the operator's judgment. It surfaces problems faster — the operator still makes the call.
- Does not implement caption burning, transitions, or VO mixing. Those are separate tasks. The review layer will flag their absence so the operator knows.

---

## Summary for the Operator

**What you'll see after this lands:**

1. **No more looping audio.** The renderer will respect the edit plan's audio instructions. If the plan says no audio, the video is silent. If it says music, it plays music. No more ambient sound loops.

2. **An AI review panel below every rendered video.** Before you even watch the video, the AI has already checked:
   - Is the file valid? (size, duration, resolution)
   - Do the visuals match the script? (vision model examines keyframes)
   - Does the audio make sense? (transcription + coherence check)
   - Are captions present? (if the plan says they should be)
   - Is this ready for your review, or are there issues to address?

3. **The same pattern for generated images.** Each image gets a quick AI check: does it match what was asked?

4. **You're still the gate.** The AI review is advisory. It surfaces problems faster so you spend less time watching broken videos. But you approve, fix, or kill — always.