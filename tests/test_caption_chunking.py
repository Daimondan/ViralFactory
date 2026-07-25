"""Tests for caption sentence-boundary chunking and reconstruction (P1-7).

Verifies:
1. No emitted CaptionPhrase contains a sentence terminator except in its final word.
2. The reconstruction invariant holds: " ".join(p.text for p in phrases) == " ".join(vo_text.split())
3. Word timestamps produce approximate=False; absence produces approximate=True.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from services.caption_timing import chunk_captions, reconstruct_text, _chunk_words


# ── Sentence-boundary tests ──────────────────────────────────────────────

SENTENCE_CORPUS = [
    "You save the money. Then you invest it.",
    "Simple. That's the whole pitch.",
    "First you learn the rules. Then you break them. Finally you profit.",
    "Don't wait for permission. Start now.",
    "The market is rational. The market is emotional. Both are true simultaneously.",
    "One sentence with no terminator at all just words",
    "Short. Punchy. Effective.",
    "Compound sentence, with a comma, and then a period.",
    "Is this a question? Yes it is!",
    "He said \"save more.\" She said \"invest better.\"",
]


@pytest.mark.parametrize("vo_text", SENTENCE_CORPUS)
def test_no_sentence_terminator_mid_phrase(vo_text):
    """No caption phrase may contain a sentence terminator except in its final word."""
    words = vo_text.strip().split()
    chunks = _chunk_words(words)
    for chunk in chunks:
        for word in chunk[:-1]:
            # The last char of a word should not be a sentence terminator
            # unless it's the final word in the chunk.
            assert not word.rstrip('"\')]').endswith(('.', '!', '?')), (
                f"Sentence terminator found mid-phrase in '{word}' "
                f"within chunk {chunk}"
            )


@pytest.mark.parametrize("vo_text", SENTENCE_CORPUS)
def test_reconstruction_invariant(vo_text):
    """Joining phrase texts equals the whitespace-normalized VO text."""
    phrases = chunk_captions(vo_text, duration_sec=10.0)
    assert " ".join(p.text for p in phrases) == " ".join(vo_text.split())


def test_short_sentence_becomes_own_cue():
    """A short trailing sentence like 'Simple.' becomes its own one-word cue."""
    chunks = _chunk_words("You save the money. Simple.".split())
    # Should be at least 2 chunks, and the last chunk should be ["Simple."]
    assert len(chunks) >= 2
    assert chunks[-1] == ["Simple."]


def test_min_words_not_enforced_across_sentence_boundary():
    """The min_words floor must not merge sentences to satisfy it."""
    chunks = _chunk_words("Save. Invest. Profit.".split())
    # Three one-word sentences should produce three one-word chunks
    assert len(chunks) == 3
    assert chunks == [["Save."], ["Invest."], ["Profit."]]


def test_soft_punctuation_preferred_break():
    """When a split is needed, soft punctuation is a preferred break point."""
    words = "Take your time, don't rush, and think carefully about it".split()
    chunks = _chunk_words(words, min_words=3, max_words=6)
    # The first chunk should break at "time," (soft punctuation) not at max_words
    assert chunks[0][-1].endswith(","), f"Expected soft break, got {chunks[0]}"


# ── Word timestamp tests ─────────────────────────────────────────────────

def test_word_timestamps_produce_exact_timing():
    """When word_timestamps are supplied, phrases are approximate=False."""
    vo_text = "You save the money. Then you invest."
    words = vo_text.split()
    word_ts = []
    for i, word in enumerate(words):
        word_ts.append({
            "word": word,
            "start": float(i * 0.5),
            "end": float(i * 0.5 + 0.4),
        })
    phrases = chunk_captions(vo_text, duration_sec=10.0, word_timestamps=word_ts)
    assert all(not p.approximate for p in phrases), "All phrases should be exact"
    # First phrase should start at 0.0
    assert phrases[0].start_sec == 0.0


def test_no_word_timestamps_produce_approximate_timing():
    """Without word_timestamps, phrases are approximate=True."""
    phrases = chunk_captions("You save the money.", duration_sec=5.0)
    assert all(p.approximate for p in phrases), "All phrases should be approximate"


def test_partial_word_timestamps_fall_back_to_approximate():
    """Incomplete word_timestamps fall back to proportional timing."""
    vo_text = "You save the money for later use"
    word_ts = [{"word": "You", "start": 0.0, "end": 0.3}]  # Only 1 of 6
    phrases = chunk_captions(vo_text, duration_sec=5.0, word_timestamps=word_ts)
    assert all(p.approximate for p in phrases), "Should fall back to approximate"