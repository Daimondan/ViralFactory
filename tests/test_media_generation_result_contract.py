"""Regression tests for missing-media generation status handling."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import _resolve_ai_video_generator, _summarize_media_generation_results


def test_resolve_named_ai_video_generator_uses_configured_provider_and_model():
    media_config = {
        "video_generators": [
            {"name": "veo", "provider": "google", "model": "veo-3.1-fast-generate-preview"},
            {"name": "grok-imagine-video", "provider": "xai", "model": "grok-imagine-video"},
        ],
        "video_provider": "xai",
        "video_default": "grok-imagine-video",
    }

    resolved = _resolve_ai_video_generator("ai_video:veo", media_config)

    assert resolved["provider"] == "google"
    assert resolved["model"] == "veo-3.1-fast-generate-preview"
    assert resolved["name"] == "veo"


def test_resolve_unknown_named_ai_video_generator_does_not_silently_default():
    media_config = {"video_generators": []}

    try:
        _resolve_ai_video_generator("ai_video:veo", media_config)
    except ValueError as exc:
        assert "Unknown AI video generator 'veo'" in str(exc)
    else:
        raise AssertionError("unknown named generator should raise instead of falling back")


def test_media_generation_summary_only_renderable_ok_counts_as_ready():
    summary = _summarize_media_generation_results([
        {"status": "submitted"},
        {"status": "failed"},
    ])

    assert summary["available_count"] == 0
    assert summary["submitted_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["ready_to_render"] is False


def test_media_generation_summary_ready_when_renderable_media_exists():
    summary = _summarize_media_generation_results([
        {"status": "ok", "path": "data/media/1/clip.mp4"},
        {"status": "failed"},
    ])

    assert summary["available_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["ready_to_render"] is True


def test_assets_template_does_not_count_submitted_jobs_as_generated_media():
    template_path = os.path.join(os.path.dirname(__file__), "..", "src", "templates", "assets.html")
    source = open(template_path).read()

    assert "r.status === 'ok' || r.status === 'submitted'" not in source
    assert "video job" in source
    assert "not renderable yet" in source
    assert "Not ready to render yet" in source
