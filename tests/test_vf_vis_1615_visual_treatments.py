import copy
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from module_store import (
    VISUAL_STYLE_SCHEMA,
    VISUAL_TREATMENT_SCHEMA,
    parse_visual_style_markdown,
    visual_style_to_markdown,
)
from validator import ValidationError, validate_llm_output


def base_style(treatments):
    return {
        "palette": {
            "primary": {"hex": "#111111", "name": "Primary"},
            "secondary": {"hex": "#222222", "name": "Secondary"},
            "accent": {"hex": "#333333", "name": "Accent"},
            "background": {"hex": "#F5F2E9", "name": "Background"},
        },
        "typography": {"feel": "clear", "weight": "bold", "sizing": "mobile-readable"},
        "stylization_level": "mixed",
        "blend_rules": {
            "real_anchors": ["operator-supplied footage"],
            "generated_supporting": ["conceptual visuals"],
            "disclosure": ["disclose generated primary visuals"],
        },
        "platform_adjustments": [{"platform": "Instagram", "aspect_ratio": "9:16", "notes": "portrait"}],
        "summary": "A visual identity with versioned treatments.",
        "visual_treatments": treatments,
    }


def treatment(treatment_id, version, status, style):
    return {
        "treatment_id": treatment_id,
        "version": version,
        "description": f"{style} treatment",
        "reference_set": [{"ref_id": f"ref:{treatment_id}:01", "role": "canonical", "status": "approved"}],
        "palette": {"allowed_colors": ["#111111", "#F5F2E9"], "prohibited_colors": ["#FF00FF"]},
        "line_texture_lighting": {
            "line_rule": "declared line treatment",
            "texture_rule": "declared texture treatment",
            "lighting_rule": "declared lighting treatment",
        },
        "prohibited_characteristics": ["unapproved mixed world layers"],
        "allowed_formats": ["reel", "carousel"],
        "continuity": {
            "character": "same treatment for recurring characters",
            "location": "same treatment for recurring locations",
            "world_subjects": "one treatment governs Tier-1 world subjects",
        },
        "tier1_generation_rules": ["use the declared treatment for every generated world subject"],
        "tier2_overlay_relationship": "Tier-2 overlays remain deterministic and disclosed as required.",
        "disclosure_requirements": ["disclose generated visuals when primary"],
        "status": status,
        "provenance": {"source": "operator proposal", "record": "fixture"},
    }


def test_visual_treatment_schema_accepts_coexisting_fixtures():
    cinematic = treatment("cinematic_painted", "2.0", "approved", "cinematic")
    vector = treatment("flat_vector_pennifold", "1.0", "proposed", "flat vector")
    style = validate_llm_output(json.dumps(base_style([cinematic, vector])), VISUAL_STYLE_SCHEMA, context="test")
    assert [item["treatment_id"] for item in style["visual_treatments"]] == [
        "cinematic_painted", "flat_vector_pennifold"
    ]


def test_visual_treatment_schema_fails_closed_on_missing_continuity():
    candidate = treatment("flat_vector_pennifold", "1.0", "proposed", "flat vector")
    del candidate["continuity"]
    with pytest.raises(ValidationError, match="continuity"):
        validate_llm_output(json.dumps(candidate), VISUAL_TREATMENT_SCHEMA, context="test")


def test_visual_style_round_trip_preserves_treatments_exactly():
    style = base_style([
        treatment("cinematic_painted", "2.0", "approved", "cinematic"),
        treatment("flat_vector_pennifold", "1.0", "proposed", "flat vector"),
    ])
    markdown = visual_style_to_markdown(style, version="2.0")
    restored = parse_visual_style_markdown(markdown)
    assert restored == style
    assert "Schema: visual_style_v2" in markdown
    assert "flat_vector_pennifold" in markdown
    assert "prohibited_characteristics" in markdown


def test_visual_style_v1_remains_backward_compatible():
    style = copy.deepcopy(base_style([]))
    style.pop("visual_treatments")
    markdown = visual_style_to_markdown(style, version="1.0")
    restored = parse_visual_style_markdown(markdown)
    assert restored == style
    assert "Schema: visual_style_v1" in markdown


def test_visual_treatment_gate_page_and_proposal_api(tmp_path):
    from app import create_app

    app = create_app(config_dir="config", db_path=str(tmp_path / "gate.db"))
    app.config.update(TESTING=True)
    client = app.test_client()
    candidate = treatment("flat_vector_pennifold", "1.0", "proposed", "flat vector")
    response = client.post(
        "/api/visual-treatments/proposals",
        json={
            "treatment": candidate,
            "reference_candidates": [{"ref_id": "asset:comparison:room", "status": "proposed", "evidence": ["palette report"]}],
            "evidence": ["operator comparison set"],
            "rationale": "Review a separate treatment without replacing the cinematic treatment.",
        },
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "pending"
    assert payload["reference_candidates"][0]["status"] == "proposed"
    assert "flat_vector_pennifold" in payload["diff"]

    page = client.get("/visual-treatments")
    assert page.status_code == 200
    body = page.get_data(as_text=True)
    assert "Visual Treatment Gate" in body
    assert "flat_vector_pennifold" in body
    assert "Reference candidates" in body
    assert "/api/proposals/" in body


def test_visual_treatment_proposal_rejects_approved_candidate(tmp_path):
    from app import create_app

    app = create_app(config_dir="config", db_path=str(tmp_path / "gate.db"))
    response = app.test_client().post(
        "/api/visual-treatments/proposals",
        json={"treatment": treatment("bad", "1.0", "approved", "bad")},
    )
    assert response.status_code == 400
    assert "proposed" in response.get_json()["error"]
