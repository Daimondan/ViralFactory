"""Tests for process registry validation (P2-10)."""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from process_engine import validate_process_registry


def test_validate_returns_empty_for_committed_tree():
    """validate_process_registry() returns [] against the committed tree."""
    result = validate_process_registry()
    assert result == [], f"Expected empty list, got {result}"


def test_validate_reports_missing_prompt(tmp_path):
    """A bogus prompt_file is reported as unresolved."""
    config_dir = tmp_path / "config"
    prompts_dir = tmp_path / "prompts"
    config_dir.mkdir()
    prompts_dir.mkdir()

    # Write a real prompt
    (prompts_dir / "real.md").write_text("# Real prompt")

    # Write a registry with one real and one bogus prompt
    (config_dir / "processes.yaml").write_text(
        "processes:\n"
        "  real_process:\n"
        "    prompt_file: real.md\n"
        "  bogus_process:\n"
        "    prompt_file: nonexistent/bogus.md\n"
    )

    result = validate_process_registry(
        config_dir=str(config_dir),
        prompts_dir=str(prompts_dir),
    )
    assert len(result) == 1
    assert result[0]["process"] == "bogus_process"
    assert result[0]["prompt_file"] == "nonexistent/bogus.md"