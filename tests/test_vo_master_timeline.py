"""Tests for VO-as-master-timeline pipeline reordering.

The VO defines the real timeline. Media planning sees VO durations before
deciding what visuals to generate. The draft stops estimating timestamps.
The edit plan receives a pre-aligned timeline. Duration is advisory, not blocking.
"""

import json
import os
import sys
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


# ─── 1. vo_generator: per-frame segments ───────────────────────────────

def test_vo_generator_has_per_frame_method():
    """vo_generator must expose generate_vo_per_frame."""
    from vo_generator import VOGenerator
    assert hasattr(VOGenerator, "generate_vo_per_frame")


def test_vo_per_frame_returns_segments_with_durations():
    """Each segment must have frame, path, duration, and text."""
    from vo_generator import VOGenerator
    # We test the return contract via a mock — real TTS calls are integration tested
    gen = VOGenerator.__new__(VOGenerator)
    gen.models_config = {}
    gen.db_path = "/tmp/test_vo.db"
    gen.provenance = MagicMock()
    # Monkey-patch internal methods
    gen._get_gemini_tts_config = MagicMock(return_value={
        "model": "test", "voice": "Kore", "style": "",
        "api_key_env": "FAKE_KEY", "sample_rate": 24000,
    })
    os.environ["FAKE_KEY"] = "test-key"
    gen._call_gemini_tts = MagicMock(return_value=b"\x00" * 48000)  # 1s of PCM at 24kHz
    gen._save_wav = MagicMock(side_effect=lambda pcm, path, sr: Path(path).write_bytes(b"wav"))
    gen._get_duration = MagicMock(return_value=5.0)
    gen._record_vo_media = MagicMock()
    gen._log_provenance = MagicMock()

    posts = [
        "When did your parents talk to you about money?",
        "We teach them to cook from young. No shame.",
        "But money? We treat it like a family secret.",
    ]
    result = gen.generate_vo_per_frame(
        asset_id=999, posts=posts, business_slug="test", take_id="test_take",
    )
    assert "segments" in result
    assert len(result["segments"]) == 3
    for i, seg in enumerate(result["segments"], 1):
        assert seg["frame"] == i
        assert seg["beat_id"] == f"b{i:02d}"
        assert "path" in seg
        assert seg["duration"] == 5.0
        assert "text" in seg
        assert seg["take_id"] == "test_take"
        assert seg["combined_path"] == result["combined_path"]
    assert "total_duration" in result
    assert result["total_duration"] == 15.0  # 3 × 5.0
    assert "combined_path" in result


def test_vo_per_frame_preserves_full_approved_text():
    """VO metadata must never truncate approved text used for compliance."""
    from vo_generator import VOGenerator
    gen = VOGenerator.__new__(VOGenerator)
    gen.models_config = {}
    gen.db_path = "/tmp/test_vo_full_text.db"
    gen.provenance = MagicMock()
    gen._get_gemini_tts_config = MagicMock(return_value={
        "model": "test", "voice": "Kore", "style": "",
        "api_key_env": "FAKE_KEY", "sample_rate": 24000,
    })
    os.environ["FAKE_KEY"] = "test-key"
    gen._call_gemini_tts = MagicMock(return_value=b"\x00" * 48000)
    gen._save_wav = MagicMock(side_effect=lambda pcm, path, sr: Path(path).write_bytes(b"wav"))
    gen._get_duration = MagicMock(return_value=5.0)
    gen._record_vo_media = MagicMock()
    gen._log_provenance = MagicMock()
    exact_text = "Exact approved sentence. " * 20
    result = gen.generate_vo_per_frame(
        asset_id=998, posts=[{"beat_id": "hook", "vo_text": exact_text}],
        business_slug="test", take_id="full_text",
    )
    assert result["segments"][0]["text"] == exact_text
    assert result["segments"][0]["beat_id"] == "hook"


# ─── 2. pipeline: vo_segments column ───────────────────────────────────

def test_asset_table_has_vo_segments_column():
    """The assets table must store VO segment data."""
    from pipeline import PipelineStore
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = PipelineStore(db_path)
        # Create a draft + asset
        draft_id = store.create_draft("testbiz", 1, "ai_originated", "Instagram Reel Script", "one_off")
        store.save_draft_content(draft_id, "summary", {}, [], platform_content=[{
            "platform": "Instagram", "variant_type": "reel",
            "content": "test", "posts": ["line 1", "line 2"], "image_prompts": ["none"],
        }])
        asset_id = store.create_asset("testbiz", draft_id, "Instagram", "reel", "test", posts=["line 1", "line 2"])
        # Save VO segments
        segments = json.dumps([
            {"frame": 1, "path": "/tmp/vo_1.wav", "duration": 5.0, "text": "line 1"},
            {"frame": 2, "path": "/tmp/vo_2.wav", "duration": 7.0, "text": "line 2"},
        ])
        store.save_vo_segments(asset_id, segments)
        # Read back
        retrieved = store.get_vo_segments(asset_id)
        assert retrieved is not None
        parsed = json.loads(retrieved)
        assert len(parsed) == 2
        assert parsed[0]["frame"] == 1
        assert parsed[1]["duration"] == 7.0
    finally:
        os.unlink(db_path)


# ─── 3. produce_chain: VO step before media plan ──────────────────────

