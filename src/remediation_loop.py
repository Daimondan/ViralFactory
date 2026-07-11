"""
ViralFactory — Bounded Remediation Loop (T10.5 — AMENDMENT-008)

The render → review → remediate → re-render loop, max 3 rounds.

Two hard conditions (architect-mandated):
1. Text-boundary firewall: SHA-256 of platform_content locked at loop entry.
   Any remediation action that would modify platform_content → rejected →
   needs_operator_decision.
2. Config-driven cost guard: max_remediation_cost_usd in models.yaml under
   asset_review block. If absent, remediation is disabled (review-only, no
   auto-fix). If exceeded, stop with needs_operator_decision + cost summary.

Safe remediation scope:
- Edit-plan timing/segment selection
- Media generation prompts
- Replacement media
- Caption rendering/styling
- Audio mixing
- Renderer mechanics

The loop NEVER modifies approved platform_content text. If the only fix
requires changing the script, it escalates to needs_operator_decision.
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Default max rounds (config can override)
DEFAULT_MAX_ROUNDS = 3


def compute_platform_content_hash(platform_content) -> str:
    """Compute SHA-256 of platform_content JSON for the text-boundary firewall.

    The hash is computed on the canonical JSON serialization (sorted keys,
    no extra whitespace) so that identical content always produces the same hash.
    """
    if isinstance(platform_content, str):
        content = platform_content
    else:
        content = json.dumps(platform_content, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def verify_text_boundary(original_hash: str, platform_content) -> bool:
    """Verify that platform_content has not changed since loop entry.

    Returns True if the hash matches (text is unchanged), False otherwise.
    """
    current_hash = compute_platform_content_hash(platform_content)
    return current_hash == original_hash


def check_remediation_cost(
    cumulative_cost: float,
    max_cost: Optional[float],
    new_action_cost: float,
) -> dict:
    """Check if a remediation action would exceed the cost cap.

    Returns: {within_budget: bool, reason: str | None, cumulative: float}
    """
    if max_cost is None:
        # Cost guard absent → remediation disabled (review-only)
        return {
            "within_budget": False,
            "reason": "Remediation disabled — max_remediation_cost_usd not set in config (review-only mode)",
            "cumulative": cumulative_cost,
        }

    new_total = cumulative_cost + new_action_cost
    if new_total > max_cost:
        return {
            "within_budget": False,
            "reason": f"Cumulative remediation cost (${new_total:.2f}) would exceed cap (${max_cost:.2f})",
            "cumulative": new_total,
        }

    return {
        "within_budget": True,
        "reason": None,
        "cumulative": new_total,
    }


def run_remediation_loop(
    asset_id: int,
    media_id: int,
    plan_id: int,
    platform_content,
    approved_script: str,
    compliance_contract: dict,
    edit_plan: dict,
    final_file_path: str,
    models_config: dict,
    db_path: str,
    business_slug: str = None,
    vo_transcript: str = "",
    vo_duration: float = 0,
    keyframe_descriptions: str = "",
    prior_review_findings: list = None,
    render_fn=None,
    prompts_dir: str = "prompts",
) -> dict:
    """Run the bounded remediation loop.

    Args:
        render_fn: callable(plan, asset_id, ...) -> {path, duration, ...}
                   Called to re-render after remediation actions are applied.
                   If None, the loop is review-only (no re-render).

    Returns: {
        final_verdict: str,  # compliant | non_convergent | cost_cap | needs_operator_decision
        rounds: list[dict],  # per-round history
        total_cost_usd: float,
        platform_content_hash: str,
        summary: str,
    }
    """
    from asset_review import AssetReviewer
    from compliance_validators import validate_remediation_instruction

    # ── Condition 1: Text-boundary firewall — lock platform_content hash ──
    original_hash = compute_platform_content_hash(platform_content)

    # ── Condition 2: Cost guard — read config ──
    review_config = models_config.get("asset_review", {})
    max_cost = review_config.get("max_remediation_cost_usd")
    max_rounds = review_config.get("max_remediation_rounds", DEFAULT_MAX_ROUNDS)
    remediation_enabled = max_cost is not None

    reviewer = AssetReviewer(models_config, db_path=db_path, prompts_dir=prompts_dir)
    store = None
    try:
        from pipeline import PipelineStore
        store = PipelineStore(db_path)
    except Exception:
        pass

    cumulative_cost = 0.0
    rounds = []
    current_plan = edit_plan
    current_file_path = final_file_path

    # ── Round 0: Initial compliance review ──
    round_num = 0
    review_result = reviewer.run_compliance_review(
        asset_id=asset_id,
        media_id=media_id,
        approved_script=approved_script,
        compliance_contract=compliance_contract,
        edit_plan=current_plan,
        final_file_path=current_file_path,
        vo_transcript=vo_transcript,
        vo_duration=vo_duration,
        keyframe_descriptions=keyframe_descriptions,
        prior_review_findings=prior_review_findings,
        remediation_round=round_num,
        business_slug=business_slug,
        models_config=models_config,
    )

    verdict = review_result["verdict"]
    rounds.append({
        "round": round_num,
        "verdict": verdict,
        "review_id": review_result.get("review_id"),
        "actions_taken": [],
        "cost_usd": 0,
        "summary": review_result.get("summary", ""),
    })

    if store and plan_id:
        store.append_review_round(plan_id, rounds[-1])

    # If already compliant or needs operator → stop
    if verdict == "compliant":
        return {
            "final_verdict": "compliant",
            "rounds": rounds,
            "total_cost_usd": cumulative_cost,
            "platform_content_hash": original_hash,
            "summary": "Compliant on first review — no remediation needed.",
        }

    if verdict == "needs_operator_decision":
        return {
            "final_verdict": "needs_operator_decision",
            "rounds": rounds,
            "total_cost_usd": cumulative_cost,
            "platform_content_hash": original_hash,
            "summary": review_result.get("summary", "Needs operator decision."),
        }

    # ── Remediation disabled → review-only ──
    if not remediation_enabled:
        return {
            "final_verdict": "needs_operator_decision",
            "rounds": rounds,
            "total_cost_usd": cumulative_cost,
            "platform_content_hash": original_hash,
            "summary": (
                f"Compliance review found issues (verdict: {verdict}) but "
                f"remediation is disabled (max_remediation_cost_usd not set). "
                f"Needs operator decision."
            ),
        }

    # ── Remediation rounds (1..max_rounds) ──
    for round_num in range(1, max_rounds + 1):
        # Call the remediation instruction prompt
        try:
            from llm_adapter import LLMAdapter
            adapter = LLMAdapter(models_config, db_path=db_path, prompts_dir=prompts_dir)

            remediation_result = adapter.complete(
                prompt_file="assembly/remediation_instruction_v1.md",
                variables={
                    "approved_script": approved_script[:6000],
                    "compliance_contract_json": json.dumps(compliance_contract, indent=2)[:4000],
                    "edit_plan_json": json.dumps(current_plan, indent=2)[:4000],
                    "compliance_review_json": json.dumps({
                        "verdict": verdict,
                        "coverage": review_result.get("coverage", []),
                        "issues": review_result.get("issues", []),
                    }, indent=2)[:3000],
                    "media_inventory": "(not available in this context)",
                },
                schema=None,
                backend="default",
                context=f"T10.5 remediation instruction round {round_num} for asset {asset_id}",
                business_slug=business_slug,
                profile="default",
            )

            validated_remediation = validate_remediation_instruction(remediation_result)

        except Exception as e:
            logger.warning(f"Remediation instruction LLM call failed: {e}")
            rounds.append({
                "round": round_num,
                "verdict": "needs_operator_decision",
                "review_id": None,
                "actions_taken": [],
                "cost_usd": 0,
                "summary": f"Remediation LLM call failed: {str(e)[:200]}",
            })
            if store and plan_id:
                store.append_review_round(plan_id, rounds[-1])
            return {
                "final_verdict": "needs_operator_decision",
                "rounds": rounds,
                "total_cost_usd": cumulative_cost,
                "platform_content_hash": original_hash,
                "summary": f"Remediation LLM call failed in round {round_num}.",
            }

        # Check if LLM escalated (can't fix without changing approved text)
        if validated_remediation.get("escalate", False):
            rounds.append({
                "round": round_num,
                "verdict": "needs_operator_decision",
                "review_id": None,
                "actions_taken": [],
                "cost_usd": 0,
                "summary": validated_remediation.get("summary", "Escalated — cannot fix without changing approved text."),
            })
            if store and plan_id:
                store.append_review_round(plan_id, rounds[-1])
            return {
                "final_verdict": "needs_operator_decision",
                "rounds": rounds,
                "total_cost_usd": cumulative_cost,
                "platform_content_hash": original_hash,
                "summary": validated_remediation.get("summary", "Escalated."),
            }

        # ── Condition 1: Text-boundary firewall check ──
        # Verify the remediation actions don't propose changing platform_content
        # (The prompt explicitly prohibits this, but we verify mechanically.)
        # We check by verifying the hash hasn't changed after applying actions.
        # For now, the actions modify the PLAN, not the platform_content.
        # If a future action type could touch platform_content, we'd verify here.
        if not verify_text_boundary(original_hash, platform_content):
            logger.error("Text-boundary firewall violation: platform_content hash changed!")
            rounds.append({
                "round": round_num,
                "verdict": "needs_operator_decision",
                "review_id": None,
                "actions_taken": [],
                "cost_usd": 0,
                "summary": "Text-boundary firewall violation — platform_content was modified.",
            })
            if store and plan_id:
                store.append_review_round(plan_id, rounds[-1])
            return {
                "final_verdict": "needs_operator_decision",
                "rounds": rounds,
                "total_cost_usd": cumulative_cost,
                "platform_content_hash": original_hash,
                "summary": "Text-boundary firewall violation.",
            }

        # ── Condition 2: Cost guard check ──
        action_cost = validated_remediation.get("estimated_cost_usd", 0)
        cost_check = check_remediation_cost(cumulative_cost, max_cost, action_cost)
        if not cost_check["within_budget"]:
            rounds.append({
                "round": round_num,
                "verdict": "cost_cap",
                "review_id": None,
                "actions_taken": [],
                "cost_usd": action_cost,
                "summary": cost_check["reason"],
            })
            if store and plan_id:
                store.append_review_round(plan_id, rounds[-1])
            return {
                "final_verdict": "cost_cap",
                "rounds": rounds,
                "total_cost_usd": cumulative_cost,
                "platform_content_hash": original_hash,
                "summary": cost_check["reason"],
            }

        cumulative_cost += action_cost

        # ── Apply remediation actions to the plan ──
        actions = validated_remediation.get("actions", [])
        applied_actions = []
        for action in actions:
            action_type = action.get("type")
            target = action.get("target", "")
            change = action.get("change", {})

            # Apply the action to the plan (mechanical)
            modified_plan = _apply_remediation_action(current_plan, action_type, target, change)
            if modified_plan:
                current_plan = modified_plan
                applied_actions.append({
                    "action_id": action.get("action_id"),
                    "type": action_type,
                    "target": target,
                    "reason": action.get("reason", ""),
                })

        # ── Re-render with the modified plan ──
        if render_fn and applied_actions:
            try:
                render_result = render_fn(current_plan, asset_id)
                current_file_path = render_result.get("path", current_file_path)
            except Exception as e:
                logger.warning(f"Re-render failed in round {round_num}: {e}")
                rounds.append({
                    "round": round_num,
                    "verdict": "needs_operator_decision",
                    "review_id": None,
                    "actions_taken": applied_actions,
                    "cost_usd": action_cost,
                    "summary": f"Re-render failed: {str(e)[:200]}",
                })
                if store and plan_id:
                    store.append_review_round(plan_id, rounds[-1])
                return {
                    "final_verdict": "needs_operator_decision",
                    "rounds": rounds,
                    "total_cost_usd": cumulative_cost,
                    "platform_content_hash": original_hash,
                    "summary": f"Re-render failed in round {round_num}.",
                }

        # ── Re-review after remediation ──
        review_result = reviewer.run_compliance_review(
            asset_id=asset_id,
            media_id=media_id,
            approved_script=approved_script,
            compliance_contract=compliance_contract,
            edit_plan=current_plan,
            final_file_path=current_file_path,
            vo_transcript=vo_transcript,
            vo_duration=vo_duration,
            keyframe_descriptions=keyframe_descriptions,
            prior_review_findings=prior_review_findings,
            remediation_round=round_num,
            business_slug=business_slug,
            models_config=models_config,
        )

        verdict = review_result["verdict"]
        rounds.append({
            "round": round_num,
            "verdict": verdict,
            "review_id": review_result.get("review_id"),
            "actions_taken": applied_actions,
            "cost_usd": action_cost,
            "summary": review_result.get("summary", ""),
        })

        if store and plan_id:
            store.append_review_round(plan_id, rounds[-1])

        if verdict == "compliant":
            return {
                "final_verdict": "compliant",
                "rounds": rounds,
                "total_cost_usd": cumulative_cost,
                "platform_content_hash": original_hash,
                "summary": f"Compliant after {round_num} remediation round(s).",
            }

        if verdict == "needs_operator_decision":
            return {
                "final_verdict": "needs_operator_decision",
                "rounds": rounds,
                "total_cost_usd": cumulative_cost,
                "platform_content_hash": original_hash,
                "summary": review_result.get("summary", "Needs operator decision."),
            }

    # ── Max rounds reached without compliance → non_convergent ──
    return {
        "final_verdict": "non_convergent",
        "rounds": rounds,
        "total_cost_usd": cumulative_cost,
        "platform_content_hash": original_hash,
        "summary": (
            f"Non-convergent after {max_rounds} remediation round(s). "
            f"Total cost: ${cumulative_cost:.2f}. Needs operator decision."
        ),
    }


def _apply_remediation_action(
    plan: dict,
    action_type: str,
    target: str,
    change: dict,
) -> dict | None:
    """Apply a single remediation action to the plan.

    This is MECHANICAL — it modifies the plan based on the action type.
    It NEVER modifies platform_content (the text-boundary firewall ensures this).

    Returns the modified plan, or None if the action couldn't be applied.
    """
    import copy
    modified = copy.deepcopy(plan)

    if action_type == "revise_plan_timing":
        # target is like "canvas.duration_target" or "segments[2].out"
        if target == "canvas.duration_target":
            new_val = change.get("to")
            if new_val is not None:
                modified.setdefault("canvas", {})["duration_target"] = new_val
                return modified
        elif target.startswith("segments[") and "].out" in target:
            # Parse segment index
            try:
                idx = int(target.split("[")[1].split("]")[0])
                new_val = change.get("to")
                if new_val is not None and idx < len(modified.get("segments", [])):
                    modified["segments"][idx]["out"] = new_val
                    return modified
            except (ValueError, IndexError):
                pass

    elif action_type == "adjust_audio_mixing":
        if target == "audio.vo.ducking":
            new_val = change.get("to")
            if new_val is not None:
                modified.setdefault("audio", {}).setdefault("vo", {})["ducking"] = new_val
                return modified
        elif target == "audio.music.volume":
            new_val = change.get("to")
            if new_val is not None:
                modified.setdefault("audio", {}).setdefault("music", {})["volume"] = new_val
                return modified

    elif action_type == "adjust_caption_rendering":
        # target like "captions.burned_in" or "captions.style_ref"
        if target.startswith("captions."):
            field = target.split(".", 1)[1]
            new_val = change.get("to")
            if new_val is not None:
                modified.setdefault("captions", {})[field] = new_val
                return modified

    elif action_type == "adjust_renderer_mechanics":
        # target like "canvas.resolution"
        if target.startswith("canvas."):
            field = target.split(".", 1)[1]
            new_val = change.get("to")
            if new_val is not None:
                modified.setdefault("canvas", {})[field] = new_val
                return modified

    # regenerate_media_prompts and replacement_media require the media adapter
    # — they can't be applied to the plan directly. They would trigger a new
    # media generation call. For now, return None (not supported in plan-only mode).
    # The full implementation would integrate with the media adapter.

    return None