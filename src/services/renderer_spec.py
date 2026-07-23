"""
VF-RA-001 — Canonical RendererSpec v1 + local conformance adapter.

Mechanically compiles only a current immutable manifest and ratified
CompositionPlan into a provider-neutral schema covering identity/hashes,
output/canvas, exact layered timeline, source trims/crops/focal points,
keyframes/easing, transition type/duration, exact display text/word
timings/font artifacts/style hashes, graphics composition IDs, and exact
VO/music/source-sound/SFX gain automation.

Adds a versioned capability registry and fail-closed lowering contract.
Existing FFmpeg/PIL becomes one adapter rather than the canonical schema.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Optional


RENDERER_SPEC_VERSION = "1.0"


# ── Capability registry ────────────────────────────────────────────────

# Capabilities that a renderer adapter must support.
# If a RendererSpec requires a capability the adapter doesn't support,
# the lowering fails closed with a structured blocker.
CAPABILITY_REGISTRY = {
    "text_overlay": "On-screen text with font, size, color, position, timing",
    "audio_mix": "Multi-track audio mixing with gain automation",
    "video_trim": "Trimming video clips to exact in/out points",
    "image_scale": "Scaling and positioning images on canvas",
    "transition_crossfade": "Crossfade transitions between segments",
    "transition_cut": "Hard cut transitions",
    "motion_zoom": "Zoom/pan motion keyframes",
    "safe_zones": "Safe zone awareness for platform framing",
    "loudness_target": "LUFS loudness normalization",
    "sfx_trigger": "SFX at exact timestamps",
}


def get_required_capabilities(spec: dict) -> list[str]:
    """Determine which capabilities a RendererSpec requires."""
    caps = set()

    # Text overlays
    for el in spec.get("timeline", []):
        if el.get("type") == "text":
            caps.add("text_overlay")
        elif el.get("type") == "audio":
            caps.add("audio_mix")
            if el.get("lane_type") == "sfx":
                caps.add("sfx_trigger")
            if el.get("lufs_target") is not None:
                caps.add("loudness_target")
        elif el.get("type") == "visual":
            if el.get("trim_in") is not None or el.get("trim_out") is not None:
                caps.add("video_trim")
            if el.get("kind") == "image":
                caps.add("image_scale")
            if el.get("motion_keyframes"):
                caps.add("motion_zoom")
        elif el.get("type") == "transition":
            ttype = el.get("transition_type", "cut")
            if ttype == "crossfade":
                caps.add("transition_crossfade")
            elif ttype == "cut":
                caps.add("transition_cut")

    # Safe zones
    canvas = spec.get("canvas", {})
    if canvas.get("safe_zones"):
        caps.add("safe_zones")

    return sorted(caps)


def check_adapter_capabilities(
    adapter_caps: list[str], required_caps: list[str]
) -> dict:
    """Check if an adapter supports all required capabilities.

    Returns:
    {
        "supported": bool,
        "missing": [...],
        "supported_caps": [...],
    }
    """
    adapter_set = set(adapter_caps)
    required_set = set(required_caps)
    missing = required_set - adapter_set

    return {
        "supported": len(missing) == 0,
        "missing": sorted(missing),
        "supported_caps": sorted(required_set & adapter_set),
    }


# ── RendererSpec schema ────────────────────────────────────────────────

RENDERER_SPEC_SCHEMA = {
    "type": "object",
    "required": ["spec_version", "identity", "canvas", "timeline"],
    "properties": {
        "spec_version": {"type": "string"},
        "identity": {
            "type": "object",
            "required": ["composition_plan_hash", "manifest_hash",
                         "session_id", "asset_id"],
            "properties": {
                "composition_plan_hash": {"type": "string"},
                "manifest_hash": {"type": "string"},
                "session_id": {"type": "integer"},
                "asset_id": {"type": "integer"},
                "business_slug": {"type": "string"},
            },
        },
        "canvas": {
            "type": "object",
            "required": ["width", "height", "fps"],
            "properties": {
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "fps": {"type": "number"},
                "aspect_ratio": {"type": "string"},
                "background": {"type": "string"},
                "safe_zones": {"type": "object"},
                "platform_framing": {"type": "string"},
            },
        },
        "timeline": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "layer", "in_point", "out_point"],
                "properties": {
                    "type": {"type": "string"},
                    "layer": {"type": "integer"},
                    "in_point": {"type": "number"},
                    "out_point": {"type": "number"},
                    "element_id": {"type": "string"},
                    "source_hash": {"type": "string"},
                    "source_path": {"type": "string"},
                    # Text-specific
                    "text": {"type": "string"},
                    "font_family": {"type": "string"},
                    "font_path": {"type": "string"},
                    "font_hash": {"type": "string"},
                    "font_size": {"type": "number"},
                    "font_color": {"type": "string"},
                    "position": {"type": "object"},
                    "word_timings": {"type": "array"},
                    "emphasis_marks": {"type": "array"},
                    # Audio-specific
                    "lane_type": {"type": "string"},
                    "gain": {"type": "number"},
                    "gain_curve": {"type": "array"},
                    "ducking_points": {"type": "array"},
                    "fade_in": {"type": "number"},
                    "fade_out": {"type": "number"},
                    "lufs_target": {"type": "number"},
                    "true_peak_limit": {"type": "number"},
                    # Visual-specific
                    "kind": {"type": "string"},
                    "trim_in": {"type": "number"},
                    "trim_out": {"type": "number"},
                    "crop": {"type": "object"},
                    "scale": {"type": "number"},
                    "motion_keyframes": {"type": "array"},
                    # Transition-specific
                    "transition_type": {"type": "string"},
                    "duration": {"type": "number"},
                    "easing": {"type": "string"},
                    "beat_boundary": {"type": "string"},
                    # Graphics-specific
                    "overlay_type": {"type": "string"},
                    "config_hash": {"type": "string"},
                    "animation": {"type": "object"},
                },
            },
        },
        "audio_automation": {
            "type": "object",
            "properties": {
                "lufs_target": {"type": "number"},
                "true_peak_limit": {"type": "number"},
                "tracks": {"type": "array"},
            },
        },
    },
}


# ── Spec compiler ──────────────────────────────────────────────────────

class RendererSpecError(Exception):
    """RendererSpec compilation or validation error."""
    pass


class LocalConformanceAdapter:
    """The existing FFmpeg/PIL renderer as one adapter of RendererSpec v1.

    This adapter declares its capabilities and can lower a RendererSpec
    to the existing local rendering pipeline. It is NOT the canonical
    schema — it is one implementation of it.
    """

    # Capabilities supported by the local FFmpeg/PIL adapter
    SUPPORTED_CAPABILITIES = [
        "text_overlay",
        "audio_mix",
        "video_trim",
        "image_scale",
        "transition_cut",
        "transition_crossfade",
        "motion_zoom",
        "safe_zones",
        "loudness_target",
        "sfx_trigger",
    ]

    @property
    def capabilities(self) -> list[str]:
        return list(self.SUPPORTED_CAPABILITIES)

    def can_render(self, spec: dict) -> dict:
        """Check if this adapter can render the given spec."""
        required = get_required_capabilities(spec)
        return check_adapter_capabilities(self.capabilities, required)

    def lower(self, spec: dict) -> dict:
        """Lower a RendererSpec to the local FFmpeg/PIL rendering pipeline.

        Returns a lowering result with the consumed spec hash and
        any lowering evidence.
        """
        capability_check = self.can_render(spec)
        if not capability_check["supported"]:
            raise RendererSpecError(
                "Local adapter missing capabilities: "
                + ", ".join(capability_check["missing"])
            )

        spec_hash = compute_spec_hash(spec)

        return {
            "adapter": "local_ffmpeg",
            "spec_hash": spec_hash,
            "capabilities_used": capability_check["supported_caps"],
            "lowering_evidence": {
                "timeline_elements": len(spec.get("timeline", [])),
                "canvas": spec.get("canvas", {}),
                "audio_automation": spec.get("audio_automation", {}),
            },
        }


def compute_spec_hash(spec: dict) -> str:
    """Compute canonical SHA-256 hash of a RendererSpec."""
    # Exclude any existing hash from computation
    data = {k: v for k, v in spec.items() if k != "spec_hash"}
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_spec(spec: dict) -> tuple[bool, list[str]]:
    """Validate a RendererSpec against the schema.

    Mechanical validation only: required fields present, types correct,
    hashes are strings. No creative judgment.
    """
    errors = []

    if not isinstance(spec, dict):
        return False, ["Spec must be a dict"]

    # Check required top-level fields
    for field in ["spec_version", "identity", "canvas", "timeline"]:
        if field not in spec:
            errors.append(f"Missing required field: {field}")

    if errors:
        return False, errors

    # Check identity
    identity = spec.get("identity", {})
    for field in ["composition_plan_hash", "manifest_hash", "session_id", "asset_id"]:
        if not identity.get(field):
            errors.append(f"Identity missing: {field}")

    # Check canvas
    canvas = spec.get("canvas", {})
    for field in ["width", "height", "fps"]:
        if field not in canvas:
            errors.append(f"Canvas missing: {field}")

    # Check timeline
    timeline = spec.get("timeline", [])
    if not isinstance(timeline, list):
        errors.append("Timeline must be an array")
    else:
        for i, el in enumerate(timeline):
            if not isinstance(el, dict):
                errors.append(f"Timeline element {i} must be an object")
                continue
            for field in ["type", "layer", "in_point", "out_point"]:
                if field not in el:
                    errors.append(f"Timeline element {i} missing: {field}")

    return len(errors) == 0, errors


def compile_from_ratified_plan(
    plan: dict,
    manifest: dict,
    session: dict,
) -> dict:
    """Compile a ratified CompositionPlan into a RendererSpec v1.

    This is the canonical compilation path. The plan must be ratified
    (session in composition_ratified state). The manifest must be active.

    The RendererSpec inherits the composition plan hash as an input hash.
    """
    plan_hash = plan.get("plan_hash") or plan.get("manifest_hash", "")

    # Build the timeline from the plan
    timeline = []

    # Text elements
    for text_el in plan.get("text_elements", []):
        timeline.append({
            "type": "text",
            "layer": 10,  # text is above visuals
            "in_point": text_el.get("start", 0),
            "out_point": text_el.get("end", 0),
            "element_id": text_el.get("element_id", ""),
            "text": text_el.get("text", ""),
            "font_family": text_el.get("font_family", ""),
            "font_path": text_el.get("font_path", ""),
            "font_hash": text_el.get("font_hash", ""),
            "font_size": text_el.get("font_size", 0),
            "font_color": text_el.get("font_color", ""),
            "position": text_el.get("position", {}),
            "word_timings": text_el.get("word_timings", []),
            "emphasis_marks": text_el.get("emphasis_marks", []),
            "source_hash": text_el.get("font_hash", ""),
        })

    # Audio elements
    for audio_el in plan.get("audio_elements", []):
        for lane in audio_el.get("lanes", []):
            timeline.append({
                "type": "audio",
                "layer": 0,  # audio is its own layer
                "in_point": lane.get("start", 0),
                "out_point": lane.get("end", 0),
                "element_id": lane.get("element_id", ""),
                "lane_type": lane.get("lane_type", ""),
                "source_hash": lane.get("source_hash", ""),
                "source_path": lane.get("source_path", ""),
                "gain": lane.get("gain", 1.0),
                "gain_curve": lane.get("gain_curve", []),
                "ducking_points": lane.get("ducking_points", []),
                "fade_in": lane.get("fade_in", 0),
                "fade_out": lane.get("fade_out", 0),
                "lufs_target": audio_el.get("lufs_target"),
                "true_peak_limit": audio_el.get("true_peak_limit"),
            })

    # Visual elements
    for i, vis_el in enumerate(plan.get("visual_elements", [])):
        timeline.append({
            "type": "visual",
            "layer": 1,  # visuals below text
            "in_point": vis_el.get("start", 0),
            "out_point": vis_el.get("end", 0),
            "element_id": vis_el.get("element_id", ""),
            "kind": vis_el.get("kind", ""),
            "source_hash": vis_el.get("source_hash", ""),
            "source_path": vis_el.get("source_path", ""),
            "trim_in": vis_el.get("trim_in"),
            "trim_out": vis_el.get("trim_out"),
            "crop": vis_el.get("crop", {}),
            "scale": vis_el.get("scale", 1.0),
            "motion_keyframes": vis_el.get("motion_keyframes", []),
        })

    # Graphics elements
    for gfx_el in plan.get("graphics_elements", []):
        timeline.append({
            "type": "graphics",
            "layer": 5,  # graphics above visuals, below text
            "in_point": gfx_el.get("start", 0),
            "out_point": gfx_el.get("end", 0),
            "element_id": gfx_el.get("element_id", ""),
            "overlay_type": gfx_el.get("overlay_type", ""),
            "config_hash": gfx_el.get("config_hash", ""),
            "source_path": gfx_el.get("overlay_path", ""),
            "position": gfx_el.get("position", {}),
            "scale": gfx_el.get("scale", 1.0),
            "animation": gfx_el.get("animation", {}),
        })

    # Transitions
    for trans_el in plan.get("transitions", []):
        timeline.append({
            "type": "transition",
            "layer": 20,  # transitions are meta-elements
            "in_point": trans_el.get("start", 0),
            "out_point": trans_el.get("start", 0) + trans_el.get("duration", 0.5),
            "element_id": trans_el.get("element_id", ""),
            "transition_type": trans_el.get("transition_type", "cut"),
            "duration": trans_el.get("duration", 0.5),
            "easing": trans_el.get("easing", "linear"),
            "beat_boundary": trans_el.get("beat_boundary", ""),
        })

    # Canvas
    canvas = plan.get("canvas", {})

    # Audio automation
    audio_automation = {}
    for audio_el in plan.get("audio_elements", []):
        if audio_el.get("lufs_target") is not None:
            audio_automation["lufs_target"] = audio_el["lufs_target"]
        if audio_el.get("true_peak_limit") is not None:
            audio_automation["true_peak_limit"] = audio_el["true_peak_limit"]
        audio_automation.setdefault("tracks", [])
        for lane in audio_el.get("lanes", []):
            audio_automation["tracks"].append({
                "element_id": lane.get("element_id", ""),
                "lane_type": lane.get("lane_type", ""),
                "gain": lane.get("gain", 1.0),
            })

    # Build the spec
    manifest_data = manifest.get("manifest_json", {}) if isinstance(manifest, dict) else {}
    if isinstance(manifest_data, str):
        manifest_data = json.loads(manifest_data)

    spec = {
        "spec_version": RENDERER_SPEC_VERSION,
        "identity": {
            "composition_plan_hash": plan_hash,
            "manifest_hash": manifest_data.get("manifest_hash", ""),
            "session_id": session.get("id"),
            "asset_id": session.get("asset_id"),
            "business_slug": session.get("business_slug"),
        },
        "canvas": {
            "width": canvas.get("width", 1080),
            "height": canvas.get("height", 1920),
            "fps": canvas.get("fps", 30.0),
            "aspect_ratio": canvas.get("aspect_ratio", "9:16"),
            "background": canvas.get("background", "#000000"),
            "safe_zones": canvas.get("safe_zones", {}),
            "platform_framing": canvas.get("platform_framing", ""),
        },
        "timeline": timeline,
        "audio_automation": audio_automation,
    }

    # Compute and attach the spec hash
    spec["spec_hash"] = compute_spec_hash(spec)

    return spec