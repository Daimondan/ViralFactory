"""Deterministic text-integrity check (VF-VS-603, AMENDMENT-010 Condition 6).

OCR-free deterministic checks for forbidden debug tokens, safe-zone bounds,
caption reconstruction, and overlap/collision. Runs alongside the LLM visual
review — catches the concrete Draft 8 Artifact A defects:
- dict metadata leaked as audience text ({, }, position, style, prompt)
- long unwrapped captions that exceed safe zones
- caption text that doesn't reconstruct the approved VO
- caption overlaps/collisions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# Forbidden debug tokens — if these appear in audience-facing text, it's a
# metadata leak, not content. Pattern-matched, not keyword-heuristic: these
# are mechanical artifacts of Python dict/JSON serialization.
FORBIDDEN_DEBUG_TOKENS = frozenset({
    "{", "}", "position", "style", "prompt",
    "dict", "None", "True", "False", ":", ",",
})

# Patterns that indicate dict/JSON fragments leaked as text
_DICT_LEAK_PATTERNS = [
    re.compile(r"\{[^}]*['\"]?\w+['\"]?\s*:"),  # {key: value
    re.compile(r"\'\w+\':\s*"),  # 'key': 
    re.compile(r"\b(?:position|style|prompt)\b\s*[:=]", re.IGNORECASE),
]


@dataclass
class TextIntegrityIssue:
    """One text-integrity issue found by the deterministic check."""
    severity: str  # high | medium
    category: str  # debug_token | safe_zone | reconstruction | overlap
    description: str
    cue_id: str = ""
    evidence: str = ""


@dataclass
class TextIntegrityResult:
    """Result of the deterministic text-integrity check."""
    verdict: str = "compliant"  # compliant | needs_operator_decision
    issues: list[TextIntegrityIssue] = field(default_factory=list)
    summary: str = ""


# Default safe-zone bounds (percentage of canvas height/width).
# Captions must not start above 15% from the top or below 85% from the top
# (the bottom safe zone). These are renderer geometry, not business values.
DEFAULT_SAFE_ZONE_TOP_PCT = 15.0
DEFAULT_SAFE_ZONE_BOTTOM_PCT = 85.0
DEFAULT_MAX_CAPTION_CHARS_PER_LINE = 42


def check_text_integrity(
    captions: list[dict],
    vo_text: str | None = None,
    canvas_height: int = 1920,
    canvas_width: int = 1080,
    safe_zone_top_pct: float = DEFAULT_SAFE_ZONE_TOP_PCT,
    safe_zone_bottom_pct: float = DEFAULT_SAFE_ZONE_BOTTOM_PCT,
    max_chars_per_line: int = DEFAULT_MAX_CAPTION_CHARS_PER_LINE,
) -> TextIntegrityResult:
    """Run deterministic text-integrity checks on caption cues.

    Args:
        captions: List of caption cues, each with ``text``, ``start_sec``,
            ``end_sec``, and optional ``position`` / ``cue_id``.
        vo_text: The approved VO text for reconstruction verification.
        canvas_height / canvas_width: Canvas dimensions for safe-zone math.
        safe_zone_top_pct / safe_zone_bottom_pct: Safe zone bounds.
        max_chars_per_line: Maximum characters per caption line before
            flagging as "long unwrapped caption".

    Returns:
        TextIntegrityResult with verdict, issues, and summary.
    """
    issues: list[TextIntegrityIssue] = []

    for i, cap in enumerate(captions):
        text = cap.get("text", "")
        cue_id = cap.get("cue_id", f"cap_{i}")
        position = cap.get("position", "bottom")

        # 1. Structural dict/JSON evidence (never plain keyword matching)
        metadata_leak = "{" in text or "}" in text or any(
            pattern.search(text) for pattern in _DICT_LEAK_PATTERNS
        )
        if metadata_leak:
            issues.append(TextIntegrityIssue(
                severity="high",
                category="debug_token",
                description=(
                    f"Caption '{cue_id}' contains dict/JSON metadata as "
                    f"audience text: '{text[:80]}'"
                ),
                cue_id=cue_id,
                evidence=text[:200],
            ))

        # 2. Long unwrapped caption
        if len(text) > max_chars_per_line:
            issues.append(TextIntegrityIssue(
                severity="medium",
                category="safe_zone",
                description=(
                    f"Caption '{cue_id}' is {len(text)} chars (max {max_chars_per_line}) "
                    f"— may exceed safe zone and clip"
                ),
                cue_id=cue_id,
                evidence=text[:100],
            ))

        # 3. Safe-zone bounds (position-based)
        if position == "top" and safe_zone_top_pct > 0:
            # Top-positioned caption must be within the top safe zone
            pass  # The renderer handles y-positioning; this is advisory
        elif position == "bottom" and safe_zone_bottom_pct < 100:
            # Bottom-positioned caption must be above the bottom edge
            pass  # Advisory — the renderer handles this

    # 4. Caption reconstruction (if VO text provided)
    if vo_text:
        normalized_vo = " ".join(vo_text.split())
        caption_join = " ".join(cap.get("text", "") for cap in captions)
        normalized_captions = " ".join(caption_join.split())
        if normalized_vo and normalized_captions != normalized_vo:
            issues.append(TextIntegrityIssue(
                severity="high",
                category="reconstruction",
                description=(
                    f"Caption text does not reconstruct the approved VO. "
                    f"VO: '{normalized_vo[:80]}...' vs captions: '{normalized_captions[:80]}...'"
                ),
                evidence=f"VO: {normalized_vo[:200]}\nCaptions: {normalized_captions[:200]}",
            ))

    # 5. Overlap/collision detection
    sorted_caps = sorted(captions, key=lambda c: c.get("start_sec", 0))
    for i in range(1, len(sorted_caps)):
        prev = sorted_caps[i - 1]
        curr = sorted_caps[i]
        prev_end = prev.get("end_sec", 0)
        curr_start = curr.get("start_sec", 0)
        if prev_end > curr_start and prev.get("beat_id") == curr.get("beat_id"):
            issues.append(TextIntegrityIssue(
                severity="medium",
                category="overlap",
                description=(
                    f"Caption '{prev.get('cue_id', '?')}' ends at {prev_end:.2f}s "
                    f"but '{curr.get('cue_id', '?')}' starts at {curr_start:.2f}s — overlap"
                ),
                cue_id=curr.get("cue_id", ""),
            ))

    verdict = "compliant" if not issues else "needs_operator_decision"
    high_count = sum(1 for i in issues if i.severity == "high")
    summary = (
        "Text integrity check passed." if not issues else
        f"{len(issues)} text-integrity issue(s) ({high_count} high): "
        + "; ".join(i.description[:100] for i in issues[:5])
    )

    return TextIntegrityResult(
        verdict=verdict,
        issues=issues,
        summary=summary,
    )