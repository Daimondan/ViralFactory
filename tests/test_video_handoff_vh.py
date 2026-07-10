"""
Regression tests for video generation → assembly handoff corrections (VH-1 through VH-6).

Covers:
- VH-1: generate-clip route reads download_url, calls download_video(), returns valid ingredient_id
- VH-2: generate-media route polls, downloads, and registers AI video (no more "submit and walk away")
- VH-3: Google/Veo fixes (aspect ratio, response nesting, download API key, env var)
- VH-4: 0-byte render file validation
- VH-5: Duration read from plan_item, not hardcoded
"""

import json
import os
import sys
import tempfile
from unittest.mock import patch, MagicMock

import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import PipelineStore
from media_adapter import MediaAdapter, MediaAdapterError
from assembly import AssemblyRenderer


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_test_app(tmp_path):
    """Create a Flask test app with a fresh DB."""
    from app import create_app
    db_path = str(tmp_path / "test.db")
    app = create_app(config_dir="config", db_path=db_path)
    return app, db_path


def _setup_asset_for_media_gen(store, tmp_path):
    """Create a minimal asset that needs media generation."""
    card_id = store.create_idea_card(
        business_slug="stackpenni",
        idea="Test reel idea",
        hook_options=[],
        treatment={
            "format": {"format_name": "Instagram Reel Script"},
            "capture_required": ["Test footage"],
        },
        origin="test",
    )
    draft_id = store.create_draft("stackpenni", card_id, "test", format_name="Instagram Reel Script")
    store.save_draft_content(draft_id, "draft", {}, [], platform_content=[])
    store.update_draft_state(draft_id, "shipped")
    asset_id = store.create_asset("stackpenni", draft_id, "Instagram", "reel", "Test reel")
    return asset_id


# ── VH-1: generate-clip reads download_url, calls download_video() ────────────

class TestVH1GenerateClip:
    """VH-1: generate-clip must read download_url from poll result, call
    download_video(), and return a valid ingredient_id with a real file path."""

    def test_generate_clip_downloads_and_returns_ingredient_id(self, tmp_path):
        """When a video job completes, generate-clip should download the file
        via download_video() and return a valid ingredient_id."""
        from app import create_app
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        # Create a fake video file that download_video would produce
        video_content = b"fake_video_data_at_least_1kb" * 60  # >1KB

        def mock_submit(self, prompt, asset_id, aspect_ratio, duration, context, business_slug, **kw):
            return {
                "model": "test-model",
                "prompt": prompt,
                "external_job_id": "test-job-123",
                "status": "submitted",
                "cost_usd": 0,
                "provider": "xai",
            }

        def mock_check(self, external_job_id, provider=None):
            return {
                "status": "completed",
                "download_url": "http://example.invalid/video.mp4",
                "cost_usd": 0,
            }

        def mock_download(self, external_job_id, download_url, asset_id, model, prompt, cost_usd, business_slug, video_provider=None):
            file_path = str(tmp_path / "downloaded_video.mp4")
            with open(file_path, "wb") as f:
                f.write(video_content)
            return {"file_path": file_path, "media_id": 42}

        with patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch.object(MediaAdapter, "download_video", mock_download), \
             patch("time.sleep"):  # skip polling delays
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-clip", json={
                "prompt": "test prompt",
                "duration": 5,
                "aspect_ratio": "9:16",
            })

        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["ingredient_id"] == "generated:42"
        assert data["path"] == str(tmp_path / "downloaded_video.mp4")
        # File must exist on disk
        assert os.path.exists(data["path"])
        assert os.path.getsize(data["path"]) > 1024

    def test_generate_clip_derives_prompt_from_asset_when_dialog_prompt_is_blank(self, tmp_path):
        """The optional prompt field must not send the API into ``prompt required``."""
        from app import create_app
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)
        submitted_prompts = []

        def mock_submit(self, prompt, **kwargs):
            submitted_prompts.append(prompt)
            return {"model": "test", "external_job_id": "test-job", "cost_usd": 0, "provider": "xai"}

        def mock_check(self, external_job_id, provider=None):
            return {"status": "failed", "error": "test stops after prompt resolution"}

        with patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch("time.sleep"):
            resp = app.test_client().post(
                f"/api/assets/{asset_id}/generate-clip",
                json={"prompt": "", "duration": 5, "aspect_ratio": "9:16"},
            )

        assert resp.status_code == 500
        assert submitted_prompts == ["Test reel"]

    def test_generate_clip_error_on_missing_download_url(self, tmp_path):
        """If poll returns completed but no download_url, generate-clip returns 500."""
        from app import create_app
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        def mock_submit(self, **kw):
            return {"model": "test", "prompt": "", "external_job_id": "job-1",
                    "status": "submitted", "cost_usd": 0, "provider": "xai"}

        def mock_check(self, external_job_id, provider=None):
            return {"status": "completed", "download_url": "", "cost_usd": 0}

        with patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch("time.sleep"):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-clip", json={
                "prompt": "test", "duration": 5, "aspect_ratio": "9:16",
            })

        assert resp.status_code == 500
        assert "download url" in resp.get_json()["error"].lower()

    def test_generate_clip_does_not_poison_asset_media(self, tmp_path):
        """asset_media should NOT have a row with path='' after a completed job."""
        import sqlite3
        from app import create_app
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        def mock_submit(self, **kw):
            return {"model": "test", "prompt": "", "external_job_id": "job-1",
                    "status": "submitted", "cost_usd": 0, "provider": "xai"}

        def mock_check(self, external_job_id, provider=None):
            return {"status": "completed", "download_url": "http://x/v.mp4", "cost_usd": 0}

        def mock_download(self, external_job_id, download_url, asset_id, model, prompt, cost_usd, business_slug, video_provider=None):
            file_path = str(tmp_path / "clip.mp4")
            with open(file_path, "wb") as f:
                f.write(b"x" * 2048)
            return {"file_path": file_path, "media_id": 99}

        with patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch.object(MediaAdapter, "download_video", mock_download), \
             patch("time.sleep"):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-clip", json={
                "prompt": "test", "duration": 5, "aspect_ratio": "9:16",
            })

        assert resp.status_code == 200
        # Check asset_media — no empty paths
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT path FROM asset_media WHERE asset_id = ?", (asset_id,)
        ).fetchall()
        conn.close()
        assert len(rows) == 0  # download_video mock doesn't call _record_media
        # But if it did, the path would be the real file path, not ""


