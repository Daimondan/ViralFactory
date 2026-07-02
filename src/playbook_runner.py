"""
ViralFactory — Playbook Runner

Generic engine that executes playbook markdown files as console flows.
A playbook is a markdown file with:
- Purpose
- Inputs
- Procedure (numbered steps, some with sub-steps)
- Output schema
- Gate

The runner parses the playbook, presents each step to the user through a web console,
collects inputs, calls the LLM adapter for AI steps, and enforces gates.

This is the engine that makes onboarding repeatable for any user.
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class PlaybookStep:
    """A single step in a playbook procedure."""
    number: str                    # e.g. "1", "1b", "2", "3"
    title: str                     # human-readable title
    description: str               # what happens in this step
    is_gate: bool = False          # does this step require human approval?
    is_intake: bool = False        # does this step collect user materials?
    is_llm: bool = False           # does this step call the LLM?
    is_interview: bool = False     # is this the interview fallback?
    sub_steps: list = field(default_factory=list)
    prompt_file: Optional[str] = None  # associated prompt template if LLM step
    schema: Optional[dict] = None      # output schema if LLM step


@dataclass
class Playbook:
    """A parsed playbook ready for execution."""
    name: str
    purpose: str
    inputs: list[str]               # list of input descriptions
    steps: list[PlaybookStep]
    output_schema_heading: str      # the markdown heading for the output schema
    guardrails: list[str]
    file_path: str
    file_version: str
    run_order: int = 99             # UI-REVIEW-001 F1: explicit ordering, config-driven
    display_label: str = ""         # UI-REVIEW-001 F4: operator-facing label


class PlaybookParser:
    """Parses a playbook markdown file into a Playbook dataclass."""

    @staticmethod
    def parse(file_path: str) -> Playbook:
        """Parse a playbook markdown file into a Playbook object."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Playbook not found: {file_path}")

        content = path.read_text()
        name = path.stem  # filename without extension

        # Extract version from comment (same pattern as LLM adapter)
        version_match = re.search(r'<!--\s*version:\s*([\d.]+)\s*-->', content)
        version = version_match.group(1) if version_match else "1.0"

        # Extract run_order from comment (UI-REVIEW-001 F1)
        run_order_match = re.search(r'<!--\s*run_order:\s*(\d+)\s*-->', content)
        run_order = int(run_order_match.group(1)) if run_order_match else 99

        # Extract display_label from comment (UI-REVIEW-001 F4)
        display_label_match = re.search(r'<!--\s*display_label:\s*(.+?)\s*-->', content)
        display_label = display_label_match.group(1) if display_label_match else name

        # Extract sections by markdown headers
        purpose = PlaybookParser._extract_section(content, "Purpose")
        inputs_raw = PlaybookParser._extract_section(content, "Inputs")
        procedure_raw = PlaybookParser._extract_section(content, "Procedure")
        guardrails_raw = PlaybookParser._extract_section(content, "Guardrails")

        # Parse inputs into a list
        inputs = []
        for line in inputs_raw.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("1.") or line.startswith("2.") or line.startswith("3.") or line.startswith("4."):
                # Remove the bullet/number prefix
                cleaned = re.sub(r'^[-\d]+\.\s*', '', line)
                if cleaned:
                    inputs.append(cleaned)

        # Parse procedure into steps
        steps = PlaybookParser._parse_steps(procedure_raw)

        # Determine output schema heading
        schema_heading = "Output schema"
        if "## Output schema" in content:
            schema_heading = "Output schema"
        elif "## Output" in content:
            schema_heading = "Output"

        return Playbook(
            name=name,
            purpose=purpose.strip(),
            inputs=inputs,
            steps=steps,
            output_schema_heading=schema_heading,
            guardrails=[g.strip() for g in guardrails_raw.split("\n") if g.strip().startswith("-")],
            file_path=str(file_path),
            file_version=version,
            run_order=run_order,
            display_label=display_label,
        )

    @staticmethod
    def _extract_section(content: str, section_name: str) -> str:
        """Extract the text under a ## section header until the next ## or end."""
        sections = {}
        current_header = None
        current_text = []

        for line in content.split("\n"):
            header_match = re.match(r'^##\s+(.+)', line)
            if header_match:
                if current_header:
                    sections[current_header] = "\n".join(current_text).strip()
                current_header = header_match.group(1).strip()
                current_text = []
            elif current_header:
                current_text.append(line)

        if current_header:
            sections[current_header] = "\n".join(current_text).strip()

        # Look for the section by name (case-insensitive, partial match)
        for header, text in sections.items():
            if section_name.lower() in header.lower():
                return text

        return ""

    @staticmethod
    def _parse_steps(procedure_text: str) -> list[PlaybookStep]:
        """Parse the procedure section into PlaybookStep objects.

        Handles two formats:
        1. '### Step N — Title' (structured format, e.g. voice-profile-builder)
        2. 'N. Description' (numbered-list format, e.g. viral-patterns-starter)
        """
        # Try structured format first
        steps = PlaybookParser._parse_steps_structured(procedure_text)
        if steps:
            return steps

        # Fall back to numbered-list format
        return PlaybookParser._parse_steps_numbered(procedure_text)

    @staticmethod
    def _parse_steps_structured(procedure_text: str) -> list[PlaybookStep]:
        """Parse '### Step N — Title' format."""
        steps = []
        lines = procedure_text.split("\n")
        current_step = None

        for line in lines:
            # Match ### Step N — Title or ### Step Nb — Title
            step_match = re.match(r'^###\s+Step\s+(\w+)\s*[—–-]\s*(.+)', line)
            if step_match:
                if current_step:
                    steps.append(current_step)
                num = step_match.group(1)
                title = step_match.group(2).strip()
                current_step = PlaybookStep(
                    number=num,
                    title=title,
                    description="",
                    is_gate="gate" in title.lower() or "gate" in num.lower(),
                    is_intake="intake" in title.lower() or "interview" in title.lower() or "1b" in num,
                    is_interview="interview" in title.lower() or "fallback" in title.lower(),
                )
                continue

            # Match ### Step N (no em-dash, just title after colon or space)
            step_match2 = re.match(r'^###\s+Step\s+(\w+)\s*:?\s*(.*)', line)
            if step_match2 and not current_step:
                num = step_match2.group(1)
                title = step_match2.group(2).strip() or f"Step {num}"
                current_step = PlaybookStep(
                    number=num,
                    title=title,
                    description="",
                    is_gate="gate" in title.lower(),
                    is_intake="intake" in title.lower() or "interview" in title.lower(),
                    is_interview="interview" in title.lower() or "fallback" in title.lower(),
                )
                continue

            # Accumulate description
            if current_step:
                current_step.description += line + "\n"
                # Detect LLM steps (description mentions AI analyzes, AI drafts, etc.)
                if any(kw in line.lower() for kw in ["ai analyzes", "ai drafts", "ai generates", "llm", "prompt"]):
                    current_step.is_llm = True

        if current_step:
            steps.append(current_step)

        return steps

    @staticmethod
    def _parse_steps_numbered(procedure_text: str) -> list[PlaybookStep]:
        """Parse 'N. Description' numbered-list format.

        Each line like '1. Do something' or '5. Gate → v1.' becomes a PlaybookStep.
        Gate steps are detected by 'gate' appearing in the line.
        """
        steps = []
        for line in procedure_text.split("\n"):
            line = line.strip()
            # Match 'N. Description' but not sub-bullets or sub-numbers
            match = re.match(r'^(\d+)\.\s+(.+)', line)
            if match:
                num = match.group(1)
                desc = match.group(2).strip()
                is_gate = bool(re.match(r'^gate\b', desc.lower()))
                is_intake = any(kw in desc.lower() for kw in ["intake", "ingest", "collect", "paste", "upload"])
                is_llm = any(kw in desc.lower() for kw in ["ai analyzes", "ai drafts", "ai generates", "ai builds", "llm"])
                steps.append(PlaybookStep(
                    number=num,
                    title=desc[:80],
                    description=desc,
                    is_gate=is_gate,
                    is_intake=is_intake,
                    is_llm=is_llm,
                ))

        return steps


