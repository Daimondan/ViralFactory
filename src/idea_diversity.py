"""Idea diversity utilities — text extraction and dedup helpers.

These functions support the idea generation pipeline's anti-duplication
mechanisms. They are kept here (not in app.py) so they can be tested
independently without importing the full Flask app.
"""
import re


def summarize_idea(idea_text: str, max_chars: int = 160) -> str:
    """Extract a meaningful summary of an idea for the existing_ideas list.

    Takes the first 1-2 complete sentences (up to max_chars) instead of
    cutting mid-sentence at a fixed offset. This preserves the core claim
    so the LLM can assess semantic overlap between ideas.

    Examples:
        >>> summarize_idea("Short idea.")
        'Short idea.'
        >>> summarize_idea("First sentence. Second sentence. Third.", max_chars=20)
        'First sentence.'
        >>> summarize_idea("a" * 300, max_chars=160)
        'aaaa…'
    """
    if not idea_text:
        return ""
    text = idea_text.strip()
    if len(text) <= max_chars:
        return text
    # Search slightly beyond max_chars to allow completing a sentence
    search_region = text[: max_chars + 60]
    # Match end of sentence: . ! ? followed by whitespace or end of string
    sentences = re.split(r"(?<=[.!?])\s+", search_region)
    result = ""
    for s in sentences:
        if len(result) + len(s) > max_chars and result:
            break
        result = (result + " " + s).strip() if result else s
        if len(result) >= max_chars - 20:
            break
    if result and len(result) <= max_chars:
        return result
    # Result is empty or too long (no sentence boundary within limit)
    # Fall back to word-boundary truncation
    truncated = text[:max_chars]
    if " " in truncated:
        return truncated.rsplit(" ", 1)[0] + "…"
    return truncated + "…"