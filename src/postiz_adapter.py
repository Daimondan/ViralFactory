"""
ViralFactory — Postiz Adapter (M4: T4.1 + T4.2)

Wraps the Postiz Public API for:
  - Publishing pieces to social platforms (after per-piece approval)
  - Pulling post-level analytics metrics on a schedule

Postiz API reference: https://docs.postiz.com/public-api
  POST   /public/v1/posts          — create/schedule/now post
  GET    /public/v1/posts          — list posts
  DELETE /public/v1/posts/:id      — delete a post
  PUT    /public/v1/posts/:id/status — change status (draft ↔ schedule)
  GET    /public/v1/integrations    — list connected integrations
  GET    /public/v1/analytics/post/:postId — post analytics
  GET    /public/v1/analytics/:integration — platform analytics
  POST   /public/v1/upload          — upload media

Config (config/models.yaml):
  postiz:
    base_url: "http://localhost:3000/api/public/v1"  # self-hosted or cloud
    api_key: ""                                       # from POSTIZ_API_KEY env
    default_integration_ids:                          # per-platform integration IDs
      X: ""
      Instagram: ""

Business rules enforced:
  - No auto-publish. Every piece requires explicit per-piece approval (Gate 4).
  - Failures are surfaced, never silently swallowed.
  - Postiz down → pieces stay in the publish queue, never lost.
  - Every publish attempt is logged to provenance.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib import request as urlrequest
from urllib.error import URLError, HTTPError

logger = logging.getLogger("viralfactory.postiz")


class PostizError(Exception):
    """Postiz API error."""
    pass


class PostizAdapter:
    """Adapter for the Postiz Public API — publishing + metrics."""

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        postiz_cfg = (models_config or {}).get("postiz", {})
        self.base_url = postiz_cfg.get(
            "base_url",
            os.environ.get("POSTIZ_BASE_URL", "http://localhost:3000/api/public/v1"),
        ).rstrip("/")
        self.api_key = postiz_cfg.get("api_key", "") or os.environ.get("POSTIZ_API_KEY", "")
        self.integration_ids = postiz_cfg.get("default_integration_ids", {})
        self._ensure_tables()

    def _ensure_tables(self):
        """Create publish_log and post_metrics tables if they don't exist."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS publish_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_slug TEXT NOT NULL,
                asset_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                postiz_post_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                error_message TEXT,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                scheduled_at TEXT,
                posted_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES assets(id)
            );
            CREATE INDEX IF NOT EXISTS idx_publish_asset ON publish_log(asset_id);
            CREATE INDEX IF NOT EXISTS idx_publish_status ON publish_log(status);

            CREATE TABLE IF NOT EXISTS post_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_slug TEXT NOT NULL,
                asset_id INTEGER,
                publish_log_id INTEGER,
                platform TEXT NOT NULL,
                metric_label TEXT NOT NULL,
                metric_value TEXT,
                metric_date TEXT,
                percentage_change REAL,
                pulled_at TEXT NOT NULL,
                FOREIGN KEY (asset_id) REFERENCES assets(id),
                FOREIGN KEY (publish_log_id) REFERENCES publish_log(id)
            );
            CREATE INDEX IF NOT EXISTS idx_metrics_asset ON post_metrics(asset_id);
            CREATE INDEX IF NOT EXISTS idx_metrics_date ON post_metrics(pulled_at);
        """)
        conn.commit()
        conn.close()

    # ── HTTP helper ──────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: dict = None) -> dict:
        """Make an authenticated request to the Postiz API."""
        if not self.api_key:
            raise PostizError("POSTIZ_API_KEY not set — Postiz adapter cannot function")

        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body else None
        req = urlrequest.Request(url, data=data, method=method)
        req.add_header("Authorization", self.api_key)
        if body:
            req.add_header("Content-Type", "application/json")

        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                body_text = resp.read().decode("utf-8")
                if not body_text:
                    return {}
                return json.loads(body_text)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:500]
            raise PostizError(f"Postiz API error {e.code}: {error_body}") from e
        except URLError as e:
            raise PostizError(f"Postiz connection error: {e.reason}") from e
        except Exception as e:
            raise PostizError(f"Postiz request failed: {e}") from e

    # ── Integrations ──────────────────────────────────────────────────────

    def list_integrations(self) -> list[dict]:
        """List connected social media integrations from Postiz."""
        try:
            result = self._request("GET", "/integrations")
            if isinstance(result, list):
                return result
            return result.get("integrations", result.get("data", []))
        except PostizError as e:
            logger.warning(f"Failed to list integrations: {e}")
            return []

    def get_integration_for_platform(self, platform: str) -> Optional[str]:
        """Get the Postiz integration ID for a given platform name (X, Instagram, etc.)."""
        # First check config
        if platform in self.integration_ids and self.integration_ids[platform]:
            return self.integration_ids[platform]

        # Then check live integrations
        integrations = self.list_integrations()
        for integ in integrations:
            # Postiz returns integration type in various fields
            integ_type = str(integ.get("type", integ.get("__type", integ.get("name", "")))).lower()
            platform_lower = platform.lower()
            if platform_lower == "x" and "x" in integ_type:
                return str(integ.get("id", ""))
            if platform_lower == "instagram" and "instagram" in integ_type:
                return str(integ.get("id", ""))
            if platform_lower in integ_type:
                return str(integ.get("id", ""))
        return None

    # ── Publishing ───────────────────────────────────────────────────────

    def publish_piece(
        self,
        business_slug: str,
        asset_id: int,
        platform: str,
        content: str,
        posts: list[str] = None,
        images: list[dict] = None,
        scheduled_at: str = None,
        asset_state: str = "approved",
    ) -> dict:
        """
        Publish or schedule a piece via Postiz.

        HARD RULE: asset_state must be 'approved'. No auto-publish.
        Returns a publish_log row dict.
        """
        if asset_state != "approved":
            raise PostizError(
                "Per-piece approval required: asset must be 'approved' before publishing. "
                "No auto-publish at any trust level."
            )

        integration_id = self.get_integration_for_platform(platform)
        if not integration_id:
            error_msg = f"No Postiz integration found for platform '{platform}'. Check Postiz connections or config."
            self._log_publish(business_slug, asset_id, platform, status="failed", error=error_msg)
            raise PostizError(error_msg)

        # Build post payload
        post_type = "schedule" if scheduled_at else "now"
        post_date = scheduled_at or datetime.now(timezone.utc).isoformat()

        # Build value array (content items)
        value_items = []
        if posts and len(posts) > 1:
            # Thread / carousel: each post is a value item
            for i, post_text in enumerate(posts):
                item = {"content": post_text}
                if images and i < len(images):
                    item["image"] = [{"id": images[i].get("id", ""), "path": images[i].get("path", "")}] if images[i].get("id") else []
                value_items.append(item)
        else:
            # Single post
            item = {"content": content}
            if images:
                item["image"] = [{"id": img.get("id", ""), "path": img.get("path", "")} for img in images if img.get("id")]
            value_items.append(item)

        # Build settings based on platform
        settings = self._build_platform_settings(platform)

        payload = {
            "type": post_type,
            "date": post_date,
            "shortLink": False,
            "tags": [],
            "posts": [
                {
                    "integration": {"id": integration_id},
                    "value": value_items,
                    "settings": settings,
                }
            ],
        }

        # Attempt the API call
        try:
            result = self._request("POST", "/posts", payload)
            postiz_post_id = str(result.get("id", result.get("post_id", ""))) if isinstance(result, dict) else str(result)

            log_row = self._log_publish(
                business_slug, asset_id, platform,
                postiz_post_id=postiz_post_id,
                status="scheduled" if scheduled_at else "posted",
                scheduled_at=scheduled_at,
                posted_at=datetime.now(timezone.utc).isoformat() if not scheduled_at else None,
            )
            logger.info(f"Published asset {asset_id} to {platform} via Postiz: {postiz_post_id}")
            return log_row

        except PostizError as e:
            # Log the failure — piece stays in queue, no data loss
            self._log_publish(
                business_slug, asset_id, platform,
                status="failed",
                error=str(e),
            )
            logger.error(f"Failed to publish asset {asset_id} to {platform}: {e}")
            raise

    def _build_platform_settings(self, platform: str) -> dict:
        """Build Postiz settings object for a platform."""
        platform_lower = platform.lower()
        if platform_lower == "x":
            return {"__type": "x", "who_can_reply_post": "everyone"}
        elif platform_lower == "instagram":
            return {"__type": "instagram", "post_type": "post"}
        elif platform_lower in ("linkedin",):
            return {"__type": "linkedin"}
        elif platform_lower in ("threads",):
            return {"__type": "threads"}
        elif platform_lower in ("bluesky",):
            return {"__type": "bluesky"}
        elif platform_lower in ("mastodon",):
            return {"__type": "mastodon"}
        elif platform_lower in ("telegram",):
            return {"__type": "telegram"}
        else:
            # Generic fallback — Postiz will return an error if unsupported
            return {"__type": platform_lower}

    def _log_publish(
        self,
        business_slug: str,
        asset_id: int,
        platform: str,
        postiz_post_id: str = None,
        status: str = "pending",
        error: str = None,
        scheduled_at: str = None,
        posted_at: str = None,
    ) -> dict:
        """Log a publish attempt to the publish_log table."""
        conn = sqlite3.connect(self.db_path)
        ts = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO publish_log
               (business_slug, asset_id, platform, postiz_post_id, status,
                error_message, attempt_count, scheduled_at, posted_at,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)""",
            (business_slug, asset_id, platform, postiz_post_id, status,
             error, scheduled_at, posted_at, ts, ts),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM publish_log WHERE asset_id = ? AND platform = ? ORDER BY id DESC LIMIT 1",
            (asset_id, platform),
        ).fetchone()
        conn.close()

        if row:
            cols = [d[0] for d in sqlite3.connect(self.db_path).execute("SELECT * FROM publish_log LIMIT 0").description]
            return dict(zip(cols, row))
        return {}

    def get_publish_log(self, asset_id: int) -> list[dict]:
        """Get publish log entries for an asset."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM publish_log WHERE asset_id = ? ORDER BY id DESC",
            (asset_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def list_publish_log(self, business_slug: str = None, status: str = None) -> list[dict]:
        """List publish log entries, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM publish_log WHERE 1=1"
        params = []
        if business_slug:
            query += " AND business_slug = ?"
            params.append(business_slug)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC"
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def retry_failed(self, business_slug: str) -> list[dict]:
        """List failed publish attempts that should be retried."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM publish_log WHERE business_slug = ? AND status = 'failed' ORDER BY id ASC",
            (business_slug,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── Metrics (T4.2) ────────────────────────────────────────────────────

    def pull_post_metrics(self, publish_log_id: int, days: int = 7) -> list[dict]:
        """Pull analytics for a single published post from Postiz."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        log_row = conn.execute(
            "SELECT * FROM publish_log WHERE id = ?", (publish_log_id,)
        ).fetchone()
        conn.close()

        if not log_row:
            raise PostizError(f"Publish log entry {publish_log_id} not found")
        if not log_row["postiz_post_id"]:
            raise PostizError(f"No Postiz post ID for publish log {publish_log_id}")

        try:
            result = self._request("GET", f"/analytics/post/{log_row['postiz_post_id']}?date={days}")
        except PostizError as e:
            logger.warning(f"Failed to pull metrics for post {log_row['postiz_post_id']}: {e}")
            raise

        # result is an array of {label, data: [{total, date}], percentageChange}
        metrics_saved = []
        if isinstance(result, list):
            ts = datetime.now(timezone.utc).isoformat()
            conn = sqlite3.connect(self.db_path)
            for metric in result:
                label = metric.get("label", "")
                pct_change = metric.get("percentageChange")
                data_points = metric.get("data", [])
                for dp in data_points:
                    conn.execute(
                        """INSERT INTO post_metrics
                           (business_slug, asset_id, publish_log_id, platform,
                            metric_label, metric_value, metric_date,
                            percentage_change, pulled_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (log_row["business_slug"], log_row["asset_id"],
                         publish_log_id, log_row["platform"],
                         label, str(dp.get("total", "")),
                         dp.get("date", ""), pct_change, ts),
                    )
                    metrics_saved.append({
                        "label": label,
                        "value": dp.get("total"),
                        "date": dp.get("date"),
                        "percentage_change": pct_change,
                    })
            conn.commit()
            conn.close()

        return metrics_saved

    def pull_all_metrics(self, business_slug: str, days: int = 7) -> dict:
        """Pull metrics for all published posts of a business. Used by the nightly cron."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM publish_log WHERE business_slug = ? AND status IN ('posted', 'scheduled') AND postiz_post_id IS NOT NULL",
            (business_slug,),
        ).fetchall()
        conn.close()

        pulled = 0
        failed = 0
        for row in rows:
            try:
                self.pull_post_metrics(row["id"], days=days)
                pulled += 1
            except PostizError as e:
                logger.warning(f"Metrics pull failed for log {row['id']}: {e}")
                failed += 1

        return {"pulled": pulled, "failed": failed, "total": len(rows)}

    def get_metrics_summary(self, business_slug: str) -> dict:
        """Get a summary of latest metrics for a business."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # Get latest pull per asset per metric
        rows = conn.execute(
            """SELECT pm.* FROM post_metrics pm
               INNER JOIN (
                   SELECT asset_id, metric_label, MAX(pulled_at) as latest_pull
                   FROM post_metrics
                   WHERE business_slug = ?
                   GROUP BY asset_id, metric_label
               ) latest ON pm.asset_id = latest.asset_id
                   AND pm.metric_label = latest.metric_label
                   AND pm.pulled_at = latest.latest_pull
               WHERE pm.business_slug = ?
               ORDER BY pm.asset_id, pm.metric_label""",
            (business_slug, business_slug),
        ).fetchall()
        conn.close()

        # Group by asset
        by_asset = {}
        for r in rows:
            asset_id = r["asset_id"]
            if asset_id not in by_asset:
                by_asset[asset_id] = {}
            by_asset[asset_id][r["metric_label"]] = {
                "value": r["metric_value"],
                "date": r["metric_date"],
                "percentage_change": r["percentage_change"],
            }

        return by_asset

    # ── Health check ─────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check if Postiz is reachable and configured."""
        if not self.api_key:
            return False
        try:
            self._request("GET", "/integrations")
            return True
        except PostizError:
            return False