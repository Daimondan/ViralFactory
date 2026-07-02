"""
ViralFactory — T2.4 Visual Style Intake + Shot Library Tests

Tests for:
- VISUAL_STYLE_SCHEMA validation (valid passes, missing fields fail)
- SHOT_LIBRARY_ITEM_SCHEMA validation
- visual_style_to_markdown converter
- shot_library_to_markdown converter
- Gate enforcement (approved writes both modules, parked writes nothing)
- API endpoints (shot library item, visual style input, store)
- Page route returns 200
- Zero tenant strings in new code/prompts
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
    VISUAL_STYLE_SCHEMA, visual_style_to_markdown,
    SHOT_LIBRARY_ITEM_SCHEMA, shot_library_to_markdown,
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
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)
            business = {
                "business": {"name": "TestBrand", "slug": "testbrand", "description": "Test"},
                "subjects": ["AI"],
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


@pytest.fixture
def valid_style_guide():
    return {
        "palette": {
            "primary": {"hex": "#1A1A2E", "name": "Deep Navy"},
            "secondary": {"hex": "#16213E", "name": "Midnight Blue"},
            "accent": {"hex": "#E94560", "name": "Electric Coral"},
            "background": {"hex": "#0F0F0F", "name": "Near Black"},
        },
        "typography": {
            "feel": "Clean and bold, modern sans-serif",
            "weight": "Medium to bold for headers, regular for body",
            "sizing": "Large headers, generous line height",
        },
        "stylization_level": "moderate",
        "stylization_rationale": "Balance real footage with stylized graphics for a polished but authentic look.",
        "blend_rules": {
            "real_anchors": ["Lifestyle shots require real phone footage", "Receipts and documents must be real"],
            "generated_supporting": ["Background textures and patterns", "Data visualization graphics"],
            "disclosure": ["Label AI-generated visuals per platform policy"],
        },
        "platform_adjustments": [
            {"platform": "X", "aspect_ratio": "16:9", "notes": "Landscape for feed cards"},
            {"platform": "Instagram", "aspect_ratio": "4:5", "notes": "Portrait for maximum feed real estate"},
        ],
        "shot_library_usage": "Reference shot library items by tag when building visual direction blocks in drafts.",
        "summary": "Clean, bold visual identity with real footage as the anchor and stylized graphics as supporting layer.",
    }


@pytest.fixture
def valid_shot_items():
    return [
        {
            "description": "Street market at noon with vendors selling fruit",
            "tags": ["market", "street", "vendors", "fruit", "daytime"],
            "mood": "warm",
            "best_for": ["cultural observation", "lifestyle"],
            "platforms": ["IG", "X"],
        },
        {
            "description": "Close-up of a receipt on a wooden table",
            "tags": ["receipt", "close-up", "money", "table"],
            "mood": "documentary",
            "best_for": ["money lesson", "data drop"],
            "platforms": ["IG"],
        },
    ]


# --- Schema Tests ---

class TestVisualStyleSchema:

    def test_valid_passes(self, valid_style_guide):
        result = validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")
        assert result["palette"]["primary"]["hex"] == "#1A1A2E"
        assert result["stylization_level"] == "moderate"

    def test_missing_palette_fails(self, valid_style_guide):
        del valid_style_guide["palette"]
        with pytest.raises(ValidationError, match="palette"):
            validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")

    def test_missing_typography_fails(self, valid_style_guide):
        del valid_style_guide["typography"]
        with pytest.raises(ValidationError, match="typography"):
            validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")

    def test_missing_blend_rules_fails(self, valid_style_guide):
        del valid_style_guide["blend_rules"]
        with pytest.raises(ValidationError, match="blend_rules"):
            validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")

    def test_missing_platform_adjustments_fails(self, valid_style_guide):
        del valid_style_guide["platform_adjustments"]
        with pytest.raises(ValidationError, match="platform_adjustments"):
            validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")

    def test_missing_summary_fails(self, valid_style_guide):
        del valid_style_guide["summary"]
        with pytest.raises(ValidationError, match="summary"):
            validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")

    def test_palette_missing_hex_fails(self, valid_style_guide):
        del valid_style_guide["palette"]["primary"]["hex"]
        with pytest.raises(ValidationError, match="hex"):
            validate_llm_output(json.dumps(valid_style_guide), VISUAL_STYLE_SCHEMA, context="test")


class TestShotLibraryItemSchema:

    def test_valid_passes(self, valid_shot_items):
        item = valid_shot_items[0]
        result = validate_llm_output(json.dumps(item), SHOT_LIBRARY_ITEM_SCHEMA, context="test")
        assert result["tags"][0] == "market"
        assert len(result["tags"]) == 5

    def test_missing_tags_fails(self, valid_shot_items):
        item = valid_shot_items[0]
        del item["tags"]
        with pytest.raises(ValidationError, match="tags"):
            validate_llm_output(json.dumps(item), SHOT_LIBRARY_ITEM_SCHEMA, context="test")

    def test_missing_description_fails(self, valid_shot_items):
        item = valid_shot_items[0]
        del item["description"]
        with pytest.raises(ValidationError, match="description"):
            validate_llm_output(json.dumps(item), SHOT_LIBRARY_ITEM_SCHEMA, context="test")


# --- Converter Tests ---

class TestVisualStyleConverter:

    def test_markdown_has_all_sections(self, valid_style_guide):
        md = visual_style_to_markdown(valid_style_guide, "1.0")
        assert "# Visual Style Guide — v1.0" in md
        assert "## Summary" in md
        assert "## Palette" in md
        assert "Deep Navy" in md
        assert "#1A1A2E" in md
        assert "## Typography" in md
        assert "## Stylization level" in md
        assert "moderate" in md
        assert "## Blend rules" in md
        assert "Real anchors" in md
        assert "Generated supporting" in md
        assert "Disclosure" in md
        assert "## Platform adjustments" in md
        assert "## Shot library usage" in md
        assert "visual_style_v1" in md

    def test_markdown_has_provenance(self, valid_style_guide):
        md = visual_style_to_markdown(valid_style_guide, "1.0")
        assert "## Provenance" in md
        assert "Version: 1.0" in md


class TestShotLibraryConverter:

    def test_markdown_has_items(self, valid_shot_items):
        md = shot_library_to_markdown(valid_shot_items, "1.0")
        assert "# Shot Library — v1.0" in md
        assert "2 indexed items" in md
        assert "### Item 1" in md
        assert "### Item 2" in md
        assert "Street market" in md
        assert "receipt" in md
        assert "shot_library_v1" in md

    def test_empty_library(self):
        md = shot_library_to_markdown([], "1.0")
        assert "0 indexed items" in md


# --- Gate Enforcement Tests ---

class TestVisualStyleGateEnforcement:

    def test_approved_writes_both_modules(self, valid_style_guide, valid_shot_items, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("visual-style-intake", "1.0", "testbrand")
        runner.set_gate_result(run_id, "4", "approve", "test")
        token = generate_gate_token(run_id)

        # Write visual-style module
        md = visual_style_to_markdown(valid_style_guide, "1.0")
        path1 = store.store("testbrand", "visual-style", md, version="1.0",
                            provenance={"version": "1.0"}, gate_token=token, run_id=run_id)
        assert os.path.exists(path1)

        # Write shot-library module
        sl_md = shot_library_to_markdown(valid_shot_items, "1.0")
        path2 = store.store("testbrand", "shot-library", sl_md, version="1.0",
                            provenance={"version": "1.0"}, gate_token=token, run_id=run_id)
        assert os.path.exists(path2)

        # Verify content
        assert "Deep Navy" in store.load("testbrand", "visual-style")
        assert "Street market" in store.load("testbrand", "shot-library")

    def test_parked_writes_nothing(self, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "visual-style")
        assert not store.exists("testbrand", "shot-library")

    def test_no_token_raises(self, valid_style_guide, tmp_dirs):
        config_dir, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        md = visual_style_to_markdown(valid_style_guide, "1.0")
        with pytest.raises(GateTokenError):
            store.store("testbrand", "visual-style", md, version="1.0",
                       provenance={"version": "1.0"})


# --- API Integration Tests ---

class TestVisualStyleAPI:

    @pytest.fixture
    def app_client(self, tmp_dirs):
        from app import create_app
        config_dir, modules_dir, db_path = tmp_dirs
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        pb_dir = os.path.abspath(os.path.join(repo_root, "playbooks"))
        app = create_app(config_dir=config_dir, db_path=db_path, playbooks_dir=pb_dir)
        client = app.test_client()
        yield client, db_path, modules_dir

    def test_shot_library_item_api(self, app_client):
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("visual-style-intake", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/shot-library-item",
            data=json.dumps({"description": "Market scene at noon"}),
            content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["count"] == 1

    def test_visual_style_input_api(self, app_client):
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("visual-style-intake", "1.0", "testbrand")

        resp = client.post(f"/api/run/{run_id}/visual-style-input",
            data=json.dumps({"key": "brand_assets", "value": "Logo: blue geometric mark"}),
            content_type="application/json")
        assert resp.status_code == 200

    def test_store_parked_writes_nothing(self, app_client, valid_style_guide):
        client, db_path, modules_dir = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("visual-style-intake", "1.0", "testbrand")
        runner.add_llm_output(run_id, "style_guide", valid_style_guide)

        resp = client.post(f"/api/run/{run_id}/store-visual-style",
            data=json.dumps({"approved": False, "version": "1.0"}),
            content_type="application/json")
        assert resp.status_code == 200
        assert resp.get_json()["approved"] is False
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        assert not store.exists("testbrand", "visual-style")

    def test_page_route_returns_200(self, app_client):
        client, db_path, _ = app_client
        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("visual-style-intake", "1.0", "testbrand")
        resp = client.get(f"/onboard/visual-style-intake/{run_id}/visual-style")
        assert resp.status_code == 200


# --- Zero Tenant Strings ---

class TestNoTenantStringsT24:

    def test_no_stackpenni_in_new_prompts(self):
        prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts", "visual_style")
        for fname in os.listdir(prompts_dir):
            if not fname.endswith(".md"):
                continue
            with open(os.path.join(prompts_dir, fname), "r") as f:
                content = f.read()
            assert "stackpenni" not in content.lower(), f"Tenant string in {fname}"
            assert "caribbean" not in content.lower(), f"Tenant string in {fname}"

    def test_no_stackpenni_in_template(self):
        tmpl = os.path.join(os.path.dirname(__file__), "..", "src", "templates", "visual_style.html")
        with open(tmpl, "r") as f:
            content = f.read()
        assert "stackpenni" not in content.lower()
        assert "caribbean" not in content.lower()