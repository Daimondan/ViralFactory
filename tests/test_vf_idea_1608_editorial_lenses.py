"""VF-IDEA-1608: tenant-owned editorial lens catalogue and persistence."""

import json
import os
import sqlite3
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from editorial_lenses import load_lens_catalogue, validate_editorial_fit, editorial_fit_label
from pipeline import PipelineStore


def _config(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "editorial_lenses.yaml").write_text(
        yaml.safe_dump(
            {
                "catalogues": {
                    "tenant_a": {"lenses": [{"id": "policy", "label": "Policy"}]},
                    "tenant_b": {"lenses": [{"id": "culture", "label": "Culture"}]},
                }
            }
        )
    )
    return config_dir


def test_lens_catalogue_is_tenant_config_not_python_logic(tmp_path):
    config_dir = _config(tmp_path)
    assert load_lens_catalogue("tenant_a", str(config_dir))[0]["id"] == "policy"
    assert load_lens_catalogue("tenant_b", str(config_dir))[0]["id"] == "culture"


def test_editorial_fit_accepts_only_configured_lens_ids(tmp_path):
    config_dir = _config(tmp_path)
    fit = {"lens_id": "policy", "status": "supported", "evidence": ["source 1"]}
    assert validate_editorial_fit(fit, "tenant_a", str(config_dir)) == fit
    with pytest.raises(ValueError, match="lens"):
        validate_editorial_fit({"lens_id": "culture", "status": "supported"}, "tenant_a", str(config_dir))


def test_legacy_editorial_fit_is_not_recorded(tmp_path):
    assert editorial_fit_label(None) == "Not recorded"


def test_editorial_fit_round_trips_on_idea_card(tmp_path):
    store = PipelineStore(db_path=str(tmp_path / "pipeline.db"))
    fit = {"lens_id": "policy", "status": "supported", "evidence": ["source 1"]}
    card_id = store.create_idea_card(
        "tenant_a", "An idea", ["Hook"],
        {"scope": {"type": "one_off"}, "format": {}, "capture_required": [], "rationale": "r"},
        "ai_originated", [], source_refs=[], editorial_fit=fit,
    )
    card = store.get_idea_card(card_id)
    assert json.loads(card["editorial_fit"]) == fit


def test_existing_database_migration_adds_nullable_editorial_fit(tmp_path):
    store = PipelineStore(db_path=str(tmp_path / "pipeline.db"))
    conn = sqlite3.connect(str(tmp_path / "pipeline.db"))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(idea_cards)").fetchall()}
    conn.close()
    assert "editorial_fit" in columns
    assert "editorial_fit_provenance" in columns
