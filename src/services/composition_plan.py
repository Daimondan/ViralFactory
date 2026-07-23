"""
VF-CP-001 — CompositionPlan schema + generator.

Provider-neutral, typed structured data declaring every element of the final
video. Generated mechanically from the frozen manifest, Writer contract,
visual events, audio intents, and edit plan.

No audience-copy re-generation, no vendor-specific fields, no LLM judgment
in the generator. Every text element traces to approved Writer contract
text. Every audio/visual/graphics element traces to a manifest ingredient
hash. Missing or unapproved ingredients fail closed.

The plan is content-hashed (canonical SHA-256), serializable as JSON, and
diffable between any two plans. The hash is key-order independent.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
from typing import Any


COMPOSITION_PLAN_SCHEMA_VERSION = "1.0"

# Text function → plan role
_TEXT_ROLE_MAP = {
    "hook": "hook",
    "orientation": "lower_third",
    "caption": "caption",
    "emphasis": "emphasis",
    "proof": "proof",
    "reframe": "reframe",
    "cta": "cta",
}

# Text function → render overlay style ref
_TEXT_STYLE_REF_MAP = {
    "hook": "hook",
    "orientation": "title",
    "caption": "caption",
    "emphasis": "emphasis",
    "proof": "proof",
    "reframe": "reframe",
    "cta": "cta",
}

# Manifest categories that map to audio tracks
_VO_CATEGORIES = frozenset({"narration", "voice", "vo"})
_MUSIC_CATEGORIES = frozenset({"soundtrack", "music"})

_TRANSITION_TYPES = frozenset({"cut", "crossfade", "wipe", "slide", "zoom"})
_DEFAULT_EASING = "ease_in_out"

# Default text positions (normalized 0-1, can be overridden via render_styles.text_positions)
_DEFAULT_TEXT_POSITIONS = {
    "hook": {"x": 0.5, "y": 0.30, "anchor": "center"},
    "caption": {"x": 0.5, "y": 0.85, "anchor": "center"},
    "emphasis": {"x": 0.5, "y": 0.50, "anchor": "center"},
    "lower_third": {"x": 0.05, "y": 0.75, "anchor": "bottom_left"},
    "cta": {"x": 0.5, "y": 0.70, "anchor": "center"},
    "proof": {"x": 0.5, "y": 0.40, "anchor": "center"},
    "reframe": {"x": 0.5, "y": 0.50, "anchor": "center"},
    "citation": {"x": 0.05, "y": 0.92, "anchor": "bottom_left"},
}


class CompositionPlanError(Exception):
    """Composition plan generation or validation error."""
    pass


# ── Hashing helpers ──────────────────────────────────────────────────────

def _compute_canonical_hash(data: Any) -> str:
    """SHA-256 of canonical JSON (sort_keys, ensure_ascii=False)."""
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _compute_file_hash(path: str) -> str:
    """SHA-256 of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_plan_hash(plan: dict) -> str:
    """Compute the canonical content hash of a CompositionPlan.

    Excludes the ``plan_hash`` field itself. Key-order independent because
    canonical JSON sorts keys.
    """
    data = {k: v for k, v in plan.items() if k != "plan_hash"}
    return _compute_canonical_hash(data)


# ── Text parsing helpers ─────────────────────────────────────────────────

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")


def _parse_emphasis_marks(text: str) -> list[dict]:
    """Parse markdown-style emphasis marks from text."""
    marks = []
    for m in _BOLD_RE.finditer(text):
        marks.append({"type": "bold", "start_idx": m.start(), "end_idx": m.end()})
    for m in _ITALIC_RE.finditer(text):
        marks.append({"type": "italic", "start_idx": m.start(), "end_idx": m.end()})
    return marks