# ── VH-2: generate-media polls, downloads, and registers AI video ─────────────

class TestVH2GenerateMediaVideo:
    """VH-2: generate-media must poll, download, and register AI video jobs."""

    def test_generate_media_ai_video_polls_and_downloads(self, tmp_path):
        """When the LLM media plan includes an ai_video generator, generate-media
        should poll the job, download on completion, and return ingredient_id."""
        from app import create_app
        from llm_adapter import LLMAdapter
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            return {
                "media_plan": [{
                    "capture_index": 0,
                    "capture_task": "Test footage",
                    "generator": "ai_video",
                    "generation_prompt": "Cinematic clip of test footage",
                    "duration": 10,
                }]
            }

        def mock_submit(self, prompt, asset_id, aspect_ratio, duration, context, business_slug, **kw):
            return {
                "model": "test-model",
                "prompt": prompt,
                "external_job_id": "ext-job-1",
                "status": "submitted",
                "cost_usd": 0,
                "provider": "xai",
            }

        def mock_check(self, external_job_id, provider=None):
            return {"status": "completed", "download_url": "http://x/v.mp4", "cost_usd": 0}

        def mock_download(self, external_job_id, download_url, asset_id, model, prompt, cost_usd, business_slug, video_provider=None):
            file_path = str(tmp_path / "gen_video.mp4")
            with open(file_path, "wb") as f:
                f.write(b"v" * 2048)
            return {"file_path": file_path, "media_id": 7}

        with patch.object(LLMAdapter, "complete", mock_complete), \
             patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch.object(MediaAdapter, "download_video", mock_download), \
             patch("time.sleep"):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-media", json={})

        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["results"][0]["status"] == "ok"
        assert data["results"][0]["ingredient_id"] == "generated:7"
        assert data["results"][0]["path"] == str(tmp_path / "gen_video.mp4")

    def test_generate_media_ai_video_timeout_returns_processing(self, tmp_path):
        """If the video job doesn't complete within the poll window,
        generate-media should return status='processing' with the external_job_id."""
        from app import create_app
        from llm_adapter import LLMAdapter
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            return {
                "media_plan": [{
                    "capture_index": 0,
                    "capture_task": "Test footage",
                    "generator": "ai_video",
                    "generation_prompt": "Cinematic clip",
                    "duration": 5,
                }]
            }

        def mock_submit(self, **kw):
            return {"model": "test", "prompt": "", "external_job_id": "ext-1",
                    "status": "submitted", "cost_usd": 0, "provider": "xai"}

        # Always returns "processing" — simulates timeout
        def mock_check(self, external_job_id, provider=None):
            return {"status": "processing", "download_url": None, "cost_usd": 0}

        with patch.object(LLMAdapter, "complete", mock_complete), \
             patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch.object(MediaAdapter, "download_video", MagicMock()), \
             patch("time.sleep"):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-media", json={})

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["results"][0]["status"] == "processing"
        assert data["results"][0]["external_job_id"] == "ext-1"

    def test_generate_media_fallback_ai_video_polls_and_downloads(self, tmp_path):
        """The fallback-to-AI path (when stock returns nothing) should also poll
        and download, not just submit and walk away."""
        from app import create_app
        from llm_adapter import LLMAdapter
        from stock_adapter import StockAdapter
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            return {
                "media_plan": [{
                    "capture_index": 0,
                    "capture_task": "Test footage",
                    "generator": "stock",
                    "search_query": "test footage",
                    "fallback_generator": "ai_video",
                    "fallback_prompt": "AI generated test footage",
                    "duration": 8,
                }]
            }

        def mock_search(self, query, kind="video", per_page=3):
            return []  # No stock results → triggers fallback

        def mock_submit(self, prompt, asset_id, aspect_ratio, duration, context, business_slug, **kw):
            assert duration == 8  # VH-5: duration from plan_item
            return {"model": "test", "prompt": prompt, "external_job_id": "fb-job-1",
                    "status": "submitted", "cost_usd": 0, "provider": "xai"}

        def mock_check(self, external_job_id, provider=None):
            return {"status": "completed", "download_url": "http://x/fb.mp4", "cost_usd": 0}

        def mock_download(self, external_job_id, download_url, asset_id, model, prompt, cost_usd, business_slug, video_provider=None):
            file_path = str(tmp_path / "fallback_video.mp4")
            with open(file_path, "wb") as f:
                f.write(b"f" * 2048)
            return {"file_path": file_path, "media_id": 55}

        with patch.object(LLMAdapter, "complete", mock_complete), \
             patch.object(StockAdapter, "search", mock_search), \
             patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch.object(MediaAdapter, "download_video", mock_download), \
             patch("time.sleep"):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-media", json={})

        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["results"][0]["status"] == "ok"
        assert data["results"][0]["ingredient_id"] == "generated:55"


