"""VF-FMT-1604: Format Guide production-binding contract and gate surface."""

import json
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_store import (
    FORMAT_GUIDE_SCHEMA,
    ModuleStore,
    format_guide_proposal_diff,
    format_guide_to_markdown,
    parse_format_guide_markdown,
    generate_gate_token,
)
from playbook_runner import PlaybookRunner
from validator import ValidationError, validate_llm_output


def _format_guide(production_binding=None):
    entry = {
        "format_name": "Test Reel",
        "platforms": ["Instagram"],
        "variant_type": "reel",
        "audience_experience": "A short audiovisual experience.",
        "native_mechanics": ["vertical motion"],
        "expressive_strengths": ["shows a scene"],
        "limitations": ["requires pacing"],
        "production_demands": ["visual plan"],
        "length": "15-30 seconds",
        "structure_notes": "Hook then payoff",
        "skeleton": "1. Hook\n2. Payoff",
        "requires_human_capture": "none",
        "capture_tasks": [],
        "effort_level": "medium",
        "reuse_pathways": [],
        "status": "proven",
        "performance_evidence": {
            "source": "platform_prior",
            "notes": "fixture",
            "last_updated": "2026-07-30",
        },
        "aspect_ratio": "9:16",
        "provenance": "fixture",
    }
    if production_binding is not None:
        entry["production_binding"] = production_binding
    return {"formats": [entry], "summary": "fixture guide"}


def _approved_store(tmp_path):
    db_path = str(tmp_path / "vf.db")
    modules_dir = str(tmp_path / "modules")
    store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
    runner = PlaybookRunner(db_path)
    run_id = runner.start_run("format-guide-starter", "1.0", "testbrand")
    runner.set_gate_result(run_id, "3", "approve", "fixture")
    return store, run_id, generate_gate_token(run_id)


def test_schema_accepts_optional_standard_production_binding():
    binding = {"mode": "standard"}
    result = validate_llm_output(
        json.dumps(_format_guide(binding)), FORMAT_GUIDE_SCHEMA, context="test"
    )
    assert result["formats"][0]["production_binding"] == binding


def test_schema_rejects_invalid_production_binding_mode():
    with pytest.raises(ValidationError, match="mode"):
        validate_llm_output(
            json.dumps(_format_guide({"mode": "not-a-production-mode"})),
            FORMAT_GUIDE_SCHEMA,
            context="test",
        )


def test_missing_binding_is_not_inferred_as_episode():
    guide = validate_llm_output(json.dumps(_format_guide()), FORMAT_GUIDE_SCHEMA)
    assert "production_binding" not in guide["formats"][0]


def test_production_binding_survives_markdown_round_trip():
    binding = {
        "mode": "episode",
        "process_ref": "episode-format",
        "governance_module_ref": "episode-format-parable",
        "governance_module_version": "1.0",
    }
    guide = _format_guide(binding)
    markdown = format_guide_to_markdown(guide, "3.0")
    parsed = parse_format_guide_markdown(markdown)
    assert parsed == guide


def test_proposal_diff_identifies_exact_binding_change():
    current = _format_guide({"mode": "standard"})
    proposed = _format_guide(
        {
            "mode": "episode",
            "process_ref": "episode-format",
            "governance_module_ref": "episode-format-parable",
            "governance_module_version": "1.0",
        }
    )
    diff = format_guide_proposal_diff(current, proposed)
    assert "production_binding" in diff
    assert '"standard"' in diff
    assert '"episode"' in diff
    assert "episode-format-parable" in diff


def test_archived_format_guide_history_keeps_structured_binding(tmp_path):
    store, run_id, token = _approved_store(tmp_path)
    first = _format_guide({"mode": "standard"})
    second = _format_guide(
        {
            "mode": "episode",
            "process_ref": "episode-format",
            "governance_module_ref": "episode-format-parable",
            "governance_module_version": "1.0",
        }
    )
    store.store(
        "testbrand",
        "format-guide",
        format_guide_to_markdown(first, "1.0"),
        version="1.0",
        gate_token=token,
        run_id=run_id,
        structured_data=first,
    )
    store.store(
        "testbrand",
        "format-guide",
        format_guide_to_markdown(second, "2.0"),
        version="2.0",
        gate_token=token,
        run_id=run_id,
        structured_data=second,
    )
    history = store.list_versions("testbrand", "format-guide")
    archived = next(item for item in history if item["version"] == "1.0")
    assert archived["structured_filename"]
    archived_path = tmp_path / "modules" / "testbrand" / "versions" / "format-guide" / archived["structured_filename"]
    assert json.loads(archived_path.read_text()) == first
    assert store.load_json("testbrand", "format-guide") == second


def test_format_guide_gate_surface_displays_binding_and_diff(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "business.yaml").write_text(
        yaml.safe_dump(
            {
                "business": {"name": "TestBrand", "slug": "testbrand"},
                "subjects": ["test"],
                "platforms": [{"name": "Instagram", "handle": "@test"}],
            }
        )
    )
    (config_dir / "models.yaml").write_text(
        yaml.safe_dump(
            {
                "active": {"default": "test"},
                "test": {"provider": "test", "model": "test", "temperature": 0},
            }
        )
    )
    (config_dir / "sources.yaml").write_text(yaml.safe_dump({"feeds": [], "channels": [], "queries": []}))

    from app import create_app

    db_path = str(tmp_path / "app.db")
    app = create_app(
        config_dir=str(config_dir),
        db_path=db_path,
        playbooks_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks")),
    )
    runner = PlaybookRunner(db_path)
    run_id = runner.start_run("format-guide-starter", "1.0", "testbrand")
    guide = _format_guide(
        {
            "mode": "episode",
            "process_ref": "episode-format",
            "governance_module_ref": "episode-format-parable",
            "governance_module_version": "1.0",
        }
    )
    runner.add_llm_output(run_id, "guide", guide)

    response = app.test_client().get(f"/onboard/format-guide-starter/{run_id}/format-guide")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Production binding" in body
    assert "episode-format-parable" in body
    assert "Proposal diff" in body
