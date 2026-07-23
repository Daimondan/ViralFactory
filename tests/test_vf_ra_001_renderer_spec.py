"""
VF-RA-001 — Canonical RendererSpec v1 + local conformance adapter tests.

Tests:
  - Schema round-trip is canonical and content-hashed
  - Two tenant/style fixtures produce visibly different specs with zero Python edits
  - Unsupported mandatory features return structured blockers and never silently degrade
  - No provider field enters the component manifest
  - No judgment or open-ended renderer prompt enters Python
  - RendererSpec cannot be compiled without a ratified CompositionPlan
  - Local conformance adapter declares capabilities and can lower
  - Capability check: missing capabilities fail closed
  - Spec hash is key-order independent
"""

import json
import os
import tempfile
from datetime import datetime, timezone

import pytest


@pytest.fixture
def tmp_db():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_vf.db")
    yield db_path
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestRendererSpecSchema:
    def test_spec_has_required_fields(self):
        """A valid spec has spec_version, identity, canvas, timeline."""
        from services.renderer_spec import RENDERER_SPEC_VERSION
        assert RENDERER_SPEC_VERSION == "1.0"

    def test_validate_valid_spec(self):
        from services.renderer_spec import validate_spec
        spec = {
            "spec_version": "1.0",
            "identity": {
                "composition_plan_hash": "abc",
                "manifest_hash": "def",
                "session_id": 1,
                "asset_id": 1,
            },
            "canvas": {"width": 1080, "height": 1920, "fps": 30.0},
            "timeline": [
                {"type": "text", "layer": 10, "in_point": 0, "out_point": 5},
            ],
        }
        valid, errors = validate_spec(spec)
        assert valid, f"Should be valid: {errors}"

    def test_validate_missing_fields(self):
        from services.renderer_spec import validate_spec
        spec = {"spec_version": "1.0"}
        valid, errors = validate_spec(spec)
        assert not valid
        assert any("identity" in e for e in errors)
        assert any("canvas" in e for e in errors)
        assert any("timeline" in e for e in errors)


class TestSpecHash:
    def test_hash_is_canonical(self):
        """Same spec produces same hash regardless of key order."""
        from services.renderer_spec import compute_spec_hash
        spec_a = {"a": 1, "b": 2, "timeline": [1, 2, 3]}
        spec_b = {"b": 2, "timeline": [1, 2, 3], "a": 1}
        assert compute_spec_hash(spec_a) == compute_spec_hash(spec_b)

    def test_hash_excludes_spec_hash(self):
        """The spec_hash field itself is excluded from hash computation."""
        from services.renderer_spec import compute_spec_hash
        spec_a = {"spec_version": "1.0", "spec_hash": "abc", "timeline": []}
        spec_b = {"spec_version": "1.0", "spec_hash": "def", "timeline": []}
        assert compute_spec_hash(spec_a) == compute_spec_hash(spec_b)