# ── VH-3: Google/Veo bug fixes ───────────────────────────────────────────────

class TestVH3GoogleVeoBugs:
    """VH-3: Five independent Google/Veo bugs."""

    def test_aspect_ratio_not_mangled(self, tmp_path):
        """Bug 1: aspect_ratio '9:16' should be sent as '9:16', not '9x16'."""
        adapter = MediaAdapter({"media": {"video_provider": "google"}}, db_path=str(tmp_path / "test.db"))
        captured_payload = {}

        def mock_post(url, json=None, headers=None, params=None, timeout=None, **kw):
            captured_payload.update(json)
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"name": "op-1"}
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.post", mock_post), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            try:
                adapter.submit_video(
                    prompt="test", asset_id=1, aspect_ratio="9:16",
                    duration=5, model="veo-3.0", business_slug="test",
                    provider="google",
                )
            except Exception:
                pass

        assert captured_payload["parameters"]["aspectRatio"] == "9:16"

    def test_response_parsing_deep_nesting(self, tmp_path):
        """Bug 2: Veo response nests samples under generateVideoResponse.generatedSamples."""
        adapter = MediaAdapter({"media": {"video_provider": "google"}}, db_path=str(tmp_path / "test.db"))

        veo_response = {
            "done": True,
            "response": {
                "generateVideoResponse": {
                    "generatedSamples": [
                        {"video": {"gcsUri": "gs://bucket/video.mp4"}}
                    ]
                }
            },
        }

        def mock_get(url, params=None, timeout=None, **kw):
            mock_resp = MagicMock()
            mock_resp.json.return_value = veo_response
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.get", mock_get), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = adapter.check_video_job("op-1", provider="google")

        assert result["status"] == "completed"
        assert result["download_url"] == "gs://bucket/video.mp4"

    def test_response_parsing_shallow_fallback(self, tmp_path):
        """Bug 2 fallback: if samples are at the shallow level, still find them."""
        adapter = MediaAdapter({"media": {"video_provider": "google"}}, db_path=str(tmp_path / "test.db"))

        veo_response = {
            "done": True,
            "response": {
                "generatedSamples": [
                    {"video": {"gcsUri": "gs://bucket/video2.mp4"}}
                ]
            },
        }

        def mock_get(url, params=None, timeout=None, **kw):
            mock_resp = MagicMock()
            mock_resp.json.return_value = veo_response
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.get", mock_get), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            result = adapter.check_video_job("op-1", provider="google")

        assert result["status"] == "completed"
        assert result["download_url"] == "gs://bucket/video2.mp4"

    def test_download_appends_api_key_for_google(self, tmp_path):
        """Bug 3: download_video should append ?key={api_key} to Google download URLs."""
        adapter = MediaAdapter({"media": {"video_provider": "google"}}, db_path=str(tmp_path / "test.db"))

        captured_url = {}

        def mock_get(url, timeout=None, **kw):
            captured_url["url"] = url
            mock_resp = MagicMock()
            mock_resp.content = b"x" * 2048  # >1KB
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.get", mock_get), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "test-api-key"}):
            try:
                adapter.download_video(
                    "ext-1", "https://generativelanguage.googleapis.com/v1beta/files/abc",
                    asset_id=1, model="veo", prompt="test", cost_usd=0,
                    business_slug="test", video_provider="google",
                )
            except Exception:
                pass

        assert "?key=test-api-key" in captured_url["url"]

    def test_gemini_api_key_env_var(self, tmp_path):
        """Bug 4: submit_video should accept GEMINI_API_KEY, not just GOOGLE_API_KEY."""
        adapter = MediaAdapter({"media": {"video_provider": "google"}}, db_path=str(tmp_path / "test.db"))

        def mock_post(url, json=None, headers=None, params=None, timeout=None, **kw):
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"name": "op-1"}
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.post", mock_post), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "gemini-key"}, clear=False):
            # Remove GOOGLE_API_KEY to prove GEMINI_API_KEY works alone
            import os as _os
            _os.environ.pop("GOOGLE_API_KEY", None)
            result = adapter.submit_video(
                prompt="test", asset_id=1, aspect_ratio="9:16",
                duration=5, model="veo-3.0", business_slug="test",
                provider="google",
            )

        assert result["external_job_id"] == "op-1"

    def test_download_rejects_small_files(self, tmp_path):
        """Bug 3 sanity check: downloaded file < 1KB should raise an error."""
        adapter = MediaAdapter({"media": {"video_provider": "google"}}, db_path=str(tmp_path / "test.db"))

        def mock_get(url, timeout=None, **kw):
            mock_resp = MagicMock()
            mock_resp.content = b"error blob"  # ~10 bytes
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.get", mock_get), \
             patch.dict(os.environ, {"GEMINI_API_KEY": "key"}):
            with pytest.raises(MediaAdapterError, match="likely an error response"):
                adapter.download_video(
                    "ext-1", "https://googleapis.com/v.mp4",
                    asset_id=1, model="veo", prompt="test", cost_usd=0,
                    business_slug="test", video_provider="google",
                )


