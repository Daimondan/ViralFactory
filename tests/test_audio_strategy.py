"""Tests for AUDIO-1: plan-audio-block-driven audio mixing.

Per CORRECTION-final-output-review-and-audio-fix-v1.0:
- original_audio == false, no music → silent video
- original_audio == true, no music  → keep concat audio (loudnorm only)
- music stock_ref present           → mix music at specified volume
- vo take_id present                → duck under VO (deferred: graceful if no VO file)
- The old looping audio bed heuristic is removed.
"""

import json
import os
import subprocess
import sqlite3
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from assembly import AssemblyRenderer, AssemblyError


def _make_video(path, duration=2, with_audio=True, size="320x240"):
    """Create a test video file via ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=30",
    ]
    if with_audio:
        cmd.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"])
        cmd.extend([
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", path,
        ])
    else:
        cmd.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p", path])
    subprocess.run(cmd, capture_output=True, timeout=30)
    return path


def _make_audio(path, duration=3):
    """Create a test audio file."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=300:duration={duration}",
         "-c:a", "aac", path],
        capture_output=True, timeout=30,
    )
    return path


def _make_image(path):
    """Create a test image."""
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=red:s=320x240:d=1",
         "-frames:v", "1", path],
        capture_output=True, timeout=30,
    )
    return path


class TestAudioStrategySelection:
    """Test that the audio strategy is correctly derived from the plan's audio block."""

    def test_silent_when_no_audio_block(self, tmp_path):
        """No audio block → silent strategy."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        strategy = renderer._resolve_audio_strategy({"original_audio": False})
        assert strategy == "silent"

    def test_silent_when_original_audio_false_no_music(self, tmp_path):
        """original_audio=false, no music → silent."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        strategy = renderer._resolve_audio_strategy({
            "original_audio": False,
            "music": {},
            "vo": {},
        })
        assert strategy == "silent"

    def test_original_when_original_audio_true_no_music(self, tmp_path):
        """original_audio=true, no music → original."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        strategy = renderer._resolve_audio_strategy({
            "original_audio": True,
            "music": {},
            "vo": {},
        })
        assert strategy == "original"

    def test_music_when_music_ref_present(self, tmp_path):
        """music.stock_ref present → music strategy."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        strategy = renderer._resolve_audio_strategy({
            "original_audio": False,
            "music": {"stock_ref": "stock:123", "volume": 0.3},
            "vo": {},
        })
        assert strategy == "music"

    def test_vo_deferred_when_no_vo_file(self, tmp_path):
        """vo.take_id present but no VO file → degrades to next strategy."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        # VO file doesn't exist → should fall back
        strategy = renderer._resolve_audio_strategy({
            "original_audio": False,
            "music": {},
            "vo": {"take_id": "take_1", "ducking": True},
        }, asset_id=99999)
        # No VO file, no music, original_audio=false → silent
        assert strategy == "silent"

    def test_vo_deferred_falls_back_to_music(self, tmp_path):
        """vo.take_id present but no file, music ref present → music strategy."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        strategy = renderer._resolve_audio_strategy({
            "original_audio": False,
            "music": {"stock_ref": "stock:123", "volume": 0.3},
            "vo": {"take_id": "take_1", "ducking": True},
        }, asset_id=99999)
        assert strategy == "music"


