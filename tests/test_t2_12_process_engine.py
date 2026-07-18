"""
Tests for T2.12: Process registry + compose-and-run engine (AMENDMENT-005).

AC:
- ideas and draft routes contain zero inline module wiring
- magic truncation slices gone
- every provenance row records registry version
- process registry is versioned data with gate-only writes
"""
import os
import json
import pytest
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from process_engine import (
    load_process_registry, compose_and_run, ProcessError,
    _resolve_input, _apply_transform,
)


@pytest.fixture
def tmp_config(tmp_path):
    """Create a temp config dir with processes.yaml."""
    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)

    processes_yaml = """
processes:
  test_process:
    prompt_file: "test/prompt_v1.md"
    backend: "default"
    schema: "TEST_SCHEMA"
    context_template: "Test process | module_ctx: {module_prov}"
    inputs:
      business_name: {source: business, field: "business.name"}
      subjects: {source: business, field: "subjects", transform: "join_comma"}
      module_views: "test/prompt_v1.md"
      origin_type: {source: dynamic, default: "ai_originated"}
      visual_style: {source: dynamic}
      num_cards: {source: static, value: "3"}
      existing_ideas: {source: dynamic, builder: "existing_ideas"}

schemas:
  TEST_SCHEMA: "inline:test_schema"
"""
    with open(os.path.join(config_dir, "processes.yaml"), "w") as f:
        f.write(processes_yaml)

    return config_dir


class TestProcessRegistry:
    """T2.12: Process registry loads and validates."""

    def test_load_process_registry(self, tmp_config):
        """Registry loads from processes.yaml."""
        reg = load_process_registry(tmp_config)
        assert "processes" in reg
        assert "test_process" in reg["processes"]
        assert reg["processes"]["test_process"]["prompt_file"] == "test/prompt_v1.md"

    def test_missing_processes_key_raises(self, tmp_path):
        """Missing 'processes' key raises ProcessError."""
        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "processes.yaml"), "w") as f:
            f.write("schemas: {}\n")
        with pytest.raises(ProcessError, match="missing 'processes'"):
            load_process_registry(config_dir)

    def test_missing_file_returns_empty(self, tmp_path):
        """Missing processes.yaml returns empty dict (graceful degradation)."""
        from config_loader import load_processes
        result = load_processes(str(tmp_path / "nonexistent"))
        assert result == {"processes": {}, "schemas": {}}

    def test_config_loader_load_all_includes_processes(self, tmp_path):
        """load_all includes processes key."""
        from config_loader import load_all, load_business, load_models, load_sources
        config_dir = str(tmp_path / "config")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "business.yaml"), "w") as f:
            yaml.dump({"business": {"name": "T", "slug": "t", "description": "T"},
                        "subjects": ["AI"], "platforms": [{"name": "X", "handle": "@t", "priority": 1}]}, f)
        with open(os.path.join(config_dir, "models.yaml"), "w") as f:
            yaml.dump({"active": {"default": "tb", "drafter": "tb"},
                        "tb": {"provider": "ollama_cloud", "model": "m", "temperature": 0,
                               "max_tokens": 100, "base_url": ""}}, f)
        with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
            yaml.dump({"feeds": [], "channels": [], "queries": []}, f)
        with open(os.path.join(config_dir, "processes.yaml"), "w") as f:
            yaml.dump({"processes": {"test": {"prompt_file": "t.md"}}}, f)

        config = load_all(config_dir)
        assert "processes" in config
        assert "test" in config["processes"]["processes"]


class TestTransforms:
    """T2.12: Transform functions work correctly."""

    def test_join_comma(self):
        assert _apply_transform(["a", "b", "c"], "join_comma") == "a, b, c"

    def test_join_newline_bullet(self):
        assert _apply_transform(["a", "b"], "join_newline_bullet") == "- a\n- b"

    def test_truncate(self):
        assert _apply_transform("hello world", "truncate_5") == "hello"

    def test_json_truncate(self):
        result = _apply_transform({"key": "value"}, "json_truncate_1000")
        assert "key" in result


