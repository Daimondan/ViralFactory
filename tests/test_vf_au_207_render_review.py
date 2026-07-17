"""Tests for VF-AU-207: Render/review service."""

import os, pytest, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from services.render_review import RenderReviewService, RenderResult, ReviewResult, FullRenderReviewResult


class FakeRenderer:
    """Fake renderer for testing."""
    def __init__(self, output_path="", fail=False, zero_byte=False):
        self.output_path = output_path
        self.fail = fail
        self.zero_byte = zero_byte

    def render(self, **kwargs):
        if self.fail:
            raise Exception("Render failed")
        if self.zero_byte:
            path = self.output_path or "/tmp/zero_byte.mp4"
            with open(path, "w") as f: f.write("")
            return {"path": path, "duration": 0, "render_time_s": 1.0, "version": 1}
        # Create a real file
        path = self.output_path or "/tmp/test_output.mp4"
        with open(path, "wb") as f: f.write(b"\x00" * 5000)
        return {"path": path, "duration": 5.0, "render_time_s": 2.0, "version": 1, "cut_list": []}


class FakeReviewer:
    """Fake reviewer for testing."""
    def __init__(self, verdict="compliant", summary="All good"):
        self.verdict = verdict
        self.summary = summary

    def review_render(self, *args, **kwargs):
        return {"verdict": self.verdict, "summary": self.summary, "findings": {"warnings": []}}


class TestRender:
    def test_successful_render(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(renderer=FakeRenderer(output_path=out))
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert result.render.success
        assert result.render.output_path == out

    def test_zero_byte_output_detected_and_deleted(self, tmp_path):
        out = str(tmp_path / "zero.mp4")
        svc = RenderReviewService(renderer=FakeRenderer(output_path=out, zero_byte=True))
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert not result.render.success
        assert "0-byte" in result.render.error
        assert not os.path.exists(out)  # file should be deleted

    def test_missing_output_detected(self):
        svc = RenderReviewService(renderer=FakeRenderer(output_path="/nonexistent/path.mp4"))
        # FakeRenderer creates the file, but if path doesn't exist after, it's caught
        # Let's use a renderer that returns a path to a nonexistent file
        class BadRenderer:
            def render(self, **kwargs):
                return {"path": "/nonexistent/output.mp4", "duration": 5, "render_time_s": 1, "version": 1}
        svc = RenderReviewService(renderer=BadRenderer())
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert not result.render.success
        assert "no output" in result.render.error.lower()

    def test_render_exception_handled(self):
        svc = RenderReviewService(renderer=FakeRenderer(fail=True))
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert not result.render.success
        assert "Render failed" in result.render.error

    def test_no_renderer_configured(self):
        svc = RenderReviewService()
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert not result.render.success
        assert "No renderer" in result.render.error


class TestReview:
    def test_compliant_review_sets_ready_for_gate3(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(
            renderer=FakeRenderer(output_path=out),
            reviewer=FakeReviewer(verdict="compliant"),
        )
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert result.review.verdict == "compliant"
        assert result.ready_for_gate3

    def test_non_compliant_review_blocks_gate3(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(
            renderer=FakeRenderer(output_path=out),
            reviewer=FakeReviewer(verdict="needs_operator_decision"),
        )
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert not result.ready_for_gate3

    def test_no_reviewer_keeps_pending(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(renderer=FakeRenderer(output_path=out))
        result = svc.render_and_review(plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1)
        assert result.review.verdict == "pending"
        assert not result.ready_for_gate3


class TestRemediationLoop:
    def test_compliant_first_round_stops(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(
            renderer=FakeRenderer(output_path=out),
            reviewer=FakeReviewer(verdict="compliant"),
        )
        result = svc.run_remediation_loop(
            plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1,
            max_rounds=3, max_cost_usd=5.0,
        )
        assert result.ready_for_gate3
        assert len(result.remediation_history) == 1

    def test_non_convergent_after_max_rounds(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(
            renderer=FakeRenderer(output_path=out),
            reviewer=FakeReviewer(verdict="rerender"),  # always needs rerender
        )
        result = svc.run_remediation_loop(
            plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1,
            max_rounds=3, max_cost_usd=100.0,
        )
        assert not result.ready_for_gate3
        assert result.review.verdict == "needs_operator_decision"
        assert "Non-convergent" in result.review.summary
        assert len(result.remediation_history) == 3

    def test_needs_operator_stops_immediately(self, tmp_path):
        out = str(tmp_path / "output.mp4")
        svc = RenderReviewService(
            renderer=FakeRenderer(output_path=out),
            reviewer=FakeReviewer(verdict="needs_operator_decision"),
        )
        result = svc.run_remediation_loop(
            plan={}, asset_id=1, draft_id=1, business_slug="test", plan_id=1,
            max_rounds=3, max_cost_usd=100.0,
        )
        assert not result.ready_for_gate3
        assert len(result.remediation_history) == 1