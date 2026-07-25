"""Tests for process registry validation (P2-10)."""

import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))

from process_engine import ProcessError, load_process_registry, validate_process_registry


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


def test_validate_reports_prompt_placeholder_without_declared_input(tmp_path):
    """P0-3: a prompt variable must be declared by its process."""
    config_dir = tmp_path / "config"
    prompts_dir = tmp_path / "prompts"
    config_dir.mkdir()
    prompts_dir.mkdir()
    (prompts_dir / "real.md").write_text("# Prompt\n{required_input}\n")
    (config_dir / "processes.yaml").write_text(
        "processes:\n"
        "  test_process:\n"
        "    prompt_file: real.md\n"
        "    inputs: {}\n"
    )

    result = validate_process_registry(
        config_dir=str(config_dir), prompts_dir=str(prompts_dir)
    )

    assert result == [{
        "process": "test_process",
        "prompt_file": "real.md",
        "kind": "missing_input",
        "names": ["required_input"],
    }]


def test_validate_reports_declared_input_unused_by_prompt(tmp_path):
    """P0-3: a declared input must be consumed by its process prompt."""
    config_dir = tmp_path / "config"
    prompts_dir = tmp_path / "prompts"
    config_dir.mkdir()
    prompts_dir.mkdir()
    (prompts_dir / "real.md").write_text("# Prompt\n{used_input}\n")
    (config_dir / "processes.yaml").write_text(
        "processes:\n"
        "  test_process:\n"
        "    prompt_file: real.md\n"
        "    inputs:\n"
        "      used_input: {source: dynamic}\n"
        "      unused_input: {source: dynamic}\n"
    )

    result = validate_process_registry(
        config_dir=str(config_dir), prompts_dir=str(prompts_dir)
    )

    assert result == [{
        "process": "test_process",
        "prompt_file": "real.md",
        "kind": "unused_input",
        "names": ["unused_input"],
    }]


def test_load_process_registry_fails_startup_on_prompt_input_mismatch(tmp_path):
    """P0-3: registry mismatch is a startup failure, not a warning."""
    config_dir = tmp_path / "config"
    prompts_dir = tmp_path / "prompts"
    config_dir.mkdir()
    prompts_dir.mkdir()
    (prompts_dir / "real.md").write_text("{required_input}\n")
    (config_dir / "processes.yaml").write_text(
        "processes:\n"
        "  test_process:\n"
        "    prompt_file: real.md\n"
        "    inputs: {}\n"
    )

    with pytest.raises(ProcessError, match="test_process.*required_input"):
        load_process_registry(str(config_dir), prompts_dir=str(prompts_dir))