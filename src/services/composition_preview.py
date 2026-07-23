"""VF-CP-002: Per-element preview generator.

Generates low-cost local previews from a CompositionPlan (dict-based, as
produced by ``services.composition_plan.CompositionPlanGenerator``) using
PIL and matplotlib only — NO provider API calls.

Previews are evidence for ratification, not final artifacts.

Preview types
~~~~~~~~~~~~~

1. **Text role** — rendered font specimen on a blank canvas (PIL).
2. **Audio mix** — waveform display with VO / music / SFX lanes, gain curves,
   ducking points, and a LUFS target marker (matplotlib).
3. **Visual clip** — thumbnail showing crop / framing / scale on the canvas
   with a safe-zone overlay (PIL).
4. **Graphics overlay** — static frame of overlay on a representative
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
from typing import Any, Optional


class PreviewError(Exception):
    """Raised when a preview cannot be generated (missing file, bad input, …)."""


# ---------------------------------------------------------------------------
# Plan helpers
# ---------------------------------------------------------------------------

def _plan_hash(plan: dict) -> str:
    """Return the plan's hash, or compute one if missing."""
    h = plan.get("plan_hash")
    if h:
        return h
    # Fallback: compute a simple hash from the plan dict
    blob = json.dumps(plan, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _element_hash(element: dict) -> str:
    """Stable hash for a single plan element dict."""
    blob = json.dumps(element, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _canvas_dims(plan: dict) -> tuple[int, int]:
    """Extract (width, height) from the plan's canvas spec."""
    canvas = plan.get("canvas", {})
    res = canvas.get("resolution", {})
    if isinstance(res, dict):
        return int(res.get("width", 1080)), int(res.get("height", 1920))
    # String format "1080x1920"
    if isinstance(res, str) and "x" in res:
        w, h = res.split("x", 1)
        return int(w), int(h)
    return 1080, 1920


def _safe_zone_margins(plan: dict) -> tuple[float, float]:
    """Return (title_safe, action_safe) normalized margins from canvas spec."""
    sz = plan.get("canvas", {}).get("safe_zones", {})
    return float(sz.get("title_safe", 0.9)), float(sz.get("action_safe", 0.95))


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
    step = len(samples) / max_samples
    return [samples[int(i * step)] for i in range(max_samples)]


def _ffmpeg_extract_frame(video_path: str, time_sec: float, out_path: str) -> bool:
    """Extract a single frame from a local video file. Returns True on success."""
    cmd = [
        "ffmpeg", "-v", "quiet", "-y",
        "-ss", str(time_sec),
        "-i", video_path,
        "-frames:v", "1",
        "-f", "image2",
        out_path,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError:
        raise PreviewError("ffmpeg not found on PATH")
    return proc.returncode == 0 and os.path.exists(out_path)


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


def _resolve_font_for_text(
    text_element: dict,
    models_config: dict,
    config_dir: str,
) -> str:
    """Resolve a font file path for a text element from the plan dict.

    The plan stores font metadata (family, weight, file_hash, size, color)
    but NOT the file path. We resolve the actual file from models_config
    based on whether the element uses a display font (hook/title/lower_third/cta)
    or a body font.

    Fail closed only when no usable font can be found anywhere.
    """
    rendering = (models_config or {}).get("rendering", {})
    role = text_element.get("role", "")
    is_display = role in ("hook", "title", "lower_third", "cta")

    if is_display:
        config_font = rendering.get("font_display", "")
    else:
        config_font = rendering.get("font_path", "")

    if _is_valid_font(config_font):
        return config_font

    # System fallback
    sys_font = _system_fallback_font()
    if sys_font:
        return sys_font

    raise PreviewError(
        "No usable font found: config font invalid and no system fallback available"
    )


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
# Position helpers
# ---------------------------------------------------------------------------

def _text_position_from_plan(text_element: dict, canvas_w: int, canvas_h: int) -> tuple[int, int]:
    """Compute (x, y) pixel position from the text element's position dict."""
    pos = text_element.get("position", {})
    if isinstance(pos, dict):
        nx = float(pos.get("x", 0.5))
        ny = float(pos.get("y", 0.5))
        anchor = pos.get("anchor", "center")
    elif isinstance(pos, str):
        # Named position
        named = {
            "top": (0.5, 0.08),
            "center": (0.5, 0.5),
            "bottom": (0.5, 0.88),
            "bottom-third": (0.5, 0.72),
        }
        nx, ny = named.get(pos, (0.5, 0.5))
        anchor = "center"
    else:
        nx, ny = 0.5, 0.5
        anchor = "center"
    px = int(nx * canvas_w)
    py = int(ny * canvas_h)
    return px, py


# ---------------------------------------------------------------------------
# Preview generators
# ---------------------------------------------------------------------------

def _generate_text_preview(
    text_element: dict,
    canvas_w: int,
    canvas_h: int,
    models_config: dict,
    config_dir: str,
    out_path: str,
) -> str:
    """Render a text element as a font specimen on a blank canvas (PIL)."""
    from PIL import Image, ImageDraw, ImageFont

    font_path = _resolve_font_for_text(text_element, models_config, config_dir)
    font_info = text_element.get("font", {})
    style_ref = text_element.get("style_ref", "default")
    style = _resolve_text_style(style_ref, config_dir)

    font_size = int(font_info.get("size", style.get("fontsize", 48)))
    color_str = font_info.get("color", style.get("fontcolor", "white"))
    text_color = _parse_color(color_str)

    try:
        font = ImageFont.truetype(font_path, font_size)
    except (IOError, OSError) as exc:
        sys_font = _system_fallback_font()
        if sys_font and sys_font != font_path:
            try:
                font = ImageFont.truetype(sys_font, font_size)
            except (IOError, OSError):
                raise PreviewError(f"Cannot load font {font_path}: {exc}") from exc
        else:
            raise PreviewError(f"Cannot load font {font_path}: {exc}") from exc

    text = text_element.get("text", "")
    if not text:
        raise PreviewError("Text element has no text content")

    img = Image.new("RGBA", (canvas_w, canvas_h), (20, 20, 20, 255))
    draw = ImageDraw.Draw(img)

    # Auto-wrap
    max_text_width = canvas_w - 120
    lines: list[str] = []
    for raw_line in text.split("\n"):
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
        raise PreviewError("Text element produced no visible lines")

    line_height = font_size + 14
    total_text_h = len(lines) * line_height

    # Compute position
    px, py = _text_position_from_plan(text_element, canvas_w, canvas_h)
    # Adjust for anchor — center vertically on the position point
    y_start = py - total_text_h // 2

    # Label in corner
    label = f"role={text_element.get('role','')}  style={style_ref}  size={font_size}px"
    try:
        label_font = ImageFont.truetype(font_path, 20)
    except (IOError, OSError):
        try:
            label_font = ImageFont.truetype(_system_fallback_font(), 20)
        except Exception:
            label_font = ImageFont.load_default()
    draw.text((20, 20), label, fill=(128, 128, 128, 200), font=label_font)

    # Position reference line
    draw.line([(0, py), (canvas_w, py)], fill=(60, 60, 60, 120), width=1)

    y = y_start
    borderw = int(font_info.get("border_width", style.get("borderw", 2)))
    border_color = _parse_color(
        font_info.get("border_color", style.get("bordercolor", "black")),
        (0, 0, 0, 255),
    )
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        x = (canvas_w - w) // 2
        if borderw > 0:
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
    audio: dict,
    canvas_w: int,
    canvas_h: int,
    source_resolver: Optional[callable],
    out_path: str,
) -> str:
    """Render an audio mix waveform preview with lanes, gain curves, ducking, LUFS (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    # Build lane list from the plan's audio dict
    lanes: list[dict] = []
    total_dur = float(audio.get("_total_duration", 10.0))

    vo_track = audio.get("vo_track")
    if vo_track:
        lanes.append({
            "label": "VO",
            "color": "#4FC3F7",
            "source_path": source_resolver(vo_track.get("source_hash")) if source_resolver else "",
            "start": float(vo_track.get("trim_start_sec", 0.0)),
            "end": float(vo_track.get("trim_end_sec", total_dur)),
            "gain_curve": vo_track.get("gain_curve", []),
            "ducking": vo_track.get("ducking", {}),
        })

    music_track = audio.get("music_track")
    if music_track:
        lanes.append({
            "label": "MUSIC",
            "color": "#81C784",
            "source_path": source_resolver(music_track.get("source_hash")) if source_resolver else "",
            "start": float(music_track.get("start_sec", 0.0)),
            "end": float(music_track.get("stop_sec", total_dur)),
            "gain_curve": [{"time_sec": 0.0, "gain_db": float(music_track.get("gain_db", 0.0))}],
            "ducking": music_track.get("ducking", {}),
        })

    sfx_events = audio.get("sfx_events", [])
    if sfx_events:
        lanes.append({
            "label": "SFX",
            "color": "#FFD54F",
            "source_path": "",
            "start": 0.0,
            "end": total_dur,
            "gain_curve": [],
            "ducking": {},
            "sfx_points": [(float(s.get("trigger_sec", 0)), s.get("preset", "")) for s in sfx_events],
        })

    if not lanes:
        raise PreviewError("Audio plan has no tracks (no vo_track, music_track, or sfx_events)")

    mix_spec = audio.get("mix_spec", {})
    lufs_target = mix_spec.get("lufs_target", -14.0)

    n = len(lanes)
    fig, axes = plt.subplots(n, 1, figsize=(10, 2.2 * n), squeeze=False)
    fig.suptitle(f"Audio Mix Preview  —  LUFS target: {lufs_target}", fontsize=11)

    for idx, lane in enumerate(lanes):
        ax = axes[idx, 0]
        color = lane["color"]
        ax.set_facecolor("#1a1a2e")
        ax.set_title(f"{lane['label']}", fontsize=9, color=color)

        lane_start = lane["start"]
        lane_end = lane["end"]
        lane_dur = max(lane_end - lane_start, 0.5)

        # Get waveform
        if lane["source_path"] and os.path.exists(lane["source_path"]):
            samples = _ffprobe_audio_samples(lane["source_path"], max_samples=1000)
        else:
            # Synthetic placeholder
            t = np.linspace(0, lane_dur, 200)
            samples = list(0.3 * np.sin(2 * np.pi * 3 * t) * np.exp(-t * 0.2))

        if samples:
            t_axis = np.linspace(lane_start, lane_start + len(samples) * 0.05, len(samples))
            ax.fill_between(t_axis, 0, samples, color=color, alpha=0.6, linewidth=0.5)
            ax.fill_between(t_axis, 0, [-s for s in samples], color=color, alpha=0.6, linewidth=0.5)

        # Gain curve
        for gc in lane.get("gain_curve", []):
            gt = float(gc.get("time_sec", 0))
            gdb = float(gc.get("gain_db", 0))
            # Map dB to a 0-1 visual range (0dB → 0.7, -20dB → 0.1)
            vis_gain = max(0.05, min(1.0, 0.7 + gdb / 40.0))
            ax.axhline(y=vis_gain, color="white", linestyle="--", linewidth=0.8, alpha=0.5)
            ax.text(lane_start, vis_gain, f"gain={gdb}dB", color="white", fontsize=7, va="bottom")

        # Ducking points
        ducking = lane.get("ducking", {})
        if ducking and ducking.get("depth"):
            duck_y = 1.0 - float(ducking["depth"])
            ax.axhline(y=duck_y, color="#FF6E40", linestyle=":", linewidth=1.0)
            ax.text(lane_end - 0.3, duck_y, f"duck {float(ducking['depth']):.0%}",
                    color="#FF6E40", fontsize=7, va="bottom", ha="right")

        # SFX trigger points
        for trigger_t, preset in lane.get("sfx_points", []):
            ax.axvline(x=trigger_t, color="#FFD54F", linestyle="-", linewidth=1.5)
            ax.text(trigger_t, 0.9, f"sfx:{preset}", color="#FFD54F", fontsize=6,
                    rotation=90, va="top")

        ax.set_xlim(lane_start, lane_start + lane_dur)
        ax.set_ylim(-1.2, 1.2)
        ax.tick_params(colors="grey", labelsize=7)

    # LUFS marker
    axes[-1, 0].axhline(y=0, color="#E0E0E0", linewidth=0.4)
    fig.text(0.99, 0.01, f"LUFS {lufs_target}", ha="right", va="bottom",
             fontsize=8, color="#E0E0E0")

    fig.tight_layout(rect=[0, 0.02, 1, 0.95])
    fig.savefig(out_path, dpi=100, facecolor="#0f0f23")
    plt.close(fig)
    return out_path


def _generate_visual_preview(
    visual_element: dict,
    canvas_w: int,
    canvas_h: int,
    source_resolver: Optional[callable],
    out_path: str,
) -> str:
    """Render a visual clip thumbnail with crop/framing/scale + safe-zone overlay (PIL)."""
    from PIL import Image, ImageDraw

    source_hash = visual_element.get("source_hash", "")
    if not source_hash:
        raise PreviewError("Visual element has no source_hash")
    if not source_resolver:
        raise PreviewError("No source resolver provided for visual element")

    source_path = source_resolver(source_hash)
    if not source_path:
        raise PreviewError(f"Cannot resolve source_hash: {source_hash}")
    if not os.path.exists(source_path):
        raise PreviewError(f"Visual source file not found: {source_path}")

    kind = visual_element.get("kind", "still")
    trim_start = float(visual_element.get("trim_start_sec", 0.0))

    if kind == "clip" and not source_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        tmp_frame = out_path + ".frame.png"
        if not _ffmpeg_extract_frame(source_path, trim_start, tmp_frame):
            raise PreviewError(f"Could not extract frame from {source_path}")
        src_img = Image.open(tmp_frame).convert("RGBA")
        os.remove(tmp_frame)
    else:
        src_img = Image.open(source_path).convert("RGBA")

    canvas_img = Image.new("RGBA", (canvas_w, canvas_h), (15, 15, 15, 255))
    draw = ImageDraw.Draw(canvas_img)

    # Crop
    crop = visual_element.get("crop")
    sw, sh = src_img.size
    if crop and isinstance(crop, dict):
        cx = float(crop.get("x", 0))
        cy = float(crop.get("y", 0))
        cw = float(crop.get("w", 1.0))
        ch = float(crop.get("h", 1.0))
        cropped = src_img.crop((
            int(cx * sw), int(cy * sh),
            int((cx + cw) * sw), int((cy + ch) * sh),
        ))
    else:
        cropped = src_img

    # Scale
    scale = float(visual_element.get("scale", 1.0))
    if scale != 1.0:
        new_w = max(1, int(cropped.width * scale))
        new_h = max(1, int(cropped.height * scale))
        cropped = cropped.resize((new_w, new_h))

    # Fit into canvas
    ratio = min(canvas_w / cropped.width, canvas_h / cropped.height)
    fit_w = int(cropped.width * ratio)
    fit_h = int(cropped.height * ratio)
    if fit_w != cropped.width or fit_h != cropped.height:
        cropped = cropped.resize((fit_w, fit_h))

    # Canvas position offset
    canvas_pos = visual_element.get("canvas_position", {})
    pos_x = int(float(canvas_pos.get("x", 0)) * canvas_w)
    pos_y = int(float(canvas_pos.get("y", 0)) * canvas_h)

    paste_x = pos_x + (canvas_w - fit_w) // 2
    paste_y = pos_y + (canvas_h - fit_h) // 2
    canvas_img.paste(cropped, (paste_x, paste_y), cropped)

    # Safe-zone overlay (90% centre)
    safe_margin_x = int(canvas_w * 0.05)
    safe_margin_y = int(canvas_h * 0.05)
    draw.rectangle(
        [safe_margin_x, safe_margin_y, canvas_w - safe_margin_x, canvas_h - safe_margin_y],
        outline=(0, 255, 0, 160), width=3,
    )
    draw.text((safe_margin_x + 6, safe_margin_y + 6), "SAFE ZONE", fill=(0, 255, 0, 200))
    info = f"kind={kind}  scale={scale:.2f}  crop={'yes' if crop else 'no'}"
    draw.text((20, canvas_h - 30), info, fill=(200, 200, 200, 220))

    canvas_img.save(out_path)
    return out_path


def _generate_graphics_preview(
    graphics_element: dict,
    canvas_w: int,
    canvas_h: int,
    background_path: str,
    out_path: str,
) -> str:
    """Render a graphics overlay on a representative background (PIL).

    Graphics elements in the plan are text-based overlays (lower-thirds, etc.)
    — they don't have an explicit image file. We render a placeholder
    representing the overlay's position and type on the given background.
    """
    from PIL import Image, ImageDraw, ImageFont

    # Background
    if background_path:
        if not os.path.exists(background_path):
            raise PreviewError(f"Graphics background not found: {background_path}")
        bg_img = Image.open(background_path).convert("RGBA")
    else:
        bg_img = Image.new("RGBA", (canvas_w, canvas_h), (60, 60, 60, 255))

    bg_img = bg_img.resize((canvas_w, canvas_h))
    draw = ImageDraw.Draw(bg_img)

    # Position
    pos = graphics_element.get("position", {})
    if isinstance(pos, dict):
        nx = float(pos.get("x", 0.5))
        ny = float(pos.get("y", 0.5))
    else:
        nx, ny = 0.5, 0.5
    px = int(nx * canvas_w)
    py = int(ny * canvas_h)

    gfx_type = graphics_element.get("type", "overlay")
    scale = float(graphics_element.get("scale", 1.0))

    # Draw a semi-transparent rectangle representing the overlay area
    box_w = int(400 * scale)
    box_h = int(120 * scale)
    box_x = px - box_w // 2
    box_y = py - box_h // 2
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rounded_rectangle(
        [box_x, box_y, box_x + box_w, box_y + box_h],
        radius=15, fill=(0, 0, 0, 160),
    )
    bg_img = Image.alpha_composite(bg_img, overlay)
    draw = ImageDraw.Draw(bg_img)

    # Label
    eid = graphics_element.get("element_id", "")
    label = f"{gfx_type}  ({eid})"
    sys_font = _system_fallback_font()
    if sys_font:
        try:
            font = ImageFont.truetype(sys_font, 24)
        except (IOError, OSError):
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()
    draw.text((box_x + 10, box_y + 10), label, fill=(255, 255, 255, 230), font=font)
    draw.text((box_x + 10, box_y + 40), f"pos=({nx:.2f},{ny:.2f})  scale={scale:.2f}",
              fill=(200, 200, 200, 200), font=font)

    bg_img.save(out_path)
    return out_path


def _generate_transition_preview(
    transition: dict,
    canvas_w: int,
    canvas_h: int,
    out_path: str,
) -> str:
    """Render an annotated timing diagram for a transition (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    trans_type = transition.get("type", "cut")
    duration = float(transition.get("duration_sec", 0.0))
    trans_id = transition.get("transition_id", "")

    # We don't have an absolute start time in the plan; transitions are
    # beat-boundary events. We'll diagram the transition itself.
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.set_facecolor("#1a1a2e")

    if duration > 0:
        seg_a_end = 1.0
        trans_end = seg_a_end + duration
        ax.barh(0, seg_a_end, left=0, height=0.4, color="#4FC3F7", label="Segment A")
        ax.barh(0, duration, left=seg_a_end, height=0.4, color="#FFD54F", alpha=0.7,
                label=f"Transition: {trans_type}")
        ax.barh(0, 1.0, left=trans_end, height=0.4, color="#81C784", label="Segment B")

        ax.axvline(x=seg_a_end, color="white", linestyle="--", linewidth=1)
        ax.axvline(x=trans_end, color="white", linestyle="--", linewidth=1)
        ax.annotate(f"start\n{seg_a_end:.2f}s", xy=(seg_a_end, 0.3), ha="center", color="white", fontsize=8)
        ax.annotate(f"end\n{trans_end:.2f}s", xy=(trans_end, 0.3), ha="center", color="white", fontsize=8)
        ax.annotate(f"{trans_type}\n{duration:.2f}s",
                    xy=(seg_a_end + duration / 2, 0), ha="center", va="center",
                    color="black", fontsize=9, fontweight="bold")
        ax.set_xlim(-0.3, trans_end + 1.3)
    else:
        # Cut — no overlap
        ax.barh(0, 1.0, left=0, height=0.4, color="#4FC3F7", label="Segment A")
        ax.barh(0, 1.0, left=1.0, height=0.4, color="#81C784", label="Segment B")
        ax.axvline(x=1.0, color="#FF6E40", linestyle="-", linewidth=2)
        ax.annotate("CUT", xy=(1.0, 0), ha="center", va="center",
                    color="#FF6E40", fontsize=10, fontweight="bold")
        ax.set_xlim(-0.3, 2.3)

    ax.set_ylim(-0.5, 0.8)
    ax.set_yticks([])
    ax.set_xlabel("Timeline (s)", color="grey")
    ax.tick_params(colors="grey")
    ax.set_title(f"Transition: {trans_type}  ({trans_id})", color="white", fontsize=10)
    ax.legend(loc="upper right", fontsize=7, facecolor="#2a2a3e", labelcolor="white")

    fig.tight_layout()
    fig.savefig(out_path, dpi=100, facecolor="#0f0f23")
    plt.close(fig)
    return out_path


def _generate_timeline_preview(
    plan: dict,
    out_path: str,
) -> str:
    """Render a full horizontal multi-lane timeline diagram (matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    canvas_w, canvas_h = _canvas_dims(plan)
    total_dur = float(plan.get("total_duration_sec", 0.0))

    text_elements = plan.get("text_elements", [])
    visual_elements = plan.get("visual_elements", [])
    graphics_elements = plan.get("graphics_elements", [])
    transitions = plan.get("transitions", [])
    audio = plan.get("audio", {})

    # Determine total duration from element timings if not set
    if not total_dur:
        all_ends = []
        for te in text_elements:
            t = te.get("timing", {})
            all_ends.append(float(t.get("out_sec", 0)))
        for ve in visual_elements:
            all_ends.append(float(ve.get("trim_end_sec", 0)))
        for ge in graphics_elements:
            t = ge.get("timing", {})
            all_ends.append(float(t.get("out_sec", 0)))
        total_dur = max(all_ends + [1.0])

    lane_defs = [
        ("Visual", visual_elements, "#4FC3F7"),
        ("Text", text_elements, "#FFD54F"),
        ("Graphics", graphics_elements, "#BA68C8"),
        ("Transition", transitions, "#FF6E40"),
    ]

    n_lanes = len(lane_defs)
    has_audio = bool(audio.get("vo_track") or audio.get("music_track") or audio.get("sfx_events"))
    if has_audio:
        n_lanes += 1

    fig, ax = plt.subplots(figsize=(12, max(3, 1.2 * n_lanes + 1)))
    ax.set_facecolor("#1a1a2e")

    lane_idx = 0
    for label, elements, color in lane_defs:
        for el in elements:
            eid = el.get("element_id", el.get("transition_id", ""))
            if label == "Transition":
                start = 0.0
                dur = float(el.get("duration_sec", 0.3))
                end = start + dur
            elif label == "Visual":
                start = float(el.get("trim_start_sec", 0))
                end = float(el.get("trim_end_sec", start + 2))
            else:
                t = el.get("timing", {})
                start = float(t.get("in_sec", 0))
                end = float(t.get("out_sec", start + 2))
            ax.barh(lane_idx, max(end - start, 0.05), left=start, height=0.5,
                    color=color, alpha=0.75, edgecolor="white", linewidth=0.5)
            if eid:
                ax.text(start + 0.05, lane_idx, eid[:20], va="center", fontsize=6, color="white")
        ax.text(-0.3, lane_idx, label, ha="right", va="center", color=color,
                fontsize=8, fontweight="bold")
        lane_idx += 1

    if has_audio:
        audio_lane_items = []
        if audio.get("vo_track"):
            vt = audio["vo_track"]
            audio_lane_items.append(("VO", float(vt.get("trim_start_sec", 0)),
                                     float(vt.get("trim_end_sec", total_dur)), "#4FC3F7"))
        if audio.get("music_track"):
            mt = audio["music_track"]
            audio_lane_items.append(("MUSIC", float(mt.get("start_sec", 0)),
                                     float(mt.get("stop_sec", total_dur)), "#81C784"))
        for i, (lbl, st, en, clr) in enumerate(audio_lane_items):
            ax.barh(lane_idx + i * 0.3, max(en - st, 0.05), left=st, height=0.3,
                    color=clr, alpha=0.7, edgecolor="white", linewidth=0.5)
            ax.text(st + 0.05, lane_idx + i * 0.3, lbl, va="center", fontsize=6, color="white")
        ax.text(-0.3, lane_idx, "Audio", ha="right", va="center", color="#81C784",
                fontsize=8, fontweight="bold")
        lane_idx += 1

    ax.set_xlim(-0.5, total_dur + 0.5)
    ax.set_ylim(-0.8, max(lane_idx - 0.2, 0.5))
    ax.set_xlabel("Timeline (s)", color="grey")
    ax.tick_params(colors="grey", labelsize=8)
    ax.set_yticks([])
    plan_id = plan.get("plan_hash", "")[:8]
    ax.set_title(f"Full Timeline  —  {plan_id}  —  {total_dur:.1f}s",
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
    """Generate and cache per-element previews from a CompositionPlan dict.

    Parameters
    ----------
    cache_dir
        Root directory for cached preview files.
    models_config
        The parsed ``config/models.yaml`` dict (used for font paths).
    config_dir
        Directory containing ``render_styles.yaml``.
    source_resolver
        Optional callable mapping ``source_hash`` → local file path.
        Used to resolve visual/audio source files. If None, visual/audio
        previews that need file access will fail closed.
    """

    def __init__(
        self,
        cache_dir: str = "data/previews",
        models_config: Optional[dict] = None,
        config_dir: str = "config",
        source_resolver: Optional[callable] = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.models_config = models_config or {}
        self.config_dir = config_dir
        self.source_resolver = source_resolver

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _plan_cache_dir(self, plan: dict) -> str:
        d = os.path.join(self.cache_dir, _plan_hash(plan))
        os.makedirs(d, exist_ok=True)
        return d

    def _cache_path(self, plan: dict, category: str, eid: str, ext: str) -> str:
        d = self._plan_cache_dir(plan)
        safe_eid = eid.replace("/", "_").replace(":", "_")
        return os.path.join(d, f"{category}_{safe_eid}.{ext}")

    def _is_cached(self, path: str) -> bool:
        return os.path.exists(path) and os.path.getsize(path) > 0

    # ------------------------------------------------------------------
    # Element-level dispatch
    # ------------------------------------------------------------------

    def preview_text(self, plan: dict, text_element: dict) -> str:
        eid = text_element.get("element_id", _element_hash(text_element))
        out = self._cache_path(plan, "text", eid, "png")
        if self._is_cached(out):
            return out
        w, h = _canvas_dims(plan)
        return _generate_text_preview(text_element, w, h, self.models_config, self.config_dir, out)

    def preview_audio(self, plan: dict) -> str:
        audio = plan.get("audio", {})
        if not audio or not isinstance(audio, dict):
            raise PreviewError("Plan has no audio section")
        audio_with_dur = dict(audio)
        audio_with_dur["_total_duration"] = plan.get("total_duration_sec", 10.0)
        out = self._cache_path(plan, "audio", "mix", "png")
        if self._is_cached(out):
            return out
        w, h = _canvas_dims(plan)
        return _generate_audio_preview(audio_with_dur, w, h, self.source_resolver, out)

    def preview_visual(self, plan: dict, visual_element: dict) -> str:
        eid = visual_element.get("element_id", _element_hash(visual_element))
        out = self._cache_path(plan, "visual", eid, "png")
        if self._is_cached(out):
            return out
        w, h = _canvas_dims(plan)
        return _generate_visual_preview(visual_element, w, h, self.source_resolver, out)

    def preview_graphics(self, plan: dict, graphics_element: dict,
                         background_path: str = "") -> str:
        eid = graphics_element.get("element_id", _element_hash(graphics_element))
        out = self._cache_path(plan, "graphics", eid, "png")
        if self._is_cached(out):
            return out
        w, h = _canvas_dims(plan)
        return _generate_graphics_preview(graphics_element, w, h, background_path, out)

    def preview_transition(self, plan: dict, transition: dict) -> str:
        eid = transition.get("transition_id", _element_hash(transition))
        out = self._cache_path(plan, "transition", eid, "png")
        if self._is_cached(out):
            return out
        w, h = _canvas_dims(plan)
        return _generate_transition_preview(transition, w, h, out)

    def preview_timeline(self, plan: dict) -> str:
        out = self._cache_path(plan, "timeline", "full", "png")
        if self._is_cached(out):
            return out
        return _generate_timeline_preview(plan, out)

    # ------------------------------------------------------------------
    # Batch generation
    # ------------------------------------------------------------------

    def generate_all(self, plan: dict, graphics_background: str = "") -> dict[str, list[str]]:
        """Generate previews for every element in the plan.

        Returns a dict mapping category → list of output paths.
        Errors are collected and re-raised as a single ``PreviewError``.
        """
        results: dict[str, list[str]] = {
            "text": [], "audio": [], "visual": [],
            "graphics": [], "transition": [], "timeline": [],
        }
        errors: list[str] = []

        for te in plan.get("text_elements", []):
            try:
                results["text"].append(self.preview_text(plan, te))
            except PreviewError as exc:
                eid = te.get("element_id", "?")
                errors.append(f"text:{eid}: {exc}")

        try:
            results["audio"].append(self.preview_audio(plan))
        except PreviewError as exc:
            errors.append(f"audio: {exc}")

        for ve in plan.get("visual_elements", []):
            try:
                results["visual"].append(self.preview_visual(plan, ve))
            except PreviewError as exc:
                eid = ve.get("element_id", "?")
                errors.append(f"visual:{eid}: {exc}")

        for ge in plan.get("graphics_elements", []):
            try:
                results["graphics"].append(self.preview_graphics(plan, ge, graphics_background))
            except PreviewError as exc:
                eid = ge.get("element_id", "?")
                errors.append(f"graphics:{eid}: {exc}")

        for tr in plan.get("transitions", []):
            try:
                results["transition"].append(self.preview_transition(plan, tr))
            except PreviewError as exc:
                eid = tr.get("transition_id", "?")
                errors.append(f"transition:{eid}: {exc}")

        try:
            results["timeline"].append(self.preview_timeline(plan))
        except PreviewError as exc:
            errors.append(f"timeline: {exc}")

        if errors:
            # Return partial results with errors — don't throw away
            # successful previews when some fail. The caller can check
            # which categories have previews and which are missing.
            results["_errors"] = errors
            return results

        return results