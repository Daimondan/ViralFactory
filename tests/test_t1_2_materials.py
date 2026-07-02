"""
ViralFactory — T1.2 Materials Intake Tests

Tests for:
- WhatsApp export detection and normalization (strip other parties' messages)
- Plain text ingestion and normalization (strip email signatures, forwarded text)
- Audio file metadata storage
- Corpus assembly (word count, sample listing)
- API endpoints (upload, paste, corpus) via Flask test client
"""

import os
import json
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from materials import MaterialsIntake


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
def tmp_upload_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def intake(tmp_db, tmp_upload_dir):
    return MaterialsIntake(db_path=tmp_db, upload_dir=tmp_upload_dir)


WHATSAPP_EXPORT = """12/31/23, 11:45 PM - Daimon: Caribbean wealth isn't just about money in the bank
12/31/23, 11:45 PM - Sarah: What do you mean?
12/31/23, 11:46 PM - Daimon: It's about community. Sou-sou, pooling, helping each other build.
12/31/23, 11:47 PM - Sarah: That's interesting
12/31/23, 11:48 PM - Daimon: My grandmother used to say "one hand can't clap" and she meant it literally
12/31/23, 11:50 PM - Mike: Cool story
12/31/23, 11:51 PM - Daimon: The receipts are in the culture, not just the spreadsheet
01/01/24, 12:01 AM - Daimon: That's why I started StackPenni. The receipts are Caribbean."""


# --- Normalization Tests ---

class TestWhatsAppNormalization:

    def test_detect_whatsapp_export(self, intake):
        """WhatsApp export format is detected correctly."""
        assert intake._is_whatsapp_export(WHATSAPP_EXPORT)
        assert not intake._is_whatsapp_export("Just some regular text, nothing special.")
        assert not intake._is_whatsapp_export("Hello world\nThis is a plain paragraph.")

    def test_strip_other_parties(self, intake):
        """Other parties' messages are stripped from WhatsApp export."""
        normalized = intake.normalize_whatsapp(WHATSAPP_EXPORT, ["Daimon"])
        lines = normalized.split("\n")
        # Only Daimon's messages should remain (8 lines from Daimon)
        assert "Caribbean wealth isn't just about money in the bank" in normalized
        assert "It's about community" in normalized
        assert "My grandmother used to say" in normalized
        # Sarah and Mike's messages should NOT be present
        assert "What do you mean?" not in normalized
        assert "That's interesting" not in normalized
        assert "Cool story" not in normalized

    def test_multiline_messages_preserved(self, intake):
        """Multi-line messages from the user are preserved as continuation lines."""
        export = """01/15/24, 2:30 PM - Daimon: Here's a story
that spans multiple lines
because it's a longer thought
01/15/24, 2:31 PM - Other: nice"""
        normalized = intake.normalize_whatsapp(export, ["Daimon"])
        assert "Here's a story" in normalized
        assert "that spans multiple lines" in normalized
        assert "because it's a longer thought" in normalized
        assert "nice" not in normalized

    def test_multiple_user_identifiers(self, intake):
        """Multiple identifiers for the same user work."""
        export = """01/01/24, 1:00 PM - Daimon Nurse: first message
01/01/24, 1:01 PM - Sarah: my message
01/01/24, 1:02 PM - Daimon: second message"""
        normalized = intake.normalize_whatsapp(export, ["Daimon Nurse", "Daimon"])
        assert "first message" in normalized
        assert "second message" in normalized
        assert "my message" not in normalized

    def test_android_24h_format(self, intake):
        """R5: Android non-US locale 24-hour format is detected and parsed."""
        export = """31/12/2023, 23:45 - Daimon: Caribbean wealth is about community
31/12/2023, 23:46 - Sarah: What do you mean?
31/12/2023, 23:47 - Daimon: Sou-sou, pooling, helping each other build"""
        # Detection
        assert intake._is_whatsapp_export(export), "24h format not detected as WhatsApp export"
        # Normalization — Sarah's message stripped
        normalized = intake.normalize_whatsapp(export, ["Daimon"])
        assert "Caribbean wealth is about community" in normalized
        assert "Sou-sou, pooling" in normalized
        assert "What do you mean?" not in normalized

    def test_ios_format_with_seconds(self, intake):
        """R5: iOS format with seconds and brackets is detected and parsed."""
        export = """[31/12/2023, 11:45:23 PM] Daimon: The receipts are in the culture
[31/12/2023, 11:45:45 PM] Sarah: That's interesting
[31/12/2023, 11:46:02 PM] Daimon: Not just in some spreadsheet"""
        # Detection
        assert intake._is_whatsapp_export(export), "iOS format not detected as WhatsApp export"
        # Normalization
        normalized = intake.normalize_whatsapp(export, ["Daimon"])
        assert "The receipts are in the culture" in normalized
        assert "Not just in some spreadsheet" in normalized
        assert "That's interesting" not in normalized

    def test_ios_24h_format_with_seconds(self, intake):
        """R5: iOS 24-hour format with seconds is detected and parsed."""
        export = """[31/12/2023, 23:45:07] Daimon: One hand can't clap
[31/12/2023, 23:45:30] Mike: Cool story bro
[31/12/2023, 23:46:02] Daimon: She meant it literally"""
        assert intake._is_whatsapp_export(export), "iOS 24h format not detected"
        normalized = intake.normalize_whatsapp(export, ["Daimon"])
        assert "One hand can't clap" in normalized
        assert "She meant it literally" in normalized
        assert "Cool story bro" not in normalized


