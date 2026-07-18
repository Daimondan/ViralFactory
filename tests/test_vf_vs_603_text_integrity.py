"""VF-VS-603 — Deterministic text-integrity check.

AC: Artifact A's leaked dict text and clipped captions fail in a regression fixture.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from text_integrity import (
    check_text_integrity,
    TextIntegrityResult,
    FORBIDDEN_DEBUG_TOKENS,
)


def test_clean_captions_pass():
    captions = [
        {"cue_id": "cap_0", "text": "We built a thing", "start_sec": 0.0, "end_sec": 2.0},
        {"cue_id": "cap_1", "text": "that turned into something", "start_sec": 2.0, "end_sec": 5.0},
    ]
    result = check_text_integrity(captions)
    assert result.verdict == "compliant"
    assert len(result.issues) == 0


def test_dict_metadata_leak_detected():
    """Artifact A's leaked dict text — the exact Draft 8 defect."""
    captions = [
        {"cue_id": "cap_0", "text": "{'position': 'center', 'style': 'default'}", "start_sec": 0.0, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions)
    assert result.verdict == "needs_operator_decision"
    assert any(i.category == "debug_token" for i in result.issues)


def test_curly_braces_detected():
    captions = [
        {"cue_id": "cap_0", "text": "Some {text} with braces", "start_sec": 0.0, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions)
    assert any(i.category == "debug_token" for i in result.issues)


def test_position_style_keywords_detected():
    """position and style as standalone words in dict-like context."""
    captions = [
        {"cue_id": "cap_0", "text": "position: center, style: default", "start_sec": 0.0, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions)
    assert any(i.category == "debug_token" for i in result.issues)


def test_long_caption_flagged():
    captions = [
        {"cue_id": "cap_0", "text": "A" * 50, "start_sec": 0.0, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions, max_chars_per_line=42)
    assert any(i.category == "safe_zone" for i in result.issues)


def test_caption_reconstruction_mismatch():
    """Caption text that doesn't reconstruct the approved VO."""
    captions = [
        {"cue_id": "cap_0", "text": "Completely different text", "start_sec": 0.0, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions, vo_text="The approved VO text")
    assert any(i.category == "reconstruction" for i in result.issues)


def test_caption_reconstruction_match():
    captions = [
        {"cue_id": "cap_0", "text": "The approved", "start_sec": 0.0, "end_sec": 1.5},
        {"cue_id": "cap_1", "text": "VO text", "start_sec": 1.5, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions, vo_text="The approved VO text")
    assert result.verdict == "compliant"


def test_caption_overlap_detected():
    captions = [
        {"cue_id": "cap_0", "text": "First", "start_sec": 0.0, "end_sec": 3.0, "beat_id": "b01"},
        {"cue_id": "cap_1", "text": "Second", "start_sec": 2.5, "end_sec": 5.0, "beat_id": "b01"},
    ]
    result = check_text_integrity(captions)
    assert any(i.category == "overlap" for i in result.issues)


def test_colon_in_normal_text_not_flagged():
    """A colon in normal caption text (not dict-like) should not be flagged."""
    captions = [
        {"cue_id": "cap_0", "text": "Here's the thing: it works", "start_sec": 0.0, "end_sec": 3.0},
    ]
    result = check_text_integrity(captions)
    # No debug_token issue for normal colon usage
    debug_issues = [i for i in result.issues if i.category == "debug_token"]
    assert len(debug_issues) == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))