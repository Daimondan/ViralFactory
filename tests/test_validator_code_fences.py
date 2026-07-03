"""
Test: validator strips markdown code fences from LLM JSON output.

Real-world bug: GLM-5.2 wraps JSON in ```json ... ``` fences.
json.loads() chokes on the leading ``` — both initial attempt and retry
fail identically, surfacing as "LLM output is not valid JSON: Expecting
value: line 1 column 1 (char 0)".
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validator import validate_llm_output, _strip_code_fences, ValidationError


class TestStripCodeFences:
    def test_strips_json_fence(self):
        raw = '```json\n{"key": "value"}\n```'
        assert _strip_code_fences(raw) == '{"key": "value"}'

    def test_strips_plain_fence(self):
        raw = '```\n{"key": "value"}\n```'
        assert _strip_code_fences(raw) == '{"key": "value"}'

    def test_strips_js_fence(self):
        raw = '```javascript\n{"key": "value"}\n```'
        assert _strip_code_fences(raw) == '{"key": "value"}'

    def test_no_fence_unchanged(self):
        raw = '{"key": "value"}'
        assert _strip_code_fences(raw) == '{"key": "value"}'

    def test_strips_fence_with_multiline_json(self):
        raw = '```json\n{\n  "reply": "hello",\n  "ready_to_draft": false\n}\n```'
        result = _strip_code_fences(raw)
        assert json.loads(result) == {"reply": "hello", "ready_to_draft": False}

    def test_real_provenance_output_from_run_24(self):
        """Exact raw output from provenance #5 that caused the P0 error."""
        raw = (
            '```json\n'
            '{\n'
            '  "reply": "Hey! So I\'m putting together your Voice Profile",\n'
            '  "ready_to_draft": false\n'
            '}\n'
            '```'
        )
        result = _strip_code_fences(raw)
        parsed = json.loads(result)
        assert parsed["ready_to_draft"] is False
        assert "Voice Profile" in parsed["reply"]


class TestValidateOutputWithFences:
    """validate_output must accept JSON wrapped in code fences."""

    def test_validate_output_strips_fence_before_parsing(self):
        schema = {
            "type": "object",
            "required": ["reply", "ready_to_draft"],
            "properties": {
                "reply": {"type": "string"},
                "ready_to_draft": {"type": "boolean"},
            },
        }
        raw = (
            '```json\n'
            '{"reply": "test reply", "ready_to_draft": false}\n'
            '```'
        )
        result = validate_llm_output(raw, schema, context="test")
        assert result["reply"] == "test reply"
        assert result["ready_to_draft"] is False

    def test_validate_output_still_rejects_garbage(self):
        schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
        with pytest.raises(ValidationError, match="not valid JSON"):
            validate_llm_output("this is not json at all", schema, context="test")

    def test_validate_output_still_rejects_invalid_json_in_fence(self):
        schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
        with pytest.raises(ValidationError, match="not valid JSON"):
            validate_llm_output('```json\n{not valid json}\n```', schema, context="test")
