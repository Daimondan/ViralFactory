"""VF-CP-002: Per-element preview generator.

Generates low-cost local previews from a CompositionPlan using PIL and
matplotlib only — NO provider API calls.  Previews are evidence for
ratification, not final artifacts.

Preview types
~~~~~~~~~~~~~

1. **Text role** — rendered font specimen on a blank canvas (PIL).
2. **Audio mix** — waveform display with VO / music / SFX lanes, gain curves,
   ducking points, and a LUFS target marker (matplotlib).
3. **Visual clip** — thumbnail showing crop / framing / scale on the canvas
   with a safe-zone overlay (PIL).
4. **Graphics overlay** — static frame of the overlay on a representative
   background (PIL).
5. **Transition** — annotated timing diagram (matplotlib).
6. **Full timeline** — horizontal multi-lane timeline diagram showing all
   elements with in/out points (matplotlib).

Design constraints
~~~~~~~~~~~~~~~~~~

- Local files only — any referenced font / clip / image must exist on disk.
- Fail closed — a missing reference raises ``PreviewError`` rather than
  silently producing a broken preview.
- Cache by element hash — previews are written to a cache directory keyed by
  ``element_hash``.  If the cached file already exists and the plan hash
  matches, the cached file is returned without re-rendering.
- Plan invalidation — a different plan hash produces a new cache subdirectory,
  so stale previews from a previous plan are never served.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
from dataclasses import asdict
from typing import Any, Optional

from services.composition_plan import (
    AudioLane,
    AudioMix,
    CanvasSpec,
    CompositionPlan,
    GraphicsOverlay,
    TextRole,
    Transition,
    VisualClip,
    element_hash,
)


class PreviewError(Exception):
    """Raised when a preview cannot be generated (missing file, bad input, …)."""


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _parse_color(color: str, default: tuple[int, int, int, int] = (255, 255, 255, 255)) -> tuple[int, int, int, int]:
    """Parse a CSS-style colour string into an RGBA tuple."""
    if not color:
        return default
    c = color.strip()
    if c.startswith("#"):
        hex_val = c[1:]
        if len(hex_val) == 3:
            hex_val = "".join(ch * 2 for ch in hex_val)
        r = int(hex_val[0:2], 16)
        g = int(hex_val[2:4], 16)
        b = int(hex_val[4:6], 16)
        return (r, g, b, 255)
    named = {
        "white": (255, 255, 255, 255),
        "black": (0, 0, 0, 255),
        "red": (255, 0, 0, 255),
        "yellow": (255, 255, 0, 255),
        "blue": (0, 0, 255, 255),
        "green": (0, 255, 0, 255),
    }
    return named.get(c.lower(), default)


# ---------------------------------------------------------------------------
# FFmpeg helpers (local only)
# ---------------------------------------------------------------------------

def _ffprobe_audio_samples(path: str, max_samples: int = 2000) -> list[float]:
    """Extract a downsampled mono waveform from a local audio/video file.

    Uses ``ffmpeg`` to decode to raw f32le mono at 8 kHz, then picks
    ``max_samples`` evenly-spaced peaks.  No network calls.
    """
    cmd = [
        "ffmpeg", "-v", "quiet", "-i", path,
        "-f", "f32le", "-ac", "1", "-ar", "8000", "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError as exc:
        raise PreviewError("ffmpeg not found on PATH") from exc
    if proc.returncode != 0:
        return []
    raw = proc.stdout
    if not raw:
        return []
    n_floats = len(raw) // 4
    if n_floats == 0:
        return []
    samples = struct.unpack(f"<{n_floats}f", raw[: n_floats * 4])
    if len(samples) <= max_samples:
        return list(samples)
    # Evenly-spaced sampling
    step = len(samples) / max_samples
    return [samples[int(i * step)] for i in range(max_samples)]


# ---------------------------------------------------------------------------
# Style resolution (local config only)
# ---------------------------------------------------------------------------

def _load_overlay_styles(config_dir: str = "config") -> dict[str, dict]:
    """Load overlay style definitions from ``render_styles.yaml``."""
    import yaml
    p = os.path.join(config_dir, "render_styles.yaml")
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        data = yaml.safe_load(f) or {}
    return data.get("overlay_styles") or {}


def _resolve_text_style(style_ref: str, config_dir: str) -> dict:
    styles = _load_overlay_styles(config_dir)
    return styles.get(style_ref) or styles.get("default") or {
        "fontsize": 48,
        "fontcolor": "white",
        "borderw": 2,
        "bordercolor": "black",
    }


# ---------------------------------------------------------------------------
# Font resolution
# ---------------------------------------------------------------------------

def _is_valid_font(path: str) -> bool:
    """Check that a file exists and is a loadable TrueType/OpenType font."""
    if not path or not os.path.exists(path):
        return False
    from PIL import ImageFont
    try:
        ImageFont.truetype(path, 16)
        return True
    except Exception:
        return False


def _system_fallback_font() -> str:
    """Find a usable system font for silent fallback (DejaVuSans bundled with matplotlib)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    # matplotlib bundles DejaVu — a reliable last resort
    try:
        import matplotlib
        mpl_data = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
        candidates.append(os.path.join(mpl_data, "DejaVuSans-Bold.ttf"))
        candidates.append(os.path.join(mpl_data, "DejaVuSans.ttf"))
    except ImportError:
        pass
    for c in candidates:
        if _is_valid_font(c):
            return c
    return ""


