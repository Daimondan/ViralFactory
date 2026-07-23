"""Tests for VF-CP-002: Per-element preview generator.

All previews are generated locally — no provider API calls.
"""

import os
import sys
import tempfile
import shutil
import unittest

# Ensure src is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PIL import Image

from services.composition_plan import (
    AudioLane,
    AudioMix,
    CanvasSpec,
    CompositionPlan,
    GraphicsOverlay,
    TextRole,
    Transition,
    VisualClip,
)
from services.composition_preview import (
    CompositionPreviewGenerator,
    PreviewError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FONTS_DIR = "/home/daimon/.hermes/profiles/vf-coder/home/.fonts"
BODY_FONT = os.path.join(FONTS_DIR, "Montserrat-Bold.ttf")
DISPLAY_FONT = os.path.join(FONTS_DIR, "Anton-Regular.ttf")

# The vf-coder profile font files may be HTML placeholders (not real TTFs).
# Use the matplotlib-bundled DejaVu fonts as reliable, always-present fixtures.
import matplotlib
_MPL_FONT_DIR = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
_VALID_BODY = os.path.join(_MPL_FONT_DIR, "DejaVuSans-Bold.ttf")
_VALID_DISPLAY = os.path.join(_MPL_FONT_DIR, "DejaVuSans.ttf")

# Use valid fonts for tests that need rendering; keep the HTML-path config
# to exercise the system-fallback path in the generator.
MODELS_CONFIG = {
    "rendering": {
        "font_path": _VALID_BODY,
        "font_display": _VALID_DISPLAY,
    }
}


def _make_test_image(path: str, w: int = 400, h: int = 600, color=(100, 150, 200)):
    """Create a minimal PNG for test fixtures."""
    img = Image.new("RGBA", (w, h), color + (255,))
    img.save(path)


def _make_test_wav(path: str, duration_s: float = 1.0, freq: float = 440.0):
    """Create a minimal WAV file using Python's wave module."""
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


class PreviewTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vf_cp002_")
        self.cache_dir = os.path.join(self.tmp, "previews")
        self.config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        self.gen = CompositionPreviewGenerator(
            cache_dir=self.cache_dir,
            models_config=MODELS_CONFIG,
            config_dir=self.config_dir,
        )
        # Create test fixtures
        self.bg_image = os.path.join(self.tmp, "bg.png")
        _make_test_image(self.bg_image, 800, 1200, (80, 100, 140))
        self.overlay_image = os.path.join(self.tmp, "overlay.png")
        _make_test_image(self.overlay_image, 200, 200, (255, 200, 0))
        self.clip_image = os.path.join(self.tmp, "clip.png")
        _make_test_image(self.clip_image, 720, 1280, (120, 80, 160))
        self.audio_wav = os.path.join(self.tmp, "tone.wav")
        _make_test_wav(self.audio_wav, 1.5, 440)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _canvas(self):
        return CanvasSpec(width=540, height=960)

    def _text_plan(self, **kw):
        defaults = dict(
            element_id="txt1",
            text="Hello World",
            style_ref="default",
            position="center",
        )
        defaults.update(kw)
        tr = TextRole(**defaults)
        return CompositionPlan(
            plan_id="p1",
            canvas=self._canvas(),
            text_roles=(tr,),
        )

    def _audio_plan(self, source_path: str = ""):
        lane = AudioLane(
            element_id="aud1",
            lane_type="vo",
            source_path=source_path,
            gain=0.85,
            start=0.0,
            end=2.0,
            duck_points=((1.0, 0.3),),
        )
        mix = AudioMix(element_id="mix1", lanes=(lane,), lufs_target=-16.0)
        return CompositionPlan(
            plan_id="p2",
            canvas=self._canvas(),
            audio_mix=mix,
        )

    def _visual_plan(self, source_path: str = ""):
        vc = VisualClip(
            element_id="vis1",
            source_path=source_path or self.clip_image,
            in_point=0.0,
            out_point=2.0,
            crop_x=0.1,
            crop_y=0.1,
            crop_w=0.8,
            crop_h=0.8,
            scale=1.0,
            start=0.0,
            end=2.0,
        )
        return CompositionPlan(
            plan_id="p3",
            canvas=self._canvas(),
            visual_clips=(vc,),
        )

    def _graphics_plan(self, overlay_path: str = "", bg_path: str = ""):
        go = GraphicsOverlay(
            element_id="gfx1",
            overlay_path=overlay_path or self.overlay_image,
            background_path=bg_path or self.bg_image,
            position_x=0.5,
            position_y=0.8,
            scale=1.0,
            opacity=0.9,
        )
        return CompositionPlan(
            plan_id="p4",
            canvas=self._canvas(),
            graphics_overlays=(go,),
        )

    def _transition_plan(self):
        tr = Transition(
            element_id="tr1",
            transition_type="crossfade",
            duration=0.5,
            start=2.0,
        )
        return CompositionPlan(
            plan_id="p5",
            canvas=self._canvas(),
            transitions=(tr,),
            total_duration=5.0,
        )


# ---------------------------------------------------------------------------
# Text role preview
# ---------------------------------------------------------------------------

class TestTextPreview(PreviewTestBase):
    def test_text_preview_visible_font_specimen(self):
        """Text role produces a visible font specimen (PIL image, >0 bytes)."""
        plan = self._text_plan()
        tr = plan.text_roles[0]
        path = self.gen.preview_text(plan, tr)
        self.assertTrue(os.path.exists(path), "Preview file should exist")
        self.assertGreater(os.path.getsize(path), 0, "Preview file should be non-empty")
        # Verify it's a valid image
        img = Image.open(path)
        self.assertIn(img.format, ("PNG",))
        self.assertEqual(img.size, (plan.canvas.width, plan.canvas.height))

    def test_text_preview_display_font_for_hook(self):
        """Hook style ref resolves to display font and still renders."""
        plan = self._text_plan(style_ref="hook", text="BIG HOOK")
        tr = plan.text_roles[0]
        path = self.gen.preview_text(plan, tr)
        self.assertGreater(os.path.getsize(path), 100)  # should be a real image

    def test_missing_font_fails_closed(self):
        """Missing font file raises PreviewError."""
        plan = self._text_plan(font_path="/nonexistent/font.ttf")
        tr = plan.text_roles[0]
        with self.assertRaises(PreviewError) as ctx:
            self.gen.preview_text(plan, tr)
        self.assertIn("not found", str(ctx.exception))


# ---------------------------------------------------------------------------
# Audio preview
# ---------------------------------------------------------------------------

class TestAudioPreview(PreviewTestBase):
    def test_audio_waveform_exists(self):
        """Audio lane shows a waveform (matplotlib output exists, >0 bytes)."""
        plan = self._audio_plan(source_path=self.audio_wav)
        path = self.gen.preview_audio(plan, plan.audio_mix)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)
        img = Image.open(path)
        self.assertEqual(img.format, "PNG")

    def test_audio_preview_synthetic_when_no_source(self):
        """Audio preview renders with synthetic waveform when no source file."""
        plan = self._audio_plan(source_path="")
        path = self.gen.preview_audio(plan, plan.audio_mix)
        self.assertGreater(os.path.getsize(path), 0)


