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

# F4 (CORRECTION-feedback-plumbing): owner_type column replaces the
# synthetic draft_id + 100000 scheme for draft-stage visual previews.
OWNER_TYPE_MIGRATION = """
-- Migration: add owner_type column if not present
-- Runs idempotently in _init_tables via PRAGMA table_info check
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


def _veo_clamp_duration(duration: int) -> int:
    """Veo 3.1 Fast only accepts even-numbered durations (4, 6, 8).
    Odd values (5, 7) return 400 'out of bound' despite the docs saying 4-8.
    Clamp to the nearest valid value."""
    d = int(duration)
    if d in (4, 6, 8):
        return d
    # Round to nearest even value in [4, 8]
    if d < 5:
        return 4
    elif d < 7:
        return 6
    else:
        return 8


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

        # F4 (CORRECTION-feedback-plumbing): add owner_type column if missing
        cols = [row[1] for row in conn.execute("PRAGMA table_info(asset_media)").fetchall()]
        if "owner_type" not in cols:
            conn.execute("ALTER TABLE asset_media ADD COLUMN owner_type TEXT NOT NULL DEFAULT 'asset'")
            conn.commit()

            # Migrate legacy rows: asset_id >= 100000 were draft visuals
            # (synthetic ID = draft_id + 100000). Convert them to owner_type='draft'
            # and set asset_id = asset_id - 100000.
            legacy_rows = conn.execute(
                "SELECT id, asset_id FROM asset_media WHERE asset_id >= 100000"
            ).fetchall()
            for row_id, old_asset_id in legacy_rows:
                new_asset_id = old_asset_id - 100000
                conn.execute(
                    "UPDATE asset_media SET owner_type = 'draft', asset_id = ? WHERE id = ?",
                    (new_asset_id, row_id),
                )
            if legacy_rows:
                conn.commit()

        conn.commit()
        conn.close()

    def _ensure_media_dir(self, asset_id: int) -> str:
        """Ensure the media directory for an asset exists."""
        media_dir = os.path.join("data", "media", str(asset_id))
        os.makedirs(media_dir, exist_ok=True)
        return media_dir

    def _compute_cost(self, model: str, kind: str, duration_seconds: int = None) -> float:
        """Compute the USD cost of a media generation from config (cost_per_image_usd /
        cost_per_second_usd). Returns 0 if the model isn't found in config.
        This is the deterministic source of truth for cost — APIs often return 0."""
        media = self.media_config
        if kind == "image":
            for gen in media.get("image_generators", []):
                if gen.get("name") == model or gen.get("endpoint") == model:
                    return float(gen.get("cost_per_image_usd", 0))
        elif kind == "video":
            for gen in media.get("video_generators", []):
                if gen.get("name") == model or gen.get("endpoint") == model:
                    rate = float(gen.get("cost_per_second_usd", 0))
                    return rate * (duration_seconds or 5)
        return 0

    def _log_provenance(self, model: str, prompt: str, cost_usd: float = None,
                        context: str = "", business_slug: str = None,
                        provider: str = "openrouter"):
        """Log a media call to provenance."""
        self.provenance.log(
            input_hash=hashlib.sha256(prompt.encode()).hexdigest(),
            prompt_file="(media_adapter)",
            prompt_version="1.0",
            model=model,
            provider=provider,
            raw_output=f"cost: ${cost_usd or 0}",
            validated_output={"prompt": prompt[:500], "cost_usd": cost_usd},
            validator_verdict="valid",
            context=context,
            temperature=0,
            business_slug=business_slug,
        )

    def _record_media(self, asset_id: int, kind: str, path: str, model: str,
                      prompt: str, cost_usd: float = None, owner_type: str = "asset"):
        """Record generated media in the asset_media table."""
        import sqlite3
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        # Check if owner_type column exists (defensive for old DBs)
        cols = [row[1] for row in conn.execute("PRAGMA table_info(asset_media)").fetchall()]
        if "owner_type" in cols:
            cursor = conn.execute(
                """INSERT INTO asset_media
                   (asset_id, kind, path, model, prompt, cost_usd, created_at, owner_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, kind, path, model, prompt[:2000], cost_usd, ts, owner_type),
            )
        else:
            cursor = conn.execute(
                """INSERT INTO asset_media
                   (asset_id, kind, path, model, prompt, cost_usd, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (asset_id, kind, path, model, prompt[:2000], cost_usd, ts),
            )
        media_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return media_id

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

    def _resolve_fal_image_generator(self, model: str) -> dict:
        """Find a fal image generator config by name or endpoint."""
        for gen in self.media_config.get("image_generators", []):
            if gen.get("provider") == "fal" and (gen.get("name") == model or gen.get("endpoint") == model):
                return gen
        return None

    def _resolve_fal_video_generator(self, model: str) -> dict:
        """Find a fal video generator config by name or endpoint."""
        for gen in self.media_config.get("video_generators", []):
            if gen.get("provider") == "fal" and (gen.get("name") == model or gen.get("endpoint") == model):
                return gen
        return None

    def _get_fal_api_key(self, gen_config: dict) -> str:
        """Get the FAL API key from env var specified in config.
        fal_client uses FAL_KEY (not FAL_API_KEY). We check both for compatibility.
        """
        env_var = gen_config.get("api_key_env", "FAL_KEY") if gen_config else "FAL_KEY"
        return os.environ.get(env_var, "") or os.environ.get("FAL_KEY", "")

    def generate_image(
        self,
        prompt: str,
        asset_id: int,
        model: str = None,
        aspect_ratio: str = "9:16",
        context: str = "Image generation",
        business_slug: str = None,
        owner_type: str = "asset",
        reference_images: list = None,
    ) -> dict:
        """
        Generate an image. Supports fal.ai (reference-conditioned) and
        OpenRouter (text-only) providers.

        Args:
            reference_images: List of local file paths to use as reference
                             (fal providers only). Files are uploaded to fal
                             storage and passed as reference_image URLs.

        Returns dict: {path, model, prompt, cost_usd}.
        Raises MediaAdapterError on failure.

        Synchronous-ish (seconds). Content-hash cached — same prompt+model = cached file.
        """
        model = model or self.media_config.get("image_default", "google/gemini-3.1-flash-image")

        # Check if this is a fal provider
        fal_gen = self._resolve_fal_image_generator(model)
        if fal_gen:
            return self._generate_image_fal(
                prompt=prompt, asset_id=asset_id, model=model,
                fal_gen=fal_gen, aspect_ratio=aspect_ratio,
                context=context, business_slug=business_slug,
                owner_type=owner_type, reference_images=reference_images,
            )

        # Fall back to OpenRouter path (existing code)
        return self._generate_image_openrouter(
            prompt=prompt, asset_id=asset_id, model=model,
            aspect_ratio=aspect_ratio, context=context,
            business_slug=business_slug, owner_type=owner_type,
        )

    def _generate_image_fal(
        self,
        prompt: str,
        asset_id: int,
        model: str,
        fal_gen: dict,
        aspect_ratio: str,
        context: str,
        business_slug: str,
        owner_type: str,
        reference_images: list,
    ) -> dict:
        """Generate an image via fal.ai provider."""
        import fal_client

        api_key = self._get_fal_api_key(fal_gen)
        if not api_key:
            raise MediaAdapterError(f"FAL_KEY not set — cannot generate image with fal provider '{model}'")

        endpoint = fal_gen.get("endpoint", model)

        # Build cache key including reference images
        cache_key_parts = [prompt, model]
        if reference_images:
            for ref in reference_images:
                cache_key_parts.append(os.path.basename(ref))
        cache_key = hashlib.sha256("|".join(cache_key_parts).encode()).hexdigest()

        # Check cache
        cached = self._get_cached_image(prompt, model)
        if cached:
            self._log_provenance(model, prompt, cost_usd=0,
                                 context=f"{context} (cached)", business_slug=business_slug,
                                 provider="fal")
            return {"path": cached, "model": model, "prompt": prompt, "cost_usd": 0, "cached": True}

        media_dir = self._ensure_media_dir(asset_id)

        # Upload reference images if provided
        ref_urls = []
        if reference_images:
            for ref_path in reference_images:
                if os.path.exists(ref_path):
                    try:
                        url = fal_client.upload_file(ref_path)
                        ref_urls.append(url)
                    except Exception as e:
                        raise MediaAdapterError(f"Failed to upload reference image {ref_path}: {e}")
                else:
                    raise MediaAdapterError(f"Reference image not found: {ref_path}")

        # Build fal arguments
        arguments = {"prompt": prompt}
        if ref_urls:
            # fal image endpoints accept reference images as image_url or reference_images
            # The exact parameter name depends on the endpoint. We use "image_url" for
            # single ref and "reference_images" for multiple. The endpoint config
            # can specify the parameter name via "ref_param" if needed.
            ref_param = fal_gen.get("ref_param", "image_url" if len(ref_urls) == 1 else "reference_images")
            arguments[ref_param] = ref_urls[0] if len(ref_urls) == 1 else ref_urls

        # Add aspect ratio if the endpoint supports it
        if aspect_ratio:
            arguments["aspect_ratio"] = aspect_ratio

        start = time.time()
        try:
            result = fal_client.run(endpoint, arguments=arguments, timeout=120)
        except Exception as e:
            self._log_provenance(model, prompt, context=f"{context} (failed)",
                                 business_slug=business_slug, provider="fal")
            raise MediaAdapterError(f"fal.ai image generation failed: {e}")

        # Extract image URL from fal response
        # fal responses typically have: {images: [{url: "..."}]} or {image: {url: "..."}}
        image_url = None
        if isinstance(result, dict):
            images = result.get("images", [])
            if isinstance(images, list) and len(images) > 0:
                image_url = images[0].get("url") if isinstance(images[0], dict) else images[0]
            elif "image" in result:
                img = result["image"]
                image_url = img.get("url") if isinstance(img, dict) else img
            elif "url" in result:
                image_url = result["url"]

        if not image_url:
            raise MediaAdapterError(f"fal.ai returned no image: {json.dumps(result)[:500]}")

        # Download the image
        file_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        filename = f"image_{file_hash}.png"
        file_path = os.path.join(media_dir, filename)

        img_response = requests.get(image_url, timeout=60)
        img_response.raise_for_status()
        with open(file_path, "wb") as f:
            f.write(img_response.content)

        cost_usd = fal_gen.get("cost_per_image_usd", 0)

        self._cache_image(prompt, model, file_path, cost_usd)
        self._record_media(asset_id, "image", file_path, model, prompt, cost_usd, owner_type=owner_type)
        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=context, business_slug=business_slug,
                            provider="fal")

        print(f"[media] Image generated (fal): {model} — ${cost_usd:.4f} — {file_path}")
        return {"path": file_path, "model": model, "prompt": prompt, "cost_usd": cost_usd}

    def _generate_image_openrouter(
        self,
        prompt: str,
        asset_id: int,
        model: str,
        aspect_ratio: str,
        context: str,
        business_slug: str,
        owner_type: str,
    ) -> dict:
        """Generate an image via OpenRouter Image API (legacy path)."""
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
        # OpenRouter Image API returns: {"data": [{"b64_json": "..."} or {"url": "..."}]}
        # The data field is a LIST of image objects, not a dict.
        image_url = None
        image_b64 = None
        cost_usd = data.get("cost", 0)

        data_items = data.get("data", [])
        if isinstance(data_items, list) and len(data_items) > 0:
            first = data_items[0]
            if isinstance(first, dict):
                image_url = first.get("url")
                image_b64 = first.get("b64_json")
        elif isinstance(data_items, dict):
            # Some models might return a dict directly
            image_url = data_items.get("url")
            image_b64 = data_items.get("b64_json")

        # Also check top-level fields as fallback
        if not image_url:
            image_url = data.get("url")
        if not image_b64:
            image_b64 = data.get("b64_json")

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
        cost_usd = data.get("cost", 0)
        # If the API didn't return a cost, compute from config
        if not cost_usd:
            cost_usd = self._compute_cost(model, "image")

        self._cache_image(prompt, model, file_path, cost_usd)
        self._record_media(asset_id, "image", file_path, model, prompt, cost_usd, owner_type=owner_type)
        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=context, business_slug=business_slug)

        print(f"[media] Image generated: {model} — ${cost_usd:.4f} — {file_path}")
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
        provider: str = None,
        source_image: str = None,
        mode: str = None,
    ) -> dict:
        """
        Submit a video generation job (async).
        Supports fal.ai (image-to-video), xAI (Grok), Google (Veo), and
        OpenRouter providers.

        Args:
            source_image: Local file path of the source image for
                         image-to-video mode (fal providers only).
            mode: Generation mode — "image_to_video" or "text_to_video".
                  If None, uses the config-specified mode for fal providers.

        Returns dict: {model, prompt, external_job_id, status, cost_usd, provider}.
        """
        model = model or self.media_config.get("video_default", "grok-imagine-video")
        video_provider = provider or self.media_config.get("video_provider", "openrouter")
        video_base_url = self.media_config.get("video_base_url", self.base_url)

        # Check if this is a fal provider
        fal_gen = self._resolve_fal_video_generator(model)
        if fal_gen:
            return self._submit_video_fal(
                prompt=prompt, asset_id=asset_id, model=model,
                fal_gen=fal_gen, aspect_ratio=aspect_ratio,
                duration=duration, context=context,
                business_slug=business_slug,
                source_image=source_image, mode=mode,
            )

        if video_provider == "google":
            # Google Veo — Generative Language API (long-running operation)
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
            if not api_key:
                raise MediaAdapterError(
                    "GEMINI_API_KEY (or GOOGLE_API_KEY) not set — cannot generate video with Google/Veo"
                )
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predictLongRunning"
            headers = {"Content-Type": "application/json"}
            params = {"key": api_key}
            payload = {
                "instances": [{"prompt": prompt}],
                "parameters": {
                    "sampleCount": 1,
                    "aspectRatio": aspect_ratio,  # VH-3 bug 1: send as-is, NOT replace(":", "x")
                    "durationSeconds": _veo_clamp_duration(duration),
                },
            }
            try:
                response = requests.post(url, json=payload, headers=headers, params=params, timeout=60)
                response.raise_for_status()
            except requests.RequestException as e:
                # Include response body in error for debugging
                detail = ""
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        detail = f" — {e.response.text[:300]}"
                    except Exception:
                        pass
                self._log_provenance(model, prompt, context=f"{context} (submit failed)",
                                     business_slug=business_slug, provider="google")
                raise MediaAdapterError(f"Google Veo API submit failed: {e}{detail}")

            data = response.json()
            external_job_id = data.get("name") or data.get("operationId")
            cost_usd = 0
            # Compute from config
            cost_usd = self._compute_cost(model, "video", duration_seconds=duration)

            self._log_provenance(model, prompt, cost_usd=cost_usd,
                                context=f"{context} (submitted, ext_job={external_job_id})",
                                business_slug=business_slug, provider="google")

            print(f"[media] Video submitted: {model} (google) — ${cost_usd:.4f} ({duration}s × rate from config) — ext_job={external_job_id}")

            return {
                "model": model,
                "prompt": prompt,
                "external_job_id": external_job_id,
                "status": "submitted",
                "cost_usd": cost_usd,
                "provider": "google",
            }

        elif video_provider == "xai":
            api_key = os.environ.get("XAI_API_KEY", "")
            if not api_key:
                raise MediaAdapterError("XAI_API_KEY not set — cannot generate video with xAI")
            url = f"{video_base_url}/v1/videos/generations"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,
                "duration": duration,
            }
        else:
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
            self._log_provenance(model, prompt, context=f"{context} (submit failed)",
                                 business_slug=business_slug, provider=video_provider)
            raise MediaAdapterError(f"Video API submit failed: {e}")

        data = response.json()
        external_job_id = data.get("request_id") or data.get("id") or data.get("job_id")
        cost_usd = data.get("cost", 0)
        # If the API didn't return a cost, compute from config
        if not cost_usd:
            cost_usd = self._compute_cost(model, "video", duration_seconds=duration)

        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=f"{context} (submitted, ext_job={external_job_id})",
                            business_slug=business_slug, provider=video_provider)

        print(f"[media] Video submitted: {model} — ${cost_usd:.4f} ({duration}s × rate from config) — ext_job={external_job_id}")
        return {
            "model": model,
            "prompt": prompt,
            "external_job_id": external_job_id,
            "status": "submitted",
            "cost_usd": cost_usd,
            "provider": video_provider,
        }

    def check_video_job(self, external_job_id: str, provider: str = None) -> dict:
        """
        Poll a video generation job. Returns:
        {status: "processing"|"completed"|"failed", download_url, cost_usd}
        """
        video_base_url = self.media_config.get("video_base_url", self.base_url)
        video_provider = provider or self.media_config.get("video_provider", "openrouter")

        if video_provider == "google":
            # Google Veo — poll long-running operation
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
            if not api_key:
                raise MediaAdapterError(
                    "GEMINI_API_KEY (or GOOGLE_API_KEY) not set — cannot poll Google video jobs"
                )
            url = f"https://generativelanguage.googleapis.com/v1beta/{external_job_id}"
            params = {"key": api_key}
            try:
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
            except requests.RequestException as e:
                raise MediaAdapterError(f"Google Veo poll failed: {e}")

            data = response.json()
            # Log raw response to provenance for debugging response-shape mismatches
            self._log_provenance(
                "google-veo-poll", str(external_job_id),
                context=f"Veo poll raw response: {str(data)[:500]}",
                business_slug=None, provider="google",
            )
            done = data.get("done", False)
            if not done:
                return {"status": "processing", "download_url": None, "cost_usd": 0}

            # Operation complete — extract video URI from response.
            # VH-3 bug 2: Veo nests samples under response.generateVideoResponse.generatedSamples
            result = data.get("response", {})
            generate_video_response = result.get("generateVideoResponse", {})
            generated_samples = generate_video_response.get("generatedSamples", [])
            # Fallback: some model versions may nest differently — also try the
            # shallow path and log a warning if the deep path found nothing.
            if not generated_samples:
                shallow_samples = result.get("generatedSamples", [])
                if shallow_samples:
                    self._log_provenance(
                        "google-veo-poll", str(external_job_id),
                        context="WARNING: generatedSamples found at shallow level (response.generatedSamples), "
                                "not under generateVideoResponse. Response shape may differ by model version.",
                        business_slug=None, provider="google",
                    )
                    generated_samples = shallow_samples
            if generated_samples:
                video_data = generated_samples[0].get("video", {})
                download_url = video_data.get("gcsUri") or video_data.get("url") or video_data.get("uri")
            else:
                download_url = None

            status = "completed" if download_url else "failed"
            return {
                "status": status,
                "download_url": download_url,
                "cost_usd": 0,
            }

        elif video_provider == "xai":
            api_key = os.environ.get("XAI_API_KEY", "")
            if not api_key:
                raise MediaAdapterError("XAI_API_KEY not set — cannot poll xAI video jobs")
            url = f"{video_base_url}/v1/videos/{external_job_id}"
            headers = {"Authorization": f"Bearer {api_key}"}
        else:
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

    def _submit_video_fal(
        self,
        prompt: str,
        asset_id: int,
        model: str,
        fal_gen: dict,
        aspect_ratio: str,
        duration: int,
        context: str,
        business_slug: str,
        source_image: str,
        mode: str,
    ) -> dict:
        """Submit a video generation job to fal.ai (image-to-video or text-to-video)."""
        import fal_client

        api_key = self._get_fal_api_key(fal_gen)
        if not api_key:
            raise MediaAdapterError(f"FAL_KEY not set — cannot generate video with fal provider '{model}'")

        endpoint = fal_gen.get("endpoint", model)
        gen_mode = mode or fal_gen.get("mode", "image_to_video")

        arguments = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": str(duration) if duration else "5",
        }

        # Image-to-video: upload source image and add to arguments
        if gen_mode == "image_to_video":
            if not source_image:
                raise MediaAdapterError(
                    f"fal video provider '{model}' is image-to-video mode — source_image is required"
                )
            if not os.path.exists(source_image):
                raise MediaAdapterError(f"Source image not found: {source_image}")
            try:
                image_url = fal_client.upload_file(source_image)
            except Exception as e:
                raise MediaAdapterError(f"Failed to upload source image {source_image}: {e}")
            # fal image-to-video endpoints use "image_url" parameter
            arguments["image_url"] = image_url

        try:
            handle = fal_client.submit(endpoint, arguments=arguments)
        except Exception as e:
            self._log_provenance(model, prompt, context=f"{context} (submit failed)",
                                 business_slug=business_slug, provider="fal")
            raise MediaAdapterError(f"fal.ai video submit failed: {e}")

        request_id = handle.request_id
        cost_usd = self._compute_cost(model, "video", duration_seconds=duration)

        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=f"{context} (submitted, ext_job={request_id})",
                            business_slug=business_slug, provider="fal")

        print(f"[media] Video submitted (fal): {model} — ${cost_usd:.4f} ({duration}s × rate from config) — ext_job={request_id}")
        return {
            "model": model,
            "prompt": prompt,
            "external_job_id": request_id,
            "status": "submitted",
            "cost_usd": cost_usd,
            "provider": "fal",
        }

    def check_fal_job(self, endpoint: str, request_id: str) -> dict:
        """Poll a fal.ai video job. Returns {status, download_url, cost_usd}."""
        import fal_client

        try:
            status = fal_client.status(endpoint, request_id)
        except Exception as e:
            raise MediaAdapterError(f"fal.ai status check failed: {e}")

        # Status objects: Queued, InProgress, Completed (dataclass instances)
        if isinstance(status, fal_client.Completed):
            try:
                result = fal_client.result(endpoint, request_id)
            except Exception as e:
                raise MediaAdapterError(f"fal.ai result fetch failed: {e}")

            # Extract video URL from result
            video_url = None
            if isinstance(result, dict):
                video_url = result.get("video", {}).get("url") if isinstance(result.get("video"), dict) else None
                if not video_url:
                    # Try other common response shapes
                    video_url = result.get("url") or result.get("output_url")

            return {
                "status": "completed",
                "download_url": video_url,
                "cost_usd": 0,
            }
        elif isinstance(status, (fal_client.Queued, fal_client.InProgress)):
            return {"status": "processing", "download_url": None, "cost_usd": 0}
        else:
            return {"status": "failed", "download_url": None, "cost_usd": 0}

    def download_video(self, external_job_id: str, download_url: str, asset_id: int,
                       model: str, prompt: str, cost_usd: float = 0,
                       business_slug: str = None,
                       video_provider: str = None) -> dict:
        """Download a completed video and record it.

        Returns dict: {file_path, media_id} so the caller can construct
        an ingredient_id of the form ``generated:<media_id>``.
        """
        media_dir = self._ensure_media_dir(asset_id)
        file_hash = hashlib.sha256(prompt.encode()).hexdigest()[:16]
        filename = f"video_{file_hash}.mp4"
        file_path = os.path.join(media_dir, filename)

        # VH-3 bug 3: Google/Veo download URIs require the API key as a
        # query parameter. Without it Google returns a small JSON error
        # blob with HTTP 200 — raise_for_status won't catch it.
        effective_url = download_url
        vp = video_provider or self.media_config.get("video_provider", "openrouter")
        if vp == "google" or "googleapis" in download_url:
            api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
            if api_key:
                if "?" not in download_url:
                    effective_url = download_url + f"?key={api_key}"
                elif "key=" not in download_url:
                    effective_url = download_url + f"&key={api_key}"

        response = requests.get(effective_url, timeout=120)
        response.raise_for_status()

        # Sanity check: Google error blobs are a few hundred bytes of JSON.
        # A real video is at least 1KB.
        if len(response.content) < 1024:
            raise MediaAdapterError(
                f"Downloaded file is only {len(response.content)} bytes — "
                f"likely an error response, not a video. URL: {effective_url}"
            )

        with open(file_path, "wb") as f:
            f.write(response.content)

        media_id = self._record_media(asset_id, "video", file_path, model, prompt, cost_usd)
        self._log_provenance(model, prompt, cost_usd=cost_usd,
                            context=f"Video download (ext_job={external_job_id})",
                            business_slug=business_slug)

        print(f"[media] Video downloaded: {model} — ${cost_usd:.4f} — {file_path}")
        return {"file_path": file_path, "media_id": media_id, "cost_usd": cost_usd}

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

    def clear_draft_media(self, draft_id: int) -> int:
        """Delete all draft preview media rows for a draft.

        Called before generating fresh draft visuals so stale images from a
        previous draft generation (different content/topic) don't persist and
        get carried into assets during fan-out.

        Returns count of deleted rows.
        """
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM asset_media WHERE asset_id = ? AND owner_type = 'draft'",
            (draft_id,),
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted

    def list_asset_media(self, asset_id: int, kind: str = None,
                         owner_type: str = None) -> list[dict]:
        """List all media for an asset, optionally filtered by kind and/or owner_type.

        F4: owner_type filter separates draft visuals (owner_type='draft')
        from asset media (owner_type='asset'). If owner_type is None, returns
        all rows for the asset_id (backward compatible).
        """
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cols = [row[1] for row in conn.execute("PRAGMA table_info(asset_media)").fetchall()]
        has_owner_type = "owner_type" in cols

        conditions = ["asset_id = ?"]
        params = [asset_id]

        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if owner_type and has_owner_type:
            conditions.append("owner_type = ?")
            params.append(owner_type)

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM asset_media WHERE {where} ORDER BY id ASC",
            params,
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