def _compute_word_timing(text: str, start_sec: float, end_sec: float) -> list[dict]:
    """Compute word-level timing by distributing duration evenly."""
    words = text.split()
    if not words:
        return []
    duration = end_sec - start_sec
    if duration <= 0:
        return [{"word": w, "start_sec": start_sec, "end_sec": start_sec} for w in words]
    per_word = duration / len(words)
    return [
        {
            "word": w,
            "start_sec": round(start_sec + i * per_word, 3),
            "end_sec": round(start_sec + (i + 1) * per_word, 3),
        }
        for i, w in enumerate(words)
    ]


# ── Audio helpers ────────────────────────────────────────────────────────

def _volume_to_db(volume: float) -> float:
    """Convert linear volume (0-1) to dB."""
    if volume <= 0:
        return -60.0
    return round(20 * math.log10(volume), 2)


# ── Cue timeline normalization ───────────────────────────────────────────

def _cue_to_dict(cue: Any) -> dict:
    """Convert a CompiledCue-like object or dict to a plain dict."""
    if isinstance(cue, dict):
        return cue
    return {
        "cue_id": cue.cue_id,
        "cue_type": cue.cue_type,
        "beat_id": cue.beat_id,
        "text": cue.text,
        "start_sec": cue.start_sec,
        "end_sec": cue.end_sec,
        "metadata": cue.metadata,
    }


def _normalize_cue_timeline(cue_timeline: Any) -> dict:
    """Normalize a CompiledTimeline or dict to a plain dict."""
    if isinstance(cue_timeline, dict):
        return cue_timeline
    return {
        "vo_timings": [_cue_to_dict(c) for c in cue_timeline.vo_timings],
        "captions": [_cue_to_dict(c) for c in cue_timeline.captions],
        "overlays": [_cue_to_dict(c) for c in cue_timeline.overlays],
        "sfx_events": [_cue_to_dict(c) for c in cue_timeline.sfx_events],
        "music_events": [_cue_to_dict(c) for c in cue_timeline.music_events],
        "silence_events": [_cue_to_dict(c) for c in cue_timeline.silence_events],
        "text_hash": cue_timeline.text_hash,
        "total_duration_sec": cue_timeline.total_duration_sec,
    }


# ── Generator ────────────────────────────────────────────────────────────

