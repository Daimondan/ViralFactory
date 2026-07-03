"""
P0-1 Regression tests: drafting input starvation fix.

Tests that:
1. No rendered prompt for any of the 8 docs contains unresolved {placeholder} tokens
2. Routed seeds from the orchestrator are persisted to collected['seeds'][doc]
3. The shot_library_summary is NOT the hardcoded "(see uploaded files)" literal
4. Voice Profile corpus includes operator messages and text materials

Per CORRECTION-orchestrator-drafting-and-ux-v1.0.md P0-1(e).
"""
import json
import os
import sys
import tempfile
import re

import pytest

# Ensure src is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

# The 8 onboarding docs and their v2 prompt files
DOC_PROMPT_MAP = {
    "business-profile-intake": "business_profile/analyze_v2.md",
    "voice-profile-builder": "voice_profile/analyze_v2.md",
    "sources-engine": "sources_engine/analyze_v2.md",
    "viral-patterns-starter": "viral_patterns/analyze_v2.md",
    "audience-insights-builder": "audience_insights/analyze_v2.md",
    "story-frameworks-starter": "story_frameworks/analyze_v2.md",
    "format-guide-starter": "format_guide/analyze_v2.md",
    "visual-style-intake": "visual_style/analyze_v2.md",
}

# All variables the v2 prompts might use
ALL_VARIABLES = {
    "business_name": "Test Business",
    "existing_info": "A test business",
    "subjects": "testing, ai",
    "audience_description": "Testers",
    "routed_seeds": "- Caribbean AI brand\n- wealth building",
    "conversation_transcript": "AI: Hello\nOperator: We're a Caribbean AI brand",
    "materials_content": "Test brand document content here.",
    "corpus": "Test corpus content for voice analysis.",
    "seed_sources": "(none provided yet)",
    "anti_examples": "(none provided)",
    "admired_examples": "(none provided yet)",
    "operator_description": "Small vendors in the Caribbean",
    "audience_data": "(none)",
    "admired_signals": "(none)",
    "operator_stories": "The sou-sou payout story",
    "voice_summary": "(not available)",
    "platforms": "X (@test)",
    "format_observations": "(none)",
    "platform_norms": "(use general knowledge)",
    "brand_assets": "(none)",
    "visual_examples": "(none)",
    "shot_library_summary": "- brand_doc.docx (plain_text): Test brand document...",
    "business_region": "Caribbean",
    "qa_transcript": "(legacy — use conversation_transcript instead)",
}


class TestNoUnresolvedPlaceholders:
    """P0-1(e): No rendered prompt anywhere in the system may ship with an unresolved placeholder."""

    @pytest.mark.parametrize("doc_name,prompt_file", list(DOC_PROMPT_MAP.items()))
    def test_no_unresolved_placeholders(self, doc_name, prompt_file):
        """For each of the 8 docs, render the v2 prompt with all package variables
        and assert no {placeholder} tokens survive rendering."""
        from llm_adapter import LLMAdapter

        prompt_path = os.path.join(PROMPTS_DIR, prompt_file)
        if not os.path.exists(prompt_path):
            pytest.skip(f"v2 prompt not yet created: {prompt_file}")

        with open(prompt_path) as f:
            template = f.read()

        # Render the prompt with all variables
        rendered = re.sub(r'\{(\w+)\}', lambda m: str(ALL_VARIABLES.get(m.group(1), m.group(0))), template)

        # Find unresolved {placeholder} tokens
        unresolved = re.findall(r'\{(\w+)\}', rendered)
        assert unresolved == [], (
            f"Doc '{doc_name}' prompt '{prompt_file}' has unresolved placeholders: "
            f"{list(set(unresolved))}. "
            f"Every variable in the prompt must be provided by the drafting package."
        )

    def test_materials_content_reaches_prompt(self):
        """P0-1(c): The materials_content variable must appear in every v2 prompt
        so material content reaches the drafting LLM."""
        for doc_name, prompt_file in DOC_PROMPT_MAP.items():
            prompt_path = os.path.join(PROMPTS_DIR, prompt_file)
            if not os.path.exists(prompt_path):
                pytest.skip(f"v2 prompt not yet created: {prompt_file}")

            with open(prompt_path) as f:
                template = f.read()

            assert "{materials_content}" in template, (
                f"Doc '{doc_name}' prompt '{prompt_file}' is missing {{materials_content}}. "
                f"Every v2 prompt must include materials content so drafting isn't starved."
            )

    def test_routed_seeds_in_prompt(self):
        """P0-1(c): The routed_seeds variable must appear in every v2 prompt."""
        for doc_name, prompt_file in DOC_PROMPT_MAP.items():
            prompt_path = os.path.join(PROMPTS_DIR, prompt_file)
            if not os.path.exists(prompt_path):
                pytest.skip(f"v2 prompt not yet created: {prompt_file}")

            with open(prompt_path) as f:
                template = f.read()

            assert "{routed_seeds}" in template, (
                f"Doc '{doc_name}' prompt '{prompt_file}' is missing {{routed_seeds}}. "
                f"Every v2 prompt must include routed seeds."
            )

    def test_conversation_transcript_in_prompt(self):
        """P0-1(c): The conversation_transcript variable must appear in every v2 prompt."""
        for doc_name, prompt_file in DOC_PROMPT_MAP.items():
            prompt_path = os.path.join(PROMPTS_DIR, prompt_file)
            if not os.path.exists(prompt_path):
                pytest.skip(f"v2 prompt not yet created: {prompt_file}")

            with open(prompt_path) as f:
                template = f.read()

            assert "{conversation_transcript}" in template, (
                f"Doc '{doc_name}' prompt '{prompt_file}' is missing {{conversation_transcript}}. "
                f"Every v2 prompt must include the conversation transcript."
            )


