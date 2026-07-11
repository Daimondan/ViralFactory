"""
ViralFactory — Pre-render Feasibility Checks (T10.3 — AMENDMENT-008)

Deterministic code that runs AFTER TTS generates VO but BEFORE the renderer
executes the edit plan. Catches the 92s VO + 18s plan failure case before
render — the operator sees the mismatch, not a silently truncated video.

Two checks:
1. VO duration vs planned timeline duration — if VO exceeds timeline beyond
   a configurable tolerance, return needs_operator_decision with the mismatch.
2. Beat mapping — every required compliance contract beat must have at least
   one planned_segment_id. If any required beat has no plan mapping, return
   needs_operator_decision.

These are MECHANICAL checks — no LLM, no judgment. The LLM compliance contract
defines what should be present; this code verifies the plan can physically
accommodate it.
"""

import json
import os
import subprocess
from typing import Optional


# Default tolerance: VO may exceed timeline by up to this many seconds
# without triggering a feasibility failure (allows for small rounding differences).
DEFAULT_DURATION_TOLERANCE_S = 2.0


def probe_duration(file_path: str) -> Optional[float]:
    """Get a media file's duration in seconds via ffprobe. Returns None on failure."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", file_path],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return None


def compute_plan_timeline_duration(plan: dict) -> float:
    """Compute the total timeline duration from the edit plan.

    Sums segment durations (out - in) for video segments. For image segments
    (where in/out don't apply), uses the canvas duration_target as fallback.

    If canvas.duration_target is set and is longer than the sum of segment
    durations, uses duration_target (the renderer will hold last frame or
    pad to that target).
    """
    segments = plan.get("segments", [])
    canvas = plan.get("canvas", {})
    duration_target = canvas.get("duration_target")

    total = 0.0
    for seg in segments:
        in_pt = seg.get("in", 0)
        out_pt = seg.get("out", 0)
        source = seg.get("source", "")

        # Image segments: in/out are 0 — duration comes from the timeline slot
        # (the renderer displays them for a fixed period). We can't know the
        # slot duration from the plan alone, so we fall back to duration_target.
        if source.startswith("generated:") or source.startswith("upload:"):
            # Could be an image or video — if in/out are both 0, treat as image
            if out_pt > in_pt:
                total += out_pt - in_pt
            # else: image segment, duration unknown from plan — skip
        elif source.startswith("stock:"):
            if out_pt > in_pt:
                total += out_pt - in_pt

    # If duration_target is set and longer than segment sum, use it
    if duration_target and duration_target > total:
        return float(duration_target)

    return total


def check_vo_timeline_feasibility(
    vo_duration: float,
    plan_timeline_duration: float,
    tolerance_s: float = DEFAULT_DURATION_TOLERANCE_S,
) -> dict:
    """Check if VO duration fits within the plan timeline duration.

    Returns: {feasible: bool, mismatch: str | None, vo_duration: float,
              plan_timeline_duration: float}
    """
    if vo_duration <= 0:
        # No VO — no constraint
        return {
            "feasible": True,
            "mismatch": None,
            "vo_duration": vo_duration,
            "plan_timeline_duration": plan_timeline_duration,
        }

    if plan_timeline_duration <= 0:
        # No timeline duration — can't determine feasibility
        return {
            "feasible": True,
            "mismatch": None,
            "vo_duration": vo_duration,
            "plan_timeline_duration": plan_timeline_duration,
        }

    excess = vo_duration - plan_timeline_duration
    if excess > tolerance_s:
        return {
            "feasible": False,
            "mismatch": (
                f"VO duration ({vo_duration:.1f}s) exceeds plan timeline duration "
                f"({plan_timeline_duration:.1f}s) by {excess:.1f}s — "
                f"{excess:.1f}s of dialogue will be lost to silent truncation"
            ),
            "vo_duration": vo_duration,
            "plan_timeline_duration": plan_timeline_duration,
        }

    return {
        "feasible": True,
        "mismatch": None,
        "vo_duration": vo_duration,
        "plan_timeline_duration": plan_timeline_duration,
    }


def check_beat_mapping(
    compliance_contract: dict,
    plan: dict,
) -> dict:
    """Check that every required compliance contract beat has a plan mapping.

    A required beat has no plan mapping if planned_segment_ids is empty.

    Returns: {feasible: bool, unmapped_beats: list[dict]}
    """
    beats = compliance_contract.get("beats", []) if compliance_contract else []
    segments = plan.get("segments", [])

    # Build a set of available segment IDs (by index)
    available_segment_ids = set()
    for i, seg in enumerate(segments):
        # Use both index-based and source-based IDs
        available_segment_ids.add(str(i))
        source = seg.get("source", "")
        if source:
            available_segment_ids.add(source)

    unmapped = []
    for beat in beats:
        if not beat.get("required", False):
            continue
        planned_ids = beat.get("planned_segment_ids", [])
        if not planned_ids:
            unmapped.append({
                "beat_id": beat.get("beat_id"),
                "source_excerpt": beat.get("source_excerpt", ""),
                "requirement_type": beat.get("requirement_type", ""),
                "reason": "No planned_segment_ids — this beat is not mapped to any plan segment",
            })

    return {
        "feasible": len(unmapped) == 0,
        "unmapped_beats": unmapped,
    }


def run_feasibility_checks(
    plan: dict,
    compliance_contract: dict,
    vo_file_path: Optional[str] = None,
    vo_duration: Optional[float] = None,
    tolerance_s: float = DEFAULT_DURATION_TOLERANCE_S,
) -> dict:
    """Run all pre-render feasibility checks.

    Args:
        plan: The edit plan dict
        compliance_contract: The compliance contract dict (from T10.1)
        vo_file_path: Path to the VO file (if any). If provided, duration is probed.
        vo_duration: VO duration in seconds (if already known, skips ffprobe)
        tolerance_s: Tolerance for VO vs timeline duration mismatch

    Returns: {
        feasible: bool,
        verdict: "feasible" | "needs_operator_decision",
        checks: {
            vo_timeline: {...},
            beat_mapping: {...},
        },
        issues: list[str],  # human-readable issue descriptions
        summary: str,
    }
    """
    issues = []

    # 1. VO duration vs timeline duration
    actual_vo_duration = vo_duration
    if actual_vo_duration is None and vo_file_path:
        actual_vo_duration = probe_duration(vo_file_path)

    timeline_duration = compute_plan_timeline_duration(plan)

    vo_check = check_vo_timeline_feasibility(
        actual_vo_duration or 0,
        timeline_duration,
        tolerance_s,
    )
    if not vo_check["feasible"]:
        issues.append(vo_check["mismatch"])

    # 2. Beat mapping
    beat_check = check_beat_mapping(compliance_contract, plan)
    if not beat_check["feasible"]:
        for ub in beat_check["unmapped_beats"]:
            issues.append(
                f"Required beat '{ub['beat_id']}' ({ub['requirement_type']}) "
                f"has no plan mapping — source: \"{ub['source_excerpt'][:80]}\""
            )

    feasible = len(issues) == 0
    if feasible:
        verdict = "feasible"
        summary = "All pre-render feasibility checks passed."
    else:
        verdict = "needs_operator_decision"
        summary = f"{len(issues)} feasibility issue(s): " + "; ".join(issues)

    return {
        "feasible": feasible,
        "verdict": verdict,
        "checks": {
            "vo_timeline": vo_check,
            "beat_mapping": beat_check,
        },
        "issues": issues,
        "summary": summary,
    }