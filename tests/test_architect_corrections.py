"""
Tests for architect review corrections:
- P1-1: Jargon — no raw state strings in operator UI
- P1-2: Relative timestamps on pipeline pages
- P2-1: Config-driven platform fallback (no hardcoded "X", "Instagram")
- P2-2: Awaiting-capture cleanup (non-blocking per AMENDMENT-006)
- P2-3: Postiz dead code removed, Buffer is the publishing platform
- DIVERGENCE-007: Source review gate (status='new' for RSS, restrict ideation to active)
"""

import os
import sys
import json
import tempfile
import sqlite3
from unittest.mock import patch, MagicMock

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


# ── P1-1: Jargon tests ──

class TestJargonCleanup:
    """P1-1: No raw state strings visible as text in operator-facing templates."""

    @pytest.fixture
    def template_dir(self):
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")

    def test_ideas_html_no_raw_awaiting_tab(self, template_dir):
        """The 'awaiting' tab must not exist in ideas.html."""
        with open(os.path.join(template_dir, "ideas.html")) as f:
            content = f.read()
        # No "Awaiting" tab button
        assert "Awaiting (" not in content
        # No tab=awaiting link
        assert "tab=awaiting" not in content

    def test_ideas_html_has_state_labels_mapping(self, template_dir):
        """ideas.html must have a state_labels mapping for human-readable labels."""
        with open(os.path.join(template_dir, "ideas.html")) as f:
            content = f.read()
        assert "state_labels" in content
        assert "asset_ready" in content  # used in the mapping

    def test_ideas_html_card_state_uses_labels(self, template_dir):
        """Card state badge uses state_labels mapping, not raw card_state."""
        with open(os.path.join(template_dir, "ideas.html")) as f:
            content = f.read()
        # The badge should use state_labels.get, not raw card.card_state
        assert "state_labels.get(card.card_state" in content
        # Should NOT have raw {{ card.card_state }} as the only badge text
        assert ">}}{{ card.card_state }}" not in content

    def test_assemble_html_no_raw_state_text(self, template_dir):
        """Assembler page shows human labels, not raw state strings as visible text."""
        with open(os.path.join(template_dir, "assemble.html")) as f:
            content = f.read()
        # The state badge should use a human-label dict, not raw display_state
        assert "'assembling': 'Assembling'" in content
        assert "'ready_review': 'Ready for review'" in content

    def test_no_raw_state_as_visible_text_in_templates(self, template_dir):
        """Raw state strings must not appear as visible text in templates.
        They may appear in CSS class names, Jinja if-conditions, JS data attributes,
        and label mapping dicts — but not as bare output in {{ }} expressions."""
        raw_states = ["asset_ready", "writer_failed", "assembly_failed", "production_failed", "awaiting_capture"]
        for template_file in ["ideas.html", "create.html", "assemble.html"]:
            filepath = os.path.join(template_dir, template_file)
            with open(filepath) as f:
                lines = f.readlines()
            for i, line in enumerate(lines, 1):
                for state in raw_states:
                    if state not in line:
                        continue
                    stripped = line.strip()
                    # Allow in CSS class names
                    if f"st-{state}" in line or f"state-{state}" in line:
                        continue
                    # Allow in Jinja if-conditions
                    if "{% if" in line and state in line:
                        continue
                    # Allow in label mapping dicts
                    if f"'{state}'" in line and (":" in line or "':" in line):
                        continue
                    # Allow in JS data attributes
                    if "data-state=" in line or "data-filter=" in line:
                        continue
                    # Allow in comments
                    if stripped.startswith("{#") or stripped.startswith("<!--"):
                        continue
                    # Allow in JS conditionals
                    if "==" in line or "!=" in line or "if " in line.lower():
                        continue
                    # Allow in .get() calls (label lookups)
                    if ".get(" in line or "labels" in line:
                        continue
                    pytest.fail(f"Raw state '{state}' on line {i} of {template_file}: {stripped}")


# ── P1-2: Relative timestamp tests ──