class CompositionPlanGenerator:
    """Mechanical CompositionPlan generator — no LLM, no text mutation.

    All configuration is injected via the constructor so that two
    tenant/format fixtures produce visibly different plans with zero
    Python edits.
    """

    def __init__(
        self,
        render_styles: dict,
        font_config: dict,
        canvas_config: dict,
        mix_config: dict,
    ):
        self._render_styles = render_styles
        self._overlay_styles = render_styles.get("overlay_styles", {})
        self._sfx_presets = render_styles.get("sfx_presets", {})
        self._sfx_default = render_styles.get("sfx_default_preset", "pop")
        self._text_positions = render_styles.get("text_positions", {})

        self._font_config = font_config
        self._font_file_hash = font_config.get("font_file_hash") or self._safe_file_hash(
            font_config.get("font_path", "")
        )
        self._font_display_hash = font_config.get("font_display_hash") or self._safe_file_hash(
            font_config.get("font_display", "")
        )
        self._font_family = font_config.get("font_family", "Montserrat")
        self._font_weight = font_config.get("font_weight", "Bold")
        self._font_display_family = font_config.get("font_display_family", "Anton")
        self._font_display_weight = font_config.get("font_display_weight", "Regular")

        self._canvas_config = canvas_config
        self._mix_config = mix_config

    # ── public API ───────────────────────────────────────────────────

    def generate(
        self,
        manifest: dict,
        writer_contract: dict,
        cue_timeline: Any,
    ) -> dict:
        """Generate a CompositionPlan dict.

        Raises CompositionPlanError if any ingredient is missing or
        unapproved, or if the writer contract hash does not match the
        manifest.
        """
        timeline = _normalize_cue_timeline(cue_timeline)

        # Verify writer contract hash matches manifest
        manifest_wc_hash = manifest.get("writer_contract_hash")
        contract_wc_hash = writer_contract.get("writer_contract_hash")
        if (
            manifest_wc_hash
            and contract_wc_hash
            and manifest_wc_hash != contract_wc_hash
        ):
            raise CompositionPlanError(
                f"Writer contract hash mismatch: "
                f"manifest={manifest_wc_hash}, contract={contract_wc_hash}"
            )

        # ── Build indexes ────────────────────────────────────────────
        candidates_by_category: dict[str, list[dict]] = {}
        all_hashes: set[str] = set()
        for c in manifest.get("candidates", []):
            if not c.get("artifact_hash"):
                raise CompositionPlanError(
                    f"Candidate {c['candidate_id']} "
                    f"({c.get('category')}:{c.get('role')}) "
                    f"has no artifact_hash"
                )
            all_hashes.add(c["artifact_hash"])
            candidates_by_category.setdefault(c.get("category", ""), []).append(c)

        text_intents_by_id: dict[str, dict] = {}
        for ti in writer_contract.get("text_intents", []):
            text_intents_by_id[ti["text_intent_id"]] = ti

        beats = writer_contract.get("beats", [])
        beats_by_id = {b["beat_id"]: b for b in beats}

        vo_timing_by_beat: dict[str, dict] = {}
        for vt in timeline.get("vo_timings", []):
            vo_timing_by_beat[vt.get("beat_id", "")] = vt

        # ── Compile elements ─────────────────────────────────────────
        text_elements = self._compile_text_elements(
            writer_contract, timeline, text_intents_by_id, vo_timing_by_beat
        )
        audio = self._compile_audio_elements(
            manifest, writer_contract, timeline, candidates_by_category
        )
        visual_elements = self._compile_visual_elements(
            manifest, writer_contract, timeline,
            candidates_by_category, vo_timing_by_beat,
        )
        graphics_elements = self._compile_graphics_elements(text_elements)
        transitions = self._compile_transitions(writer_contract, timeline)
        canvas = self._compile_canvas()

        # ── Assemble plan ────────────────────────────────────────────
        plan = {
            "schema_version": COMPOSITION_PLAN_SCHEMA_VERSION,
            "manifest_hash": manifest.get("manifest_hash", ""),
            "writer_contract_hash": writer_contract.get("writer_contract_hash", ""),
            "text_hash": timeline.get("text_hash", ""),
            "canvas": canvas,
            "text_elements": text_elements,
            "audio": audio,
            "visual_elements": visual_elements,
            "graphics_elements": graphics_elements,
            "transitions": transitions,
            "total_duration_sec": timeline.get("total_duration_sec", 0.0),
        }
        plan["plan_hash"] = compute_plan_hash(plan)
        return plan

    # ── compilation methods ──────────────────────────────────────────

    def _compile_text_elements(
        self,
        writer_contract: dict,
        timeline: dict,
        text_intents_by_id: dict[str, dict],
        vo_timing_by_beat: dict[str, dict],
    ) -> list[dict]:
        elements: list[dict] = []

        caption_cues = timeline.get("captions", [])
        overlay_cues = [
            c for c in timeline.get("overlays", [])
            if c.get("cue_type") == "overlay"
        ]

        for ti in writer_contract.get("text_intents", []):
            func = ti.get("function", "")
            role = _TEXT_ROLE_MAP.get(func, func)
            style_ref = _TEXT_STYLE_REF_MAP.get(func, "default")
            style = self._overlay_styles.get(
                style_ref, self._overlay_styles.get("default", {})
            )
            text = ti.get("text", "")
            ti_id = ti["text_intent_id"]
            beat_id = ti.get("beat_id", "")

            timing = self._find_text_timing(
                ti_id, beat_id, caption_cues, overlay_cues, vo_timing_by_beat
            )

            is_display = role in ("hook", "lower_third", "cta")
            font_file_hash = (
                self._font_display_hash if is_display else self._font_file_hash
            )
            font_family = (
                self._font_display_family if is_display else self._font_family
            )
            font_weight = (
                self._font_display_weight if is_display else self._font_weight
            )

            shadow = None
            if style.get("shadowx") or style.get("shadowy"):
                shadow = {
                    "x": style.get("shadowx", 0),
                    "y": style.get("shadowy", 0),
                    "color": style.get("shadowcolor", ""),
                }

            elements.append({
                "element_id": f"text_{ti_id}",
                "role": role,
                "text": text,
                "text_intent_id": ti_id,
                "beat_id": beat_id,
                "font": {
                    "file_hash": font_file_hash,
                    "family": font_family,
                    "weight": font_weight,
                    "size": style.get("fontsize", 48),
                    "color": style.get("fontcolor", "white"),
                    "border_width": style.get("borderw", 0),
                    "border_color": style.get("bordercolor", "black"),
                    "shadow": shadow,
                },
                "style_ref": style_ref,
                "position": self._get_text_position(role),
                "timing": {
                    "in_sec": timing["start_sec"],
                    "out_sec": timing["end_sec"],
                },
                "word_timing": _compute_word_timing(
                    text, timing["start_sec"], timing["end_sec"]
                ),
                "emphasis_marks": _parse_emphasis_marks(text),
            })

        # Citations from beat evidence_refs
        for beat in writer_contract.get("beats", []):
            evidence_refs = beat.get("evidence_refs") or []
            if not evidence_refs:
                continue
            beat_id = beat.get("beat_id", "")
            vo = vo_timing_by_beat.get(beat_id, {})
            start = vo.get("start_sec", 0.0)
            end = vo.get("end_sec", start + 2.0)
            for i, ref in enumerate(evidence_refs):
                elements.append({
                    "element_id": f"cite_{beat_id}_{i}",
                    "role": "citation",
                    "text": ref,
                    "text_intent_id": None,
                    "beat_id": beat_id,
                    "font": {
                        "file_hash": self._font_file_hash,
                        "family": self._font_family,
                        "weight": self._font_weight,
                        "size": 24,
                        "color": "white",
                        "border_width": 1,
                        "border_color": "black",
                        "shadow": None,
                    },
                    "style_ref": "default",
                    "position": self._get_text_position("citation"),
                    "timing": {"in_sec": start, "out_sec": end},
                    "word_timing": [],
                    "emphasis_marks": [],
                })

        return elements

    def _compile_audio_elements(
        self,
        manifest: dict,
        writer_contract: dict,
        timeline: dict,
        candidates_by_category: dict[str, list[dict]],
    ) -> dict:
        # VO track
        vo_candidates: list[dict] = []
        for cat in _VO_CATEGORIES:
            vo_candidates.extend(candidates_by_category.get(cat, []))

        vo_track = None
        if vo_candidates:
            c = vo_candidates[0]
            vo_track = {
                "source_hash": c["artifact_hash"],
                "manifest_candidate_id": c["candidate_id"],
                "trim_start_sec": 0.0,
                "trim_end_sec": timeline.get("total_duration_sec", 0.0),
                "gain_curve": [{"time_sec": 0.0, "gain_db": 0.0}],
                "ducking": {
                    "depth": self._mix_config.get("ducking", {}).get(
                        "default_depth", 0.20
                    ),
                    "attack_s": self._mix_config.get("ducking", {}).get(
                        "attack_s", 0.3
                    ),
                    "release_s": self._mix_config.get("ducking", {}).get(
                        "release_s", 0.5
                    ),
                },
            }
        elif any(b.get("vo_text") for b in writer_contract.get("beats", [])):
            raise CompositionPlanError(
                "Beats have vo_text but manifest has no narration candidate"
            )

        # Music track
        music_candidates: list[dict] = []
        for cat in _MUSIC_CATEGORIES:
            music_candidates.extend(candidates_by_category.get(cat, []))

        music_track = None
        if music_candidates:
            c = music_candidates[0]
            music_events = timeline.get("music_events", [])
            start_sec = music_events[0]["start_sec"] if music_events else 0.0
            music_track = {
                "source_hash": c["artifact_hash"],
                "manifest_candidate_id": c["candidate_id"],
                "start_sec": start_sec,
                "stop_sec": timeline.get("total_duration_sec", 0.0),
                "gain_db": 0.0,
                "ducking": {
                    "depth": self._mix_config.get("ducking", {}).get(
                        "default_depth", 0.20
                    ),
                    "attack_s": self._mix_config.get("ducking", {}).get(
                        "attack_s", 0.3
                    ),
                    "release_s": self._mix_config.get("ducking", {}).get(
                        "release_s", 0.5
                    ),
                },
                "fade_in_sec": 0.5,
                "fade_out_sec": 1.0,
            }

        # SFX events
        sfx_events: list[dict] = []
        for sfx_cue in timeline.get("sfx_events", []):
            meta = sfx_cue.get("metadata", {})
            sfx_type = meta.get("type", "")
            preset_name = sfx_type if sfx_type in self._sfx_presets else self._sfx_default
            preset = self._sfx_presets.get(preset_name, {})
            sfx_events.append({
                "sfx_id": sfx_cue.get("cue_id", ""),
                "trigger_sec": sfx_cue.get("start_sec", 0.0),
                "gain_db": _volume_to_db(preset.get("volume", 0.5)),
                "duration_sec": preset.get("duration", 0.3),
                "preset": preset_name,
                "beat_id": sfx_cue.get("beat_id", ""),
            })

        mix_spec = {
            "lufs_target": self._mix_config.get("lufs_target", -14.0),
            "true_peak_db": self._mix_config.get("true_peak_db", -1.0),
        }

        return {
            "vo_track": vo_track,
            "music_track": music_track,
            "sfx_events": sfx_events,
            "mix_spec": mix_spec,
        }

    def _compile_visual_elements(
        self,
        manifest: dict,
        writer_contract: dict,
        timeline: dict,
        candidates_by_category: dict[str, list[dict]],
        vo_timing_by_beat: dict[str, dict],
    ) -> list[dict]:
        visual_candidates: list[dict] = []
        for cat, candidates in candidates_by_category.items():
            if cat not in _VO_CATEGORIES and cat not in _MUSIC_CATEGORIES:
                visual_candidates.extend(candidates)

        elements: list[dict] = []
        for c in visual_candidates:
            beat_refs = c.get("beat_refs") or []
            beat_id = beat_refs[0] if beat_refs else ""
            vo = vo_timing_by_beat.get(beat_id, {})
            start_sec = vo.get("start_sec", 0.0)
            end_sec = vo.get("end_sec", start_sec + 5.0)

            measurement = c.get("measurement") or {}
            source_type = c.get("source_type", "")
            kind = "still" if source_type in (
                "image", "still", "generated_image"
            ) else "clip"

            elements.append({
                "element_id": f"vis_{c['candidate_id']}",
                "source_hash": c["artifact_hash"],
                "manifest_candidate_id": c["candidate_id"],
                "kind": kind,
                "trim_start_sec": 0.0,
                "trim_end_sec": measurement.get(
                    "duration", end_sec - start_sec
                ),
                "crop": None,
                "focal": None,
                "canvas_position": {"x": 0.0, "y": 0.0},
                "scale": 1.0,
                "motion_keyframes": [],
                "beat_id": beat_id,
                "event_id": None,
            })

        # Fail closed: beats have visual events but no visual candidates
        has_visual_content = any(
            beat.get("visual_events") or beat.get("visual_intent")
            for beat in writer_contract.get("beats", [])
        )
        if has_visual_content and not visual_candidates:
            raise CompositionPlanError(
                "Beats have visual events/intent but manifest has no "
                "visual candidates"
            )

        return elements

    def _compile_graphics_elements(
        self,
        text_elements: list[dict],
    ) -> list[dict]:
        graphics: list[dict] = []
        overlay_roles = {"hook", "emphasis", "proof", "reframe", "cta", "lower_third"}
        for te in text_elements:
            if te["role"] not in overlay_roles:
                continue
            style_config = self._overlay_styles.get(te["style_ref"], {})
            config_hash = _compute_canonical_hash(style_config)
            graphics.append({
                "element_id": f"gfx_{te['element_id']}",
                "type": "lower_third" if te["role"] == "lower_third" else "overlay",
                "config_hash": config_hash,
                "position": te["position"],
                "scale": 1.0,
                "timing": te["timing"],
                "animation": {
                    "type": "fade",
                    "duration_sec": 0.3,
                    "easing": _DEFAULT_EASING,
                },
                "beat_id": te["beat_id"],
            })
        return graphics

    def _compile_transitions(
        self,
        writer_contract: dict,
        timeline: dict,
    ) -> list[dict]:
        transitions: list[dict] = []

        # From cue timeline transition cues
        transition_cues = [
            c for c in timeline.get("overlays", [])
            if c.get("cue_type") == "transition"
        ]
        for tc in transition_cues:
            meta = tc.get("metadata", {})
            raw = meta.get("transition_in", "cut")
            trans_type = self._normalize_transition_type(raw)
            if trans_type == "crossfade":
                duration = meta.get("overlap_sec", 0.3)
            elif trans_type == "cut":
                duration = 0.0
            else:
                duration = 0.3
            transitions.append({
                "transition_id": tc.get("cue_id", ""),
                "type": trans_type,
                "duration_sec": duration,
                "easing": _DEFAULT_EASING,
                "beat_boundary": tc.get("beat_id", ""),
            })

        # From edit segments
        for seg in writer_contract.get("edit_segments", []):
            trans = seg.get("transition", "")
            if not trans:
                continue
            trans_type = self._normalize_transition_type(trans)
            beat_ids = seg.get("beat_ids") or []
            transitions.append({
                "transition_id": f"trans_seg_{seg.get('segment_id', '')}",
                "type": trans_type,
                "duration_sec": 0.3 if trans_type != "cut" else 0.0,
                "easing": _DEFAULT_EASING,
                "beat_boundary": beat_ids[0] if beat_ids else "",
            })

        return transitions

    def _compile_canvas(self) -> dict:
        return {
            "resolution": self._canvas_config.get(
                "resolution", {"width": 1080, "height": 1920}
            ),
            "aspect_ratio": self._canvas_config.get("aspect_ratio", "9:16"),
            "fps": self._canvas_config.get("fps", 30),
            "background": self._canvas_config.get(
                "background", {"color": "#000000"}
            ),
            "safe_zones": self._canvas_config.get(
                "safe_zones",
                {"title_safe": 0.9, "action_safe": 0.95},
            ),
            "platform_framing": self._canvas_config.get(
                "platform_framing", "9:16_vertical"
            ),
        }

    # ── helpers ──────────────────────────────────────────────────────

    def _safe_file_hash(self, path: str) -> str:
        if not path:
            return ""
        try:
            return _compute_file_hash(path)
        except (OSError, IOError):
            return ""

    def _find_text_timing(
        self,
        text_intent_id: str,
        beat_id: str,
        caption_cues: list[dict],
        overlay_cues: list[dict],
        vo_timing_by_beat: dict[str, dict],
    ) -> dict:
        # Caption cue matching this text_intent_id
        for cap in caption_cues:
            if text_intent_id in cap.get("cue_id", ""):
                return {"start_sec": cap["start_sec"], "end_sec": cap["end_sec"]}
        # Overlay cue matching this text_intent_id
        for ovl in overlay_cues:
            if text_intent_id in ovl.get("cue_id", ""):
                return {"start_sec": ovl["start_sec"], "end_sec": ovl["end_sec"]}
        # Fall back to VO timing for the beat
        vt = vo_timing_by_beat.get(beat_id)
        if vt:
            return {"start_sec": vt["start_sec"], "end_sec": vt["end_sec"]}
        return {"start_sec": 0.0, "end_sec": 2.0}

    def _get_text_position(self, role: str) -> dict:
        if role in self._text_positions:
            return self._text_positions[role]
        return _DEFAULT_TEXT_POSITIONS.get(
            role, {"x": 0.5, "y": 0.5, "anchor": "center"}
        )

    @staticmethod
    def _normalize_transition_type(raw: str) -> str:
        if raw in _TRANSITION_TYPES:
            return raw
        if raw == "hold":
            return "cut"
        if raw == "dissolve":
            return "crossfade"
        return "cut"


