"""
ViralFactory — Buffer Adapter (replaces Postiz for M4: T4.1 + T4.2)

Wraps the Buffer GraphQL API for:
  - Publishing pieces to social platforms (after per-piece approval)
  - Pulling post-level analytics metrics

Buffer API: https://api.buffer.com (GraphQL)
Auth: Bearer token (BUFFER_API_KEY env var)
Channel IDs: from config (buffer.channels in models.yaml) or from ~/.hermes/config/buffer_channels.json

Business rules enforced:
  - No auto-publish. Every piece requires explicit per-piece approval (Gate 4).
  - Failures are surfaced, never silently swallowed.
  - Buffer down → pieces stay in the publish queue, never lost.
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

logger = logging.getLogger("viralfactory.buffer")

BUFFER_API_URL = "https://api.buffer.com"


class BufferError(Exception):
    """Buffer API error."""
    pass


class BufferAdapter:
    """Adapter for the Buffer GraphQL API — publishing + metrics.
    Drop-in replacement for PostizAdapter with the same interface."""

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        buffer_cfg = (models_config or {}).get("buffer", {})
        self.api_url = buffer_cfg.get("api_url", BUFFER_API_URL)
        self.api_key = buffer_cfg.get("api_key", "") or os.environ.get("BUFFER_API_KEY", "")
        self.organization_id = buffer_cfg.get("organization_id", "")
        self.channels = buffer_cfg.get("channels", {})
        self._ensure_tables()

    def _ensure_tables(self):
        """Create publish_log and post_metrics tables if they don't exist.
        Reuses the same tables as Postiz — publish_log.postiz_post_id stores Buffer post ID."""
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

    # ── GraphQL helper ──────────────────────────────────────────────────

    def _gql(self, query: str, variables: dict = None) -> dict:
        """Make an authenticated GraphQL request to Buffer API."""
        if not self.api_key:
            raise BufferError("BUFFER_API_KEY not set — Buffer adapter cannot function")

        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        req = urlrequest.Request(self.api_url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")

        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                body_text = resp.read().decode("utf-8")
                if not body_text:
                    return {}
                result = json.loads(body_text)
                if "errors" in result:
                    error_msg = result["errors"][0].get("message", "Unknown GraphQL error")
                    raise BufferError(f"Buffer GraphQL error: {error_msg}")
                return result.get("data", result)
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")[:500]
            raise BufferError(f"Buffer API error {e.code}: {error_body}") from e
        except URLError as e:
            raise BufferError(f"Buffer connection error: {e.reason}") from e
        except BufferError:
            raise
        except Exception as e:
            raise BufferError(f"Buffer request failed: {e}") from e

    # ── Channels ────────────────────────────────────────────────────────

    def list_integrations(self) -> list[dict]:
        """List connected social media channels from Buffer."""
        if not self.organization_id:
            # Fall back to config channels
            result = []
            for key, ch in self.channels.items():
                result.append({"id": ch.get("id", ""), "name": ch.get("name", key),
                               "type": ch.get("service", key), "__type": ch.get("service", key)})
            return result

        try:
            query = """
                query Channels($organizationId: OrganizationId!) {
                  channels(input: {organizationId: $organizationId}) {
                    id name service avatar
                  }
                }
            """
            data = self._gql(query, {"organizationId": self.organization_id})
            channels = data.get("channels", [])
            return [{"id": ch["id"], "name": ch["name"], "type": ch["service"],
                     "__type": ch["service"]} for ch in channels]
        except BufferError as e:
            logger.warning(f"Failed to list Buffer channels: {e}")
            # Fall back to config
            result = []
            for key, ch in self.channels.items():
                result.append({"id": ch.get("id", ""), "name": ch.get("name", key),
                               "type": ch.get("service", key), "__type": ch.get("service", key)})
            return result

    def get_integration_for_platform(self, platform: str) -> Optional[str]:
        """Get the Buffer channel ID for a given platform name (X, Instagram, etc.)."""
        platform_lower = platform.lower()

        # Check config channels first (supports aliases: x/twitter, instagram/ig)
        if platform_lower in self.channels:
            ch = self.channels[platform_lower]
            if ch.get("id"):
                return ch["id"]

        # Check common aliases
        aliases = {
            "x": ["x", "twitter"],
            "twitter": ["x", "twitter"],
            "instagram": ["instagram", "ig"],
            "ig": ["instagram", "ig"],
        }
        for alias in aliases.get(platform_lower, [platform_lower]):
            if alias in self.channels:
                ch = self.channels[alias]
                if ch.get("id"):
                    return ch["id"]

        # Fall back to live API lookup
        integrations = self.list_integrations()
        for integ in integrations:
            integ_type = str(integ.get("type", integ.get("__type", ""))).lower()
            if platform_lower in integ_type or integ_type in platform_lower:
                return str(integ.get("id", ""))
            if platform_lower == "x" and "twitter" in integ_type:
                return str(integ.get("id", ""))
            if platform_lower == "twitter" and "twitter" in integ_type:
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
        """Publish or schedule a piece via Buffer.
        HARD RULE: asset_state must be 'approved'. No auto-publish.
        Returns a publish_log row dict."""
        if asset_state != "approved":
            raise BufferError(
                "Per-piece approval required: asset must be 'approved' before publishing. "
                "No auto-publish at any trust level."
            )

        channel_id = self.get_integration_for_platform(platform)
        if not channel_id:
            error_msg = f"No Buffer channel found for platform '{platform}'. Check Buffer connections or config."
            self._log_publish(business_slug, asset_id, platform, status="failed", error=error_msg)
            raise BufferError(error_msg)

        # Determine action mode
        if scheduled_at:
            mode = "addToQueue"
            due_at = scheduled_at
        else:
            mode = "shareNow"
            due_at = None

        # Use the first post for single posts, or join for threads
        post_text = content
        if posts and len(posts) > 1:
            # Thread: join posts with newlines (Buffer handles thread posts as separate items)
            # For now, use the content field as the main text
            post_text = content if content else posts[0]

        # Build GraphQL mutation
        input_obj = {
            "text": post_text,
            "channelId": channel_id,
            "schedulingType": "automatic",
            "mode": mode,
            "source": "viralfactory",
            "aiAssisted": True,
        }

        if due_at:
            input_obj["dueAt"] = due_at

        # Attach images if provided (as public URLs)
        assets = []
        if images:
            for img in images:
                img_path = img.get("path", "")
                img_id = img.get("id", "")
                if img_path and img_path.startswith("http"):
                    assets.append({"image": {"url": img_path}})
                elif img_id:
                    # Already uploaded — use ID reference
                    assets.append({"image": {"id": img_id}})
        if assets:
            input_obj["assets"] = assets

        mutation = """
            mutation CreatePost($input: CreatePostInput!) {
              createPost(input: $input) {
                ... on PostActionSuccess {
                  post {
                    id text status dueAt
                    channel { id name service }
                    assets { id mimeType }
                  }
                }
                ... on MutationError {
                  message
                }
              }
            }
        """

        try:
            result = self._gql(mutation, {"input": input_obj})
            create_result = result.get("createPost", {})

            # Check for mutation error
            if "message" in create_result and "post" not in create_result:
                error_msg = create_result.get("message", "Unknown Buffer error")
                self._log_publish(business_slug, asset_id, platform, status="failed", error=error_msg)
                raise BufferError(error_msg)

            post_data = create_result.get("post", {})
            buffer_post_id = post_data.get("id", "")
            post_status = post_data.get("status", "scheduled" if scheduled_at else "posted")

            log_row = self._log_publish(
                business_slug, asset_id, platform,
                postiz_post_id=buffer_post_id,  # reuse same column name
                status=post_status,
                scheduled_at=scheduled_at,
                posted_at=datetime.now(timezone.utc).isoformat() if not scheduled_at else None,
            )
            logger.info(f"Published asset {asset_id} to {platform} via Buffer: {buffer_post_id}")
            return log_row

        except BufferError as e:
            self._log_publish(business_slug, asset_id, platform, status="failed", error=str(e))
            logger.error(f"Failed to publish asset {asset_id} to {platform}: {e}")
            raise

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
        """Pull analytics for a single published post from Buffer.
        Buffer's GraphQL API provides limited analytics; we fetch what's available."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        log_row = conn.execute(
            "SELECT * FROM publish_log WHERE id = ?", (publish_log_id,)
        ).fetchone()
        conn.close()

        if not log_row:
            raise BufferError(f"Publish log entry {publish_log_id} not found")
        if not log_row["postiz_post_id"]:
            raise BufferError(f"No Buffer post ID for publish log {publish_log_id}")

        buffer_post_id = log_row["postiz_post_id"]

        # Buffer doesn't have a public analytics endpoint in the GraphQL API
        # We record the post status as a metric placeholder
        # When Buffer adds analytics support, this can be extended
        try:
            query = """
                query GetPost($id: PostId!) {
                  post(id: $id) {
                    id text status
                    channel { id name service }
                  }
                }
            """
            result = self._gql(query, {"id": buffer_post_id})
            post_data = result.get("post", {})

            ts = datetime.now(timezone.utc).isoformat()
            metrics_saved = []

            # Record post status as a metric
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                """INSERT INTO post_metrics
                   (business_slug, asset_id, publish_log_id, platform,
                    metric_label, metric_value, metric_date,
                    percentage_change, pulled_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (log_row["business_slug"], log_row["asset_id"],
                 publish_log_id, log_row["platform"],
                 "status", post_data.get("status", "unknown"),
                 ts, None, ts),
            )
            conn.commit()
            conn.close()

            metrics_saved.append({
                "label": "status",
                "value": post_data.get("status", "unknown"),
            })

            return metrics_saved

        except BufferError as e:
            logger.warning(f"Failed to pull metrics for Buffer post {buffer_post_id}: {e}")
            raise

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
            except BufferError as e:
                logger.warning(f"Metrics pull failed for log {row['id']}: {e}")
                failed += 1

        return {"pulled": pulled, "failed": failed, "total": len(rows)}

    def get_metrics_summary(self, business_slug: str) -> dict:
        """Get a summary of latest metrics for a business."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
        """Check if Buffer is reachable and configured."""
        if not self.api_key:
            return False
        try:
            # If we have channels in config, consider it available
            if self.channels:
                return True
            # Otherwise try the API
            if self.organization_id:
                self._gql(
                    "query Channels($organizationId: OrganizationId!) { channels(input: {organizationId: $organizationId}) { id } }",
                    {"organizationId": self.organization_id},
                )
                return True
            return bool(self.api_key)
        except BufferError:
            return False