"""
Tests for T11.10: Golden episodes + validator pass-rate metric.

AC: goldens in suite and blocking; pass-rate report generated per Writer prompt version.
"""

import json
import os
import pytest
import sys
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Golden episode fixtures ───────────────────────────────────────────────────

class TestGoldenEpisodes:

    def test_golden_episodes_exist(self):
        """Two golden episode fixtures must exist under tests/fixtures/golden/."""
        from episode_goldens import list_golden_episodes
        goldens = list_golden_episodes()
        assert len(goldens) >= 2, f"Expected >=2 golden episodes, found {len(goldens)}: {goldens}"

    def test_golden_episode_01_loads(self):
        """Golden episode 01 loads and has the correct structure."""
        from episode_goldens import load_golden_episode
        plan = load_golden_episode("episode_01")
        assert "beats" in plan
        assert len(plan["beats"]) >= 5
        roles = [b["role"] for b in plan["beats"]]
        assert "hook" in roles
        assert "lesson" in roles
        assert "cta" in roles

    def test_golden_episode_02_loads(self):
        """Golden episode 02 loads and has the correct structure."""
        from episode_goldens import load_golden_episode
        plan = load_golden_episode("episode_02")
        assert "beats" in plan
        assert len(plan["beats"]) >= 5
        roles = [b["role"] for b in plan["beats"]]
        assert "hook" in roles
        assert "lesson" in roles
        assert "cta" in roles

    def test_golden_episode_validates_duration(self):
        """Golden episode duration matches expected."""
        from episode_goldens import validate_golden_episode
        result = validate_golden_episode("episode_01", expected_duration=72.0)
        assert result["valid"], f"Validation failed: {result['issues']}"
        assert result["checks"]["duration"] is True
        assert result["checks"]["plan_structure"] is True

    def test_golden_episode_has_no_tenant_strings_in_beats(self):
        """Golden episode beats must not contain tenant-specific strings in code."""
        from episode_goldens import load_golden_episode
        tenant_strings = ["StackPenni", "stackpenni", "Daimon", "daimon"]
        for name in ["episode_01", "episode_02"]:
            plan = load_golden_episode(name)
            plan_json = json.dumps(plan)
            for tenant in tenant_strings:
                assert tenant.lower() not in plan_json.lower(), (
                    f"Tenant string '{tenant}' found in golden episode {name}"
                )

    def test_golden_episode_beats_have_staged_actions(self):
        """Every beat in golden episodes must have a staged_action."""
        from episode_goldens import load_golden_episode
        for name in ["episode_01", "episode_02"]:
            plan = load_golden_episode(name)
            for beat in plan["beats"]:
                assert beat.get("staged_action"), (
                    f"Beat {beat.get('id', '?')} in {name} has no staged_action"
                )

    def test_golden_episode_numbers_have_graphics(self):
        """Every numeral in vo_text must have a graphics entry (Layer-1 lint rule)."""
        from episode_goldens import load_golden_episode
        import re
        for name in ["episode_01", "episode_02"]:
            plan = load_golden_episode(name)
            for beat in plan["beats"]:
                vo = beat.get("vo_text", "")
                numbers = re.findall(r'\b\d+\b', vo)
                if numbers:
                    assert beat.get("graphics"), (
                        f"Beat {beat.get('id')} in {name} has numbers {numbers} in vo_text "
                        f"but no graphics entry"
                    )


# ── Pass-rate metric ─────────────────────────────────────────────────────────