class TestResolveInput:
    """T2.12: Input resolution from different sources."""

    def test_business_source(self):
        business = {"business": {"name": "TestBrand"}, "subjects": ["AI", "Wealth"]}
        spec = {"source": "business", "field": "business.name"}
        assert _resolve_input(spec, business, {}, {}, {}) == "TestBrand"

    def test_business_with_transform(self):
        business = {"business": {"name": "T"}, "subjects": ["AI", "Wealth"]}
        spec = {"source": "business", "field": "subjects", "transform": "join_comma"}
        assert _resolve_input(spec, business, {}, {}, {}) == "AI, Wealth"

    def test_static_source(self):
        spec = {"source": "static", "value": "3"}
        assert _resolve_input(spec, {}, {}, {}, {}) == "3"

    def test_dynamic_source(self):
        spec = {"source": "dynamic", "field": "num_cards", "default": "3"}
        assert _resolve_input(spec, {}, {"num_cards": "5"}, {}, {}) == "5"
        assert _resolve_input(spec, {}, {}, {}, {}) == "3"

    def test_builder_source(self):
        builders = {"existing_ideas": lambda: "[new] test idea (X Thread)"}
        spec = {"source": "dynamic", "builder": "existing_ideas"}
        assert _resolve_input(spec, {}, {}, builders, {}) == "[new] test idea (X Thread)"

    def test_template(self):
        spec = {"source": "dynamic", "template": "Operator seed: {seed}"}
        assert _resolve_input(spec, {}, {"seed": "my idea"}, {}, {}) == "Operator seed: my idea"


class TestComposeAndRun:
    """T2.12: compose_and_run assembles and calls the LLM."""

    def test_compose_and_run_basic(self, tmp_config, tmp_path):
        """compose_and_run assembles variables and calls the adapter."""
        from unittest.mock import patch, MagicMock

        # Create prompts dir with the test prompt
        prompts_dir = str(tmp_path / "prompts" / "test")
        os.makedirs(prompts_dir)
        with open(os.path.join(prompts_dir, "prompt_v1.md"), "w") as f:
            f.write("<!-- version: 1.0 -->\n# Test\n{business_name}\n{subjects}\n{origin_type}\n{num_cards}\n{existing_ideas}\n")

        # Create modules dir
        modules_dir = str(tmp_path / "modules")
        os.makedirs(modules_dir)

        business_config = {"business": {"name": "TestBrand"}, "subjects": ["AI"]}

        # Mock the adapter
        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = {"cards": []}

        # Mock context_assembly.assemble_module_context
        with patch("context_assembly.assemble_module_context") as mock_assemble:
            mock_assemble.return_value = ({"visual_style": "cream editorial"}, "modules:v1")

            inline_schemas = {"test_schema": {"type": "object", "required": [], "properties": {}}}
            builders = {"existing_ideas": lambda: "(no existing ideas)"}

            result, prov = compose_and_run(
                "test_process",
                "testbrand",
                {"origin_type": "operator_seed"},
                {"models": {}},
                db_path=str(tmp_path / "test.db"),
                config_dir=tmp_config,
                modules_dir=modules_dir,
                prompts_dir=str(tmp_path / "prompts"),
                builders=builders,
                inline_schemas=inline_schemas,
                business_config=business_config,
                adapter=mock_adapter,
            )

        # Verify the adapter was called with assembled variables
        mock_adapter.complete.assert_called_once()
        call_kwargs = mock_adapter.complete.call_args
        variables = call_kwargs.kwargs.get("variables") or call_kwargs[1].get("variables")

        assert variables["business_name"] == "TestBrand"
        assert variables["subjects"] == "AI"
        assert variables["origin_type"] == "operator_seed"
        assert variables["visual_style"] == "cream editorial"
        assert variables["num_cards"] == "3"
        assert variables["existing_ideas"] == "(no existing ideas)"

    def test_unknown_process_raises(self, tmp_config, tmp_path):
        """Unknown process name raises ProcessError."""
        with pytest.raises(ProcessError, match="not found"):
            compose_and_run(
                "nonexistent_process",
                "test",
                {},
                {},
                config_dir=tmp_config,
            )

    def test_production_processes_yaml_loads(self):
        """The production config/processes.yaml loads and validates."""
        reg = load_process_registry("config")
        assert "ideas_generate" in reg["processes"]
        assert "draft_generate" in reg["processes"]
        assert "fan_out_adapt" in reg["processes"]
        assert "native_structure" in reg["processes"]

        # Verify required fields
        for name, proc in reg["processes"].items():
            assert "prompt_file" in proc, f"Process {name} missing prompt_file"
            assert "backend" in proc, f"Process {name} missing backend"
            assert "inputs" in proc, f"Process {name} missing inputs"

    def test_production_processes_no_magic_truncation_slices(self):
        """T2.12 AC: magic truncation slices gone from process specs.
        Truncation is now declared in processes.yaml via transforms, not hardcoded in routes."""
        reg = load_process_registry("config")
        # fan_out_adapt is retired (AMENDMENT-009); check draft_generate instead
        # which has truncation transforms on capture_material
        draft = reg["processes"]["draft_generate"]
        capture_spec = draft["inputs"]["capture_material"]
        assert "transform" in capture_spec
        assert "truncate" in capture_spec["transform"]