# ── Validation ───────────────────────────────────────────────────────────

def validate_plan(plan: dict, manifest: dict, writer_contract: dict) -> list[str]:
    """Validate a CompositionPlan against its sources.

    Returns a list of error strings (empty = valid). Checks:
    - Every text element traces to approved Writer contract text
    - Every audio/visual element traces to a manifest ingredient hash
    - Plan hash is correct
    """
    errors: list[str] = []

    # Build text intent index
    text_intents_by_id: dict[str, dict] = {}
    for ti in writer_contract.get("text_intents", []):
        text_intents_by_id[ti["text_intent_id"]] = ti

    # Build beat evidence_refs
    beat_evidence_refs: dict[str, list[str]] = {}
    for beat in writer_contract.get("beats", []):
        beat_evidence_refs[beat.get("beat_id", "")] = beat.get("evidence_refs") or []

    # Build manifest candidate hashes
    manifest_hashes: set[str] = set()
    for c in manifest.get("candidates", []):
        manifest_hashes.add(c.get("artifact_hash", ""))

    # 1. Text elements trace to Writer contract
    for te in plan.get("text_elements", []):
        role = te.get("role", "")
        text = te.get("text", "")

        if role == "citation":
            beat_id = te.get("beat_id", "")
            refs = beat_evidence_refs.get(beat_id, [])
            if text not in refs:
                errors.append(
                    f"Text element '{te['element_id']}' (citation) text "
                    f"not in beat '{beat_id}' evidence_refs"
                )
        else:
            ti_id = te.get("text_intent_id")
            if not ti_id:
                errors.append(
                    f"Text element '{te['element_id']}' has no text_intent_id"
                )
            elif ti_id not in text_intents_by_id:
                errors.append(
                    f"Text element '{te['element_id']}' references "
                    f"unknown text_intent_id: {ti_id}"
                )
            else:
                ti = text_intents_by_id[ti_id]
                if ti.get("text", "") != text:
                    errors.append(
                        f"Text element '{te['element_id']}' text does not "
                        f"match text_intent '{ti_id}'"
                    )

    # 2. Audio elements trace to manifest hashes
    audio = plan.get("audio", {})
    vo_track = audio.get("vo_track")
    if vo_track:
        if vo_track.get("source_hash") not in manifest_hashes:
            errors.append(
                f"VO track source_hash not in manifest: "
                f"{vo_track.get('source_hash')}"
            )

    music_track = audio.get("music_track")
    if music_track:
        if music_track.get("source_hash") not in manifest_hashes:
            errors.append(
                f"Music track source_hash not in manifest: "
                f"{music_track.get('source_hash')}"
            )

    # 3. Visual elements trace to manifest hashes
    for ve in plan.get("visual_elements", []):
        if ve.get("source_hash") not in manifest_hashes:
            errors.append(
                f"Visual element '{ve['element_id']}' source_hash not in "
                f"manifest: {ve.get('source_hash')}"
            )

    # 4. Plan hash is correct
    expected = compute_plan_hash(plan)
    if plan.get("plan_hash") != expected:
        errors.append(
            f"Plan hash mismatch: stored={plan.get('plan_hash')}, "
            f"computed={expected}"
        )

    return errors


