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


# ── VF-VS-403: Multi-event coverage + generated-motion check ─────────────────


def check_visual_event_coverage(
    beats: list[dict],
    vo_segments: list[dict] | None = None,
    *,
    tolerance_s: float,
) -> dict:
    """Check that every beat's ``visual_events`` cover the beat's VO span.

    Per AMENDMENT-010 Condition 5 / VF-VS-403: multi-event coverage validation.
    Missing event coverage → block. Events must:
    - Cover the beat's full VO span (no gaps beyond tolerance)
    - Not overlap beyond tolerance
    - Each event's time_range must be within the beat's span

    Args:
        beats: Contract beats (each may carry ``visual_events`` and
            ``intended_duration_sec``).
        vo_segments: Measured VO segments ``[{beat_id, duration, text}, ...]``.
            When provided, the beat's VO span is the measured duration. When
            absent, falls back to ``intended_duration_sec.max``.

    Returns: {feasible: bool, issues: list[dict]}
    """
    vo_by_beat: dict[str, float] = {}
    if vo_segments:
        for seg in vo_segments:
            bid = seg.get("beat_id", "")
            vo_by_beat[bid] = float(seg.get("duration", 0.0))

    issues: list[dict] = []
    for beat in beats:
        bid = beat.get("beat_id", "?")
        events = beat.get("visual_events") or []
        if not events:
            # No events — degradation path (VF-VS-401) synthesizes one.
            # Not a coverage failure here.
            continue

        # Determine the beat's span
        span = vo_by_beat.get(bid)
        if span is None:
            dur = beat.get("intended_duration_sec") or {}
            if isinstance(dur, dict):
                span = float(dur.get("max", 0.0))
            else:
                span = 0.0

        if span <= 0:
            # Can't verify coverage without a span — skip
            continue

        # Sort events by start time
        sorted_events = sorted(events, key=lambda e: (e.get("time_range", {}).get("start", 0)))
        prev_end = 0.0
        for i, ev in enumerate(sorted_events):
            tr = ev.get("time_range") or {}
            start = float(tr.get("start", 0.0))
            end = float(tr.get("end", 0.0))

            # Check event within beat span
            if start < -tolerance_s or end > span + tolerance_s:
                issues.append({
                    "beat_id": bid,
                    "event_id": ev.get("event_id", f"[{i}]"),
                    "type": "out_of_bounds",
                    "detail": f"Event time_range [{start:.1f}-{end:.1f}]s outside beat span [0-{span:.1f}]s",
                })

            # Check for gap
            gap = start - prev_end
            if i > 0 and gap > tolerance_s:
                issues.append({
                    "beat_id": bid,
                    "event_id": ev.get("event_id", f"[{i}]"),
                    "type": "gap",
                    "detail": f"Gap of {gap:.1f}s between event {sorted_events[i-1].get('event_id', f'[{i-1}]')} and this event — beat span not covered",
                })

            # Check for overlap
            if i > 0 and gap < -tolerance_s:
                issues.append({
                    "beat_id": bid,
                    "event_id": ev.get("event_id", f"[{i}]"),
                    "type": "overlap",
                    "detail": f"Overlap of {abs(gap):.1f}s with previous event — events must not overlap",
                })

            prev_end = max(prev_end, end)

        # Check total coverage
        coverage = prev_end  # events are sorted; prev_end is the last end
        uncovered = span - coverage
        if uncovered > tolerance_s:
            issues.append({
                "beat_id": bid,
                "event_id": None,
                "type": "incomplete_coverage",
                "detail": f"Events cover [{0:.1f}-{coverage:.1f}]s but beat span is {span:.1f}s — {uncovered:.1f}s uncovered",
            })

    return {
        "feasible": len(issues) == 0,
        "issues": issues,
    }


