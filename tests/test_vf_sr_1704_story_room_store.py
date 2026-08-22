import json
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from story_room_store import StoryRoomConflictError, StoryRoomScopeError, StoryRoomStore


def make_store(tmp_path):
    return StoryRoomStore(str(tmp_path / "story-room.db"))


def test_story_room_store_initializes_additive_contract_tables(tmp_path):
    store = make_store(tmp_path)
    tables = store.table_names()

    assert {
        "stories",
        "story_events",
        "story_contributions",
        "story_artifacts",
        "story_artifact_versions",
        "story_artifact_decisions",
        "story_understanding_entries",
        "story_tool_runs",
    }.issubset(tables)


def test_story_creation_and_event_retry_are_idempotent_and_ordered(tmp_path):
    store = make_store(tmp_path)
    story = store.create_story("tenant-a", "A first thought", idempotency_key="story-1")
    same_story = store.create_story("tenant-a", "A first thought", idempotency_key="story-1")

    assert story["story_id"] == same_story["story_id"]

    first = store.append_event(
        "tenant-a", story["story_id"], "operator", "message", {"text": "first"}, "event-1"
    )
    retry = store.append_event(
        "tenant-a", story["story_id"], "operator", "message", {"text": "first"}, "event-1"
    )
    second = store.append_event(
        "tenant-a", story["story_id"], "ai", "message", {"text": "second"}, "event-2"
    )
    events = store.list_events("tenant-a", story["story_id"])

    assert first["event_id"] == retry["event_id"]
    assert [event["sequence_number"] for event in events] == [1, 2]
    assert [json.loads(event["payload_json"])["text"] for event in events] == ["first", "second"]
    assert second["event_id"] != first["event_id"]


def test_idempotency_key_reuse_with_changed_payload_fails(tmp_path):
    store = make_store(tmp_path)
    story = store.create_story("tenant-a", "A thought")
    store.append_event("tenant-a", story["story_id"], "operator", "message", {"text": "one"}, "event-1")

    with pytest.raises(StoryRoomConflictError, match="idempotency"):
        store.append_event("tenant-a", story["story_id"], "operator", "message", {"text": "two"}, "event-1")


def test_cross_tenant_reads_and_writes_fail_closed(tmp_path):
    store = make_store(tmp_path)
    story = store.create_story("tenant-a", "Private thought")

    with pytest.raises(StoryRoomScopeError):
        store.get_story("tenant-b", story["story_id"])
    with pytest.raises(StoryRoomScopeError):
        store.append_event("tenant-b", story["story_id"], "operator", "message", {}, "other-tenant-event")


def test_typed_contributions_and_tool_failures_preserve_exact_refs(tmp_path):
    store = make_store(tmp_path)
    story = store.create_story("tenant-a", "Evidence-led story")
    contribution = store.add_contribution(
        "tenant-a",
        story["story_id"],
        "inspiration_observation",
        {"item_id": 12, "observation_id": 44},
        ["inspiration:item:12", "inspiration:observation:44"],
        "contribution-1",
    )
    failure = store.record_tool_run(
        "tenant-a",
        story["story_id"],
        "research",
        {"source_refs": ["source:9"]},
        status="failed",
        error={"message": "provider unavailable"},
        idempotency_key="tool-1",
    )

    assert contribution["contribution_type"] == "inspiration_observation"
    assert json.loads(contribution["source_refs_json"]) == ["inspiration:item:12", "inspiration:observation:44"]
    assert failure["status"] == "failed"
    assert json.loads(failure["error_json"])["message"] == "provider unavailable"


def test_artifact_versions_are_monotonic_and_locks_bind_exact_hash(tmp_path):
    store = make_store(tmp_path)
    story = store.create_story("tenant-a", "Versioned story")
    artifact = store.create_artifact("tenant-a", story["story_id"], "creative_brief", "brief-1")
    version_one = store.create_artifact_version(
        "tenant-a", story["story_id"], artifact["artifact_id"], {"purpose": "why now"}, "version-1"
    )
    version_two = store.create_artifact_version(
        "tenant-a", story["story_id"], artifact["artifact_id"], {"purpose": "why now", "stake": "specific"}, "version-2"
    )
    decision = store.record_artifact_decision(
        "tenant-a", story["story_id"], version_two["artifact_version_id"], "lock", "decision-1"
    )

    assert version_one["version"] == 1
    assert version_two["version"] == 2
    assert decision["bound_content_hash"] == version_two["content_hash"]
    assert store.get_artifact_version("tenant-a", version_one["artifact_version_id"])["status"] == "working"
    assert store.get_artifact_version("tenant-a", version_two["artifact_version_id"])["status"] == "locked"


def test_understanding_correction_supersedes_without_erasing_history(tmp_path):
    store = make_store(tmp_path)
    story = store.create_story("tenant-a", "Understanding")
    known = store.add_understanding(
        "tenant-a", story["story_id"], "known", "The operator supplied a receipt", "brief", ["event:1"], "operator", "understanding-1"
    )
    correction = store.add_understanding(
        "tenant-a", story["story_id"], "known", "The operator supplied two receipts", "brief", ["event:2"], "operator", "understanding-2", supersedes=known["entry_id"]
    )

    current = store.list_understanding("tenant-a", story["story_id"], current_only=True)
    all_entries = store.list_understanding("tenant-a", story["story_id"], current_only=False)

    assert len(all_entries) == 2
    assert [entry["entry_id"] for entry in current] == [correction["entry_id"]]
    history_by_id = {entry["entry_id"]: entry for entry in all_entries}
    assert history_by_id[known["entry_id"]]["current"] == 0


def test_restart_preserves_story_ledger(tmp_path):
    db_path = str(tmp_path / "restart.db")
    first_store = StoryRoomStore(db_path)
    story = first_store.create_story("tenant-a", "Survives restart")
    first_store.append_event("tenant-a", story["story_id"], "system", "failure", {"retryable": True}, "event-1")

    second_store = StoryRoomStore(db_path)
    restored = second_store.get_story("tenant-a", story["story_id"])
    events = second_store.list_events("tenant-a", story["story_id"])

    assert restored["title"] == "Survives restart"
    assert len(events) == 1
    assert json.loads(events[0]["payload_json"])["retryable"] is True


def test_app_startup_initializes_story_room_tables(tmp_path):
    from app import create_app

    db_path = str(tmp_path / "app-startup.db")
    create_app(config_dir="config", db_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND (name = 'stories' OR name LIKE 'story_%')"
            )
        }
    finally:
        conn.close()

    assert "stories" in tables
    assert "story_events" in tables
