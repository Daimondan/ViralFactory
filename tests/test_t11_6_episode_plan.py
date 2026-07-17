"""
T11.6 — EpisodePlan schema + Writer beats + media plan v2 tests.

Proves:
1. EpisodePlan schema validates (valid plans pass, invalid plans fail)
2. Shot spec assembly is mechanical (character_block + staged_action + location_block + grade_token)
3. Edit plan compiles with beat_id on segments (existing EDIT_PLAN_SCHEMA)
4. Loudnorm I=-14 is enforced for episode format (not optional)
5. One shot per beat by construction
6. Compliance contract beats map 1:1 to authored beats
7. Approved text = ordered vo_text sequence (AMENDMENT-008 firewall)
8. Banned tokens detected in shot specs
9. Caption chunking 3–5 words
10. Graphics overlays from beat graphics
"""

import json
import os
import sys
import pytest
import sqlite3
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from episode_plan import (
    EPISODE_PLAN_SCHEMA,
    EPISODE_BEAT_SCHEMA,
    EPISODE_BEAT_ROLES,
    GRAPHICS_TYPES,
    BANNED_PROMPT_TOKENS,
    EPISODE_LOUDNORM_I,
    EPISODE_LOUDNORM_TP,
    EPISODE_LOUDNORM_LRA,
    ShotSpec,
    ShotSpecAssembler,
    EpisodePlanCompiler,
    EpisodePlanValidationError,
    validate_episode_plan_schema,
    extract_approved_text,
    extract_approved_text_hash,
    episode_loudnorm_filter,
    is_episode_format_plan,
)
from reference_assets import ReferenceAssetStore


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    """Temporary database for reference asset registry."""
    return str(tmp_path / "test_vf.db")


@pytest.fixture
def ref_store(tmp_db):
    """ReferenceAssetStore with pre-seeded approved assets."""
    store = ReferenceAssetStore(db_path=tmp_db)

    # Seed a character_ref
    store.propose("test_business", "character_ref", "the_elder", {
        "name": "The Elder",
        "face_canon": "an older man with weathered hands and calm eyes",
        "wardrobe_canon": "linen shirt and simple trousers",
        "files": ["data/media/reference/test_business/character_ref/the_elder/front.png",
                   "data/media/reference/test_business/character_ref/the_elder/3q_left.png"],
    })
    char_asset = store.list_assets("test_business", kind="character_ref")[0]
    store.approve(char_asset["id"])

    # Seed a location_ref
    store.propose("test_business", "location_ref", "kitchen_dawn", {
        "prompt_text": "a rustic kitchen at dawn, golden light through a small window",
        "files": ["data/media/reference/test_business/location_ref/kitchen_dawn/plate1.png"],
    })
    loc_asset = store.list_assets("test_business", kind="location_ref")[0]
    store.approve(loc_asset["id"])

    # Seed a grade_token
    store.propose("test_business", "grade_token", "default", {
        "grade_string": "warm golden-hour Caribbean light, soft film grain, shallow depth of field",
    })
    grade_asset = store.list_assets("test_business", kind="grade_token")[0]
    store.approve(grade_asset["id"])

    # Seed a music_bed
    store.propose("test_business", "music_bed", "bed_somber", {
        "file": "data/media/reference/test_business/music_bed/bed_somber.mp3",
        "register": "somber",
        "duration": 80,
        "source": "elevenlabs_music",
    })
    bed_asset = store.list_assets("test_business", kind="music_bed")[0]
    store.approve(bed_asset["id"])

    # Seed a card_style
    store.propose("test_business", "card_style", "title_card_v1", {
        "font": "DejaVuSans-Bold",
        "fontsize": 80,
        "fontcolor": "white",
    })
    style_asset = store.list_assets("test_business", kind="card_style")[0]
    store.approve(style_asset["id"])

    return store


