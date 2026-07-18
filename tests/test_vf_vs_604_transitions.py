"""VF-VS-604 — Transition intent in cue compiler.

AC: hard cuts, crossfades, holds have explicit jobs; no silent cut override.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from services.cue_compiler import CueCompiler


def _make_beat(beat_id="b01", transition_in="cut", audio_mode="vo_only"):
    return {
        "beat_id": beat_id,
        "vo_text": "",
        "transition_in": transition_in,
        "audio_intent": {"mode": audio_mode},
    }


def test_hard_cut_has_explicit_job():
    beats = [_make_beat("b01", "cut"), _make_beat("b02", "cut")]
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "first"},
        {"beat_id": "b02", "duration": 3.0, "text": "second"},
    ]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, [], vo_segments=vo_segments)
    trans = [o for o in timeline.overlays if o.cue_type == "transition"]
    assert len(trans) == 2
    assert all(o.metadata.get("transition_in") == "cut" for o in trans)


def test_crossfade_has_overlap_budget():
    beats = [_make_beat("b01", "cut"), _make_beat("b02", "crossfade")]
    vo_segments = [
        {"beat_id": "b01", "duration": 4.0, "text": "first"},
        {"beat_id": "b02", "duration": 4.0, "text": "second"},
    ]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, [], vo_segments=vo_segments)
    trans = [o for o in timeline.overlays if o.cue_type == "transition"]
    crossfade = next(t for t in trans if t.beat_id == "b02")
    assert crossfade.metadata["transition_in"] == "crossfade"
    assert "overlap_sec" in crossfade.metadata
    assert crossfade.metadata["overlap_sec"] > 0


def test_hold_transition():
    beats = [_make_beat("b01", "cut"), _make_beat("b02", "hold")]
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "first"},
        {"beat_id": "b02", "duration": 3.0, "text": "second"},
    ]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, [], vo_segments=vo_segments)
    trans = [o for o in timeline.overlays if o.cue_type == "transition"]
    hold = next(t for t in trans if t.beat_id == "b02")
    assert hold.metadata["transition_in"] == "hold"


def test_unsupported_transition_warns():
    beats = [_make_beat("b01", "cut"), _make_beat("b02", "star_wipe")]
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "first"},
        {"beat_id": "b02", "duration": 3.0, "text": "second"},
    ]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, [], vo_segments=vo_segments)
    trans = [o for o in timeline.overlays if o.cue_type == "transition"]
    unsupported = next(t for t in trans if t.beat_id == "b02")
    assert unsupported.metadata.get("unsupported") is True
    assert "warning" in unsupported.metadata


def test_crossfade_on_first_beat_falls_back_to_cut():
    """Crossfade on the first beat (no previous) → cut with warning."""
    beats = [_make_beat("b01", "crossfade")]
    vo_segments = [{"beat_id": "b01", "duration": 3.0, "text": "first"}]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, [], vo_segments=vo_segments)
    trans = [o for o in timeline.overlays if o.cue_type == "transition"]
    assert len(trans) == 1
    assert trans[0].metadata["transition_in"] == "cut"
    assert trans[0].metadata.get("fallback") is True


def test_no_silent_cut_override():
    """Default transition is cut but it's an explicit job, not a silent override."""
    beats = [_make_beat("b01"), _make_beat("b02")]  # no transition_in specified
    vo_segments = [
        {"beat_id": "b01", "duration": 3.0, "text": "first"},
        {"beat_id": "b02", "duration": 3.0, "text": "second"},
    ]
    compiler = CueCompiler()
    timeline = compiler.compile(beats, [], vo_segments=vo_segments)
    trans = [o for o in timeline.overlays if o.cue_type == "transition"]
    # All transitions have explicit metadata — no silent defaults
    for t in trans:
        assert "transition_in" in t.metadata


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))