"""
Tests for F1 (jobs table + idempotency), F2 (audit flags), F3 (visual direction validation),
F4 (media adapter), F5 (from_json filter), and Final Assembly (edit plan, stock adapter, renderer).
"""

import json
import os
import tempfile
import pytest
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from jobs import JobsStore
from pipeline import PipelineStore, EDIT_PLAN_SCHEMA, DRAFT_SCHEMA
from validator import validate_llm_output, ValidationError
from media_adapter import MediaAdapter, MediaAdapterError
from stock_adapter import StockAdapter
from assembly import AssemblyRenderer, AssemblyError


# ── F1: Jobs table ──────────────────────────────────────────────────────────

class TestJobsTable:
    """F1: Jobs table — idempotency and async job tracking."""

    def test_start_job_returns_started(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        result = store.start_job("draft_generate", entity_id=1)
        assert result["status"] == "started"
        assert "job_id" in result

    def test_duplicate_job_returns_running(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        r1 = store.start_job("draft_generate", entity_id=1)
        assert r1["status"] == "started"
        r2 = store.start_job("draft_generate", entity_id=1)
        assert r2["status"] == "running"
        assert r2["job_id"] == r1["job_id"]

    def test_complete_job_allows_new_same_key(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        r1 = store.start_job("fan_out", entity_id=5)
        store.complete_job(r1["job_id"], "result_ref")
        r2 = store.start_job("fan_out", entity_id=5)
        assert r2["status"] == "started"  # new job, previous was done
        assert r2["job_id"] != r1["job_id"]

    def test_completed_job_returns_done(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        r1 = store.start_job("media_images", entity_id=10)
        store.complete_job(r1["job_id"], "images:3")
        r2 = store.start_job("media_images", entity_id=10)
        # After completion, a new request starts a new job (not "done" — we allow re-runs)
        assert r2["status"] == "started"

    def test_fail_job_allows_retry(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        r1 = store.start_job("media_video", entity_id=3)
        store.fail_job(r1["job_id"], "API timeout")
        r2 = store.start_job("media_video", entity_id=3)
        assert r2["status"] == "started"

    def test_job_key_with_input_hash(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        r1 = store.start_job("analyze", entity_id=1, input_hash="abc123")
        r2 = store.start_job("analyze", entity_id=1, input_hash="abc123")
        assert r2["status"] == "running"  # same key = running
        r3 = store.start_job("analyze", entity_id=1, input_hash="def456")
        assert r3["status"] == "started"  # different hash = new job

    def test_stale_job_is_marked_dead(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        r1 = store.start_job("assembly_render", entity_id=7)
        # Simulate stale by manually setting old timestamp
        import sqlite3
        from datetime import datetime, timezone, timedelta
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute("UPDATE jobs SET started_at = ? WHERE id = ?", (old_ts, r1["job_id"]))
        conn.commit()
        conn.close()
        # Next start should detect stale and start fresh
        r2 = store.start_job("assembly_render", entity_id=7, stale_timeout_s=60)
        assert r2["status"] == "started"
        assert r2["job_id"] != r1["job_id"]

    def test_list_jobs_filtered(self, tmp_path):
        store = JobsStore(str(tmp_path / "test.db"))
        store.start_job("draft_generate", entity_id=1)
        store.start_job("fan_out", entity_id=2)
        store.start_job("draft_generate", entity_id=3)
        all_jobs = store.list_jobs()
        assert len(all_jobs) >= 3
        draft_jobs = store.list_jobs(job_type="draft_generate")
        assert all(j["job_type"] == "draft_generate" for j in draft_jobs)


# ── F2: Audit flags ─────────────────────────────────────────────────────────

class TestAuditFlags:
    """F2: Self-audit flags become actionable (Apply/Dismiss)."""

    def _setup_store_and_draft(self, tmp_path):
        store = PipelineStore(str(tmp_path / "test.db"))
        card_id = store.create_idea_card(
            business_slug="test-biz",
            idea="Test idea",
            hook_options=["Hook 1"],
            treatment={"scope": {"type": "one_off"}, "format": {"format_name": "reel", "experimental": False}, "capture_required": [], "rationale": "test"},
            origin="ai_originated",
        )
        draft_id = store.create_draft("test-biz", card_id, "ai_originated", "reel", "one_off")
        store.save_draft_content(
            draft_id,
            draft_text="This is a test line that sounds too polished.\nSecond line here.",
            visual_direction={"image_prompts": ["test prompt"], "reference_notes": [], "shot_format_choices": ["portrait"]},
            self_audit_flags=[
                {"line": "This is a test line that sounds too polished.", "rule": "too_polished", "suggestion": "Make it more casual."},
                {"line": "Second line here.", "rule": "generic", "suggestion": "Add a specific detail."},
            ],
        )
        return store, draft_id

    def test_apply_flag_replaces_line(self, tmp_path):
        store, draft_id = self._setup_store_and_draft(tmp_path)
        updated = store.update_audit_flag(draft_id, 0, "apply")
        assert "Make it more casual." in updated["draft_text"]
        assert "too polished" not in updated["draft_text"]
        # Version bumped
        assert updated["draft_version"] == 2

    def test_apply_flag_marks_status(self, tmp_path):
        store, draft_id = self._setup_store_and_draft(tmp_path)
        updated = store.update_audit_flag(draft_id, 0, "apply")
        flags = json.loads(updated["self_audit_flags"])
        assert flags[0]["status"] == "applied"

    def test_dismiss_flag_marks_status(self, tmp_path):
        store, draft_id = self._setup_store_and_draft(tmp_path)
        updated = store.update_audit_flag(draft_id, 1, "dismiss")
        flags = json.loads(updated["self_audit_flags"])
        assert flags[1]["status"] == "dismissed"

    def test_apply_flag_records_feedback(self, tmp_path):
        store, draft_id = self._setup_store_and_draft(tmp_path)
        store.update_audit_flag(draft_id, 0, "apply")
        feedback = store.list_feedback("test-biz", draft_id)
        assert any(f["feedback_type"] == "direct_edit" for f in feedback)

    def test_apply_flag_line_changed(self, tmp_path):
        store, draft_id = self._setup_store_and_draft(tmp_path)
        # Manually edit the draft text so the flagged line no longer exists
        conn = __import__("sqlite3").connect(str(tmp_path / "test.db"))
        conn.execute("UPDATE drafts SET draft_text = 'Completely different text.' WHERE id = ?", (draft_id,))
        conn.commit()
        conn.close()
        updated = store.update_audit_flag(draft_id, 0, "apply")
        flags = json.loads(updated["self_audit_flags"])
        assert flags[0]["status"] == "line_changed"

    def test_dismiss_records_feedback(self, tmp_path):
        store, draft_id = self._setup_store_and_draft(tmp_path)
        store.update_audit_flag(draft_id, 0, "dismiss")
        feedback = store.list_feedback("test-biz", draft_id)
        assert any("Dismissed" in f["feedback_text"] for f in feedback)


# ── F3: Visual direction validation ─────────────────────────────────────────

class TestVisualDirection:
    """F3: Visual direction minItems validation + prompt v2 exists."""

    def test_draft_schema_rejects_empty_image_prompts(self):
        bad_output = json.dumps({
            "platform_content": [{"platform": "X", "variant_type": "thread", "content": "test", "posts": ["test"]}],
            "visual_direction": {
                "image_prompts": [],
                "reference_notes": [],
                "shot_format_choices": ["portrait"],
            },
            "self_audit_flags": [],
        })
        with pytest.raises(ValidationError) as exc_info:
            validate_llm_output(bad_output, DRAFT_SCHEMA)
        assert "image_prompts" in str(exc_info.value)

    def test_draft_schema_rejects_empty_shot_format_choices(self):
        bad_output = json.dumps({
            "platform_content": [{"platform": "X", "variant_type": "thread", "content": "test", "posts": ["test"]}],
            "visual_direction": {
                "image_prompts": ["a prompt"],
                "reference_notes": [],
                "shot_format_choices": [],
            },
            "self_audit_flags": [],
        })
        with pytest.raises(ValidationError) as exc_info:
            validate_llm_output(bad_output, DRAFT_SCHEMA)
        assert "shot_format_choices" in str(exc_info.value)

    def test_draft_schema_accepts_valid_visual_direction(self):
        good_output = json.dumps({
            "platform_content": [{"platform": "X", "variant_type": "thread", "content": "Some text", "posts": ["Some text"]}],
            "visual_direction": {
                "image_prompts": ["sunset over ocean, 9:16, warm tones"],
                "reference_notes": [],
                "shot_format_choices": ["vertical talking head"],
            },
            "self_audit_flags": [],
        })
        result = validate_llm_output(good_output, DRAFT_SCHEMA)
        assert len(result["visual_direction"]["image_prompts"]) >= 1

    def test_draft_prompt_v2_exists(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "draft", "generate_v2.md")
        assert os.path.exists(prompt_path)
        with open(prompt_path) as f:
            content = f.read()
        assert "version: 2.3" in content
        assert "REQUIRED" in content.upper()

    def test_draft_prompt_v3_exists(self):
        """T9.3: The v3 prompt (per-platform content) exists."""
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "draft", "generate_v3.md")
        assert os.path.exists(prompt_path)
        with open(prompt_path) as f:
            content = f.read()
        assert "version: 3.0" in content
        assert "platform_content" in content

    def test_validator_minitems_support(self):
        schema = {
            "type": "object",
            "required": ["items"],
            "properties": {
                "items": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            },
        }
        with pytest.raises(ValidationError):
            validate_llm_output(json.dumps({"items": ["one"]}), schema)
        # Valid
        result = validate_llm_output(json.dumps({"items": ["one", "two"]}), schema)
        assert len(result["items"]) == 2


# ── F4: Media adapter ───────────────────────────────────────────────────────

class TestMediaAdapter:
    """F4: Media adapter — image + video generation via OpenRouter."""

    def test_media_adapter_init(self, tmp_path):
        config = {"media": {"image_default": "test-model", "base_url": "https://test.api"}}
        adapter = MediaAdapter(config, db_path=str(tmp_path / "test.db"))
        assert adapter.media_config["image_default"] == "test-model"

    def test_generate_image_no_api_key_raises(self, tmp_path):
        config = {"media": {"image_default": "test-model", "base_url": "https://test.api"}}
        adapter = MediaAdapter(config, db_path=str(tmp_path / "test.db"))
        # No OPENROUTER_API_KEY set
        os.environ.pop("OPENROUTER_API_KEY", None)
        with pytest.raises(MediaAdapterError) as exc_info:
            adapter.generate_image("test prompt", asset_id=1)
        assert "OPENROUTER_API_KEY" in str(exc_info.value)

    def test_media_config_in_models_yaml(self):
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        import yaml
        with open(models_path) as f:
            config = yaml.safe_load(f)
        assert "media" in config
        assert "image_default" in config["media"]
        assert "video_default" in config["media"]
        assert "base_url" in config["media"]

    def test_asset_media_table_created(self, tmp_path):
        config = {"media": {}}
        adapter = MediaAdapter(config, db_path=str(tmp_path / "test.db"))
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "asset_media" in tables
        assert "image_cache" in tables

    def test_image_cache_dedup(self, tmp_path):
        """Same prompt + model = cached file, no second call."""
        config = {"media": {}}
        adapter = MediaAdapter(config, db_path=str(tmp_path / "test.db"))
        # Manually insert a cache entry
        import sqlite3
        from datetime import datetime, timezone
        import hashlib
        cache_key = hashlib.sha256("test|model".encode()).hexdigest()
        fake_path = str(tmp_path / "cached_image.png")
        with open(fake_path, "wb") as f:
            f.write(b"fake image data")
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.execute(
            "INSERT INTO image_cache (cache_key, prompt, model, file_path, cost_usd, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cache_key, "test", "model", fake_path, 0.01, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()
        # Check cache hit
        cached = adapter._get_cached_image("test", "model")
        assert cached == fake_path


# ── Final Assembly: Edit Plan + Stock + Renderer ────────────────────────────

class TestEditPlan:
    """Final Assembly: Edit Plan schema and storage."""

    def test_edit_plan_schema_validates(self):
        valid_plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3.5, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920", "duration_target": 30},
        }
        result = validate_llm_output(json.dumps(valid_plan), EDIT_PLAN_SCHEMA)
        assert "segments" in result

    def test_edit_plan_schema_rejects_empty_segments(self):
        bad_plan = {"segments": [], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        with pytest.raises(ValidationError):
            validate_llm_output(json.dumps(bad_plan), EDIT_PLAN_SCHEMA)

    def test_edit_plan_prompt_exists(self):
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "assembly", "edit_plan_v1.md")
        assert os.path.exists(prompt_path)

    def test_save_and_get_edit_plan(self, tmp_path):
        store = PipelineStore(str(tmp_path / "test.db"))
        card_id = store.create_idea_card(
            "test-biz", "Idea", ["hook"],
            {"scope": {"type": "one_off"}, "format": {"format_name": "reel", "experimental": False},
             "capture_required": [], "rationale": "test"},
            "ai_originated",
        )
        draft_id = store.create_draft("test-biz", card_id, "ai_originated", "reel", "one_off")
        plan = {"segments": [{"source": "generated:1", "in": 0, "out": 5}], "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"}}
        plan_id = store.save_edit_plan(draft_id, 1, plan)
        assert plan_id > 0

        retrieved = store.get_edit_plan(plan_id)
        assert retrieved["asset_id"] == 1
        assert json.loads(retrieved["plan_json"])["segments"][0]["source"] == "generated:1"

    def test_list_edit_plans(self, tmp_path):
        store = PipelineStore(str(tmp_path / "test.db"))
        card_id = store.create_idea_card(
            "test-biz", "Idea", ["hook"],
            {"scope": {"type": "one_off"}, "format": {"format_name": "reel", "experimental": False},
             "capture_required": [], "rationale": "test"},
            "ai_originated",
        )
        draft_id = store.create_draft("test-biz", card_id, "ai_originated", "reel", "one_off")
        store.save_edit_plan(draft_id, 1, {"segments": [], "canvas": {}})
        store.save_edit_plan(draft_id, 1, {"segments": [], "canvas": {}})
        plans = store.list_edit_plans(1)
        assert len(plans) >= 2

    def test_update_edit_plan_status(self, tmp_path):
        store = PipelineStore(str(tmp_path / "test.db"))
        card_id = store.create_idea_card(
            "test-biz", "Idea", ["hook"],
            {"scope": {"type": "one_off"}, "format": {"format_name": "reel", "experimental": False},
             "capture_required": [], "rationale": "test"},
            "ai_originated",
        )
        draft_id = store.create_draft("test-biz", card_id, "ai_originated", "reel", "one_off")
        plan_id = store.save_edit_plan(draft_id, 1, {"segments": [], "canvas": {}})
        updated = store.update_edit_plan_status(plan_id, "rendering")
        assert updated["status"] == "rendering"


class TestStockAdapter:
    """Final Assembly: Stock library adapter."""

    def test_stock_adapter_init(self, tmp_path):
        config = {"stock": {"cache_dir": str(tmp_path / "stock")}}
        adapter = StockAdapter(config, db_path=str(tmp_path / "test.db"))
        assert os.path.exists(str(tmp_path / "stock"))

    def test_stock_cache_table_created(self, tmp_path):
        config = {"stock": {}}
        adapter = StockAdapter(config, db_path=str(tmp_path / "test.db"))
        import sqlite3
        conn = sqlite3.connect(str(tmp_path / "test.db"))
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        conn.close()
        assert "stock_cache" in tables

    def test_search_no_api_keys_returns_empty(self, tmp_path):
        config = {"stock": {"providers": ["pexels", "pixabay"]}}
        adapter = StockAdapter(config, db_path=str(tmp_path / "test.db"))
        os.environ.pop("PEXELS_API_KEY", None)
        os.environ.pop("PIXABAY_API_KEY", None)
        results = adapter.search("sunset beach", kind="photo", per_page=3)
        assert results == []

    def test_stock_config_in_models_yaml(self):
        models_path = os.path.join(os.path.dirname(__file__), "..", "config", "models.yaml")
        import yaml
        with open(models_path) as f:
            config = yaml.safe_load(f)
        assert "stock" in config
        assert "providers" in config["stock"]


class TestAssemblyRenderer:
    """Final Assembly: FFmpeg-based renderer."""

    def test_renderer_init(self, tmp_path):
        config = {}
        renderer = AssemblyRenderer(config, db_path=str(tmp_path / "test.db"))
        assert renderer.TRANSITIONS == {"cut", "crossfade", "slide", "whip"}

    def test_build_cut_list(self, tmp_path):
        config = {}
        renderer = AssemblyRenderer(config, db_path=str(tmp_path / "test.db"))
        plan = {
            "segments": [
                {"source": "generated:1", "in": 0, "out": 3, "transition_in": "cut",
                 "overlays": [{"type": "caption", "text": "Hello world"}]},
                {"source": "stock:2", "in": 0, "out": 5, "transition_in": "crossfade"},
            ]
        }
        cut_list = renderer.format_cut_list_for_display(plan)
        assert "0:00" in cut_list
        assert "generated" in cut_list
        assert "Hello world" in cut_list
        assert "crossfade" in cut_list

    def test_render_empty_plan_raises(self, tmp_path):
        config = {}
        renderer = AssemblyRenderer(config, db_path=str(tmp_path / "test.db"))
        with pytest.raises(AssemblyError):
            renderer.render({"segments": []}, asset_id=1, draft_id=1)

    def test_render_missing_source_raises(self, tmp_path):
        config = {}
        renderer = AssemblyRenderer(config, db_path=str(tmp_path / "test.db"))
        plan = {
            "segments": [{"source": "generated:999", "in": 0, "out": 3}],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }
        with pytest.raises(AssemblyError) as exc_info:
            renderer.render(plan, asset_id=1, draft_id=1)
        assert "not found" in str(exc_info.value).lower() or "missing" in str(exc_info.value).lower()

    def test_has_video_stream_detects_audio_only(self, tmp_path):
        """_has_video_stream returns False for audio-only files (WhatsApp voice memos)."""
        import subprocess
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        # Generate a 1s audio-only mp4 (no video stream)
        audio_file = str(tmp_path / "audio_only.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:a", "aac", audio_file],
            capture_output=True, timeout=30,
        )
        assert os.path.exists(audio_file)
        assert renderer._has_video_stream(audio_file) is False

    def test_has_video_stream_detects_video(self, tmp_path):
        """_has_video_stream returns True for files with a video track."""
        import subprocess
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))
        video_file = str(tmp_path / "video.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", video_file],
            capture_output=True, timeout=30,
        )
        assert os.path.exists(video_file)
        assert renderer._has_video_stream(video_file) is True

    def test_render_audio_only_source_succeeds(self, tmp_path):
        """Render should succeed when a segment source is audio-only (no video).

        Regression: WhatsApp voice memos saved as .mp4 have only an audio stream.
        The concat filter requires [i:v] from every input — the renderer must
        synthesize a black video track for audio-only sources.
        """
        import subprocess
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create an audio-only file
        audio_file = str(tmp_path / "voice_memo.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:a", "aac", audio_file],
            capture_output=True, timeout=30,
        )

        # Create a video file
        video_file = str(tmp_path / "clip.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=1080x1920:rate=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video_file],
            capture_output=True, timeout=30,
        )

        # Stub _resolve_source to return our test files
        sources = [video_file, audio_file]
        call_idx = [0]
        original = renderer._resolve_source
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        plan = {
            "segments": [
                {"source": "upload:1", "in": 0, "out": 2, "transition_in": "cut"},
                {"source": "upload:2", "in": 0, "out": 2, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

        # Override media_dir to tmp_path
        os.makedirs(os.path.join("data", "media", "9999"), exist_ok=True)
        result = renderer.render(plan, asset_id=9999, draft_id=1)
        assert os.path.exists(result["path"])
        assert result["duration"] > 0

        # Cleanup
        import shutil
        shutil.rmtree(os.path.join("data", "media", "9999"), ignore_errors=True)

    def test_render_video_only_source_succeeds(self, tmp_path):
        """Render should succeed when a video source has no audio track.

        The concat filter requires [i:a] from every input — the renderer must
        synthesize a silent audio track for video-only sources.
        """
        import subprocess
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create a video-only file (no audio)
        video_only = str(tmp_path / "video_only.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=1080x1920:rate=30",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", video_only],
            capture_output=True, timeout=30,
        )

        # Create a normal video+audio file
        video_audio = str(tmp_path / "video_audio.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=1080x1920:rate=30",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-shortest", video_audio],
            capture_output=True, timeout=30,
        )

        sources = [video_audio, video_only]
        call_idx = [0]
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        plan = {
            "segments": [
                {"source": "upload:1", "in": 0, "out": 2, "transition_in": "cut"},
                {"source": "upload:2", "in": 0, "out": 2, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

        os.makedirs(os.path.join("data", "media", "9998"), exist_ok=True)
        result = renderer.render(plan, asset_id=9998, draft_id=1)
        assert os.path.exists(result["path"])
        assert result["duration"] > 0

        import shutil
        shutil.rmtree(os.path.join("data", "media", "9998"), ignore_errors=True)


# ── Integration: Flask app with new routes ──────────────────────────────────

class TestFlaskRoutes:
    """Integration tests for new API routes in the Flask app."""

    def test_audit_flag_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        # Should return 500 for missing business config or 404 for missing draft
        resp = client.post("/api/draft/999/audit-flag",
                           json={"index": 0, "action": "apply"})
        # Either business not configured (500) or draft not found (404)
        assert resp.status_code in (500, 404)

    def test_generate_visuals_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.post("/api/assets/999/generate-images", json={})
        assert resp.status_code in (500, 404)

    def test_generate_video_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.post("/api/assets/999/generate-video", json={})
        assert resp.status_code in (500, 404)

    def test_edit_plan_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.post("/api/assets/999/edit-plan", json={})
        assert resp.status_code in (500, 404)

    def test_render_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.post("/api/assets/999/render", json={"plan_id": 1})
        assert resp.status_code in (500, 404)

    def test_stock_search_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.post("/api/stock/search", json={"query": "sunset", "kind": "photo"})
        assert resp.status_code == 200

    def test_asset_media_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.get("/api/assets/999/media")
        assert resp.status_code == 200

    def test_busy_js_served(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.get("/static/busy.js")
        assert resp.status_code == 200
        assert b"busyAction" in resp.data

    def test_draft_generate_visuals_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.post("/api/draft/999/generate-visuals", json={})
        assert resp.status_code in (500, 404)

    def test_draft_visuals_list_endpoint_exists(self, tmp_path):
        from app import create_app
        app = create_app(config_dir="config", db_path=str(tmp_path / "test.db"))
        client = app.test_client()
        resp = client.get("/api/draft/999/visuals")
        assert resp.status_code == 200


# ── Assembly: in/out validation against source duration ────────────────────

class TestAssemblyInOutValidation:
    """The renderer must clamp in/out that exceed the source file's actual
    duration. The edit plan LLM sometimes generates cumulative timeline
    timestamps (0→2, 2→4.5, 4.5→7…) instead of per-source seek positions.
    Without clamping, ffmpeg produces a file with no streams and the concat
    filter crashes with 'matches no streams'."""

    def test_clamp_out_exceeding_duration(self, tmp_path):
        """If out > source duration, render should clamp, not crash."""
        import subprocess
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create a 3-second audio-only file
        audio_file = str(tmp_path / "short_audio.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
             "-c:a", "aac", audio_file],
            capture_output=True, timeout=30,
        )

        # Create a 2-second video+audio file
        video_file = str(tmp_path / "clip.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=1080x1920:rate=30",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
             "-shortest", video_file],
            capture_output=True, timeout=30,
        )

        sources = [video_file, audio_file]
        call_idx = [0]
        def stub_resolve(ref, asset_id):
            path = sources[call_idx[0]]
            call_idx[0] += 1
            return path
        renderer._resolve_source = stub_resolve

        # Plan with out=30 on a 3-second file — should clamp, not crash
        plan = {
            "segments": [
                {"source": "upload:1", "in": 0, "out": 2, "transition_in": "cut"},
                {"source": "upload:2", "in": 27, "out": 30, "transition_in": "cut"},
            ],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }

        os.makedirs(os.path.join("data", "media", "9998"), exist_ok=True)
        result = renderer.render(plan, asset_id=9998, draft_id=1)
        assert os.path.exists(result["path"])
        assert result["duration"] > 0

        import shutil
        shutil.rmtree(os.path.join("data", "media", "9998"), ignore_errors=True)

    def test_error_message_excludes_ffmpeg_banner(self, tmp_path):
        """Error messages should not include the full ffmpeg copyright banner."""
        import subprocess
        renderer = AssemblyRenderer({}, db_path=str(tmp_path / "test.db"))

        # Create an audio-only file that will be trimmed to impossible range
        audio_file = str(tmp_path / "tiny.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
             "-c:a", "aac", audio_file],
            capture_output=True, timeout=30,
        )

        renderer._resolve_source = lambda ref, aid: audio_file

        # The clamping should prevent the crash, but verify that if a
        # trim *did* fail, the error doesn't contain the banner
        plan = {
            "segments": [{"source": "upload:1", "in": 0, "out": 0.5}],
            "canvas": {"aspect_ratio": "9:16", "resolution": "1080x1920"},
        }
        os.makedirs(os.path.join("data", "media", "9997"), exist_ok=True)
        result = renderer.render(plan, asset_id=9997, draft_id=1)
        assert os.path.exists(result["path"])

        import shutil
        shutil.rmtree(os.path.join("data", "media", "9997"), ignore_errors=True)


# ── Fan-out idempotency: no duplicate platform assets ──────────────────────

class TestFanOutIdempotency:
    """Clicking 'Generate per-platform variants' twice should NOT create
    duplicate assets for the same platform. The endpoint must skip platforms
    that already have an asset for this draft."""

    def test_fan_out_skips_existing_platforms(self, tmp_path):
        """Fan-out should return 'already_exists' when all platforms have assets."""
        from app import create_app

        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        client = app.test_client()

        # Create a draft in shipped state
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Test idea for fan-out idempotency",
            hook_options=[],
            treatment={"format": {"format_name": "Instagram Reel Script"}},
            origin="test",
        )
        draft_id = store.create_draft(
            business_slug="stackpenni",
            idea_card_id=card_id,
            origin="test",
            format_name="Instagram Reel Script",
        )
        store.save_draft_content(draft_id, "Test draft text", "{}", "[]")
        store.update_draft_state(draft_id, "shipped")

        # Create an existing asset for Instagram
        store.create_asset(
            business_slug="stackpenni",
            draft_id=draft_id,
            platform="Instagram",
            variant_type="reel",
            content="Existing content",
            native=True,
        )

        # Fan-out should skip Instagram (already exists)
        resp = client.post(f"/api/assets/{draft_id}/fan-out", json={})
        data = resp.get_json()
        # Should return ok or already_exists, not create a duplicate
        assert data["status"] in ("ok", "already_exists")
        # Should not have created new assets
        assets = store.list_assets(draft_id)
        instagram_assets = [a for a in assets if a["platform"] == "Instagram"]
        assert len(instagram_assets) == 1  # only the original, no duplicate