# ── VH-4: 0-byte render file validation ─────────────────────────────────────

class TestVH4ZeroByteRender:
    """VH-4: Render route must check output file size and fail on 0 bytes."""

    def test_no_zero_byte_files_after_cleanup(self):
        """No 0-byte final_*.mp4 files should exist in data/media/."""
        import subprocess
        result = subprocess.run(
            ["find", "data/media/", "-name", "final_*.mp4", "-size", "0"],
            capture_output=True, text=True,
        )
        assert result.stdout.strip() == "", f"0-byte files found:\n{result.stdout}"

    def test_render_route_rejects_zero_byte_output(self, tmp_path):
        """If the renderer returns a 0-byte file path, the route should mark
        the job as failed, delete the file, and return 500."""
        from app import create_app
        from assembly import AssemblyError
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)

        # Create an asset + edit plan
        card_id = store.create_idea_card(
            business_slug="stackpenni", idea="test", hook_options=[],
            treatment={"format": {"format_name": "Reel"}}, origin="test",
        )
        draft_id = store.create_draft("stackpenni", card_id, "t", format_name="Reel")
        store.save_draft_content(draft_id, "draft", {}, [], platform_content=[])
        store.update_draft_state(draft_id, "shipped")
        asset_id = store.create_asset("stackpenni", draft_id, "Instagram", "reel", "test")
        plan_id = store.save_edit_plan(draft_id, asset_id, {"segments": []})

        # Mock the renderer to produce a 0-byte file
        zero_path = str(tmp_path / "final_0.mp4")
        open(zero_path, "wb").close()  # Create 0-byte file

        def mock_render(self, **kw):
            return {
                "path": zero_path,
                "duration": 0.0,
                "render_time_s": 0.1,
                "version": "v1",
                "cut_list": [],
            }

        with patch.object(AssemblyRenderer, "render", mock_render):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/render", json={"plan_id": plan_id})

        assert resp.status_code == 500
        assert "0-byte" in resp.get_json()["error"]
        # The 0-byte file should have been deleted
        assert not os.path.exists(zero_path)


