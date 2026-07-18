"""VF-VS-303 — episode_plan delegates to caption_timing (no duplication).

AC: `episode_plan._chunk_vo_text` delegates to `caption_timing.py`.
"""

import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from episode_plan import EpisodePlanCompiler, CAPTION_CHUNK_MIN, CAPTION_CHUNK_MAX  # noqa: E402
from services.caption_timing import _chunk_words  # noqa: E402


def test_episode_plan_chunk_vo_text_delegates_to_shared_service():
    """The episode compiler's chunker produces the same output as the shared
    service's _chunk_words with episode bounds (3, 5)."""
    compiler = EpisodePlanCompiler()
    samples = [
        "I worked fifty years and retired with absolutely nothing to show",
        "one two three four five six seven",
        "short line",
        "a b c d e f g h i j k l",
        "",
    ]
    for s in samples:
        words = s.strip().split()
        expected = [" ".join(g) for g in _chunk_words(
            words, min_words=CAPTION_CHUNK_MIN, max_words=CAPTION_CHUNK_MAX
        )] if words else []
        assert compiler._chunk_vo_text(s) == expected


def test_episode_plan_uses_three_to_five_bounds():
    """Episode format pins 3–5 (its spec), not the amendment's generic 3–6."""
    assert CAPTION_CHUNK_MIN == 3
    assert CAPTION_CHUNK_MAX == 5

    compiler = EpisodePlanCompiler()
    chunks = compiler._chunk_vo_text("one two three four five six seven eight nine ten")
    for c in chunks:
        wc = len(c.split())
        assert 3 <= wc <= 5, f"Episode chunk '{c}' has {wc} words — must be 3–5"


def test_no_dangling_short_chunk_after_delegation():
    compiler = EpisodePlanCompiler()
    chunks = compiler._chunk_vo_text("one two three four five six seven")
    for c in chunks:
        assert len(c.split()) >= 3


def test_exact_reconstruction_after_delegation():
    compiler = EpisodePlanCompiler()
    text = "We  built   a thing that turned into\n something much bigger"
    chunks = compiler._chunk_vo_text(text)
    assert " ".join(chunks) == " ".join(text.split())


def test_empty_text_returns_empty():
    compiler = EpisodePlanCompiler()
    assert compiler._chunk_vo_text("") == []


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))