class TestRelativeTimestamps:
    """P1-2: Relative timestamps on pipeline pages."""

    def test_relative_time_filter_exists(self):
        """The relative_time Jinja filter is registered in create_app()."""
        from app import create_app
        import tempfile
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        app = create_app(config_dir=config_dir, db_path=tempfile.mktemp(suffix=".db"))
        assert "relative_time" in app.jinja_env.filters

    def test_relative_time_recent(self):
        """Relative time returns 'just now' for recent timestamps."""
        from app import create_app
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        app = create_app(config_dir=config_dir, db_path=tempfile.mktemp(suffix=".db"))
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        result = app.jinja_env.filters["relative_time"](now)
        assert "just now" in result or "minute" in result

    def test_relative_time_hours_ago(self):
        """Relative time returns 'N hours ago' for timestamps hours in the past."""
        from app import create_app
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        app = create_app(config_dir=config_dir, db_path=tempfile.mktemp(suffix=".db"))
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
        result = app.jinja_env.filters["relative_time"](past)
        assert "3 hour" in result

    def test_relative_time_days_ago(self):
        """Relative time returns 'N days ago' for timestamps days in the past."""
        from app import create_app
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        app = create_app(config_dir=config_dir, db_path=tempfile.mktemp(suffix=".db"))
        from datetime import datetime, timezone, timedelta
        past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        result = app.jinja_env.filters["relative_time"](past)
        assert "2 day" in result

    def test_relative_time_empty(self):
        """Relative time returns empty string for None/empty input."""
        from app import create_app
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        app = create_app(config_dir=config_dir, db_path=tempfile.mktemp(suffix=".db"))
        assert app.jinja_env.filters["relative_time"](None) == ""
        assert app.jinja_env.filters["relative_time"]("") == ""

    def test_ideas_html_has_timestamp_display(self):
        """ideas.html template includes relative timestamp display."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")
        with open(os.path.join(template_dir, "ideas.html")) as f:
            content = f.read()
        assert "relative_time" in content
        assert "time-ago" in content
        assert "created_at" in content

    def test_create_html_has_timestamp_display(self):
        """create.html template includes relative timestamp display."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")
        with open(os.path.join(template_dir, "create.html")) as f:
            content = f.read()
        assert "relative_time" in content
        assert "time-ago" in content
        assert "state_changed_at" in content

    def test_assemble_html_has_timestamp_display(self):
        """assemble.html template includes relative timestamp display."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")
        with open(os.path.join(template_dir, "assemble.html")) as f:
            content = f.read()
        assert "relative_time" in content
        assert "time-ago" in content
        assert "state_changed_at" in content


# ── P2-1: Config-driven platform fallback tests ──

class TestPlatformFallback:
    """P2-1: Platform fallback uses business config, not hardcoded names."""

    def test_no_hardcoded_x_instagram_fallback(self):
        """produce_chain.py must not have hardcoded ["X", "Instagram"] fallback."""
        produce_chain_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "produce_chain.py"
        )
        with open(produce_chain_path) as f:
            content = f.read()
        # The old hardcoded fallback must be gone
        assert '"X", "Instagram"' not in content
        assert '# fallback' not in content or 'business_config' in content

    def test_get_platforms_from_format_entry_uses_business_config(self):
        """_get_platforms_from_format_entry falls back to business config platforms."""
        from produce_chain import _get_platforms_from_format_entry
        ms = MagicMock()
        ms.get_entry.return_value = None  # no Format Guide entry
        business_config = {"platforms": [{"name": "TikTok"}, {"name": "YouTube"}]}
        result = _get_platforms_from_format_entry(ms, "test-slug", "some_format", business_config=business_config)
        assert result == ["TikTok", "YouTube"]

    def test_get_platforms_from_format_entry_no_config_returns_empty(self):
        """_get_platforms_from_format_entry returns empty list when no config and no entry."""
        from produce_chain import _get_platforms_from_format_entry
        ms = MagicMock()
        ms.get_entry.return_value = None
        result = _get_platforms_from_format_entry(ms, "test-slug", "some_format", business_config=None)
        assert result == []

    def test_get_platforms_from_format_entry_parses_structured_line(self):
        """T9.1: Platforms parsed from '- **Platforms:**' structured field, not regex."""
        from produce_chain import _get_platforms_from_format_entry
        ms = MagicMock()
        ms.get_entry.return_value = "### X Thread\n- **Platforms:** X, Instagram\n- **Status:** proven\n"
        result = _get_platforms_from_format_entry(ms, "test-slug", "X Thread")
        assert result == ["X", "Instagram"]

    def test_get_variant_type_from_format_entry_parses_structured_line(self):
        """T9.1: variant_type parsed from '- **Variant type:**' structured field."""
        from produce_chain import _get_variant_type_from_format_entry
        ms = MagicMock()
        ms.get_entry.return_value = "### X Thread\n- **Platforms:** X\n- **Variant type:** thread\n"
        result = _get_variant_type_from_format_entry(ms, "test-slug", "X Thread")
        assert result == "thread"

    def test_get_variant_type_returns_none_when_field_missing(self):
        """T9.1: variant_type returns None when the field is not present."""
        from produce_chain import _get_variant_type_from_format_entry
        ms = MagicMock()
        ms.get_entry.return_value = "### Some Format\n- **Platforms:** X\n"
        result = _get_variant_type_from_format_entry(ms, "test-slug", "Some Format")
        assert result is None


# ── P2-2: Awaiting-capture cleanup tests ──

class TestAwaitingCaptureCleanup:
    """P2-2: Awaiting-capture is deprecated as a blocking state per AMENDMENT-006."""

    def test_no_awaiting_tab_in_state_map(self):
        """app.py state_map must not have 'awaiting' key."""
        app_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "app.py"
        )
        with open(app_path) as f:
            content = f.read()
        # The state_map should not have a separate awaiting entry
        # (awaiting_capture is folded into the approved tab)
        assert '"awaiting":' not in content

    def test_pipeline_py_notes_deprecation(self):
        """pipeline.py schema comment notes awaiting_capture is deprecated."""
        pipeline_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "pipeline.py"
        )
        with open(pipeline_path) as f:
            content = f.read()
        assert "DEPRECATED" in content
        assert "AMENDMENT-006" in content

    def test_ideas_html_no_awaiting_tab(self):
        """ideas.html must not have an 'Awaiting' tab."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")
        with open(os.path.join(template_dir, "ideas.html")) as f:
            content = f.read()
        assert "Awaiting (" not in content
        assert "tab=awaiting" not in content

    def test_capture_tasks_still_display_on_approved_cards(self):
        """Capture tasks still display on cards (as a non-blocking flag, not a separate state)."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")
        with open(os.path.join(template_dir, "ideas.html")) as f:
            content = f.read()
        # Capture tasks section still exists
        assert "capture-tasks" in content
        assert "Capture required" in content
        # "Manage capture" button still exists for cards with capture tasks
        assert "Manage capture" in content


# ── P2-3: Postiz cleanup tests ──

class TestPostizCleanup:
    """P2-3: Postiz dead code removed per DIVERGENCE-008."""

    def test_postiz_adapter_deleted(self):
        """src/postiz_adapter.py must not exist."""
        postiz_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "src", "postiz_adapter.py"
        )
        assert not os.path.exists(postiz_path), "postiz_adapter.py should be deleted per DIVERGENCE-008"

    def test_cron_pull_metrics_uses_buffer(self):
        """cron_pull_metrics.py imports BufferAdapter, not PostizAdapter."""
        cron_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "cron_pull_metrics.py"
        )
        with open(cron_path) as f:
            content = f.read()
        assert "BufferAdapter" in content
        assert "BufferError" in content
        assert "postiz_adapter" not in content
        assert "PostizAdapter" not in content

    def test_no_postiz_config_in_models_yaml(self):
        """config/models.yaml must not have a postiz: block."""
        models_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config", "models.yaml"
        )
        with open(models_path) as f:
            content = f.read()
        # Should have buffer: block
        assert "buffer:" in content
        # Should not have a standalone postiz: config block
        lines = content.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("postiz:") and not stripped.startswith("#"):
                pytest.fail(f"Found active postiz: config block: {stripped}")


# ── DIVERGENCE-007: Source review gate tests ──

class TestSourceReviewGate:
    """DIVERGENCE-007 Item 1: New sources enter with status='new', only active feed ideation."""

    def test_source_snapshot_writes_new_status(self):
        """RSS sources enter the sources table with status='new', not 'active'."""
        from source_snapshot import SourceSnapshot
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        snap = SourceSnapshot(db_path=db_path, business_slug="test-biz")

        # Insert a source item directly through the snapshot method
        items = [{"url": "https://example.com/feed1", "title": "Test Source", "summary": "A test", "content": "content"}]
        snap._register_sources(items)

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT status FROM sources WHERE url = ? AND business_slug = ?",
                          ("https://example.com/feed1", "test-biz")).fetchone()
        conn.close()

        assert row is not None, "Source should have been written to sources table"
        assert row[0] == "new", f"New RSS source should have status='new', got '{row[0]}'"

    def test_source_snapshot_dedup_any_status(self):
        """Dedup check looks at any status, not just active — prevents re-adding reviewed sources."""
        from source_snapshot import SourceSnapshot
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        # Pre-insert a source with status='removed'
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_slug TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT, summary TEXT, content TEXT,
                origin TEXT NOT NULL DEFAULT 'system',
                first_seen TEXT NOT NULL,
                content_hash TEXT,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        import hashlib
        url = "https://example.com/dup"
        chash = hashlib.sha256(url.encode()).hexdigest()[:16]
        conn.execute(
            "INSERT INTO sources (business_slug, source_type, title, url, origin, first_seen, content_hash, status) "
            "VALUES ('test-biz', 'rss_item', 'Existing', ?, 'system', ?, ?, 'removed')",
            (url, "2026-01-01T00:00:00Z", chash)
        )
        conn.commit()
        conn.close()

        snap = SourceSnapshot(db_path=db_path, business_slug="test-biz")
        items = [{"url": url, "title": "Dup Source", "summary": "dup", "content": "dup"}]
        snap._register_sources(items)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT COUNT(*) FROM sources WHERE url = ? AND business_slug = ?",
                           (url, "test-biz")).fetchone()
        conn.close()

        assert rows[0] == 1, "Should not re-add a source that exists with any status"

    def test_list_sources_default_active_only(self):
        """PipelineStore.list_sources default returns only active sources."""
        from pipeline import PipelineStore
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        store = PipelineStore(db_path=db_path)
        store._init_db()

        # Insert sources with different statuses
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO sources (business_slug, source_type, title, origin, first_seen, content_hash, status) "
            "VALUES ('test-biz', 'rss_item', 'Active', 'system', '2026-01-01', 'h1', 'active')"
        )
        conn.execute(
            "INSERT INTO sources (business_slug, source_type, title, origin, first_seen, content_hash, status) "
            "VALUES ('test-biz', 'rss_item', 'New', 'system', '2026-01-02', 'h2', 'new')"
        )
        conn.commit()
        conn.close()

        active = store.list_sources("test-biz", status="active")
        assert len(active) == 1
        assert active[0]["title"] == "Active"

    def test_list_sources_can_filter_new(self):
        """PipelineStore.list_sources can filter by status='new'."""
        from pipeline import PipelineStore
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        store = PipelineStore(db_path=db_path)
        store._init_db()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO sources (business_slug, source_type, title, origin, first_seen, content_hash, status) "
            "VALUES ('test-biz', 'rss_item', 'New', 'system', '2026-01-01', 'h1', 'new')"
        )
        conn.execute(
            "INSERT INTO sources (business_slug, source_type, title, origin, first_seen, content_hash, status) "
            "VALUES ('test-biz', 'rss_item', 'Active', 'system', '2026-01-02', 'h2', 'active')"
        )
        conn.commit()
        conn.close()

        new_sources = store.list_sources("test-biz", status="new")
        assert len(new_sources) == 1
        assert new_sources[0]["title"] == "New"

    def test_resolve_source_refs_only_active(self):
        """resolve_source_refs only resolves active sources — new sources don't resolve."""
        from pipeline import PipelineStore
        import tempfile

        db_path = tempfile.mktemp(suffix=".db")
        store = PipelineStore(db_path=db_path)
        store._init_db()

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO sources (id, business_slug, source_type, title, origin, first_seen, content_hash, status) "
            "VALUES (1, 'test-biz', 'rss_item', 'Active', 'system', '2026-01-01', 'h1', 'active')"
        )
        conn.execute(
            "INSERT INTO sources (id, business_slug, source_type, title, origin, first_seen, content_hash, status) "
            "VALUES (2, 'test-biz', 'rss_item', 'NewUnreviewed', 'system', '2026-01-02', 'h2', 'new')"
        )
        conn.commit()
        conn.close()

        resolved = store.resolve_source_refs("test-biz", [1, 2])
        assert len(resolved) == 1
        assert resolved[0]["title"] == "Active"

    def test_source_bank_page_has_new_filter(self):
        """source_bank.html template includes 'New' status and bulk actions."""
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "templates")
        with open(os.path.join(template_dir, "source_bank.html")) as f:
            content = f.read()
        assert "'new': 'New'" in content or "'new'" in content
        assert "st-new" in content
        assert "bulkUpdateSources" in content
        assert "bulk-status" in content

    def test_bulk_status_api_exists(self):
        """The /api/sources/bulk-status endpoint is registered."""
        from app import create_app
        import tempfile
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        app = create_app(config_dir=config_dir, db_path=tempfile.mktemp(suffix=".db"))

        # Check the route exists by looking at URL map
        rules = [r.rule for r in app.url_map.iter_rules()]
        assert "/api/sources/bulk-status" in rules


