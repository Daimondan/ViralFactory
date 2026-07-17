"""
ViralFactory — Layer-3 Editorial Critic (T11.9 — CORRECTION-episode-format §7.3)

Post-Writer, pre-Gate-2: critic scores the Writer's beats against the rubric
that lives in the episode-format module. Scores are advisory — they appear
on the Gate 2 card as one-line reasons. The critic NEVER blocks.

The rubric text lives in the episode-format module (gated, improvable by the
Analyst through the module review gate), NOT in prompts or code. The critic
prompt receives the rubric + the beats and returns structured scores.

The Analyst may propose rubric edits only through the module review gate
(same discipline as every module).
"""

import json
import os
import sys
from typing import Optional

# Support both package and direct imports
try:
    from .llm_adapter import LLMAdapter, LLMAdapterError
except ImportError:
    from llm_adapter import LLMAdapter, LLMAdapterError


# ── Result type ──────────────────────────────────────────────────────────────

class CriticResult:
    """Result of the Layer-3 editorial critic."""
    def __init__(self, scores: list, overall_score: float, summary: str):
        self.scores = scores           # list of {criterion, score, reason}
        self.overall_score = overall_score  # 0-1
        self.summary = summary          # one-line summary for Gate 2 card

    def to_dict(self) -> dict:
        return {
            "scores": self.scores,
            "overall_score": self.overall_score,
            "summary": self.summary,
        }


# ── Critic ───────────────────────────────────────────────────────────────────

def run_episode_critic(
    beats: list,
    rubric: list,
    models_config: dict,
    db_path: str = "data/viralfactory.db",
    business_slug: str = None,
    prompts_dir: str = "prompts",
) -> CriticResult:
    """Run the Layer-3 editorial critic on Writer beats against the rubric.

    Args:
        beats: The Writer's beats[] (each has role, vo_text, staged_action, etc.)
        rubric: The rubric from the episode-format module — list of
                {criterion, description, pass_hint} dicts.
        models_config: Config dict for LLM adapter.
        db_path: Provenance DB path.
        business_slug: Current business slug.

    Returns:
        CriticResult with per-criterion scores + overall score + summary.
        NEVER blocks — always returns a result, even on failure.
    """
    # Build the rubric text for the prompt
    rubric_lines = []
    for i, item in enumerate(rubric, 1):
        criterion = item.get("criterion", f"Criterion {i}")
        desc = item.get("description", "")
        hint = item.get("pass_hint", "")
        rubric_lines.append(f"{i}. {criterion}: {desc}")
        if hint:
            rubric_lines.append(f"   Pass if: {hint}")
    rubric_text = "\n".join(rubric_lines)

    # Build the beats text for the prompt
    beats_lines = []
    for beat in beats:
        bid = beat.get("id", "?")
        role = beat.get("role", "")
        vo = beat.get("vo_text", "")
        action = beat.get("staged_action", "")
        beats_lines.append(f"Beat {bid} ({role}): vo_text=\"{vo}\" staged_action=\"{action}\"")
    beats_text = "\n".join(beats_lines)

    try:
        adapter = LLMAdapter(models_config, db_path=db_path, prompts_dir=prompts_dir)
        result = adapter.complete(
            prompt_file="assembly/episode_critic_v1.md",
            variables={
                "rubric": rubric_text,
                "beats": beats_text,
            },
            schema=None,
            backend="default",
            context=f"T11.9 episode critic for {business_slug}",
            business_slug=business_slug,
            profile="default",
        )

        # Parse the critic output — expects {scores: [...], overall_score: float, summary: str}
        if isinstance(result, str):
            parsed = json.loads(result)
        else:
            parsed = result

        scores = parsed.get("scores", [])
        overall = float(parsed.get("overall_score", 0))
        summary = parsed.get("summary", "Critic completed.")

        return CriticResult(scores=scores, overall_score=overall, summary=summary)

    except Exception as e:
        # The critic NEVER blocks — on failure, return a neutral result
        return CriticResult(
            scores=[],
            overall_score=0.0,
            summary=f"Critic unavailable: {str(e)[:100]}",
        )


def default_rubric() -> list:
    """Return the default rubric criteria for episode-format pieces.

    This is the fallback when the module doesn't define a rubric. The
    authoritative rubric lives in the episode-format module (gated).
    """
    return [
        {
            "criterion": "Hook contains contradiction or confession",
            "description": "The hook beat must contain a spoken contradiction or confession that creates immediate tension.",
            "pass_hint": "The vo_text of the hook beat has a clear contradiction or personal confession.",
        },
        {
            "criterion": "Each staged_action literally depicts its vo_text",
            "description": "Every beat's staged_action must literally depict what the vo_text says — no symbolic or unrelated visuals.",
            "pass_hint": "The staged_action describes the character doing exactly what the vo_text narrates.",
        },
        {
            "criterion": "One idea per beat",
            "description": "Each beat carries exactly one idea. No beat should pack two concepts.",
            "pass_hint": "Each beat's vo_text is a single sentence with one clear idea.",
        },
        {
            "criterion": "Lesson stated plainly",
            "description": "The lesson beat names the concept in plain words — no metaphor or indirection.",
            "pass_hint": "The lesson beat's vo_text is a direct, clear statement of the takeaway.",
        },
        {
            "criterion": "Sign-off (CTA) present",
            "description": "The CTA beat has a recurring sign-off line.",
            "pass_hint": "The cta beat's vo_text contains a clear call to action.",
        },
    ]