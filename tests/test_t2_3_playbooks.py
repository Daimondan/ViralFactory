"""
ViralFactory — T2.3 Playbook Tests

Tests for 4 playbooks: Viral Patterns, Audience Insights, Story Frameworks, Format Guide.

For each playbook:
- Schema validation (valid data passes, missing required fields fail)
- Markdown converter (all required sections present)
- Gate enforcement (approved writes module, parked writes nothing)
- API endpoint integration (input collection, analysis mocked, store with gate token)
- Zero tenant strings in new schemas/converters
- Format Guide AMENDMENT-004 enrichment fields present
"""

import json
import os
import tempfile
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from config_loader import load_all, ConfigError
from module_store import (
    ModuleStore, generate_gate_token, GateTokenError,
    VIRAL_PATTERNS_SCHEMA, viral_patterns_to_markdown,
    AUDIENCE_INSIGHTS_SCHEMA, audience_insights_to_markdown,
    STORY_FRAMEWORKS_SCHEMA, story_frameworks_to_markdown,
    FORMAT_GUIDE_SCHEMA, format_guide_to_markdown,
)
from validator import validate_llm_output, ValidationError
from playbook_runner import PlaybookRunner


# --- Fixtures ---

@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def tmp_dirs():
    """Temporary config dir + modules dir + db for integration tests."""
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)

            business = {
                "business": {"name": "TestBrand", "slug": "testbrand", "description": "Test"},
                "subjects": ["AI", "wealth"],
                "platforms": [{"name": "X", "handle": "@t", "priority": 1}],
            }
            with open(os.path.join(config_dir, "business.yaml"), "w") as f:
                yaml.dump(business, f)
            models = {
                "active": {"default": "tb", "drafter": "tb", "drafter_ab_candidate": None},
                "tb": {"provider": "ollama_cloud", "model": "m", "temperature": 0, "max_tokens": 4, "base_url": "https://x.com"},
            }
            with open(os.path.join(config_dir, "models.yaml"), "w") as f:
                yaml.dump(models, f)
            sources = {"feeds": [], "channels": [], "queries": []}
            with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
                yaml.dump(sources, f)

            yield config_dir, modules_dir, db_path
            if os.path.exists(db_path):
                os.unlink(db_path)


# --- Valid data fixtures ---

@pytest.fixture
def valid_viral_patterns():
    return {
        "patterns": [
            {
                "name": "Contrarian Truth Bomb",
                "hook_type": "Contrarian opening",
                "structure": "Claim → evidence → pivot",
                "emotional_beat": "Surprise then relief",
                "format": "thread",
                "pacing": "fast",
                "why_it_likely_worked": "Appears to work because it challenges conventional wisdom early",
                "examples": [
                    {"url": "https://example.com/1", "name": "Example 1", "note": "Great hook"}
                ],
            },
        ],
        "never_list": [
            {"pattern": "Content-mill SEO", "reason": "No original reporting", "evidence": "Anti-example 1"}
        ],
        "summary": "Patterns favor contrarian opens with evidence backing.",
    }


@pytest.fixture
def valid_audience_insights():
    return {
        "who_they_are": "Entrepreneurs 25-45 interested in AI",
        "what_they_care_about": [
            {"concern": "ROI of AI tools", "type": "belief", "evidence": ["operator assumption"]}
        ],
        "language": [
            {"phrase": "real talk", "context": "comments", "type": "evidence"}
        ],
        "what_they_reward": [
            {"behavior": "Practical examples", "type": "belief", "evidence": ["operator belief"]}
        ],
        "what_turns_them_off": [
            {"turn_off": "Jargon-heavy content", "type": "evidence", "evidence": ["comment feedback"]}
        ],
        "evidence_vs_belief": "Most beliefs are untested; evidence from comments supports anti-jargon stance.",
        "summary": "Audience values practical, jargon-free AI content.",
    }


