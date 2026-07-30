"""VF-IDEA-1612: operator-gated module/config proposal preparation."""

import hashlib
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_proposal import prepare_module_proposals
from proposal_store import ProposalStore


def test_module_config_proposals_are_pending_and_config_owned(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    spec = {
        "proposals": {
            "tenant_a": [
                {"target_module": "voice-profile", "target_section": "remit", "proposal_type": "module_change", "evidence": ["operator request"], "change_description": "broaden remit", "exact_diff": "+ remit: broad", "rationale": "broaden"},
                {"target_module": "audience-insights", "target_section": "claims", "proposal_type": "module_change", "evidence": ["operator request"], "change_description": "mark beliefs", "exact_diff": "+ status: belief", "rationale": "honesty"},
            ]
        }
    }
    (config_dir / "module_proposals.yaml").write_text(yaml.safe_dump(spec))
    store = ProposalStore(str(tmp_path / "proposals.db"))
    ids = prepare_module_proposals(store, "tenant_a", str(config_dir))
    rows = [store.get_proposal(item) for item in ids]
    assert len(rows) == 2
    assert all(row["status"] == "pending" for row in rows)
    assert all(row["exact_diff"] for row in rows)


def test_preparation_never_writes_target_files(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "module_proposals.yaml").write_text(yaml.safe_dump({"proposals": {"tenant_a": [{"target_module": "business", "target_section": "audience", "proposal_type": "config_change", "evidence": [], "change_description": "broaden", "exact_diff": "+ audience: broad", "rationale": "r"}]}}))
    target = tmp_path / "business.yaml"
    target.write_text("audience: current\n")
    before = hashlib.sha256(target.read_bytes()).hexdigest()
    store = ProposalStore(str(tmp_path / "proposals.db"))
    prepare_module_proposals(store, "tenant_a", str(config_dir))
    assert hashlib.sha256(target.read_bytes()).hexdigest() == before
