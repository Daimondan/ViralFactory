"""Tests for VF-AU-205: Deterministic cue compiler."""

import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from services.cue_compiler import CueCompiler, CompiledTimeline


def _make_beat(beat_id="b01", **kw):
    base = {"beat_id": beat_id, "vo_text": "The eighth wonder", "audio_intent": {"mode": "vo_only"}}
    base.update(kw)
    return base


class TestVOCompilation:
    def test_vo_timings_from_measured_segments(self):
        beats = [_make_beat("b01"), _make_beat("b02", vo_text="Start now")]
        vo_segments = [
            {"beat_id": "b01", "duration": 3.5, "text": "The eighth wonder"},
            {"beat_id": "b02", "duration": 2.0, "text": "Start now"},
        ]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, [], vo_segments=vo_segments)
        assert len(timeline.vo_timings) == 2
        assert timeline.vo_timings[0].start_sec == 0.0
        assert timeline.vo_timings[0].end_sec == 3.5
        assert timeline.vo_timings[1].start_sec == 3.5
        assert timeline.vo_timings[1].end_sec == 5.5
        assert timeline.total_duration_sec == 5.5
        assert timeline.vo_timings[0].metadata.get("measured") is True

    def test_vo_timings_estimated_when_no_segments(self):
        beats = [_make_beat("b01", intended_duration_sec={"min": 2, "max": 4})]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, [])
        assert len(timeline.vo_timings) == 1
        assert timeline.vo_timings[0].metadata.get("estimated") is True
        assert timeline.vo_timings[0].end_sec == 4.0


class TestCaptionCompilation:
    def test_caption_from_text_intent(self):
        beats = [_make_beat("b01")]
        text_intents = [{"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": "Eighth wonder"}]
        vo_segments = [{"beat_id": "b01", "duration": 3.0, "text": "The eighth wonder"}]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)
        assert len(timeline.captions) == 1
        assert timeline.captions[0].text == "Eighth wonder"
        assert timeline.captions[0].start_sec == 0.0
        assert timeline.captions[0].end_sec == 3.0

    def test_non_caption_text_intents_become_overlays(self):
        beats = [_make_beat("b01")]
        text_intents = [
            {"text_intent_id": "t01", "beat_id": "b01", "function": "hook", "text": "WONDER"},
            {"text_intent_id": "t02", "beat_id": "b01", "function": "cta", "text": "Save this"},
        ]
        vo_segments = [{"beat_id": "b01", "duration": 3.0, "text": "The eighth wonder"}]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)
        assert len(timeline.overlays) == 2
        assert timeline.overlays[0].metadata["function"] == "hook"
        assert timeline.overlays[1].metadata["function"] == "cta"


class TestTextHash:
    def test_hash_is_deterministic(self):
        beats = [_make_beat("b01")]
        compiler = CueCompiler()
        t1 = compiler.compile(beats, [])
        t2 = compiler.compile(beats, [])
        assert t1.text_hash == t2.text_hash

    def test_hash_changes_when_vo_text_changes(self):
        compiler = CueCompiler()
        t1 = compiler.compile([_make_beat("b01", vo_text="A")], [])
        t2 = compiler.compile([_make_beat("b01", vo_text="B")], [])
        assert t1.text_hash != t2.text_hash

    def test_hash_changes_when_caption_text_changes(self):
        compiler = CueCompiler()
        beats = [_make_beat("b01")]
        vo = [{"beat_id": "b01", "duration": 3.0, "text": "x"}]
        t1 = compiler.compile(beats, [{"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": "A"}], vo_segments=vo)
        t2 = compiler.compile(beats, [{"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": "B"}], vo_segments=vo)
        assert t1.text_hash != t2.text_hash


class TestSFXAndMusic:
    def test_sfx_events_from_audio_intent(self):
        beats = [_make_beat("b01", audio_intent={"mode": "vo_only", "sfx": [{"type": "pop", "timing": "on_text_appear"}]})]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, [], vo_segments=[{"beat_id": "b01", "duration": 3.0, "text": "x"}])
        assert len(timeline.sfx_events) == 1
        assert timeline.sfx_events[0].metadata["type"] == "pop"

    def test_music_events_from_audio_intent(self):
        beats = [_make_beat("b01", audio_intent={"mode": "vo_plus_music", "music_action": "duck"})]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, [], vo_segments=[{"beat_id": "b01", "duration": 3.0, "text": "x"}])
        assert len(timeline.music_events) == 1
        assert timeline.music_events[0].metadata["action"] == "duck"

    def test_silence_events(self):
        beats = [_make_beat("b01", audio_intent={"mode": "silence", "silence_duration_sec": 1.5})]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, [], vo_segments=[{"beat_id": "b01", "duration": 3.0, "text": "x"}])
        assert len(timeline.silence_events) == 1
        assert timeline.silence_events[0].end_sec - timeline.silence_events[0].start_sec == 1.5


class TestTimingValidation:
    def test_overlay_exceeding_duration_flagged(self):
        compiler = CueCompiler()
        timeline = CompiledTimeline(total_duration_sec=3.0)
        timeline.overlays.append(type(timeline.overlays)() if timeline.overlays else None)
        # Directly test validate_timing with a bad overlay
        from services.cue_compiler import CompiledCue
        timeline.overlays = [CompiledCue(cue_id="ovl_bad", cue_type="overlay", beat_id="b01", text="x", start_sec=0, end_sec=5.0)]
        errors = compiler.validate_timing(timeline)
        assert any("exceeds" in e.lower() or "duration" in e.lower() for e in errors)

    def test_valid_timeline_no_errors(self):
        beats = [_make_beat("b01")]
        compiler = CueCompiler()
        timeline = compiler.compile(beats, [], vo_segments=[{"beat_id": "b01", "duration": 3.0, "text": "x"}])
        errors = compiler.validate_timing(timeline)
        assert errors == []