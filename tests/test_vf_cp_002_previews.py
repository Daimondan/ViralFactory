"""Tests for VF-CP-002: Per-element preview generator.

All previews are generated locally — no provider API calls.
Tests use the dict-based CompositionPlan format produced by
``services.composition_plan.CompositionPlanGenerator``.
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image

from services.composition_preview import (
    CompositionPreviewGenerator,
    PreviewError,
    _element_hash,
    _plan_hash,
)

# ---------------------------------------------------------------------------
# Font config — use matplotlib-bundled DejaVu fonts (always present, valid TTFs)
# ---------------------------------------------------------------------------

import matplotlib
_MPL_FONT_DIR = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
_VALID_BODY = os.path.join(_MPL_FONT_DIR, "DejaVuSans-Bold.ttf")
_VALID_DISPLAY = os.path.join(_MPL_FONT_DIR, "DejaVuSans.ttf")

MODELS_CONFIG = {
    "rendering": {
        "font_path": _VALID_BODY,
        "font_display": _VALID_DISPLAY,
    }
}


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_test_image(path: str, w: int = 400, h: int = 600, color=(100, 150, 200)):
    img = Image.new("RGBA", (w, h), color + (255,))
    img.save(path)


def _make_test_wav(path: str, duration_s: float = 1.0, freq: float = 440.0):
    import wave
    import struct
    import math
    sr = 8000
    n = int(sr * duration_s)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", int(32767 * 0.5 * math.sin(2 * math.pi * freq * i / sr)))
            for i in range(n)
        )
        wf.writeframes(frames)


def _make_text_element(
    element_id="text_001",
    role="hook",
    text="Hello World",
    style_ref="hook",
    x=0.5,
    y=0.3,
    size=64,
    color="white",
    in_sec=0.0,
    out_sec=2.0,
):
    return {
        "element_id": element_id,
        "role": role,
        "text": text,
        "text_intent_id": "ti_001",
        "beat_id": "beat_001",
        "font": {
            "file_hash": "abc123",
            "family": "DejaVu",
            "weight": "Bold",
            "size": size,
            "color": color,
            "border_width": 3,
            "border_color": "black",
            "shadow": None,
        },
        "style_ref": style_ref,
        "position": {"x": x, "y": y, "anchor": "center"},
        "timing": {"in_sec": in_sec, "out_sec": out_sec},
        "word_timing": [],
        "emphasis_marks": [],
    }


def _make_visual_element(
    element_id="vis_001",
    source_hash="hash_001",
    kind="still",
    trim_start=0.0,
    trim_end=2.0,
    scale=1.0,
    crop=None,
):
    return {
        "element_id": element_id,
        "source_hash": source_hash,
        "manifest_candidate_id": "cand_001",
        "kind": kind,
        "trim_start_sec": trim_start,
        "trim_end_sec": trim_end,
        "crop": crop,
        "focal": None,
        "canvas_position": {"x": 0.0, "y": 0.0},
        "scale": scale,
        "motion_keyframes": [],
        "beat_id": "beat_001",
        "event_id": None,
    }


def _make_graphics_element(
    element_id="gfx_text_001",
    gfx_type="overlay",
    x=0.5,
    y=0.7,
    scale=1.0,
    in_sec=0.0,
    out_sec=2.0,
):
    return {
        "element_id": element_id,
        "type": gfx_type,
        "config_hash": "cfg_hash_001",
        "position": {"x": x, "y": y, "anchor": "center"},
        "scale": scale,
        "timing": {"in_sec": in_sec, "out_sec": out_sec},
        "animation": {"type": "fade", "duration_sec": 0.3, "easing": "ease_in_out"},
        "beat_id": "beat_001",
    }


def _make_transition(
    transition_id="trans_001",
    trans_type="crossfade",
    duration=0.5,
    beat_boundary="beat_002",
):
    return {
        "transition_id": transition_id,
        "type": trans_type,
        "duration_sec": duration,
        "easing": "ease_in_out",
        "beat_boundary": beat_boundary,
    }


def _make_audio(
    vo_source_hash="vo_hash",
    music_source_hash="music_hash",
    total_dur=10.0,
    lufs_target=-14.0,
):
    return {
        "vo_track": {
            "source_hash": vo_source_hash,
            "manifest_candidate_id": "cand_vo",
            "trim_start_sec": 0.0,
            "trim_end_sec": total_dur,
            "gain_curve": [{"time_sec": 0.0, "gain_db": 0.0}],
            "ducking": {"depth": 0.20, "attack_s": 0.3, "release_s": 0.5},
        },
        "music_track": {
            "source_hash": music_source_hash,
            "manifest_candidate_id": "cand_music",
            "start_sec": 0.0,
            "stop_sec": total_dur,
            "gain_db": -3.0,
            "ducking": {"depth": 0.20, "attack_s": 0.3, "release_s": 0.5},
            "fade_in_sec": 0.5,
            "fade_out_sec": 1.0,
        },
        "sfx_events": [
            {
                "sfx_id": "sfx_001",
                "trigger_sec": 2.0,
                "gain_db": -6.0,
                "duration_sec": 0.15,
                "preset": "pop",
                "beat_id": "beat_001",
            },
        ],
        "mix_spec": {"lufs_target": lufs_target, "true_peak_db": -1.0},
    }


def _make_plan(
    text_elements=None,
    visual_elements=None,
    graphics_elements=None,
    transitions=None,
    audio=None,
    total_duration=10.0,
    plan_hash=None,
):
    plan = {
        "schema_version": "1.0",
        "manifest_hash": "man_001",
        "writer_contract_hash": "wc_001",
        "text_hash": "txt_001",
        "canvas": {
            "resolution": {"width": 540, "height": 960},
            "aspect_ratio": "9:16",
            "fps": 30,
            "background": {"color": "#000000"},
            "safe_zones": {"title_safe": 0.9, "action_safe": 0.95},
            "platform_framing": "9:16_vertical",
        },
        "text_elements": text_elements or [],
        "audio": audio or {},
        "visual_elements": visual_elements or [],
        "graphics_elements": graphics_elements or [],
        "transitions": transitions or [],
        "total_duration_sec": total_duration,
    }
    plan["plan_hash"] = plan_hash or _plan_hash(plan)
    return plan


# ---------------------------------------------------------------------------
# Test base
# ---------------------------------------------------------------------------

class PreviewTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vf_cp002_")
        self.cache_dir = os.path.join(self.tmp, "previews")
        self.config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        # Test fixtures
        self.bg_image = os.path.join(self.tmp, "bg.png")
        _make_test_image(self.bg_image, 800, 1200, (80, 100, 140))
        self.clip_image = os.path.join(self.tmp, "clip.png")
        _make_test_image(self.clip_image, 720, 1280, (120, 80, 160))
        self.audio_wav = os.path.join(self.tmp, "tone.wav")
        _make_test_wav(self.audio_wav, 1.5, 440)
        # Source resolver maps hash → local file
        self.source_map = {
            "hash_001": self.clip_image,
            "vo_hash": self.audio_wav,
            "music_hash": self.audio_wav,
        }
        self.gen = CompositionPreviewGenerator(
            cache_dir=self.cache_dir,
            models_config=MODELS_CONFIG,
            config_dir=self.config_dir,
            source_resolver=lambda h: self.source_map.get(h, ""),
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Text role preview
# ---------------------------------------------------------------------------

class TestTextPreview(PreviewTestBase):
    def test_text_preview_visible_font_specimen(self):
        """Text role produces a visible font specimen (PIL image, >0 bytes)."""
        te = _make_text_element(role="hook", style_ref="hook", text="Hello World")
        plan = _make_plan(text_elements=[te])
        path = self.gen.preview_text(plan, te)
        self.assertTrue(os.path.exists(path), "Preview file should exist")
        self.assertGreater(os.path.getsize(path), 0, "Preview file should be non-empty")
        img = Image.open(path)
        self.assertEqual(img.format, "PNG")
        self.assertEqual(img.size, (540, 960))

    def test_text_preview_display_font_for_hook(self):
        """Hook style ref resolves to display font and still renders."""
        te = _make_text_element(role="hook", style_ref="hook", text="BIG HOOK", size=72)
        plan = _make_plan(text_elements=[te])
        path = self.gen.preview_text(plan, te)
        self.assertGreater(os.path.getsize(path), 100)

    def test_text_preview_caption_role(self):
        """Caption role uses body font and renders."""
        te = _make_text_element(role="caption", style_ref="caption",
                                text="This is a caption", y=0.85, size=42)
        plan = _make_plan(text_elements=[te])
        path = self.gen.preview_text(plan, te)
        self.assertGreater(os.path.getsize(path), 0)


# ---------------------------------------------------------------------------
# Audio preview
# ---------------------------------------------------------------------------

class TestAudioPreview(PreviewTestBase):
    def test_audio_waveform_exists(self):
        """Audio lane shows a waveform (matplotlib output exists, >0 bytes)."""
        audio = _make_audio(total_dur=5.0)
        plan = _make_plan(audio=audio, total_duration=5.0)
        path = self.gen.preview_audio(plan)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)
        img = Image.open(path)
        self.assertEqual(img.format, "PNG")

    def test_audio_preview_synthetic_when_no_source(self):
        """Audio preview renders with synthetic waveform when source can't be resolved."""
        audio = _make_audio(total_dur=5.0)
        plan = _make_plan(audio=audio, total_duration=5.0)
        # Use a generator with no source resolver
        gen = CompositionPreviewGenerator(
            cache_dir=self.cache_dir,
            models_config=MODELS_CONFIG,
            config_dir=self.config_dir,
            source_resolver=None,
        )
        path = gen.preview_audio(plan)
        self.assertGreater(os.path.getsize(path), 0)

    def test_audio_preview_no_tracks_fails_closed(self):
        """Empty audio dict fails closed."""
        plan = _make_plan(audio={}, total_duration=5.0)
        with self.assertRaises(PreviewError):
            self.gen.preview_audio(plan)