def _make_beat(bid="b01", role="hook", vo_text="I worked fifty years.",
               register="somber", staged_action="the man sits alone at the kitchen table",
               location_ref="kitchen_dawn", character_ref="the_elder",
               graphics=None, duration_ms=3000):
    """Helper: create a valid episode beat."""
    beat = {
        "id": bid,
        "role": role,
        "vo_text": vo_text,
        "register": register,
        "staged_action": staged_action,
        "location_ref": location_ref,
        "character_ref": character_ref,
        "duration_ms": duration_ms,
    }
    if graphics is not None:
        beat["graphics"] = graphics
    return beat


def _make_valid_plan(beats=None):
    """Helper: create a valid EpisodePlan."""
    if beats is None:
        beats = [
            _make_beat("b01", "hook", "I worked fifty years and retired with nothing.",
                       graphics=[{"type": "number_card", "text": "50 YEARS", "style": "title_card_v1"}]),
            _make_beat("b02", "setup", "Every morning I sit at this same table."),
            _make_beat("b03", "struggle", "I tried saving, but inflation ate it."),
            _make_beat("b04", "struggle", "I tried investing, but I was too late."),
            _make_beat("b05", "turn", "Then I learned about compound consistency."),
            _make_beat("b06", "lesson", "Small amounts, every week, over time."),
            _make_beat("b07", "cta", "Start now. Not next year. Now."),
        ]
    return {
        "format_module": "episode-format-parable@v1",
        "beats": beats,
    }


# ── 1. EpisodePlan schema validation ────────────────────────────────────────

class TestEpisodePlanSchema:
    """EpisodePlan schema validates correctly."""

    def test_valid_plan_passes(self):
        plan = _make_valid_plan()
        errors = validate_episode_plan_schema(plan)
        assert errors == [], f"Valid plan should have no errors: {errors}"

    def test_missing_format_module_fails(self):
        plan = _make_valid_plan()
        plan["format_module"] = ""
        errors = validate_episode_plan_schema(plan)
        assert any("format_module" in e for e in errors)

    def test_empty_beats_fails(self):
        plan = {"format_module": "test@v1", "beats": []}
        errors = validate_episode_plan_schema(plan)
        assert any("at least one" in e.lower() for e in errors)

    def test_beat_missing_id_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["id"] = ""
        errors = validate_episode_plan_schema(plan)
        assert any("missing" in e.lower() and "id" in e.lower() for e in errors)

    def test_duplicate_beat_id_fails(self):
        plan = _make_valid_plan()
        plan["beats"][1]["id"] = "b01"  # duplicate
        errors = validate_episode_plan_schema(plan)
        assert any("duplicate" in e.lower() for e in errors)

    def test_invalid_role_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["role"] = "invalid_role"
        errors = validate_episode_plan_schema(plan)
        assert any("role" in e.lower() for e in errors)

    def test_missing_vo_text_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["vo_text"] = ""
        errors = validate_episode_plan_schema(plan)
        assert any("vo_text" in e.lower() for e in errors)

    def test_missing_staged_action_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["staged_action"] = ""
        errors = validate_episode_plan_schema(plan)
        assert any("staged_action" in e.lower() for e in errors)

    def test_missing_location_ref_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["location_ref"] = ""
        errors = validate_episode_plan_schema(plan)
        assert any("location_ref" in e.lower() for e in errors)

    def test_invalid_graphics_type_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["graphics"] = [{"type": "invalid_card", "text": "X", "style": "s"}]
        errors = validate_episode_plan_schema(plan)
        assert any("graphics" in e.lower() and "type" in e.lower() for e in errors)

    def test_graphics_missing_text_fails(self):
        plan = _make_valid_plan()
        plan["beats"][0]["graphics"] = [{"type": "number_card", "text": "", "style": "s"}]
        errors = validate_episode_plan_schema(plan)
        assert any("graphics" in e.lower() and "text" in e.lower() for e in errors)


# ── 2. Shot spec assembly is mechanical ──────────────────────────────────────

