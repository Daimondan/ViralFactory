"""QA-loop F-005: render cut-off regression.

Asset 11 (Card 49) rendered at 36.9s while the approved VO is 39.4s.
Two compounding bugs:
  1. The xfade path applies a 0.5s fade to "cut" transitions, eating
     2.5s off the timeline whenever any segment has a crossfade.
  2. _mix_vo trims the VO to the (already too-short) video duration,
     silently discarding the last beat.

These tests fail first (RED), then pass after the fix (GREEN).
"""
import os
import json
import subprocess
import sys
import math
import sqlite3
import wave
import struct

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from assembly import AssemblyRenderer, AssemblyError


def _write_wav(path: str, duration_s: float, freq: float = 220.0):
    """Write a real WAV file with a tone so loudnorm has something to normalize."""
    sample_rate = 16000
    n_samples = int(duration_s * sample_rate)
    with wave.open(path, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        for i in range(n_samples):
            val = int(16000 * math.sin(2 * math.pi * freq * (i / sample_rate)))
            w.writeframes(struct.pack("<h", val))


def _write_image(path: str):
    """Write a tiny valid PNG via ffmpeg."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         "color=c=blue:s=1080x1920:d=1", "-frames:v", "1", path],
        capture_output=True, timeout=30, check=True,
    )


def _seed_asset_media(db_path: str, asset_id: int, media_dir: str, n: int):
    """Insert n image rows into asset_media pointing to real files in media_dir."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS asset_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            asset_id INTEGER, kind TEXT, path TEXT, model TEXT,
            prompt TEXT, cost_usd REAL, created_at TEXT,
            owner_type TEXT, beat_id TEXT, source_media_id INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS provenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, input_hash TEXT, prompt_file TEXT, prompt_version TEXT,
            model TEXT, provider TEXT, raw_output TEXT, validated_output TEXT,
            validator_verdict TEXT, validator_errors TEXT, context TEXT,
            temperature REAL, latency_ms INTEGER, cached INTEGER,
            business_slug TEXT, profile TEXT
        )"""
    )
    media_ids = []
    for i in range(n):
        p = os.path.abspath(os.path.join(media_dir, f"img_{i}.png"))
        _write_image(p)
        cur = conn.execute(
            """INSERT INTO asset_media (asset_id, kind, path, model, prompt, cost_usd, created_at)
               VALUES (?, 'image', ?, 'test', '', NULL, ?)""",
            (asset_id, p, "2026-01-01T00:00:00Z"),
        )
        media_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()
    return media_ids


def _make_plan(segments, vo_path, vo_duration):
    return {
        "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        "audio": {
            "original_audio": False,
            "vo": {
                "take_id": "take_test",
                "path": vo_path,
                "duration_sec": vo_duration,
                "ducking": True,
            },
            "music": {},
        },
        "segments": segments,
    }


def test_cut_and_crossfade_mix_does_not_lose_duration(tmp_path, monkeypatch):
    """A 6-segment plan (4 cuts + 1 crossfade + final cut) whose VO is
    6.0s must render to ~6.0s, not 3.5s. The old xfade path ate 0.5s per
    transition (5 × 0.5 = 2.5s) and trimmed the VO to match."""
    # The renderer writes to data/media/<asset_id> relative to cwd.
    monkeypatch.chdir(tmp_path)
    db_path = str(tmp_path / "test.db")
    media_dir = os.path.join(str(tmp_path), "data", "media", "1")
    os.makedirs(media_dir, exist_ok=True)
    media_ids = _seed_asset_media(db_path, 1, media_dir, 6)

    vo_path = os.path.join(media_dir, "vo_take_test.wav")
    _write_wav(vo_path, 6.0)

    transitions = ["cut", "cut", "crossfade", "cut", "cut"]
    segments = []
    for i, mid in enumerate(media_ids):
        seg = {"source": f"generated:{mid}", "in": 0, "out": 1.0,
               "overlays": [], "sfx": [], "beat_ids": [f"b0{i+1}"]}
        if i > 0:
            seg["transition_in"] = transitions[i - 1]
        segments.append(seg)

    plan = _make_plan(segments, vo_path, 6.0)

    renderer = AssemblyRenderer({}, db_path=db_path)
    result = renderer.render(plan, asset_id=1, draft_id=1, business_slug="test")
    final_path = result["path"]
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", final_path],
        capture_output=True, text=True, timeout=30,
    )
    rendered_dur = float(probe.stdout.strip())
    # VO is 6.0s; render must cover the full VO. Old bug produced ~3.5s.
    assert rendered_dur >= 5.7, (
        f"Render cut off: got {rendered_dur}s, expected ~6.0s. "
        f"VO last beat is being trimmed."
    )


def test_vo_not_trimmed_below_full_duration(tmp_path, monkeypatch):
    """When the concatenated video is shorter than the VO, _mix_vo must
    NOT trim the VO to the video duration. VO is the master timeline."""
    monkeypatch.chdir(tmp_path)
    db_path = str(tmp_path / "test.db")
    media_dir = os.path.join(str(tmp_path), "data", "media", "1")
    os.makedirs(media_dir, exist_ok=True)
    media_ids = _seed_asset_media(db_path, 1, media_dir, 1)

    vo_path = os.path.join(media_dir, "vo_take_test.wav")
    _write_wav(vo_path, 4.0)

    # Single image held 2s, but VO is 4s.
    segments = [{"source": f"generated:{media_ids[0]}", "in": 0, "out": 2.0,
                 "overlays": [], "sfx": [], "beat_ids": ["b01"]}]
    plan = _make_plan(segments, vo_path, 4.0)

    renderer = AssemblyRenderer({}, db_path=db_path)
    result = renderer.render(plan, asset_id=1, draft_id=1, business_slug="test")
    final_path = result["path"]
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", final_path],
        capture_output=True, text=True, timeout=30,
    )
    rendered_dur = float(probe.stdout.strip())
    # VO is 4.0s; output must be >= 4.0s (not trimmed to 2.0s).
    assert rendered_dur >= 3.8, (
        f"VO was trimmed to video duration: got {rendered_dur}s, "
        f"expected >= 4.0s. Master timeline (VO) was cut off."
    )