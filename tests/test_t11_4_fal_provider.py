"""
Tests for T11.4: fal provider in MediaAdapter.

AC: one reference-conditioned image and one image-to-video clip generate
end-to-end with cost logged to provenance; zero hardcoded endpoints.

These tests use mocks (no real API calls) to verify the fal provider
integration works correctly:
- Image generation with reference images (fal)
- Image generation without reference images (fal, text-only)
- Video submission (image-to-video, fal)
- Fal job polling
- Cost computation from config
- Endpoints read from config only
- Provenance logging with provider="fal"
"""

import json
import os
import pytest
import sys
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def media_config():
    """Config with fal providers matching models.yaml."""
    return {
        "media": {
            "image_generators": [
                {
                    "name": "nano-banana-2",
                    "provider": "fal",
                    "endpoint": "fal-ai/gemini-3.1-flash-image-preview",
                    "api_key_env": "FAL_KEY",
                    "cost_per_image_usd": 0.039,
                    "supports_reference_images": True,
                },
                {
                    "name": "flux2-pro",
                    "provider": "fal",
                    "endpoint": "fal-ai/flux-2-pro",
                    "api_key_env": "FAL_KEY",
                    "cost_per_image_usd": 0.03,
                    "supports_reference_images": True,
                },
            ],
            "image_default": "nano-banana-2",
            "video_generators": [
                {
                    "name": "kling-3",
                    "provider": "fal",
                    "endpoint": "fal-ai/kling-video/v3/standard/image-to-video",
                    "api_key_env": "FAL_KEY",
                    "cost_per_second_usd": 0.10,
                    "mode": "image_to_video",
                    "native_audio": False,
                },
                {
                    "name": "veo-3.1-fast",
                    "provider": "fal",
                    "endpoint": "fal-ai/veo3.1/fast/image-to-video",
                    "api_key_env": "FAL_KEY",
                    "cost_per_second_usd": 0.15,
                    "mode": "image_to_video",
                    "native_audio": False,
                },
            ],
            "video_default": "kling-3",
        }
    }


@pytest.fixture
def adapter(media_config, tmp_path):
    """Create a MediaAdapter with a temp DB."""
    db_path = str(tmp_path / "test.db")
    from media_adapter import MediaAdapter
    return MediaAdapter(media_config, db_path=db_path)


