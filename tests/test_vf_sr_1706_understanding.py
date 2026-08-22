import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from story_room_store import StoryRoomConflictError, StoryRoomStore
from story_room_understanding import StoryRoomEvidenceError, StoryRoomUnderstandingService


def make_room(tmp_path, tenant="tenant-a"):
    store = StoryRoomStore(str(tmp_path / "understanding.db"))
    story = store.create_story(tenant, "A story")
    return store, StoryRoomUnderstandingService(store), story


def test_ai_known_requires_exact_evidence_and_preserves_missing_entries(tmp_path):
    store, understanding, story = make_room(tmp_path)
    missing = understanding.add_entry(
        "tenant-a", story["story_id"], "missing", "What happened next?", "brief", [], "ai", "missing-1"
    )
    with pytest.raises(StoryRoomEvidenceError, match="exact evidence"):
        understanding.add_entry(
            "tenant-a", story["story_id"], "known", "The operator was present", "brief", [], "ai", "known-1"
        )

    event = store.append_event(
        "tenant-a", story["story_id"], "operator", "message", {"text": "I was there"}, "event-1"
    )
    known = understanding.add_entry(
        "tenant-a", story["story_id"], "known", "The operator was present", "brief", [event["event_id"]], "ai", "known-1"
    )

    assert missing["kind"] == "missing"
    assert known["kind"] == "known"


def test_evidence_cannot_cross_tenant_or_use_unknown_refs(tmp_path):
    store, understanding, story = make_room(tmp_path, "tenant-a")
    other_story = store.create_story("tenant-b", "Other story")
    other_event = store.append_event(
        "tenant-b", other_story["story_id"], "operator", "message", {"text": "private"}, "other-event"
    )

    with pytest.raises(StoryRoomEvidenceError, match="scope"):
        understanding.add_entry(
            "tenant-a", story["story_id"], "known", "Imported fact", "brief", [other_event["event_id"]], "ai", "cross-tenant"
        )
    with pytest.raises(StoryRoomEvidenceError, match="exact Story Room ref"):
        understanding.add_entry(
            "tenant-a", story["story_id"], "known", "Unsupported fact", "brief", ["event:missing"], "ai", "unknown-ref"
        )


def test_locked_understanding_requires_server_verified_artifact_decision(tmp_path):
    store, understanding, story = make_room(tmp_path)
    artifact = store.create_artifact("tenant-a", story["story_id"], "creative_brief")
    version = store.create_artifact_version(
        "tenant-a", story["story_id"], artifact["artifact_id"], {"purpose": "exact"}, idempotency_key="brief-version"
    )

    with pytest.raises(StoryRoomEvidenceError, match="verified lock decision"):
        understanding.add_entry(
            "tenant-a", story["story_id"], "locked", "The brief is locked", "brief", [version["artifact_version_id"]], "ai", "locked-1"
        )

    decision = store.record_artifact_decision(
        "tenant-a", story["story_id"], version["artifact_version_id"], "lock", idempotency_key="brief-decision"
    )
    locked = understanding.add_entry(
        "tenant-a", story["story_id"], "locked", "The brief is locked", "brief", [version["artifact_version_id"]], "ai", "locked-1", verified_decision_id=decision["decision_id"]
    )

    assert locked["kind"] == "locked"


def test_human_correction_supersedes_without_duplicate_retry(tmp_path):
    store, understanding, story = make_room(tmp_path)
    event = store.append_event(
        "tenant-a", story["story_id"], "operator", "message", {"text": "first"}, "event-1"
    )
    original = understanding.add_entry(
        "tenant-a", story["story_id"], "known", "The first account", "brief", [event["event_id"]], "operator", "entry-1"
    )
    correction = understanding.add_entry(
        "tenant-a", story["story_id"], "known", "The corrected account", "brief", [event["event_id"]], "operator", "entry-2", supersedes=original["entry_id"]
    )
    retry = understanding.add_entry(
        "tenant-a", story["story_id"], "known", "The corrected account", "brief", [event["event_id"]], "operator", "entry-2", supersedes=original["entry_id"]
    )

    current = store.list_understanding("tenant-a", story["story_id"], current_only=True)
    assert retry["entry_id"] == correction["entry_id"]
    assert [entry["entry_id"] for entry in current] == [correction["entry_id"]]
    assert len(store.list_understanding("tenant-a", story["story_id"], current_only=False)) == 2


def test_ai_cannot_self_lock_without_decision_even_with_evidence(tmp_path):
    store, understanding, story = make_room(tmp_path)
    event = store.append_event(
        "tenant-a", story["story_id"], "operator", "message", {"text": "claim"}, "event-1"
    )

    with pytest.raises(StoryRoomEvidenceError, match="verified lock decision"):
        understanding.add_entry(
            "tenant-a", story["story_id"], "locked", "AI says locked", "brief", [event["event_id"]], "ai", "self-lock"
        )