class TestShotSpecAssembly:
    """Shot spec assembly is mechanical: character_block + staged_action + location_block + grade_token."""

    def test_assembles_all_four_blocks(self, ref_store):
        """The image_prompt contains all four mechanical blocks."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        beat = _make_beat(staged_action="the man sits alone at the kitchen table")
        spec = assembler.assemble_shot_spec(beat)

        # character_block: from registry character_ref payload
        assert "older man" in spec.image_prompt or "weathered" in spec.image_prompt
        # staged_action: the beat's action text
        assert "the man sits alone at the kitchen table" in spec.image_prompt
        # location_block: from registry location_ref prompt_text
        assert "kitchen" in spec.image_prompt.lower() or "dawn" in spec.image_prompt.lower()
        # grade_token: from registry
        assert "warm golden-hour" in spec.image_prompt or "film grain" in spec.image_prompt

    def test_reference_images_are_canonical_registry_files(self, ref_store):
        """Reference images are always canonical registry files — never chained outputs."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        beat = _make_beat()
        spec = assembler.assemble_shot_spec(beat)

        # Should include character_ref files
        assert any("the_elder" in f for f in spec.reference_images)
        # Should include location_ref files
        assert any("kitchen_dawn" in f for f in spec.reference_images)

    def test_one_shot_per_beat_by_construction(self, ref_store):
        """Exactly one shot spec per beat — by construction."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        specs = assembler.assemble_all(plan["beats"])
        assert len(specs) == len(plan["beats"])

    def test_no_character_ref_produces_empty_character_block(self, ref_store):
        """A beat without character_ref produces a shot spec without a character block."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        beat = _make_beat(character_ref="")
        spec = assembler.assemble_shot_spec(beat)
        # Should still have staged_action and location_block and grade
        assert "the man sits alone" in spec.image_prompt
        assert "kitchen" in spec.image_prompt.lower() or "dawn" in spec.image_prompt.lower()

    def test_banned_tokens_detected(self):
        """Banned tokens in shot spec image_prompt are detected."""
        assembler = ShotSpecAssembler(ref_store=None, business_slug="test")
        spec = ShotSpec(
            beat_id="b01",
            image_prompt="a phone showing a screen with text saying hello",
            reference_images=[],
        )
        violations = assembler.scan_banned_tokens(spec)
        assert len(violations) > 0
        assert "phone" in violations
        assert "screen" in violations
        assert "text" in violations

    def test_clean_prompt_has_no_banned_tokens(self, ref_store):
        """A clean shot spec has no banned tokens."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        beat = _make_beat(staged_action="the man sits alone at the kitchen table at dawn")
        spec = assembler.assemble_shot_spec(beat)
        violations = assembler.scan_banned_tokens(spec)
        assert violations == [], f"Unexpected banned tokens: {violations}"

    def test_shot_spec_is_mechanical_not_llm_freeform(self, ref_store):
        """The image_prompt is assembled from registry data, not LLM-authored."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        beat1 = _make_beat(staged_action="the man sits alone at the kitchen table")
        spec1 = assembler.assemble_shot_spec(beat1)

        # Same registry refs + same staged_action → same image_prompt (deterministic)
        beat2 = _make_beat(staged_action="the man sits alone at the kitchen table")
        spec2 = assembler.assemble_shot_spec(beat2)
        assert spec1.image_prompt == spec2.image_prompt, "Mechanical assembly must be deterministic"

    def test_assemble_all_returns_shot_specs(self, ref_store):
        """assemble_all returns a list of ShotSpec objects."""
        assembler = ShotSpecAssembler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        specs = assembler.assemble_all(plan["beats"])
        assert all(isinstance(s, ShotSpec) for s in specs)
        assert all(s.beat_id for s in specs)


# ── 3. Edit plan compilation with beat_id on segments ────────────────────────