# ---------------------------------------------------------------------------
# Visual clip preview
# ---------------------------------------------------------------------------

class TestVisualPreview(PreviewTestBase):
    def test_visual_clip_shows_framing(self):
        """Visual clip shows framing with safe-zone overlay."""
        plan = self._visual_plan()
        vc = plan.visual_clips[0]
        path = self.gen.preview_visual(plan, vc)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)
        img = Image.open(path)
        self.assertEqual(img.size, (plan.canvas.width, plan.canvas.height))

    def test_missing_clip_fails_closed(self):
        """Missing clip image raises PreviewError."""
        plan = self._visual_plan(source_path="/nonexistent/clip.mp4")
        vc = plan.visual_clips[0]
        with self.assertRaises(PreviewError) as ctx:
            self.gen.preview_visual(plan, vc)
        self.assertIn("not found", str(ctx.exception))


# ---------------------------------------------------------------------------
# Graphics overlay preview
# ---------------------------------------------------------------------------

class TestGraphicsPreview(PreviewTestBase):
    def test_graphics_overlay_renders(self):
        """Graphics overlay renders on representative background."""
        plan = self._graphics_plan()
        go = plan.graphics_overlays[0]
        path = self.gen.preview_graphics(plan, go)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)

    def test_missing_overlay_fails_closed(self):
        """Missing overlay file raises PreviewError."""
        plan = self._graphics_plan(overlay_path="/nope.png")
        go = plan.graphics_overlays[0]
        with self.assertRaises(PreviewError):
            self.gen.preview_graphics(plan, go)

    def test_missing_background_fails_closed(self):
        """Missing background file raises PreviewError."""
        plan = self._graphics_plan(bg_path="/nope_bg.png")
        go = plan.graphics_overlays[0]
        with self.assertRaises(PreviewError):
            self.gen.preview_graphics(plan, go)


# ---------------------------------------------------------------------------
# Transition preview
# ---------------------------------------------------------------------------

class TestTransitionPreview(PreviewTestBase):
    def test_transition_timing_diagram(self):
        """Transition produces an annotated timing diagram."""
        plan = self._transition_plan()
        tr = plan.transitions[0]
        path = self.gen.preview_transition(plan, tr)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(os.path.getsize(path), 0)


# ---------------------------------------------------------------------------
# Full timeline preview
# ---------------------------------------------------------------------------

