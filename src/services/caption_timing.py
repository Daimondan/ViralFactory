"""Caption timing service (VF-VS-301).

Shared phrase-level caption chunking. Reuses the no-dangling-fragment
algorithm from ``episode_plan._chunk_vo_text`` and lifts it into a service
so the generic reel cue compiler (VF-VS-302) and the episode plan compiler
(VF-VS-303) share one implementation.

Per AMENDMENT-010 Condition 3: captions are chunked into 3–6 word phrases,
timed proportionally within the beat's VO span (or by word timestamps when
available). Proportional timing is labeled ``approximate: True`` until
word-level timestamps land (T2.6–T2.8).

Exact-text reconstruction is guaranteed: joining the phrase texts after
whitespace normalization equals the approved VO text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# Default phrase bounds per AMENDMENT-010 Condition 3.
DEFAULT_MIN_WORDS = 3
DEFAULT_MAX_WORDS = 6


@dataclass(frozen=True)
class CaptionPhrase:
    """One phrase-level caption cue with its time span."""

    text: str
    start_sec: float
    end_sec: float
    word_count: int
    # True when timing is proportional (no word-level timestamps). Flips to
    # False once word timestamps are wired (T2.6–T2.8).
    approximate: bool = True


def _chunk_words(
    words: list[str],
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[list[str]]:
    """Split ``words`` into min..max word groups with no dangling tail.

    Reuses the algorithm from ``episode_plan._chunk_vo_text``: take up to
    ``max_words`` per group, but if that would leave a dangling 1–2 word
    tail, shrink the current group so the tail reaches ``min_words``.
    """
    if not words:
        return []
    if min_words < 1 or max_words < min_words:
        raise ValueError(
            f"Invalid phrase bounds: min={min_words} max={max_words}"
        )

    chunks: list[list[str]] = []
    i = 0
    n = len(words)
    while i < n:
        remaining = n - i
        if remaining <= max_words:
            chunk_len = remaining
        else:
            chunk_len = max_words
            leftover = remaining - chunk_len
            if leftover < min_words:
                chunk_len = remaining - min_words
                if chunk_len < min_words:
                    chunk_len = min_words
        chunks.append(words[i : i + chunk_len])
        i += chunk_len
    return chunks


def chunk_captions(
    vo_text: str,
    duration_sec: float,
    word_timestamps: Optional[list[dict]] = None,
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[CaptionPhrase]:
    """Chunk ``vo_text`` into phrase-level captions timed within ``duration_sec``.

    Args:
        vo_text: The approved VO line for one beat.
        duration_sec: The beat's VO span in seconds.
        word_timestamps: Optional ``[{word, start, end}, ...]``. When supplied
            and complete, phrases are timed from the word clocks; otherwise
            timing is proportional and flagged ``approximate``.
        min_words / max_words: Phrase bounds (defaults 3 / 6 per amendment).

    Returns:
        One ``CaptionPhrase`` per chunk. Empty list if ``vo_text`` is blank
        or ``duration_sec`` is non-positive.

    Reconstruction invariant: ``" ".join(p.text for p in phrases)`` equals
    ``" ".join(vo_text.split())`` (whitespace-normalized).
    """
    words = vo_text.strip().split()
    if not words or duration_sec <= 0:
        return []

    word_groups = _chunk_words(words, min_words, max_words)
    if not word_groups:
        return []

    # Word-timestamp alignment is deferred (T2.6–T2.8). When a complete,
    # well-formed timestamp list is supplied, use it; otherwise proportional.
    use_timestamps = bool(word_timestamps) and _timestamps_complete(
        word_timestamps, len(words)
    )

    phrases: list[CaptionPhrase] = []
    if use_timestamps:
        idx = 0
        for group in word_groups:
            start = float(word_timestamps[idx].get("start", 0.0))
            end = float(word_timestamps[idx + len(group) - 1].get("end", start))
            phrases.append(
                CaptionPhrase(
                    text=" ".join(group),
                    start_sec=round(start, 3),
                    end_sec=round(end, 3),
                    word_count=len(group),
                    approximate=False,
                )
            )
            idx += len(group)
        return phrases

    # Proportional timing — each phrase gets a share of the beat proportional
    # to its word count.
    total_words = sum(len(g) for g in word_groups)
    offset = 0.0
    for group in word_groups:
        share = len(group) / total_words
        chunk_duration = share * duration_sec
        phrases.append(
            CaptionPhrase(
                text=" ".join(group),
                start_sec=round(offset, 3),
                end_sec=round(offset + chunk_duration, 3),
                word_count=len(group),
                approximate=True,
            )
        )
        offset += chunk_duration
    return phrases


def _timestamps_complete(word_timestamps: list[dict], word_count: int) -> bool:
    """True if the timestamp list covers every word with start/end floats."""
    if len(word_timestamps) != word_count:
        return False
    for ts in word_timestamps:
        if "start" not in ts or "end" not in ts:
            return False
        try:
            float(ts["start"])
            float(ts["end"])
        except (TypeError, ValueError):
            return False
    return True


def reconstruct_text(phrases: list[CaptionPhrase]) -> str:
    """Join phrase texts back into the whitespace-normalized VO line."""
    return " ".join(p.text for p in phrases)