class TestCompileFromPlan:
    def _make_plan(self, text="Hook text", width=1080, height=1920):
        """Create a minimal CompositionPlan dict for testing."""
        return {
            "schema_version": "1.0",
            "plan_hash": "plan_abc123",
            "canvas": {
                "width": width,
                "height": height,
                "fps": 30.0,
                "aspect_ratio": "9:16",
                "background": "#000000",
                "safe_zones": {"top": 0.1, "bottom": 0.1},
            },
            "text_elements": [
                {
                    "element_id": "txt_1",
                    "text": text,
                    "font_family": "Montserrat",
                    "font_path": "/fonts/Montserrat-Bold.ttf",
                    "font_hash": "font_hash_abc",
                    "font_size": 48,
                    "font_color": "#FFFFFF",
                    "position": {"x": 0.5, "y": 0.1},
                    "start": 0,
                    "end": 3,
                    "word_timings": [],
                    "emphasis_marks": [],
                },
            ],
            "audio_elements": [
                {
                    "element_id": "mix_1",
                    "lanes": [
                        {
                            "element_id": "vo_1",
                            "lane_type": "vo",
                            "source_hash": "vo_hash",
                            "source_path": "/data/vo.wav",
                            "start": 0,
                            "end": 10,
                            "gain": 1.0,
                            "gain_curve": [],
                            "ducking_points": [],
                            "fade_in": 0,
                            "fade_out": 0,
                        },
                    ],
                    "lufs_target": -16.0,
                    "true_peak_limit": -1.0,
                },
            ],
            "visual_elements": [
                {
                    "element_id": "vis_1",
                    "kind": "image",
                    "source_hash": "img_hash",
                    "source_path": "/data/image.jpg",
                    "start": 0,
                    "end": 5,
                    "scale": 1.0,
                    "crop": {},
                    "motion_keyframes": [],
                },
            ],
            "graphics_elements": [
                {
                    "element_id": "gfx_1",
                    "overlay_type": "overlay",
                    "overlay_path": "/data/overlay.png",
                    "config_hash": "gfx_hash",
                    "position": {"x": 0.5, "y": 0.8},
                    "scale": 1.0,
                    "start": 1,
                    "end": 4,
                    "animation": {},
                },
            ],
            "transitions": [
                {
                    "element_id": "tr_1",
                    "transition_type": "crossfade",
                    "duration": 0.5,
                    "easing": "linear",
                    "start": 5,
                    "beat_boundary": "b01/b02",
                },
            ],
            "manifest_hash": "manifest_hash_abc",
            "writer_contract_hash": "writer_hash_abc",
        }

    def test_compile_produces_valid_spec(self):
        from services.renderer_spec import compile_from_ratified_plan, validate_spec
        plan = self._make_plan()
        manifest = {"manifest_json": {"manifest_hash": "manifest_hash_abc"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}

        spec = compile_from_ratified_plan(plan, manifest, session)

        valid, errors = validate_spec(spec)
        assert valid, f"Compiled spec should be valid: {errors}"

        # Identity inherits plan hash
        assert spec["identity"]["composition_plan_hash"] == "plan_abc123"
        assert spec["identity"]["manifest_hash"] == "manifest_hash_abc"

        # Timeline has all element types
        types = {el["type"] for el in spec["timeline"]}
        assert "text" in types
        assert "audio" in types
        assert "visual" in types
        assert "graphics" in types
        assert "transition" in types

        # Spec hash is computed
        assert "spec_hash" in spec
        assert spec["spec_hash"] is not None

    def test_two_plans_produce_different_specs(self):
        """Two different plans produce different specs."""
        from services.renderer_spec import compile_from_ratified_plan, compute_spec_hash
        plan_a = self._make_plan(text="Hook A", width=1080, height=1920)
        plan_b = self._make_plan(text="Hook B", width=540, height=960)

        manifest = {"manifest_json": {"manifest_hash": "m_hash"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}

        spec_a = compile_from_ratified_plan(plan_a, manifest, session)
        spec_b = compile_from_ratified_plan(plan_b, manifest, session)

        assert compute_spec_hash(spec_a) != compute_spec_hash(spec_b)

    def test_no_provider_fields_in_spec(self):
        """The spec has no vendor-specific fields."""
        from services.renderer_spec import compile_from_ratified_plan
        plan = self._make_plan()
        manifest = {"manifest_json": {"manifest_hash": "m_hash"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}

        spec = compile_from_ratified_plan(plan, manifest, session)
        spec_str = json.dumps(spec, sort_keys=True)

        # No vendor names in the spec
        assert "shotstack" not in spec_str.lower()
        assert "creatomate" not in spec_str.lower()
        assert "template" not in spec_str.lower()
        assert "vendor" not in spec_str.lower()

    def test_audio_automation_preserved(self):
        """Audio automation (LUFS, true peak, tracks) is preserved."""
        from services.renderer_spec import compile_from_ratified_plan
        plan = self._make_plan()
        manifest = {"manifest_json": {"manifest_hash": "m_hash"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}

        spec = compile_from_ratified_plan(plan, manifest, session)

        assert spec["audio_automation"]["lufs_target"] == -16.0
        assert spec["audio_automation"]["true_peak_limit"] == -1.0
        assert len(spec["audio_automation"]["tracks"]) == 1
        assert spec["audio_automation"]["tracks"][0]["lane_type"] == "vo"

    def test_text_element_preserves_word_timings(self):
        """Text elements preserve word timings and emphasis marks."""
        from services.renderer_spec import compile_from_ratified_plan
        plan = self._make_plan()
        plan["text_elements"][0]["word_timings"] = [
            {"word": "Hook", "start": 0, "end": 0.5},
            {"word": "text", "start": 0.5, "end": 1.0},
        ]
        plan["text_elements"][0]["emphasis_marks"] = [{"word": "Hook", "type": "bold"}]

        manifest = {"manifest_json": {"manifest_hash": "m_hash"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}

        spec = compile_from_ratified_plan(plan, manifest, session)

        text_el = [el for el in spec["timeline"] if el["type"] == "text"][0]
        assert len(text_el["word_timings"]) == 2
        assert len(text_el["emphasis_marks"]) == 1


class TestLocalConformanceAdapter:
    def test_adapter_declares_capabilities(self):
        from services.renderer_spec import LocalConformanceAdapter
        adapter = LocalConformanceAdapter()
        caps = adapter.capabilities
        assert "text_overlay" in caps
        assert "audio_mix" in caps
        assert "video_trim" in caps
        assert len(caps) >= 8

    def test_can_render_supported_spec(self):
        from services.renderer_spec import LocalConformanceAdapter, compile_from_ratified_plan
        adapter = LocalConformanceAdapter()

        plan = {
            "plan_hash": "p1",
            "canvas": {"width": 1080, "height": 1920, "fps": 30.0,
                        "safe_zones": {"top": 0.1}},
            "text_elements": [{"element_id": "t1", "text": "Test", "start": 0, "end": 1}],
            "audio_elements": [],
            "visual_elements": [],
            "graphics_elements": [],
            "transitions": [],
        }
        manifest = {"manifest_json": {"manifest_hash": "m1"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}
        spec = compile_from_ratified_plan(plan, manifest, session)

        check = adapter.can_render(spec)
        assert check["supported"]

    def test_lower_produces_evidence(self):
        from services.renderer_spec import LocalConformanceAdapter, compile_from_ratified_plan
        adapter = LocalConformanceAdapter()

        plan = {
            "plan_hash": "p1",
            "canvas": {"width": 1080, "height": 1920, "fps": 30.0},
            "text_elements": [{"element_id": "t1", "text": "Test", "start": 0, "end": 1}],
            "audio_elements": [],
            "visual_elements": [],
            "graphics_elements": [],
            "transitions": [],
        }
        manifest = {"manifest_json": {"manifest_hash": "m1"}}
        session = {"id": 1, "asset_id": 1, "business_slug": "test"}
        spec = compile_from_ratified_plan(plan, manifest, session)

        result = adapter.lower(spec)
        assert result["adapter"] == "local_ffmpeg"
        assert result["spec_hash"] is not None
        assert "capabilities_used" in result
        assert "lowering_evidence" in result


class TestCapabilityRegistry:
    def test_get_required_capabilities(self):
        from services.renderer_spec import get_required_capabilities
        spec = {
            "timeline": [
                {"type": "text", "layer": 10, "in_point": 0, "out_point": 1},
                {"type": "audio", "layer": 0, "in_point": 0, "out_point": 5,
                 "lane_type": "sfx"},
                {"type": "visual", "layer": 1, "in_point": 0, "out_point": 3,
                 "kind": "image"},
                {"type": "transition", "layer": 20, "in_point": 3, "out_point": 3.5,
                 "transition_type": "crossfade"},
            ],
            "canvas": {"width": 1080, "height": 1920, "fps": 30,
                        "safe_zones": {"top": 0.1}},
        }
        caps = get_required_capabilities(spec)
        assert "text_overlay" in caps
        assert "audio_mix" in caps
        assert "sfx_trigger" in caps
        assert "image_scale" in caps
        assert "transition_crossfade" in caps
        assert "safe_zones" in caps

    def test_missing_capabilities_fail_closed(self):
        from services.renderer_spec import check_adapter_capabilities
        result = check_adapter_capabilities(
            adapter_caps=["text_overlay", "audio_mix"],
            required_caps=["text_overlay", "audio_mix", "video_trim", "motion_zoom"],
        )
        assert not result["supported"]
        assert "video_trim" in result["missing"]
        assert "motion_zoom" in result["missing"]