class TestSilentAudio:
    """Test that silent strategy produces a silent audio track."""

    def test_silent_video_has_audio_stream(self, tmp_path):
        """A video with no audio should get a silent AAC track added."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "no_audio.mp4"), with_audio=False)
        assert not renderer._has_audio_stream(video)

        # Apply silent audio strategy
        renderer._apply_silent_audio(video, str(tmp_path), 1)

        assert renderer._has_audio_stream(video), "Silent audio track was not added"

    def test_silent_video_audio_is_silent(self, tmp_path):
        """The added audio track should be actually silent (not just present)."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        video = _make_video(str(tmp_path / "no_audio.mp4"), with_audio=False)
        renderer._apply_silent_audio(video, str(tmp_path), 1)

        # Extract audio and check volume
        audio_extract = str(tmp_path / "check.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1", "-ar", "16000",
             audio_extract],
            capture_output=True, timeout=30,
        )
        # Use volumedetect
        result = subprocess.run(
            ["ffmpeg", "-i", audio_extract, "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        stderr = result.stderr
        # Silent audio should have mean_volume of -inf or very low
        assert "mean_volume" in stderr
        # Parse the mean_volume line
        for line in stderr.split("\n"):
            if "mean_volume" in line:
                # Should be -inf or very negative (silent)
                vol_str = line.split("mean_volume:")[1].strip()
                assert vol_str == "-inf" or float(vol_str.replace(" dB", "")) < -60, \
                    f"Audio is not silent: mean_volume={vol_str}"


class TestOriginalAudioPreserved:
    """Test that original_audio=true preserves segment source audio (no looping)."""

    def test_original_audio_no_looping(self, tmp_path):
        """Render with original_audio=true should NOT add a looping bed."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create a 2s video with audio
        video = _make_video(str(tmp_path / "clip.mp4"), duration=2, with_audio=True)
        # Create a 2s image
        image = _make_image(str(tmp_path / "img.png"))

        sources = [video, image]
        call_idx = [0]
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 2, "transition_in": "cut"},
                {"source": "generated:2", "in": 0, "out": 2, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
            "audio": {
                "original_audio": True,
                "music": {},
                "vo": {},
            },
        }

        os.makedirs(os.path.join("data", "media", "9971"), exist_ok=True)
        result = renderer.render(plan, asset_id=9971, draft_id=1)
        assert os.path.exists(result["path"])
        assert result["duration"] > 0

        # Check that the output has audio (from the video clip)
        assert renderer._has_audio_stream(result["path"]), \
            "Output should have audio stream when original_audio=true"

        # Verify audio is not looping: extract and check it's not repeating
        # the same pattern 3 times
        audio_check = str(tmp_path / "orig_check.wav")
        subprocess.run(
            ["ffmpeg", "-y", "-i", result["path"], "-vn", "-ac", "1",
             "-ar", "16000", audio_check],
            capture_output=True, timeout=30,
        )
        # Get duration of extracted audio
        dur_result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", audio_check],
            capture_output=True, text=True, timeout=30,
        )
        audio_dur = float(json.loads(dur_result.stdout).get("format", {}).get("duration", 0))
        # Should be ~4s (2s video + 2s image), not looped to longer
        assert 3.5 < audio_dur < 5.0, f"Audio duration {audio_dur}s suggests looping"

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", "9971"), ignore_errors=True)


class TestNoLoopingAudioBed:
    """Regression: the old audio bed heuristic must be gone."""

    def test_no_audio_bed_looping(self, tmp_path):
        """original_audio=false, no music → NO looping ambient sound."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Video with audio + images (the exact scenario that caused the bug)
        video = _make_video(str(tmp_path / "clip.mp4"), duration=6, with_audio=True)
        image = _make_image(str(tmp_path / "img.png"))

        sources = [video, image, image, image, image, image]
        call_idx = [0]
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3, "transition_in": "cut"},
                {"source": "generated:2", "in": 0, "out": 3, "transition_in": "cut"},
                {"source": "generated:3", "in": 0, "out": 3, "transition_in": "cut"},
                {"source": "generated:4", "in": 0, "out": 3, "transition_in": "cut"},
                {"source": "generated:5", "in": 0, "out": 3, "transition_in": "cut"},
                {"source": "generated:6", "in": 0, "out": 3, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
            "audio": {
                "original_audio": False,
                "music": {},
                "vo": {},
            },
        }

        os.makedirs(os.path.join("data", "media", "9972"), exist_ok=True)
        result = renderer.render(plan, asset_id=9972, draft_id=1)
        assert os.path.exists(result["path"])

        # The audio should be silent — check volume at multiple timestamps
        for t in [2, 6, 10, 15]:
            audio_extract = str(tmp_path / f"check_t{t}.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(t), "-i", result["path"],
                 "-t", "1", "-vn", "-ac", "1", "-ar", "16000", audio_extract],
                capture_output=True, timeout=30,
            )
            if not os.path.exists(audio_extract):
                continue
            vol_result = subprocess.run(
                ["ffmpeg", "-i", audio_extract, "-af", "volumedetect",
                 "-f", "null", "-"],
                capture_output=True, text=True, timeout=30,
            )
            for line in vol_result.stderr.split("\n"):
                if "mean_volume" in line:
                    vol_str = line.split("mean_volume:")[1].strip()
                    assert vol_str == "-inf" or float(vol_str.replace(" dB", "")) < -50, \
                        f"Audio at t={t}s is not silent: mean_volume={vol_str} — looping bed still present?"

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", "9972"), ignore_errors=True)