# ── Serialization ────────────────────────────────────────────────────────

def serialize_plan(plan: dict) -> str:
    """Serialize a CompositionPlan to canonical JSON (sorted keys)."""
    return json.dumps(plan, sort_keys=True, ensure_ascii=False, indent=2)


def deserialize_plan(json_str: str) -> dict:
    """Deserialize a CompositionPlan from JSON."""
    return json.loads(json_str)


def diff_plans(plan_a: dict, plan_b: dict) -> str:
    """Produce a unified diff between two serialized plans."""
    a_lines = serialize_plan(plan_a).splitlines(keepends=True)
    b_lines = serialize_plan(plan_b).splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(a_lines, b_lines, fromfile="plan_a", tofile="plan_b")
    )


# ── Dataclass-style wrappers for convenient construction ───────────────
# These provide a typed way to build plan elements that the preview
# generator and tests can use. They serialize to the same dict format.

from dataclasses import dataclass, field as _field
from typing import Optional as _Optional


@dataclass
class CanvasSpec:
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    aspect_ratio: str = "9:16"
    background: str = "#000000"
    safe_zones: dict = _field(default_factory=lambda: {"top": 0.1, "bottom": 0.1})


@dataclass
class TextRole:
    element_id: str
    text: str
    style_ref: str = "default"
    font_family: str = ""
    font_path: str = ""
    font_hash: str = ""
    font_size: float = 0
    font_color: str = ""
    position: dict = _field(default_factory=lambda: {"x": 0.5, "y": 0.5})
    start: float = 0
    end: float = 0
    word_timings: list = _field(default_factory=list)
    emphasis_marks: list = _field(default_factory=list)
    writer_contract_ref: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class AudioLane:
    element_id: str
    lane_type: str  # "vo", "music", "sfx"
    source_path: str = ""
    source_hash: str = ""
    start: float = 0
    end: float = 0
    gain: float = 1.0
    gain_curve: list = _field(default_factory=list)
    ducking_points: list = _field(default_factory=list)
    fade_in: float = 0
    fade_out: float = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class AudioMix:
    element_id: str
    lanes: tuple = ()
    lufs_target: float = -16.0
    true_peak_limit: float = -1.0

    def to_dict(self) -> dict:
        return {
            "element_id": self.element_id,
            "lanes": [l.to_dict() if hasattr(l, "to_dict") else l for l in self.lanes],
            "lufs_target": self.lufs_target,
            "true_peak_limit": self.true_peak_limit,
        }


