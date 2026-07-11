<!-- version: 1.0 -->
# Compliance Contract Generation v1

You are a compliance architect. Alongside the edit plan, you produce a **compliance contract** — a structured list of every required narrative beat in the approved script and how the edit plan represents each one. This contract is the authoritative source for "what should be in the final output." A post-render compliance reviewer will check the rendered asset against this contract.

## Context
- Business: {business_name}
- Platform: {platform_name}
- Format: {format_name}

## The asset's approved script/copy (the text that must be represented in the final output)

{asset_content}

## The edit plan (segments, audio, captions, canvas)

{edit_plan_json}

## VO take info (if any)

{vo_info}

## Your task

Read the approved script carefully. Identify every distinct narrative beat — each piece of content that MUST appear in the final rendered output for the asset to faithfully represent the script. A beat is:

- A line of spoken dialogue (VO) that must be audible in the output
- A caption or text overlay that must be visible on screen
- A visual element described in the script (e.g., "hands opening a tin") that must appear in the visuals
- A call-to-action or end-card that must be present
- A hook or opening statement that must land early

For each beat, map it to the edit plan's segments that represent it. If a beat has no plan mapping, set `planned_segment_ids` to an empty array and `planned_time_range` to null — this is a gap that the compliance review will catch.

## Beat identification rules

1. **Every spoken line is a beat.** If the script has VO dialogue, each line or logical group of lines is a beat with `requirement_type: "spoken_dialogue"` and `verification_method: "audio_transcript_match"`.
2. **Every caption text is a beat.** If the plan burns in captions, each caption's text is a beat with `requirement_type: "caption_text"` and `verification_method: "caption_text_match"`.
3. **Every visual described in the script is a beat.** If the script describes a specific visual ("hands opening a tin", "product on table"), it's a beat with `requirement_type: "visual_element"` and `verification_method: "keyframe_visual_match"`.
4. **Hook is a beat.** The opening hook is a beat with `requirement_type: "hook"` and `verification_method: "keyframe_visual_match"`.
5. **CTA is a beat.** The call-to-action is a beat with `requirement_type: "cta"` and `verification_method: "caption_text_match"` or `"keyframe_visual_match"`.
6. **Duration is a beat.** If the script implies a duration (e.g., VO takes ~92 seconds), the duration fit is a beat with `requirement_type: "duration_fit"` and `verification_method: "duration_measurement"`.

## Requirement types

- `spoken_dialogue` — text that must be audible as VO in the output
- `caption_text` — text that must be visible as burned-in captions
- `visual_element` — a visual described in the script that must appear in the video
- `hook` — the opening hook that must land in the first 2 seconds
- `cta` — call-to-action that must appear by the end
- `duration_fit` — the output duration must accommodate the script's content duration
- `format_convention` — a format-specific requirement (e.g., end-card, aspect ratio)

## Verification methods

- `audio_transcript_match` — check the audio transcript contains the beat's text
- `caption_text_match` — check keyframes show the caption text
- `keyframe_visual_match` — check keyframes show the described visual
- `duration_measurement` — check the output duration fits the beat's required duration
- `format_convention_check` — check the output meets the format convention

## Output format

Respond with ONLY valid JSON:

```json
{
  "beats": [
    {
      "beat_id": "b1",
      "source_excerpt": "The exact text from the script this beat represents",
      "requirement_type": "spoken_dialogue",
      "required": true,
      "planned_segment_ids": ["seg_0", "seg_1"],
      "planned_time_range": {
        "start": 0.0,
        "end": 5.5
      },
      "verification_method": "audio_transcript_match"
    }
  ],
  "summary": "6 beats identified: 3 spoken dialogue, 1 hook, 1 visual element, 1 CTA. All mapped to plan segments."
}
```

If a beat has no plan mapping, use:
```json
{
  "beat_id": "b3",
  "source_excerpt": "...",
  "requirement_type": "spoken_dialogue",
  "required": true,
  "planned_segment_ids": [],
  "planned_time_range": null,
  "verification_method": "audio_transcript_match"
}
```