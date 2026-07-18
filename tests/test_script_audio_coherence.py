"""Tests for script↔audio coherence and LLM-based content alignment.

FIX-1: Audio inspection cross-references the script — if it has VO/dialogue
but the plan has no take_id and no music, flag as a silent failure.

FIX-2: Content alignment uses an LLM to judge coherence (script vs plan vs
output), not just dumb aggregation. Falls back to mechanical aggregation
with the script-audio coherence check if LLM is unavailable.
"""

import json
import os
import subprocess
import sqlite3
import sys
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from asset_review import AssetReviewer


def _make_silent_video(path, duration=3):
    """Create a video with silent audio track."""
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
         "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100",
         "-t", str(duration),
         "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", path],
        capture_output=True, timeout=30,
    )
    return path


class TestScriptVODetection:
    """Test _script_has_vo_or_dialogue — T10.8: contract-based, not keyword-based.

    The keyword heuristic is RETIRED as a compliance decision (AMENDMENT-008).
    The function now checks the compliance contract for spoken_dialogue beats.
    Without a contract, it returns False (no compliance decision from keywords).
    """

    def test_contract_with_spoken_dialogue_detected(self, tmp_path):
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        contract = {"beats": [
            {"beat_id": "b1", "requirement_type": "spoken_dialogue", "required": True},
        ]}
        assert reviewer._script_has_vo_or_dialogue(
            "any content", compliance_contract=contract,
        ) is True

    def test_contract_without_spoken_dialogue_not_detected(self, tmp_path):
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        contract = {"beats": [
            {"beat_id": "b1", "requirement_type": "caption_text", "required": True},
        ]}
        assert reviewer._script_has_vo_or_dialogue(
            "any content", compliance_contract=contract,
        ) is False

    def test_no_contract_returns_false(self, tmp_path):
        """T10.8: Without a compliance contract, no keyword-based decision."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        assert reviewer._script_has_vo_or_dialogue(
            "Script with VO: 'Your grandmother kept cash in a biscuit tin'",
        ) is False

    def test_no_contract_empty_content(self, tmp_path):
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        assert reviewer._script_has_vo_or_dialogue("") is False
        assert reviewer._script_has_vo_or_dialogue(None) is False

    def test_contract_with_duration_fit_detected(self, tmp_path):
        """Duration fit beats may imply VO content."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        contract = {"beats": [
            {"beat_id": "b1", "requirement_type": "duration_fit", "required": True},
        ]}
        assert reviewer._script_has_vo_or_dialogue(
            "any content", compliance_contract=contract,
        ) is True

    def test_contract_with_optional_beats_not_detected(self, tmp_path):
        """Optional spoken_dialogue beats (required=false) don't trigger."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        contract = {"beats": [
            {"beat_id": "b1", "requirement_type": "spoken_dialogue", "required": False},
        ]}
        assert reviewer._script_has_vo_or_dialogue(
            "any content", compliance_contract=contract,
        ) is False


class TestAudioInspectionScriptCoherence:
    """FIX-1: Audio inspection flags silent output when script has VO.

    T10.8: The script-VO coherence check now uses the compliance contract,
    not keyword matching. Tests pass a contract with spoken_dialogue beats
    to trigger the coherence warning.
    """

    def _vo_contract(self):
        """A compliance contract with spoken_dialogue beats."""
        return {"beats": [
            {"beat_id": "b1", "requirement_type": "spoken_dialogue", "required": True,
             "source_excerpt": "Your grandmother kept cash in a biscuit tin",
             "planned_segment_ids": ["seg_0"], "verification_method": "audio_transcript_match"},
        ]}

    def test_silent_video_with_vo_contract_flagged(self, tmp_path):
        """Silent output + contract has spoken_dialogue + no take_id + no music → issues_found."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        plan = {
            "audio": {
                "original_audio": False,
                "music": {},
                "vo": {"take_id": "", "ducking": True},
            },
        }
        content = "Reel about biscuit tins"
        posts = json.dumps([
            "[FRAME 1]\nVO: \"Your grandmother kept cash in a biscuit tin\"",
            "[FRAME 2]\nVO: \"Growing up, saving meant one thing\"",
        ])

        result = reviewer.run_audio_inspection(
            video, plan, asset_id=1, media_id=1,
            asset_content=content, asset_posts=posts,
            compliance_contract=self._vo_contract(),
        )

        assert result["verdict"] == "issues_found"
        assert "silent" in result["summary"].lower()
        assert result["findings"]["script_has_vo"] is True

    def test_silent_video_without_vo_contract_passes(self, tmp_path):
        """Silent output + no VO in contract → passes (silent as specified)."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        plan = {
            "audio": {"original_audio": False, "music": {}, "vo": {}},
        }
        content = "A carousel about Caribbean financial decisions. No audio needed."
        posts = json.dumps(["Slide 1: Wedding rings", "Slide 2: Money scripts"])

        result = reviewer.run_audio_inspection(
            video, plan, asset_id=1, media_id=1,
            asset_content=content, asset_posts=posts,
        )

        assert result["verdict"] == "pass"
        assert "silent as specified" in result["summary"]

    def test_silent_video_with_vo_take_in_plan_is_flagged(self, tmp_path):
        """A referenced VO take makes sound mandatory in the final output."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        plan = {
            "audio": {
                "original_audio": False,
                "music": {},
                "vo": {"take_id": "vo_take_1", "ducking": True},
            },
        }
        content = "Reel about biscuit tins"
        posts = json.dumps(["[FRAME 1]\nVO: \"Your grandmother kept cash\""])

        result = reviewer.run_audio_inspection(
            video, plan, asset_id=1, media_id=1,
            asset_content=content, asset_posts=posts,
            compliance_contract=self._vo_contract(),
        )

        assert result["verdict"] == "issues_found"
        assert "expects audio" in result["summary"]

    def test_silent_video_with_music_in_plan_not_flagged_for_vo(self, tmp_path):
        """Silent output + contract has spoken_dialogue + plan has music ref → flagged as
        'plan expects audio but silent', NOT as 'script has VO but no audio plan'."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        plan = {
            "audio": {
                "original_audio": False,
                "music": {"stock_ref": "stock:123", "volume": 0.3},
                "vo": {"take_id": "", "ducking": True},
            },
        }
        content = "Reel about biscuit tins"
        posts = json.dumps(["[FRAME 1]\nVO: \"Your grandmother kept cash\""])

        result = reviewer.run_audio_inspection(
            video, plan, asset_id=1, media_id=1,
            asset_content=content, asset_posts=posts,
            compliance_contract=self._vo_contract(),
        )

        # Should be issues_found (silent when music expected) but NOT the
        # script-VO coherence warning (music ref means plan had an audio strategy)
        assert result["verdict"] == "issues_found"
        assert "Plan expects audio but output is silent" in result["summary"]
        # Should NOT have the script_has_vo coherence flag
        assert not result["findings"].get("script_has_vo")

    def test_provenance_logged_for_script_coherence_flag(self, tmp_path):
        """Script-audio coherence flag should be logged to provenance."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))
        video = _make_silent_video(str(tmp_path / "video.mp4"))

        plan = {"audio": {"original_audio": False, "music": {}, "vo": {"take_id": ""}}}
        content = "Reel about biscuit tins"
        posts = json.dumps(["[FRAME 1]\nVO: \"Your grandmother kept cash\""])

        reviewer.run_audio_inspection(
            video, plan, asset_id=1, media_id=1,
            asset_content=content, asset_posts=posts,
            business_slug="test",
            compliance_contract=self._vo_contract(),
        )

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT raw_output FROM provenance WHERE raw_output LIKE '%issues_found%' "
            "AND raw_output LIKE '%VO%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0