# ── Integration: full page render tests ──

class TestPageRendering:
    """Verify pages render without errors and contain expected elements."""

    @pytest.fixture
    def app_client(self):
        from app import create_app
        import tempfile
        config_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
        db_path = tempfile.mktemp(suffix=".db")
        app = create_app(config_dir=config_dir, db_path=db_path)
        app.config["TESTING"] = True
        return app.test_client()

    def test_ideas_page_renders(self, app_client):
        """Ideas page renders without error."""
        resp = app_client.get("/ideas")
        assert resp.status_code == 200

    def test_create_page_renders(self, app_client):
        """Writer page renders without error."""
        resp = app_client.get("/create")
        assert resp.status_code == 200

    def test_assemble_page_renders(self, app_client):
        """Assembler page renders without error."""
        resp = app_client.get("/assemble")
        assert resp.status_code == 200

    def test_sources_page_renders(self, app_client):
        """Source Bank page renders without error."""
        resp = app_client.get("/sources")
        assert resp.status_code == 200

    def test_ideas_page_has_relative_timestamps(self, app_client):
        """Ideas page contains time-ago class (relative timestamps are wired)."""
        resp = app_client.get("/ideas")
        assert b"time-ago" in resp.data

    def test_create_page_has_relative_timestamps(self, app_client):
        """Writer page contains time-ago class."""
        resp = app_client.get("/create")
        assert b"time-ago" in resp.data

    def test_assemble_page_has_relative_timestamps(self, app_client):
        """Assembler page contains time-ago class."""
        resp = app_client.get("/assemble")
        assert b"time-ago" in resp.data

    def test_sources_page_has_new_status(self, app_client):
        """Source Bank page has the 'New' status class and bulk actions."""
        resp = app_client.get("/sources")
        assert b"st-new" in resp.data
        assert b"bulkUpdateSources" in resp.data