class PlaybookRunner:
    """
    Executes a Playbook through the console.

    The runner tracks state for each step:
    - intake steps: collect materials from the user
    - llm steps: call the LLM adapter with the right prompt + schema
    - gate steps: present results to the user for approval

    State is persisted so a playbook can be paused and resumed.
    """

    def __init__(self, db_path: str = "data/viralfactory.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create the playbook_runs table for state tracking."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS playbook_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playbook_name TEXT NOT NULL,
                playbook_version TEXT NOT NULL,
                business_slug TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                -- pending, in_progress, awaiting_gate, completed, cancelled
                current_step TEXT,
                collected_inputs TEXT,    -- JSON dict of collected materials
                llm_outputs TEXT,          -- JSON dict of LLM outputs per step
                gate_results TEXT,         -- JSON dict of gate decisions
                started_at TEXT,
                completed_at TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()

    def start_run(self, playbook_name: str, playbook_version: str, business_slug: str) -> int:
        """Start a new playbook run. Returns the run ID."""
        import sqlite3
        from datetime import datetime, timezone
        conn = sqlite3.connect(self.db_path)
        ts = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            """INSERT INTO playbook_runs
               (playbook_name, playbook_version, business_slug, status,
                collected_inputs, llm_outputs, gate_results, created_at)
               VALUES (?, ?, ?, 'pending', '{}', '{}', '{}', ?)""",
            (playbook_name, playbook_version, business_slug, ts),
        )
        run_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return run_id

    def get_run(self, run_id: int) -> dict:
        """Get the current state of a playbook run."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM playbook_runs WHERE id = ?", (run_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def update_run(self, run_id: int, **fields):
        """Update one or more fields on a playbook run."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        sets = []
        values = []
        for key, value in fields.items():
            sets.append(f"{key} = ?")
            values.append(value)
        values.append(run_id)
        conn.execute(
            f"UPDATE playbook_runs SET {', '.join(sets)} WHERE id = ?",
            values,
        )
        conn.commit()
        conn.close()

    def add_input(self, run_id: int, key: str, value: str):
        """Add a collected input to a run."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        inputs = json.loads(run.get("collected_inputs") or "{}")
        if key not in inputs:
            inputs[key] = []
        inputs[key].append(value)
        self.update_run(run_id, collected_inputs=json.dumps(inputs))

    def add_llm_output(self, run_id: int, step: str, output: dict):
        """Store an LLM output for a step."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        outputs = json.loads(run.get("llm_outputs") or "{}")
        outputs[step] = output
        self.update_run(run_id, llm_outputs=json.dumps(outputs))

    def set_gate_result(self, run_id: int, step: str, result: str, notes: str = ""):
        """Record a gate decision for a step."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        results = json.loads(run.get("gate_results") or "{}")
        results[step] = {"decision": result, "notes": notes}
        self.update_run(run_id, gate_results=json.dumps(results))

    def list_runs(self, business_slug: str = None) -> list[dict]:
        """List playbook runs, optionally filtered by business."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        if business_slug:
            rows = conn.execute(
                "SELECT * FROM playbook_runs WHERE business_slug = ? ORDER BY id DESC",
                (business_slug,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM playbook_runs ORDER BY id DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_gate_step_number(playbook: Playbook) -> str:
        """Derive the gate step number from a parsed playbook.

        Returns the step number of the first gate step, or "1" as fallback
        if no gate step is found (should not happen for valid playbooks).

        This replaces hardcoded gate step strings in route handlers (R15).
        """
        for step in playbook.steps:
            if step.is_gate:
                return step.number
        return "1"