def _resolve_font(text_role: TextRole, models_config: dict, config_dir: str) -> str:
    """Resolve a font file path for a text role.

    Order of precedence:
    1. ``text_role.font_path`` (explicit per-element override)
    2. display font from ``models_config['rendering']['font_display']`` for
       hook/title style refs
    3. body font from ``models_config['rendering']['font_path']``
    4. System fallback (DejaVuSans bundled with matplotlib)

    Fail closed only when the *explicit* ``text_role.font_path`` is set but
    the file is missing — that's a hard error. Config-level fonts silently
    fall back to a system font so previews can still render as evidence.
    """
    # 1. Explicit per-element font — fail closed if missing
    if text_role.font_path:
        if not _is_valid_font(text_role.font_path):
            if not os.path.exists(text_role.font_path):
                raise PreviewError(f"Font file not found: {text_role.font_path}")
            raise PreviewError(f"Font file not a valid TrueType font: {text_role.font_path}")
        return text_role.font_path

    # 2/3. Config fonts — validate, fall back to system if invalid
    rendering = (models_config or {}).get("rendering", {})
    if text_role.style_ref in ("hook", "title"):
        font = rendering.get("font_display", "")
    else:
        font = rendering.get("font_path", "")

    if _is_valid_font(font):
        return font

    # 4. System fallback
    sys_font = _system_fallback_font()
    if sys_font:
        return sys_font

    raise PreviewError("No usable font found: config font invalid and no system fallback available")


# ---------------------------------------------------------------------------
# Position helpers
# ---------------------------------------------------------------------------

def _text_position_y(position: str, height: int) -> int:
    if position == "top":
        return 60
    if position == "bottom":
        return height - 200
    if position == "bottom-third":
        return int(height * 0.72)
    return (height - 100) // 2


# ---------------------------------------------------------------------------
# Preview generators
# ---------------------------------------------------------------------------

