"""VF-VS-302 — cue compiler produces phrase-level captions via caption_timing.

AC: cue compiler produces multiple caption cues per beat, not one
full-beat caption.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from services.cue_compiler import CueCompiler  # noqa: E402


def _make_beat(beat_id="b01", audio_mode="vo_only"):
    return {
        "beat_id": beat_id,
        "vo_text": "",
        "audio_intent": {"mode": audio_mode},
    }


def test_long_caption_produces_multiple_phrase_cues():
    """A caption longer than 6 words must split into multiple cues."""
    beats = [_make_beat("b01")]
    long_caption = "We built a thing that turned into something much bigger than we planned"
    text_intents = [
        {
            "text_intent_id": "t01",
            "beat_id": "b01",
            "function": "caption",
            "text": long_caption,
        }
    ]
    vo_segments = [{"beat_id": "b01", "duration": 12.0, "text": long_caption}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    assert len(timeline.captions) > 1, (
        "Long caption must produce multiple phrase cues, not one full-beat caption"
    )
    # Reconstruction: joining phrase texts equals the normalized original
    reconstructed = " ".join(c.text for c in timeline.captions)
    assert reconstructed == " ".join(long_caption.split())


def test_phrase_cues_stay_within_beat_vo_span():
    """Every phrase cue's start/end must lie within the beat's VO timing."""
    beats = [_make_beat("b01")]
    caption = "We built a thing that turned into something much bigger"
    text_intents = [
        {"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": caption}
    ]
    vo_segments = [{"beat_id": "b01", "duration": 10.0, "text": caption}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    vo = timeline.vo_timings[0]
    for cap in timeline.captions:
        assert cap.start_sec >= vo.start_sec - 0.001
        assert cap.end_sec <= vo.end_sec + 0.001
        assert cap.end_sec > cap.start_sec


def test_phrase_cues_contiguous_no_gaps_overlaps():
    """Within a beat, phrase cues should be contiguous (proportional mode)."""
    beats = [_make_beat("b01")]
    caption = "One two three four five six seven eight nine ten"
    text_intents = [
        {"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": caption}
    ]
    vo_segments = [{"beat_id": "b01", "duration": 10.0, "text": caption}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    caps = timeline.captions
    assert caps[0].start_sec == pytest.approx(0.0, abs=0.01)
    assert caps[-1].end_sec == pytest.approx(10.0, abs=0.01)
    for i in range(1, len(caps)):
        assert abs(caps[i].start_sec - caps[i - 1].end_sec) < 0.01


def test_short_caption_still_one_cue():
    """A caption shorter than min_words stays a single cue (no over-splitting)."""
    beats = [_make_beat("b01")]
    text_intents = [
        {"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": "Short line"}
    ]
    vo_segments = [{"beat_id": "b01", "duration": 2.0, "text": "Short line"}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    assert len(timeline.captions) == 1
    assert timeline.captions[0].text == "Short line"


def test_multi_beat_captions_each_chunked():
    """Two beats with long captions each produce their own phrase cues."""
    beats = [_make_beat("b01"), _make_beat("b02")]
    cap1 = "We built a thing that turned into something much bigger"
    cap2 = "Then it grew again and again until it was enormous"
    text_intents = [
        {"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": cap1},
        {"text_intent_id": "t02", "beat_id": "b02", "function": "caption", "text": cap2},
    ]
    vo_segments = [
        {"beat_id": "b01", "duration": 8.0, "text": cap1},
        {"beat_id": "b02", "duration": 8.0, "text": cap2},
    ]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    b01_caps = [c for c in timeline.captions if c.beat_id == "b01"]
    b02_caps = [c for c in timeline.captions if c.beat_id == "b02"]
    assert len(b01_caps) > 1
    assert len(b02_caps) > 1
    # Beat 2 cues start after beat 1's VO span
    assert b02_caps[0].start_sec >= 8.0 - 0.01


def test_phrase_metadata_records_word_count_and_approximate():
    """Phrase cues carry metadata for downstream compliance."""
    beats = [_make_beat("b01")]
    caption = "We built a thing that turned into something much bigger"
    text_intents = [
        {"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": caption}
    ]
    vo_segments = [{"beat_id": "b01", "duration": 8.0, "text": caption}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    for cap in timeline.captions:
        assert "word_count" in cap.metadata
        assert "approximate_timing" in cap.metadata
        assert cap.metadata["approximate_timing"] is True  # no word timestamps yet


def test_blank_caption_emits_single_spanning_cue():
    """A blank caption text still produces one cue (visible downstream)."""
    beats = [_make_beat("b01")]
    text_intents = [
        {"text_intent_id": "t01", "beat_id": "b01", "function": "caption", "text": ""}
    ]
    vo_segments = [{"beat_id": "b01", "duration": 3.0, "text": ""}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, text_intents, vo_segments=vo_segments)

    assert len(timeline.captions) == 1
    assert timeline.captions[0].text == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))