"""VF-VS-601 — Skipped evidence blocks readiness.

AC: skipped visual/transcript creates saved row and blocks readiness.
"""

import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from asset_review import AssetReviewer


@pytest.fixture
def reviewer(tmp_path):
    return AssetReviewer(models_config={}, db_path=str(tmp_path / "test_review.db"))


def test_skipped_visual_blocks_ready_for_operator(reviewer):
    """Skipped visual inspection → needs_operator_decision, not ready_for_operator."""
    result = reviewer.run_content_alignment(
        asset_id=1, media_id=1,
        mechanical={"verdict": "pass", "warnings": []},
        visual={"status": "skipped", "verdict": "skipped", "summary": "Vision model not configured"},
        audio={"status": "complete", "verdict": "pass"},
        business_slug="test",
        asset_content="Some content",
        asset_posts="",
    )
    assert result["verdict"] != "ready_for_operator"
    assert result["verdict"] == "needs_operator_decision" or result["verdict"] == "needs_rerender"
    # The skipped evidence is visible in the findings
    findings = result.get("findings", {})
    skipped_issues = [i for i in findings.get("issues", []) if "skipped" in i.get("description", "").lower()]
    assert len(skipped_issues) > 0


def test_skipped_audio_blocks_ready_for_operator(reviewer):
    """Skipped audio inspection → needs_operator_decision."""
    result = reviewer.run_content_alignment(
        asset_id=1, media_id=1,
        mechanical={"verdict": "pass", "warnings": []},
        visual={"status": "complete", "verdict": "pass"},
        audio={"status": "skipped", "verdict": "skipped", "summary": "Audio probe failed"},
        business_slug="test",
        asset_content="Some content",
        asset_posts="",
    )
    assert result["verdict"] != "ready_for_operator"
    findings = result.get("findings", {})
    skipped_issues = [i for i in findings.get("issues", []) if "skipped" in i.get("description", "").lower()]
    assert len(skipped_issues) > 0


def test_both_skipped_blocks_ready_for_operator(reviewer):
    """Both visual and audio skipped → needs_operator_decision with both issues."""
    result = reviewer.run_content_alignment(
        asset_id=1, media_id=1,
        mechanical={"verdict": "pass", "warnings": []},
        visual={"status": "skipped", "verdict": "skipped", "summary": "Vision model not configured"},
        audio={"status": "skipped", "verdict": "skipped", "summary": "Audio probe failed"},
        business_slug="test",
        asset_content="Some content",
        asset_posts="",
    )
    assert result["verdict"] != "ready_for_operator"
    findings = result.get("findings", {})
    skipped_issues = [i for i in findings.get("issues", []) if "skipped" in i.get("description", "").lower()]
    assert len(skipped_issues) >= 2  # both visual and audio


def test_complete_pass_still_ready_for_operator(reviewer):
    """When nothing is skipped and all pass → ready_for_operator (no regression)."""
    result = reviewer.run_content_alignment(
        asset_id=1, media_id=1,
        mechanical={"verdict": "pass", "warnings": []},
        visual={"status": "complete", "verdict": "pass"},
        audio={"status": "complete", "verdict": "pass"},
        business_slug="test",
        asset_content="Some content",
        asset_posts="",
    )
    assert result["verdict"] == "ready_for_operator"


def test_skipped_evidence_saved_to_db(reviewer):
    """AC: skipped creates a saved evidence row."""
    result = reviewer.run_content_alignment(
        asset_id=1, media_id=1,
        mechanical={"verdict": "pass", "warnings": []},
        visual={"status": "skipped", "verdict": "skipped", "summary": "Vision model not configured"},
        audio={"status": "complete", "verdict": "pass"},
        business_slug="test",
        asset_content="Some content",
        asset_posts="",
    )
    assert result.get("review_id")  # a review row was saved
    # Verify the review row exists in the DB
    import sqlite3
    conn = sqlite3.connect(reviewer.db_path)
    row = conn.execute(
        "SELECT verdict FROM asset_reviews WHERE id = ?",
        (result["review_id"],),
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] != "ready_for_operator"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))