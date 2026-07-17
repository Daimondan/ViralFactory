"""
ViralFactory — EpisodePlan Schema + Shot Spec Assembly + Edit Plan Compilation
(T11.6 — CORRECTION-episode-format-and-reference-assets-v1.0 §3)

This module implements the EpisodePlan layer:

1. EPISODE_PLAN_SCHEMA — the JSON schema for episode-format pieces. Beats are
   first-class with: id, role, vo_text, register, staged_action, location_ref,
   graphics. The approved text for episode-format pieces IS the ordered vo_text
   sequence — so AMENDMENT-008's text-boundary firewall automatically protects
   the script verbatim through remediation.

2. ShotSpecAssembler — mechanical assembly of shot specs from beats + registry
   refs. The shot spec is NOT LLM-freeform: it is
     character_block(character_ref) + staged_action + location_block(location_ref) + grade_token
   Reference images are always the canonical registry files — never chained
   outputs. Re-anchoring is structural. One shot per beat by construction.

3. EpisodePlanCompiler — compiles an EpisodePlan down to the EXISTING edit plan
   schema (pipeline.EDIT_PLAN_SCHEMA): one segment per beat, beat_id on each
   segment, overlays = captions chunked 3–5 words from vo_text + graphics,
   audio block = VO primary + registry music_bed for dominant register (ducked),
   enforced loudnorm I=-14 for this format (not optional).

No business-specific values live in this code. All tenant content comes from
the episode-format module and reference asset registry.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Optional


# ── Constants ────────────────────────────────────────────────────────────────

# Episode-format loudness target — enforced (not optional) per §3.3 + §6
EPISODE_LOUDNORM_I = -14.0
EPISODE_LOUDNORM_TP = -1.5
EPISODE_LOUDNORM_LRA = 11.0

# Caption chunking for episode format: 3–5 words per caption overlay
CAPTION_CHUNK_MIN = 3
CAPTION_CHUNK_MAX = 5

# Graphics types the renderer knows how to draw (no text in generated images)
GRAPHICS_TYPES = frozenset({"number_card", "title_card", "quote_card"})

# Episode beat roles (per §1.1 beat grammar — superset of production_contract roles)
EPISODE_BEAT_ROLES = frozenset({
    "hook", "setup", "struggle", "turn", "lesson", "cta",
})

# Banned tokens in staged_action / image prompts (§3.2) — the renderer owns all
# text/numbers. The mush class is eliminated by construction.
BANNED_PROMPT_TOKENS = frozenset({
    "text", "words", "sign", "screen", "phone", "logo",
    "document", "chart", "letters", "numbers on",
})


# ── EpisodePlan JSON Schema ──────────────────────────────────────────────────

EPISODE_BEAT_SCHEMA = {
    "type": "object",
    "required": ["id", "role", "vo_text", "register", "staged_action", "location_ref"],
    "properties": {
        "id": {"type": "string", "minLength": 1},         # b01, b02, ...
        "role": {
            "type": "string",
            "enum": list(EPISODE_BEAT_ROLES),
        },
        "vo_text": {"type": "string", "minLength": 1},   # the exact spoken line
        "register": {"type": "string"},                   # somber | hopeful | wry | ...
        "staged_action": {"type": "string", "minLength": 1},  # one sentence: what the character does
        "location_ref": {"type": "string", "minLength": 1},   # registry location_ref name
        "character_ref": {"type": "string"},                 # registry character_ref name (optional per beat)
        "graphics": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["type", "text", "style"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": list(GRAPHICS_TYPES),
                    },
                    "text": {"type": "string", "minLength": 1},
                    "style": {"type": "string"},  # card_style ref from registry
                },
            },
        },
        "duration_ms": {"type": "number"},  # measured VO duration (per-beat master clock)
    },
}

EPISODE_PLAN_SCHEMA = {
    "type": "object",
    "required": ["format_module", "beats"],
    "properties": {
        "format_module": {"type": "string", "minLength": 1},  # e.g. "episode-format-parable@v1"
        "beats": {
            "type": "array",
            "minItems": 1,
            "items": EPISODE_BEAT_SCHEMA,
        },
    },
}


# ── Validation ───────────────────────────────────────────────────────────────

class EpisodePlanValidationError(Exception):
    """Raised when an EpisodePlan fails schema validation."""
    pass


def validate_episode_plan_schema(plan: dict) -> list[str]:
    """Validate an EpisodePlan against the schema.

    Returns a list of error strings (empty = valid).
    """
    errors = []

    # Required top-level fields
    if "format_module" not in plan or not plan["format_module"]:
        errors.append("Missing required field: format_module")
    if "beats" not in plan or not isinstance(plan["beats"], list):
        errors.append("Missing or invalid 'beats' array")
        return errors

    if len(plan["beats"]) == 0:
        errors.append("beats array must have at least one beat")
        return errors

    seen_ids = set()
    for i, beat in enumerate(plan["beats"]):
        if not isinstance(beat, dict):
            errors.append(f"Beat {i} is not an object")
            continue

        bid = beat.get("id", "")
        if not bid:
            errors.append(f"Beat {i} missing 'id'")
        elif bid in seen_ids:
            errors.append(f"Duplicate beat id: {bid}")
        else:
            seen_ids.add(bid)

        for field_name in ("id", "role", "vo_text", "register", "staged_action", "location_ref"):
            if field_name not in beat or not beat[field_name]:
                errors.append(f"Beat '{bid}': missing or empty '{field_name}'")

        # Role must be valid
        role = beat.get("role", "")
        if role and role not in EPISODE_BEAT_ROLES:
            errors.append(
                f"Beat '{bid}': role '{role}' not in allowed episode roles: {sorted(EPISODE_BEAT_ROLES)}"
            )

        # Graphics validation
        graphics = beat.get("graphics", [])
        if not isinstance(graphics, list):
            errors.append(f"Beat '{bid}': graphics must be an array")
        else:
            for j, g in enumerate(graphics):
                if not isinstance(g, dict):
                    errors.append(f"Beat '{bid}': graphics[{j}] is not an object")
                    continue
                for gf in ("type", "text", "style"):
                    if not g.get(gf):
                        errors.append(f"Beat '{bid}': graphics[{j}] missing '{gf}'")
                gtype = g.get("type", "")
                if gtype and gtype not in GRAPHICS_TYPES:
                    errors.append(
                        f"Beat '{bid}': graphics[{j}] type '{gtype}' not in {sorted(GRAPHICS_TYPES)}"
                    )

    return errors


# ── Shot Spec Assembly (mechanical — no LLM) ──────────────────────────────────

@dataclass
class ShotSpec:
    """A mechanically assembled shot spec for one beat.

    Per §3.2: image_prompt = character_block + staged_action + location_block + grade_token
    Reference images are always canonical registry files — never chained outputs.
    """
    beat_id: str
    image_prompt: str              # mechanically assembled — no LLM freeform
    reference_images: list[str]     # canonical registry file paths
    motion_prompt: str = ""        # LLM-authored camera/movement line (optional, separate)
    duration_ms: float = 0.0       # measured VO duration of the beat
    graphics: list[dict] = field(default_factory=list)
    location_ref: str = ""
    character_ref: str = ""

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "image_prompt": self.image_prompt,
            "reference_images": self.reference_images,
            "motion_prompt": self.motion_prompt,
            "duration_ms": self.duration_ms,
            "graphics": self.graphics,
            "location_ref": self.location_ref,
            "character_ref": self.character_ref,
        }


class ShotSpecAssembler:
    """Mechanically assembles shot specs from EpisodePlan beats + registry refs.

    The shot spec is NOT LLM-freeform. It is:
      character_block(character_ref) + staged_action + location_block(location_ref) + grade_token

    All text/numbers are renderer-drawn graphics. The mush class is eliminated
    by construction, not by review.
    """

    def __init__(self, ref_store=None, business_slug: str = ""):
        """
        Args:
            ref_store: ReferenceAssetStore instance for resolving registry refs.
            business_slug: Current business slug for registry lookups.
        """
        self.ref_store = ref_store
        self.business_slug = business_slug

    def _resolve_character_block(self, character_ref: str) -> str:
        """Build the character block from the registry character_ref.

        Returns a prompt fragment describing the character's visual identity
        (face canon + wardrobe). If the ref doesn't resolve, returns the ref
        name as a fallback (the lint layer catches unresolvable refs).
        """
        if not character_ref:
            return ""

        if self.ref_store:
            asset = self.ref_store.resolve_ref(
                self.business_slug, "character_ref", character_ref
            )
            if asset:
                payload = json.loads(asset["payload_json"])
                face = payload.get("face_canon", "")
                wardrobe = payload.get("wardrobe_canon", "")
                parts = []
                if face:
                    parts.append(face)
                if wardrobe:
                    parts.append(f"wearing {wardrobe}")
                if parts:
                    return ", ".join(parts)

        return character_ref  # fallback — lint layer catches unresolvable refs

    def _resolve_location_block(self, location_ref: str) -> str:
        """Build the location block from the registry location_ref.

        Returns the location's prompt_text (the approved description that
        produced the establishing plate). Falls back to the ref name.
        """
        if not location_ref:
            return ""

        if self.ref_store:
            asset = self.ref_store.resolve_ref(
                self.business_slug, "location_ref", location_ref
            )
            if asset:
                payload = json.loads(asset["payload_json"])
                prompt = payload.get("prompt_text", "")
                if prompt:
                    return prompt

        return location_ref  # fallback

    def _resolve_grade_token(self) -> str:
        """Get the verbatim grade token string from the registry."""
        if self.ref_store:
            return self.ref_store.get_grade_token(self.business_slug) or ""
        return ""

    def _resolve_reference_images(self, character_ref: str, location_ref: str) -> list[str]:
        """Get the canonical reference image file paths from the registry.

        Always the canonical registry files — never chained outputs.
        Re-anchoring is structural.
        """
        refs = []

        if self.ref_store:
            if character_ref:
                char_asset = self.ref_store.resolve_ref(
                    self.business_slug, "character_ref", character_ref
                )
                if char_asset:
                    payload = json.loads(char_asset["payload_json"])
                    refs.extend(payload.get("files", []))

            if location_ref:
                loc_asset = self.ref_store.resolve_ref(
                    self.business_slug, "location_ref", location_ref
                )
                if loc_asset:
                    payload = json.loads(loc_asset["payload_json"])
                    refs.extend(payload.get("files", []))

        return refs

    def assemble_shot_spec(self, beat: dict) -> ShotSpec:
        """Mechanically assemble a shot spec from one beat.

        image_prompt = character_block + staged_action + location_block + grade_token
        This is mechanical assembly — no LLM, no creative judgment.
        """
        beat_id = beat.get("id", "")
        character_ref = beat.get("character_ref", "")
        location_ref = beat.get("location_ref", "")
        staged_action = beat.get("staged_action", "")

        # Build blocks mechanically
        character_block = self._resolve_character_block(character_ref)
        location_block = self._resolve_location_block(location_ref)
        grade_token = self._resolve_grade_token()

        # Assemble image prompt: character + action + location + grade
        prompt_parts = []
        if character_block:
            prompt_parts.append(character_block)
        if staged_action:
            prompt_parts.append(staged_action)
        if location_block:
            prompt_parts.append(location_block)
        if grade_token:
            prompt_parts.append(grade_token)

        image_prompt = ", ".join(prompt_parts)

        # Reference images = canonical registry files (never chained)
        reference_images = self._resolve_reference_images(character_ref, location_ref)

        return ShotSpec(
            beat_id=beat_id,
            image_prompt=image_prompt,
            reference_images=reference_images,
            motion_prompt="",  # LLM-authored separately (storyboard/animation stage)
            duration_ms=beat.get("duration_ms", 0.0),
            graphics=beat.get("graphics", []),
            location_ref=location_ref,
            character_ref=character_ref,
        )

    def assemble_all(self, beats: list[dict]) -> list[ShotSpec]:
        """Assemble shot specs for all beats — one shot per beat by construction."""
        return [self.assemble_shot_spec(b) for b in beats]

    def scan_banned_tokens(self, shot_spec: ShotSpec) -> list[str]:
        """Check a shot spec's image_prompt for banned tokens.

        Per §3.2: text, words, sign, screen, phone, logo, document, chart,
        letters, 'numbers on' are banned. All text/numbers are renderer-drawn.
        """
        violations = []
        prompt_lower = shot_spec.image_prompt.lower()
        for token in BANNED_PROMPT_TOKENS:
            if token in prompt_lower:
                violations.append(token)
        return violations


# ── Edit Plan Compilation (EpisodePlan → existing EDIT_PLAN_SCHEMA) ─────────

class EpisodePlanCompiler:
    """Compiles an EpisodePlan down to the existing edit plan schema.

    Per §3.3: one segment per beat, beat_id on each segment, overlays = captions
    chunked 3–5 words from vo_text + graphics as overlay entries, sfx per
    standing order 10, audio = VO primary + registry music_bed for dominant
    register (ducked), loudnorm I=-14 ENFORCED for this format.

    The existing renderer (assembly.py) executes the plan — no renderer rewrite.
    """

    def __init__(self, ref_store=None, business_slug: str = ""):
        self.ref_store = ref_store
        self.business_slug = business_slug

    def _chunk_vo_text(self, vo_text: str) -> list[str]:
        """Chunk vo_text into 3–5 word caption phrases.

        Per §3.3: captions chunked 3–5 words from vo_text.
        """
        words = vo_text.strip().split()
        if not words:
            return []

        chunks = []
        i = 0
        while i < len(words):
            # Take 3–5 words, but don't leave a dangling 1–2 word chunk at the end
            remaining = len(words) - i
            if remaining <= CAPTION_CHUNK_MAX:
                # Take all remaining if they fit in the max
                chunk_len = remaining
            else:
                chunk_len = CAPTION_CHUNK_MAX
                # If taking 5 would leave 1–2 words, take 4 or 3 instead
                leftover = remaining - chunk_len
                if leftover < CAPTION_CHUNK_MIN:
                    chunk_len = remaining - CAPTION_CHUNK_MIN
                    if chunk_len < CAPTION_CHUNK_MIN:
                        chunk_len = CAPTION_CHUNK_MIN

            chunk = " ".join(words[i:i + chunk_len])
            chunks.append(chunk)
            i += chunk_len

        return chunks

    def _build_caption_overlays(self, beat: dict, beat_index: int,
                                  cumulative_start: float) -> tuple[list[dict], float]:
        """Build caption overlays for one beat's vo_text.

        Returns (overlays, beat_end_time).
        Captions are chunked 3–5 words, timed proportionally within the beat.
        """
        vo_text = beat.get("vo_text", "")
        duration_ms = beat.get("duration_ms", 0.0)
        duration_s = duration_ms / 1000.0 if duration_ms > 100 else duration_ms

        chunks = self._chunk_vo_text(vo_text)
        if not chunks or duration_s <= 0:
            return [], cumulative_start + duration_s

        # Distribute chunks proportionally across the beat duration
        total_words = sum(len(c.split()) for c in chunks)
        overlays = []
        current_offset = cumulative_start

        for chunk in chunks:
            chunk_words = len(chunk.split())
            chunk_duration = (chunk_words / total_words) * duration_s
            overlays.append({
                "type": "caption",
                "text": chunk,
                "start": round(current_offset, 2),
                "end": round(current_offset + chunk_duration, 2),
                "style_ref": "default",
                "position": "bottom",
            })
            current_offset += chunk_duration

        return overlays, cumulative_start + duration_s

    def _build_graphics_overlays(self, beat: dict, beat_start: float,
                                    beat_end: float) -> list[dict]:
        """Build graphics overlays (number_card, title_card, quote_card).

        Per §3.3: the beat's graphics are overlay entries. These are
        renderer-drawn — no text in generated images.
        """
        overlays = []
        graphics = beat.get("graphics", [])

        for g in graphics:
            overlays.append({
                "type": g.get("type", "title_card"),
                "text": g.get("text", ""),
                "start": round(beat_start, 2),
                "end": round(beat_end, 2),
                "style_ref": g.get("style", "default"),
                "position": "center",
            })

        return overlays

    def _resolve_dominant_register(self, beats: list[dict]) -> str:
        """Find the dominant register across all beats.

        Used to select the registry music_bed for the audio block.
        """
        register_counts: dict[str, int] = {}
        for beat in beats:
            register = beat.get("register", "")
            if register:
                register_counts[register] = register_counts.get(register, 0) + 1

        if not register_counts:
            return ""

        return max(register_counts, key=register_counts.get)

    def _resolve_music_bed_ref(self, register: str) -> str:
        """Resolve the dominant register to a registry music_bed reference.

        Returns a reference string like "registry:bed_somber" or empty string
        if no bed resolves.
        """
        if not register or not self.ref_store:
            return ""

        bed_name = f"bed_{register}"
        asset = self.ref_store.resolve_ref(
            self.business_slug, "music_bed", bed_name
        )
        if asset:
            return f"registry:bed_{register}"
        return ""

    def compile_to_edit_plan(
        self,
        episode_plan: dict,
        vo_take_id: str = "",
        canvas_aspect: str = "9:16",
        canvas_resolution: str = "1080x1920",
    ) -> dict:
        """Compile an EpisodePlan to the existing edit plan schema.

        Per §3.3:
        - One segment per beat (source: generated:<video_media_id>, in/out = full clip)
        - beat_id carried on each segment
        - overlays = captions chunked 3–5 words from vo_text + graphics
        - sfx per existing standing order 10
        - audio = VO primary + registry music_bed for dominant register, ducked
        - loudnorm I=-14 ENFORCED for this format (not optional)

        Args:
            episode_plan: The EpisodePlan dict with format_module + beats[]
            vo_take_id: The VO take ID for the audio block
            canvas_aspect: Canvas aspect ratio
            canvas_resolution: Canvas resolution (e.g. "1080x1920")

        Returns:
            A dict matching the existing EDIT_PLAN_SCHEMA (pipeline.py).
        """
        beats = episode_plan.get("beats", [])
        if not beats:
            raise EpisodePlanValidationError("EpisodePlan has no beats")

        # Validate schema first
        errors = validate_episode_plan_schema(episode_plan)
        if errors:
            raise EpisodePlanValidationError(
                f"EpisodePlan schema invalid: {'; '.join(errors)}"
            )

        segments = []
        cumulative_time = 0.0
        total_duration = 0.0

        for i, beat in enumerate(beats):
            beat_id = beat.get("id", f"b{i+1:02d}")
            duration_ms = beat.get("duration_ms", 0.0)
            # Convert ms to seconds if it looks like milliseconds
            if duration_ms > 100:
                duration_s = duration_ms / 1000.0
            else:
                duration_s = duration_ms

            beat_start = cumulative_time
            beat_end = cumulative_time + duration_s

            # Build overlays: captions + graphics
            caption_overlays, beat_end = self._build_caption_overlays(
                beat, i, beat_start
            )
            graphics_overlays = self._build_graphics_overlays(
                beat, beat_start, beat_end
            )
            overlays = caption_overlays + graphics_overlays

            # One segment per beat — source will be resolved to generated:<video_media_id>
            # The media_id is filled when the animation is produced (storyboard gate)
            segment = {
                "source": f"generated:pending_{beat_id}",
                "in": 0,
                "out": round(duration_s, 2),
                "beat_id": beat_id,  # ← carried on each segment for compliance linkage
                "transition_in": "cut" if i > 0 else "none",
                "overlays": overlays,
                "sfx": [],  # per standing order 10 — sparse, motivated only
            }
            segments.append(segment)

            cumulative_time = beat_end
            total_duration += duration_s

        # Audio block: VO primary + registry music_bed for dominant register, ducked
        dominant_register = self._resolve_dominant_register(beats)
        music_ref = self._resolve_music_bed_ref(dominant_register)

        audio_block = {
            "vo": {
                "take_id": vo_take_id,
                "ducking": True,
            },
            "original_audio": False,  # episode format: narration-over-scenes, no on-camera dialogue
        }
        if music_ref:
            audio_block["music"] = {
                "stock_ref": music_ref,  # registry bed reference
                "volume": 0.15,  # ducked under VO
            }

        # Captions config
        captions_block = {
            "burned_in": True,
            "source": "vo_script",
            "style_ref": "default",
        }

        # Canvas
        canvas_block = {
            "aspect_ratio": canvas_aspect,
            "resolution": canvas_resolution,
            "duration_target": round(total_duration, 1),
        }

        # Episode-format loudnorm enforcement (§3.3 + §6)
        # This flag tells the renderer to use I=-14 (not the default I=-16)
        # for episode-format pieces. The renderer checks this to select the
        # correct loudnorm target.
        edit_plan = {
            "segments": segments,
            "audio": audio_block,
            "captions": captions_block,
            "canvas": canvas_block,
            # Episode-format-specific metadata
            "episode_format": True,  # ← signals the renderer to enforce I=-14
            "loudnorm_target": {
                "I": EPISODE_LOUDNORM_I,
                "TP": EPISODE_LOUDNORM_TP,
                "LRA": EPISODE_LOUDNORM_LRA,
            },
            "format_module": episode_plan.get("format_module", ""),
        }

        return edit_plan

    def compile_compliance_beats(self, episode_plan: dict) -> list[dict]:
        """Compile EpisodePlan beats to AMENDMENT-008 compliance contract beats.

        Per §3.1: compliance contract beats map 1:1 to authored beats (beat_id
        on segments). The approved text = ordered vo_text sequence — the
        text-boundary firewall protects it.

        Returns a list of compliance contract beat dicts matching the
        COMPLIANCE_CONTRACT_SCHEMA beats format (pipeline.py).
        """
        beats = episode_plan.get("beats", [])
        compliance_beats = []

        for beat in beats:
            beat_id = beat.get("id", "")
            vo_text = beat.get("vo_text", "")
            role = beat.get("role", "")

            # Map episode beat role to compliance requirement_type
            if role == "hook":
                req_type = "hook"
            elif role == "cta":
                req_type = "cta"
            else:
                req_type = "spoken_dialogue"

            # verification_method for episode format
            if role in ("hook", "cta"):
                verification = "format_convention_check"
            else:
                verification = "audio_transcript_match"

            compliance_beats.append({
                "beat_id": beat_id,
                "source_excerpt": vo_text,  # the approved text — firewall protects this
                "requirement_type": req_type,
                "required": True,
                "planned_segment_ids": [f"seg_{beat_id}"],
                "planned_time_range": None,  # filled after timing is measured
                "verification_method": verification,
            })

        return compliance_beats


# ── Approved text extraction (AMENDMENT-008 firewall) ───────────────────────

def extract_approved_text(episode_plan: dict) -> str:
    """Extract the ordered vo_text sequence — the approved text for episode format.

    Per §3.1: the platform_content (approved text) for episode-format pieces
    IS the ordered vo_text sequence. AMENDMENT-008's text-boundary firewall
    automatically protects the script verbatim through remediation.

    Returns the concatenated vo_text of all beats in order.
    """
    beats = episode_plan.get("beats", [])
    return " ".join(beat.get("vo_text", "") for beat in beats).strip()


def extract_approved_text_hash(episode_plan: dict) -> str:
    """Compute a SHA-256 hash of the approved text (ordered vo_text sequence).

    This is the hash-lock for the AMENDMENT-008 text-boundary firewall.
    Any remediation that would change the vo_text is detected by comparing
    this hash before and after.
    """
    import hashlib
    approved = extract_approved_text(episode_plan)
    return hashlib.sha256(approved.encode("utf-8")).hexdigest()


# ── Loudnorm filter string generation ───────────────────────────────────────

def episode_loudnorm_filter() -> str:
    """Generate the ffmpeg loudnorm filter string for episode format.

    Enforced I=-14 (not the default I=-16) per §3.3 + §6.
    """
    return f"loudnorm=I={EPISODE_LOUDNORM_I}:TP={EPISODE_LOUDNORM_TP}:LRA={EPISODE_LOUDNORM_LRA}"


def is_episode_format_plan(plan: dict) -> bool:
    """Check if an edit plan is an episode-format plan (for loudnorm enforcement).

    The renderer uses this to select the correct loudnorm target.
    """
    return plan.get("episode_format", False) is True