@pytest.fixture
def valid_story_frameworks():
    return {
        "frameworks": [
            {
                "subject_type": "AI",
                "structure_name": "dramatic_arc",
                "beats": [
                    {"name": "entry_point", "content": "Start with a contrarian claim about AI"},
                    {"name": "tension", "content": "The gap between AI hype and practical ROI"},
                    {"name": "turn", "content": "Show a specific real-world example"},
                    {"name": "landing", "content": "Practical takeaway the reader can use"},
                ],
                "grounded_in_example": "https://example.com/ai-thread",
                "grounded_in_story": "The time I saw a startup waste $50k on AI tools",
                "voice_compatible": True,
                "voice_note": "",
            },
        ],
        "summary": "One framework per subject type, grounded in real examples.",
    }


@pytest.fixture
def valid_format_guide():
    return {
        "formats": [
            {
                "format_name": "X Thread",
                "platforms": ["X"],
                "best_for": ["contrarian takes", "data drops"],
                "length": "5-15 tweets",
                "structure_notes": "Hook tweet → body tweets → CTA tweet",
                "skeleton": "1. Hook: [contrarian claim]\n2-N. Evidence/support\nN+1. CTA: [what to do next]",
                "requires_human_capture": "none",
                "capture_tasks": [],
                "effort_level": "low",
                "reuse_pathways": ["Carousel on IG", "Newsletter section"],
                "status": "proven",
                "provenance": "Derived from Viral Patterns analysis",
            },
            {
                "format_name": "IG Reel with Footage",
                "platforms": ["Instagram"],
                "best_for": ["cultural observations", "on-the-ground content"],
                "length": "15-30 seconds",
                "structure_notes": "Text overlay on real footage",
                "skeleton": "1. Open: [street footage 3s]\n2. Text: [claim]\n3. Footage: [supporting visuals]\n4. Text: [takeaway]",
                "requires_human_capture": "required",
                "capture_tasks": ["Record 15s of street footage", "Photograph relevant scene"],
                "effort_level": "medium",
                "reuse_pathways": ["Extract single frame for carousel"],
                "status": "experimental",
                "provenance": "Operator request for more visual content",
            },
        ],
        "decision_table": [
            {"message_type": "contrarian take", "platform": "X", "recommended_format": "X Thread", "rationale": "Threads allow building an argument"}
        ],
        "summary": "X threads for takes, IG reels for on-the-ground content.",
    }


# ────────────────────────────────────────────────────────────────────
# Viral Patterns Tests
# ────────────────────────────────────────────────────────────────────

class TestViralPatternsSchema:

    def test_valid_passes(self, valid_viral_patterns):
        raw = json.dumps(valid_viral_patterns)
        result = validate_llm_output(raw, VIRAL_PATTERNS_SCHEMA, context="test")
        assert result["patterns"][0]["name"] == "Contrarian Truth Bomb"
        assert len(result["never_list"]) == 1

    def test_missing_patterns_fails(self, valid_viral_patterns):
        del valid_viral_patterns["patterns"]
        with pytest.raises(ValidationError, match="patterns"):
            validate_llm_output(json.dumps(valid_viral_patterns), VIRAL_PATTERNS_SCHEMA, context="test")

    def test_missing_never_list_fails(self, valid_viral_patterns):
        del valid_viral_patterns["never_list"]
        with pytest.raises(ValidationError, match="never_list"):
            validate_llm_output(json.dumps(valid_viral_patterns), VIRAL_PATTERNS_SCHEMA, context="test")

    def test_missing_summary_fails(self, valid_viral_patterns):
        del valid_viral_patterns["summary"]
        with pytest.raises(ValidationError, match="summary"):
            validate_llm_output(json.dumps(valid_viral_patterns), VIRAL_PATTERNS_SCHEMA, context="test")