class TestEditPlanCompilation:
    """EpisodePlan compiles to existing edit plan with beat_id on segments."""

    def test_compiles_to_edit_plan_schema(self, ref_store):
        """The compiled plan has segments, audio, captions, canvas — matching EDIT_PLAN_SCHEMA."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan, vo_take_id="vo_take_1")

        assert "segments" in edit_plan
        assert "audio" in edit_plan
        assert "captions" in edit_plan
        assert "canvas" in edit_plan
        assert len(edit_plan["segments"]) == len(plan["beats"])

    def test_beat_id_on_every_segment(self, ref_store):
        """Every segment carries beat_id for compliance-contract linkage."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)

        for seg, beat in zip(edit_plan["segments"], plan["beats"]):
            assert seg["beat_id"] == beat["id"], f"Segment beat_id mismatch: {seg.get('beat_id')} != {beat['id']}"

    def test_one_segment_per_beat(self, ref_store):
        """Exactly one segment per beat."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        assert len(edit_plan["segments"]) == len(plan["beats"])

    def test_segment_source_is_generated(self, ref_store):
        """Segment source is generated:<beat_id> (resolved to video_media_id after animation)."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        for seg in edit_plan["segments"]:
            assert seg["source"].startswith("generated:"), f"Source must be generated: {seg['source']}"

    def test_segment_in_out_full_clip(self, ref_store):
        """Segment in=0, out=duration (full clip per §3.3)."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        for seg in edit_plan["segments"]:
            assert seg["in"] == 0
            assert seg["out"] > 0

    def test_invalid_plan_raises_error(self, ref_store):
        """An invalid EpisodePlan raises EpisodePlanValidationError."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        bad_plan = {"format_module": "test@v1", "beats": []}
        with pytest.raises(EpisodePlanValidationError):
            compiler.compile_to_edit_plan(bad_plan)

    def test_captions_chunked_3_to_5_words(self, ref_store):
        """Caption overlays are chunked 3–5 words from vo_text."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        beat = _make_beat("b01", "hook", "I worked fifty years and retired with nothing",
                          duration_ms=5000,
                          graphics=[{"type": "number_card", "text": "50 YEARS", "style": "title_card_v1"}])
        plan = {"format_module": "test@v1", "beats": [beat]}
        edit_plan = compiler.compile_to_edit_plan(plan)

        # Find caption overlays (type="caption")
        captions = [o for o in edit_plan["segments"][0]["overlays"] if o["type"] == "caption"]
        assert len(captions) >= 2  # 8 words → 2 chunks (5+3 or 4+4)
        for cap in captions:
            word_count = len(cap["text"].split())
            assert 3 <= word_count <= 5, f"Caption '{cap['text']}' has {word_count} words — must be 3–5"

    def test_graphics_as_overlay_entries(self, ref_store):
        """Graphics from beats become overlay entries in the edit plan."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        beat = _make_beat("b01", "hook", "I worked fifty years",
                          duration_ms=3000,
                          graphics=[{"type": "number_card", "text": "50 YEARS", "style": "title_card_v1"}])
        plan = {"format_module": "test@v1", "beats": [beat]}
        edit_plan = compiler.compile_to_edit_plan(plan)

        # Find graphics overlays
        graphics_overlays = [o for o in edit_plan["segments"][0]["overlays"]
                             if o["type"] in ("number_card", "title_card", "quote_card")]
        assert len(graphics_overlays) == 1
        assert graphics_overlays[0]["text"] == "50 YEARS"
        assert graphics_overlays[0]["style_ref"] == "title_card_v1"

    def test_audio_block_has_vo_primary(self, ref_store):
        """Audio block has VO as primary audio with ducking."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan, vo_take_id="vo_take_1")
        assert edit_plan["audio"]["vo"]["take_id"] == "vo_take_1"
        assert edit_plan["audio"]["vo"]["ducking"] is True

    def test_audio_block_has_music_bed_for_dominant_register(self, ref_store):
        """Audio block includes registry music_bed for the dominant register, ducked."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        # All beats somber → dominant register is somber
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        # somber is the dominant register → bed_somber resolves from registry
        assert "music" in edit_plan["audio"]
        assert "bed_somber" in edit_plan["audio"]["music"]["stock_ref"]
        # Volume is low (ducked under VO)
        assert edit_plan["audio"]["music"]["volume"] <= 0.2

    def test_canvas_duration_matches_total_vo(self, ref_store):
        """Canvas duration_target matches total VO duration."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        total_ms = sum(b["duration_ms"] for b in plan["beats"])
        total_s = total_ms / 1000.0
        edit_plan = compiler.compile_to_edit_plan(plan)
        assert abs(edit_plan["canvas"]["duration_target"] - total_s) < 0.2


# ── 4. Loudnorm I=-14 enforcement ─────────────────────────────────────────────

class TestLoudnormEnforcement:
    """Enforced loudnorm I=-14 for episode format (not optional)."""

    def test_episode_loudnorm_I_is_minus_14(self):
        """The episode format loudnorm target is I=-14 (not the default -16)."""
        assert EPISODE_LOUDNORM_I == -14.0

    def test_loudnorm_filter_string(self):
        """The loudnorm filter string uses I=-14."""
        filt = episode_loudnorm_filter()
        assert "I=-14" in filt
        assert f"TP={EPISODE_LOUDNORM_TP}" in filt
        assert f"LRA={EPISODE_LOUDNORM_LRA}" in filt

    def test_edit_plan_has_episode_format_flag(self, ref_store):
        """Compiled edit plan has episode_format=True flag."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        assert edit_plan["episode_format"] is True

    def test_edit_plan_has_loudnorm_target(self, ref_store):
        """Compiled edit plan has loudnorm_target with I=-14."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        assert edit_plan["loudnorm_target"]["I"] == -14.0
        assert edit_plan["loudnorm_target"]["TP"] == EPISODE_LOUDNORM_TP
        assert edit_plan["loudnorm_target"]["LRA"] == EPISODE_LOUDNORM_LRA

    def test_is_episode_format_plan_true(self, ref_store):
        """is_episode_format_plan returns True for episode plans."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        edit_plan = compiler.compile_to_edit_plan(plan)
        assert is_episode_format_plan(edit_plan) is True

    def test_is_episode_format_plan_false_for_regular(self):
        """is_episode_format_plan returns False for non-episode plans."""
        regular_plan = {"segments": [], "audio": {}, "canvas": {}}
        assert is_episode_format_plan(regular_plan) is False

    def test_default_loudnorm_is_minus_16_for_non_episode(self):
        """Non-episode plans don't have loudnorm_target — default -16 applies."""
        regular_plan = {"segments": [], "audio": {}, "canvas": {}}
        assert not regular_plan.get("loudnorm_target")
        assert not is_episode_format_plan(regular_plan)


