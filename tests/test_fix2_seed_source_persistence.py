"""
FIX-2: Seed source persistence tests.

When the Sources Engine gate is approved, the seed sources from
collected_inputs.seed_sources must be persisted into the sources table.
Previously, seeds were analyzed to produce the Source Criteria module but
the individual seed sources were discarded — the bank stayed empty.
"""
import json
import os
import tempfile
import sqlite3
import pytest
import yaml

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from playbook_runner import PlaybookRunner
from module_store import (
    SOURCE_CRITERIA_SCHEMA,
    source_criteria_to_markdown, monitoring_plan_to_yaml,
    generate_gate_token,
)


@pytest.fixture
def tmp_dirs():
    """Temporary config + modules + db with valid business config."""
    with tempfile.TemporaryDirectory() as config_dir:
        with tempfile.TemporaryDirectory() as modules_dir:
            with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
                db_path = f.name
            os.unlink(db_path)

            business = {
                "business": {"name": "Test", "slug": "test-biz", "description": "Test biz"},
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


def _valid_criteria():
    """Minimal valid source criteria JSON matching SOURCE_CRITERIA_SCHEMA."""
    return {
        "subjects_covered": [
            {"subject": "AI", "evidence": ["TechCrunch"]},
        ],
        "formats_favored": [
            {"format": "long-form articles", "evidence": ["Stratechery"]},
        ],
        "freshness": {
            "expectation": "Within 6 months",
            "evidence": ["Stratechery"],
        },
        "quality_signals": [
            {"signal": "original data", "description": "Has proprietary research",
             "evidence": ["Stratechery"]},
        ],
        "disqualifiers": [
            {"disqualifier": "content-mill SEO", "evidence": ["anti-example"]},
        ],
        "regional_relevance": {
            "requirement": "Global is fine",
            "evidence": ["Stratechery covers global tech"],
        },
        "monitoring_plan": {
            "feeds": [
                {"name": "TechCrunch AI", "url": "https://techcrunch.com/feed/",
                 "type": "rss", "enabled": True},
            ],
            "channels": [],
            "queries": [],
        },
        "criteria_summary": "Good sources cover AI with original data.",
    }


class TestSeedSourcePersistence:
    """FIX-2: Seed sources are persisted into the sources table on gate approval."""

    def test_approved_gate_persists_seeds(self, tmp_dirs, monkeypatch):
        """When the gate is approved, seed_sources are written to the sources table."""
        config_dir, modules_dir, db_path = tmp_dirs

        from app import create_app
        # ModuleStore uses "modules" as a relative path — chdir to tmp
        monkeypatch.chdir(modules_dir)
        app = create_app(
            config_dir=config_dir,
            db_path=db_path,
            playbooks_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks")),
        )

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("sources-engine", "1.0", "test-biz")

        # Set seed sources in collected_inputs
        seeds = [
            {"url": "https://example.com/feed1", "name": "Source A", "type": "rss"},
            {"url": "https://example.com/feed2", "name": "Source B", "type": "web"},
            {"url": "https://youtube.com/@channel", "name": "Channel X", "type": "youtube"},
        ]
        runner.update_run(run_id, collected_inputs=json.dumps({"seed_sources": seeds}))

        # Set LLM output (criteria)
        criteria = _valid_criteria()
        runner.add_llm_output(run_id, "criteria", criteria)

        client = app.test_client()
        resp = client.post(f"/api/run/{run_id}/store-sources",
                           json={"approved": True, "version": "1.0", "note": "test"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["approved"] is True
        assert data.get("paths", {}).get("seed_sources_persisted") == 3

        # Verify sources are in the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM sources WHERE business_slug = ? ORDER BY id",
            ("test-biz",),
        ).fetchall()
        conn.close()

        assert len(rows) == 3
        titles = {r["title"] for r in rows}
        assert titles == {"Source A", "Source B", "Channel X"}
        # All should be active (operator-approved seeds)
        assert all(r["status"] == "active" for r in rows)
        # All should have origin='operator'
        assert all(r["origin"] == "operator" for r in rows)

    def test_parked_gate_does_not_persist_seeds(self, tmp_dirs, monkeypatch):
        """When the gate is parked (not approved), seed_sources are NOT written."""
        config_dir, modules_dir, db_path = tmp_dirs

        from app import create_app
        monkeypatch.chdir(modules_dir)
        app = create_app(
            config_dir=config_dir,
            db_path=db_path,
            playbooks_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks")),
        )

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("sources-engine", "1.0", "test-biz")

        seeds = [
            {"url": "https://example.com/feed1", "name": "Source A", "type": "rss"},
        ]
        runner.update_run(run_id, collected_inputs=json.dumps({"seed_sources": seeds}))
        runner.add_llm_output(run_id, "criteria", _valid_criteria())

        client = app.test_client()
        resp = client.post(f"/api/run/{run_id}/store-sources",
                           json={"approved": False, "version": "1.0", "note": "park"})
        assert resp.status_code == 200

        # No sources should be in the database
        from pipeline import PipelineStore
        store = PipelineStore(db_path=db_path)
        store._init_db()
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sources WHERE business_slug = ?", ("test-biz",)).fetchone()[0]
        conn.close()
        assert count == 0

    def test_seed_dedup_on_reapprove(self, tmp_dirs, monkeypatch):
        """Re-approving the same run doesn't duplicate seed sources."""
        config_dir, modules_dir, db_path = tmp_dirs

        from app import create_app
        monkeypatch.chdir(modules_dir)
        app = create_app(
            config_dir=config_dir,
            db_path=db_path,
            playbooks_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks")),
        )

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("sources-engine", "1.0", "test-biz")

        seeds = [
            {"url": "https://example.com/feed1", "name": "Source A", "type": "rss"},
            {"url": "https://example.com/feed2", "name": "Source B", "type": "web"},
        ]
        runner.update_run(run_id, collected_inputs=json.dumps({"seed_sources": seeds}))
        runner.add_llm_output(run_id, "criteria", _valid_criteria())

        client = app.test_client()
        # First approval
        resp1 = client.post(f"/api/run/{run_id}/store-sources",
                            json={"approved": True, "version": "1.0", "note": "first"})
        assert resp1.status_code == 200

        # Second approval (re-approve same run)
        resp2 = client.post(f"/api/run/{run_id}/store-sources",
                            json={"approved": True, "version": "1.0", "note": "second"})
        assert resp2.status_code == 200

        # Should still only have 2 sources (deduped by content_hash)
        conn = sqlite3.connect(db_path)
        count = conn.execute("SELECT COUNT(*) FROM sources WHERE business_slug = ?", ("test-biz",)).fetchone()[0]
        conn.close()
        assert count == 2

    def test_no_seed_sources_no_error(self, tmp_dirs, monkeypatch):
        """Approving with zero seed sources doesn't error."""
        config_dir, modules_dir, db_path = tmp_dirs

        from app import create_app
        monkeypatch.chdir(modules_dir)
        app = create_app(
            config_dir=config_dir,
            db_path=db_path,
            playbooks_dir=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "playbooks")),
        )

        runner = PlaybookRunner(db_path)
        run_id = runner.start_run("sources-engine", "1.0", "test-biz")

        # No seed_sources in collected_inputs
        runner.update_run(run_id, collected_inputs=json.dumps({}))
        runner.add_llm_output(run_id, "criteria", _valid_criteria())

        client = app.test_client()
        resp = client.post(f"/api/run/{run_id}/store-sources",
                           json={"approved": True, "version": "1.0", "note": "no seeds"})
        assert resp.status_code == 200
        # seed_sources_persisted should be 0 or absent
        data = resp.get_json()
        assert data.get("paths", {}).get("seed_sources_persisted", 0) == 0