"""
ViralFactory — T1.1 Playbook Runner Tests

Tests for:
- PlaybookParser: parses markdown playbooks into structured data
- PlaybookRunner: starts runs, collects inputs, records gate decisions, persists state
- Generic proof: runs a trivial test playbook end-to-end (parse → start → input → gate → complete)
"""

import os
import json
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playbook_runner import PlaybookParser, PlaybookRunner, Playbook, PlaybookStep


# --- Test fixture: a trivial test playbook ---

TRIVIAL_PLAYBOOK = """# Playbook: Trivial Test

<!-- version: 1.0 -->

## Purpose
A minimal playbook to prove the runner is generic. Collects a greeting, echoes it, asks for approval.

## Inputs
1. A greeting string

## Procedure

### Step 1 — Intake
Console asks the user for a greeting. Accept a text input.

### Step 2 — AI Echo
AI analyzes the greeting and produces a response. The output is a JSON object with the echoed greeting.

### Step 3 — Gate
Present the AI response to the user. User approves or rejects.

## Output schema
```json
{"echo": "string"}
```

## Guardrails
- This is a test playbook.
- No real LLM calls are made.
"""


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def tmp_playbook():
    """Write the trivial test playbook to a temp file."""
    with tempfile.NamedTemporaryFile(suffix=".md", delete=False, mode="w") as f:
        f.write(TRIVIAL_PLAYBOOK)
        path = f.name
    yield path
    os.unlink(path)


# --- Parser Tests ---

class TestPlaybookParser:

    def test_parse_basic(self, tmp_playbook):
        """Parser extracts name, purpose, version from a playbook."""
        pb = PlaybookParser.parse(tmp_playbook)
        assert pb.file_version == "1.0"
        assert "minimal playbook" in pb.purpose.lower()

    def test_parse_inputs(self, tmp_playbook):
        """Parser extracts the inputs list."""
        pb = PlaybookParser.parse(tmp_playbook)
        assert len(pb.inputs) >= 1
        assert any("greeting" in inp.lower() for inp in pb.inputs)

    def test_parse_steps(self, tmp_playbook):
        """Parser extracts procedure steps with correct flags."""
        pb = PlaybookParser.parse(tmp_playbook)
        assert len(pb.steps) == 3

        step1 = pb.steps[0]
        assert step1.number == "1"
        assert step1.is_intake  # Step 1 is intake
        assert not step1.is_gate

        step3 = pb.steps[2]
        assert step3.number == "3"
        assert step3.is_gate  # Step 3 is a gate

    def test_parse_guardrails(self, tmp_playbook):
        """Parser extracts guardrails."""
        pb = PlaybookParser.parse(tmp_playbook)
        assert len(pb.guardrails) >= 1
        assert any("test playbook" in g.lower() for g in pb.guardrails)

    def test_parse_real_voice_profile(self):
        """Parser handles the real voice-profile-builder playbook."""
        pb_path = os.path.join(os.path.dirname(__file__), "..", "playbooks", "voice-profile-builder.md")
        if not os.path.exists(pb_path):
            pytest.skip("voice-profile-builder.md not found")

        pb = PlaybookParser.parse(pb_path)
        assert pb.name == "voice-profile-builder"
        assert "voice" in pb.purpose.lower()
        assert len(pb.steps) >= 5  # Steps 1, 1b, 2, 3, 4, 5, 6

        # Step 1 should be intake
        intake_steps = [s for s in pb.steps if s.is_intake]
        assert len(intake_steps) >= 1

        # Step 5 should be a gate (calibration)
        gate_steps = [s for s in pb.steps if s.is_gate]
        assert len(gate_steps) >= 1

    def test_parse_missing_file(self):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            PlaybookParser.parse("/nonexistent/playbook.md")


# --- Runner Tests ---