# ── 5. Compliance contract beats map 1:1 to authored beats ──────────────────

class TestComplianceBeatsMapping:
    """Compliance contract beats map 1:1 to authored beats."""

    def test_one_compliance_beat_per_episode_beat(self, ref_store):
        """Every episode beat produces exactly one compliance beat."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        compliance_beats = compiler.compile_compliance_beats(plan)
        assert len(compliance_beats) == len(plan["beats"])

    def test_compliance_beat_ids_match(self, ref_store):
        """Compliance beat_ids match the episode beat ids."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        compliance_beats = compiler.compile_compliance_beats(plan)
        for cb, beat in zip(compliance_beats, plan["beats"]):
            assert cb["beat_id"] == beat["id"]

    def test_compliance_source_excerpt_is_vo_text(self, ref_store):
        """Compliance source_excerpt is the beat's vo_text (approved text)."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        compliance_beats = compiler.compile_compliance_beats(plan)
        for cb, beat in zip(compliance_beats, plan["beats"]):
            assert cb["source_excerpt"] == beat["vo_text"]

    def test_hook_beat_gets_hook_requirement_type(self, ref_store):
        """Hook beats get requirement_type='hook'."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        compliance_beats = compiler.compile_compliance_beats(plan)
        assert compliance_beats[0]["requirement_type"] == "hook"

    def test_cta_beat_gets_cta_requirement_type(self, ref_store):
        """CTA beats get requirement_type='cta'."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        compliance_beats = compiler.compile_compliance_beats(plan)
        # Last beat is cta
        assert compliance_beats[-1]["requirement_type"] == "cta"

    def test_all_compliance_beats_required(self, ref_store):
        """All compliance beats are required=True."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        plan = _make_valid_plan()
        compliance_beats = compiler.compile_compliance_beats(plan)
        for cb in compliance_beats:
            assert cb["required"] is True


# ── 6. Approved text = ordered vo_text sequence (AMENDMENT-008 firewall) ───