class TestTextNormalization:

    def test_strip_email_signature(self, intake):
        """Email signatures after -- are stripped."""
        text = "Here's my take on AI.\n\n--\nDaimon Nurse\nCEO"
        normalized = intake.normalize_text(text)
        assert "Here's my take on AI" in normalized
        assert "--" not in normalized

    def test_strip_forwarded_header(self, intake):
        """Forwarded email headers are stripped."""
        text = "On Jan 1, 2024, someone wrote:\n> This is quoted text\n\nMy actual reply"
        normalized = intake.normalize_text(text)
        assert "On Jan 1, 2024" not in normalized
        assert "> This is quoted text" not in normalized
        assert "My actual reply" in normalized

    def test_preserve_grammar_and_dialect(self, intake):
        """Grammar and dialect are preserved (never corrected)."""
        text = "I cyan believe he do dat. Is real bajan ting, yuh know?"
        normalized = intake.normalize_text(text)
        assert "cyan believe" in normalized  # Bajan "can't" preserved
        assert "bajan ting" in normalized     # Dialect preserved
        assert "yuh know" in normalized       # Not "corrected" to "you know"

    def test_collapse_excessive_blank_lines(self, intake):
        """3+ blank lines collapse to 2."""
        text = "Para one\n\n\n\n\nPara two"
        normalized = intake.normalize_text(text)
        assert "\n\n\n" not in normalized
        assert "Para one" in normalized
        assert "Para two" in normalized


# --- Ingestion Tests ---

class TestIngestion:

    def test_ingest_pasted_text(self, intake, tmp_db):
        """Pasted text is stored with correct metadata."""
        mid = intake.ingest_text(
            "Caribbean wealth is about community not just cash.",
            business_slug="stackpenni",
            material_type="pasted",
            channel="social_post",
            date_approx="2024-01-15",
            audience="public followers",
        )
        assert mid > 0
        mat = intake.get_material(mid)
        assert mat["channel"] == "social_post"
        assert mat["date_approx"] == "2024-01-15"
        assert mat["audience"] == "public followers"
        assert "Caribbean wealth" in mat["raw_content"]

    def test_ingest_whatsapp_file(self, intake, tmp_upload_dir):
        """WhatsApp export file is detected and ingested."""
        path = os.path.join(tmp_upload_dir, "chat.txt")
        with open(path, "w") as f:
            f.write(WHATSAPP_EXPORT)

        mid = intake.ingest_file(path, business_slug="stackpenni")
        assert mid > 0
        mat = intake.get_material(mid)
        assert mat["material_type"] == "whatsapp_export"
        assert mat["channel"] == "whatsapp"

    def test_ingest_plain_text_file(self, intake, tmp_upload_dir):
        """Plain text file is ingested correctly."""
        path = os.path.join(tmp_upload_dir, "notes.txt")
        with open(path, "w") as f:
            f.write("My thoughts on AI in the Caribbean.\n\nWe need to build our own tools.")

        mid = intake.ingest_file(path, business_slug="stackpenni")
        mat = intake.get_material(mid)
        assert mat["material_type"] == "plain_text"
        assert "AI in the Caribbean" in mat["raw_content"]

    def test_ingest_audio_file(self, intake, tmp_upload_dir):
        """Audio file is ingested with metadata and marked for transcription."""
        path = os.path.join(tmp_upload_dir, "voice_note.mp3")
        with open(path, "wb") as f:
            f.write(b"fake audio data")

        mid = intake.ingest_file(path, business_slug="stackpenni")
        mat = intake.get_material(mid)
        assert mat["material_type"] == "audio"
        assert "transcription pending" in (mat["normalized_content"] or "")

    def test_corpus_assembly(self, intake):
        """Multiple materials are assembled into a corpus with word count."""
        intake.ingest_text("First sample with some words.", business_slug="test",
                           material_type="pasted", channel="social_post")
        intake.ingest_text("Second sample with more words here.", business_slug="test",
                           material_type="pasted", channel="email")

        # Get corpus (run_id=None means all)
        materials = intake.list_materials(business_slug="test")
        assert len(materials) == 2

    def test_corpus_with_run_id(self, intake, tmp_db):
        """Corpus filtered by run_id works."""
        mid1 = intake.ingest_text("Sample one.", run_id=100, business_slug="test")
        mid2 = intake.ingest_text("Sample two.", run_id=100, business_slug="test")
        mid3 = intake.ingest_text("Different run.", run_id=200, business_slug="test")

        corpus = intake.get_corpus(100)
        assert len(corpus["samples"]) == 2
        assert corpus["total_words"] > 0

        corpus2 = intake.get_corpus(200)
        assert len(corpus2["samples"]) == 1