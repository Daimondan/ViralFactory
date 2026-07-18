"""VF-VS-301 — caption timing service extraction.

AC: 3–6 word phrases, no dangling fragments, exact-text reconstruction.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from services.caption_timing import (
    CaptionPhrase,
    chunk_captions,
    reconstruct_text,
    DEFAULT_MIN_WORDS,
    DEFAULT_MAX_WORDS,
)


# ── AC: 3–6 word phrases ────────────────────────────────────────────────────


def test_default_bounds_are_three_to_six():
    assert DEFAULT_MIN_WORDS == 3
    assert DEFAULT_MAX_WORDS == 6


def test_phrases_within_three_to_six_words():
    vo = "We built a thing that turned into something much bigger than we planned"
    phrases = chunk_captions(vo, duration_sec=12.0)
    assert phrases
    for p in phrases:
        assert DEFAULT_MIN_WORDS <= p.word_count <= DEFAULT_MAX_WORDS
        assert p.word_count == len(p.text.split())


def test_short_text_one_phrase():
    phrases = chunk_captions("Small line", duration_sec=2.0)
    assert len(phrases) == 1
    assert phrases[0].word_count == 2  # shorter than min is allowed when total is small


# ── AC: no dangling fragments ───────────────────────────────────────────────


def test_no_dangling_one_word_tail():
    # 7 words: a 6+1 split would leave a dangling 1-word tail. Algorithm must
    # rebalance so no phrase is below min (unless the whole text is small).
    vo = "one two three four five six seven"
    phrases = chunk_captions(vo, duration_sec=7.0)
    assert len(phrases) >= 2
    # No phrase should be a dangling single word
    for p in phrases:
        if p.word_count < DEFAULT_MIN_WORDS:
            # Only allowed if the whole text was shorter than min
            assert sum(len(w.text.split()) for w in phrases) < DEFAULT_MIN_WORDS


def test_no_dangling_two_word_tail():
    # 8 words: 6+2 would leave a dangling 2-word tail. Rebalance.
    vo = "one two three four five six seven eight"
    phrases = chunk_captions(vo, duration_sec=8.0)
    assert len(phrases) >= 2
    for p in phrases:
        if p.word_count < DEFAULT_MIN_WORDS:
            assert sum(len(w.text.split()) for w in phrases) < DEFAULT_MIN_WORDS


def test_exact_split_at_max():
    # 12 words = exactly two 6-word phrases
    vo = " ".join([f"word{i}" for i in range(12)])
    phrases = chunk_captions(vo, duration_sec=12.0)
    assert len(phrases) == 2
    assert phrases[0].word_count == 6
    assert phrases[1].word_count == 6


# ── AC: exact-text reconstruction ───────────────────────────────────────────


def test_reconstruction_equals_normalized_vo():
    vo = "We  built   a thing that turned into\n something much bigger than we planned"
    phrases = chunk_captions(vo, duration_sec=12.0)
    assert reconstruct_text(phrases) == " ".join(vo.split())


def test_reconstruction_single_phrase():
    vo = "Tight line"
    phrases = chunk_captions(vo, duration_sec=1.5)
    assert reconstruct_text(phrases) == " ".join(vo.split())


# ── Timing ───────────────────────────────────────────────────────────────────


def test_proportional_timing_covers_full_duration():
    phrases = chunk_captions("a b c d e f g h i j", duration_sec=10.0)
    assert phrases[0].start_sec == 0.0
    assert abs(phrases[-1].end_sec - 10.0) < 0.01
    # No gaps or overlaps in proportional mode
    for i in range(1, len(phrases)):
        assert abs(phrases[i].start_sec - phrases[i - 1].end_sec) < 0.001


def test_approximate_flag_true_for_proportional():
    phrases = chunk_captions("a b c d e f", duration_sec=6.0)
    assert all(p.approximate is True for p in phrases)


def test_word_timestamps_used_when_complete():
    words = ["a", "b", "c", "d", "e", "f"]
    ts = [{"word": w, "start": i * 0.5, "end": (i + 1) * 0.5} for i, w in enumerate(words)]
    phrases = chunk_captions(" ".join(words), duration_sec=3.0, word_timestamps=ts)
    assert all(p.approximate is False for p in phrases)
    assert phrases[0].start_sec == 0.0
    assert phrases[-1].end_sec == 3.0


def test_word_timestamps_ignored_when_incomplete():
    words = ["a", "b", "c", "d", "e", "f"]
    # Only 5 timestamps for 6 words — fall back to proportional
    ts = [{"word": w, "start": i * 0.5, "end": (i + 1) * 0.5} for i, w in enumerate(words[:5])]
    phrases = chunk_captions(" ".join(words), duration_sec=3.0, word_timestamps=ts)
    assert all(p.approximate is True for p in phrases)


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_empty_text_returns_empty():
    assert chunk_captions("", duration_sec=3.0) == []


def test_zero_duration_returns_empty():
    assert chunk_captions("a b c", duration_sec=0.0) == []


def test_negative_duration_returns_empty():
    assert chunk_captions("a b c", duration_sec=-1.0) == []


def test_invalid_bounds_raise():
    with pytest.raises(ValueError):
        chunk_captions("a b c", duration_sec=3.0, min_words=0, max_words=5)
    with pytest.raises(ValueError):
        chunk_captions("a b c", duration_sec=3.0, min_words=5, max_words=3)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))