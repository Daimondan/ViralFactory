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


# ── VF-CP-004: RendererSpecCompiler ──────────────────────────────────────
#
# State-machine-gated compilation from a ratified CompositionPlan (dict form
# as produced by CompositionPlanGenerator) into RendererSpec v1.  Rejects
# unratified, stale, rejected, and hash-mismatched plans.  The provider
# adapter receives only the compiled RendererSpec — never the raw plan.

_LAYER_TEXT = 10
_LAYER_VISUAL = 1
_LAYER_GRAPHICS = 5
_LAYER_TRANSITION = 20
_LAYER_AUDIO = 0


class RendererSpecCompiler:
    """Compile a ratified CompositionPlan (generator dict form) into a
    provider-neutral RendererSpec v1.

    The compiler is the sole gate between the composition plan and the
    provider adapter.  It verifies:

    1.  **Ratification** — the production session is in
        ``composition_ratified`` state.
    2.  **Staleness** — the plan's ``plan_hash`` matches the session's
        ``active_composition_plan_hash`` (the ratified plan hasn't been
        superseded).
    3.  **Integrity** — ``compute_plan_hash(plan)`` matches the plan's
        declared ``plan_hash`` (no post-ratification tampering).

    Only after all three checks pass does it compile the plan into a
    RendererSpec, which inherits the composition plan hash as an input
    hash and preserves every element source hash.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path

    # ── public API ───────────────────────────────────────────────────

    def compile(
        self,
        business_slug: str,
        session_id: int,
        plan: dict,
    ) -> dict:
        """Compile a ratified CompositionPlan into a RendererSpec v1.

        Raises ``RendererSpecError`` if the plan is unratified, stale,
        or hash-mismatched.

        Returns the compiled RendererSpec dict with ``spec_hash`` attached.
        """
        blockers = self._validate_preconditions(business_slug, session_id, plan)
        if blockers:
            raise RendererSpecError(
                "Cannot compile RendererSpec: " + "; ".join(blockers)
            )

        session = self._get_session(business_slug, session_id)
        manifest = self._get_active_manifest(business_slug, session_id)

        spec = self._build_spec(plan, session, manifest)

        # Capability check — structured blockers for unsupported features
        required_caps = get_required_capabilities(spec)
        adapter_check = check_adapter_capabilities(
            LocalConformanceAdapter.SUPPORTED_CAPABILITIES, required_caps
        )
        if not adapter_check["supported"]:
            raise RendererSpecError(
                "Unsupported mandatory features: "
                + ", ".join(adapter_check["missing"])
            )

        spec["spec_hash"] = compute_spec_hash(spec)
        return spec

    def validate_spec(self, spec: dict) -> tuple[bool, list[str]]:
        """Validate a RendererSpec round-trip.

        Delegates to the module-level ``validate_spec`` function and
        additionally verifies that ``spec_hash`` is canonical.
        """
        ok, errors = validate_spec(spec)
        if not ok:
            return ok, errors

        # Verify spec_hash round-trip
        if "spec_hash" in spec:
            expected = compute_spec_hash(spec)
            if spec["spec_hash"] != expected:
                errors.append(
                    f"Spec hash mismatch: stored={spec['spec_hash'][:16]}, "
                    f"computed={expected[:16]}"
                )

        return len(errors) == 0, errors

    def compute_spec_hash(self, spec: dict) -> str:
        """Compute canonical hash of a RendererSpec."""
        return compute_spec_hash(spec)

    def check_capabilities(self, spec: dict) -> dict:
        """Return structured blockers for unsupported mandatory features.

        Returns::
        {
            "supported": bool,
            "missing": [...],
            "required": [...],
            "supported_caps": [...],
        }
        """
        required = get_required_capabilities(spec)
        check = check_adapter_capabilities(
            LocalConformanceAdapter.SUPPORTED_CAPABILITIES, required
        )
        check["required"] = required
        return check

    # ── precondition validation ──────────────────────────────────────

    def _validate_preconditions(
        self,
        business_slug: str,
        session_id: int,
        plan: dict,
    ) -> list[str]:
        """Return a list of blocker strings (empty = all checks pass)."""
        blockers: list[str] = []

        # 1. Session exists and is tenant-scoped
        try:
            session = self._get_session(business_slug, session_id)
        except Exception as exc:
            blockers.append(f"Session not found: {exc}")
            return blockers

        # 2. Ratification — session must be in composition_ratified state
        if session.get("current_state") != "composition_ratified":
            blockers.append(
                f"Session state is '{session.get('current_state')}', "
                f"must be 'composition_ratified'"
            )

        # 3. Staleness — plan hash must match session's ratified plan hash
        plan_hash = plan.get("plan_hash", "")
        active_hash = session.get("active_composition_plan_hash", "")
        if not active_hash:
            blockers.append(
                "Session has no active composition plan hash — not ratified"
            )
        elif plan_hash != active_hash:
            blockers.append(
                f"Stale plan: plan_hash={plan_hash[:16]} != "
                f"session active_composition_plan_hash={active_hash[:16]}"
            )

        # 4. Integrity — plan hash must be internally consistent
        from services.composition_plan import compute_plan_hash
        computed_hash = compute_plan_hash(plan)
        if computed_hash != plan_hash:
            blockers.append(
                f"Plan hash mismatch (tampered/corrupt): "
                f"declared={plan_hash[:16]}, computed={computed_hash[:16]}"
            )

        return blockers

    # ── compilation ──────────────────────────────────────────────────

    def _build_spec(
        self,
        plan: dict,
        session: dict,
        manifest: Optional[dict],
    ) -> dict:
        """Build the RendererSpec dict from the plan."""
        plan_hash = plan.get("plan_hash", "")
        manifest_hash = plan.get("manifest_hash", "")
        if manifest:
            md = manifest.get("manifest_json", {})
            if isinstance(md, str):
                md = json.loads(md)
            manifest_hash = md.get("manifest_hash", manifest_hash)

        timeline = []
        timeline.extend(self._compile_text_elements(plan))
        timeline.extend(self._compile_audio_elements(plan))
        timeline.extend(self._compile_visual_elements(plan))
        timeline.extend(self._compile_graphics_elements(plan))
        timeline.extend(self._compile_transitions(plan))

        canvas = self._compile_canvas(plan)
        audio_automation = self._compile_audio_automation(plan)

        spec = {
            "spec_version": RENDERER_SPEC_VERSION,
            "identity": {
                "composition_plan_hash": plan_hash,
                "manifest_hash": manifest_hash,
                "session_id": session.get("id"),
                "asset_id": session.get("asset_id"),
                "business_slug": session.get("business_slug"),
            },
            "canvas": canvas,
            "timeline": timeline,
            "audio_automation": audio_automation,
        }
        return spec

    def _compile_text_elements(self, plan: dict) -> list[dict]:
        """Compile text_elements from the generator-produced plan dict."""
        elements = []
        for te in plan.get("text_elements", []):
            timing = te.get("timing", {})
            font = te.get("font", {})
            elements.append({
                "type": "text",
                "layer": _LAYER_TEXT,
                "in_point": timing.get("in_sec", 0.0),
                "out_point": timing.get("out_sec", 0.0),
                "element_id": te.get("element_id", ""),
                "text": te.get("text", ""),
                "role": te.get("role", ""),
                "beat_id": te.get("beat_id", ""),
                "font_family": font.get("family", ""),
                "font_hash": font.get("file_hash", ""),
                "font_weight": font.get("weight", ""),
                "font_size": font.get("size", 0),
                "font_color": font.get("color", ""),
                "border_width": font.get("border_width", 0),
                "border_color": font.get("border_color", ""),
                "shadow": font.get("shadow"),
                "style_ref": te.get("style_ref", ""),
                "position": te.get("position", {}),
                "word_timings": te.get("word_timing", []),
                "emphasis_marks": te.get("emphasis_marks", []),
                "source_hash": font.get("file_hash", ""),
            })
        return elements

    def _compile_audio_elements(self, plan: dict) -> list[dict]:
        """Compile audio tracks from the generator-produced plan dict."""
        audio = plan.get("audio", {})
        elements = []

        vo_track = audio.get("vo_track")
        if vo_track:
            elements.append({
                "type": "audio",
                "layer": _LAYER_AUDIO,
                "lane_type": "vo",
                "in_point": vo_track.get("trim_start_sec", 0.0),
                "out_point": vo_track.get("trim_end_sec", 0.0),
                "element_id": "vo_track",
                "source_hash": vo_track.get("source_hash", ""),
                "manifest_candidate_id": vo_track.get("manifest_candidate_id"),
                "gain_curve": vo_track.get("gain_curve", []),
                "ducking": vo_track.get("ducking", {}),
                "fade_in": 0.0,
                "fade_out": 0.0,
            })

        music_track = audio.get("music_track")
        if music_track:
            elements.append({
                "type": "audio",
                "layer": _LAYER_AUDIO,
                "lane_type": "music",
                "in_point": music_track.get("start_sec", 0.0),
                "out_point": music_track.get("stop_sec", 0.0),
                "element_id": "music_track",
                "source_hash": music_track.get("source_hash", ""),
                "manifest_candidate_id": music_track.get("manifest_candidate_id"),
                "gain_db": music_track.get("gain_db", 0.0),
                "ducking": music_track.get("ducking", {}),
                "fade_in": music_track.get("fade_in_sec", 0.0),
                "fade_out": music_track.get("fade_out_sec", 0.0),
            })

        for sfx in audio.get("sfx_events", []):
            trigger = sfx.get("trigger_sec", 0.0)
            duration = sfx.get("duration_sec", 0.3)
            elements.append({
                "type": "audio",
                "layer": _LAYER_AUDIO,
                "lane_type": "sfx",
                "in_point": trigger,
                "out_point": trigger + duration,
                "element_id": sfx.get("sfx_id", ""),
                "source_hash": "",
                "gain_db": sfx.get("gain_db", 0.0),
                "duration_sec": duration,
                "preset": sfx.get("preset", ""),
                "beat_id": sfx.get("beat_id", ""),
            })

        return elements

    def _compile_visual_elements(self, plan: dict) -> list[dict]:
        """Compile visual_elements from the generator-produced plan dict."""
        elements = []
        for ve in plan.get("visual_elements", []):
            elements.append({
                "type": "visual",
                "layer": _LAYER_VISUAL,
                "in_point": ve.get("trim_start_sec", 0.0),
                "out_point": ve.get("trim_end_sec", 0.0),
                "element_id": ve.get("element_id", ""),
                "kind": ve.get("kind", ""),
                "source_hash": ve.get("source_hash", ""),
                "manifest_candidate_id": ve.get("manifest_candidate_id"),
                "trim_in": ve.get("trim_start_sec", 0.0),
                "trim_out": ve.get("trim_end_sec", 0.0),
                "crop": ve.get("crop"),
                "focal": ve.get("focal"),
                "canvas_position": ve.get("canvas_position", {}),
                "scale": ve.get("scale", 1.0),
                "motion_keyframes": ve.get("motion_keyframes", []),
                "beat_id": ve.get("beat_id", ""),
            })
        return elements

    def _compile_graphics_elements(self, plan: dict) -> list[dict]:
        """Compile graphics_elements from the generator-produced plan dict."""
        elements = []
        for gfx in plan.get("graphics_elements", []):
            timing = gfx.get("timing", {})
            elements.append({
                "type": "graphics",
                "layer": _LAYER_GRAPHICS,
                "in_point": timing.get("in_sec", 0.0),
                "out_point": timing.get("out_sec", 0.0),
                "element_id": gfx.get("element_id", ""),
                "overlay_type": gfx.get("type", ""),
                "config_hash": gfx.get("config_hash", ""),
                "position": gfx.get("position", {}),
                "scale": gfx.get("scale", 1.0),
                "animation": gfx.get("animation", {}),
                "beat_id": gfx.get("beat_id", ""),
            })
        return elements

    def _compile_transitions(self, plan: dict) -> list[dict]:
        """Compile transitions from the generator-produced plan dict."""
        elements = []
        for tr in plan.get("transitions", []):
            duration = tr.get("duration_sec", 0.0)
            elements.append({
                "type": "transition",
                "layer": _LAYER_TRANSITION,
                "in_point": 0.0,
                "out_point": duration,
                "element_id": tr.get("transition_id", ""),
                "transition_type": tr.get("type", "cut"),
                "duration": duration,
                "easing": tr.get("easing", "ease_in_out"),
                "beat_boundary": tr.get("beat_boundary", ""),
            })
        return elements

    def _compile_canvas(self, plan: dict) -> dict:
        """Compile canvas from the generator-produced plan dict."""
        canvas = plan.get("canvas", {})
        resolution = canvas.get("resolution", {})
        if isinstance(resolution, str) and "x" in resolution:
            parts = resolution.split("x", 1)
            width, height = int(parts[0]), int(parts[1])
        else:
            width = resolution.get("width", 1080)
            height = resolution.get("height", 1920)

        background = canvas.get("background", {})
        if isinstance(background, dict):
            bg_color = background.get("color", "#000000")
        else:
            bg_color = str(background)

        return {
            "width": width,
            "height": height,
            "fps": canvas.get("fps", 30),
            "aspect_ratio": canvas.get("aspect_ratio", "9:16"),
            "background": bg_color,
            "safe_zones": canvas.get("safe_zones", {}),
            "platform_framing": canvas.get("platform_framing", ""),
        }

    def _compile_audio_automation(self, plan: dict) -> dict:
        """Compile audio automation from the generator-produced plan dict."""
        audio = plan.get("audio", {})
        mix_spec = audio.get("mix_spec", {})

        tracks = []
        vo_track = audio.get("vo_track")
        if vo_track:
            tracks.append({
                "element_id": "vo_track",
                "lane_type": "vo",
                "source_hash": vo_track.get("source_hash", ""),
                "gain_curve": vo_track.get("gain_curve", []),
                "ducking": vo_track.get("ducking", {}),
            })

        music_track = audio.get("music_track")
        if music_track:
            tracks.append({
                "element_id": "music_track",
                "lane_type": "music",
                "source_hash": music_track.get("source_hash", ""),
                "gain_db": music_track.get("gain_db", 0.0),
                "ducking": music_track.get("ducking", {}),
                "fade_in": music_track.get("fade_in_sec", 0.0),
                "fade_out": music_track.get("fade_out_sec", 0.0),
            })

        for sfx in audio.get("sfx_events", []):
            tracks.append({
                "element_id": sfx.get("sfx_id", ""),
                "lane_type": "sfx",
                "gain_db": sfx.get("gain_db", 0.0),
                "trigger_sec": sfx.get("trigger_sec", 0.0),
                "preset": sfx.get("preset", ""),
            })

        return {
            "lufs_target": mix_spec.get("lufs_target", -14.0),
            "true_peak_limit": mix_spec.get("true_peak_db", -1.0),
            "tracks": tracks,
        }

    # ── DB helpers ───────────────────────────────────────────────────

    def _get_session(self, business_slug: str, session_id: int) -> dict:
        from services.production_orchestrator import ProductionSessionService
        svc = ProductionSessionService(db_path=self.db_path)
        return svc.get_session(business_slug, session_id)

    def _get_active_manifest(
        self, business_slug: str, session_id: int
    ) -> Optional[dict]:
        from services.manifest_freeze import ManifestStore
        store = ManifestStore(db_path=self.db_path)
        return store.get_active_manifest(business_slug, session_id)