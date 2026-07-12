# Architect Note: VO as Master Timeline

**Date:** 2026-07-11  
**Status:** Implemented  
**Related:** `docs/architect/2026-07-11-affordance-based-format-selection.md`

## Problem

The assembler chain generated visuals before generating the voiceover. The media plan was blind to the real runtime — it planned against the script's estimated frame timings (e.g. `[0:00–0:03]`), but the VO came out at 61.5s for a script "estimated" at 42s. The edit plan inherited a 37-second coverage gap it couldn't fix without going back upstream.

## Decision

**VO is sacred. The Reel is as long as the voiceover naturally takes.** Duration is flagged to the human at review, not enforced by the system. The media plan and edit plan are downstream of the VO and sized to it.

## Changes

### 1. Pipeline order: VO before media plan

```
Old: fanout → media plan → media exec → [VO separately] → edit plan → render
New: fanout → VO → media plan → media exec → edit plan → render
```

`produce_chain.py:run_assembler_chain()` now calls `_step_vo()` immediately after fan-out. The VO step generates per-frame TTS, measures real durations, and stores them on the asset row. The media plan stage reads those durations and plans enough visual coverage to fill every frame.

### 2. Per-frame VO generation

`vo_generator.py` has a new `generate_vo_per_frame()` method. Instead of one TTS call for all spoken text, it generates one call per post/frame and measures each segment's duration. Returns:

```json
{
  "take_id": "take_...",
  "segments": [
    {"frame": 1, "path": "...", "duration": 6.2, "text": "..."},
    {"frame": 2, "path": "...", "duration": 12.1, "text": "..."}
  ],
  "total_duration": 61.5,
  "combined_path": "..."
}
```

The combined WAV is also produced for backward compatibility with the existing renderer.

### 3. Media plan sees real VO durations

`prompts/assembly/media_plan_v1.md` (v2.0) receives `{vo_timeline}` and `{coverage_gaps}` as new variables. The prompt instructs the LLM: "The VO defines the real timeline. Every second of VO must have visual coverage. If a stock clip is shorter than the frame's VO duration, plan a supplement."

`app.py` builds these variables from the stored VO segments before calling the media plan LLM.

### 4. Draft stops estimating timestamps

`prompts/draft/generate_v3.md` (v3.2) now says: "Do NOT write timestamps. The VO generation stage measures real durations after the draft is written. Write beats (HOOK, SETUP, PAYOFF, CLOSE) or frame labels, not `[0:00–0:03]` or `[0-2s]`."

The Format Guide Reel skeleton changed from `[0-2s HOOK — visual: ...]` to `HOOK: [visual/spoken entry]`.

### 5. Edit plan receives VO timeline

`prompts/assembly/edit_plan_v1.md` (v1.3) receives `{vo_timeline}` with the instruction: "The canvas duration must equal the total VO duration. Segment timing must align to frame boundaries."

### 6. Duration advisory (non-blocking)

`asset_review.py` has a new `_check_duration_advisory()` method. If VO duration exceeds 60s, it adds a `severity: low, blocking: false, advisory: true` finding. The verdict stays `ready_for_operator`. The human decides whether to ship, trim, or re-record.

### 7. MEDIA_PLAN_SCHEMA relaxed

The `capture_index` field is no longer required (only `generator` is). New optional fields `frame`, `vo_duration`, and `coverage_note` are accepted for v2 media plans.

## Files changed

- `src/vo_generator.py` — `generate_vo_per_frame()`, `_concat_wavs()`, `has_vo_segments_for_asset()`, `has_vo_for_asset()` skips frame segments
- `src/pipeline.py` — `vo_segments` column + migration, `save_vo_segments()`, `get_vo_segments()`, relaxed `MEDIA_PLAN_SCHEMA`
- `src/produce_chain.py` — `_step_vo()` before media plan, stub methods for full chain, updated `_identify_failed_step()`
- `src/app.py` — builds `vo_timeline` and `coverage_gaps` from stored VO segments for media plan prompt
- `src/asset_review.py` — `_check_duration_advisory()` (non-blocking)
- `prompts/assembly/media_plan_v1.md` — v2.0, VO-driven visual coverage
- `prompts/assembly/edit_plan_v1.md` — v1.3, receives `{vo_timeline}`
- `prompts/draft/generate_v3.md` — v3.2, no timestamps
- `modules/stackpenni/format-guide.json` + `.md` — Reel skeleton uses HOOK not [0-2s]
- `tests/test_vo_master_timeline.py` — 11 contract tests
- `tests/test_audio_strategy.py` — version assertion updated
- `tests/test_vo_generator.py` — `has_vo_for_asset` skips frame segments

## Invariants

1. VO generates before media plan — always.
2. Real durations come from TTS, not from the LLM's estimates.
3. Every second of VO must have visual coverage.
4. Duration > 60s is advisory — never blocks.
5. The human decides whether a long Reel ships, trims, or re-records.
6. The combined WAV preserves backward compatibility with the existing renderer.