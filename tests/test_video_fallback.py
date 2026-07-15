"""Test video generator fallback: when a generator's API key is missing,
the system automatically falls back to the next available generator.

T11.1: Sora removed (API discontinued 2026-09-24). fal providers (kling-3,
veo-3.1-fast) are the new default path. Legacy grok/veo remain as named backends.
"""
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
            "name": "kling-3",
            "provider": "fal",
            "endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
            "api_key_env": "FAL_API_KEY",
            "cost_per_second_usd": 0.10,
        },
        {
            "name": "veo-3.1-fast",
            "provider": "fal",
            "endpoint": "fal-ai/veo3.1/fast/image-to-video",
            "api_key_env": "FAL_API_KEY",
            "cost_per_second_usd": 0.15,
        },
        {
            "name": "veo",
            "provider": "google",
            "model": "veo-3.1-fast-generate-preview",
            "api_key_env": "GOOGLE_API_KEY",
        },
        {
            "name": "grok-imagine-video",
            "provider": "xai",
            "model": "grok-imagine-video",
            "api_key_env": "XAI_API_KEY",
        },
    ],
    "video_default": "kling-3",
    "video_provider": "fal",
}


class TestFindAvailableVideoGenerator:
    """Test the helper that scans for the first generator with a key set."""

    def test_returns_first_available(self, monkeypatch):
        """FAL key is set → returns kling-3 (first in list)."""
        monkeypatch.setenv("FAL_API_KEY", "test-key")
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        result = _find_available_video_generator(MEDIA_CONFIG)
        assert result is not None
        assert result["name"] == "kling-3"
        assert result["provider"] == "fal"

    def test_returns_google_when_fal_missing(self, monkeypatch):
        """FAL key NOT set, Google key IS → returns Veo (legacy)."""
        monkeypatch.delenv("FAL_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
        monkeypatch.delenv("XAI_API_KEY", raising=False)

        result = _find_available_video_generator(MEDIA_CONFIG)
        assert result is not None
        assert result["name"] == "veo"
        assert result["provider"] == "google"

    def test_returns_none_when_no_keys(self, monkeypatch):
        """No API keys set → returns None."""
        monkeypatch.delenv("FAL_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        result = _find_available_video_generator(MEDIA_CONFIG)
        assert result is None

    def test_exclude_name(self, monkeypatch):
        """Exclude a specific generator from the search."""
        monkeypatch.setenv("FAL_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _find_available_video_generator(MEDIA_CONFIG, exclude_name="kling-3")
        assert result is not None
        assert result["name"] == "veo-3.1-fast"


class TestResolveWithFallback:
    """Test the full resolve-with-fallback path."""

    def test_no_fallback_when_key_set(self, monkeypatch):
        """FAL key IS set → no fallback, returns kling-3."""
        monkeypatch.setenv("FAL_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video:kling-3", MEDIA_CONFIG)
        assert result["name"] == "kling-3"
        assert result["provider"] == "fal"
        assert result["fell_back"] is False

    def test_falls_back_when_key_missing(self, monkeypatch):
        """FAL key NOT set, Google key IS → falls back to Veo (legacy)."""
        monkeypatch.delenv("FAL_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video:kling-3", MEDIA_CONFIG)
        assert result["name"] == "veo"
        assert result["provider"] == "google"
        assert result["fell_back"] is True

    def test_falls_back_past_multiple_missing(self, monkeypatch):
        """FAL + xAI keys NOT set, only Google → falls back to Veo."""
        monkeypatch.delenv("FAL_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video:veo-3.1-fast", MEDIA_CONFIG)
        assert result["name"] == "veo"
        assert result["provider"] == "google"
        assert result["fell_back"] is True

    def test_no_fallback_available(self, monkeypatch):
        """No keys set at all → no fallback, returns the requested generator."""
        monkeypatch.delenv("FAL_API_KEY", raising=False)
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        result = _resolve_ai_video_generator_with_fallback("ai_video:kling-3", MEDIA_CONFIG)
        assert result["name"] == "kling-3"
        assert result["provider"] == "fal"
        assert result["fell_back"] is False

    def test_bare_ai_video_falls_back(self, monkeypatch):
        """Bare 'ai_video' (no model name) with FAL missing → falls back."""
        monkeypatch.delenv("FAL_API_KEY", raising=False)
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video", MEDIA_CONFIG)
        assert result["name"] == "veo"
        assert result["provider"] == "google"
        assert result["fell_back"] is True

    def test_bare_ai_video_no_fallback_when_key_set(self, monkeypatch):
        """Bare 'ai_video' with FAL key set → uses default (kling-3)."""
        monkeypatch.setenv("FAL_API_KEY", "test-key")
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        result = _resolve_ai_video_generator_with_fallback("ai_video", MEDIA_CONFIG)
        assert result["fell_back"] is False

    def test_unknown_generator_raises(self):
        """Unknown generator name still raises ValueError — fallback doesn't hide config errors."""
        with pytest.raises(ValueError, match="Unknown AI video generator"):
            _resolve_ai_video_generator_with_fallback("ai_video:nonexistent", MEDIA_CONFIG)

    def test_no_sora_in_config(self):
        """T11.1 AC: no 'sora' reference anywhere in the test config."""
        config_str = str(MEDIA_CONFIG)
        assert "sora" not in config_str.lower(), "Sora should be retired from all config"