def check_talking_head_motion_coverage(
    beats: list[dict],
    vo_segments: list[dict] | None = None,
    motion_durations: dict[str, float] | None = None,
    *,
    shortfall_ratio: float,
) -> dict:
    """Check requested generated-motion time against planned moving source time.

    The Visual Director makes the semantic decision in ``visual_events``.
    This function only compares its explicit ``generated_motion`` time ranges
    with mechanically measured motion in the proposed edit plan. Non-motion
    events are explicit cutaways and do not consume the motion budget.
    """
    motion_durations = motion_durations or {}
    vo_by_beat: dict[str, float] = {}
    if vo_segments:
        for seg in vo_segments:
            bid = seg.get("beat_id", "")
            vo_by_beat[bid] = float(seg.get("duration", 0.0))

    issues: list[dict] = []
    for beat in beats:
        bid = beat.get("beat_id", "?")
        events = beat.get("visual_events") or []
        motion_events = [
            event for event in events
            if event.get("source_policy") == "generated_motion"
        ]
        if not motion_events:
            continue

        span = vo_by_beat.get(bid)
        if span is None:
            span = max(
                (
                    float((event.get("time_range") or {}).get("end", 0.0))
                    for event in events
                ),
                default=0.0,
            )

        required_motion = sum(
            max(
                0.0,
                min(
                    span,
                    float((event.get("time_range") or {}).get("end", 0.0)),
                ) - max(
                    0.0,
                    float((event.get("time_range") or {}).get("start", 0.0)),
                ),
            )
            for event in motion_events
        )
        if required_motion <= 0:
            continue

        available_motion = motion_durations.get(bid, 0.0)
        if available_motion >= required_motion:
            continue

        shortfall = required_motion - available_motion
        if shortfall / required_motion < shortfall_ratio:
            continue

        issues.append({
            "beat_id": bid,
            "type": "generated_motion_shortfall",
            "detail": (
                f"Beat '{bid}' requests {required_motion:.1f}s of generated motion "
                f"but the plan contains only {available_motion:.1f}s of moving "
                f"source (shortfall {shortfall:.1f}s). Add an explicit cutaway "
                f"event or capture more motion before render."
            ),
        })

    return {
        "feasible": len(issues) == 0,
        "issues": issues,
    }


def run_feasibility_checks(
    plan: dict,
    compliance_contract: dict,
    vo_file_path: Optional[str] = None,
    vo_duration: Optional[float] = None,
    tolerance_s: float = DEFAULT_DURATION_TOLERANCE_S,
    beats: Optional[list[dict]] = None,
    vo_segments: Optional[list[dict]] = None,
    motion_durations: Optional[dict[str, float]] = None,
    event_coverage_tolerance_s: Optional[float] = None,
    motion_shortfall_ratio: Optional[float] = None,
) -> dict:
    """Run all pre-render feasibility checks.

    Args:
        plan: The edit plan dict
        compliance_contract: The compliance contract dict (from T10.1)
        vo_file_path: Path to the VO file (if any). If provided, duration is probed.
        vo_duration: VO duration in seconds (if already known, skips ffprobe)
        tolerance_s: Tolerance for VO vs timeline duration mismatch
        beats: Contract beats for visual-event coverage checks (VF-VS-403).
            When None, the checks are skipped.
        vo_segments: Measured VO segments for event and motion coverage checks.
        motion_durations: ``{beat_id: available_motion_seconds}`` for motion checks.
        event_coverage_tolerance_s: Configured event gap/overlap tolerance.
        motion_shortfall_ratio: Configured generated-motion shortfall tolerance.

    Returns: {
        feasible: bool,
        verdict: "feasible" | "needs_operator_decision",
        checks: {
            vo_timeline: {...},
            beat_mapping: {...},
            visual_event_coverage: {...},   # VF-VS-403
            talking_head_motion: {...},     # compatibility key: generated-motion coverage
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

    # 3. Visual event coverage (VF-VS-403)
    event_check = {"feasible": True, "issues": []}
    if beats is not None:
        if event_coverage_tolerance_s is None:
            raise ValueError("event_coverage_tolerance_s is required when beats are provided")
        event_check = check_visual_event_coverage(
            beats,
            vo_segments,
            tolerance_s=event_coverage_tolerance_s,
        )
        if not event_check["feasible"]:
            for iss in event_check["issues"]:
                issues.append(
                    f"Beat '{iss['beat_id']}' visual event {iss['type']}: {iss['detail']}"
                )

    # 4. Visual Director generated-motion coverage (VF-VS-403)
    talking_check = {"feasible": True, "issues": []}
    if beats is not None:
        if motion_shortfall_ratio is None:
            raise ValueError("motion_shortfall_ratio is required when beats are provided")
        talking_check = check_talking_head_motion_coverage(
            beats,
            vo_segments,
            motion_durations,
            shortfall_ratio=motion_shortfall_ratio,
        )
        if not talking_check["feasible"]:
            for iss in talking_check["issues"]:
                issues.append(iss["detail"])

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
            "visual_event_coverage": event_check,
            "talking_head_motion": talking_check,
        },
        "issues": issues,
        "summary": summary,
    }