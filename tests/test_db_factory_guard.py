"""Guard test for db.py connection factory migration (P1-5).

Ensures migrated modules use ``db.connect`` and never call
``sqlite3.connect`` directly. Extend the ``migrated`` list in the same
commit that migrates each module — the list is the migration ledger.
"""


def test_no_direct_sqlite_connect_in_migrated_modules():
    """Migrated modules must use db.connect so busy_timeout is never skipped."""
    migrated = [
        # Migration order per P1-5: pipeline.py, app.py, production_orchestrator.py,
        # materials.py, jobs.py, then the remainder.
        "src/pipeline.py",
        "src/materials.py",
        "src/jobs.py",
        "src/services/production_orchestrator.py",
    ]
    for path in migrated:
        import os
        full_path = os.path.join(os.path.dirname(__file__), os.pardir, path)
        source = open(full_path).read()
        assert "sqlite3.connect" not in source, (
            f"{path} still calls sqlite3.connect directly — "
            f"migrate it to use db.connect()"
        )