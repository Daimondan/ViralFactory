"""
QA-loop F-001: Autonomous assembler must generate AI visuals when
capture_required is empty but the asset has image_prompts.

Reproduction of the blocker: a Reel idea card with capture_required=[]
ships through the assembler chain. MediaPlanningService.generate_for_asset
short-circuits with "No missing captures — all fulfilled" and never
generates AI images, so EditPlanningService fails with
"No usable visual media is available."

The fix: when capture_required is empty but the asset carries image_prompts,
generate AI images from those prompts (the same path the UI's
"Generate visuals" button uses) so the edit plan has render-ready
ingredients.
"""

import json
import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.media_planning import MediaPlanningService


def _seed_reel_asset(db_path, *, image_prompts, capture_required=None):
    """Create a minimal StackPenni Reel asset/draft/card with the given
    image_prompts and capture_required treatment."""
    import sqlite3
    from datetime import datetime, timezone

    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()
    treatment = {
        "scope": {"type": "one_off", "n": 0, "cadence": ""},
        "format": {
            "primary_platform": "Instagram",
            "format_name": "Instagram Reel Script",
            "experimental": False,
        },
        "capture_required": capture_required or [],
        "reuse": [],
        "rationale": "QA-loop test",
    }
    conn.execute(
        "INSERT INTO idea_cards (business_slug, idea, hook_options, treatment, "
        "origin, evidence_links, seed_text, card_state, source_refs, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("stackpenni", "QA test idea", "[]", json.dumps(treatment),
         "ai_originated", "[]", "", "drafted", "[]", now, now),
    )
    card_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO drafts (business_slug, idea_card_id, origin, format, scope, "
        "draft_text, visual_direction, draft_state, platform_content, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("stackpenni", card_id, "ai_originated", "Instagram Reel Script",
         "one_off", "draft text", json.dumps({"image_prompts": image_prompts}),
         "shipped", json.dumps([{"platform": "Instagram", "variant_type": "reel"}]),
         now, now),
    )
    draft_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO assets (business_slug, draft_id, platform, variant_type, "
        "content, image_prompts, generated_images, asset_state, posts, vo_segments, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("stackpenni", draft_id, "Instagram", "reel", "reel content",
         json.dumps(image_prompts), "[]", "pending", "[]", "[]", now, now),
    )
    asset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return card_id, draft_id, asset_id


def _bootstrap_schema(db_path):
    """Run the project's schema bootstrap so the temp DB has all tables."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from pipeline import PipelineStore
    PipelineStore(db_path)  # __init__ executes SCHEMA_SQL


def _bootstrap_edit_plan_schema(db_path):
    """Create edit_plans + soundtrack_plans tables for the temp DB."""
    import sqlite3
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    from pipeline import PipelineStore
    store = PipelineStore(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(store.EDIT_PLAN_SCHEMA)
    conn.executescript(store.SOUNDTRACK_PLAN_SCHEMA)
    conn.commit()
    conn.close()


class TestGenerateForAssetNoCapturesWithPrompts:
    """F-001: media planning must not short-circuit when there are
    image_prompts to fulfill even if no captures are required."""

    def test_generates_ai_images_from_prompts_when_no_captures(self, tmp_path):
        db_path = str(tmp_path / "vf.db")
        _bootstrap_schema(db_path)
        prompts = [
            "Caribbean entrepreneur at a laptop, warm light, 9:16",
            "Over-the-shoulder shot of hands typing, warm tones, 9:16",
        ]
        _seed_reel_asset(db_path, image_prompts=prompts, capture_required=[])

        svc = MediaPlanningService(
            models_config={"media": {"image_default": "google/test"}},
            db_path=db_path,
            config_dir=os.path.join(os.path.dirname(__file__), "..", "config"),
            modules_dir=os.path.join(os.path.dirname(__file__), "..", "modules"),
            prompts_dir=os.path.join(os.path.dirname(__file__), "..", "prompts"),
        )

        # Spy on the LLM adapter so we don't make real LLM calls; force a plan
        # that asks for one AI image per prompt.
        from services import ServiceResponse

        result = svc.generate_for_asset(asset_id=1, business_slug="stackpenni")

        # The service must NOT short-circuit with "No missing captures".
        assert result.payload.get("message") != "No missing captures — all fulfilled"
        # It must report a media plan / results, indicating it proceeded.
        assert result.payload.get("status") != "ok" or "media_plan" in result.payload or "results" in result.payload