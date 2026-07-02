"""
ViralFactory — T2.9 Gate-Token Enforcement Tests

Tests for:
- Gate token verification (valid, missing, invalid, no approval)
- ModuleStore.store() refuses without gate token
- ModuleStore.store() refuses with invalid gate token
- ModuleStore.store() refuses with 'unknown' business slug
- ModuleStore.store() succeeds with valid gate token after approval recorded
- Config writes refuse without gate token
- Config writes refuse with invalid gate token
- store_voice endpoint: parked writes nothing (existing behavior preserved)
- store_business endpoint: approved writes with gate token
- store_sources endpoint: refuses when business slug is 'unknown'
- Orphan prevention: no modules/unknown/ directory created
"""

import json
import os
import tempfile
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_store import (
    ModuleStore, GateTokenError, verify_gate_token, generate_gate_token,
    brand_context_to_markdown,
)
from playbook_runner import PlaybookRunner


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
def tmp_dirs():
    """Temporary config + modules + db. The DB is initialized with playbook_runs table."""
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)

            # Initialize the playbook_runs table in this DB
            runner = PlaybookRunner(db_path)
            # Just calling the constructor creates the table

            business = {
                "business": {"name": "Test", "slug": "testbrand", "description": "Test"},
                "subjects": ["AI"], "platforms": [{"name": "X", "handle": "@t", "priority": 1}],
            }
            with open(os.path.join(config_dir, "business.yaml"), "w") as f:
                yaml.dump(business, f)
            models = {
                "active": {"default": "tb", "drafter": "tb", "drafter_ab_candidate": None},
                "tb": {"provider": "ollama_cloud", "model": "m", "temperature": 0,
                       "max_tokens": 4, "base_url": "https://x.com"},
            }
            with open(os.path.join(config_dir, "models.yaml"), "w") as f:
                yaml.dump(models, f)
            sources = {"feeds": [], "channels": [], "queries": []}
            with open(os.path.join(config_dir, "sources.yaml"), "w") as f:
                yaml.dump(sources, f)

            yield config_dir, modules_dir, db_path
            if os.path.exists(db_path):
                os.unlink(db_path)


@pytest.fixture
def approved_run_in_dirs(tmp_dirs):
    """Create a run with an approved gate decision, using the tmp_dirs DB."""
    _, _, db_path = tmp_dirs
    runner = PlaybookRunner(db_path)
    run_id = runner.start_run("test-playbook", "1.0", "testbrand")
    runner.set_gate_result(run_id, "4", "approve", "looks good")
    return run_id


@pytest.fixture
def unapproved_run_in_dirs(tmp_dirs):
    """Create a run with a parked gate decision, using the tmp_dirs DB."""
    _, _, db_path = tmp_dirs
    runner = PlaybookRunner(db_path)
    run_id = runner.start_run("test-playbook", "1.0", "testbrand")
    runner.set_gate_result(run_id, "4", "park", "")
    return run_id


@pytest.fixture
def approved_run(tmp_db):
    """Create a run with an approved gate decision, using tmp_db (for standalone verification tests)."""
    runner = PlaybookRunner(tmp_db)
    run_id = runner.start_run("test-playbook", "1.0", "testbrand")
    runner.set_gate_result(run_id, "4", "approve", "looks good")
    return run_id


@pytest.fixture
def unapproved_run(tmp_db):
    """Create a run with a parked gate decision, using tmp_db."""
    runner = PlaybookRunner(tmp_db)
    run_id = runner.start_run("test-playbook", "1.0", "testbrand")
    runner.set_gate_result(run_id, "4", "park", "")
    return run_id


# --- Gate Token Verification Tests ---

