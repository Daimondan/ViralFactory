"""
ViralFactory — T1.5 Interview Fallback Tests

Tests for:
- Interview question schema validation
- Interview page loads
- Interview produces corpus from answers alone (simulated end-to-end)
"""

import os
import json
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from validator import validate_json_schema, validate_llm_output, ValidationError


INTERVIEW_SCHEMA = {
    "type": "object",
    "required": ["question_number", "question"],
    "properties": {
        "question_number": {"type": "integer", "minimum": 1},
        "question": {"type": "string"},
        "prompt_hint": {"type": "string"},
    },
}


class TestInterviewSchema:

    def test_valid_question_accepted(self):
        """Valid interview question passes validation."""
        q = {"question_number": 1, "question": "Tell me about a money lesson.", "prompt_hint": "Personal story"}
        result = validate_json_schema(q, INTERVIEW_SCHEMA)
        assert result["question_number"] == 1

    def test_missing_question_rejected(self):
        """Missing question text is rejected."""
        with pytest.raises(ValidationError, match="question"):
            validate_json_schema({"question_number": 1}, INTERVIEW_SCHEMA)

    def test_question_number_must_be_integer(self):
        """Question number must be an integer, not a string."""
        with pytest.raises(ValidationError, match="question_number"):
            validate_json_schema({"question_number": "one", "question": "test"}, INTERVIEW_SCHEMA)

    def test_question_number_minimum(self):
        """Question number must be >= 1."""
        with pytest.raises(ValidationError, match=">= 1"):
            validate_json_schema({"question_number": 0, "question": "test"}, INTERVIEW_SCHEMA)

    def test_full_json_validation(self):
        """Full pipeline: raw JSON → validated."""
        raw = json.dumps({"question_number": 3, "question": "What's a story you tell often?", "prompt_hint": ""})
        result = validate_llm_output(raw, INTERVIEW_SCHEMA)
        assert result["question_number"] == 3


class TestInterviewPage:

    def test_interview_page_loads(self):
        """The interview fallback page loads."""
        from app import create_app
        db = "data/viralfactory_test.db"
        if os.path.exists(db):
            os.unlink(db)
        app = create_app(config_dir="config", db_path=db)
        client = app.test_client()

        resp = client.get("/onboard/voice-profile-builder/1/interview")
        assert resp.status_code == 200
        assert b"Voice Interview" in resp.data
        assert b"Answer a few questions" in resp.data

        if os.path.exists(db):
            os.unlink(db)


class TestInterviewProducesCorpus:

    def test_answers_become_corpus(self):
        """Simulated: interview answers stored as materials become a corpus."""
        from materials import MaterialsIntake
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        os.unlink(db_path)

        intake = MaterialsIntake(db_path=db_path)

        # Simulate 5 interview answers
        answers = [
            "Caribbean wealth isn't about individual bank accounts. It's about how we pool resources, sou-sou style.",
            "My grandmother used to say 'one hand can't clap' and she meant it literally. She showed me that community is the real asset.",
            "I started StackPenni because the receipts are in our culture. Not in some Wall Street spreadsheet.",
            "AI is a tool. It doesn't replace Caribbean ingenuity. It amplifies it — if we use it right.",
            "The biggest lie in personal finance is that wealth is a solo journey. Show me a wealthy person and I'll show you a village behind them.",
        ]

        run_id = 1
        for i, answer in enumerate(answers):
            intake.ingest_text(
                answer, run_id=run_id, business_slug="stackpenni",
                material_type="interview_answer", channel="interview",
                audience="system",
            )

        # Get the corpus
        corpus = intake.get_corpus(run_id)
        assert len(corpus["samples"]) == 5
        assert corpus["total_words"] >= 80  # 5 short answers

        # Verify the content is there
        materials = intake.list_materials(run_id=run_id)
        assert all(m["material_type"] == "interview_answer" for m in materials)

        if os.path.exists(db_path):
            os.unlink(db_path)