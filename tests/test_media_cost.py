"""
Tests for media cost computation (T11.3 cost surfacing).
Verifies that costs are computed from config when APIs return 0.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from media_adapter import MediaAdapter


@pytest.fixture
def adapter(tmp_path):
    """Create a MediaAdapter with test config."""
    models_config = {
        "media": {
            "image_generators": [
                {
                    "name": "flux2-pro",
                    "provider": "fal",
                    "endpoint": "fal-ai/flux-2-pro",
                    "cost_per_image_usd": 0.03,
                },
                {
                    "name": "nano-banana-2",
                    "provider": "fal",
                    "endpoint": "fal-ai/gemini-3.1-flash-image-preview",
                    "cost_per_image_usd": 0.039,
                },
            ],
            "video_generators": [
                {
                    "name": "kling-3",
                    "provider": "fal",
                    "endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
                    "cost_per_second_usd": 0.10,
                },
                {
                    "name": "veo-3.1-fast",
                    "provider": "fal",
                    "endpoint": "fal-ai/veo3.1/fast/image-to-video",
                    "cost_per_second_usd": 0.15,
                },
            ],
        }
    }
    return MediaAdapter(models_config, db_path=str(tmp_path / "test_media.db"))


class TestComputeCost:
    def test_image_cost_by_name(self, adapter):
        """Computes image cost from config by generator name."""
        assert adapter._compute_cost("flux2-pro", "image") == 0.03
        assert adapter._compute_cost("nano-banana-2", "image") == 0.039

    def test_image_cost_by_endpoint(self, adapter):
        """Computes image cost from config by endpoint."""
        assert adapter._compute_cost("fal-ai/flux-2-pro", "image") == 0.03

    def test_video_cost_by_name(self, adapter):
        """Computes video cost from config: rate × duration."""
        assert adapter._compute_cost("kling-3", "video", duration_seconds=5) == 0.50
        assert adapter._compute_cost("kling-3", "video", duration_seconds=10) == 1.00
        assert adapter._compute_cost("veo-3.1-fast", "video", duration_seconds=5) == 0.75

    def test_video_cost_by_endpoint(self, adapter):
        """Computes video cost from config by endpoint."""
        cost = adapter._compute_cost("fal-ai/kling-video/v3/standard/image-to-video", "video", duration_seconds=5)
        assert cost == 0.50

    def test_unknown_model_returns_zero(self, adapter):
        """Unknown model returns 0 cost."""
        assert adapter._compute_cost("unknown-model", "image") == 0
        assert adapter._compute_cost("unknown-model", "video", duration_seconds=5) == 0

    def test_unknown_kind_returns_zero(self, adapter):
        """Unknown kind returns 0 cost."""
        assert adapter._compute_cost("flux2-pro", "audio") == 0

    def test_default_duration_5s(self, adapter):
        """Video cost defaults to 5 seconds if duration not specified."""
        assert adapter._compute_cost("kling-3", "video") == 0.50