# ── VH-5: Duration from plan_item ─────────────────────────────────────────────

class TestVH5DurationFromPlan:
    """VH-5: Duration must come from plan_item, not hardcoded to 5."""

    def test_duration_from_plan_item_passed_to_submit(self, tmp_path):
        """When plan_item has duration=10, submit_video should be called with duration=10."""
        from app import create_app
        from llm_adapter import LLMAdapter
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        asset_id = _setup_asset_for_media_gen(store, tmp_path)

        captured_duration = {}

        def mock_complete(self, prompt_file, variables, schema, **kwargs):
            return {
                "media_plan": [{
                    "capture_index": 0,
                    "capture_task": "Test footage",
                    "generator": "ai_video",
                    "generation_prompt": "Cinematic 15-second clip",
                    "duration": 15,
                }]
            }

        def mock_submit(self, prompt, asset_id, aspect_ratio, duration, context, business_slug, **kw):
            captured_duration["value"] = duration
            return {"model": "test", "prompt": prompt, "external_job_id": "j-1",
                    "status": "submitted", "cost_usd": 0, "provider": "xai"}

        def mock_check(self, external_job_id, provider=None):
            return {"status": "completed", "download_url": "http://x/v.mp4", "cost_usd": 0}

        def mock_download(self, external_job_id, download_url, asset_id, model, prompt, cost_usd, business_slug, video_provider=None):
            file_path = str(tmp_path / "dur_test.mp4")
            with open(file_path, "wb") as f:
                f.write(b"d" * 2048)
            return {"file_path": file_path, "media_id": 1}

        with patch.object(LLMAdapter, "complete", mock_complete), \
             patch.object(MediaAdapter, "submit_video", mock_submit), \
             patch.object(MediaAdapter, "check_video_job", mock_check), \
             patch.object(MediaAdapter, "download_video", mock_download), \
             patch("time.sleep"):
            client = app.test_client()
            resp = client.post(f"/api/assets/{asset_id}/generate-media", json={})

        assert resp.status_code == 200
        assert captured_duration["value"] == 15  # Not hardcoded 5


# ── download_video return type ───────────────────────────────────────────────

class TestDownloadVideoReturnType:
    """download_video() must return a dict with file_path and media_id."""

    def test_download_video_returns_dict(self, tmp_path):
        adapter = MediaAdapter({}, db_path=str(tmp_path / "test.db"))

        def mock_get(url, timeout=None, **kw):
            mock_resp = MagicMock()
            mock_resp.content = b"x" * 2048
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        with patch("requests.get", mock_get):
            result = adapter.download_video(
                "ext-1", "http://example.invalid/v.mp4",
                asset_id=1, model="test", prompt="test", cost_usd=0,
                business_slug="test",
            )

        assert isinstance(result, dict)
        assert "file_path" in result
        assert "media_id" in result
        assert os.path.exists(result["file_path"])
        assert os.path.getsize(result["file_path"]) > 1024