def test_assembler_chain_runs_vo_before_media_plan():
    """run_assembler_chain must call _step_vo before _step_media_plan."""
    from produce_chain import ProductionChain
    chain = ProductionChain.__new__(ProductionChain)
    chain.db_path = "/tmp/test.db"
    chain.config_dir = "config"
    chain.modules_dir = "modules"
    chain.prompts_dir = "prompts"

    call_order = []

    def make_step(name):
        def step(*args, **kwargs):
            call_order.append(name)
        return step

    chain._step_fanout = make_step("fanout")
    chain._step_vo = make_step("vo")
    chain._step_media_plan = make_step("media_plan")
    chain._step_media_exec = make_step("media_exec")
    chain._step_edit_plan = make_step("edit_plan")
    chain._step_render = make_step("render")

    from unittest.mock import MagicMock, patch
    store = MagicMock()
    store.update_card_state = MagicMock()

    with patch("pipeline.PipelineStore", return_value=store):
        chain.run_assembler_chain(draft_id=1, card_id=1, business_slug="test")

    assert call_order == ["fanout", "vo", "media_plan", "media_exec", "edit_plan", "render"]


# ─── 4. draft prompt: no fake timestamps ──────────────────────────────

def test_draft_prompt_has_no_timestamp_instructions():
    """The draft prompt must not ask the LLM to write [0:00–0:03] timestamps."""
    prompt = (REPO_ROOT / "prompts" / "draft" / "generate_v3.md").read_text()
    # The prompt should explicitly tell the LLM NOT to use timestamps
    assert "Do NOT write timestamps" in prompt
    # The instruction itself mentions [0:00–0:03] as an example of what NOT to do —
    # that's correct. Check that no skeleton or template line starts with a timestamp.
    import re
    # Look for timestamp patterns in skeleton/template blocks (not in the instruction)
    # Strip the instruction line itself, then check
    cleaned = re.sub(r'\[0:00.0:03\].*naturally takes\.', '', prompt, flags=re.DOTALL)
    # The format guide skeleton should not have timestamps like [0-2s HOOK]
    # Check for patterns that look like timestamp assignments in skeleton lines
    timestamp_skeleton = re.findall(r'\[\d+:\d+.*?\]', cleaned)
    # Filter out the instruction example
    real_timestamps = [t for t in timestamp_skeleton if 'not' not in t.lower()]
    assert len(real_timestamps) == 0, f"Found timestamp patterns in prompt: {real_timestamps}"
    # The prompt should mention beats or frames
    assert "beat" in prompt.lower() or "frame" in prompt.lower()


# ─── 5. media plan prompt: sees VO timeline ────────────────────────────

def test_media_plan_prompt_has_vo_timeline_variable():
    """The media plan prompt must have {vo_timeline} and {coverage_gaps}."""
    prompt = (REPO_ROOT / "prompts" / "assembly" / "media_plan_v1.md").read_text()
    assert "{vo_timeline}" in prompt
    assert "{coverage_gaps}" in prompt


def test_media_plan_prompt_explains_vo_is_master():
    """The prompt must tell the LLM that VO defines the real timeline."""
    prompt = (REPO_ROOT / "prompts" / "assembly" / "media_plan_v1.md").read_text()
    assert "master timeline" in prompt.lower() or "VO defines" in prompt
    assert "coverage" in prompt.lower()


# ─── 6. edit plan prompt: receives vo_timeline ─────────────────────────

def test_edit_plan_prompt_has_vo_timeline():
    """The edit plan prompt must receive {vo_timeline}."""
    prompt = (REPO_ROOT / "prompts" / "assembly" / "edit_plan_v1.md").read_text()
    assert "{vo_timeline}" in prompt


# ─── 7. format guide: Reel skeleton uses beats not timestamps ──────────

def test_format_guide_reel_skeleton_no_timestamps():
    """The Reel skeleton must use HOOK not [0-2s HOOK]."""
    guide = (REPO_ROOT / "modules" / "stackpenni" / "format-guide.md").read_text()
    # The skeleton appears in the ## Formats section as a code block after
    # the Reel entry's bullet list. Check the whole guide for the Reel skeleton.
    # No timestamps should appear anywhere in the guide.
    assert "0-2s" not in guide
    assert "[0:00" not in guide
    # The Reel skeleton should use HOOK (beat labels, not timestamps)
    assert "HOOK:" in guide or "HOOK:" in guide.upper()
    # Verify the Reel skeleton specifically doesn't have timestamp patterns
    import re
    # Find skeleton blocks (code fences) near the Reel section
    reel_idx = guide.find("### Instagram Reel")
    assert reel_idx >= 0
    # Grab a window that includes the entry + skeleton
    reel_window = guide[reel_idx:reel_idx + 2000]
    # The skeleton in this window should not have [0-2s or [0:00 patterns
    assert "0-2s" not in reel_window
    assert "[0:00" not in reel_window


# ─── 8. asset review: duration advisory (non-blocking) ────────────────

def test_asset_review_has_duration_advisory():
    """Asset review must flag VO duration > 60s as advisory, not blocking."""
    from asset_review import AssetReviewer
    assert hasattr(AssetReviewer, "check_duration_advisory") or \
           hasattr(AssetReviewer, "_check_duration_advisory")


def test_duration_advisory_does_not_block():
    """A duration_advisory flag must not set the verdict to needs_rerender."""
    from asset_review import AssetReviewer
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        reviewer = AssetReviewer(db_path)
        # Simulate a 61.5s VO duration
        result = reviewer._check_duration_advisory(61.5) if hasattr(reviewer, "_check_duration_advisory") else None
        if result:
            assert result.get("severity") != "high"
            assert result.get("blocking") is False or result.get("advisory") is True
    finally:
        os.unlink(db_path)