# ---------------------------------------------------------------------------
# Visual clip preview
# ---------------------------------------------------------------------------

class TestVisualPreview(PreviewTestBase):
    def test_visual_clip_shows_framing(self):
        """Visual clip shows framing with safe-zone overlay."""
        ve = _make_visual_element(source_hash="hash_001", kind="still",
                                  crop={"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8})
        plan = _make_plan(visual_elements=[ve], total_duration=5.0)
        path = self.gen.preview_visual(plan, ve)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)
        img = Image.open(path)
        self.assertEqual(img.size, (540, 960))

    def test_missing_clip_fails_closed(self):
        """Missing clip image raises PreviewError."""
        ve = _make_visual_element(source_hash="nonexistent_hash")
        plan = _make_plan(visual_elements=[ve], total_duration=5.0)
        with self.assertRaises(PreviewError) as ctx:
            self.gen.preview_visual(plan, ve)
        self.assertIn("resolve", str(ctx.exception).lower())

    def test_no_source_resolver_fails_closed(self):
        """No source resolver at all fails closed for visual elements."""
        ve = _make_visual_element(source_hash="hash_001")
        plan = _make_plan(visual_elements=[ve], total_duration=5.0)
        gen = CompositionPreviewGenerator(
            cache_dir=self.cache_dir,
            models_config=MODELS_CONFIG,
            config_dir=self.config_dir,
            source_resolver=None,
        )
        with self.assertRaises(PreviewError):
            gen.preview_visual(plan, ve)


# ---------------------------------------------------------------------------
# Graphics overlay preview
# ---------------------------------------------------------------------------

class TestGraphicsPreview(PreviewTestBase):
    def test_graphics_overlay_renders(self):
        """Graphics overlay renders on representative background."""
        ge = _make_graphics_element()
        plan = _make_plan(graphics_elements=[ge], total_duration=5.0)
        path = self.gen.preview_graphics(plan, ge, background_path=self.bg_image)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_missing_background_fails_closed(self):
        """Missing background file raises PreviewError."""
        ge = _make_graphics_element()
        plan = _make_plan(graphics_elements=[ge], total_duration=5.0)
        with self.assertRaises(PreviewError):
            self.gen.preview_graphics(plan, ge, background_path="/nonexistent_bg.png")


# ---------------------------------------------------------------------------
# Transition preview
# ---------------------------------------------------------------------------

class TestTransitionPreview(PreviewTestBase):
    def test_transition_timing_diagram(self):
        """Transition produces an annotated timing diagram."""
        tr = _make_transition(trans_type="crossfade", duration=0.5)
        plan = _make_plan(transitions=[tr], total_duration=5.0)
        path = self.gen.preview_transition(plan, tr)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_transition_cut(self):
        """Cut transition (duration=0) renders without error."""
        tr = _make_transition(trans_type="cut", duration=0.0)
        plan = _make_plan(transitions=[tr], total_duration=5.0)
        path = self.gen.preview_transition(plan, tr)
        self.assertGreater(os.path.getsize(path), 0)


# ---------------------------------------------------------------------------
# Full timeline preview
# ---------------------------------------------------------------------------

class TestTimelinePreview(PreviewTestBase):
    def test_full_timeline(self):
        """Full timeline diagram shows all elements."""
        te = _make_text_element(role="hook", text="Hook", in_sec=0, out_sec=2)
        ve = _make_visual_element(source_hash="hash_001", kind="still",
                                  trim_start=0, trim_end=3)
        ge = _make_graphics_element(in_sec=1, out_sec=2)
        tr = _make_transition(trans_type="crossfade", duration=0.5)
        audio = _make_audio(total_dur=5.0)
        plan = _make_plan(
            text_elements=[te],
            visual_elements=[ve],
            graphics_elements=[ge],
            transitions=[tr],
            audio=audio,
            total_duration=5.0,
        )
        path = self.gen.preview_timeline(plan)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

class TestCaching(PreviewTestBase):
    def test_preview_cached_by_element_hash(self):
        """Second call returns cached file (same path, no re-render)."""
        te = _make_text_element()
        plan = _make_plan(text_elements=[te])
        path1 = self.gen.preview_text(plan, te)
        self.assertGreater(os.path.getsize(path1), 0)
        # Append a marker to prove no re-render on cache hit
        with open(path1, "ab") as f:
            f.write(b"CACHE_MARKER")
        marker_size = os.path.getsize(path1)
        path2 = self.gen.preview_text(plan, te)
        self.assertEqual(path1, path2, "Cached path should be identical")
        self.assertEqual(os.path.getsize(path2), marker_size,
                         "File should not have been re-rendered (cache hit)")

    def test_plan_change_invalidates_cache(self):
        """Different plan hash → different cache directory → new preview."""
        te = _make_text_element(text="Original")
        plan_a = _make_plan(text_elements=[te], plan_hash="hash_a_001")
        te_b = _make_text_element(text="Different text")
        plan_b = _make_plan(text_elements=[te_b], plan_hash="hash_b_002")
        path_a = self.gen.preview_text(plan_a, te)
        path_b = self.gen.preview_text(plan_b, te_b)
        self.assertNotEqual(path_a, path_b,
                            "Different plan hashes should produce different cache paths")
        self.assertGreater(os.path.getsize(path_a), 0)
        self.assertGreater(os.path.getsize(path_b), 0)

    def test_different_plan_hash_different_dir(self):
        """Verify the cache directory name includes the plan hash."""
        te = _make_text_element()
        plan = _make_plan(text_elements=[te], plan_hash="my_custom_hash_123")
        self.gen.preview_text(plan, te)
        cache_subdir = os.path.join(self.cache_dir, "my_custom_hash_123")
        self.assertTrue(os.path.isdir(cache_subdir),
                        "Cache subdir should be named after plan hash")


# ---------------------------------------------------------------------------
# Local-only constraint
# ---------------------------------------------------------------------------

class TestLocalOnly(PreviewTestBase):
    def test_no_network_calls(self):
        """Preview generation uses only local files (no HTTP / sockets).

        We patch socket.socket to fail on any outbound connection attempt
        and confirm previews still generate successfully.
        """
        import socket
        original_socket = socket.socket

        class GuardedSocket(original_socket):
            def __init__(self, *args, **kwargs):
                family = args[0] if args else socket.AF_INET
                if family in (socket.AF_INET, socket.AF_INET6):
                    raise PermissionError("Network access blocked in test")
                super().__init__(*args, **kwargs)

        socket.socket = GuardedSocket
        try:
            # Text preview
            te = _make_text_element()
            plan = _make_plan(text_elements=[te], total_duration=5.0)
            path = self.gen.preview_text(plan, te)
            self.assertGreater(os.path.getsize(path), 0)

            # Audio with local wav
            audio = _make_audio(total_dur=5.0)
            plan_a = _make_plan(audio=audio, total_duration=5.0)
            path_a = self.gen.preview_audio(plan_a)
            self.assertGreater(os.path.getsize(path_a), 0)

            # Visual clip with local image
            ve = _make_visual_element(source_hash="hash_001", kind="still")
            plan_v = _make_plan(visual_elements=[ve], total_duration=5.0)
            path_v = self.gen.preview_visual(plan_v, ve)
            self.assertGreater(os.path.getsize(path_v), 0)
        finally:
            socket.socket = original_socket


# ---------------------------------------------------------------------------
# generate_all batch
# ---------------------------------------------------------------------------

class TestGenerateAll(PreviewTestBase):
    def test_generate_all_categories(self):
        """generate_all produces previews for every element type."""
        te = _make_text_element(role="hook", text="Hook", in_sec=0, out_sec=2)
        ve = _make_visual_element(source_hash="hash_001", kind="still",
                                  trim_start=0, trim_end=3)
        ge = _make_graphics_element(in_sec=1, out_sec=2)
        tr = _make_transition(trans_type="crossfade", duration=0.5)
        audio = _make_audio(total_dur=5.0)
        plan = _make_plan(
            text_elements=[te],
            visual_elements=[ve],
            graphics_elements=[ge],
            transitions=[tr],
            audio=audio,
            total_duration=5.0,
        )
        results = self.gen.generate_all(plan, graphics_background=self.bg_image)
        for cat in ("text", "audio", "visual", "graphics", "transition", "timeline"):
            self.assertIn(cat, results)
            self.assertGreater(len(results[cat]), 0, f"{cat} should have previews")
            for p in results[cat]:
                self.assertGreater(os.path.getsize(p), 0)

    def test_generate_all_collects_errors(self):
        """generate_all returns partial results with _errors list on failures."""
        te = _make_text_element(text="Hi")
        ve = _make_visual_element(source_hash="nonexistent_hash")
        plan = _make_plan(
            text_elements=[te],
            visual_elements=[ve],
            total_duration=2.0,
        )
        results = self.gen.generate_all(plan)
        # Text preview should still succeed
        self.assertGreater(len(results["text"]), 0)
        # Visual preview should fail — error collected in _errors
        self.assertIn("_errors", results)
        errors_msg = " ".join(results["_errors"])
        self.assertIn("visual", errors_msg)

    def test_generate_all_missing_font_in_config(self):
        """If config fonts are invalid but system fallback exists, text still renders."""
        te = _make_text_element()
        plan = _make_plan(text_elements=[te], total_duration=2.0)
        gen = CompositionPreviewGenerator(
            cache_dir=self.cache_dir,
            models_config={"rendering": {"font_path": "/nonexistent.ttf",
                                         "font_display": "/nonexistent2.ttf"}},
            config_dir=self.config_dir,
        )
        path = gen.preview_text(plan, te)
        self.assertGreater(os.path.getsize(path), 0,
                           "System fallback font should be used when config font is invalid")


if __name__ == "__main__":
    unittest.main()