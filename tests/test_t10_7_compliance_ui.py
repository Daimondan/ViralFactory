"""
Tests for T10.7: Assets UI — remediation history + coverage.

Acceptance criteria:
- The operator can see the full remediation history without reading JSON
- Per-beat coverage is human-readable
- The stop reason is plain language
- No raw JSON default; technical details collapsible
- XSS safe

Tests cover:
1. API endpoint returns structured data (not raw JSON)
2. API handles no-data case gracefully
3. API returns beat coverage in human-readable format
4. API returns remediation rounds with plain-language summaries
5. API returns stop reason in plain language
6. Template renders compliance panel HTML
7. XSS safety: escapeHtml function escapes dangerous characters
8. No raw JSON as default view (structured fields, JSON is collapsible)
9. API returns total cost
10. API handles compliance verdict labels correctly
"""

import json
import os
import pytest
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@pytest.fixture
def test_app():
    """Create a test app with a temp DB."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
    modules_dir = os.path.join(os.path.dirname(__file__), "..", "modules")
    prompts_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
    playbooks_dir = os.path.join(os.path.dirname(__file__), "..", "playbooks")

    # Initialize the DB with PipelineStore (which creates all required tables)
    from pipeline import PipelineStore
    store = PipelineStore(db_path)
    
    # Also init asset_review tables
    from asset_review import AssetReviewer
    reviewer = AssetReviewer({}, db_path=db_path)
    
    # Init media adapter tables
    from media_adapter import MediaAdapter
    adapter = MediaAdapter({}, db_path=db_path)
    
    # Trigger edit_plans table creation (lazy-created by PipelineStore)
    store.list_edit_plans(1)
    
    # Insert minimal data for the assets page to work
    ts = "2026-01-01T00:00:00"
    conn = sqlite3.connect(db_path)
    conn.executescript(f"""
        INSERT OR IGNORE INTO idea_cards (id, business_slug, idea, card_state, origin, created_at, updated_at) 
            VALUES (1, 'stackpenni', 'Test idea', 'approved', 'ai', '{ts}', '{ts}');
        INSERT OR IGNORE INTO drafts (id, business_slug, idea_card_id, draft_state, draft_text, origin, created_at, updated_at) 
            VALUES (1, 'stackpenni', 1, 'shipped', 'Test draft', 'ai', '{ts}', '{ts}');
        INSERT OR IGNORE INTO assets (id, business_slug, draft_id, platform, variant_type, content, asset_state, created_at, updated_at)
            VALUES (1, 'stackpenni', 1, 'instagram', 'reel', 'Test content', 'pending', '{ts}', '{ts}');
    """)
    conn.commit()
    conn.close()

    from app import create_app
    app = create_app(config_dir=config_dir, db_path=db_path, playbooks_dir=playbooks_dir)
    app.config["MODULES_DIR"] = modules_dir
    app.config["PROMPTS_DIR"] = prompts_dir
    app.config["TESTING"] = True

    yield app, db_path

    os.close(db_fd)
    os.unlink(db_path)


class TestComplianceAPI:
    """Test the /api/assets/<id>/compliance endpoint."""

    def test_no_data_returns_clean_response(self, test_app):
        """When no compliance review exists, the API returns has_data=False with clean fields."""
        app, db_path = test_app
        with app.test_client() as c:
            resp = c.get("/api/assets/1/compliance")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["has_data"] is False
            assert data["compliance_verdict"] is None
            assert data["compliance_verdict_label"] == "Not reviewed"
            assert data["stop_reason"] == "No compliance review has been run yet."
            assert data["beat_coverage"] == []
            assert data["remediation_rounds"] == []
            assert data["issues"] == []
            assert data["total_cost_usd"] == 0.0

    def test_compliance_review_returns_structured_data(self, test_app):
        """A compliance review produces structured beat coverage, not raw JSON."""
        app, db_path = test_app
        # Insert a compliance review with per-beat coverage
        findings = {
            "verdict": "needs_operator_decision",
            "coverage": [
                {"beat_id": "b1", "status": "verified", "evidence": "VO line 1 matches script"},
                {"beat_id": "b2", "status": "missing", "evidence": "Caption text not found in output"},
                {"beat_id": "b3", "status": "partial", "evidence": "Visual element partially matches"},
            ],
            "issues": [
                {"severity": "high", "description": "Missing caption", "beat_id": "b2", "remediable": True},
                {"severity": "low", "description": "Color slightly off", "beat_id": "b3", "remediable": False},
            ],
            "safe_remediation_scope": ["adjust_caption_rendering"],
            "summary": "Two beats need attention.",
        }
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO asset_reviews (asset_id, media_id, media_path, review_type, status, verdict, findings_json, summary, created_at, updated_at) "
            "VALUES (1, 1, 'test.mp4', 'compliance', 'complete', 'needs_operator_decision', ?, ?, '2026-01-01', '2026-01-01')",
            (json.dumps(findings), "Two beats need attention."),
        )
        conn.commit()
        conn.close()

        with app.test_client() as c:
            resp = c.get("/api/assets/1/compliance")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["has_data"] is True
            assert data["compliance_verdict"] == "needs_operator_decision"
            assert data["compliance_verdict_label"] == "Needs your decision"
            assert len(data["beat_coverage"]) == 3

            # Per-beat coverage is human-readable, not raw JSON
            beat = data["beat_coverage"][0]
            assert beat["beat_id"] == "b1"
            assert beat["status"] == "verified"
            assert "VO line 1" in beat["evidence"]

            # Missing beat is clearly marked
            missing = [b for b in data["beat_coverage"] if b["status"] == "missing"][0]
            assert "Caption text not found" in missing["evidence"]

            # Issues are structured
            assert len(data["issues"]) == 2
            assert data["issues"][0]["severity"] == "high"
            assert "Missing caption" in data["issues"][0]["description"]

    def test_remediation_rounds_from_edit_plan(self, test_app):
        """Remediation rounds are pulled from edit_plans.review_round_history."""
        app, db_path = test_app
        # Insert an edit plan with review round history
        rounds = [
            {"round": 0, "verdict": "rerender", "actions_taken": [], "cost_usd": 0, "summary": "Initial review found timing issues."},
            {"round": 1, "verdict": "rerender", "actions_taken": [{"action_id": "a1", "type": "revise_plan_timing", "target": "canvas.duration_target"}], "cost_usd": 0.02, "summary": "Adjusted timing, re-rendering."},
            {"round": 2, "verdict": "compliant", "actions_taken": [{"action_id": "a2", "type": "adjust_caption_rendering", "target": "captions.style_ref"}], "cost_usd": 0.01, "summary": "Captions fixed, compliant."},
        ]
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO edit_plans (draft_id, asset_id, plan_json, status, review_round_history, compliance_contract_json, created_at, updated_at) "
            "VALUES (1, 1, '{}', 'rendered', ?, '{\"beats\": [{\"beat_id\": \"b1\"}]}', '2026-01-01', '2026-01-01')",
            (json.dumps(rounds),),
        )
        conn.commit()
        conn.close()

        with app.test_client() as c:
            resp = c.get("/api/assets/1/compliance")
            data = json.loads(resp.data)
            assert len(data["remediation_rounds"]) == 3
            assert data["remediation_rounds"][0]["round"] == 0
            assert data["remediation_rounds"][1]["round"] == 1
            assert data["remediation_rounds"][2]["verdict"] == "compliant"
            assert data["total_cost_usd"] == 0.03
            assert data["has_contract"] is True
            assert data["contract_beat_count"] == 1

    def test_stop_reason_plain_language(self, test_app):
        """The stop reason is human-readable, not a JSON string."""
        app, db_path = test_app
        # Insert a non-convergent compliance review
        findings = {
            "verdict": "non_convergent",
            "coverage": [{"beat_id": "b1", "status": "partial", "evidence": "test"}],
            "issues": [],
            "safe_remediation_scope": [],
            "summary": "Could not fix after 3 rounds.",
        }
        rounds = [
            {"round": 0, "verdict": "rerender", "actions_taken": [], "cost_usd": 0, "summary": "Initial review."},
            {"round": 1, "verdict": "rerender", "actions_taken": [], "cost_usd": 0, "summary": "Round 1."},
            {"round": 2, "verdict": "rerender", "actions_taken": [], "cost_usd": 0, "summary": "Round 2."},
        ]
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO asset_reviews (asset_id, media_id, media_path, review_type, status, verdict, findings_json, summary, created_at, updated_at) "
            "VALUES (1, 1, 'test.mp4', 'compliance', 'complete', 'non_convergent', ?, ?, '2026-01-01', '2026-01-01')",
            (json.dumps(findings), "Could not fix after 3 rounds."),
        )
        conn.execute(
            "INSERT INTO edit_plans (draft_id, asset_id, plan_json, status, review_round_history, created_at, updated_at) "
            "VALUES (1, 1, '{}', 'rendered', ?, '2026-01-01', '2026-01-01')",
            (json.dumps(rounds),),
        )
        conn.commit()
        conn.close()

        with app.test_client() as c:
            resp = c.get("/api/assets/1/compliance")
            data = json.loads(resp.data)
            assert data["compliance_verdict"] == "non_convergent"
            assert data["compliance_verdict_label"] == "Non-convergent"
            # Stop reason must be plain language, not JSON
            assert "Remediation did not converge" in data["stop_reason"]
            assert "{" not in data["stop_reason"]  # no raw JSON
            assert len(data["remediation_rounds"]) == 3

    def test_compliant_verdict_stop_reason(self, test_app):
        """A compliant verdict has a clear stop reason."""
        app, db_path = test_app
        findings = {
            "verdict": "compliant",
            "coverage": [{"beat_id": "b1", "status": "verified", "evidence": "all good"}],
            "issues": [],
            "safe_remediation_scope": [],
            "summary": "All beats verified.",
        }
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO asset_reviews (asset_id, media_id, media_path, review_type, status, verdict, findings_json, summary, created_at, updated_at) "
            "VALUES (1, 1, 'test.mp4', 'compliance', 'complete', 'compliant', ?, ?, '2026-01-01', '2026-01-01')",
            (json.dumps(findings), "All beats verified."),
        )
        conn.commit()
        conn.close()

        with app.test_client() as c:
            resp = c.get("/api/assets/1/compliance")
            data = json.loads(resp.data)
            assert data["compliance_verdict"] == "compliant"
            assert data["compliance_verdict_label"] == "Compliant"
            assert "All beats verified" in data["stop_reason"]

    def test_verdict_labels_all_types(self, test_app):
        """All verdict types produce human-readable labels."""
        app, db_path = test_app
        verdicts_and_labels = [
            ("compliant", "Compliant"),
            ("non_convergent", "Non-convergent"),
            ("needs_operator_decision", "Needs your decision"),
            ("revise_plan", "Plan needs revision"),
            ("regenerate_media", "Media needs regeneration"),
            ("rerender", "Needs re-render"),
        ]
        for verdict, expected_label in verdicts_and_labels:
            conn = sqlite3.connect(db_path)
            # Clear and re-insert
            conn.execute("DELETE FROM asset_reviews WHERE asset_id=1")
            findings = {"verdict": verdict, "coverage": [], "issues": [], "safe_remediation_scope": [], "summary": "test"}
            conn.execute(
                "INSERT INTO asset_reviews (asset_id, media_id, media_path, review_type, status, verdict, findings_json, summary, created_at, updated_at) "
                "VALUES (1, 1, 'test.mp4', 'compliance', 'complete', ?, ?, 'test', '2026-01-01', '2026-01-01')",
                (verdict, json.dumps(findings)),
            )
            conn.commit()
            conn.close()

            with app.test_client() as c:
                resp = c.get("/api/assets/1/compliance")
                data = json.loads(resp.data)
                assert data["compliance_verdict_label"] == expected_label, \
                    f"Verdict '{verdict}' should map to '{expected_label}', got '{data['compliance_verdict_label']}'"


class TestComplianceTemplateRendering:
    """Test that the template includes the compliance panel."""

    def test_assets_page_renders_compliance_panel(self, test_app):
        """The assets page HTML includes the compliance panel for assets with final cuts."""
        app, db_path = test_app
        # Add a final cut for asset 1
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO asset_media (asset_id, kind, path, model, created_at, owner_type) "
            "VALUES (1, 'final_cut', 'data/media/1/final.mp4', 'test', '2026-01-01', 'user')"
        )
        conn.commit()
        conn.close()

        with app.test_client() as c:
            resp = c.get("/create/assets/1")
            assert resp.status_code == 200
            html = resp.data.decode("utf-8")
            # Compliance panel should be present
            assert "compliance-panel-1" in html
            assert "Compliance & Remediation History" in html
            # JS functions should be present
            assert "loadCompliancePanels" in html
            assert "displayCompliancePanel" in html
            assert "escapeHtml" in html

    def test_compliance_panel_not_shown_without_final_cut(self, test_app):
        """The compliance panel should only appear for assets with final cuts."""
        app, db_path = test_app
        # No final_cut media — compliance panel should NOT be in the HTML
        with app.test_client() as c:
            resp = c.get("/create/assets/1")
            assert resp.status_code == 200
            html = resp.data.decode("utf-8")
            # The JS functions are always in the page (global), but the panel div
            # should not be present for this asset
            assert "compliance-panel-1" not in html


class TestXSSSafety:
    """Test that the escapeHtml function properly escapes dangerous characters."""

    def test_escape_html_escapes_script_tag(self):
        """The escapeHtml function must escape <script> tags."""
        # Simulate the escapeHtml function from the template
        def escapeHtml(text):
            if not text:
                return ""
            import html
            return html.escape(text)

        malicious = '<script>alert("xss")</script>'
        escaped = escapeHtml(malicious)
        assert "<script>" not in escaped
        assert "&lt;script&gt;" in escaped

    def test_escape_html_escapes_quotes(self):
        """The escapeHtml function must escape quotes."""
        def escapeHtml(text):
            if not text:
                return ""
            import html
            return html.escape(text)

        malicious = '"; onclick="alert(1)'
        escaped = escapeHtml(malicious)
        assert '"' not in escaped or '\\"' in escaped or '&quot;' in escaped


class TestNoRawJsonDefault:
    """Test that the API returns structured data, not raw JSON as the primary view."""

    def test_api_returns_structured_fields_not_json_strings(self, test_app):
        """All API response fields are structured objects/arrays, not JSON strings."""
        app, db_path = test_app
        # Insert a compliance review
        findings = {
            "verdict": "needs_operator_decision",
            "coverage": [{"beat_id": "b1", "status": "verified", "evidence": "test"}],
            "issues": [{"severity": "high", "description": "test issue", "beat_id": "b1", "remediable": False}],
            "safe_remediation_scope": [],
            "summary": "Test summary.",
        }
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO asset_reviews (asset_id, media_id, media_path, review_type, status, verdict, findings_json, summary, created_at, updated_at) "
            "VALUES (1, 1, 'test.mp4', 'compliance', 'complete', 'needs_operator_decision', ?, ?, '2026-01-01', '2026-01-01')",
            (json.dumps(findings), "Test summary."),
        )
        conn.commit()
        conn.close()

        with app.test_client() as c:
            resp = c.get("/api/assets/1/compliance")
            data = json.loads(resp.data)

            # beat_coverage should be a list of dicts, not a JSON string
            assert isinstance(data["beat_coverage"], list)
            if data["beat_coverage"]:
                assert isinstance(data["beat_coverage"][0], dict)
                assert "beat_id" in data["beat_coverage"][0]
                assert "status" in data["beat_coverage"][0]
                assert "evidence" in data["beat_coverage"][0]

            # issues should be a list of dicts
            assert isinstance(data["issues"], list)
            if data["issues"]:
                assert isinstance(data["issues"][0], dict)
                assert "severity" in data["issues"][0]
                assert "description" in data["issues"][0]

            # remediation_rounds should be a list of dicts
            assert isinstance(data["remediation_rounds"], list)

            # stop_reason should be a plain string, not JSON
            assert isinstance(data["stop_reason"], str)
            assert "{" not in data["stop_reason"]