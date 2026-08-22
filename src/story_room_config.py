"""Tenant-scoped Story Room experiment configuration.

The Story Room is additive and disabled by default for legacy configurations.
This module validates the small runtime contract and exposes a canonical hash so
later room events and provenance records can identify the exact configuration
that selected the mode.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


STORY_ROOM_MODES = ("legacy", "story_room")


def resolve_story_room_config(business_config: dict[str, Any]) -> dict[str, Any]:
    """Return validated Story Room settings with a canonical config hash.

    An absent block is an explicit backwards-compatibility case: existing
    tenants remain in legacy mode until they opt into the experiment through
    their tenant config. The returned ``source`` makes that compatibility path
    visible to callers and future provenance records.
    """
    raw = business_config.get("story_room")
    source = "business.yaml"
    if raw is None:
        raw = {"enabled": False, "default_mode": "legacy"}
        source = "legacy_compatibility_default"
    if not isinstance(raw, dict):
        raise ValueError("story_room must be a mapping")

    enabled = raw.get("enabled")
    default_mode = raw.get("default_mode")
    if not isinstance(enabled, bool):
        raise ValueError("story_room.enabled must be a boolean")
    if default_mode not in STORY_ROOM_MODES:
        raise ValueError(
            "story_room.default_mode must be one of: "
            + ", ".join(STORY_ROOM_MODES)
        )
    if not enabled and default_mode != "legacy":
        raise ValueError("disabled Story Room config must use default_mode=legacy")

    canonical = {"enabled": enabled, "default_mode": default_mode}
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return {
        **canonical,
        "config_hash": hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
        "config_source": source,
    }
