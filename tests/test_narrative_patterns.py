"""Tests for config-driven narrative patterns and flexible story framework schema."""
import json
import pytest


def test_story_frameworks_schema_accepts_flexible_beats():
    """Schema must accept structure_name + beats instead of hardcoded 4 fields."""
    from module_store import STORY_FRAMEWORKS_SCHEMA
    from llm_adapter import validate_llm_output

    framework = {
        "subject_type": "AI",
        "structure_name": "myth_buster",
        "beats": [
            {"name": "myth", "content": "AI will replace Caribbean jobs"},
            {"name": "reality", "content": "AI will replace businesses that don't adopt"},
            {"name": "proof", "content": "Evidence from..."},
            {"name": "takeaway", "content": "Start integrating AI today"},
        ],
        "grounded_in_example": "GaryVee content",
        "grounded_in_story": "Operator's AI adoption story",
        "voice_compatible": True,
        "voice_note": "",
    }
    result = validate_llm_output(json.dumps({"frameworks": [framework], "summary": "test"}), STORY_FRAMEWORKS_SCHEMA, context="test")
    assert result["frameworks"][0]["structure_name"] == "myth_buster"


def test_story_frameworks_markdown_renders_flexible_beats():
    from module_store import story_frameworks_to_markdown

    data = {
        "frameworks": [
            {
                "subject_type": "AI",
                "structure_name": "myth_buster",
                "beats": [
                    {"name": "myth", "content": "AI replaces jobs"},
                    {"name": "reality", "content": "AI replaces businesses that don't adopt"},
                    {"name": "proof", "content": "Evidence here"},
                    {"name": "takeaway", "content": "Adopt AI now"},
                ],
                "grounded_in_example": "GaryVee",
                "grounded_in_story": "My AI story",
                "voice_compatible": True,
                "voice_note": "",
            }
        ],
        "summary": "Test summary",
    }
    md = story_frameworks_to_markdown(data, "1.0")
    assert "### AI" in md
    assert "**Structure:** myth_buster" in md
    assert "AI replaces jobs" in md
    assert "AI replaces businesses" in md
    # Old hardcoded labels should NOT appear
    assert "Entry point:" not in md
    assert "Tension:" not in md


def test_story_frameworks_schema_allows_multiple_structures():
    """Multiple frameworks in one output can have different structure_names."""
    from module_store import STORY_FRAMEWORKS_SCHEMA
    from llm_adapter import validate_llm_output

    data = {
        "frameworks": [
            {
                "subject_type": "AI",
                "structure_name": "myth_buster",
                "beats": [
                    {"name": "myth", "content": "x"},
                    {"name": "reality", "content": "y"},
                    {"name": "proof", "content": "z"},
                    {"name": "takeaway", "content": "w"},
                ],
                "grounded_in_example": "",
                "grounded_in_story": "",
                "voice_compatible": True,
                "voice_note": "",
            },
            {
                "subject_type": "wealth",
                "structure_name": "how_to",
                "beats": [
                    {"name": "problem", "content": "x"},
                    {"name": "steps", "content": "y"},
                    {"name": "result", "content": "z"},
                ],
                "grounded_in_example": "",
                "grounded_in_story": "",
                "voice_compatible": True,
                "voice_note": "",
            },
        ],
        "summary": "test",
    }
    result = validate_llm_output(json.dumps(data), STORY_FRAMEWORKS_SCHEMA, context="test")
    assert len(result["frameworks"]) == 2


def test_narrative_patterns_config_loads():
    """The narrative patterns config file should load with expected structure."""
    import yaml
    import os

    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "narrative_patterns.yaml")
    with open(config_path) as f:
        data = yaml.safe_load(f)

    assert "patterns" in data
    assert len(data["patterns"]) >= 8
    assert data.get("allow_custom") is True

    # Each pattern should have name, description, beats
    for p in data["patterns"]:
        assert "name" in p
        assert "description" in p
        assert "beats" in p
        assert isinstance(p["beats"], list)
        assert len(p["beats"]) >= 2