@pytest.fixture
def ref_image(tmp_path):
    """Create a dummy reference image file."""
    img_path = str(tmp_path / "ref.png")
    with open(img_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # dummy PNG header
    return img_path


# ═══════════════════════════════════════════════════════════════════════════════
# Image generation via fal
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalImageGeneration:

    def test_fal_image_without_reference_images(self, adapter, monkeypatch, tmp_path):
        """fal image generation works without reference images (text-only)."""
        monkeypatch.setenv("FAL_KEY", "test_key")

        # Mock fal_client.run to return an image URL
        mock_result = {"images": [{"url": "https://fal.storage/img123.png"}]}
        with patch("fal_client.run", return_value=mock_result):
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(content=b"\x89PNG" + b"\x00" * 200, status_code=200)
                mock_get.return_value.raise_for_status = MagicMock()
                result = adapter.generate_image(
                    prompt="a man at a table",
                    asset_id=1,
                    model="nano-banana-2",
                    context="test",
                )

        assert result["model"] == "nano-banana-2"
        assert result["cost_usd"] == 0.039
        assert os.path.exists(result["path"])

    def test_fal_image_with_reference_images(self, adapter, monkeypatch, ref_image):
        """fal image generation with reference_images uploads them and passes URLs."""
        monkeypatch.setenv("FAL_KEY", "test_key")

        mock_result = {"images": [{"url": "https://fal.storage/img456.png"}]}
        with patch("fal_client.run", return_value=mock_result) as mock_run:
            with patch("fal_client.upload_file", return_value="https://fal.storage/ref.png") as mock_upload:
                with patch("requests.get") as mock_get:
                    mock_get.return_value = MagicMock(content=b"\x89PNG" + b"\x00" * 200, status_code=200)
                    mock_get.return_value.raise_for_status = MagicMock()
                    result = adapter.generate_image(
                        prompt="the man sits at the table",
                        asset_id=1,
                        model="nano-banana-2",
                        reference_images=[ref_image],
                    )

        # Verify fal_client.upload_file was called with the ref image
        mock_upload.assert_called_once_with(ref_image)
        # Verify fal_client.run was called with the ref URL
        call_args = mock_run.call_args
        arguments = call_args[1]["arguments"] if "arguments" in call_args[1] else call_args[0][1]
        assert "image_url" in arguments
        assert arguments["image_url"] == "https://fal.storage/ref.png"
        assert result["cost_usd"] == 0.039

    def test_fal_image_missing_reference_file_raises(self, adapter, monkeypatch):
        """Missing reference image file raises MediaAdapterError."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        from media_adapter import MediaAdapterError
        with pytest.raises(MediaAdapterError, match="Reference image not found"):
            adapter.generate_image(
                prompt="test",
                asset_id=1,
                model="nano-banana-2",
                reference_images=["/nonexistent/path.png"],
            )

    def test_fal_image_no_api_key_raises(self, adapter, monkeypatch):
        """Missing FAL_KEY raises MediaAdapterError."""
        monkeypatch.delenv("FAL_KEY", raising=False)
        from media_adapter import MediaAdapterError
        with pytest.raises(MediaAdapterError, match="FAL_KEY not set"):
            adapter.generate_image(
                prompt="test",
                asset_id=1,
                model="nano-banana-2",
            )

    def test_fal_image_cost_from_config(self, adapter, monkeypatch, tmp_path):
        """Cost is read from config, not hardcoded."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_result = {"images": [{"url": "https://fal.storage/img789.png"}]}
        with patch("fal_client.run", return_value=mock_result):
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(content=b"\x89PNG" + b"\x00" * 200, status_code=200)
                mock_get.return_value.raise_for_status = MagicMock()
                # flux2-pro costs $0.03/image
                result = adapter.generate_image(
                    prompt="test",
                    asset_id=1,
                    model="flux2-pro",
                )
        assert result["cost_usd"] == 0.03

    def test_fal_image_endpoint_from_config(self, adapter, monkeypatch):
        """The fal endpoint is read from config, not hardcoded."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_result = {"images": [{"url": "https://fal.storage/img000.png"}]}
        with patch("fal_client.run", return_value=mock_result) as mock_run:
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(content=b"\x89PNG" + b"\x00" * 200, status_code=200)
                mock_get.return_value.raise_for_status = MagicMock()
                adapter.generate_image(
                    prompt="test",
                    asset_id=1,
                    model="nano-banana-2",
                )
        # The endpoint should be the one from config
        call_args = mock_run.call_args
        endpoint = call_args[0][0]  # first positional arg
        assert endpoint == "fal-ai/gemini-3.1-flash-image-preview"

    def test_fal_image_provenance_logged(self, adapter, monkeypatch):
        """Provenance records the call with provider='fal'."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_result = {"images": [{"url": "https://fal.storage/prov.png"}]}
        with patch("fal_client.run", return_value=mock_result):
            with patch("requests.get") as mock_get:
                mock_get.return_value = MagicMock(content=b"\x89PNG" + b"\x00" * 200, status_code=200)
                mock_get.return_value.raise_for_status = MagicMock()
                adapter.generate_image(
                    prompt="test provenance",
                    asset_id=1,
                    model="nano-banana-2",
                    business_slug="testbiz",
                )
        # Check provenance table
        conn = sqlite3.connect(adapter.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM provenance WHERE business_slug = 'testbiz' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        conn.close()
        assert len(rows) > 0
        row = dict(rows[0])
        assert row["provider"] == "fal"
        assert "nano-banana-2" in row["model"]


# ═══════════════════════════════════════════════════════════════════════════════
# Video generation via fal (image-to-video)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalVideoGeneration:

    def test_fal_video_submit_image_to_video(self, adapter, monkeypatch, ref_image):
        """fal video submission (image-to-video) uploads the source image."""
        monkeypatch.setenv("FAL_KEY", "test_key")

        mock_handle = MagicMock()
        mock_handle.request_id = "fal-req-12345"
        with patch("fal_client.submit", return_value=mock_handle) as mock_submit:
            with patch("fal_client.upload_file", return_value="https://fal.storage/src.png") as mock_upload:
                result = adapter.submit_video(
                    prompt="slow push-in as he exhales",
                    asset_id=1,
                    model="kling-3",
                    duration=5,
                    source_image=ref_image,
                )

        assert result["provider"] == "fal"
        assert result["external_job_id"] == "fal-req-12345"
        assert result["status"] == "submitted"
        assert result["cost_usd"] == 0.50  # 5s × $0.10/s

        # Verify source image was uploaded
        mock_upload.assert_called_once_with(ref_image)
        # Verify submit was called with image_url in arguments
        call_args = mock_submit.call_args
        arguments = call_args[1]["arguments"]
        assert "image_url" in arguments
        assert arguments["image_url"] == "https://fal.storage/src.png"

    def test_fal_video_image_to_video_requires_source_image(self, adapter, monkeypatch):
        """image-to-video mode without source_image raises error."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        from media_adapter import MediaAdapterError
        with pytest.raises(MediaAdapterError, match="source_image is required"):
            adapter.submit_video(
                prompt="test",
                asset_id=1,
                model="kling-3",
                duration=5,
            )

    def test_fal_video_no_api_key_raises(self, adapter, monkeypatch):
        """Missing FAL_KEY raises MediaAdapterError."""
        monkeypatch.delenv("FAL_KEY", raising=False)
        from media_adapter import MediaAdapterError
        with pytest.raises(MediaAdapterError, match="FAL_KEY not set"):
            adapter.submit_video(
                prompt="test",
                asset_id=1,
                model="kling-3",
                duration=5,
                source_image="/tmp/any.png",
            )

    def test_fal_video_cost_from_config(self, adapter, monkeypatch, ref_image):
        """Video cost is computed from config cost_per_second_usd."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_handle = MagicMock()
        mock_handle.request_id = "fal-req-67890"
        with patch("fal_client.submit", return_value=mock_handle):
            with patch("fal_client.upload_file", return_value="https://fal.storage/src.png"):
                # kling-3: $0.10/s, 8s = $0.80
                result = adapter.submit_video(
                    prompt="test",
                    asset_id=1,
                    model="kling-3",
                    duration=8,
                    source_image=ref_image,
                )
        assert result["cost_usd"] == 0.80

    def test_fal_video_endpoint_from_config(self, adapter, monkeypatch, ref_image):
        """The fal endpoint is read from config, not hardcoded."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_handle = MagicMock()
        mock_handle.request_id = "fal-req-endpoint"
        with patch("fal_client.submit", return_value=mock_handle) as mock_submit:
            with patch("fal_client.upload_file", return_value="https://fal.storage/src.png"):
                adapter.submit_video(
                    prompt="test",
                    asset_id=1,
                    model="kling-3",
                    duration=5,
                    source_image=ref_image,
                )
        call_args = mock_submit.call_args
        endpoint = call_args[0][0]
        assert endpoint == "fal-ai/kling-video/v3/standard/image-to-video"

    def test_fal_video_provenance_logged(self, adapter, monkeypatch, ref_image):
        """Provenance records the video submission with provider='fal'."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_handle = MagicMock()
        mock_handle.request_id = "fal-req-prov"
        with patch("fal_client.submit", return_value=mock_handle):
            with patch("fal_client.upload_file", return_value="https://fal.storage/src.png"):
                adapter.submit_video(
                    prompt="test video provenance",
                    asset_id=1,
                    model="kling-3",
                    duration=5,
                    source_image=ref_image,
                    business_slug="testbiz",
                )
        conn = sqlite3.connect(adapter.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM provenance WHERE business_slug = 'testbiz' ORDER BY id DESC LIMIT 1"
        ).fetchall()
        conn.close()
        assert len(rows) > 0
        row = dict(rows[0])
        assert row["provider"] == "fal"
        assert "kling-3" in row["model"]


# ═══════════════════════════════════════════════════════════════════════════════
# Fal job polling
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalJobPolling:

    def test_fal_job_processing(self, adapter, monkeypatch):
        """Polling returns 'processing' when the job is still running."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        import fal_client
        with patch("fal_client.status", return_value=fal_client.InProgress(logs=None)):
            result = adapter.check_fal_job(
                endpoint="fal-ai/kling-video/v3/standard/image-to-video",
                request_id="fal-req-123",
            )
        assert result["status"] == "processing"
        assert result["download_url"] is None

    def test_fal_job_completed(self, adapter, monkeypatch):
        """Polling returns 'completed' with download_url when done."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        import fal_client
        mock_result = {"video": {"url": "https://fal.storage/video.mp4"}}
        completed = fal_client.Completed(logs=None, metrics={})
        with patch("fal_client.status", return_value=completed):
            with patch("fal_client.result", return_value=mock_result):
                result = adapter.check_fal_job(
                    endpoint="fal-ai/kling-video/v3/standard/image-to-video",
                    request_id="fal-req-456",
                )
        assert result["status"] == "completed"
        assert result["download_url"] == "https://fal.storage/video.mp4"


# ═══════════════════════════════════════════════════════════════════════════════
# Zero hardcoded endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestZeroHardcodedEndpoints:

    def test_no_hardcoded_fal_endpoints_in_source(self):
        """No fal.ai endpoint strings should be hardcoded in media_adapter.py."""
        src_path = os.path.join(os.path.dirname(__file__), "..", "src", "media_adapter.py")
        with open(src_path) as f:
            content = f.read()

        # These are config-driven — they should not appear as string literals
        # in the source code (they're in config/models.yaml only)
        hardcoded = [
            "fal-ai/kling-video",
            "fal-ai/gemini-3.1-flash-image",
            "fal-ai/flux-2-pro",
            "fal-ai/veo3.1",
        ]
        for endpoint in hardcoded:
            assert endpoint not in content, (
                f"Hardcoded fal endpoint '{endpoint}' found in media_adapter.py — "
                f"endpoints must come from config only"
            )

    def test_endpoints_resolved_from_config(self, adapter, monkeypatch, ref_image):
        """The adapter resolves endpoints from config, not from code constants."""
        monkeypatch.setenv("FAL_KEY", "test_key")
        mock_handle = MagicMock()
        mock_handle.request_id = "fal-req-check"
        with patch("fal_client.submit", return_value=mock_handle) as mock_submit:
            with patch("fal_client.upload_file", return_value="https://fal.storage/src.png"):
                adapter.submit_video(
                    prompt="test",
                    asset_id=1,
                    model="veo-3.1-fast",  # different model, different endpoint
                    duration=5,
                    source_image=ref_image,
                )
        call_args = mock_submit.call_args
        endpoint = call_args[0][0]
        # Should be the veo endpoint from config, not kling
        assert endpoint == "fal-ai/veo3.1/fast/image-to-video"