"""P0-1 — governance documents must be visible at the module review gate."""

import sqlite3


def test_library_shows_pending_reference_governance_document(tmp_path):
    """A DRAFT canon outside modules/ is still surfaced for operator review."""
    from app import create_app

    app = create_app(config_dir="config", db_path=str(tmp_path / "library.db"))
    app.config["TESTING"] = True

    response = app.test_client().get("/library")

    assert response.status_code == 200
    assert b"World Canon" in response.data
    assert b"DRAFT" in response.data
    assert b"Awaiting operator decision" in response.data


def test_governance_gate_records_operator_decision_without_applying_document(tmp_path):
    """Approval is auditable and never silently applies a proposed document."""
    from app import create_app

    db_path = tmp_path / "library.db"
    app = create_app(config_dir="config", db_path=str(db_path))
    app.config["TESTING"] = True

    response = app.test_client().post(
        "/api/governance-documents/decision",
        json={
            "path": "assets/reference/stackpenni/grade_token/world_canon.md",
            "decision": "approve",
            "notes": "Ready for episode work.",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT decision, notes FROM governance_document_decisions"
    ).fetchone()
    conn.close()
    assert row == ("approve", "Ready for episode work.")
