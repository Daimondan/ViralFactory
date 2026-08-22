import copy
import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app import create_app
from config_loader import ConfigError, load_business
from story_room_config import resolve_story_room_config


def _business_config(story_room=None):
    config = {
        "business": {
            "name": "Test Business",
            "slug": "test-business",
            "description": "A generic test tenant",
        },
        "subjects": ["subject"],
        "platforms": [{"name": "Test", "handle": "@test", "priority": 1}],
    }
    if story_room is not None:
        config["story_room"] = story_room
    return config


def _write_business(tmp_path, story_room=None):
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "business.yaml").write_text(
        yaml.safe_dump(_business_config(story_room), sort_keys=False),
        encoding="utf-8",
    )
    return config_dir


def test_story_room_config_supports_tenant_enablement_and_hash(tmp_path):
    disabled_dir = _write_business(tmp_path / "disabled", {"enabled": False, "default_mode": "legacy"})
    enabled_dir = _write_business(tmp_path / "enabled", {"enabled": True, "default_mode": "story_room"})

    disabled = resolve_story_room_config(load_business(str(disabled_dir)))
    enabled = resolve_story_room_config(load_business(str(enabled_dir)))

    assert disabled["enabled"] is False
    assert disabled["default_mode"] == "legacy"
    assert enabled["enabled"] is True
    assert enabled["default_mode"] == "story_room"
    assert disabled["config_hash"] != enabled["config_hash"]
    assert disabled["config_source"] == "business.yaml"


def test_missing_story_room_block_preserves_legacy_mode():
    resolved = resolve_story_room_config(_business_config())

    assert resolved["enabled"] is False
    assert resolved["default_mode"] == "legacy"
    assert resolved["config_source"] == "legacy_compatibility_default"
    assert len(resolved["config_hash"]) == 64


def test_invalid_story_room_config_fails_config_validation(tmp_path):
    config_dir = _write_business(tmp_path, {"enabled": False, "default_mode": "story_room"})

    with pytest.raises(ConfigError, match="Disabled Story Room config"):
        load_business(str(config_dir))


def test_app_exposes_story_room_config_without_cutting_over_legacy_routes(tmp_path):
    config_dir = _write_business(tmp_path, {"enabled": False, "default_mode": "legacy"})
    app = create_app(config_dir=str(config_dir), db_path=str(tmp_path / "vf.db"))

    assert app.config["STORY_ROOM_CONFIG"]["enabled"] is False
    assert app.config["STORY_ROOM_CONFIG"]["default_mode"] == "legacy"
    routes = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/ideas" in routes
    assert "/stories" not in routes
