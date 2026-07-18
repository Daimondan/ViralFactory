"""Regression: three operator-reported bugs in the Writer surface state machine.

1. Approving an idea didn't bump the Drafting counter — the Writer page's
   Drafting tab counts ready_review + writing + queued, but
   `_writer_display_state` mapped neither `approved` nor `capture_fulfilled`
   to `queued` — they fell through to `return cs`, producing raw-state badges
   that the counter doesn't sum.

2. A draft stuck in `draft_state='drafting'` with `card_state='writer_failed'`
   showed the spinning "Writer is working" panel forever — draft.html only
   inspected `draft_state`, not `card_state`, so a failed mid-draft chain
   looked indistinguishable from an in-progress chain.

3. While the writer chain was running (card_state='writing', no draft row
   yet), the draft page rendered the "No draft yet — Generate draft" button.
   Clicking it hit /api/draft/<id>/generate, whose guard rejects `writing`
   ("Card state is 'writing' — must be approved or capture_fulfilled to
   draft").
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _make_app(tmp_path, monkeypatch):
    """Build a Flask app wired to a throwaway DB + the stackpenni config."""
    from app import create_app
    db_path = str(tmp_path / "test.db")
    # Force the stackpenni business slug on by pointing at the real config dir.
    app = create_app(config_dir="config", db_path=db_path)
    return app, db_path


def _seed_card(store, slug="stackpenni", state="approved"):
    return store.create_idea_card(
        business_slug=slug,
        idea="Test idea for state mapping",
        hook_options=[],
        treatment={"format": {"format_name": "Instagram Reel Script"}},
        origin="test",
        _state=state,
    ) if hasattr(store.create_idea_card, "_state") else store.create_idea_card(
        business_slug=slug,
        idea="Test idea for state mapping",
        hook_options=[],
        treatment={"format": {"format_name": "Instagram Reel Script"}},
        origin="test",
    )


class TestWriterDisplayStateMapping:
    """Bug 1: approved / capture_fulfilled / awaiting_capture → 'queued'."""

    def test_approved_maps_to_queued(self, tmp_path):
        from app import create_app
        from pipeline import PipelineStore
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Approved idea",
            hook_options=[],
            treatment={},
            origin="test",
        )
        store.update_card_state(card_id, "approved")
        card = store.get_idea_card(card_id)
        # _writer_display_state is a closure inside create_app; reach it via
        # the rendered /create page and inspect state_counts. The Drafting tab
        # counter sums ready_review + writing + queued — an approved card must
        # land in `queued` so the counter reflects it.
        client = app.test_client()
        resp = client.get("/create")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # The Queued section header includes a count; approved card should be
        # listed under "Queued for Writer".
        assert "Queued for Writer" in body
        assert "Approved idea" in body

    def test_capture_fulfilled_maps_to_queued(self, tmp_path):
        from app import create_app
        from pipeline import PipelineStore
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Capture-fulfilled idea",
            hook_options=[],
            treatment={},
            origin="test",
        )
        store.update_card_state(card_id, "capture_fulfilled")
        client = app.test_client()
        resp = client.get("/create")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Queued for Writer" in body
        assert "Capture-fulfilled idea" in body

    def test_awaiting_capture_maps_to_queued(self, tmp_path):
        from app import create_app
        from pipeline import PipelineStore
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Awaiting capture idea",
            hook_options=[],
            treatment={},
            origin="test",
        )
        store.update_card_state(card_id, "awaiting_capture")
        client = app.test_client()
        resp = client.get("/create")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Queued for Writer" in body
        assert "Awaiting capture idea" in body


class TestDraftPageFailedState:
    """Bug 2: a draft stuck in 'drafting' with card_state='writer_failed'
    must surface the failure + Retry, not the spinning Writer panel."""

    def test_failed_mid_draft_shows_retry_not_spinner(self, tmp_path):
        from app import create_app
        from pipeline import PipelineStore
        import json
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Failed mid-draft idea",
            hook_options=[],
            treatment={"format": {"format_name": "Instagram Reel Script"}},
            origin="test",
        )
        # create_draft sets draft_state='drafting' and card_state='drafting'
        draft_id = store.create_draft(
            "stackpenni", card_id, "test", format_name="Instagram Reel Script"
        )
        # Simulate the writer chain failing mid-draft: card_state → writer_failed,
        # draft_state stays 'drafting'.
        store.update_card_state(
            card_id, "writer_failed",
            production_error={"step": "draft_generation", "error": "LLM timeout"},
        )
        client = app.test_client()
        resp = client.get(f"/create/draft/{card_id}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Must surface the failure message and Retry button (retryProduction),
        # NOT the "Writer is working — draft not ready" spinner panel.
        assert "Writer failed" in body
        assert "Retry draft" in body
        assert "retryProduction" in body
        # The spinning "Writer is working" panel must not appear for a failed card.
        assert "Writer is working — draft not ready" not in body


class TestDraftPageWritingNoDraftYet:
    """Bug 3: while the writer chain runs (card_state='writing', no draft row
    yet) the draft page must show the spinner, not a Generate button that the
    API will reject."""

    def test_writing_state_shows_spinner_not_generate(self, tmp_path):
        from app import create_app
        from pipeline import PipelineStore
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Writing-in-progress idea",
            hook_options=[],
            treatment={"format": {"format_name": "Instagram Reel Script"}},
            origin="test",
        )
        # No draft row created yet — the LLM call is in flight.
        store.update_card_state(card_id, "writing")
        client = app.test_client()
        resp = client.get(f"/create/draft/{card_id}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        # Spinner panel, not the Generate draft button.
        assert "Writer is working" in body
        assert "draft not ready" in body
        # The bare "No draft yet. Click generate" panel must NOT appear while
        # the writer chain is running.
        assert "No draft yet" not in body

    def test_writing_state_generate_api_rejects(self, tmp_path):
        """The API guard at /api/draft/<id>/generate must reject 'writing' —
        this is the error the operator hit. Confirms the guard is the reason
        the UI must not offer the button during 'writing'."""
        from app import create_app
        from pipeline import PipelineStore
        db_path = str(tmp_path / "test.db")
        app = create_app(config_dir="config", db_path=db_path)
        store = PipelineStore(db_path)
        card_id = store.create_idea_card(
            business_slug="stackpenni",
            idea="Writing-in-progress idea",
            hook_options=[],
            treatment={"format": {"format_name": "Instagram Reel Script"}},
            origin="test",
        )
        store.update_card_state(card_id, "writing")
        client = app.test_client()
        resp = client.post(f"/api/draft/{card_id}/generate", json={})
        assert resp.status_code == 400
        data = resp.get_json()
        assert "writing" in data["error"]