class TestPlaybookRunner:

    def test_start_run(self, tmp_db):
        """Starting a run creates a row in the database."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("test-playbook", "1.0", "testbrand")
        assert run_id > 0

        run = runner.get_run(run_id)
        assert run["playbook_name"] == "test-playbook"
        assert run["status"] == "pending"
        assert run["business_slug"] == "testbrand"

    def test_add_input(self, tmp_db):
        """Adding input stores it in collected_inputs."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("test", "1.0", "brand")

        runner.add_input(run_id, "greeting", "Hello world")
        run = runner.get_run(run_id)
        collected = json.loads(run["collected_inputs"])
        assert "greeting" in collected
        assert collected["greeting"] == ["Hello world"]

    def test_add_multiple_inputs(self, tmp_db):
        """Multiple inputs for the same key accumulate."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("test", "1.0", "brand")

        runner.add_input(run_id, "samples", "first text")
        runner.add_input(run_id, "samples", "second text")

        run = runner.get_run(run_id)
        collected = json.loads(run["collected_inputs"])
        assert len(collected["samples"]) == 2

    def test_set_gate_result(self, tmp_db):
        """Setting a gate decision records it and updates status."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("test", "1.0", "brand")

        runner.set_gate_result(run_id, "3", "approve", "looks good")
        run = runner.get_run(run_id)
        gates = json.loads(run["gate_results"])
        assert gates["3"]["decision"] == "approve"
        assert gates["3"]["notes"] == "looks good"

    def test_update_run_status(self, tmp_db):
        """Updating status works."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("test", "1.0", "brand")
        runner.update_run(run_id, status="in_progress", current_step="2")

        run = runner.get_run(run_id)
        assert run["status"] == "in_progress"
        assert run["current_step"] == "2"

    def test_list_runs(self, tmp_db):
        """Listing runs returns them ordered by id desc."""
        runner = PlaybookRunner(tmp_db)
        id1 = runner.start_run("a", "1.0", "brand")
        id2 = runner.start_run("b", "1.0", "brand")

        all_runs = runner.list_runs()
        assert len(all_runs) == 2
        assert all_runs[0]["id"] == id2  # newest first

        brand_runs = runner.list_runs("brand")
        assert len(brand_runs) == 2

        other = runner.list_runs("nonexistent")
        assert len(other) == 0

    def test_add_llm_output(self, tmp_db):
        """LLM outputs are stored per step."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("test", "1.0", "brand")

        runner.add_llm_output(run_id, "2", {"echo": "Hello back"})
        run = runner.get_run(run_id)
        outputs = json.loads(run["llm_outputs"])
        assert outputs["2"]["echo"] == "Hello back"


# --- End-to-End Generic Proof ---

class TestEndToEndPlaybook:

    def test_trivial_playbook_full_run(self, tmp_db, tmp_playbook):
        """
        T1.1 acceptance criteria: prove the runner is generic by running a
        trivial test playbook end-to-end.

        Parse → start run → add input → record LLM output → gate approve → completed.
        """
        # 1. Parse the playbook
        pb = PlaybookParser.parse(tmp_playbook)
        assert len(pb.steps) == 3

        # 2. Start a run
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run(pb.name, pb.file_version, "testbrand")
        assert run_id > 0

        # 3. Step 1 — Intake: user provides a greeting
        runner.add_input(run_id, "1", "Hello from Barbados!")
        run = runner.get_run(run_id)
        collected = json.loads(run["collected_inputs"])
        assert "Hello from Barbados!" in collected["1"]

        # 4. Step 2 — AI Echo: (simulated LLM output)
        runner.add_llm_output(run_id, "2", {"echo": "Hello from Barbados!"})
        runner.update_run(run_id, status="in_progress", current_step="3")
        run = runner.get_run(run_id)
        outputs = json.loads(run["llm_outputs"])
        assert outputs["2"]["echo"] == "Hello from Barbados!"

        # 5. Step 3 — Gate: user approves
        runner.set_gate_result(run_id, "3", "approve", "sounds good")
        runner.update_run(run_id, status="completed")
        run = runner.get_run(run_id)
        assert run["status"] == "completed"
        gates = json.loads(run["gate_results"])
        assert gates["3"]["decision"] == "approve"

        # 6. Verify the full run is persisted and retrievable
        final_run = runner.get_run(run_id)
        assert final_run["status"] == "completed"
        assert final_run["playbook_name"] == pb.name
        assert json.loads(final_run["collected_inputs"])["1"] == ["Hello from Barbados!"]
        assert json.loads(final_run["llm_outputs"])["2"]["echo"] == "Hello from Barbados!"
        assert json.loads(final_run["gate_results"])["3"]["decision"] == "approve"

    def test_trivial_playbook_reject_path(self, tmp_db, tmp_playbook):
        """The reject path also works — gate reject cancels the run."""
        runner = PlaybookRunner(tmp_db)
        run_id = runner.start_run("trivial_test", "1.0", "testbrand")

        runner.add_input(run_id, "1", "test input")
        runner.set_gate_result(run_id, "3", "reject", "not what I wanted")
        runner.update_run(run_id, status="cancelled")

        run = runner.get_run(run_id)
        assert run["status"] == "cancelled"
        gates = json.loads(run["gate_results"])
        assert gates["3"]["decision"] == "reject"