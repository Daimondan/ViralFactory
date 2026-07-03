"""
ViralFactory — Media Adapter

Per CORRECTION-pipeline-ux-and-media-generation-v1.0 F4:
- Config-driven model selection (from models.yaml media block)
- Every call logged to provenance (including USD cost)
- Content-hash caching for images (same prompt + model = cached file)
- Backend always flows through a 'backend' parameter (BYO-AI forward-compatibility)
- Image generation is synchronous-ish (seconds)
- Video generation is async: submit → job ID → poll → download

Auth: OPENROUTER_API_KEY env var (single bearer token for image + video APIs).

Media lands in data/media/<asset_id>/, recorded in the asset_media table.
"""

import hashlib
import json
import os
import time
from typing import Optional

import requests

# Support both package and direct imports
try:
    from .provenance import ProvenanceLog
except ImportError:
    from provenance import ProvenanceLog


# ─── Schema for asset_media table ─────────────────────────────────────────────

ASSET_MEDIA_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    kind TEXT NOT NULL,              -- image | video | vo | final_cut
    path TEXT NOT NULL,              -- file path relative to data/media/
    model TEXT NOT NULL,
    prompt TEXT,
    cost_usd REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES assets(id)
);

CREATE INDEX IF NOT EXISTS idx_asset_media_asset ON asset_media(asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_media_kind ON asset_media(kind);
"""

# ─── Schema for image cache ───────────────────────────────────────────────────

IMAGE_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS image_cache (
    cache_key TEXT PRIMARY KEY,       -- SHA-256 of (prompt + model)
    prompt TEXT NOT NULL,
    model TEXT NOT NULL,
    file_path TEXT NOT NULL,          -- path to the cached image file
    cost_usd REAL,
    created_at TEXT NOT NULL
);
"""


class MediaAdapterError(Exception):
    """Raised when the media adapter cannot complete a request."""
    pass


class MediaAdapter:
    """
    Config-driven media generation adapter (F4).

    Usage:
        adapter = MediaAdapter(models_config, db_path="data/viralfactory.db")
        image_path = adapter.generate_image(
            prompt="A sunset coastline, vertical 9:16",
            asset_id=42,
        )
        video_job = adapter.submit_video(
            prompt="Aerial drone shot of a beach, 10 seconds, vertical",
            asset_id=42,
        )
    """

    def __init__(self, models_config: dict, db_path: str = "data/viralfactory.db"):
        self.models_config = models_config
        self.db_path = db_path
        self.media_config = models_config.get("media", {})
        self.base_url = self.media_config.get("base_url", "https://openrouter.ai/api/v1")
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.provenance = ProvenanceLog(db_path)
        self._init_tables()

    def _init_tables(self):
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.executescript(ASSET_MEDIA_SCHEMA)
        conn.executescript(IMAGE_CACHE_SCHEMA)
        conn.commit()
        conn.close()

    def _ensure_media_dir(self, asset_id: int) -> str:
        """Ensure the media directory for an asset exists."""
        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)
        return media_dir

    def _log_provenance(self, model: str, prompt: str, cost_usd: float = None,
                        context: str = "", business_slug: str = None):
        """Log a media call to provenance."""
        self.provenance.log(
            input_hash=hashlib.sha256(prompt.encode()).hexdigest(),
            prompt_file="(media_adapter)",
            prompt_version="1.0",
            model=model,
            provider="openrouter",
            raw_output=f"cost: ${cost_usd or 0}",
            validated_output={"prompt": prompt[:500], "cost_usd": cost_usd},
            validator_verdict="valid",
            context=context,
            temperature=0,
            business_slug=business_slug,
        )

    def _record_media(self, asset_id: int, kind: str, path: str, model: str,
                      prompt: str, cost_usd: float = None):
        """Record generated media in the asset_media table."""
        import sqlite3
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT INTO asset_media
               (asset_id, kind, path, model, prompt, cost_usd, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (asset_id, kind, path, model, prompt[:2000], cost_usd, ts),
        )
        conn.commit()
        conn.close()

    def _get_cached_image(self, prompt: str, model: str) -> Optional[str]:
        """Check if an image for this prompt+model is already cached."""
        import sqlite3
        cache_key = hashlib.sha256(f"{prompt}|{model}".encode()).hexdigest()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT file_path FROM image_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        conn.close()
        if row and os.path.exists(row["file_path"]):
            return row["file_path"]
        return None

    def _cache_image(self, prompt: str, model: str, file_path: str, cost_usd: float = None):
        """Cache an image for dedup."""
        import sqlite3
        from datetime import datetime, timezone
        cache_key = hashlib.sha256(f"{prompt}|{model}".encode()).hexdigest()
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO image_cache
               (cache_key, prompt, model, file_path, cost_usd, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (cache_key, prompt[:2000], model, file_path, cost_usd, ts),
        )
        conn.commit()
        conn.close()

    # ── Image generation (synchronous-ish) ──

    def generate_image(
        self,
        prompt: str,
        asset_id: int,
        model: str = None,
        aspect_ratio: str = "9:16",
        context: str = "Image generation",
        business_slug: str = None,
    ) -> dict:
        """
        Generate an image via OpenRouter Image API.
        Returns dict: {path, model, prompt, cost_usd}.
        Raises MediaAdapterError on failure.

        Synchronous-ish (seconds). Content-hash cached — same prompt+model = cached file.
        """
        model = model or self.media_config.get("image_default", "google/gemini-3.1-flash-image")

        # Check cache
        cached = self._get_cached_image(prompt, model)
        if cached:
            self._log_provenance(model, prompt, cost_usd=0,
                                 context=f"{context} (cached)", business_slug=business_slug)
            return {"path": cached, "model": model, "prompt": prompt, "cost_usd": 0, "cached": True}

        if not self.api_key:
            raise MediaAdapterError("OPENROUTER_API_KEY not set — cannot generate images")

        media_dir = self._ensure_media_dir(asset_id)
        url = f"{self.base_url}/images"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
        }

        start = time.time()
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            response.raise_for_status()
        except requests.RequestException as e:
            self._log_provenance(model, prompt, context=f"{context} (failed)", business_slug=business_slug)
            raise MediaAdapterError(f"Image API call failed: {e}")

        data = response.json()

        # Extract image URL from response
        # OpenRouter returns image data or URL
        image_url = data.get("data", {}).get("url") or data.get("url")
        image_b64 = data.get("data", {}).get("b64_json") or data.get("b64_json")
        cost_usd = data.get("cost", 0)

        if not image_url and not image_b64:
            raise MediaAdapterError(f"Image API returned no image data: {json.dumps(data)[:500]}")

        # Download/save the image
        import hashlib as h
        file_hash = h.sha256(prompt.encode()).hexdigest()[:16]
        ext = "png"  # default; could detect from content-type
        filename = f"image_{file_hash}.{ext}"
        file_path = os.path.join(media_dir, filename)

        if image_url:
            # Download the image
            img_response = requests.get(image_url, timeout=60)
            img_response.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(img_response.content)
        elif image_b64:
            import base64
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(image_b64))

        # Cache and record
        self._cache_image(prompt, model, file_path, cost_usd)
        self._record_media(asset_id, "image", file_path, model, prompt, cost_usd)
        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=context, business_slug=business_slug)

        return {"path": file_path, "model": model, "prompt": prompt, "cost_usd": cost_usd}

    # ── Video generation (async) ──

    def submit_video(
        self,
        prompt: str,
        asset_id: int,
        model: str = None,
        aspect_ratio: str = "9:16",
        duration: int = 5,
        context: str = "Video generation",
        business_slug: str = None,
    ) -> dict:
        """
        Submit a video generation job to OpenRouter Video API (async).
        Returns dict: {job_id, model, prompt, status, external_job_id}.

        The caller is responsible for polling check_video_job() or the worker
        framework handles it via the jobs table.
        """
        model = model or self.media_config.get("video_default", "google/veo-3.1-lite")

        if not self.api_key:
            raise MediaAdapterError("OPENROUTER_API_KEY not set — cannot generate video")

        url = f"{self.base_url}/videos"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.RequestException as e:
            self._log_provenance(model, prompt, context=f"{context} (submit failed)", business_slug=business_slug)
            raise MediaAdapterError(f"Video API submit failed: {e}")

        data = response.json()
        external_job_id = data.get("id") or data.get("job_id")
        cost_usd = data.get("cost", 0)

        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=f"{context} (submitted, ext_job={external_job_id})",
                            business_slug=business_slug)

        return {
            "model": model,
            "prompt": prompt,
            "external_job_id": external_job_id,
            "status": "submitted",
            "cost_usd": cost_usd,
        }

    def check_video_job(self, external_job_id: str) -> dict:
        """
        Poll a video generation job. Returns:
        {status: "processing"|"completed"|"failed", download_url, cost_usd}
        """
        if not self.api_key:
            raise MediaAdapterError("OPENROUTER_API_KEY not set")

        url = f"{self.base_url}/videos/{external_job_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            raise MediaAdapterError(f"Video job poll failed: {e}")

        data = response.json()
        status = data.get("status", "processing")
        download_url = data.get("download_url") or data.get("url")
        cost_usd = data.get("cost", 0)

        return {
            "status": status,
            "download_url": download_url if status == "completed" else None,
            "cost_usd": cost_usd,
        }

    def download_video(self, external_job_id: str, download_url: str, asset_id: int,
                       model: str, prompt: str, cost_usd: float = 0,
                       business_slug: str = None) -> str:
        """Download a completed video and record it."""
        media_dir = self._ensure_media_dir(asset_id)
        file_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        filename = f"video_{file_hash}.mp4"
        file_path = os.path.join(media_dir, filename)

        response = requests.get(download_url, timeout=120)
        response.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(response.content)

        self._record_media(asset_id, "video", file_path, model, prompt, cost_usd)
        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=f"Video download (ext_job={external_job_id})",
                            business_slug=business_slug)

        return file_path

    # ── Discovery ──

    def list_image_models(self) -> list[dict]:
        """Discover available image models via OpenRouter API."""
        if not self.api_key:
            return []
        url = f"{self.base_url}/images/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get("data", [])
        except requests.RequestException:
            return []

    def list_video_models(self) -> list[dict]:
        """Discover available video models via OpenRouter API."""
        if not self.api_key:
            return []
        url = f"{self.base_url}/videos/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json().get("data", [])
        except requests.RequestException:
            return []

    # ── Querying stored media ──

    def list_asset_media(self, asset_id: int, kind: str = None) -> list[dict]:
        """List all media for an asset, optionally filtered by kind."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if kind:
            rows = conn.execute(
                "SELECT * FROM asset_media WHERE asset_id = ? AND kind = ? ORDER BY id ASC",
                (asset_id, kind),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM asset_media WHERE asset_id = ? ORDER BY id ASC",
                (asset_id,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
