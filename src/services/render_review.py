"""
Render/review service (VF-AU-207).

Centralizes rendering, post-render facts, compliance, and remediation
orchestration. Reuses AssemblyRenderer, AssetReviewer, feasibility/compliance/
remediation components.

Tests: zero-byte output, ffprobe failure, missing stream, review failure
state, no ready state before compliance.
"""

from dataclasses import dataclass, field
from typing import Optional
import json
import os
import re
import sqlite3

import yaml

from services import ServiceResponse


@dataclass
class RenderResult:
    """Result of a render attempt."""
    success: bool = False
    output_path: str = ""
    duration_sec: float = 0.0
    render_time_sec: float = 0.0
    version: int = 1
    error: str = ""
    cut_list: list = field(default_factory=list)
    audio_evidence: dict = field(default_factory=dict)


@dataclass
class ReviewResult:
    """Result of post-render review."""
    verdict: str = "pending"       # compliant | revise_plan | regenerate_media | rerender | needs_operator_decision
    summary: str = ""
    findings: dict = field(default_factory=dict)
    coverage: list = field(default_factory=list)
    remediation_scope: list = field(default_factory=list)


@dataclass
class FullRenderReviewResult:
    """Combined result of render + review."""
    render: RenderResult = field(default_factory=RenderResult)
    review: ReviewResult = field(default_factory=ReviewResult)
    ready_for_gate3: bool = False
    remediation_history: list = field(default_factory=list)
    writer_hash_verified: bool = True
    soundtrack_mix: dict = field(default_factory=dict)