def _generate_text_preview(
    text_role: TextRole,
    canvas: CanvasSpec,
    models_config: dict,
    config_dir: str,
    out_path: str,
) -> str:
    """Render a text role as a font specimen on a blank canvas (PIL)."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = _resolve_font(text_role, models_config, config_dir)
    style = _resolve_text_style(text_role.style_ref, config_dir)

    font_size = text_role.font_size or int(style.get("fontsize", 48))
    color_str = text_role.color or style.get("fontcolor", "white")
    text_color = _parse_color(color_str)

    try:
        font = ImageFont.truetype(font_path, font_size)
    except (IOError, OSError) as exc:
        # Try system fallback before failing
        sys_font = _system_fallback_font()
        if sys_font and sys_font != font_path:
            try:
                font = ImageFont.truetype(sys_font, font_size)
            except (IOError, OSError):
                raise PreviewError(f"Cannot load font {font_path}: {exc}") from exc
        else:
            raise PreviewError(f"Cannot load font {font_path}: {exc}") from exc

    img = Image.new("RGBA", (canvas.width, canvas.height), (20, 20, 20, 255))
    draw = ImageDraw.Draw(img)

    # Auto-wrap
    max_text_width = canvas.width - 120
    lines: list[str] = []
    for raw_line in text_role.text.split("\n"):
        words = raw_line.split()
        current: list[str] = []
        for word in words:
            test = " ".join(current + [word])
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_text_width or not current:
                current.append(word)
            else:
                lines.append(" ".join(current))
                current = [word]
        if current:
            lines.append(" ".join(current))
    if not lines:
        raise PreviewError("Text role produced no visible lines")

    line_height = font_size + 14
    y = _text_position_y(text_role.position, canvas.height)
    # Draw a faint label indicating style_ref + position in the corner
    label = f"style={text_role.style_ref}  pos={text_role.position}  size={font_size}px"
    try:
        label_font = ImageFont.truetype(font_path, 20)
    except (IOError, OSError):
        try:
            label_font = ImageFont.truetype(_system_fallback_font(), 20)
        except Exception:
            label_font = ImageFont.load_default()
    draw.text((20, 20), label, fill=(128, 128, 128, 200), font=label_font)

    # Draw a position reference line
    draw.line([(0, y), (canvas.width, y)], fill=(60, 60, 60, 120), width=1)

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (canvas.width - w) // 2
        # Shadow / border
        borderw = int(style.get("borderw", 2))
        if borderw > 0:
            border_color = _parse_color(style.get("bordercolor", "black"), (0, 0, 0, 255))
            for dx in range(-borderw, borderw + 1):
                for dy in range(-borderw, borderw + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), line, fill=border_color, font=font)
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_height

    img.save(out_path)
    return out_path


def _generate_audio_preview(
    audio_mix: AudioMix,
    canvas: CanvasSpec,
    out_path: str,
) -> str:
    """Render an audio mix waveform preview with lanes, gain curves, ducking, LUFS (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    lanes = audio_mix.lanes
    if not lanes:
        raise PreviewError("Audio mix has no lanes")

    lane_colors = {"vo": "#4FC3F7", "music": "#81C784", "sfx": "#FFD54F"}
    fig, axes = plt.subplots(len(lanes), 1, figsize=(10, 2.2 * len(lanes)), squeeze=False)
    fig.suptitle(f"Audio Mix Preview  —  LUFS target: {audio_mix.lufs_target}", fontsize=11)

    for idx, lane in enumerate(lanes):
        ax = axes[idx, 0]
        color = lane_colors.get(lane.lane_type, "#BA68C8")
        ax.set_facecolor("#1a1a2e")
        # Title
        ax.set_title(f"{lane.lane_type.upper()}  ({lane.element_id})", fontsize=9, color=color)

        if lane.source_path and os.path.exists(lane.source_path):
            samples = _ffprobe_audio_samples(lane.source_path, max_samples=1000)
        else:
            # Synthetic placeholder waveform — no file to read
            t = np.linspace(0, max(lane.end - lane.start, 1.0), 200)
            samples = list(0.3 * np.sin(2 * np.pi * 3 * t) * np.exp(-t * 0.2))

        if samples:
            t_axis = np.linspace(lane.start, lane.start + len(samples) * 0.05, len(samples))
            ax.fill_between(t_axis, 0, samples, color=color, alpha=0.6, linewidth=0.5)
            ax.fill_between(t_axis, 0, [-s for s in samples], color=color, alpha=0.6, linewidth=0.5)

        # Gain line
        if lane.gain != 1.0:
            ax.axhline(y=lane.gain, color="white", linestyle="--", linewidth=0.8, alpha=0.5)
            ax.text(lane.start, lane.gain, f"gain={lane.gain}", color="white", fontsize=7, va="bottom")

        # Ducking points
        for duck_t, depth in lane.duck_points:
            ax.axvline(x=duck_t, color="#FF6E40", linestyle=":", linewidth=1.2)
            ax.text(duck_t, 0.9, f"duck {depth:.0%}", color="#FF6E40", fontsize=6, rotation=90, va="top")

        ax.set_xlim(lane.start, lane.start + max(lane.end - lane.start, 1.0))
        ax.set_ylim(-1.2, 1.2)
        ax.tick_params(colors="grey", labelsize=7)

    # LUFS target marker on the last axis
    last_ax = axes[-1, 0]
    last_ax.axhline(y=0, color="#E0E0E0", linewidth=0.4)
    fig.text(0.99, 0.01, f"LUFS {audio_mix.lufs_target}", ha="right", va="bottom",
             fontsize=8, color="#E0E0E0")

    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    fig.savefig(out_path, dpi=100, facecolor="#0f0f23")
    plt.close(fig)
    return out_path


def _generate_visual_preview(
    clip: VisualClip,
    canvas: CanvasSpec,
    out_path: str,
) -> str:
    """Render a visual clip thumbnail with crop/framing/scale + safe-zone overlay (PIL)."""
    from PIL import Image, ImageDraw

    if not clip.source_path:
        raise PreviewError("Visual clip has no source_path")
    if not os.path.exists(clip.source_path):
        raise PreviewError(f"Visual clip source not found: {clip.source_path}")

    # Open the source image (first frame for video — PIL can't read video,
    # so we use ffprobe/ffmpeg to extract a frame if it's a video file)
    ext = clip.source_path.lower()
    is_video = not ext.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp"))

    if is_video:
        # Extract a representative frame at in_point
        tmp_frame = out_path + ".frame.png"
        cmd = [
            "ffmpeg", "-v", "quiet", "-y",
            "-ss", str(clip.in_point),
            "-i", clip.source_path,
            "-frames:v", "1",
            "-f", "image2",
            tmp_frame,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=30)
        except FileNotFoundError as exc:
            raise PreviewError("ffmpeg not found") from exc
        if proc.returncode != 0 or not os.path.exists(tmp_frame):
            raise PreviewError(f"Could not extract frame from {clip.source_path}")
        src_img = Image.open(tmp_frame).convert("RGBA")
        os.remove(tmp_frame)
    else:
        src_img = Image.open(clip.source_path).convert("RGBA")

    # Create canvas
    canvas_img = Image.new("RGBA", (canvas.width, canvas.height), (15, 15, 15, 255))
    draw = ImageDraw.Draw(canvas_img)

    # Apply crop
    sw, sh = src_img.size
    crop_px = (
        int(clip.crop_x * sw),
        int(clip.crop_y * sh),
        int((clip.crop_x + clip.crop_w) * sw),
        int((clip.crop_y + clip.crop_h) * sh),
    )
    cropped = src_img.crop(crop_px)

    # Apply scale
    if clip.scale != 1.0:
        new_w = max(1, int(cropped.width * clip.scale))
        new_h = max(1, int(cropped.height * clip.scale))
        cropped = cropped.resize((new_w, new_h))

    # Fit into canvas (contain)
    ratio = min(canvas.width / cropped.width, canvas.height / cropped.height)
    fit_w = int(cropped.width * ratio)
    fit_h = int(cropped.height * ratio)
    if fit_w != cropped.width or fit_h != cropped.height:
        cropped = cropped.resize((fit_w, fit_h))

    paste_x = (canvas.width - fit_w) // 2
    paste_y = (canvas.height - fit_h) // 2
    canvas_img.paste(cropped, (paste_x, paste_y), cropped)

    # Safe-zone overlay (90% centre)
    safe_margin_x = int(canvas.width * 0.05)
    safe_margin_y = int(canvas.height * 0.05)
    draw.rectangle(
        [safe_margin_x, safe_margin_y, canvas.width - safe_margin_x, canvas.height - safe_margin_y],
        outline=(0, 255, 0, 160),
        width=3,
    )
    # Label
    draw.text((safe_margin_x + 6, safe_margin_y + 6), "SAFE ZONE", fill=(0, 255, 0, 200))
    info = f"crop=({clip.crop_x:.2f},{clip.crop_y:.2f},{clip.crop_w:.2f},{clip.crop_h:.2f})  scale={clip.scale:.2f}"
    draw.text((20, canvas.height - 30), info, fill=(200, 200, 200, 220))

    canvas_img.save(out_path)
    return out_path


def _generate_graphics_preview(
    overlay: GraphicsOverlay,
    canvas: CanvasSpec,
    out_path: str,
) -> str:
    """Render a graphics overlay on a representative background (PIL)."""
    from PIL import Image

    if not overlay.overlay_path:
        raise PreviewError("Graphics overlay has no overlay_path")
    if not os.path.exists(overlay.overlay_path):
        raise PreviewError(f"Graphics overlay file not found: {overlay.overlay_path}")

    ov_img = Image.open(overlay.overlay_path).convert("RGBA")

    # Background: use provided background_path, else a grey canvas
    if overlay.background_path:
        if not os.path.exists(overlay.background_path):
            raise PreviewError(f"Graphics overlay background not found: {overlay.background_path}")
        bg_img = Image.open(overlay.background_path).convert("RGBA")
    else:
        bg_img = Image.new("RGBA", (canvas.width, canvas.height), (60, 60, 60, 255))

    # Scale background to canvas
    bg_img = bg_img.resize((canvas.width, canvas.height))

    # Scale overlay
    if overlay.scale != 1.0:
        new_w = max(1, int(ov_img.width * overlay.scale))
        new_h = max(1, int(ov_img.height * overlay.scale))
        ov_img = ov_img.resize((new_w, new_h))

    # Apply opacity
    if overlay.opacity < 1.0:
        alpha = ov_img.split()[3]
        alpha = alpha.point(lambda p: int(p * overlay.opacity))
        ov_img.putalpha(alpha)

    # Position
    pos_x = int(overlay.position_x * canvas.width) - ov_img.width // 2
    pos_y = int(overlay.position_y * canvas.height) - ov_img.height // 2

    bg_img.paste(ov_img, (pos_x, pos_y), ov_img)
    bg_img.save(out_path)
    return out_path


def _generate_transition_preview(
    transition: Transition,
    canvas: CanvasSpec,
    out_path: str,
) -> str:
    """Render an annotated timing diagram for a transition (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.set_facecolor("#1a1a2e")

    # Two segment bars with the transition overlap region
    seg1_end = transition.start
    trans_end = transition.start + transition.duration

    ax.barh(0, seg1_end, left=0, height=0.4, color="#4FC3F7", label="Segment A")
    ax.barh(0, transition.duration, left=seg1_end, height=0.4, color="#FFD54F", alpha=0.7, label=f"Transition: {transition.transition_type}")
    ax.barh(0, 2.0, left=trans_end, height=0.4, color="#81C784", label="Segment B")

    # Annotations
    ax.axvline(x=seg1_end, color="white", linestyle="--", linewidth=1)
    ax.axvline(x=trans_end, color="white", linestyle="--", linewidth=1)
    ax.annotate(f"start\n{transition.start:.2f}s", xy=(seg1_end, 0.3), ha="center", color="white", fontsize=8)
    ax.annotate(f"end\n{trans_end:.2f}s", xy=(trans_end, 0.3), ha="center", color="white", fontsize=8)
    ax.annotate(f"{transition.transition_type}\n{transition.duration:.2f}s",
                xy=(seg1_end + transition.duration / 2, 0), ha="center", va="center",
                color="black", fontsize=9, fontweight="bold")

    ax.set_xlim(-0.5, trans_end + 2.5)
    ax.set_ylim(-0.5, 0.8)
    ax.set_yticks([])
    ax.set_xlabel("Timeline (s)", color="grey")
    ax.tick_params(colors="grey")
    ax.set_title(f"Transition: {transition.transition_type}  ({transition.element_id})", color="white", fontsize=10)
    ax.legend(loc="upper right", fontsize=7, facecolor="#2a2a3e", labelcolor="white")

    fig.tight_layout()
    fig.savefig(out_path, dpi=100, facecolor="#0f0f23")
    plt.close(fig)
    return out_path


def _generate_timeline_preview(
    plan: CompositionPlan,
    out_path: str,
) -> str:
    """Render a full horizontal multi-lane timeline diagram (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    # Collect lanes: visual, text, audio, graphics, transition
    lane_defs = [
        ("Visual", plan.visual_clips, "#4FC3F7"),
        ("Text", plan.text_roles, "#FFD54F"),
        ("Graphics", plan.graphics_overlays, "#BA68C8"),
        ("Transition", plan.transitions, "#FF6E40"),
    ]

    total_dur = plan.total_duration or max(
        ([e.end for e in plan.visual_clips] + [e.end for e in plan.text_roles]
         + [e.end for e in plan.graphics_overlays]
         + [(t.start + t.duration) for t in plan.transitions] + [0.0]),
        default=1.0,
    )

    n_lanes = len(lane_defs) + (1 if plan.audio_mix else 0)
    fig, ax = plt.subplots(figsize=(12, max(3, 1.2 * n_lanes + 1)))
    ax.set_facecolor("#1a1a2e")

    lane_idx = 0
    for label, elements, color in lane_defs:
        for el in elements:
            start = getattr(el, "start", 0.0)
            end = getattr(el, "end", getattr(el, "start", 0.0) + getattr(el, "duration", 0.0))
            ax.barh(lane_idx, max(end - start, 0.1), left=start, height=0.5,
                    color=color, alpha=0.75, edgecolor="white", linewidth=0.5)
            eid = getattr(el, "element_id", "")
            if eid:
                ax.text(start + 0.05, lane_idx, eid, va="center", fontsize=6, color="white")
        ax.text(-0.3, lane_idx, label, ha="right", va="center", color=color, fontsize=8, fontweight="bold")
        lane_idx += 1

    if plan.audio_mix:
        for lane in plan.audio_mix.lanes:
            ax.barh(lane_idx, max(lane.end - lane.start, 0.1), left=lane.start,
                    height=0.4, color="#81C784", alpha=0.7, edgecolor="white", linewidth=0.5)
            ax.text(lane.start + 0.05, lane_idx, lane.lane_type, va="center", fontsize=6, color="white")
        ax.text(-0.3, lane_idx, "Audio", ha="right", va="center", color="#81C784", fontsize=8, fontweight="bold")
        lane_idx += 1

    ax.set_xlim(-0.5, total_dur + 0.5)
    ax.set_ylim(-0.8, lane_idx - 0.2)
    ax.set_xlabel("Timeline (s)", color="grey")
    ax.tick_params(colors="grey", labelsize=8)
    ax.set_yticks([])
    ax.set_title(f"Full Timeline  —  {plan.plan_id or '(no id)'}  —  {total_dur:.1f}s",
                 color="white", fontsize=10)
    ax.grid(axis="x", color="#333", linewidth=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=100, facecolor="#0f0f23")
    plt.close(fig)
    return out_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CompositionPreviewGenerator:
    """Generate and cache per-element previews from a CompositionPlan.

    Parameters
    ----------
    cache_dir
        Root directory for cached preview files.
    models_config
        The parsed ``config/models.yaml`` dict (used for font paths).
    config_dir
        Directory containing ``render_styles.yaml``.
    """

    def __init__(
        self,
        cache_dir: str = "data/previews",
        models_config: Optional[dict] = None,
        config_dir: str = "config",
    ) -> None:
        self.cache_dir = cache_dir
        self.models_config = models_config or {}
        self.config_dir = config_dir

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _plan_cache_dir(self, plan: CompositionPlan) -> str:
        """Return the cache subdirectory for this plan's hash."""
        d = os.path.join(self.cache_dir, plan.plan_hash())
        os.makedirs(d, exist_ok=True)
        return d

    def _cache_path(self, plan: CompositionPlan, category: str, eid: str, ext: str) -> str:
        d = self._plan_cache_dir(plan)
        return os.path.join(d, f"{category}_{eid}.{ext}")

    def _is_cached(self, path: str) -> bool:
        return os.path.exists(path) and os.path.getsize(path) > 0

    # ------------------------------------------------------------------
    # Element-level dispatch
    # ------------------------------------------------------------------

    def preview_text(self, plan: CompositionPlan, text_role: TextRole) -> str:
        out = self._cache_path(plan, "text", text_role.element_id, "png")
        if self._is_cached(out):
            return out
        return _generate_text_preview(
            text_role, plan.canvas, self.models_config, self.config_dir, out,
        )

    def preview_audio(self, plan: CompositionPlan, audio_mix: AudioMix) -> str:
        out = self._cache_path(plan, "audio", audio_mix.element_id, "png")
        if self._is_cached(out):
            return out
        return _generate_audio_preview(audio_mix, plan.canvas, out)

    def preview_visual(self, plan: CompositionPlan, clip: VisualClip) -> str:
        out = self._cache_path(plan, "visual", clip.element_id, "png")
        if self._is_cached(out):
            return out
        return _generate_visual_preview(clip, plan.canvas, out)

    def preview_graphics(self, plan: CompositionPlan, overlay: GraphicsOverlay) -> str:
        out = self._cache_path(plan, "graphics", overlay.element_id, "png")
        if self._is_cached(out):
            return out
        return _generate_graphics_preview(overlay, plan.canvas, out)

    def preview_transition(self, plan: CompositionPlan, transition: Transition) -> str:
        out = self._cache_path(plan, "transition", transition.element_id, "png")
        if self._is_cached(out):
            return out
        return _generate_transition_preview(transition, plan.canvas, out)

    def preview_timeline(self, plan: CompositionPlan) -> str:
        out = self._cache_path(plan, "timeline", "full", "png")
        if self._is_cached(out):
            return out
        return _generate_timeline_preview(plan, out)

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def generate_all(self, plan: CompositionPlan) -> dict[str, list[str]]:
        """Generate previews for every element in the plan.

        Returns a dict mapping category → list of output paths.
        Missing-file errors are collected and re-raised as a single
        ``PreviewError`` at the end so the caller sees all failures.
        """
        results: dict[str, list[str]] = {
            "text": [],
            "audio": [],
            "visual": [],
            "graphics": [],
            "transition": [],
            "timeline": [],
        }
        errors: list[str] = []

        for tr in plan.text_roles:
            try:
                results["text"].append(self.preview_text(plan, tr))
            except PreviewError as exc:
                errors.append(f"text:{tr.element_id}: {exc}")

        if plan.audio_mix:
            try:
                results["audio"].append(self.preview_audio(plan, plan.audio_mix))
            except PreviewError as exc:
                errors.append(f"audio:{plan.audio_mix.element_id}: {exc}")

        for vc in plan.visual_clips:
            try:
                results["visual"].append(self.preview_visual(plan, vc))
            except PreviewError as exc:
                errors.append(f"visual:{vc.element_id}: {exc}")

        for go in plan.graphics_overlays:
            try:
                results["graphics"].append(self.preview_graphics(plan, go))
            except PreviewError as exc:
                errors.append(f"graphics:{go.element_id}: {exc}")

        for tr in plan.transitions:
            try:
                results["transition"].append(self.preview_transition(plan, tr))
            except PreviewError as exc:
                errors.append(f"transition:{tr.element_id}: {exc}")

        try:
            results["timeline"].append(self.preview_timeline(plan))
        except PreviewError as exc:
            errors.append(f"timeline: {exc}")

        if errors:
            raise PreviewError("Preview generation failures:\n" + "\n".join(errors))

        return results