class TestProvenanceLogAudioStrategy:
    """Test that audio strategy is logged to provenance."""

    def test_audio_strategy_logged(self, tmp_path):
        """The render provenance should log the audio strategy decision."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        video = _make_video(str(tmp_path / "clip.mp4"), duration=2, with_audio=True)
        image = _make_image(str(tmp_path / "img.png"))

        sources = [video, image]
        call_idx = [0]
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 2, "transition_in": "cut"},
                {"source": "generated:2", "in": 0, "out": 2, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
            "audio": {"original_audio": False, "music": {}, "vo": {}},
        }

        os.makedirs(os.path.join("data", "media", "9973"), exist_ok=True)
        renderer.render(plan, asset_id=9973, draft_id=1)

        # Check provenance log for audio strategy entry
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%audio strategy%'",
        ).fetchall()
        conn.close()

        assert len(rows) > 0, "Audio strategy not logged to provenance"
        assert "silent" in rows[0][0] or "original" in rows[0][0] or "music" in rows[0][0]

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", "9973"), ignore_errors=True)


class TestMusicMixing:
    """Test music-only and music+original strategies."""

    def test_music_only_replaces_audio(self, tmp_path):
        """music stock_ref present, original_audio=false → music replaces audio."""
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Set up stock_cache with a music file
        music_file = _make_audio(str(tmp_path / "music.mp3"), duration=5)
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stock_cache (
                id INTEGER PRIMARY KEY,
                title TEXT,
                local_path TEXT,
                source TEXT,
                kind TEXT,
                created_at TEXT
            )
        """)
        conn.execute(
            "INSERT INTO stock_cache (id, title, local_path, source, kind, created_at) "
            "VALUES (123, 'Test Music', ?, 'pixabay', 'audio', '2026-01-01')",
            (music_file,),
        )
        conn.commit()
        conn.close()

        # Create a video with no audio (so we can verify music is added)
        video = _make_video(str(tmp_path / "no_audio.mp4"), duration=3, with_audio=False)
        image = _make_image(str(tmp_path / "img.png"))

        sources = [video, image]
        call_idx = [0]
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3, "transition_in": "cut"},
                {"source": "generated:2", "in": 0, "out": 3, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
            "audio": {
                "original_audio": False,
                "music": {"stock_ref": "stock:123", "volume": 0.3},
                "vo": {},
            },
        }

        os.makedirs(os.path.join("data", "media", "9974"), exist_ok=True)
        result = renderer.render(plan, asset_id=9974, draft_id=1)
        assert os.path.exists(result["path"])
        assert renderer._has_audio_stream(result["path"]), \
            "Music track should be present in output"

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", "9974"), ignore_errors=True)


class TestPromptVersion:
    """AUDIO-2: edit plan prompt must be v1.2 with audio strategy guidance."""

    def test_prompt_version_is_1_2(self):
        """Prompt version bumped to 1.2 per AUDIO-2."""
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "assembly", "edit_plan_v1.md"
        )
        with open(prompt_path) as f:
            content = f.read()
        import re
        m = re.search(r'<!-- version: ([\d.]+) -->', content)
        assert m, "No version tag in prompt"
        assert m.group(1) == "1.2", f"Expected v1.2, got v{m.group(1)}"

    def test_prompt_has_audio_strategy_section(self):
        """Prompt must contain audio strategy guidance."""
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "assembly", "edit_plan_v1.md"
        )
        with open(prompt_path) as f:
            content = f.read()
        assert "Audio Strategy" in content, "Audio Strategy section missing"
        assert "renderer will NOT invent audio" in content, "Key guidance missing"
        assert "original_audio" in content, "original_audio field guidance missing"
        assert "Silent is better" in content, "Silent > nonsense guidance missing"