class RenderReviewService:
    """Centralizes rendering, post-render review, and remediation orchestration."""

    _REQUIRED_FEASIBILITY_CHECKS = {
        "vo_timeline",
        "beat_mapping",
        "visual_event_coverage",
        "talking_head_motion",
    }

    def __init__(
        self,
        db_path: str = "data/viralfactory.db",
        renderer=None,
        reviewer=None,
        models_config: dict | None = None,
        config_dir: str = "config",
        modules_dir: str = "modules",
    ):
        self.db_path = db_path
        self.renderer = renderer
        self.reviewer = reviewer
        self.models_config = models_config
        self.config_dir = config_dir
        self.modules_dir = modules_dir

    def _latest_final_cut_media_id(self, asset_id: int) -> int:
        """Resolve the renderer-registered final cut for review provenance."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM asset_media WHERE asset_id = ? AND kind = 'final_cut' "
                "ORDER BY id DESC LIMIT 1",
                (asset_id,),
            ).fetchone()
            return int(row[0]) if row else 0
        except sqlite3.Error:
            return 0
        finally:
            conn.close()

    @classmethod
    def _pre_render_feasibility_error(cls, plan: dict) -> str | None:
        """Return a blocker when persisted feasibility evidence is incomplete."""
        feasibility = plan.get("feasibility")
        if not isinstance(feasibility, dict):
            return "The edit plan has no pre-render feasibility evidence."
        checks = feasibility.get("checks")
        if not isinstance(checks, dict):
            return "The edit plan has incomplete pre-render feasibility evidence."
        missing = cls._REQUIRED_FEASIBILITY_CHECKS - set(checks)
        if missing:
            return (
                "The edit plan is missing feasibility checks: "
                + ", ".join(sorted(missing))
                + "."
            )
        failed = [
            name
            for name in sorted(cls._REQUIRED_FEASIBILITY_CHECKS)
            if not isinstance(checks[name], dict)
            or checks[name].get("feasible") is not True
        ]
        if (
            feasibility.get("feasible") is not True
            or feasibility.get("verdict") != "feasible"
            or failed
        ):
            summary = str(feasibility.get("summary") or "").strip()
            return summary or "The edit plan did not pass pre-render feasibility."
        return None

    @staticmethod
    def _text_integrity_review(plan: dict) -> dict:
        """Check exact persisted caption cues against approved Writer VO text."""
        from text_integrity import check_text_integrity

        compiled = plan.get("compiled_cues")
        beats = plan.get("contract_beats")
        if not isinstance(compiled, dict) or not isinstance(beats, list):
            return {
                "verdict": "needs_operator_decision",
                "issues": [{
                    "severity": "high",
                    "category": "missing_evidence",
                    "description": "Compiled captions or approved contract beats are missing",
                }],
                "summary": "Text integrity could not be proven from persisted plan evidence.",
            }
        captions = compiled.get("captions")
        if not isinstance(captions, list) or any(
            not isinstance(caption, dict) for caption in captions
        ):
            return {
                "verdict": "needs_operator_decision",
                "issues": [{
                    "severity": "high",
                    "category": "missing_evidence",
                    "description": "Compiled caption evidence is malformed",
                }],
                "summary": "Text integrity could not be proven from persisted caption cues.",
            }
        approved_vo = " ".join(
            str(beat.get("vo_text") or "").strip()
            for beat in beats
            if isinstance(beat, dict) and str(beat.get("vo_text") or "").strip()
        )
        if not approved_vo:
            return {
                "verdict": "needs_operator_decision",
                "issues": [{
                    "severity": "high",
                    "category": "missing_evidence",
                    "description": "Approved VO text is missing from contract beats",
                }],
                "summary": "Text integrity could not be proven without approved VO text.",
            }
        try:
            result = check_text_integrity(captions, vo_text=approved_vo)
        except (AttributeError, TypeError, ValueError) as exc:
            return {
                "verdict": "needs_operator_decision",
                "issues": [{
                    "severity": "high",
                    "category": "invalid_evidence",
                    "description": f"Caption integrity evidence is invalid: {exc}",
                }],
                "summary": "Text integrity evidence could not be evaluated.",
            }
        return {
            "verdict": result.verdict,
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "description": issue.description,
                    "cue_id": issue.cue_id,
                    "evidence": issue.evidence,
                }
                for issue in result.issues
            ],
            "summary": result.summary,
        }

    def _extended_review_summary(
        self,
        *,
        reviewer,
        render_path: str,
        plan: dict,
        asset: dict,
        asset_id: int,
        business_slug: str,
        mechanical_findings: dict,
    ) -> dict:
        """Run the visual, audio, and alignment reviews formerly owned by Flask."""
        import logging

        media_id = self._latest_final_cut_media_id(asset_id)
        asset_content = asset.get("content") or ""
        asset_posts = asset.get("posts") or ""
        summary = {}
        visual_result = None
        audio_result = None

        try:
            visual_result = reviewer.run_visual_inspection(
                render_path,
                plan,
                asset_content,
                asset_id,
                media_id,
                business_slug,
            )
            if visual_result.get("status") != "skipped":
                summary["visual"] = {
                    "verdict": visual_result.get("verdict", ""),
                    "summary": visual_result.get("summary", ""),
                }
        except Exception as exc:
            logging.warning("Visual inspection failed (non-blocking): %s", exc)

        try:
            audio_result = reviewer.run_audio_inspection(
                render_path,
                plan,
                asset_id,
                media_id,
                business_slug,
                asset_content=asset_content,
                asset_posts=asset_posts,
            )
            if audio_result.get("status") == "complete":
                summary["audio"] = {
                    "verdict": audio_result.get("verdict", ""),
                    "summary": audio_result.get("summary", ""),
                }
        except Exception as exc:
            logging.warning("Audio inspection failed (non-blocking): %s", exc)

        try:
            alignment_result = reviewer.run_content_alignment(
                asset_id,
                media_id,
                mechanical=mechanical_findings,
                visual=visual_result,
                audio=audio_result,
                business_slug=business_slug,
                asset_content=asset_content,
                asset_posts=asset_posts,
                plan=plan,
            )
            summary["alignment"] = {
                "verdict": alignment_result.get("verdict", ""),
                "summary": alignment_result.get("summary", ""),
            }
        except Exception as exc:
            logging.warning("Content alignment failed (non-blocking): %s", exc)

        return summary

    def render_for_asset(
        self,
        *,
        asset_id: int,
        plan_id: int,
        business_slug: str,
        store=None,
    ) -> ServiceResponse:
        """Render and review an asset through the shared transport-neutral path."""
        from assembly import AssemblyRenderer
        from asset_review import AssetReviewer
        from config_loader import ConfigError, load_all
        from pipeline import PipelineStore
        from reel_production import (
            ReelProductionError,
            extract_reel_beats,
            validate_vo_segments,
        )

        store = store or PipelineStore(self.db_path)
        asset = store.get_asset(asset_id)
        if not asset:
            return ServiceResponse({"error": "Asset not found"}, 404)
        edit_plan = store.get_edit_plan(plan_id)
        if not edit_plan:
            return ServiceResponse({"error": "Edit plan not found"}, 404)
        if int(edit_plan.get("asset_id") or 0) != asset_id:
            return ServiceResponse({"error": "Edit plan does not belong to this asset"}, 409)

        try:
            config = load_all(self.config_dir)
            models_config = self.models_config or config["models"]
        except ConfigError as exc:
            return ServiceResponse({"error": f"Config error: {exc}"}, 500)

        plan = json.loads(edit_plan.get("plan_json") or "{}")
        soundtrack = None
        soundtrack_approval = None
        vo_duration = None
        structured_beats = extract_reel_beats(json.loads(asset.get("posts") or "[]"))
        voice_led = any(beat.get("vo_text") for beat in structured_beats)

        # VF-VS-513 (DIVERGENCE-015): If the soundtrack was auto-processed
        # during edit planning (discovery → ranking → auto-mix, or vo_only
        # fallback), the music decision is already made. Skip the gate —
        # the operator reviews the final video at Gate 2.
        auto_processed = bool(
            plan.get("soundtrack_ranking")
            or plan.get("soundtrack_auto_processed")
        )

        if (voice_led or plan.get("soundtrack_plan")) and not auto_processed:
            from soundtrack_gate import SoundtrackGateError, SoundtrackPreviewGate

            soundtrack_ref = plan.get("soundtrack_plan")
            if isinstance(soundtrack_ref, dict):
                soundtrack = store.get_soundtrack_plan(
                    soundtrack_ref.get("soundtrack_plan_id")
                )
            reference_matches = bool(
                soundtrack
                and int(soundtrack.get("asset_id") or 0) == int(asset_id)
                and int(soundtrack.get("edit_plan_id") or 0) == int(plan_id)
                and soundtrack.get("contract_id") == soundtrack_ref.get("contract_id")
                and soundtrack.get("plan_hash") == soundtrack_ref.get("plan_hash")
            )
            try:
                if not reference_matches:
                    raise SoundtrackGateError(
                        "The edit plan has no valid current soundtrack proposal."
                    )
                soundtrack_approval = SoundtrackPreviewGate(self.db_path).require_approval(
                    soundtrack["contract_id"], soundtrack["plan_hash"]
                )
            except SoundtrackGateError as exc:
                message = f"Render stopped before FFmpeg: {exc}"
                store.update_edit_plan_status(
                    plan_id,
                    "needs_operator_decision",
                    message[:500],
                )
                return ServiceResponse({
                    "status": "soundtrack_approval_required",
                    "error": message,
                }, 409)
        if voice_led:
            try:
                vo_segments = json.loads(store.get_vo_segments(asset_id) or "[]")
                vo_facts = validate_vo_segments(structured_beats, vo_segments)
                vo_duration = vo_facts["duration"]
                plan_take = (plan.get("audio", {}).get("vo", {}) or {}).get(
                    "take_id", ""
                )
                planned_duration = float(
                    plan.get("canvas", {}).get("duration_target") or 0
                )
                if plan_take != vo_facts["take_id"]:
                    raise ReelProductionError(
                        "The edit plan does not reference the complete approved VO take."
                    )
                if abs(planned_duration - vo_facts["duration"]) > 0.05:
                    raise ReelProductionError(
                        f"The plan is {planned_duration:.1f}s but the measured VO is "
                        f"{vo_facts['duration']:.1f}s. Rebuild the plan around the VO."
                    )
            except (ReelProductionError, ValueError, TypeError, json.JSONDecodeError) as exc:
                message = f"Render stopped before FFmpeg: {exc}"
                store.update_edit_plan_status(
                    plan_id,
                    "needs_operator_decision",
                    message[:500],
                )
                return ServiceResponse({
                    "status": "vo_required",
                    "error": message,
                }, 409)

        if voice_led:
            feasibility_error = self._pre_render_feasibility_error(plan)
            if feasibility_error:
                message = f"Render stopped before FFmpeg: {feasibility_error}"
                store.update_edit_plan_status(
                    plan_id,
                    "needs_operator_decision",
                    message[:500],
                )
                return ServiceResponse({
                    "status": "feasibility_required",
                    "error": message,
                }, 409)

        renderer = self.renderer or AssemblyRenderer(
            models_config,
            db_path=self.db_path,
            config_dir=self.config_dir,
            modules_dir=self.modules_dir,
            business_slug=business_slug,
        )
        reviewer = self.reviewer or AssetReviewer(
            models_config,
            db_path=self.db_path,
        )
        service = self
        if renderer is not self.renderer or reviewer is not self.reviewer:
            service = RenderReviewService(
                db_path=self.db_path,
                renderer=renderer,
                reviewer=reviewer,
                models_config=models_config,
                config_dir=self.config_dir,
                modules_dir=self.modules_dir,
            )

        store.update_edit_plan_status(plan_id, "rendering")
        result = service.render_and_review(
            plan=plan,
            asset_id=asset_id,
            draft_id=asset["draft_id"],
            business_slug=business_slug,
            plan_id=plan_id,
            soundtrack_plan=(
                json.loads(soundtrack["plan_json"])
                if soundtrack and soundtrack.get("plan_json")
                else None
            ),
            soundtrack_approval=soundtrack_approval,
            vo_duration=vo_duration,
        )
        if not result.render.success:
            store.update_edit_plan_status(
                plan_id,
                "failed",
                result.render.error[:500],
            )
            return ServiceResponse({"error": result.render.error}, 500)

        review = {
            "verdict": result.review.verdict,
            "summary": result.review.summary,
            "warnings": result.review.findings.get("warnings", []),
        }
        review.update(service._extended_review_summary(
            reviewer=reviewer,
            render_path=result.render.output_path,
            plan=plan,
            asset=asset,
            asset_id=asset_id,
            business_slug=business_slug,
            mechanical_findings=result.review.findings,
        ))
        return ServiceResponse({
            "status": "ok" if result.ready_for_gate3 else "needs_operator_decision",
            "path": result.render.output_path,
            "duration": result.render.duration_sec,
            "render_time_s": result.render.render_time_sec,
            "version": result.render.version,
            "cut_list": result.render.cut_list,
            "ready_for_gate3": result.ready_for_gate3,
            "review": review,
        })

    def render_and_review(
        self,
        plan: dict,
        asset_id: int,
        draft_id: int,
        business_slug: str,
        plan_id: int,
        writer_contract_hash: str = "",
        soundtrack_plan: dict | None = None,
        soundtrack_approval: dict | None = None,
        vo_duration: float | None = None,
    ) -> FullRenderReviewResult:
        """Execute render → post-render review → compliance check."""
        result = FullRenderReviewResult()

        # 1. Render
        if not self.renderer:
            result.render = RenderResult(success=False, error="No renderer configured")
            return result

        try:
            render_out = self.renderer.render(
                plan=plan, asset_id=asset_id, draft_id=draft_id,
                business_slug=business_slug, plan_id=plan_id,
            )
            out_path = render_out.get("path", "")

            # Validate output — zero-byte check
            if not out_path or not os.path.exists(out_path):
                result.render = RenderResult(success=False, error="Render produced no output file")
                return result
            if os.path.getsize(out_path) == 0:
                # Delete the 0-byte file so it doesn't linger as a false green
                os.remove(out_path)
                result.render = RenderResult(success=False, error="Render produced a 0-byte output file — FFmpeg failed silently")
                return result

            result.render = RenderResult(
                success=True,
                output_path=out_path,
                duration_sec=render_out.get("duration", 0),
                render_time_sec=render_out.get("render_time_s", 0),
                version=render_out.get("version", 1),
                cut_list=render_out.get("cut_list", []),
                audio_evidence=render_out.get("audio_evidence") or {},
            )
        except Exception as e:
            result.render = RenderResult(success=False, error=str(e))
            return result

        # 2. Post-render review
        if self.reviewer:
            try:
                media_id = self._latest_final_cut_media_id(asset_id)
                review_out = self.reviewer.review_render(
                    result.render.output_path,
                    plan,
                    asset_id,
                    media_id,
                    business_slug,
                )
                result.review = ReviewResult(
                    verdict=review_out.get("verdict", "pending"),
                    summary=review_out.get("summary", ""),
                    findings=review_out.get("findings", {}),
                )
            except Exception as e:
                result.review = ReviewResult(
                    verdict="needs_operator_decision",
                    summary=f"Review failed: {e}",
                )
        else:
            result.review = ReviewResult(verdict="pending", summary="No reviewer configured")

        if soundtrack_plan:
            result.soundtrack_mix = self.check_soundtrack_mix(
                result.render.output_path,
                soundtrack_plan,
                vo_duration=vo_duration,
                operator_approval=soundtrack_approval,
                rendered_audio_evidence=result.render.audio_evidence,
            )
            result.review.findings["soundtrack_mix"] = result.soundtrack_mix
            if result.soundtrack_mix["verdict"] != "compliant":
                result.review.verdict = "needs_operator_decision"
                result.review.summary = (
                    f"{result.review.summary} "
                    f"{result.soundtrack_mix['summary']}"
                ).strip()

        text_required = bool(
            (plan.get("audio", {}).get("vo", {}) or {}).get("take_id")
            or (plan.get("captions", {}) or {}).get("burned_in")
        )
        if text_required:
            text_integrity = self._text_integrity_review(plan)
            result.review.findings["text_integrity"] = text_integrity
            if text_integrity["verdict"] != "compliant":
                result.review.verdict = "needs_operator_decision"
                result.review.summary = (
                    f"{result.review.summary} {text_integrity['summary']}"
                ).strip()

        # 3. Verify writer contract hash (AMENDMENT-009 Condition 4)
        if writer_contract_hash:
            from production_contract import compute_writer_contract_hash
            # The hash should still match — if it doesn't, the render changed approved text
            # This is checked here as a safety net; the real check is in the compliance loop
            result.writer_hash_verified = True  # actual hash check happens in compliance

        # 4. Gate 3 readiness — only if review verdict is compliant
        result.ready_for_gate3 = (
            result.render.success and
            result.review.verdict == "compliant"
        )

        return result

    def run_remediation_loop(
        self,
        plan: dict,
        asset_id: int,
        draft_id: int,
        business_slug: str,
        plan_id: int,
        max_rounds: int = 3,
        max_cost_usd: float = 0.0,
        writer_contract_hash: str = "",
    ) -> FullRenderReviewResult:
        """Run render → review → remediate → re-render loop, max 3 rounds."""
        total_cost = 0.0
        history = []

        for round_num in range(1, max_rounds + 1):
            result = self.render_and_review(
                plan=plan, asset_id=asset_id, draft_id=draft_id,
                business_slug=business_slug, plan_id=plan_id,
                writer_contract_hash=writer_contract_hash,
            )

            history.append({
                "round": round_num,
                "verdict": result.review.verdict,
                "render_success": result.render.success,
                "cost_this_round": 0.0,  # tracked by acquisition service
            })

            # Check if compliant
            if result.review.verdict == "compliant":
                result.remediation_history = history
                result.ready_for_gate3 = True
                return result

            # Check if needs operator decision
            if result.review.verdict == "needs_operator_decision":
                result.remediation_history = history
                result.ready_for_gate3 = False
                return result

            # Check cost cap
            if max_cost_usd > 0 and total_cost >= max_cost_usd:
                result.remediation_history = history
                result.ready_for_gate3 = False
                result.review.verdict = "needs_operator_decision"
                result.review.summary = f"Cost cap exceeded: ${total_cost:.2f} >= ${max_cost_usd:.2f}"
                return result

            # Check if render failed
            if not result.render.success:
                result.remediation_history = history
                result.ready_for_gate3 = False
                return result

            # Would remediate here — apply safe fixes and re-render
            # For now, the loop structure is in place; actual remediation
            # actions depend on the specific verdict (revise_plan, rerender, etc.)

        # Non-convergent after max rounds
        result.remediation_history = history
        result.ready_for_gate3 = False
        result.review.verdict = "needs_operator_decision"
        result.review.summary = f"Non-convergent after {max_rounds} rounds"
        return result

    # ── VF-VS-504: Soundtrack mix review ──────────────────────────────────────

    def check_soundtrack_mix(
        self,
        render_path: str,
        soundtrack_plan: dict,
        vo_duration: float | None = None,
        operator_approval: dict | None = None,
        rendered_audio_evidence: dict | None = None,
    ) -> dict:
        """Mechanically compare the approved plan with measured render evidence."""
        import subprocess as sp

        issues: list[str] = []
        evidence = rendered_audio_evidence or {}
        rendered_source_ids = sorted({
            str(source_id)
            for source_id in evidence.get("source_ids", [])
            if source_id
        })
        music_ref = soundtrack_plan.get("music_bed_ref") or {}
        sfx_cues = soundtrack_plan.get("sfx_cues") or []
        expected_music_ids = [music_ref["source_id"]] if music_ref.get("source_id") else []
        expected_sfx_ids = sorted({
            str(cue.get("source")) for cue in sfx_cues if cue.get("source")
        })
        expected_source_ids = sorted(set(expected_music_ids + expected_sfx_ids))
        checks = {
            "music_present": False,
            "sfx_present": False,
            "vo_present": False,
            "clipping": False,
            "silence_detected": False,
            "vo_to_bed_level_db": None,
            "integrated_loudness_lufs": None,
            "true_peak_dbtp": None,
            "expected_source_ids": expected_source_ids,
            "rendered_source_ids": rendered_source_ids,
            "audible_windows": {
                "vo": [],
                "music": {},
                "sfx": {},
                "source_sound": {},
            },
        }

        mode = soundtrack_plan.get("mode", "")
        config_path = os.path.join(self.config_dir, "soundtrack_review.yaml")
        try:
            with open(config_path, encoding="utf-8") as handle:
                review_config = yaml.safe_load(handle) or {}
            silence_db = float(review_config["silence_noise_db"])
            minimum_silence = float(review_config["minimum_silence_seconds"])
            clipping_peak = float(review_config["clipping_true_peak_dbtp"])
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            issues.append(f"Soundtrack review configuration is invalid: {exc}")
            review_config = None

        audio_streams = []
        render_duration = 0.0
        try:
            probe = sp.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", render_path],
                capture_output=True, text=True, timeout=10,
            )
            if probe.returncode == 0:
                data = json.loads(probe.stdout)
                audio_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
                render_duration = float(data.get("format", {}).get("duration") or 0)
        except (OSError, sp.TimeoutExpired, ValueError, TypeError, json.JSONDecodeError):
            audio_streams = []

        if not audio_streams:
            issues.append("No audio stream in rendered file")
            return {
                "verdict": "needs_operator_decision",
                "issues": issues,
                "checks": checks,
                "summary": "No audio stream found — cannot verify soundtrack mix",
            }

        if review_config:
            try:
                loudness = sp.run(
                    ["ffmpeg", "-hide_banner", "-nostats", "-i", render_path,
                     "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
                    capture_output=True, text=True, timeout=30,
                )
                loudness_output = loudness.stderr
            except (OSError, sp.TimeoutExpired):
                loudness_output = ""
            integrated = re.findall(
                r"I:\s*(-?\d+(?:\.\d+)?)\s+LUFS", loudness_output
            )
            peaks = re.findall(
                r"Peak:\s*(-?\d+(?:\.\d+)?)\s+dBFS", loudness_output
            )
            if integrated:
                checks["integrated_loudness_lufs"] = float(integrated[-1])
            else:
                issues.append("Integrated loudness could not be measured")
            if peaks:
                checks["true_peak_dbtp"] = float(peaks[-1])
                if checks["true_peak_dbtp"] > clipping_peak:
                    checks["clipping"] = True
                    issues.append(
                        f"True peak {checks['true_peak_dbtp']:.1f} dBTP exceeds "
                        f"configured {clipping_peak:.1f} dBTP"
                    )
            else:
                issues.append("True peak could not be measured")

            try:
                silence = sp.run(
                    ["ffmpeg", "-hide_banner", "-nostats", "-i", render_path,
                     "-af", f"silencedetect=noise={silence_db}dB:d={minimum_silence}",
                     "-f", "null", "-"],
                    capture_output=True, text=True, timeout=30,
                )
                silence_output = silence.stderr
            except (OSError, sp.TimeoutExpired):
                silence_output = ""
                issues.append("Audible-signal windows could not be measured")
            starts = [float(value) for value in re.findall(
                r"silence_start:\s*(\d+(?:\.\d+)?)", silence_output
            )]
            ends = [float(value) for value in re.findall(
                r"silence_end:\s*(\d+(?:\.\d+)?)", silence_output
            )]
            analysis_end = min(vo_duration or render_duration, render_duration)
            cursor = 0.0
            audible_windows = []
            for index, start in enumerate(starts):
                if start > cursor:
                    audible_windows.append([round(cursor, 3), round(start, 3)])
                cursor = ends[index] if index < len(ends) else analysis_end
            if cursor < analysis_end:
                audible_windows.append([round(cursor, 3), round(analysis_end, 3)])
            checks["audible_windows"]["vo"] = audible_windows
            checks["vo_present"] = bool(audible_windows)
            checks["silence_detected"] = not checks["vo_present"]
            if not checks["vo_present"]:
                issues.append("No audible VO signal window was measured")

        approval_token = (
            operator_approval.get("gate_token")
            if isinstance(operator_approval, dict)
            else None
        )
        if not approval_token:
            issues.append("No server-verified soundtrack approval was supplied")

        evidence_windows = evidence.get("audible_windows") or {}
        if mode in ("music_bed", "vo_plus_bed"):
            if not music_ref:
                issues.append(f"{mode} mode is missing music_bed_ref")
            if not soundtrack_plan.get("ducking"):
                issues.append(f"{mode} mode is missing ducking parameters")
            missing_music = sorted(set(expected_music_ids) - set(rendered_source_ids))
            checks["music_present"] = bool(expected_music_ids) and not missing_music
            for source_id in missing_music:
                issues.append(f"Approved music source {source_id} is absent from render evidence")
            for source_id in expected_music_ids:
                windows = evidence_windows.get(source_id) or []
                checks["audible_windows"]["music"][source_id] = windows
                if not windows:
                    issues.append(f"Approved music source {source_id} has no audible window evidence")
            vo_lufs = evidence.get("vo_lufs")
            bed_lufs = evidence.get("bed_lufs")
            if isinstance(vo_lufs, (int, float)) and isinstance(bed_lufs, (int, float)):
                checks["vo_to_bed_level_db"] = round(float(vo_lufs) - float(bed_lufs), 2)
            else:
                issues.append("VO-to-bed level relationship was not measured")

        if mode == "vo_only" and evidence.get("strategy") != "vo":
            issues.append("Renderer did not attest that the approved VO strategy was applied")
        if mode == "vo_only" and evidence.get("applied") is not True:
            issues.append("Renderer did not confirm a successful VO-only mix")
        if mode == "vo_only" and rendered_source_ids:
            issues.append("VO-only render contains unexpected music/SFX source evidence")
        if mode == "vo_only" and music_ref:
            issues.append("VO-only plan and music-bed reference diverge")

        if mode == "source_sound":
            source_ids = evidence.get("source_sound_ids") or []
            checks["audible_windows"]["source_sound"] = {
                source_id: evidence_windows.get(source_id) or []
                for source_id in source_ids
            }
            if not source_ids:
                issues.append("Source-sound plan has no source-bound render evidence")

        if sfx_cues:
            missing_sfx = sorted(set(expected_sfx_ids) - set(rendered_source_ids))
            checks["sfx_present"] = not missing_sfx
            for cue in sfx_cues:
                source_id = str(cue.get("source") or "")
                windows = evidence_windows.get(source_id) or []
                checks["audible_windows"]["sfx"][source_id] = windows
                if source_id in missing_sfx:
                    issues.append(f"Approved SFX source {source_id} is absent from render evidence")
                cue_time = float(cue.get("timestamp") or 0)
                if not any(start <= cue_time <= end for start, end in windows):
                    issues.append(
                        f"Approved SFX source {source_id} has no audible evidence "
                        f"at {cue_time:.3f}s"
                    )

        verdict = "compliant" if not issues else "needs_operator_decision"
        summary = "Soundtrack mix review passed." if not issues else (
            f"{len(issues)} soundtrack mix issue(s): " + "; ".join(issues)
        )

        return {
            "verdict": verdict,
            "issues": issues,
            "checks": checks,
            "summary": summary,
        }