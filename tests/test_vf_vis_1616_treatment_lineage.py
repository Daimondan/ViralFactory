import copy
import hashlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from production_contract import (
    assemble_contract,
    compute_writer_contract_hash,
)
from visual_treatment_lineage import (
    VisualTreatmentLineageError,
    compute_visual_treatment_hash,
    make_visual_treatment_ref,
    resolve_visual_treatment_ref,
    require_matching_visual_treatment_ref,
)
from services.candidate_store import CandidateStore
from services.component_requirements import ComponentRequirementsStore
from services.manifest_freeze import ManifestError, ManifestStore
from services.production_orchestrator import ProductionSessionService


def treatment(status="approved", version="1.0"):
    return {
        "treatment_id": "cinematic_painted",
        "version": version,
        "description": "A cinematic treatment",
        "reference_set": [{"ref_id": "ref:cinematic:01", "role": "canonical", "status": "approved"}],
        "palette": {"allowed_colors": ["#111111"], "prohibited_colors": []},
        "line_texture_lighting": {"line_rule": "line", "texture_rule": "texture", "lighting_rule": "light"},
        "prohibited_characteristics": ["mixed treatment"],
        "allowed_formats": ["reel"],
        "continuity": {"character": "same", "location": "same", "world_subjects": "one"},
        "tier1_generation_rules": ["same"],
        "tier2_overlay_relationship": "overlays",
        "disclosure_requirements": ["disclose"],
        "status": status,
        "provenance": {"source": "fixture"},
    }


def style_data(items):
    return {"visual_treatments": items}


def content_contract(ref=None):
    contract = {
        "contract_id": "contract-1",
        "core_claim": "claim",
        "audience_value": "value",
        "evidence_refs": ["source:1"],
        "primary_emotional_job": "curiosity",
        "primary_audience_action": "finish",
        "format_name": "reel",
        "platform": "Instagram",
        "capture_policy": "generated_allowed",
        "evidence_label": "HYPOTHESIS",
    }
    if ref is not None:
        contract["visual_treatment_ref"] = ref
    return contract


def test_ref_contains_exact_version_and_content_hash():
    item = treatment()
    ref = make_visual_treatment_ref(item)
    assert ref == {
        "treatment_id": "cinematic_painted",
        "version": "1.0",
        "treatment_hash": compute_visual_treatment_hash(item),
    }
    assert len(ref["treatment_hash"]) == 64


def test_resolver_requires_approved_exact_hash_and_version():
    item = treatment()
    ref = make_visual_treatment_ref(item)
    assert resolve_visual_treatment_ref(ref, style_data([item])) == ref

    with pytest.raises(VisualTreatmentLineageError, match="not approved"):
        resolve_visual_treatment_ref(ref, style_data([treatment(status="proposed")]))

    stale = dict(ref, version="2.0")
    with pytest.raises(VisualTreatmentLineageError, match="not found"):
        resolve_visual_treatment_ref(stale, style_data([item]))

    mixed = dict(ref, treatment_hash="0" * 64)
    with pytest.raises(VisualTreatmentLineageError, match="hash"):
        resolve_visual_treatment_ref(mixed, style_data([item]))


def test_matching_ref_rejects_mixed_treatment_inputs():
    item = treatment()
    ref = make_visual_treatment_ref(item)
    other = make_visual_treatment_ref(treatment(version="2.0"))
    assert require_matching_visual_treatment_ref(ref, ref) == ref
    with pytest.raises(VisualTreatmentLineageError, match="mismatch"):
        require_matching_visual_treatment_ref(ref, other)


def test_production_contract_persists_ref_and_writer_hash_changes():
    item = treatment()
    ref = make_visual_treatment_ref(item)
    beats = [{
        "beat_id": "b1",
        "vo_text": "A line",
        "staged_action": "A person turns",
        "capture_policy": "generated_allowed",
        "visual_events": [],
    }]
    first = assemble_contract(content_contract(ref), beats)
    assert first["content_contract"]["visual_treatment_ref"] == ref
    changed_ref = dict(ref, treatment_hash="f" * 64)
    changed = assemble_contract(content_contract(changed_ref), beats)
    assert changed["content_contract"]["visual_treatment_ref"] == changed_ref
    assert changed["writer_contract_hash"] != first["writer_contract_hash"]

    legacy = assemble_contract(content_contract(), beats)
    assert "visual_treatment_ref" not in legacy["content_contract"]
    assert compute_writer_contract_hash({"production_binding": None, "visual_treatment_ref": ref}) != compute_writer_contract_hash({"production_binding": None, "visual_treatment_ref": None})


def test_bound_manifest_carries_ref_and_blocks_unbound_candidate(tmp_path):
    db_path = str(tmp_path / "lineage.db")
    item = treatment()
    ref = make_visual_treatment_ref(item)
    sessions = ProductionSessionService(db_path=db_path, foreign_keys=False)
    session = sessions.create_session(
        "tenant", 1, 2, "Instagram", "reel", visual_treatment_ref=ref
    )
    req_store = ComponentRequirementsStore(db_path=db_path)
    req_store.save_requirements(
        "tenant", session["id"], 1, 2,
        {
            "format": "reel",
            "platform": "Instagram",
            "visual_treatment_ref": ref,
            "categories": [{
                "category": "visual",
                "required": True,
                "roles": [{"role": "hero", "required": True, "none_allowed": False, "preview_required": True}],
            }],
        },
    )
    candidates = CandidateStore(db_path=db_path)
    candidate = candidates.create_candidate(
        "tenant", session["id"], 1, 2, "visual", "hero",
        artifact_ref="asset:hero", artifact_hash="a" * 64,
        preview_ref="preview:hero", preview_hash="b" * 64,
        status="approved",
    )
    assert json.loads(candidate["generation_provenance_json"])["visual_treatment_ref"] == ref
    manifest = ManifestStore(db_path=db_path, config_dir="config").freeze_manifest("tenant", session["id"])
    assert manifest["manifest_json"]["visual_treatment_ref"] == ref
    assert manifest["manifest_json"]["candidates"][0]["visual_treatment_ref"] == ref

    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE component_candidates SET generation_provenance_json = ? WHERE id = ?", ("{}", candidate["id"]))
    conn.commit()
    conn.close()
    with pytest.raises(ManifestError, match="visual treatment lineage invalid"):
        ManifestStore(db_path=db_path, config_dir="config").freeze_manifest("tenant", session["id"])