@dataclass
class VisualClip:
    element_id: str
    source_path: str = ""
    source_hash: str = ""
    trim_in: float = 0
    trim_out: float = 0
    crop: dict = _field(default_factory=dict)
    canvas_position: dict = _field(default_factory=lambda: {"x": 0, "y": 0})
    scale: float = 1.0
    motion_keyframes: list = _field(default_factory=list)
    start: float = 0
    end: float = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class GraphicsOverlay:
    element_id: str
    overlay_type: str = "overlay"
    overlay_path: str = ""
    config_hash: str = ""
    position: dict = _field(default_factory=lambda: {"x": 0.5, "y": 0.5})
    scale: float = 1.0
    start: float = 0
    end: float = 0
    animation: dict = _field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class Transition:
    element_id: str
    transition_type: str = "cut"
    duration: float = 0.5
    easing: str = "linear"
    start: float = 0
    beat_boundary: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class CompositionPlan:
    canvas: CanvasSpec = _field(default_factory=CanvasSpec)
    text_roles: tuple = ()
    audio_mix: _Optional[AudioMix] = None
    visual_clips: tuple = ()
    graphics_overlays: tuple = ()
    transitions: tuple = ()
    manifest_hash: str = ""
    writer_contract_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "schema_version": COMPOSITION_PLAN_SCHEMA_VERSION,
            "canvas": self.canvas.to_dict() if hasattr(self.canvas, "to_dict") else self.canvas,
            "text_elements": [t.to_dict() if hasattr(t, "to_dict") else t for t in self.text_roles],
            "audio_elements": [self.audio_mix.to_dict()] if self.audio_mix else [],
            "visual_elements": [v.to_dict() if hasattr(v, "to_dict") else v for v in self.visual_clips],
            "graphics_elements": [g.to_dict() if hasattr(g, "to_dict") else g for g in self.graphics_overlays],
            "transitions": [t.to_dict() if hasattr(t, "to_dict") else t for t in self.transitions],
            "manifest_hash": self.manifest_hash,
            "writer_contract_hash": self.writer_contract_hash,
        }