import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from story_room_artifacts import StoryRoomArtifactService, StoryRoomArtifactValidationError
from story_room_store import StoryRoomConflictError, StoryRoomStore


BRIEF = {
    "purpose": "why this story matters now",
    "human_stake": "a specific lived stake",
    "audience": "who needs it",
    "desired_effect": "what should change",
    "available_evidence": ["event:1"],
    "evidence_gaps": [],
    "red_lines": ["do not lecture"],
    "distribution_intent": "open",
    "understanding_snapshot": ["understanding:1"],
}

STORY_MAP = {
    "point_of_view": "a specific stance",
    "frame": "the framing",
    "narrative_movement": [{"movement_id": "m1", "job": "turn", "content": "the change"}],
    "hook_direction": "a hook purpose",
    "ending": "the ending meaning",
    "format_ref": "format:1",
    "platforms": ["Instagram"],
    "production_binding": {"mode": "standard", "process_ref": "process:1"},
    "visual_treatment_ref": {"treatment_id": "cinematic", "version": "1.0"},
    "capture_policy": {"required": False},
    "style_for_this_piece": [],
    "red_lines": [],
}

EXACT_COPY = {
    "primary_text": "The exact approved words.",
    "spoken_text": "The exact spoken words.",
    "on_screen_text": [{"role": "hook", "text": "The exact hook"}],
    "platform_variants": [{"platform": "Instagram", "variant_type": "reel", "content": "The exact words", "posts_or_slides": []}],
    "post_caption": {"text": "The caption", "hashtags": ["#tag"]},
    "title": "The title",
    "evidence_notes": [{"claim": "claim", "refs": ["event:1"]}],
    "self_audit": {"findings": [], "actual_applied_changes": []},
    "direct_edit_events": [],
}

ASSET_PLAN = {
    "format": "reel",
    "platform": "Instagram",
    "spoken_beats": [{"beat_id": "b1", "job": "hook", "text_ref": "copy:1"}],
    "visual_roles": [],
    "soundtrack": {"mode": "vo_only"},
    "caption_roles": [],
    "production_notes": [],
}


def service(tmp_path):
    store = StoryRoomStore(str(tmp_path / "artifacts.db"))
    return store, StoryRoomArtifactService(store)


def test_artifact_payloads_are_strictly_typed(tmp_path):
    store, artifacts = service(tmp_path)
    story = store.create_story("tenant-a", "A story")

    with pytest.raises(StoryRoomArtifactValidationError, match="creative_brief.*human_stake"):
        artifacts.create_version("tenant-a", story["story_id"], "creative_brief", {"purpose": "only"})

    invalid = dict(BRIEF)
    invalid["unexpected"] = True
    with pytest.raises(StoryRoomArtifactValidationError, match="unexpected"):
        artifacts.create_version("tenant-a", story["story_id"], "creative_brief", invalid)


def test_versions_are_monotonic_and_compare_and_set_is_enforced(tmp_path):
    store, artifacts = service(tmp_path)
    story = store.create_story("tenant-a", "A story")
    first = artifacts.create_version("tenant-a", story["story_id"], "creative_brief", BRIEF)
    second = artifacts.create_version(
        "tenant-a", story["story_id"], "creative_brief", {**BRIEF, "desired_effect": "a new effect"},
        expected_current_version_id=first["artifact_version_id"],
    )

    assert (first["version"], second["version"]) == (1, 2)
    with pytest.raises(StoryRoomConflictError, match="current"):
        artifacts.create_version(
            "tenant-a", story["story_id"], "creative_brief", BRIEF,
            expected_current_version_id=first["artifact_version_id"],
        )


def test_direct_edit_is_authoritative_and_returns_visible_diff(tmp_path):
    store, artifacts = service(tmp_path)
    story = store.create_story("tenant-a", "A story")
    first = artifacts.create_version("tenant-a", story["story_id"], "exact_copy", EXACT_COPY)
    edited = artifacts.direct_edit(
        "tenant-a", story["story_id"], first["artifact_version_id"],
        {**EXACT_COPY, "primary_text": "The operator's exact words."},
        idempotency_key="direct-edit-1",
    )

    assert edited["revision_kind"] == "direct_edit"
    assert edited["author"] == "operator"
    assert '-  "primary_text": "The exact approved words."' in edited["diff_text"]
    assert '+  "primary_text": "The operator\'s exact words."' in edited["diff_text"]


def test_story_map_change_stales_downstream_but_not_brief(tmp_path):
    store, artifacts = service(tmp_path)
    story = store.create_story("tenant-a", "A story")
    brief = artifacts.create_version("tenant-a", story["story_id"], "creative_brief", BRIEF)
    brief_lock = artifacts.lock("tenant-a", story["story_id"], brief["artifact_version_id"], "brief-lock")
    shape = artifacts.create_version("tenant-a", story["story_id"], "story_map", STORY_MAP, based_on=[brief["artifact_version_id"]])
    artifacts.lock("tenant-a", story["story_id"], shape["artifact_version_id"], "shape-lock")
    copy = artifacts.create_version("tenant-a", story["story_id"], "exact_copy", EXACT_COPY, based_on=[shape["artifact_version_id"]])
    artifacts.lock("tenant-a", story["story_id"], copy["artifact_version_id"], "copy-lock")
    plan = artifacts.create_version("tenant-a", story["story_id"], "asset_plan", ASSET_PLAN, based_on=[copy["artifact_version_id"]])
    artifacts.lock("tenant-a", story["story_id"], plan["artifact_version_id"], "plan-lock")

    shape_v2 = artifacts.create_version(
        "tenant-a", story["story_id"], "story_map", {**STORY_MAP, "frame": "a changed frame"},
        based_on=[brief["artifact_version_id"]], expected_current_version_id=shape["artifact_version_id"],
    )

    assert brief_lock["action"] == "lock"
    assert artifacts.get_version("tenant-a", brief["artifact_version_id"])["status"] == "locked"
    assert artifacts.get_version("tenant-a", copy["artifact_version_id"])["status"] == "stale"
    assert artifacts.get_version("tenant-a", plan["artifact_version_id"])["status"] == "stale"
    assert artifacts.get_version("tenant-a", shape_v2["artifact_version_id"])["status"] == "working"


def test_stale_version_cannot_lock_or_compile(tmp_path):
    store, artifacts = service(tmp_path)
    story = store.create_story("tenant-a", "A story")
    shape = artifacts.create_version("tenant-a", story["story_id"], "story_map", STORY_MAP)
    copy = artifacts.create_version("tenant-a", story["story_id"], "exact_copy", EXACT_COPY, based_on=[shape["artifact_version_id"]])
    artifacts.create_version("tenant-a", story["story_id"], "story_map", {**STORY_MAP, "frame": "new"}, expected_current_version_id=shape["artifact_version_id"])

    with pytest.raises(StoryRoomConflictError, match="stale"):
        artifacts.lock("tenant-a", story["story_id"], copy["artifact_version_id"], "stale-lock")
    with pytest.raises(StoryRoomConflictError, match="stale"):
        artifacts.require_locked_current("tenant-a", story["story_id"], "exact_copy")
