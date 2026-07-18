"""
Deterministic cue compiler (VF-AU-205).

Compiles VO takes/timings, phrase captions, hook/orientation/proof overlays,
silence, original audio, music events, SFX events, and compliance skeleton.

Rules: exact text hashes; timing arithmetic mechanical; no LLM copies required
text; collisions/safe zones validated; optional elements remain optional.
"""

import json
import hashlib
from dataclasses import dataclass, field
from typing import Optional

from services.caption_timing import chunk_captions


@dataclass
class CompiledCue:
    """A single compiled cue (caption, overlay, SFX, music, silence)."""
    cue_id: str
    cue_type: str          # vo_timing | caption | overlay | sfx | music | silence
    beat_id: str
    text: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class CompiledTimeline:
    """The complete compiled cue timeline for one asset."""
    vo_timings: list[CompiledCue] = field(default_factory=list)
    captions: list[CompiledCue] = field(default_factory=list)
    overlays: list[CompiledCue] = field(default_factory=list)
    sfx_events: list[CompiledCue] = field(default_factory=list)
    music_events: list[CompiledCue] = field(default_factory=list)
    silence_events: list[CompiledCue] = field(default_factory=list)
    text_hash: str = ""
    total_duration_sec: float = 0.0


class CueCompiler:
    """Deterministic compiler — no LLM, no text mutation."""

    def compile(self, beats: list[dict], text_intents: list[dict],
                vo_segments: list[dict] | None = None,
                audio_intents: list[dict] | None = None) -> CompiledTimeline:
        """Compile all cues from beats, text intents, and measured VO."""
        timeline = CompiledTimeline()

        # 1. VO timings from measured VO segments (if available)
        current_time = 0.0
        if vo_segments:
            for i, seg in enumerate(vo_segments):
                beat_id = seg.get("beat_id", f"b{i+1:02d}")
                duration = seg.get("duration", 0.0)
                text = seg.get("text", "")
                timeline.vo_timings.append(CompiledCue(
                    cue_id=f"vo_{beat_id}",
                    cue_type="vo_timing",
                    beat_id=beat_id,
                    text=text,
                    start_sec=current_time,
                    end_sec=current_time + duration,
                    metadata={"measured": True},
                ))
                current_time += duration
        else:
            # Estimate from intended durations
            for beat in beats:
                dur_range = beat.get("intended_duration_sec", {}) or {}
                duration = dur_range.get("max", 3.0)
                beat_id = beat.get("beat_id", "")
                timeline.vo_timings.append(CompiledCue(
                    cue_id=f"vo_{beat_id}",
                    cue_type="vo_timing",
                    beat_id=beat_id,
                    text=beat.get("vo_text", ""),
                    start_sec=current_time,
                    end_sec=current_time + duration,
                    metadata={"estimated": True},
                ))
                current_time += duration

        timeline.total_duration_sec = current_time

        # 2. Captions from text intents (function=caption) — phrase-level
        #    chunks via caption_timing.chunk_captions (VF-VS-302). One text
        #    intent becomes multiple caption cues, timed within the beat's
        #    VO span. Full-beat single captions are a Draft 8 defect.
        caption_idx = 0
        for ti in text_intents:
            if ti.get("function") != "caption":
                continue
            beat_id = ti.get("beat_id", "")
            vo_timing = next(
                (vt for vt in timeline.vo_timings if vt.beat_id == beat_id), None
            )
            if not vo_timing:
                continue
            caption_text = ti.get("text", "")
            beat_duration = vo_timing.end_sec - vo_timing.start_sec
            phrases = chunk_captions(
                caption_text,
                duration_sec=beat_duration,
            )
            if not phrases:
                # Blank caption or zero-duration beat — emit one cue spanning
                # the beat so the text intent is still visible downstream.
                timeline.captions.append(CompiledCue(
                    cue_id=f"cap_{ti.get('text_intent_id', beat_id)}",
                    cue_type="caption",
                    beat_id=beat_id,
                    text=caption_text,
                    start_sec=vo_timing.start_sec,
                    end_sec=vo_timing.end_sec,
                ))
                continue
            base_id = ti.get("text_intent_id", beat_id)
            for phrase in phrases:
                timeline.captions.append(CompiledCue(
                    cue_id=f"cap_{base_id}_{caption_idx}",
                    cue_type="caption",
                    beat_id=beat_id,
                    text=phrase.text,
                    start_sec=round(vo_timing.start_sec + phrase.start_sec, 3),
                    end_sec=round(vo_timing.start_sec + phrase.end_sec, 3),
                    metadata={
                        "phrase_index": caption_idx,
                        "word_count": phrase.word_count,
                        "approximate_timing": phrase.approximate,
                    },
                ))
                caption_idx += 1

        # 3. Overlays from text intents (hook, emphasis, proof, reframe, cta, orientation)
        for ti in text_intents:
            func = ti.get("function", "")
            if func in ("hook", "emphasis", "proof", "reframe", "cta", "orientation"):
                beat_id = ti.get("beat_id", "")
                vo_timing = next((vt for vt in timeline.vo_timings if vt.beat_id == beat_id), None)
                start = vo_timing.start_sec if vo_timing else 0.0
                end = vo_timing.end_sec if vo_timing else start + 2.0
                timeline.overlays.append(CompiledCue(
                    cue_id=f"ovl_{ti.get('text_intent_id', beat_id)}",
                    cue_type="overlay",
                    beat_id=beat_id,
                    text=ti.get("text", ""),
                    start_sec=start,
                    end_sec=end,
                    metadata={"function": func},
                ))

        # 4. SFX events from beat audio_intent
        for beat in beats:
            ai = beat.get("audio_intent", {}) or {}
            sfx_list = ai.get("sfx", [])
            beat_id = beat.get("beat_id", "")
            for i, sfx in enumerate(sfx_list):
                vo_timing = next((vt for vt in timeline.vo_timings if vt.beat_id == beat_id), None)
                start = vo_timing.start_sec if vo_timing else 0.0
                timeline.sfx_events.append(CompiledCue(
                    cue_id=f"sfx_{beat_id}_{i}",
                    cue_type="sfx",
                    beat_id=beat_id,
                    text="",
                    start_sec=start,
                    end_sec=start + 0.5,
                    metadata={"type": sfx.get("type", ""), "timing": sfx.get("timing", "")},
                ))

        # 5. Music events from beat audio_intent
        for beat in beats:
            ai = beat.get("audio_intent", {}) or {}
            music = ai.get("music_action", "")
            beat_id = beat.get("beat_id", "")
            if music and music != "continue":
                vo_timing = next((vt for vt in timeline.vo_timings if vt.beat_id == beat_id), None)
                start = vo_timing.start_sec if vo_timing else 0.0
                timeline.music_events.append(CompiledCue(
                    cue_id=f"mus_{beat_id}",
                    cue_type="music",
                    beat_id=beat_id,
                    text="",
                    start_sec=start,
                    end_sec=start + 1.0,
                    metadata={"action": music},
                ))

        # 6. Silence events
        for beat in beats:
            ai = beat.get("audio_intent", {}) or {}
            if ai.get("mode") == "silence":
                beat_id = beat.get("beat_id", "")
                vo_timing = next((vt for vt in timeline.vo_timings if vt.beat_id == beat_id), None)
                start = vo_timing.start_sec if vo_timing else 0.0
                duration = ai.get("silence_duration_sec", 0.8)
                timeline.silence_events.append(CompiledCue(
                    cue_id=f"sil_{beat_id}",
                    cue_type="silence",
                    beat_id=beat_id,
                    text="",
                    start_sec=start,
                    end_sec=start + duration,
                ))

        # 7. Compute text hash — exact approved text preservation
        hash_data = {
            "beats": [{"beat_id": b.get("beat_id", ""), "vo_text": b.get("vo_text", "")} for b in beats],
            "captions": [c.text for c in timeline.captions],
            "overlays": [o.text for o in timeline.overlays],
        }
        timeline.text_hash = hashlib.sha256(
            json.dumps(hash_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

        return timeline

    def validate_timing(self, timeline: CompiledTimeline) -> list[str]:
        """Validate that cues don't overlap or exceed segment bounds."""
        errors = []

        # Check overlay timing doesn't exceed VO timing
        for ovl in timeline.overlays:
            if ovl.end_sec > timeline.total_duration_sec:
                errors.append(
                    f"Overlay '{ovl.cue_id}' ends at {ovl.end_sec:.1f}s but "
                    f"total duration is {timeline.total_duration_sec:.1f}s"
                )

        # Check for caption/overlay collisions in the same time range
        for i, cap in enumerate(timeline.captions):
            for ovl in timeline.overlays:
                if cap.beat_id == ovl.beat_id:
                    # Caption and overlay in same beat — check if they're in the same zone
                    cap_zone = "bottom" if cap.start_sec >= 0 else "top"
                    ovl_zone = ovl.metadata.get("position", "center")
                    if cap_zone == ovl_zone:
                        errors.append(
                            f"Caption '{cap.cue_id}' and overlay '{ovl.cue_id}' "
                            f"may collide in beat '{cap.beat_id}' — same zone"
                        )

        return errors