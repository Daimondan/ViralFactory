"""VF-FMT-1607: operator-gated production proposal preparation."""

import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from episode_proposal import create_episode_proposals, load_episode_proposal_spec
from proposal_store import ProposalStore


def _write_spec(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "production_proposals.yaml").write_text(
        yaml.safe_dump(
            {
                "proposals": {
                    "tenant": {
                        "format_entry": {
                            "target_module": "format-guide",
                            "target_section": "Formats > Parable",
                            "proposal_type": "add",
                            "change_description": "Add exact episode format entry",
                            "exact_diff": "+ format entry with binding",
                            "evidence": ["operator format proposal"],
                            "rationale": "A gated production affordance",
                        },
                        "process_binding": {
                            "target_module": "process-registry",
                            "target_section": "production_processes.episode-format",
                            "proposal_type": "status_change",
                            "change_description": "Activate the registered process after approval",
                            "exact_diff": "- status: proposed\n+ status: approved",
                            "evidence": ["approved process prerequisites"],
                            "rationale": "Process activation is an explicit operator decision",
                        },
                        "canon_prerequisite": {
                            "target_module": "visual-style",
                            "target_section": "Fictional recurring persona",
                            "proposal_type": "add",
                            "change_description": "Add disclosure and canon prerequisite",
                            "exact_diff": "+ disclosed fictional persona rule",
                            "evidence": ["canon proposal"],
                            "rationale": "The episode route needs its governing canon",
                        },
                    }
                }
            }
        )
    )
    return config_dir


def test_loading_spec_is_config_owned_and_exact(tmp_path):
    config_dir = _write_spec(tmp_path)
    spec = load_episode_proposal_spec(str(config_dir), "tenant")
    assert spec["format_entry"]["target_module"] == "format-guide"
    assert spec["process_binding"]["exact_diff"].startswith("- status")


def test_prepare_creates_pending_proposals_without_self_approval(tmp_path):
    config_dir = _write_spec(tmp_path)
    db_path = str(tmp_path / "proposals.db")
    store = ProposalStore(db_path=db_path)

    ids = create_episode_proposals(store, "tenant", str(config_dir))

    assert len(ids) == 3
    proposals = store.list_proposals("tenant", status="pending")
    assert len(proposals) == 3
    assert {p["status"] for p in proposals} == {"pending"}
    assert {p["target_module"] for p in proposals} == {
        "format-guide", "process-registry", "visual-style"
    }


def test_repeated_prepare_supersedes_prior_pending_proposals(tmp_path):
    config_dir = _write_spec(tmp_path)
    store = ProposalStore(db_path=str(tmp_path / "proposals.db"))

    create_episode_proposals(store, "tenant", str(config_dir))
    create_episode_proposals(store, "tenant", str(config_dir))

    all_rows = store.list_proposals("tenant")
    assert sum(row["status"] == "pending" for row in all_rows) == 3
    assert sum(row["status"] == "superseded" for row in all_rows) == 3