class TestViralPatternsConverter:

    def test_markdown_has_all_sections(self, valid_viral_patterns):
        md = viral_patterns_to_markdown(valid_viral_patterns, "1.0")
        assert "# Viral Patterns Playbook — v1.0" in md
        assert "## Summary" in md
        assert "## Patterns" in md
        assert "Contrarian Truth Bomb" in md
        assert "Hook type" in md
        assert "hypothesis" in md.lower()
        assert "## Never list" in md
        assert "Content-mill SEO" in md
        assert "viral_patterns_v1" in md

    def test_markdown_has_provenance(self, valid_viral_patterns):
        md = viral_patterns_to_markdown(valid_viral_patterns, "1.0")
        assert "## Provenance" in md
        assert "Version: 1.0" in md


class TestViralPatternsGateEnforcement:

    def test_approved_writes_module(self, valid_viral_patterns, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        md = viral_patterns_to_markdown(valid_viral_patterns, "1.0")

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("viral-patterns-starter", "1.0", "testbrand")
        runner.set_gate_result(run_id, "5", "approve", "test")
        token = generate_gate_token(run_id)

        path = store.store("testbrand", "viral-patterns", md, version="1.0",
                           provenance={"version": "1.0"}, gate_token=token, run_id=run_id)
        assert os.path.exists(path)
        loaded = store.load("testbrand", "viral-patterns")
        assert "Contrarian Truth Bomb" in loaded

    def test_parked_does_not_write(self, valid_viral_patterns, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "viral-patterns")

    def test_no_token_raises(self, valid_viral_patterns, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        md = viral_patterns_to_markdown(valid_viral_patterns, "1.0")
        with pytest.raises(GateTokenError):
            store.store("testbrand", "viral-patterns", md, version="1.0",
                       provenance={"version": "1.0"})


# ────────────────────────────────────────────────────────────────────
# Audience Insights Tests
# ────────────────────────────────────────────────────────────────────

class TestAudienceInsightsSchema:

    def test_valid_passes(self, valid_audience_insights):
        result = validate_llm_output(json.dumps(valid_audience_insights), AUDIENCE_INSIGHTS_SCHEMA, context="test")
        assert result["who_they_are"] == "Entrepreneurs 25-45 interested in AI"
        assert len(result["what_they_care_about"]) == 1

    def test_missing_who_they_are_fails(self, valid_audience_insights):
        del valid_audience_insights["who_they_are"]
        with pytest.raises(ValidationError, match="who_they_are"):
            validate_llm_output(json.dumps(valid_audience_insights), AUDIENCE_INSIGHTS_SCHEMA, context="test")

    def test_missing_language_fails(self, valid_audience_insights):
        del valid_audience_insights["language"]
        with pytest.raises(ValidationError, match="language"):
            validate_llm_output(json.dumps(valid_audience_insights), AUDIENCE_INSIGHTS_SCHEMA, context="test")


class TestAudienceInsightsConverter:

    def test_markdown_has_all_sections(self, valid_audience_insights):
        md = audience_insights_to_markdown(valid_audience_insights, "1.0")
        assert "# Audience Insights — v1.0" in md
        assert "## Who they are" in md
        assert "## What they care about" in md
        assert "## Language they use" in md
        assert "## What they reward" in md
        assert "## What turns them off" in md
        assert "## Evidence vs belief" in md
        assert "audience_insights_v1" in md
        assert "real talk" in md


class TestAudienceInsightsGateEnforcement:

    def test_approved_writes_module(self, valid_audience_insights, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        md = audience_insights_to_markdown(valid_audience_insights, "1.0")

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("audience-insights-builder", "1.0", "testbrand")
        runner.set_gate_result(run_id, "3", "approve", "test")
        token = generate_gate_token(run_id)

        path = store.store("testbrand", "audience-insights", md, version="1.0",
                           provenance={"version": "1.0"}, gate_token=token, run_id=run_id)
        assert os.path.exists(path)
        loaded = store.load("testbrand", "audience-insights")
        assert "Entrepreneurs" in loaded

    def test_parked_does_not_write(self, valid_audience_insights, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "audience-insights")


# ────────────────────────────────────────────────────────────────────
# Story Frameworks Tests
# ────────────────────────────────────────────────────────────────────

class TestStoryFrameworksSchema:

    def test_valid_passes(self, valid_story_frameworks):
        result = validate_llm_output(json.dumps(valid_story_frameworks), STORY_FRAMEWORKS_SCHEMA, context="test")
        assert result["frameworks"][0]["subject_type"] == "AI"
        assert result["frameworks"][0]["voice_compatible"] is True

    def test_missing_frameworks_fails(self, valid_story_frameworks):
        del valid_story_frameworks["frameworks"]
        with pytest.raises(ValidationError, match="frameworks"):
            validate_llm_output(json.dumps(valid_story_frameworks), STORY_FRAMEWORKS_SCHEMA, context="test")

    def test_missing_structure_name_fails(self, valid_story_frameworks):
        del valid_story_frameworks["frameworks"][0]["structure_name"]
        with pytest.raises(ValidationError, match="structure_name"):
            validate_llm_output(json.dumps(valid_story_frameworks), STORY_FRAMEWORKS_SCHEMA, context="test")

    def test_voice_compatible_must_be_boolean(self, valid_story_frameworks):
        valid_story_frameworks["frameworks"][0]["voice_compatible"] = "yes"
        with pytest.raises(ValidationError):
            validate_llm_output(json.dumps(valid_story_frameworks), STORY_FRAMEWORKS_SCHEMA, context="test")


class TestStoryFrameworksConverter:

    def test_markdown_has_all_sections(self, valid_story_frameworks):
        md = story_frameworks_to_markdown(valid_story_frameworks, "1.0")
        assert "# Story Frameworks — v1.0" in md
        assert "## Frameworks" in md
        assert "### AI" in md
        assert "Structure:" in md
        assert "Entry Point" in md
        assert "Tension" in md
        assert "Turn" in md
        assert "Landing" in md
        assert "Voice compatible" in md
        assert "story_frameworks_v2" in md


class TestStoryFrameworksGateEnforcement:

    def test_approved_writes_module(self, valid_story_frameworks, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        md = story_frameworks_to_markdown(valid_story_frameworks, "1.0")

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("story-frameworks-starter", "1.0", "testbrand")
        runner.set_gate_result(run_id, "3", "approve", "test")
        token = generate_gate_token(run_id)

        path = store.store("testbrand", "story-frameworks", md, version="1.0",
                           provenance={"version": "1.0"}, gate_token=token, run_id=run_id)
        assert os.path.exists(path)
        loaded = store.load("testbrand", "story-frameworks")
        assert "contrarian claim" in loaded


# ────────────────────────────────────────────────────────────────────
# Format Guide Tests (with AMENDMENT-004 enrichment)
# ────────────────────────────────────────────────────────────────────

class TestFormatGuideSchema:

    def test_valid_passes(self, valid_format_guide):
        result = validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")
        assert len(result["formats"]) == 2
        assert result["formats"][0]["format_name"] == "X Thread"
        assert result["formats"][1]["format_name"] == "IG Reel with Footage"

    def test_missing_formats_fails(self, valid_format_guide):
        del valid_format_guide["formats"]
        with pytest.raises(ValidationError, match="formats"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_missing_decision_table_fails(self, valid_format_guide):
        del valid_format_guide["decision_table"]
        with pytest.raises(ValidationError, match="decision_table"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    # AMENDMENT-004 enrichment field tests

    def test_requires_human_capture_required(self, valid_format_guide):
        """Format Guide must have requires_human_capture field."""
        del valid_format_guide["formats"][1]["requires_human_capture"]
        with pytest.raises(ValidationError, match="requires_human_capture"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_effort_level_present(self, valid_format_guide):
        """Format Guide must have effort_level field."""
        del valid_format_guide["formats"][0]["effort_level"]
        with pytest.raises(ValidationError, match="effort_level"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_capture_tasks_present(self, valid_format_guide):
        """Format Guide must have capture_tasks field (can be empty)."""
        del valid_format_guide["formats"][0]["capture_tasks"]
        with pytest.raises(ValidationError, match="capture_tasks"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_reuse_pathways_present(self, valid_format_guide):
        """Format Guide must have reuse_pathways field."""
        del valid_format_guide["formats"][0]["reuse_pathways"]
        with pytest.raises(ValidationError, match="reuse_pathways"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_status_present(self, valid_format_guide):
        """Format Guide must have status field (proven|experimental|retired)."""
        del valid_format_guide["formats"][0]["status"]
        with pytest.raises(ValidationError, match="status"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_provenance_present(self, valid_format_guide):
        """Format Guide must have provenance field."""
        del valid_format_guide["formats"][0]["provenance"]
        with pytest.raises(ValidationError, match="provenance"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")

    def test_best_for_present(self, valid_format_guide):
        """Format Guide must have best_for field."""
        del valid_format_guide["formats"][0]["best_for"]
        with pytest.raises(ValidationError, match="best_for"):
            validate_llm_output(json.dumps(valid_format_guide), FORMAT_GUIDE_SCHEMA, context="test")


class TestFormatGuideConverter:

    def test_markdown_has_all_sections(self, valid_format_guide):
        md = format_guide_to_markdown(valid_format_guide, "1.0")
        assert "# Format Guide — v1.0" in md
        assert "## Formats" in md
        assert "### X Thread" in md
        assert "### IG Reel with Footage" in md
        assert "## Decision table" in md
        assert "format_guide_v1" in md

    def test_markdown_has_amendment004_fields(self, valid_format_guide):
        """Converter output includes AMENDMENT-004 enrichment fields."""
        md = format_guide_to_markdown(valid_format_guide, "1.0")
        assert "Requires human capture" in md
        assert "Capture tasks" in md
        assert "Effort level" in md
        assert "Reuse pathways" in md
        assert "Status" in md
        assert "Provenance" in md
        # Check values
        assert "none" in md
        assert "required" in md
        assert "proven" in md
        assert "experimental" in md
        assert "Record 15s of street footage" in md

    def test_markdown_has_skeleton(self, valid_format_guide):
        md = format_guide_to_markdown(valid_format_guide, "1.0")
        assert "Skeleton" in md
        assert "Hook" in md  # from the skeleton content


class TestFormatGuideGateEnforcement:

    def test_approved_writes_module(self, valid_format_guide, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        md = format_guide_to_markdown(valid_format_guide, "1.0")

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("format-guide-starter", "1.0", "testbrand")
        runner.set_gate_result(run_id, "3", "approve", "test")
        token = generate_gate_token(run_id)

        path = store.store("testbrand", "format-guide", md, version="1.0",
                           provenance={"version": "1.0"}, gate_token=token, run_id=run_id)
        assert os.path.exists(path)
        loaded = store.load("testbrand", "format-guide")
        assert "X Thread" in loaded
        assert "Capture tasks" in loaded

    def test_parked_does_not_write(self, valid_format_guide, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "format-guide")


# ────────────────────────────────────────────────────────────────────
# API Integration Tests (Flask test client)
# ────────────────────────────────────────────────────────────────────

class TestAPIIntegration:
    """Test the API endpoints for all 4 playbooks using Flask test client."""

    @pytest.fixture
    def app_client(self, tmp_dirs):
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        # Use absolute path to playbooks dir so it works regardless of CWD
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        pb_dir = os.path.abspath(os.path.join(repo_root, "playbooks"))
        app = create_app(config_dir=config_dir, db_path=db_path, playbooks_dir=pb_dir)
        app.config["MODULES_DIR"] = modules_dir
        client = app.test_client()
        yield client, db_path, modules_dir

    def test_viral_patterns_admired_example_api(self, app_client):
        """Add admired example via API."""
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("viral-patterns-starter", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/admired-example",
            data=json.dumps({"url": "https://example.com", "name": "Test", "note": "good"}),
            content_type="application/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["count"] == 1

    def test_viral_patterns_anti_example_api(self, app_client):
        """Add anti-example via API."""
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("viral-patterns-starter", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/viral-anti-example",
            data=json.dumps({"description": "SEO slop"}),
            content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1

    def test_audience_input_api(self, app_client):
        """Add audience input via API."""
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("audience-insights-builder", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/audience-input",
            data=json.dumps({"key": "audience_operator_desc", "value": "Testers who like AI"}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_story_input_api(self, app_client):
        """Add story input via API."""
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("story-frameworks-starter", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/story-input",
            data=json.dumps({"key": "operator_stories", "value": "Once upon a time..."}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_format_input_api(self, app_client):
        """Add format input via API."""
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("format-guide-starter", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/format-input",
            data=json.dumps({"key": "format_observations", "value": "Threads work well"}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_store_viral_patterns_parked_writes_nothing(self, app_client, valid_viral_patterns):
        """Parked viral patterns does not write module."""
        client, db_path, modules_dir = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("viral-patterns-starter", "1.0", "testbrand")
        runner.add_llm_output(run_id, "patterns", valid_viral_patterns)

        resp = client.post(f"/api/run/{run_id}/store-viral-patterns",
            data=json.dumps({"approved": False, "version": "1.0"}),
            content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["approved"] is False
        # Module should not exist
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "viral-patterns")

    def test_store_format_guide_parked_writes_nothing(self, app_client, valid_format_guide):
        """Parked format guide does not write module."""
        client, db_path, modules_dir = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("format-guide-starter", "1.0", "testbrand")
        runner.add_llm_output(run_id, "guide", valid_format_guide)

        resp = client.post(f"/api/run/{run_id}/store-format-guide",
            data=json.dumps({"approved": False, "version": "1.0"}),
            content_type="application/json")
        assert resp.status_code == 200
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "format-guide")

    def test_page_routes_return_200(self, app_client):
        """All 4 playbook intake pages return 200."""
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        for playbook in ["viral-patterns-starter", "audience-insights-builder",
                         "story-frameworks-starter", "format-guide-starter"]:
            run_id = runner.start_run(playbook, "1.0", "testbrand")
            route_map = {
                "viral-patterns-starter": "viral-patterns",
                "audience-insights-builder": "audience-insights",
                "story-frameworks-starter": "story-frameworks",
                "format-guide-starter": "format-guide",
            }
            route = route_map[playbook]
            resp = client.get(f"/onboard/{playbook}/{run_id}/{route}")
            assert resp.status_code == 200, f"{playbook} page returned {resp.status_code}"


# ────────────────────────────────────────────────────────────────────
# Zero Tenant Strings (extended for T2.3)
# ────────────────────────────────────────────────────────────────────

class TestNoTenantStringsT23:
    """No hardcoded business values in new schemas/converters."""

    def test_no_stackpenni_in_module_store(self):
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        filepath = os.path.join(src_dir, "module_store.py")
        with open(filepath, "r") as f:
            content = f.read()
        for line_num, line in enumerate(content.split("\n"), 1):
            lower = line.lower()
            if "stackpenni" in lower and "import" not in lower:
                pytest.fail(f"Tenant string in module_store.py:{line_num}: {line.strip()}")

    def test_no_stackpenni_in_app(self):
        src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
        filepath = os.path.join(src_dir, "app.py")
        with open(filepath, "r") as f:
            content = f.read()
        for line_num, line in enumerate(content.split("\n"), 1):
            lower = line.lower()
            if "stackpenni" in lower and "import" not in lower:
                pytest.fail(f"Tenant string in app.py:{line_num}: {line.strip()}")

    def test_no_caribbean_in_new_prompts(self):
        """No hardcoded Caribbean references in prompt templates."""
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
        for subdir in ["viral_patterns", "audience_insights", "story_frameworks", "format_guide"]:
            prompt_path = os.path.join(prompts_dir, subdir, "analyze_v1.md")
            if os.path.exists(prompt_path):
                with open(prompt_path, "r") as f:
                    content = f.read()
                assert "caribbean" not in content.lower(), f"Tenant string in {prompt_path}"