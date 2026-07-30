import hashlib
import json
from pathlib import Path

import yaml

import sys
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from visual_treatment_gate import validate_reference_candidates, validate_visual_treatment


CONFIG_PATH = Path(__file__).parents[1] / "config/visual_treatment_proposals/stackpenni_flat_vector_pennifold.yaml"


def test_stackpenni_vector_comparison_set_is_proposed_and_palette_evidenced():
    payload = yaml.safe_load(CONFIG_PATH.read_text())
    treatment = validate_visual_treatment(payload["treatment"])
    candidates = validate_reference_candidates(payload["reference_candidates"])

    assert treatment["treatment_id"] == "flat_vector_pennifold"
    assert treatment["status"] == "proposed"
    assert len(candidates) == 5
    assert {item["status"] for item in candidates} == {"proposed"}
    assert {item["ref_id"] for item in candidates} == set(treatment["reference_set"][i]["ref_id"] for i in range(5))

    for candidate in candidates:
        artifact = Path(candidate["artifact_path"])
        assert artifact.exists()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == candidate["artifact_sha256"]
        assert candidate["dimensions"] == [774, 1376]
        palette = candidate["palette_evidence"]
        assert palette["mechanical_verdict"] == "pass"
        assert palette["fill_set_identical"] is True
        assert all(value == 0 for value in palette["forbidden_svg_elements"].values())


def test_proposed_vector_is_not_an_approved_current_treatment():
    payload = yaml.safe_load(CONFIG_PATH.read_text())
    assert payload["treatment"]["status"] == "proposed"
    assert all(item["status"] == "proposed" for item in payload["treatment"]["reference_set"])
    assert all(item["status"] == "proposed" for item in payload["reference_candidates"])


def test_reference_preview_route_serves_real_asset_and_rejects_traversal(tmp_path):
    from app import create_app

    app = create_app(config_dir="config", db_path=str(tmp_path / "preview.db"))
    app.config.update(TESTING=True)
    client = app.test_client()
    response = client.get("/reference-assets/stackpenni/palette_lock_assets/spec01/B-fitzroy-clean.png")
    assert response.status_code == 200
    assert response.mimetype == "image/png"
    assert len(response.data) > 1000

    traversal = client.get("/reference-assets/../../src/app.py")
    assert traversal.status_code in (400, 404)