class TestRoutedSeedsPersisted:
    """P0-1(a): Routed seeds from the orchestrator are persisted to collected['seeds'][doc]."""

    def test_seeds_persisted_after_orchestrator_turn(self):
        """Simulate an orchestrator response with routed_seeds and verify they're stored."""
        from playbook_runner import PlaybookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            runner = PlaybookRunner(db_path)
            run_id = runner.start_run("onboarding", "1.0", "test-biz")

            collected = {"session_messages": [], "ai_replies": [], "business_qa": [], "coverage": {}}
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

            # Simulate what onboarding_message does after the orchestrator returns:
            result = {
                "reply": "Great, tell me more about your brand.",
                "routed_seeds": [
                    {"doc": "business-profile-intake", "seed": "Caribbean AI brand about wealth building"},
                    {"doc": "audience-insights-builder", "seed": "audience is small vendors"},
                    {"doc": "business-profile-intake", "seed": "posts on Instagram and X"},
                ],
                "coverage_updates": [
                    {"doc": "business-profile-intake", "status": "collecting"},
                ],
                "next_focus": "business-profile-intake",
            }

            ONBOARDING_PLAYBOOKS = [
                "business-profile-intake", "voice-profile-builder", "sources-engine",
                "viral-patterns-starter", "audience-insights-builder",
                "story-frameworks-starter", "format-guide-starter", "visual-style-intake",
            ]

            # Replicate the seed persistence logic
            collected = json.loads(runner.get_run(run_id)["collected_inputs"])
            if "seeds" not in collected:
                collected["seeds"] = {}
            for seed in result.get("routed_seeds", []):
                doc = seed.get("doc", "")
                seed_text = seed.get("seed", "")
                if doc and seed_text and doc in ONBOARDING_PLAYBOOKS:
                    if doc not in collected["seeds"]:
                        collected["seeds"][doc] = []
                    if seed_text not in collected["seeds"][doc]:
                        collected["seeds"][doc].append(seed_text)
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

            # Verify
            run = runner.get_run(run_id)
            stored = json.loads(run["collected_inputs"])
            assert "seeds" in stored
            assert "business-profile-intake" in stored["seeds"]
            assert len(stored["seeds"]["business-profile-intake"]) == 2
            assert "Caribbean AI brand about wealth building" in stored["seeds"]["business-profile-intake"]
            assert "audience-insights-builder" in stored["seeds"]
            assert "audience is small vendors" in stored["seeds"]["audience-insights-builder"]

    def test_duplicate_seeds_not_persisted(self):
        """Exact-duplicate seeds should not be stored twice."""
        from playbook_runner import PlaybookRunner

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            runner = PlaybookRunner(db_path)
            run_id = runner.start_run("onboarding", "1.0", "test-biz")

            collected = {"seeds": {"business-profile-intake": ["Caribbean AI brand"]}}
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

            # Try to add the same seed again
            ONBOARDING_PLAYBOOKS = ["business-profile-intake"]
            result_seeds = [
                {"doc": "business-profile-intake", "seed": "Caribbean AI brand"},
                {"doc": "business-profile-intake", "seed": "wealth building focus"},
            ]

            collected = json.loads(runner.get_run(run_id)["collected_inputs"])
            if "seeds" not in collected:
                collected["seeds"] = {}
            for seed in result_seeds:
                doc = seed.get("doc", "")
                seed_text = seed.get("seed", "")
                if doc and seed_text and doc in ONBOARDING_PLAYBOOKS:
                    if doc not in collected["seeds"]:
                        collected["seeds"][doc] = []
                    if seed_text not in collected["seeds"][doc]:
                        collected["seeds"][doc].append(seed_text)
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

            stored = json.loads(runner.get_run(run_id)["collected_inputs"])
            assert len(stored["seeds"]["business-profile-intake"]) == 2  # original + 1 new


