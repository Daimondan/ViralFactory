"""VF-FMT-1606: dynamic production binding resolution."""

import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_resolver import ProductionResolutionError, resolve_production_binding


BINDING = {
    "mode": "episode",
    "process_ref": "episode-format",
    "governance_module_ref": "episode-format-parable",
    "governance_module_version": "1.0",
}


def _fixture(tmp_path, *, process_status="approved", module_status=None, module_version="1.0"):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "processes.yaml").write_text(
        yaml.safe_dump(
            {
                "processes": {},
                "production_processes": {
                    "episode-format": {
                        "status": process_status,
                        "module_variable": "episode_format",
                        "budget": 8000,
                    }
                },
            }
        )
    )
    module_dir = tmp_path / "modules" / "tenant"
    module_dir.mkdir(parents=True)
    marker = f"<!-- status: {module_status} -->\n" if module_status else ""
    (module_dir / "episode-format-parable.md").write_text(
        marker + f"# Episode Format — v{module_version}\n\nSchema: episode_format_v1\n"
    )
    return config_dir, tmp_path / "modules"


def test_missing_binding_is_standard_without_module_lookup(tmp_path):
    result = resolve_production_binding(None, "tenant", str(tmp_path / "missing"), str(tmp_path / "missing-modules"))
    assert result["mode"] == "standard"
    assert result["module_content"] is None


def test_episode_binding_resolves_process_and_exact_module_version(tmp_path):
    config_dir, modules_dir = _fixture(tmp_path)
    result = resolve_production_binding(BINDING, "tenant", str(config_dir), str(modules_dir))
    assert result["mode"] == "episode"
    assert result["process_ref"] == "episode-format"
    assert result["governance_module_ref"] == "episode-format-parable"
    assert result["governance_module_version"] == "1.0"
    assert "Episode Format" in result["module_content"]
    assert result["module_variable"] == "episode_format"


@pytest.mark.parametrize(
    "kwargs,needle",
    [
        ({"process_status": "draft"}, "process"),
        ({"process_status": "proposed"}, "process"),
        ({"process_status": "rejected"}, "process"),
        ({"module_status": "draft"}, "module"),
        ({"module_status": "proposed"}, "module"),
        ({"module_status": "rejected"}, "module"),
        ({"module_version": "2.0"}, "version"),
    ],
)
def test_invalid_process_or_module_reference_fails_closed(tmp_path, kwargs, needle):
    config_dir, modules_dir = _fixture(tmp_path, **kwargs)
    with pytest.raises(ProductionResolutionError, match=needle):
        resolve_production_binding(BINDING, "tenant", str(config_dir), str(modules_dir))


def test_unknown_process_and_missing_module_fail_closed(tmp_path):
    config_dir, modules_dir = _fixture(tmp_path)
    unknown = dict(BINDING, process_ref="not-registered")
    with pytest.raises(ProductionResolutionError, match="process"):
        resolve_production_binding(unknown, "tenant", str(config_dir), str(modules_dir))

    missing = dict(BINDING, governance_module_ref="missing")
    with pytest.raises(ProductionResolutionError, match="module"):
        resolve_production_binding(missing, "tenant", str(config_dir), str(modules_dir))


def test_episode_binding_requires_complete_references(tmp_path):
    config_dir, modules_dir = _fixture(tmp_path)
    for field in ("process_ref", "governance_module_ref", "governance_module_version"):
        incomplete = dict(BINDING)
        incomplete.pop(field)
        with pytest.raises(ProductionResolutionError):
            resolve_production_binding(incomplete, "tenant", str(config_dir), str(modules_dir))


def test_active_views_do_not_hardcode_episode_module():
    views = open(os.path.join(os.path.dirname(__file__), "..", "prompts", "views.yaml"), encoding="utf-8").read()
    assert "episode-format-parable" not in views
