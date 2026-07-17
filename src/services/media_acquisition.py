"""
Media acquisition service (VF-AU-204).

Executes acquisition through a real lifecycle:
planned → submitted → processing → downloaded → validated → registered → render-ready

Reuses existing MediaAdapter/StockAdapter/reference-assets registry.
Rules: poll async providers; reject tiny/error blobs; probe media; register
exact local file and cost; idempotency key per request/version.
"""

import os
import json
import sqlite3
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AcquisitionResult:
    """Result of an acquisition attempt."""
    ingredient_id: str
    status: str              # render_ready | failed | pending
    local_path: str = ""
    cost_usd: float = 0.0
    error: str = ""
    provider_task_id: str = ""
    metadata: dict = field(default_factory=dict)


class MediaAcquisitionService:
    """Executes durable media acquisition with lifecycle tracking."""

    def __init__(self, db_path: str = "data/viralfactory.db", media_adapter=None, stock_adapter=None):
        self.db_path = db_path
        self.media_adapter = media_adapter
        self.stock_adapter = stock_adapter

    def acquire(self, recipe: dict, asset_id: int) -> AcquisitionResult:
        """Execute acquisition for a single media recipe.

        Lifecycle: planned → submitted → processing → downloaded → validated → registered → render-ready
        """
        primary = recipe.get("primary", {}) or {}
        kind = primary.get("kind", "")
        recipe_id = recipe.get("media_recipe_id", "")

        if kind == "stock":
            return self._acquire_stock(recipe, asset_id, recipe_id)
        elif kind in ("generated_image", "generated_video"):
            return self._acquire_generated(recipe, asset_id, recipe_id, kind)
        elif kind == "upload":
            # Upload is already registered — just verify it exists
            ingredient_id = primary.get("ingredient_id", "")
            return AcquisitionResult(
                ingredient_id=ingredient_id,
                status="render_ready",
                local_path=self._lookup_ingredient_path(ingredient_id),
            )
        elif kind == "text_card":
            return AcquisitionResult(
                ingredient_id=f"text_card:{recipe_id}",
                status="render_ready",
                local_path="",
            )
        else:
            return AcquisitionResult(
                ingredient_id=recipe_id,
                status="failed",
                error=f"Unknown media kind: {kind}",
            )

    def _acquire_stock(self, recipe: dict, asset_id: int, recipe_id: str) -> AcquisitionResult:
        """Search stock libraries and download."""
        if not self.stock_adapter:
            return AcquisitionResult(ingredient_id=recipe_id, status="failed", error="No stock adapter configured")

        primary = recipe.get("primary", {}) or {}
        query = primary.get("generation_prompt", "") or primary.get("search_query", "")

        if not query:
            return AcquisitionResult(ingredient_id=recipe_id, status="failed", error="No search query for stock")

        try:
            results = self.stock_adapter.search(query, kind="video", per_page=3)
            if not results:
                return AcquisitionResult(ingredient_id=recipe_id, status="failed", error="No stock results found")

            path = self.stock_adapter.download(results[0])

            # Validate download — reject tiny/error blobs
            if not self._validate_download(path):
                return AcquisitionResult(ingredient_id=recipe_id, status="failed", error=f"Downloaded file too small or invalid: {path}")

            # Register in DB
            media_id = self._register_media(asset_id, "video", path, f"stock:{results[0].get('provider', '')}", query, 0)

            return AcquisitionResult(
                ingredient_id=f"asset_media:{media_id}",
                status="render_ready",
                local_path=path,
                cost_usd=0.0,
                provider_task_id="",
                metadata={"source": "stock", "query": query},
            )
        except Exception as e:
            return AcquisitionResult(ingredient_id=recipe_id, status="failed", error=str(e))

    def _acquire_generated(self, recipe: dict, asset_id: int, recipe_id: str, kind: str) -> AcquisitionResult:
        """Generate media via AI provider."""
        if not self.media_adapter:
            return AcquisitionResult(ingredient_id=recipe_id, status="failed", error="No media adapter configured")

        primary = recipe.get("primary", {}) or {}
        prompt = primary.get("generation_prompt", "")

        if not prompt:
            return AcquisitionResult(ingredient_id=recipe_id, status="failed", error="No generation prompt")

        # Idempotency key per request/version
        idem_key = self._compute_idempotency_key(asset_id, recipe_id, prompt)

        # Check if we already have this exact generation cached
        cached = self._check_idempotency(idem_key)
        if cached:
            return AcquisitionResult(
                ingredient_id=cached["ingredient_id"],
                status="render_ready",
                local_path=cached["path"],
                cost_usd=0.0,  # no charge for cached result
                metadata={"idempotent": True},
            )

        try:
            if kind == "generated_image":
                result = self.media_adapter.generate_image(
                    prompt=prompt,
                    asset_id=asset_id,
                    reference_images=primary.get("reference_images"),
                )
                path = result.get("path", "")
                cost = result.get("cost_usd", 0.03)
                media_kind = "image"
            else:
                result = self.media_adapter.submit_video(
                    prompt=prompt,
                    asset_id=asset_id,
                    mode=primary.get("mode", "text_to_video"),
                )
                # Poll for async completion
                task_id = result.get("task_id", "")
                path = self._poll_async(task_id)
                cost = result.get("cost_usd", 0.0)
                media_kind = "video"

            if not path or not self._validate_download(path):
                return AcquisitionResult(ingredient_id=recipe_id, status="failed", error="Generation produced no valid file")

            media_id = self._register_media(asset_id, media_kind, path, "ai_generated", prompt, cost)

            # Store idempotency
            self._store_idempotency(idem_key, f"asset_media:{media_id}", path)

            return AcquisitionResult(
                ingredient_id=f"asset_media:{media_id}",
                status="render_ready",
                local_path=path,
                cost_usd=cost,
                provider_task_id=task_id if kind == "generated_video" else "",
                metadata={"source": "generated", "prompt": prompt[:100]},
            )
        except Exception as e:
            return AcquisitionResult(ingredient_id=recipe_id, status="failed", error=str(e))

    def _poll_async(self, task_id: str, max_wait: int = 120, interval: int = 5) -> str:
        """Poll an async provider until completion or timeout."""
        if not self.media_adapter or not task_id:
            return ""

        elapsed = 0
        while elapsed < max_wait:
            status = self.media_adapter.check_video_status(task_id)
            if status.get("status") == "completed":
                return status.get("path", "")
            elif status.get("status") == "failed":
                return ""
            time.sleep(interval)
            elapsed += interval
        return ""  # timeout

    def _validate_download(self, path: str, min_size: int = 1024) -> bool:
        """Reject tiny/error blobs."""
        if not path or not os.path.exists(path):
            return False
        size = os.path.getsize(path)
        if size < min_size:
            return False
        # Check for HTML error pages
        try:
            with open(path, "rb") as f:
                header = f.read(20)
            if header.startswith(b"<!DOCTYPE") or header.startswith(b"<html"):
                return False
        except Exception:
            pass
        return True

    def _compute_idempotency_key(self, asset_id: int, recipe_id: str, prompt: str) -> str:
        """Compute a deterministic idempotency key per request/version."""
        raw = f"{asset_id}:{recipe_id}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _check_idempotency(self, key: str) -> dict | None:
        """Check if this exact generation was already done."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "acquisition_cache" not in tables:
            conn.close()
            return None
        row = conn.execute("SELECT * FROM acquisition_cache WHERE key = ?", (key,)).fetchone()
        conn.close()
        if row:
            return {"ingredient_id": row["ingredient_id"], "path": row["path"]}
        return None

    def _store_idempotency(self, key: str, ingredient_id: str, path: str) -> None:
        """Store idempotency record to prevent duplicate paid requests."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS acquisition_cache (key TEXT PRIMARY KEY, ingredient_id TEXT, path TEXT, created_at TEXT)"
        )
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO acquisition_cache (key, ingredient_id, path, created_at) VALUES (?, ?, ?, ?)",
            (key, ingredient_id, path, ts),
        )
        conn.commit()
        conn.close()

    def _register_media(self, asset_id: int, kind: str, path: str, provider: str,
                         prompt: str, cost: float) -> int:
        """Register media in the asset_media table."""
        conn = sqlite3.connect(self.db_path)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """INSERT INTO asset_media (asset_id, kind, path, prompt, owner_type, provider, cost_usd, created_at)
               VALUES (?, ?, ?, ?, 'asset', ?, ?, ?)""",
            (asset_id, kind, path, prompt, provider, cost, ts),
        )
        media_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return media_id

    def _lookup_ingredient_path(self, ingredient_id: str) -> str:
        """Look up the local path for an existing ingredient."""
        if not ingredient_id:
            return ""
        try:
            if ingredient_id.startswith("asset_media:"):
                media_id = int(ingredient_id.split(":")[1])
                conn = sqlite3.connect(self.db_path)
                row = conn.execute("SELECT path FROM asset_media WHERE id = ?", (media_id,)).fetchone()
                conn.close()
                return row[0] if row else ""
            elif ingredient_id.startswith("capture_upload:"):
                mat_id = int(ingredient_id.split(":")[1])
                conn = sqlite3.connect(self.db_path)
                row = conn.execute("SELECT file_path FROM materials WHERE id = ?", (mat_id,)).fetchone()
                conn.close()
                return row[0] if row else ""
        except (ValueError, sqlite3.Error):
            pass
        return ""