class TestGateTokenVerification:

    def test_valid_gate_token(self, tmp_db, approved_run):
        """A valid gate token passes verification."""
        token = generate_gate_token(approved_run)
        result = verify_gate_token(tmp_db, approved_run, token)
        assert result["decision"] == "approve"

    def test_missing_gate_token(self, tmp_db, approved_run):
        """Missing gate token raises GateTokenError."""
        with pytest.raises(GateTokenError, match="No gate token"):
            verify_gate_token(tmp_db, approved_run, "")

    def test_invalid_gate_token(self, tmp_db, approved_run):
        """Invalid gate token raises GateTokenError."""
        with pytest.raises(GateTokenError, match="Invalid gate token"):
            verify_gate_token(tmp_db, approved_run, "wrong_token")

    def test_no_approval_on_run(self, tmp_db, unapproved_run):
        """Run with no approved gate decision raises GateTokenError."""
        token = generate_gate_token(unapproved_run)
        with pytest.raises(GateTokenError, match="no approved gate"):
            verify_gate_token(tmp_db, unapproved_run, token)

    def test_nonexistent_run(self, tmp_db):
        """Non-existent run raises GateTokenError."""
        with pytest.raises(GateTokenError, match="not found"):
            verify_gate_token(tmp_db, 99999, "run_99999_approved")


# --- ModuleStore.store() Gate Enforcement Tests ---

class TestModuleStoreGateEnforcement:

    def test_store_without_gate_token_raises(self, tmp_dirs, approved_run):
        """store() raises without a gate token."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        with pytest.raises(GateTokenError, match="Gate token and run_id"):
            store.store("testbrand", "test-module", "# Test", gate_token=None, run_id=approved_run)

    def test_store_with_invalid_gate_token_raises(self, tmp_dirs, approved_run_in_dirs):
        """store() raises with an invalid gate token."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        with pytest.raises(GateTokenError, match="Invalid gate token"):
            store.store("testbrand", "test-module", "# Test", gate_token="wrong", run_id=approved_run_in_dirs)

    def test_store_without_approval_raises(self, tmp_dirs, unapproved_run_in_dirs):
        """store() raises when the run has no approved gate decision."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        token = generate_gate_token(unapproved_run_in_dirs)
        with pytest.raises(GateTokenError, match="no approved gate"):
            store.store("testbrand", "test-module", "# Test", gate_token=token, run_id=unapproved_run_in_dirs)

    def test_store_with_unknown_slug_raises(self, tmp_dirs, approved_run_in_dirs):
        """store() raises with 'unknown' business slug — no orphans."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        token = generate_gate_token(approved_run_in_dirs)
        with pytest.raises(GateTokenError, match="orphan"):
            store.store("unknown", "test-module", "# Test", gate_token=token, run_id=approved_run_in_dirs)

    def test_store_with_empty_slug_raises(self, tmp_dirs, approved_run_in_dirs):
        """store() raises with empty business slug."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        token = generate_gate_token(approved_run_in_dirs)
        with pytest.raises(GateTokenError, match="orphan"):
            store.store("", "test-module", "# Test", gate_token=token, run_id=approved_run_in_dirs)

    def test_store_with_valid_token_succeeds(self, tmp_dirs, approved_run_in_dirs):
        """store() succeeds with a valid gate token after approval."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        token = generate_gate_token(approved_run_in_dirs)
        path = store.store("testbrand", "test-module", "# Test Module\n\nContent.",
                           version="1.0", provenance={"version": "1.0"},
                           gate_token=token, run_id=approved_run_in_dirs)
        assert os.path.exists(path)
        loaded = store.load("testbrand", "test-module")
        assert "Test Module" in loaded

    def test_no_orphan_directory_created(self, tmp_dirs, approved_run_in_dirs):
        """No modules/unknown/ directory is ever created."""
        _, modules_dir, db_path = tmp_dirs
        store = ModuleStore(modules_dir=modules_dir, db_path=db_path)
        token = generate_gate_token(approved_run_in_dirs)
        with pytest.raises(GateTokenError):
            store.store("unknown", "test", "# Test", gate_token=token, run_id=approved_run_in_dirs)
        # Verify no modules/unknown/ directory was created
        unknown_dir = os.path.join(modules_dir, "unknown")
        assert not os.path.exists(unknown_dir), "modules/unknown/ directory was created — orphans not prevented!"