@pytest.fixture
def ref_store():
    """Create a ReferenceAssetStore with approved assets for the corpus."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    from reference_assets import ReferenceAssetStore
    store = ReferenceAssetStore(db_path)

    # Approve minimal assets
    store.propose("test", "character_ref", "fitzroy", {"name": "Fitzroy", "files": ["r1.jpg"]})
    store.approve(1)
    store.propose("test", "location_ref", "kitchen_dawn", {"prompt_text": "kitchen", "files": ["k.jpg"]})
    store.approve(2)
    store.propose("test", "music_bed", "bed_somber", {"file": "bed.mp3", "register": "somber"})
    store.approve(3)
    store.propose("test", "grade_token", "default", {"grade_string": "warm golden light"})
    store.approve(4)
    store.propose("test", "card_style", "title_card_v1", {"font": "Georgia"})
    store.approve(5)
    store.propose("test", "location_ref", "market_morning", {"prompt_text": "market", "files": ["m.jpg"]})
    store.approve(6)
    store.propose("test", "location_ref", "desk_evening", {"prompt_text": "desk", "files": ["d.jpg"]})
    store.approve(7)
    store.propose("test", "location_ref", "porch_afternoon", {"prompt_text": "porch", "files": ["p.jpg"]})
    store.approve(8)
    store.propose("test", "location_ref", "rum_shop", {"prompt_text": "rum shop", "files": ["rs.jpg"]})
    store.approve(9)
    store.propose("test", "location_ref", "beach_dusk", {"prompt_text": "beach", "files": ["b.jpg"]})
    store.approve(10)
    store.propose("test", "music_bed", "bed_wry", {"file": "wry.mp3", "register": "wry"})
    store.approve(11)
    store.propose("test", "music_bed", "bed_hopeful", {"file": "hopeful.mp3", "register": "hopeful"})
    store.approve(12)
    store.propose("test", "location_ref", "rum_shop", {"prompt_text": "rum shop", "files": ["rs.jpg"]})
    store.approve(13)

    yield store
    store.close()
    os.close(db_fd)
    os.unlink(db_path)


class TestPassRateMetric:

    def test_pass_rate_computes(self, ref_store):
        """The pass-rate metric computes correctly for a valid corpus."""
        from episode_goldens import compute_pass_rate

        # Load golden episodes as the corpus
        golden1 = {
            "format_module": "episode-format-parable@v1",
            "beats": [
                {"id": "b01", "role": "hook", "vo_text": "I worked 50 years",
                 "staged_action": "the man sits", "character_ref": "fitzroy",
                 "location_ref": "kitchen_dawn", "register": "somber", "duration_s": 3,
                 "graphics": [{"type": "number_card", "text": "50", "style": "title_card_v1"}]},
                {"id": "b02", "role": "lesson", "vo_text": "Save early",
                 "staged_action": "the man saves", "character_ref": "fitzroy",
                 "location_ref": "kitchen_dawn", "register": "hopeful", "duration_s": 15},
                {"id": "b03", "role": "cta", "vo_text": "Start now",
                 "staged_action": "the man stands", "character_ref": "fitzroy",
                 "location_ref": "kitchen_dawn", "register": "hopeful", "duration_s": 15},
            ],
        }
        golden2 = {
            "format_module": "episode-format-parable@v1",
            "beats": [
                {"id": "b01", "role": "hook", "vo_text": "Everybody wants results",
                 "staged_action": "the man watches", "character_ref": "fitzroy",
                 "location_ref": "rum_shop", "register": "wry", "duration_s": 3},
                {"id": "b02", "role": "lesson", "vo_text": "Do the work",
                 "staged_action": "the man writes", "character_ref": "fitzroy",
                 "location_ref": "kitchen_dawn", "register": "hopeful", "duration_s": 15},
                {"id": "b03", "role": "cta", "vo_text": "Start today",
                 "staged_action": "the man closes notebook", "character_ref": "fitzroy",
                 "location_ref": "kitchen_dawn", "register": "hopeful", "duration_s": 15},
            ],
        }

        format_module = {"type": "episode-format", "name": "parable", "target_duration_s": 90, "version": "v1"}
        lint_config = {
            "banned_prompt_tokens": ["text", "screen", "phone", "logo"],
            "duration_tolerance_pct": 200,  # very generous for small test corpus
            "hook_max_duration_s": 3.0,
        }

        result = compute_pass_rate(
            episode_plans=[golden1, golden2],
            format_module=format_module,
            ref_store=ref_store,
            business_slug="test",
            lint_config=lint_config,
        )

        assert result["total"] == 2
        assert result["passed"] == 2
        assert result["pass_rate"] == 1.0
        assert result["prompt_version"] == "v1"

    def test_pass_rate_catches_failures(self, ref_store):
        """The pass-rate metric records failures correctly."""
        from episode_goldens import compute_pass_rate

        bad_plan = {
            "format_module": "episode-format-parable@v1",
            "beats": [
                {"id": "b01", "role": "setup", "vo_text": "not a hook",
                 "staged_action": "the man looks at his phone",  # banned token
                 "character_ref": "ghost",  # unapproved ref
                 "location_ref": "kitchen_dawn", "register": "somber", "duration_s": 10},
            ],
            # No lesson, no cta — grammar fails
        }

        format_module = {"type": "episode-format", "target_duration_s": 90, "version": "v1"}
        lint_config = {
            "banned_prompt_tokens": ["phone"],
            "duration_tolerance_pct": 50,
            "hook_max_duration_s": 3.0,
        }

        result = compute_pass_rate(
            episode_plans=[bad_plan],
            format_module=format_module,
            ref_store=ref_store,
            business_slug="test",
            lint_config=lint_config,
        )

        assert result["total"] == 1
        assert result["passed"] == 0
        assert result["pass_rate"] == 0.0
        assert len(result["failures"]) == 1

    def test_pass_rate_verdict(self):
        """The verdict function flags low pass rates as prompt/schema defects."""
        from episode_goldens import pass_rate_verdict
        assert pass_rate_verdict(0.90) == "pass"
        assert pass_rate_verdict(0.80) == "pass"
        assert pass_rate_verdict(0.79) == "fail_prompt_or_schema_defect"
        assert pass_rate_verdict(0.50) == "fail_prompt_or_schema_defect"

    def test_pass_rate_empty_corpus(self, ref_store):
        """Empty corpus returns 0.0 pass rate without crashing."""
        from episode_goldens import compute_pass_rate
        result = compute_pass_rate(
            episode_plans=[],
            format_module={"version": "v1"},
            ref_store=ref_store,
            business_slug="test",
            lint_config={},
        )
        assert result["total"] == 0
        assert result["pass_rate"] == 0.0