class TestApprovedTextFirewall:
    """The approved text is the ordered vo_text sequence — AMENDMENT-008 firewall applies."""

    def test_extract_approved_text(self):
        """extract_approved_text returns the ordered vo_text sequence."""
        plan = _make_valid_plan()
        text = extract_approved_text(plan)
        # Should contain the first beat's vo_text
        assert plan["beats"][0]["vo_text"] in text
        # Should contain the last beat's vo_text
        assert plan["beats"][-1]["vo_text"] in text

    def test_approved_text_order_matters(self):
        """The order of vo_text is preserved in the approved text."""
        beats = [
            _make_beat("b01", "hook", "First sentence."),
            _make_beat("b02", "setup", "Second sentence."),
            _make_beat("b03", "cta", "Third sentence."),
        ]
        plan = {"format_module": "test@v1", "beats": beats}
        text = extract_approved_text(plan)
        assert text == "First sentence. Second sentence. Third sentence."

    def test_approved_text_hash_stable(self):
        """The approved text hash is stable for the same plan."""
        plan = _make_valid_plan()
        hash1 = extract_approved_text_hash(plan)
        hash2 = extract_approved_text_hash(plan)
        assert hash1 == hash2

    def test_approved_text_hash_changes_on_text_change(self):
        """The hash changes when any vo_text changes — the firewall detects this."""
        plan = _make_valid_plan()
        hash1 = extract_approved_text_hash(plan)

        # Modify one beat's vo_text
        modified_plan = json.loads(json.dumps(plan))
        modified_plan["beats"][0]["vo_text"] = "Different opening."

        hash2 = extract_approved_text_hash(modified_plan)
        assert hash1 != hash2, "Hash must change when vo_text changes"

    def test_approved_text_hash_changes_on_order_change(self):
        """The hash changes when beat order changes — order matters."""
        beats = [
            _make_beat("b01", "hook", "First."),
            _make_beat("b02", "setup", "Second."),
            _make_beat("b03", "cta", "Third."),
        ]
        plan = {"format_module": "test@v1", "beats": beats}
        hash1 = extract_approved_text_hash(plan)

        # Swap beats 1 and 2
        reordered = {"format_module": "test@v1", "beats": [beats[1], beats[0], beats[2]]}
        hash2 = extract_approved_text_hash(reordered)
        assert hash1 != hash2, "Hash must change when beat order changes"


# ── 7. Caption chunking ──────────────────────────────────────────────────────

class TestCaptionChunking:
    """Caption chunking produces 3–5 word phrases."""

    def test_short_text_one_chunk(self, ref_store):
        """Short text (≤5 words) produces one chunk."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        chunks = compiler._chunk_vo_text("I worked fifty years")
        assert len(chunks) == 1
        assert chunks[0] == "I worked fifty years"

    def test_long_text_multiple_chunks(self, ref_store):
        """Long text produces multiple chunks of 3–5 words."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        chunks = compiler._chunk_vo_text("I worked fifty years and retired with absolutely nothing to show")
        assert len(chunks) >= 2
        for chunk in chunks:
            wc = len(chunk.split())
            assert 3 <= wc <= 5, f"Chunk '{chunk}' has {wc} words — must be 3–5"

    def test_chunk_covers_all_words(self, ref_store):
        """Chunking covers all words in the vo_text."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        text = "I worked fifty years and retired with nothing"
        chunks = compiler._chunk_vo_text(text)
        reconstructed = " ".join(chunks)
        assert reconstructed == text

    def test_no_dangling_short_chunk(self, ref_store):
        """No dangling 1–2 word chunk at the end."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        # 7 words → should not produce a 5+2 split
        chunks = compiler._chunk_vo_text("one two three four five six seven")
        assert len(chunks) >= 2
        for chunk in chunks:
            wc = len(chunk.split())
            assert wc >= 3, f"Dangling chunk '{chunk}' has {wc} words — must be ≥3"

    def test_empty_text_produces_no_chunks(self, ref_store):
        """Empty vo_text produces no caption chunks."""
        compiler = EpisodePlanCompiler(ref_store=ref_store, business_slug="test_business")
        chunks = compiler._chunk_vo_text("")
        assert chunks == []


