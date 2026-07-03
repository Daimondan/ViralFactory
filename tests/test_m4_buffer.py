"""
Tests for M4: Buffer adapter + metrics collection (T4.1 + T4.2)
"""

import os
import sys
import json
import sqlite3
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from buffer_adapter import BufferAdapter, BufferError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def adapter(temp_db):
    """Create a BufferAdapter with a temp DB and mock config."""
    config = {
        "buffer": {
            "api_url": "https://api.buffer.com",
            "api_key": "test-key",
            "channels": {
                "x": {"id": "x-int-123", "name": "TestX", "service": "twitter"},
                "instagram": {"id": "ig-int-456", "name": "TestIG", "service": "instagram"},
            },
        }
    }
    return BufferAdapter(config, db_path=temp_db)


class TestBufferAdapterInit:
    """Test adapter initialization and table creation."""

    def test_tables_created(self, adapter, temp_db):
        """publish_log and post_metrics tables should exist."""
        conn = sqlite3.connect(temp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "publish_log" in table_names
        assert "post_metrics" in table_names
        conn.close()

    def test_config_from_env(self, temp_db):
        """Adapter should read BUFFER_API_KEY from env if not in config."""
        old_key = os.environ.get("BUFFER_API_KEY")
        os.environ["BUFFER_API_KEY"] = "env-test-key"
        try:
            adapter = BufferAdapter({}, db_path=temp_db)
            assert adapter.api_key == "env-test-key"
        finally:
            if old_key is not None:
                os.environ["BUFFER_API_KEY"] = old_key
            else:
                del os.environ["BUFFER_API_KEY"]

    def test_no_api_key_raises_on_request(self, temp_db):
        """Adapter without API key should raise BufferError on request."""
        adapter = BufferAdapter({}, db_path=temp_db)
        with pytest.raises(BufferError, match="BUFFER_API_KEY not set"):
            adapter._gql("query { test }")


class TestPublishPiece:
    """Test the publish_piece method — T4.1 core."""

    def test_rejects_unapproved_asset(self, adapter):
        """HARD RULE: asset must be 'approved' — no auto-publish."""
        with pytest.raises(BufferError, match="Per-piece approval required"):
            adapter.publish_piece(
                business_slug="test",
                asset_id=1,
                platform="X",
                content="Hello",
                asset_state="pending",
            )

    def test_no_integration_found_logs_failure(self, adapter):
        """When no channel is found for a platform, failure is logged."""
        # Remove channel config
        adapter.channels = {}

        with patch.object(adapter, "list_integrations", return_value=[]):
            with pytest.raises(BufferError, match="No Buffer channel found"):
                adapter.publish_piece(
                    business_slug="test",
                    asset_id=1,
                    platform="TikTok",
                    content="Hello",
                    asset_state="approved",
                )

        # Verify failure was logged
        logs = adapter.list_publish_log(business_slug="test", status="failed")
        assert len(logs) >= 1
        assert "No Buffer channel" in logs[0]["error_message"]

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_successful_publish(self, mock_urlopen, adapter):
        """Successful publish creates a publish_log entry with postiz_post_id."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"createPost": {"post": {"id": "post-abc123", "status": "scheduled"}}}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = adapter.publish_piece(
            business_slug="test",
            asset_id=1,
            platform="X",
            content="Hello world!",
            asset_state="approved",
            scheduled_at="2026-07-10T10:00:00.000Z",
        )

        assert result["status"] == "scheduled"
        assert result["postiz_post_id"] == "post-abc123"
        assert result["platform"] == "X"
        assert result["asset_id"] == 1

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_publish_now_no_schedule(self, mock_urlopen, adapter):
        """Publishing with no scheduled_at should use shareNow mode."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"createPost": {"post": {"id": "post-now-1", "status": "posted"}}}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = adapter.publish_piece(
            business_slug="test",
            asset_id=2,
            platform="X",
            content="Live post!",
            asset_state="approved",
        )

        assert result["status"] == "posted"
        assert result["postiz_post_id"] == "post-now-1"

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_publish_thread_multi_post(self, mock_urlopen, adapter):
        """Thread/carousel with multiple posts publishes successfully."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"createPost": {"post": {"id": "thread-1", "status": "scheduled"}}}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        posts = ["First tweet", "Second tweet", "Third tweet"]
        result = adapter.publish_piece(
            business_slug="test",
            asset_id=3,
            platform="X",
            content="Thread summary",
            posts=posts,
            asset_state="approved",
        )

        assert result["postiz_post_id"] == "thread-1"

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_publish_failure_logged(self, mock_urlopen, adapter):
        """API failure is logged and error is surfaced, no data loss."""
        from http.client import HTTPResponse
        import io

        # Create a proper HTTPError mock with a readable body
        error_body = b'{"message": "Internal error"}'
        error_fp = io.BytesIO(error_body)
        from urllib.error import HTTPError
        mock_urlopen.side_effect = HTTPError(
            "http://test", 500, "Server Error", {}, error_fp
        )

        with pytest.raises(BufferError, match="Buffer API error 500"):
            adapter.publish_piece(
                business_slug="test",
                asset_id=4,
                platform="X",
                content="Test",
                asset_state="approved",
            )

        # Verify failure was logged
        logs = adapter.list_publish_log(business_slug="test", status="failed")
        assert len(logs) >= 1
        assert "Buffer API error 500" in logs[0]["error_message"]

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_connection_error_logged(self, mock_urlopen, adapter):
        """Connection error (Buffer down) is logged, not silently swallowed."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        with pytest.raises(BufferError, match="Buffer connection error"):
            adapter.publish_piece(
                business_slug="test",
                asset_id=5,
                platform="X",
                content="Test",
                asset_state="approved",
            )

        logs = adapter.list_publish_log(business_slug="test", status="failed")
        assert len(logs) >= 1


