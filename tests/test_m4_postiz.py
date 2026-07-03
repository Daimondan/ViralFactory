"""
Tests for M4: Postiz adapter + metrics collection (T4.1 + T4.2)
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

from postiz_adapter import PostizAdapter, PostizError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def adapter(temp_db):
    """Create a PostizAdapter with a temp DB and mock config."""
    config = {
        "postiz": {
            "base_url": "http://localhost:3000/api/public/v1",
            "api_key": "test-key",
            "default_integration_ids": {
                "X": "x-int-123",
                "Instagram": "ig-int-456",
            },
        }
    }
    return PostizAdapter(config, db_path=temp_db)


class TestPostizAdapterInit:
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
        """Adapter should read POSTIZ_API_KEY from env if not in config."""
        old_key = os.environ.get("POSTIZ_API_KEY")
        os.environ["POSTIZ_API_KEY"] = "env-test-key"
        try:
            adapter = PostizAdapter({}, db_path=temp_db)
            assert adapter.api_key == "env-test-key"
        finally:
            if old_key is not None:
                os.environ["POSTIZ_API_KEY"] = old_key
            else:
                del os.environ["POSTIZ_API_KEY"]

    def test_no_api_key_raises_on_request(self, temp_db):
        """Adapter without API key should raise PostizError on request."""
        adapter = PostizAdapter({}, db_path=temp_db)
        with pytest.raises(PostizError, match="POSTIZ_API_KEY not set"):
            adapter._request("GET", "/integrations")


class TestPublishPiece:
    """Test the publish_piece method — T4.1 core."""

    def test_rejects_unapproved_asset(self, adapter):
        """HARD RULE: asset must be 'approved' — no auto-publish."""
        with pytest.raises(PostizError, match="Per-piece approval required"):
            adapter.publish_piece(
                business_slug="test",
                asset_id=1,
                platform="X",
                content="Hello",
                asset_state="pending",
            )

    def test_no_integration_found_logs_failure(self, adapter):
        """When no integration is found for a platform, failure is logged."""
        # Remove integration IDs
        adapter.integration_ids = {}

        with patch.object(adapter, "list_integrations", return_value=[]):
            with pytest.raises(PostizError, match="No Postiz integration found"):
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
        assert "No Postiz integration" in logs[0]["error_message"]

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_successful_publish(self, mock_urlopen, adapter):
        """Successful publish creates a publish_log entry with postiz_post_id."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "post-abc123"}'
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

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_publish_now_no_schedule(self, mock_urlopen, adapter):
        """Publishing with no scheduled_at should use type 'now'."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "post-now-1"}'
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

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_publish_thread_multi_post(self, mock_urlopen, adapter):
        """Thread/carousel with multiple posts creates multiple value items."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"id": "thread-1"}'
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
        # Verify the request payload had 3 value items
        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        body = json.loads(req.data)
        assert len(body["posts"][0]["value"]) == 3

    @patch("postiz_adapter.urlrequest.urlopen")
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

        with pytest.raises(PostizError, match="Postiz API error 500"):
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
        assert "Postiz API error 500" in logs[0]["error_message"]

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_connection_error_logged(self, mock_urlopen, adapter):
        """Connection error (Postiz down) is logged, not silently swallowed."""
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")

        with pytest.raises(PostizError, match="Postiz connection error"):
            adapter.publish_piece(
                business_slug="test",
                asset_id=5,
                platform="X",
                content="Test",
                asset_state="approved",
            )

        logs = adapter.list_publish_log(business_slug="test", status="failed")
        assert len(logs) >= 1


class TestPlatformSettings:
    """Test platform-specific Postiz settings."""

    def test_x_settings(self, adapter):
        settings = adapter._build_platform_settings("X")
        assert settings["__type"] == "x"

    def test_instagram_settings(self, adapter):
        settings = adapter._build_platform_settings("Instagram")
        assert settings["__type"] == "instagram"

    def test_generic_fallback(self, adapter):
        settings = adapter._build_platform_settings("TikTok")
        assert settings["__type"] == "tiktok"


class TestMetricsCollection:
    """Test metrics pull — T4.2."""

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_pull_post_metrics(self, mock_urlopen, adapter):
        """Metrics pull stores data in post_metrics table."""
        # First, create a publish log entry with a postiz_post_id
        adapter._log_publish(
            business_slug="test", asset_id=1, platform="X",
            postiz_post_id="post-abc123", status="posted",
        )

        # Mock analytics response
        analytics = [
            {"label": "Likes", "data": [{"total": "150", "date": "2026-07-01"}], "percentageChange": 16.7},
            {"label": "Comments", "data": [{"total": "25", "date": "2026-07-01"}], "percentageChange": 20.0},
        ]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(analytics).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = adapter.pull_post_metrics(1, days=7)

        assert len(result) == 2
        assert result[0]["label"] == "Likes"
        assert result[0]["value"] == "150"

    def test_pull_metrics_no_post_id(self, adapter):
        """Pulling metrics for a log entry without postiz_post_id raises."""
        adapter._log_publish(
            business_slug="test", asset_id=1, platform="X",
            status="failed", error="test error",
        )
        with pytest.raises(PostizError, match="No Postiz post ID"):
            adapter.pull_post_metrics(1)

    @patch("postiz_adapter.urlrequest.urlopen")
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

        # Mock analytics
        analytics = [{"label": "Likes", "data": [{"total": "100", "date": "2026-07-01"}], "percentageChange": 5.0}]
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(analytics).encode()
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
    """Test Postiz availability check."""

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_is_available_true(self, mock_urlopen, adapter):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"[]"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        assert adapter.is_available() is True

    def test_is_available_no_api_key(self, temp_db):
        adapter = PostizAdapter({}, db_path=temp_db)
        assert adapter.is_available() is False

    @patch("postiz_adapter.urlrequest.urlopen")
    def test_is_available_connection_error(self, mock_urlopen, adapter):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("Connection refused")
        assert adapter.is_available() is False


class TestIntegrationIds:
    """Test integration ID resolution."""

    def test_from_config(self, adapter):
        """Integration ID from config takes priority."""
        assert adapter.get_integration_for_platform("X") == "x-int-123"
        assert adapter.get_integration_for_platform("Instagram") == "ig-int-456"

    def test_from_live_integrations(self, temp_db):
        """When config is empty, resolve from live integrations."""
        adapter = PostizAdapter(
            {"postiz": {"api_key": "test"}},
            db_path=temp_db,
        )
        with patch.object(adapter, "list_integrations", return_value=[
            {"id": "live-x-id", "type": "x"},
            {"id": "live-ig-id", "type": "instagram"},
        ]):
            assert adapter.get_integration_for_platform("X") == "live-x-id"
            assert adapter.get_integration_for_platform("Instagram") == "live-ig-id"

    def test_no_integration_returns_none(self, temp_db):
        adapter = PostizAdapter(
            {"postiz": {"api_key": "test"}},
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

    def test_postiz_status_route(self, flask_app):
        """POST /api/postiz/status returns availability info."""
        with flask_app.test_client() as client:
            resp = client.get("/api/postiz/status")
            assert resp.status_code == 200
            data = resp.get_json()
            assert "available" in data
            assert "base_url" in data

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
            # Will fail if Postiz not available, but should return 502 not 500
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