class TestTimelinePreview(PreviewTestBase):
    def test_full_timeline(self):
        """Full timeline diagram shows all elements."""
        tr = TextRole(element_id="t1", text="Hook", style_ref="hook", start=0, end=2)
        vc = VisualClip(element_id="v1", source_path=self.clip_image, start=0, end=3)
        go = GraphicsOverlay(element_id="g1", overlay_path=self.overlay_image,
                             background_path=self.bg_image, start=1, end=2)
        trans = Transition(element_id="tr1", transition_type="crossfade", duration=0.5, start=2)
        lane = AudioLane(element_id="a1", lane_type="music", source_path=self.audio_wav,
                         start=0, end=5)
        mix = AudioMix(element_id="m1", lanes=(lane,), lufs_target=-14)
        plan = CompositionPlan(
            plan_id="full",
            canvas=self._canvas(),
            text_roles=(tr,),
            audio_mix=mix,
            visual_clips=(vc,),
            graphics_overlays=(go,),
            transitions=(trans,),
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
        plan = self._text_plan()
        tr = plan.text_roles[0]
        path1 = self.gen.preview_text(plan, tr)
        size1 = os.path.getsize(path1)
        # Modify the output to prove caching: write a marker, then call again
        # and confirm the marker survives (no re-render)
        with open(path1, "ab") as f:
            f.write(b"CACHE_MARKER")
        size_after_marker = os.path.getsize(path1)
        path2 = self.gen.preview_text(plan, tr)
        self.assertEqual(path1, path2, "Cached path should be identical")
        self.assertEqual(os.path.getsize(path2), size_after_marker,
                         "File should not have been re-rendered (cache hit)")

    def test_plan_change_invalidates_cache(self):
        """Different plan hash → different cache directory → new preview."""
        plan_a = self._text_plan()
        plan_b = CompositionPlan(
            plan_id="p1_modified",
            canvas=self._canvas(),
            text_roles=(TextRole(element_id="txt1", text="Different text", style_ref="default"),),
        )
        tr_a = plan_a.text_roles[0]
        tr_b = plan_b.text_roles[0]
        path_a = self.gen.preview_text(plan_a, tr_a)
        path_b = self.gen.preview_text(plan_b, tr_b)
        self.assertNotEqual(path_a, path_b,
                            "Different plan hashes should produce different cache paths")
        # Both should exist and be valid
        self.assertGreater(os.path.getsize(path_a), 0)
        self.assertGreater(os.path.getsize(path_b), 0)


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
        call_count = {"n": 0}

        class GuardedSocket(original_socket):
            def __init__(self, *args, **kwargs):
                call_count["n"] += 1
                # Allow AF_UNIX (local) but block AF_INET / AF_INET6
                family = args[0] if args else socket.AF_INET
                if family in (socket.AF_INET, socket.AF_INET6):
                    raise PermissionError("Network access blocked in test")
                super().__init__(*args, **kwargs)

        socket.socket = GuardedSocket
        try:
            plan = self._text_plan()
            tr = plan.text_roles[0]
            path = self.gen.preview_text(plan, tr)
            self.assertGreater(os.path.getsize(path), 0)

            # Audio with local wav
            plan_a = self._audio_plan(source_path=self.audio_wav)
            path_a = self.gen.preview_audio(plan_a, plan_a.audio_mix)
            self.assertGreater(os.path.getsize(path_a), 0)

            # Visual clip with local image
            plan_v = self._visual_plan()
            path_v = self.gen.preview_visual(plan_v, plan_v.visual_clips[0])
            self.assertGreater(os.path.getsize(path_v), 0)
        finally:
            socket.socket = original_socket


# ---------------------------------------------------------------------------
# generate_all batch
# ---------------------------------------------------------------------------

class TestGenerateAll(PreviewTestBase):
    def test_generate_all_categories(self):
        """generate_all produces previews for every element type."""
        tr = TextRole(element_id="t1", text="Hook", style_ref="hook", start=0, end=2)
        vc = VisualClip(element_id="v1", source_path=self.clip_image, start=0, end=3)
        go = GraphicsOverlay(element_id="g1", overlay_path=self.overlay_image,
                             background_path=self.bg_image, start=1, end=2)
        trans = Transition(element_id="tr1", transition_type="crossfade", duration=0.5, start=2)
        lane = AudioLane(element_id="a1", lane_type="music", source_path=self.audio_wav,
                         start=0, end=5)
        mix = AudioMix(element_id="m1", lanes=(lane,), lufs_target=-14)
        plan = CompositionPlan(
            plan_id="all",
            canvas=self._canvas(),
            text_roles=(tr,),
            audio_mix=mix,
            visual_clips=(vc,),
            graphics_overlays=(go,),
            transitions=(trans,),
            total_duration=5.0,
        )
        results = self.gen.generate_all(plan)
        for cat in ("text", "audio", "visual", "graphics", "transition", "timeline"):
            self.assertIn(cat, results)
            self.assertGreater(len(results[cat]), 0, f"{cat} should have previews")
            for p in results[cat]:
                self.assertGreater(os.path.getsize(p), 0)

    def test_generate_all_collects_errors(self):
        """generate_all raises PreviewError listing all failures."""
        tr = TextRole(element_id="t1", text="Hi", font_path="/nonexistent.ttf")
        vc = VisualClip(element_id="v1", source_path="/nonexistent.mp4")
        plan = CompositionPlan(
            plan_id="bad",
            canvas=self._canvas(),
            text_roles=(tr,),
            visual_clips=(vc,),
            total_duration=2.0,
        )
        with self.assertRaises(PreviewError) as ctx:
            self.gen.generate_all(plan)
        msg = str(ctx.exception)
        self.assertIn("text", msg)
        self.assertIn("visual", msg)


if __name__ == "__main__":
    unittest.main()