"""Regression tests for affordance-based format selection.

The Format Guide describes media affordances; it does not route message-taxonomy
categories to formats. Idea treatments choose one primary destination and record
whether that destination was requested by the user or selected by the LLM.
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from context_assembly import assemble_module_context
from module_store import FORMAT_GUIDE_SCHEMA, format_guide_to_markdown
from pipeline import IDEA_CARD_SCHEMA, IDEA_CONCEPT_SCHEMA
from validator import validate_llm_output


def descriptive_format_guide():
    return {
        "formats": [
            {
                "format_name": "Instagram Reel",
                "platforms": ["Instagram"],
                "variant_type": "reel",
                "audience_experience": "A short audiovisual piece consumed in a vertical feed.",
                "native_mechanics": ["vertical video", "spoken or natural audio", "text overlays"],
                "expressive_strengths": ["human presence", "visual demonstration", "emotional delivery"],
                "limitations": ["dense arguments can feel rushed", "weak visuals become text read aloud"],
                "production_demands": ["clear audio", "purposeful motion or visual contrast"],
                "length": "15-90 seconds",
                "structure_notes": "Open quickly, develop one coherent idea, and close without padding.",
                "skeleton": "Hook → development → landing",
                "requires_human_capture": "optional",
                "capture_tasks": [],
                "effort_level": "high",
                "reuse_pathways": ["A strong line may later become a separate text post"],
                "status": "proven",
                "performance_evidence": {
                    "source": "platform_prior",
                    "notes": "Voice and motion can improve personality-led delivery; tenant evidence pending.",
                    "last_updated": "2026-07-11",
                },
                "aspect_ratio": "9:16",
                "provenance": "Platform prior; awaiting tenant performance data",
            }
        ],
        "summary": "Formats are described by what their medium enables, not assigned to message categories.",
    }


def test_format_guide_accepts_descriptive_profiles_without_decision_table():
    guide = descriptive_format_guide()
    result = validate_llm_output(json.dumps(guide), FORMAT_GUIDE_SCHEMA, context="test")
    assert result["formats"][0]["expressive_strengths"][0] == "human presence"
    assert "decision_table" not in result


def test_format_guide_markdown_has_selection_profiles_without_routing_table():
    markdown = format_guide_to_markdown(descriptive_format_guide(), "2.0")
    assert "## Selection profiles" in markdown
    assert "Expressive strengths" in markdown
    assert "Limitations" in markdown
    assert "Performance evidence" in markdown
    assert "## Decision table" not in markdown
    assert "Best for" not in markdown


def test_ideas_context_receives_descriptive_selection_profiles(tmp_path):
    modules_dir = tmp_path / "modules"
    business_dir = modules_dir / "testbiz"
    business_dir.mkdir(parents=True)
    (business_dir / "format-guide.md").write_text(
        format_guide_to_markdown(descriptive_format_guide(), "2.0")
    )

    variables, provenance = assemble_module_context(
        "ideas/generate_v1.md",
        "testbiz",
        modules_dir=str(modules_dir),
        prompts_dir=str(REPO_ROOT / "prompts"),
        view_map={
            "ideas/generate_v1.md": {
                "format_guide": {
                    "module": "format-guide",
                    "mode": "section",
                    "heading": "Selection profiles",
                    "budget": 6000,
                }
            }
        },
    )

    assert "human presence" in variables["format_guide"]
    assert "dense arguments can feel rushed" in variables["format_guide"]
    assert "Skeleton" not in variables["format_guide"]
    assert "section" in provenance


def test_concept_schema_is_format_neutral():
    concept_properties = IDEA_CONCEPT_SCHEMA["properties"]["cards"]["items"]["properties"]
    assert "concept_basis" in concept_properties
    assert "treatment" not in concept_properties


def test_idea_treatment_schema_requires_one_primary_destination_and_decision_source():
    format_schema = (
        IDEA_CARD_SCHEMA["properties"]["cards"]["items"]["properties"]
        ["treatment"]["properties"]["format"]
    )
    assert {
        "primary_platform",
        "format_name",
        "constraint_source",
        "selection_reason",
    }.issubset(set(format_schema["required"]))
    assert format_schema["properties"]["constraint_source"]["enum"] == [
        "user_request",
        "llm_selected",
    ]


def test_idea_prompt_exposes_distribution_intent_and_primary_destination_rules():
    prompt = (REPO_ROOT / "prompts" / "ideas" / "generate_v1.md").read_text()
    assert "{distribution_intent}" in prompt
    assert "one primary platform" in prompt.lower()
    assert "exact_format" in prompt
    assert "no obligation" in prompt.lower() and "both" in prompt.lower()
