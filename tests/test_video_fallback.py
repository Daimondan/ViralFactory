"""Test video generator fallback: when a generator's API key is missing,
the system automatically falls back to the next available generator."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import (
    _resolve_ai_video_generator,
    _resolve_ai_video_generator_with_fallback,
    _find_available_video_generator,
)

MEDIA_CONFIG = {
    "video_generators": [
        {
            "name": "grok-imagine-video",
            "provider": "xai",
            "model": "grok-imagine-video",
            "api_key_env": "XAI_API_KEY",
        },
        {
            "name": "veo",
            "provider": "google",
            "model": "veo-3.1-fast-generate-preview",
            "api_key_env": "GOOGLE_API_KEY",
        },
        {
            "name": "sora",
            "provider": "openai",
            "model": "sora",
            "api_key_env": "OPENAI_API_KEY",
        },
    ],
    "video_default": "grok-imagine-video",
    "video_provider": "xai",
}


class TestFindAvailableVideoGenerator:
    """Test the helper that scans for the first generator with a key set."""

    def test_returns_first_available(self, monkeypatch):
        """Google key is set → returns Veo even though xAI is first in list."""
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = _find_available_video_generator(MEDIA_CONFIG)
        assert result is not None
        assert result["name"] == "veo"
        assert result["provider"] == "google"

    def test_returns_none_when_no_keys(self, monkeypatch):
        """No API keys set → returns None."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = _find_available_video_generator(MEDIA_CONFIG)
        assert result is None

    def test_exclude_name(self, monkeypatch):
        """Exclude a specific generator from the search."""
        monkeypatch.setenv("XAI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _find_available_video_generator(MEDIA_CONFIG, exclude_name="grok-imagine-video")
        assert result is not None
        assert result["name"] == "veo"


class TestResolveWithFallback:
    """Test the full resolve-with-fallback path."""

    def test_no_fallback_when_key_set(self, monkeypatch):
        """xAI key IS set → no fallback, returns xAI generator."""
        monkeypatch.setenv("XAI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video:grok-imagine-video", MEDIA_CONFIG)
        assert result["name"] == "grok-imagine-video"
        assert result["provider"] == "xai"
        assert result["fell_back"] is False

    def test_falls_back_when_key_missing(self, monkeypatch):
        """xAI key NOT set, Google key IS → falls back to Veo."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video:grok-imagine-video", MEDIA_CONFIG)
        assert result["name"] == "veo"
        assert result["provider"] == "google"
        assert result["fell_back"] is True

    def test_falls_back_past_multiple_missing(self, monkeypatch):
        """xAI + OpenAI keys NOT set, only Google → falls back to Veo."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video:sora", MEDIA_CONFIG)
        assert result["name"] == "veo"
        assert result["provider"] == "google"
        assert result["fell_back"] is True

    def test_no_fallback_available(self, monkeypatch):
        """No keys set at all → no fallback, returns the requested generator."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        result = _resolve_ai_video_generator_with_fallback("ai_video:grok-imagine-video", MEDIA_CONFIG)
        assert result["name"] == "grok-imagine-video"
        assert result["provider"] == "xai"
        assert result["fell_back"] is False

    def test_bare_ai_video_falls_back(self, monkeypatch):
        """Bare 'ai_video' (no model name) with xAI missing → falls back."""
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video", MEDIA_CONFIG)
        assert result["name"] == "veo"
        assert result["provider"] == "google"
        assert result["fell_back"] is True

    def test_bare_ai_video_no_fallback_when_key_set(self, monkeypatch):
        """Bare 'ai_video' with xAI key set → uses legacy default (xAI)."""
        monkeypatch.setenv("XAI_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video", MEDIA_CONFIG)
        assert result["fell_back"] is False

    def test_unknown_generator_raises(self):
        """Unknown generator name still raises ValueError — fallback doesn't hide config errors."""
        with pytest.raises(ValueError, match="Unknown AI video generator"):
            _resolve_ai_video_generator_with_fallback("ai_video:nonexistent", MEDIA_CONFIG)