# ── 8. Episode beat roles ──────────────────────────────────────────────────

class TestEpisodeBeatRoles:
    """Episode beat roles are the correct set per §1.1 beat grammar."""

    def test_roles_include_all_grammar_roles(self):
        """The beat roles include hook, setup, struggle, turn, lesson, cta."""
        assert "hook" in EPISODE_BEAT_ROLES
        assert "setup" in EPISODE_BEAT_ROLES
        assert "struggle" in EPISODE_BEAT_ROLES
        assert "turn" in EPISODE_BEAT_ROLES
        assert "lesson" in EPISODE_BEAT_ROLES
        assert "cta" in EPISODE_BEAT_ROLES

    def test_roles_do_not_include_non_episode_roles(self):
        """Episode roles don't include generic production contract roles."""
        assert "orientation" not in EPISODE_BEAT_ROLES
        assert "proof" not in EPISODE_BEAT_ROLES
        assert "payoff" not in EPISODE_BEAT_ROLES
        assert "close" not in EPISODE_BEAT_ROLES


# ── 9. Graphics types ────────────────────────────────────────────────────────

class TestGraphicsTypes:
    """Graphics types are renderer-drawn only (no text in generated images)."""

    def test_graphics_types_are_renderer_drawn(self):
        """Graphics types are number_card, title_card, quote_card only."""
        assert "number_card" in GRAPHICS_TYPES
        assert "title_card" in GRAPHICS_TYPES
        assert "quote_card" in GRAPHICS_TYPES

    def test_no_generated_text_types(self):
        """No graphics type implies text in generated images."""
        # None of these should imply baked-in text
        for gtype in GRAPHICS_TYPES:
            assert "text" not in gtype
            assert "baked" not in gtype


# ── 10. Banned tokens ───────────────────────────────────────────────────────

class TestBannedTokens:
    """Banned tokens prevent text in generated images."""

    def test_all_banned_tokens_present(self):
        """All §3.2 banned tokens are in the set."""
        expected = {"text", "words", "sign", "screen", "phone", "logo",
                    "document", "chart", "letters", "numbers on"}
        assert expected.issubset(BANNED_PROMPT_TOKENS)

    def test_banned_token_scan_catches_phone(self):
        """The banned token scan catches 'phone' in a shot spec."""
        assembler = ShotSpecAssembler()
        spec = ShotSpec(beat_id="b01", image_prompt="a phone on a desk", reference_images=[])
        violations = assembler.scan_banned_tokens(spec)
        assert "phone" in violations

    def test_banned_token_scan_catches_screen(self):
        """The banned token scan catches 'screen' in a shot spec."""
        assembler = ShotSpecAssembler()
        spec = ShotSpec(beat_id="b01", image_prompt="a screen showing data", reference_images=[])
        violations = assembler.scan_banned_tokens(spec)
        assert "screen" in violations

    def test_clean_prompt_no_violations(self):
        """A clean prompt has no banned token violations."""
        assembler = ShotSpecAssembler()
        spec = ShotSpec(beat_id="b01", image_prompt="a man at a kitchen table", reference_images=[])
        violations = assembler.scan_banned_tokens(spec)
        assert violations == []


# ── 11. ShotSpec dataclass ──────────────────────────────────────────────────

class TestShotSpecDataclass:
    """ShotSpec dataclass works correctly."""

    def test_to_dict(self):
        """ShotSpec.to_dict produces the correct dict."""
        spec = ShotSpec(
            beat_id="b01",
            image_prompt="test prompt",
            reference_images=["a.png", "b.png"],
            motion_prompt="slow push-in",
            duration_ms=3000,
            graphics=[{"type": "number_card", "text": "50", "style": "s"}],
            location_ref="kitchen",
            character_ref="elder",
        )
        d = spec.to_dict()
        assert d["beat_id"] == "b01"
        assert d["image_prompt"] == "test prompt"
        assert d["reference_images"] == ["a.png", "b.png"]
        assert d["motion_prompt"] == "slow push-in"
        assert d["duration_ms"] == 3000
        assert len(d["graphics"]) == 1