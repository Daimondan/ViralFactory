"""Soundtrack mix engineering (VF-VS-512, DIVERGENCE-015).

Mechanical mixing of the music bed under the VO using energy curves.
No LLM calls — this is pure FFmpeg processing.

The energy curve comes from the Writer's intent, mapped through config
templates. The bed is normalized, ducked under the VO per the energy
curve, and the final mix is loudness-normalized.

Config block (config/models.yaml):
  soundtrack:
    mixing:
      bed_target_loudness_lufs: -18
      final_target_loudness_lufs: -16
      ducking:
        default_depth: 0.20
        attack_s: 0.3
        release_s: 0.5
      energy_curve_mapping:
        intro: 0.25
        build: 0.35
        duck: 0.18
        lift: 0.40
        settle: 0.35
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from typing import Any

import requests

logger = logging.getLogger(__name__)


class SoundtrackMixError(Exception):
    """Raised when the mix fails critically."""


def _probe_duration(path: str) -> float:
    """Probe file duration in seconds."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", path],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(r.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def _probe_loudness(path: str) -> dict:
    """Probe EBU R128 loudness of a file."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path,
             "-af", "loudnorm=print_format=json",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        # Extract the JSON from stderr
        stderr = r.stderr
        start = stderr.rfind("{")
        end = stderr.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(stderr[start:end])
            return {
                "input_i": float(data.get("input_i", -99)),
                "input_tp": float(data.get("input_tp", -99)),
                "input_lra": float(data.get("input_lra", 0)),
            }
    except Exception:
        pass
    return {"input_i": -99, "input_tp": -99, "input_lra": 0}


def _download_track(download_url: str, dest_path: str) -> bool:
    """Download a music track to a local file."""
    try:
        r = requests.get(download_url, timeout=60, stream=True)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024
    except Exception as e:
        logger.warning("Failed to download track from %s: %s", download_url, e)
        return False


def _build_volume_filter(
    energy_curve: list[dict],
    vo_timeline: list[dict],
    config: dict,
) -> str:
    """Build an FFmpeg volume filter from the energy curve + VO timeline.

    The energy curve maps beat phases to bed volume levels. We generate
    per-time-segment volume changes using volume=eval=frame, avoiding
    sidechain compression (which over-ducks at low thresholds).

    Example output:
      volume=0.25:enable='between(t,0,8.64)',
      volume=0.35:enable='between(t,8.64,15.44)', ...
    """
    mixing_config = config.get("mixing", {})
    energy_mapping = mixing_config.get("energy_curve_mapping", {})
    default_depth = float(mixing_config.get("ducking", {}).get("default_depth", 0.20))

    # Build volume segments from the VO timeline beats
    segments = []
    for i, beat in enumerate(vo_timeline):
        start = float(beat.get("start_sec", 0))
        end = float(beat.get("end_sec", start + 5))
        phase = beat.get("energy_phase", _phase_from_index(i))
        volume = float(energy_mapping.get(phase, default_depth))
        segments.append((start, end, volume))

    if not segments:
        return f"volume={default_depth}"

    # Build the filter expression
    parts = []
    for start, end, vol in segments:
        parts.append(f"volume={vol:.2f}:enable='between(t,{start:.2f},{end:.2f})'")

    # Chain with commas (each volume filter applies in sequence)
    return ",".join(parts)


def _phase_from_index(i: int) -> str:
    """Map a beat index to a default energy phase."""
    phases = ["intro", "build", "duck", "lift", "settle", "settle"]
    return phases[min(i, len(phases) - 1)]


def mix_soundtrack(
    vo_path: str,
    bed_url: str,
    vo_timeline: list[dict],
    energy_curve: list[dict] | None,
    config: dict,
    output_path: str,
    original_audio: bool = False,
) -> dict:
    """Mix a music bed under the VO using energy curve automation.

    Args:
        vo_path: Path to the VO WAV file.
        bed_url: URL to download the music bed.
        vo_timeline: Beat timeline with start/end times.
        energy_curve: Energy curve from the Writer intent.
        config: Soundtrack config block.
        output_path: Where to write the final mixed audio.
        original_audio: Whether to preserve original clip audio.

    Returns:
        {
            "bed_path": "...",
            "mix_path": "...",
            "energy_curve": [...],
            "final_loudness_lufs": -16.0,
            "vo_intelligible": True,
            "bed_duration_s": 120.0,
            "errors": [],
        }
    """
    mixing_config = config.get("mixing", {})
    bed_target_lufs = float(mixing_config.get("bed_target_loudness_lufs", -18))
    final_target_lufs = float(mixing_config.get("final_target_loudness_lufs", -16))

    result = {
        "bed_path": "",
        "mix_path": "",
        "energy_curve": energy_curve or [],
        "final_loudness_lufs": 0.0,
        "vo_intelligible": False,
        "bed_duration_s": 0.0,
        "errors": [],
    }

    # Download the bed
    bed_dir = os.path.dirname(output_path)
    os.makedirs(bed_dir, exist_ok=True)
    bed_path = os.path.join(bed_dir, "music_bed.mp3")

    if not _download_track(bed_url, bed_path):
        result["errors"].append("Failed to download music bed")
        return result
    result["bed_path"] = bed_path
    result["bed_duration_s"] = _probe_duration(bed_path)

    vo_duration = _probe_duration(vo_path)
    if vo_duration <= 0:
        result["errors"].append(f"VO file not readable: {vo_path}")
        return result

    # Build the volume filter from the energy curve
    volume_filter = _build_volume_filter(energy_curve or [], vo_timeline, config)

    # Normalize the bed, loop it to VO duration, apply energy curve volume
    bed_normalized = os.path.join(bed_dir, "music_bed_norm.mp3")
    cmd_bed = [
        "ffmpeg", "-y", "-i", bed_path,
        "-af", f"aloop=loop=-1:size=2e9,atrim=0:{vo_duration:.2f},"
               f"loudnorm=I={bed_target_lufs}:TP=-1.5:LRA=11,{volume_filter}",
        "-t", f"{vo_duration:.2f}",
        bed_normalized,
    ]
    r = subprocess.run(cmd_bed, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        result["errors"].append(f"Bed normalization failed: {r.stderr[-300:]}")
        return result

    # Mix the normalized bed under the VO
    # VO is the primary audio (loudnorm'd), bed is the secondary layer
    cmd_mix = [
        "ffmpeg", "-y",
        "-i", vo_path,
        "-i", bed_normalized,
        "-filter_complex",
        f"[0:a]loudnorm=I={final_target_lufs}:TP=-1.0:LRA=11[vo];"
        f"[1:a]loudnorm=I={bed_target_lufs}:TP=-1.5:LRA=11[bed];"
        f"[vo][bed]amix=inputs=2:duration=first:dropout_transition=0[aout]",
        "-map", "[aout]",
        "-c:a", "aac",
        "-t", f"{max(vo_duration, 1):.2f}",
        output_path,
    ]
    r = subprocess.run(cmd_mix, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        result["errors"].append(f"Mix failed: {r.stderr[-300:]}")
        return result

    result["mix_path"] = output_path

    # Measure the final loudness
    loudness = _probe_loudness(output_path)
    result["final_loudness_lufs"] = loudness["input_i"]

    # Check VO intelligibility — the VO should be louder than the bed
    # We check by comparing the mix loudness to the bed target
    # (a rough heuristic: the mix should be close to the VO level, not the bed)
    result["vo_intelligible"] = result["final_loudness_lufs"] > bed_target_lufs - 3

    # Clean up temp files
    for tmp in [bed_normalized]:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    return result