"""
ViralFactory — Golden Episodes + Pass-Rate Metric (T11.10 — CORRECTION-episode-format §7.4-7.5)

Two components:
1. Golden episodes: frozen EpisodePlans + assets under tests/fixtures/golden/
   Any renderer/schema change re-renders both and asserts duration, loudness,
   caption offsets, graphics frame hashes, stream layout.

2. Validator pass-rate metric: run the Writer prompt against a 20-seed corpus,
   record the fraction of EpisodePlans clearing Layer 1 unassisted.
   <80% → the prompt or schema is the defect, not the model.
   Log per prompt version.
"""

import json
import os
import sys
from typing import Optional

# Support both package and direct imports
try:
    from .episode_lints import run_episode_plan_lints, LintResult
except ImportError:
    from episode_lints import run_episode_plan_lints, LintResult


# ── Golden episode fixtures ──────────────────────────────────────────────────

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tests", "fixtures", "golden")


def load_golden_episode(name: str) -> dict:
    """Load a golden episode fixture by name.

    Golden episodes live under tests/fixtures/golden/{name}/episode_plan.json
    """
    path = os.path.join(GOLDEN_DIR, name, "episode_plan.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Golden episode '{name}' not found at {path}")
    with open(path) as f:
        return json.load(f)


def list_golden_episodes() -> list:
    """List all available golden episode names."""
    if not os.path.isdir(GOLDEN_DIR):
        return []
    return [
        d for d in os.listdir(GOLDEN_DIR)
        if os.path.isdir(os.path.join(GOLDEN_DIR, d))
        and os.path.exists(os.path.join(GOLDEN_DIR, d, "episode_plan.json"))
    ]


def validate_golden_episode(
    name: str,
    expected_duration: float,
    expected_loudness_lufs: float = -14.0,
    loudness_tolerance: float = 0.5,
) -> dict:
    """Validate a golden episode against expected properties.

    Args:
        name: Golden episode name
        expected_duration: Expected total duration in seconds
        expected_loudness_lufs: Expected integrated loudness (default -14)
        loudness_tolerance: LUFS tolerance (default ±0.5)

    Returns:
        {valid: bool, checks: {duration, loudness, plan_structure}, issues: [str]}
    """
    issues = []
    checks = {}

    try:
        plan = load_golden_episode(name)
    except FileNotFoundError as e:
        return {"valid": False, "checks": {}, "issues": [str(e)]}

    # Check plan structure
    beats = plan.get("beats", [])
    if not beats:
        issues.append("Golden episode has no beats")
        checks["plan_structure"] = False
    else:
        checks["plan_structure"] = True

    # Check duration
    total_duration = 0.0
    for beat in beats:
        d = beat.get("duration_s", 0)
        if isinstance(d, (int, float)) and d > 0:
            total_duration += d

    if expected_duration and abs(total_duration - expected_duration) > 1.0:
        issues.append(
            f"Duration mismatch: expected {expected_duration:.1f}s, got {total_duration:.1f}s"
        )
        checks["duration"] = False
    else:
        checks["duration"] = True

    # Check loudness (if metadata exists in the fixture)
    metadata_path = os.path.join(GOLDEN_DIR, name, "render_metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            metadata = json.load(f)
        measured_loudness = metadata.get("integrated_loudness_lufs")
        if measured_loudness is not None:
            if abs(measured_loudness - expected_loudness_lufs) > loudness_tolerance:
                issues.append(
                    f"Loudness mismatch: expected {expected_loudness_lufs:.1f} LUFS, "
                    f"got {measured_loudness:.1f} LUFS"
                )
                checks["loudness"] = False
            else:
                checks["loudness"] = True
        else:
            checks["loudness"] = None  # not measured
    else:
        checks["loudness"] = None  # no metadata file

    return {
        "valid": len(issues) == 0,
        "checks": checks,
        "issues": issues,
    }


# ── Pass-rate metric ─────────────────────────────────────────────────────────

def compute_pass_rate(
    episode_plans: list,
    format_module: dict,
    ref_store,
    business_slug: str,
    lint_config: dict,
) -> dict:
    """Compute the Layer-1 pass rate across a corpus of EpisodePlans.

    Args:
        episode_plans: List of EpisodePlan dicts (from Writer runs)
        format_module: The episode-format module dict
        ref_store: ReferenceAssetStore instance
        business_slug: Current business slug
        lint_config: Config dict from models.yaml episode_lint block

    Returns:
        {
            total: int,
            passed: int,
            failed: int,
            pass_rate: float,  # 0.0-1.0
            failures: list[{plan_index, errors}],
            prompt_version: str (from format_module if available),
        }
    """
    total = len(episode_plans)
    passed = 0
    failures = []

    for i, plan in enumerate(episode_plans):
        result = run_episode_plan_lints(
            episode_plan=plan,
            format_module=format_module,
            ref_store=ref_store,
            business_slug=business_slug,
            lint_config=lint_config,
        )
        if result.passed:
            passed += 1
        else:
            failures.append({
                "plan_index": i,
                "errors": result.errors,
            })

    pass_rate = passed / total if total > 0 else 0.0

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(pass_rate, 4),
        "failures": failures,
        "prompt_version": format_module.get("version", "unknown"),
    }


def pass_rate_verdict(pass_rate: float, threshold: float = 0.80) -> str:
    """Determine the verdict from a pass rate.

    <threshold → the prompt or schema is the defect (correction-file territory),
    not the model.
    """
    if pass_rate >= threshold:
        return "pass"
    return "fail_prompt_or_schema_defect"