class TestContentAlignmentLLM:
    """FIX-2: Content alignment uses LLM for coherence check."""

    def test_llm_alignment_catches_vo_gap(self, tmp_path, monkeypatch):
        """LLM alignment check should catch script-VO/audio-plan mismatch."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))

        mock_findings = {
            "verdict": "needs_rerender",
            "confidence": "high",
            "issues": [{
                "severity": "high",
                "description": "Script has VO lines but the audio plan has no VO take — output is silent despite dialogue",
                "source": "audio_coherence",
                "recommended_action": "Generate a VO take from the script's VO lines",
            }],
            "summary": "Script contains VO dialogue but output is silent — no audio plan for spoken content",
        }

        with patch.object(reviewer, '_call_vision_model', return_value=mock_findings):
            result = reviewer.run_content_alignment(
                asset_id=1, media_id=1,
                mechanical={"verdict": "pass", "warnings": []},
                visual=None,
                audio={"status": "complete", "verdict": "pass", "findings": {}},
                asset_content="Reel about biscuit tins",
                asset_posts=json.dumps(["[FRAME 1]\nVO: \"Your grandmother kept cash\""]),
                plan={"audio": {"vo": {"take_id": ""}, "music": {}, "original_audio": False}},
            )

        assert result["verdict"] == "needs_rerender"
        assert "silent" in result["summary"].lower() or "VO" in result["summary"]

    def test_fallback_catches_vo_gap_without_llm(self, tmp_path):
        """Fallback aggregation (no LLM) should still catch script-VO gap.

        T10.8: Must pass a compliance contract with spoken_dialogue beats
        for the coherence check to trigger (keyword heuristic retired).
        """
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        vo_contract = {"beats": [
            {"beat_id": "b1", "requirement_type": "spoken_dialogue", "required": True},
        ]}

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
            visual=None,
            audio={"status": "complete", "verdict": "pass", "findings": {}},
            asset_content="Reel about biscuit tins",
            asset_posts=json.dumps(["[FRAME 1]\nVO: \"Your grandmother kept cash\""]),
            plan={"audio": {"vo": {"take_id": ""}, "music": {}, "original_audio": False}},
            compliance_contract=vo_contract,
        )

        assert result["verdict"] == "needs_rerender"
        assert result["findings"]["llm_used"] is False
        # Should have the audio_coherence issue
        coherence_issues = [
            i for i in result["findings"]["issues"]
            if i.get("category") == "audio_coherence"
        ]
        assert len(coherence_issues) == 1

    def test_no_vo_gap_when_script_has_no_vo(self, tmp_path):
        """Fallback should not flag when script has no VO."""
        reviewer = AssetReviewer({}, db_path=str(tmp_path / "test.db"))

        result = reviewer.run_content_alignment(
            asset_id=1, media_id=1,
            mechanical={"verdict": "pass", "warnings": []},
            visual=None,
            audio={"status": "complete", "verdict": "pass", "findings": {}},
            asset_content="A carousel about money. No audio needed.",
            asset_posts=json.dumps(["Slide 1: Wedding rings"]),
            plan={"audio": {"vo": {}, "music": {}, "original_audio": False}},
        )

        assert result["verdict"] == "ready_for_operator"

    def test_llm_alignment_provenance_logged(self, tmp_path, monkeypatch):
        """LLM-based alignment should log to provenance with model + prompt."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))

        with patch.object(reviewer, '_call_vision_model',
                          return_value={"verdict": "ready_for_operator", "issues": [],
                                        "summary": "All good"}):
            reviewer.run_content_alignment(
                asset_id=1, media_id=1,
                asset_content="test content",
                business_slug="test",
            )

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        rows = conn.execute(
            "SELECT * FROM provenance WHERE raw_output LIKE '%Content alignment%'",
        ).fetchall()
        conn.close()
        assert len(rows) > 0

    def test_llm_alignment_saved_to_db(self, tmp_path, monkeypatch):
        """LLM-based alignment should be saved to asset_reviews with model info."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
        config = {"asset_review": {"enabled": True, "vision_model": "test-model"}}
        reviewer = AssetReviewer(config, db_path=str(tmp_path / "test.db"))

        with patch.object(reviewer, '_call_vision_model',
                          return_value={"verdict": "ready_for_operator", "issues": [],
                                        "summary": "All good"}):
            result = reviewer.run_content_alignment(asset_id=1, media_id=1)

        conn = sqlite3.connect(str(tmp_path / "test.db"))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM asset_reviews WHERE review_type = 'alignment'",
        ).fetchone()
        conn.close()
        assert row is not None
        assert row["model"] == "test-model"
        assert row["prompt_file"] == "assembly/asset_alignment_v1.md"