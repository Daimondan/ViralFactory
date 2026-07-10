"""Tests for VO generation module.

Tests cover:
- VO line extraction from script content
- Gemini TTS API call (mocked)
- WAV file creation
- DB recording
- Provenance logging
- Integration with render flow
"""

import json
import os
import subprocess
import sqlite3
import sys
import wave
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from vo_generator import VOGenerator, VOGenerationError


class TestVOLineExtraction:
    """Test extraction of VO lines from script content."""

    def test_extracts_vo_lines(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        text = '[FRAME 1]\nVO: "Your grandmother kept cash in a biscuit tin"\n[FRAME 2]\nVO: "Growing up, saving meant one thing"'
        result = gen._extract_vo_lines(text)
        assert "Your grandmother kept cash" in result
        assert "Growing up, saving" in result

    def test_extracts_voiceover(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        text = 'Voiceover: The compound interest gap.'
        result = gen._extract_vo_lines(text)
        assert "compound interest gap" in result

    def test_extracts_narrator(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        text = 'Narrator: Love is the entry point.'
        result = gen._extract_vo_lines(text)
        assert "Love is the entry point" in result

    def test_no_vo_returns_empty(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        assert gen._extract_vo_lines("A carousel about money. No audio.") == ""

    def test_extracts_from_posts(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        posts = json.dumps([
            '[FRAME 1]\nVO: "Your grandmother kept cash"',
            '[FRAME 2]\nVO: "Growing up, saving meant one thing"',
        ])
        result = gen._extract_vo_lines("Reel about biscuit tins", posts)
        assert "Your grandmother" in result
        assert "Growing up" in result

    def test_empty_content(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        assert gen._extract_vo_lines("") == ""
        assert gen._extract_vo_lines(None) == ""


class TestGeminiTTSCall:
    """Test the Gemini TTS API call (mocked)."""

    def test_tts_call_returns_audio(self, tmp_path, monkeypatch):
        """Mocked Gemini TTS should return PCM bytes."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))

        # Create fake PCM data (1 second of silence at 24kHz, 16-bit mono)
        fake_pcm = b"\x00\x00" * 24000

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "data": __import__("base64").b64encode(fake_pcm).decode()
                        }
                    }]
                }
            }]
        }

        with patch("requests.post", return_value=mock_response):
            pcm = gen._call_gemini_tts(
                "Hello world", "Kore", "warm", "gemini-3.1-flash-tts-preview", "fake-key"
            )

        assert len(pcm) > 0
        assert pcm == fake_pcm

    def test_tts_api_error_raises(self, tmp_path, monkeypatch):
        """API error should raise VOGenerationError."""
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "bad request"}'

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(VOGenerationError) as exc:
                gen._call_gemini_tts("test", "Kore", "warm", "model", "key")
            assert "400" in str(exc.value)


class TestWAVSave:
    """Test WAV file creation."""

    def test_save_wav_creates_valid_file(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        fake_pcm = b"\x00\x00" * 2400  # 0.1s of silence at 24kHz
        wav_path = str(tmp_path / "test.wav")
        gen._save_wav(fake_pcm, wav_path, 24000)

        assert os.path.exists(wav_path)
        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getframerate() == 24000
            assert wf.getsampwidth() == 2


class TestGenerateVO:
    """Test the full generate_vo flow with mocked API."""

    def test_generate_vo_success(self, tmp_path, monkeypatch):
        """Full VO generation should create file, record in DB, log provenance."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        config = {
            "voice_cloning": {
                "tts": {
                    "model": "gemini-3.1-flash-tts-preview",
                    "voice": "Kore",
                    "style": "warm Caribbean English",
                    "api_key_env": "GEMINI_API_KEY",
                }
            }
        }
        gen = VOGenerator(config, db_path=str(tmp_path / "test.db"))

        # Set up asset_media table
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER, kind TEXT, path TEXT,
                model TEXT, prompt TEXT, cost_usd REAL, created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        fake_pcm = b"\x00\x00" * 24000  # 1s of audio

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "data": __import__("base64").b64encode(fake_pcm).decode()
                        }
                    }]
                }
            }]
        }

        content = "Reel about biscuit tins"
        posts = json.dumps(['[FRAME 1]\nVO: "Your grandmother kept cash in a biscuit tin"'])

        # Use a unique asset ID and clean up after
        asset_id = 77777
        with patch("requests.post", return_value=mock_response):
            result = gen.generate_vo(
                asset_id=asset_id, content=content, posts=posts,
                business_slug="test", take_id="test_take",
            )

        assert os.path.exists(result["path"])
        assert result["take_id"] == "test_take"
        assert "Your grandmother" in result["vo_text"]

        # Verify in DB
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        row = conn.execute(
            "SELECT * FROM asset_media WHERE kind = 'vo' AND asset_id = ?",
            (asset_id,),
        ).fetchone()
        conn.close()
        assert row is not None

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", str(asset_id)), ignore_errors=True)

    def test_generate_vo_no_vo_lines_raises(self, tmp_path, monkeypatch):
        """Should raise if no VO lines in content."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))

        with pytest.raises(VOGenerationError) as exc:
            gen.generate_vo(asset_id=1, content="No VO here", posts="[]")
        assert "No VO lines" in str(exc.value)

    def test_generate_vo_no_api_key_raises(self, tmp_path, monkeypatch):
        """Should raise if API key not set."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))

        with pytest.raises(VOGenerationError) as exc:
            gen.generate_vo(
                asset_id=1,
                content='VO: "test"',
                take_id="t1",
            )
        assert "GEMINI_API_KEY" in str(exc.value)

    def test_provenance_logged(self, tmp_path, monkeypatch):
        """VO generation should log to provenance."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        config = {"voice_cloning": {"tts": {"api_key_env": "GEMINI_API_KEY"}}}
        gen = VOGenerator(config, db_path=str(tmp_path / "test.db"))

        # Create asset_media table
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS asset_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER, kind TEXT, path TEXT,
                model TEXT, prompt TEXT, cost_usd REAL, created_at TEXT
            )
        """)
        conn.commit()
        conn.close()

        fake_pcm = b"\x00\x00" * 2400
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{
                "content": {"parts": [{"inlineData": {"data": __import__("base64").b64encode(fake_pcm).decode()}}]}
            }]
        }

        with patch("requests.post", return_value=mock_response):
            gen.generate_vo(
                asset_id=77778, content='VO: "test"', business_slug="test",
                take_id="t1",
            )

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", "77778"), ignore_errors=True)

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%VO generated%'"
        ).fetchall()
        conn.close()
        assert len(rows) > 0


class TestHasVOForAsset:
    """Test checking for existing VO files."""

    def test_returns_none_when_no_vo(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        assert gen.has_vo_for_asset(999) is None

    def test_returns_path_when_vo_exists(self, tmp_path):
        gen = VOGenerator({}, db_path=str(tmp_path / "test.db"))
        media_dir = os.path.join("data", "media", "998")
        os.makedirs(media_dir, exist_ok=True)
        vo_path = os.path.join(media_dir, "vo_take_1.wav")
        with open(vo_path, "w") as f:
            f.write("fake")

        result = gen.has_vo_for_asset(998)
        assert result is not None
        assert "vo_take_1.wav" in result

        # Cleanup
        import shutil
        shutil.rmtree(media_dir, ignore_errors=True)