class TestMetricsCollection:
    """Test metrics pull — T4.2."""

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_pull_post_metrics(self, mock_urlopen, adapter):
        """Metrics pull stores data in post_metrics table."""
        # First, create a publish log entry with a postiz_post_id
        adapter._log_publish(
            business_slug="test", asset_id=1, platform="X",
            postiz_post_id="post-abc123", status="posted",
        )

        # Mock Buffer GraphQL response (post status query)
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"post": {"id": "post-abc123", "status": "posted", "channel": {"id": "x-int-123", "name": "TestX", "service": "twitter"}}}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = adapter.pull_post_metrics(1, days=7)

        assert len(result) >= 1
        assert result[0]["label"] == "status"

    def test_pull_metrics_no_post_id(self, adapter):
        """Pulling metrics for a log entry without postiz_post_id raises."""
        adapter._log_publish(
            business_slug="test", asset_id=1, platform="X",
            status="failed", error="test error",
        )
        with pytest.raises(BufferError, match="No Buffer post ID"):
            adapter.pull_post_metrics(1)

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_pull_all_metrics(self, mock_urlopen, adapter):
        """pull_all_metrics iterates over all published posts."""
        # Create two published entries
        adapter._log_publish(
            business_slug="test", asset_id=1, platform="X",
            postiz_post_id="post-1", status="posted",
        )
        adapter._log_publish(
            business_slug="test", asset_id=2, platform="Instagram",
            postiz_post_id="post-2", status="posted",
        )

        # Mock Buffer GraphQL response
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"post": {"id": "post-1", "status": "posted"}}}'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = adapter.pull_all_metrics("test", days=7)
        assert result["pulled"] == 2
        assert result["failed"] == 0
        assert result["total"] == 2

    def test_get_metrics_summary(self, adapter):
        """get_metrics_summary groups metrics by asset."""
        # Insert test metrics directly
        conn = sqlite3.connect(adapter.db_path)
        ts = datetime.now(timezone.utc).isoformat()
        for label in ["Likes", "Comments", "Impressions"]:
            conn.execute(
                """INSERT INTO post_metrics
                   (business_slug, asset_id, publish_log_id, platform,
                    metric_label, metric_value, metric_date, percentage_change, pulled_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                ("test", 1, 1, "X", label, "100", "2026-07-01", 5.0, ts),
            )
        conn.commit()
        conn.close()

        summary = adapter.get_metrics_summary("test")
        assert 1 in summary
        assert "Likes" in summary[1]
        assert summary[1]["Likes"]["value"] == "100"
        assert summary[1]["Likes"]["percentage_change"] == 5.0

    def test_retry_failed(self, adapter):
        """retry_failed lists failed publish attempts."""
        adapter._log_publish(
            business_slug="test", asset_id=1, platform="X",
            status="failed", error="Connection refused",
        )
        adapter._log_publish(
            business_slug="test", asset_id=2, platform="X",
            postiz_post_id="post-1", status="posted",
        )

        failed = adapter.retry_failed("test")
        assert len(failed) == 1
        assert failed[0]["asset_id"] == 1


class TestAvailability:
    """Test Buffer availability check."""

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_is_available_true(self, mock_urlopen, adapter):
        # Adapter has channels in config, so is_available returns True
        assert adapter.is_available() is True

    def test_is_available_no_api_key(self, temp_db):
        adapter = BufferAdapter({}, db_path=temp_db)
        assert adapter.is_available() is False

    @patch("buffer_adapter.urlrequest.urlopen")
    def test_is_available_connection_error(self, mock_urlopen, temp_db):
        """Adapter without channels but with API key returns False on connection error."""
        from urllib.error import URLError
        adapter = BufferAdapter({"buffer": {"api_key": "test", "organization_id": "org-123"}}, db_path=temp_db)
        mock_urlopen.side_effect = URLError("Connection refused")
        assert adapter.is_available() is False


class TestIntegrationIds:
    """Test integration ID resolution."""

    def test_from_config(self, adapter):
        """Channel ID from config takes priority."""
        assert adapter.get_integration_for_platform("X") == "x-int-123"
        assert adapter.get_integration_for_platform("Instagram") == "ig-int-456"

    def test_from_live_integrations(self, temp_db):
        """When config is empty, resolve from live integrations."""
        adapter = BufferAdapter(
            {"buffer": {"api_key": "test"}},
            db_path=temp_db,
        )
        with patch.object(adapter, "list_integrations", return_value=[
            {"id": "live-x-id", "type": "x"},
            {"id": "live-ig-id", "type": "instagram"},
        ]):
            assert adapter.get_integration_for_platform("X") == "live-x-id"
            assert adapter.get_integration_for_platform("Instagram") == "live-ig-id"

    def test_no_integration_returns_none(self, temp_db):
        adapter = BufferAdapter(
            {"buffer": {"api_key": "test"}},
            db_path=temp_db,
        )
        with patch.object(adapter, "list_integrations", return_value=[]):
            assert adapter.get_integration_for_platform("TikTok") is None


class TestFlaskRoutes:
    """Test Flask routes for publish + metrics."""

    @pytest.fixture
    def flask_app(self, tmp_path):
        """Create a Flask test app with temp DB."""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
        from app import create_app

        # Copy config to temp
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        db_path = str(tmp_path / "test.db")

        app = create_app(
            config_dir=config_dir,
            db_path=db_path,
            playbooks_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks")),
        )
        app.config["TESTING"] = True
        return app

    def test_buffer_status_route(self, flask_app):
        """GET /api/buffer/status returns availability info."""
        with flask_app.test_client() as client:
            resp = client.get("/api/buffer/status")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "available" in data

    def test_metrics_page_renders(self, flask_app):
        """GET /metrics renders the metrics page."""
        with flask_app.test_client() as client:
            resp = client.get("/metrics")
            assert resp.status_code == 200
            assert b"Metrics" in resp.data

    def test_pull_metrics_route(self, flask_app):
        """POST /api/metrics/pull returns pull results."""
        with flask_app.test_client() as client:
            resp = client.post("/api/metrics/pull", json={"days": 7})
            # Will fail if Buffer not available, but should return 502 not 500
            assert resp.status_code in (200, 502)

    def test_schedule_requires_approved(self, flask_app):
        """Schedule endpoint rejects non-approved assets."""
        from pipeline import PipelineStore
        store = PipelineStore(flask_app.config["DB_PATH"])
        # Create a draft and asset in 'pending' state
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Test idea",
            hook_options=json.dumps(["Hook 1"]),
            treatment=json.dumps({"scope": "one_off", "format": "X Thread", "capture_required": "none"}),
            origin="human_seeded",
        )
        draft_id = store.create_draft(
            business_slug="stackpenni",
            idea_card_id=card_id,
            origin="human_seeded",
            format_name="X Thread",
            scope="one_off",
        )
        asset_id = store.create_asset(
            business_slug="stackpenni",
            draft_id=draft_id,
            platform="X",
            variant_type="thread",
            content="Test content",
        )

        with flask_app.test_client() as client:
            resp = client.post(f"/api/assets/{asset_id}/schedule", json={"scheduled_at": "2026-07-10T10:00:00"})
            assert resp.status_code == 400
            data = resp.get_json()
            assert "approved" in data["error"]