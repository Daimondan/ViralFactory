"""VF-VS-502 — Soundtrack planning prompt + process registry.

AC: no genre inference in code; no random effects; provenance logged.
"""

import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from pipeline import SOUNDTRACK_PLAN_LLM_SCHEMA  # noqa: E402
from soundtrack_plan import SOUNDTRACK_MODES  # noqa: E402
from process_engine import load_process_registry, _resolve_schema  # noqa: E402


def _prompt_path():
    return os.path.join(ROOT, "prompts", "assembly", "soundtrack_plan_v1.md")


# ── Prompt file ──────────────────────────────────────────────────────────────


def test_prompt_file_exists():
    assert os.path.exists(_prompt_path())


def test_prompt_has_version():
    content = open(_prompt_path()).read()
    assert "version:" in content
    assert "1.2" in content


def test_prompt_has_no_tenant_strings():
    content = open(_prompt_path()).read().lower()
    forbidden = ["stackpenni", "penni", "caribbean", "barbados", "fitzroy", "stackwell"]
    for w in forbidden:
        assert w not in content, f"Tenant string '{w}' in soundtrack prompt"


def test_prompt_has_no_provider_names():
    content = open(_prompt_path()).read().lower()
    forbidden = ["fal", "kling", "veo", "openai", "anthropic", "elevenlabs"]
    for w in forbidden:
        assert not re.search(r"\b" + re.escape(w) + r"\b", content), f"Provider '{w}' in prompt"


def test_prompt_states_assembler_side_boundary():
    content = open(_prompt_path()).read().lower()
    assert "assembler" in content
    assert "no audience copy" in content or "not audience" in content


def test_prompt_states_no_genre_inference():
    content = open(_prompt_path()).read().lower()
    assert "genre" in content
    assert "not infer" in content or "no genre inference" in content


def test_prompt_states_no_random_effects():
    content = open(_prompt_path()).read().lower()
    assert "random" in content
    assert "no random" in content or "not random" in content


def test_prompt_lists_four_modes():
    content = open(_prompt_path()).read()
    for mode in SOUNDTRACK_MODES:
        assert mode in content, f"Mode '{mode}' not documented in prompt"


def test_prompt_requires_licence_provenance():
    content = open(_prompt_path()).read().lower()
    assert "licence" in content or "license" in content
    assert "provenance" in content


def test_prompt_fails_closed_without_verified_music_candidates():
    content = open(_prompt_path()).read()
    assert "<!-- version: 1.2 -->" in content
    assert "If no verified music candidates are provided" in content
    assert '"envelope": []' in content


# ── Schema ───────────────────────────────────────────────────────────────────


def test_llm_schema_modes_match():
    modes = SOUNDTRACK_PLAN_LLM_SCHEMA["properties"]["mode"]["enum"]
    assert set(modes) == set(SOUNDTRACK_MODES)


def test_llm_schema_has_emotional_register():
    assert "emotional_register" in SOUNDTRACK_PLAN_LLM_SCHEMA["properties"]
    assert "emotional_register" in SOUNDTRACK_PLAN_LLM_SCHEMA["required"]


def test_llm_schema_requires_planner_authored_search_queries():
    queries = SOUNDTRACK_PLAN_LLM_SCHEMA["properties"]["search_queries"]
    assert "search_queries" in SOUNDTRACK_PLAN_LLM_SCHEMA["required"]
    assert queries["minItems"] == 1
    assert queries["maxItems"] == 6


def test_llm_schema_requires_complete_music_reference():
    music_ref = SOUNDTRACK_PLAN_LLM_SCHEMA["properties"]["music_bed_ref"]
    licence = music_ref["properties"]["licence"]

    assert set(music_ref["required"]) == {"source_id", "licence", "cost_usd"}
    assert set(licence["required"]) == {"type", "id", "url"}


# ── Process Registry ─────────────────────────────────────────────────────────


def test_soundtrack_plan_registered():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    assert "soundtrack_plan_v1" in registry["processes"]


def test_soundtrack_plan_registry_fields():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    proc = registry["processes"]["soundtrack_plan_v1"]
    assert proc["prompt_file"] == "assembly/soundtrack_plan_v1.md"
    assert proc["schema"] == "SOUNDTRACK_PLAN_LLM_SCHEMA"
    assert proc["backend"] == "default"


def test_soundtrack_plan_playbook_type_production():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    proc = registry["processes"]["soundtrack_plan_v1"]
    assert proc.get("playbook_type") == "production"


def test_soundtrack_plan_not_retired():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    proc = registry["processes"]["soundtrack_plan_v1"]
    assert not proc.get("retired", False)


def test_soundtrack_plan_schema_resolves():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    schema = _resolve_schema("SOUNDTRACK_PLAN_LLM_SCHEMA", registry)
    assert schema is SOUNDTRACK_PLAN_LLM_SCHEMA


def test_soundtrack_plan_inputs():
    registry = load_process_registry(config_dir=os.path.join(ROOT, "config"))
    inputs = registry["processes"]["soundtrack_plan_v1"]["inputs"]
    for key in ("content_contract", "vo_timeline", "audio_intents", "visual_style"):
        assert key in inputs


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))