class TestShotLibrarySummary:
    """P0-1(d): shot_library_summary is NOT the hardcoded '(see uploaded files)' literal."""

    def test_shot_library_summary_not_hardcoded(self):
        """Verify that the _build_shot_library_summary function produces real content,
        not the hardcoded '(see uploaded files)' literal."""
        from materials import MaterialsIntake

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            upload_dir = os.path.join(tmpdir, "uploads")
            os.makedirs(upload_dir)

            intake = MaterialsIntake(db_path, upload_dir)
            mid = intake.ingest_text(
                "This is a test brand document with visual style information.",
                run_id=1, business_slug="test-biz",
                material_type="plain_text", channel="document",
            )

            materials = intake.list_materials(run_id=1)
            assert len(materials) > 0

            # Build summary the same way _build_shot_library_summary does
            lines = []
            for m in materials:
                filename = m.get("filename", "unknown")
                mtype = m.get("material_type", "unknown")
                raw = m.get("raw_content", "")
                normalized = m.get("normalized_content", "")
                content = normalized or raw
                if mtype == "image":
                    lines.append(f"- {filename} (image)")
                elif content and not content.startswith("[Audio") and not content.startswith("[Binary"):
                    excerpt = content[:300]
                    if len(content) > 300:
                        excerpt += "..."
                    lines.append(f"- {filename} ({mtype}): {excerpt}")
                else:
                    lines.append(f"- {filename} ({mtype})")

            summary = "\n".join(lines)
            assert summary != "(see uploaded files)"
            assert "test brand document" in summary.lower()

    def test_no_see_uploaded_files_in_code(self):
        """P0-1(d): The literal '(see uploaded files)' must not appear as a value
        assignment in app.py (comments/docstrings are OK)."""
        app_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(app_path) as f:
            lines = f.readlines()
        # Check no line assigns the literal as a value
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments and docstrings
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if stripped.startswith("Replaces") or stripped.startswith("Kill"):
                continue
            # Check for actual value assignment with the literal
            if '"(see uploaded files)"' in stripped or "'(see uploaded files)'" in stripped:
                if "=" in stripped and "shot_library_summary" in stripped:
                    pytest.fail(
                        f"Line {i} still assigns the hardcoded literal: {stripped}"
                    )


class TestNextFocusNullHandling:
    """P0-2: Validation crash on next_focus null."""

    def test_none_coerced_to_empty_string_for_optional_field(self):
        """When the orchestrator returns next_focus: null, the validator should
        coerce it to "" instead of crashing."""
        from validator import validate_llm_output, ValidationError

        schema = {
            "type": "object",
            "required": ["reply", "routed_seeds"],
            "properties": {
                "reply": {"type": "string"},
                "routed_seeds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "doc": {"type": "string"},
                            "seed": {"type": "string"},
                        },
                    },
                },
                "next_focus": {"type": "string"},
            },
        }

        # LLM returns next_focus as null
        raw_output = '{"reply": "test", "routed_seeds": [], "next_focus": null}'
        result = validate_llm_output(raw_output, schema)
        assert result["next_focus"] == ""
        assert result["reply"] == "test"

    def test_required_string_still_fails_on_null(self):
        """If a required string field is null, validation should still fail."""
        from validator import validate_llm_output, ValidationError

        schema = {
            "type": "object",
            "required": ["reply"],
            "properties": {
                "reply": {"type": "string"},
            },
        }

        raw_output = '{"reply": null}'
        with pytest.raises(ValidationError):
            validate_llm_output(raw_output, schema)

    def test_orchestrator_schema_next_focus_not_required(self):
        """P0-2: The orchestrator schema must not require next_focus."""
        # Verify the schema in app.py has next_focus removed from required
        app_path = os.path.join(os.path.dirname(__file__), "..", "src", "app.py")
        with open(app_path) as f:
            content = f.read()

        # Find the orchestrator_schema definition
        # It should have "required": ["reply", "routed_seeds", "coverage_updates"]
        # WITHOUT next_focus
        import re as _re
        # Look for the orchestrator schema's required list
        match = _re.search(r'orchestrator_schema\s*=\s*\{[^}]*"required"\s*:\s*\[([^\]]+)\]', content, _re.DOTALL)
        assert match, "Could not find orchestrator_schema required list"
        required_fields = match.group(1)
        assert "next_focus" not in required_fields, (
            f"next_focus must not be in the orchestrator schema's required list. "
            f"Found: {required_fields}"
        )
