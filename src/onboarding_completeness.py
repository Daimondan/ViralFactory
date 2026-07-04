"""Onboarding completeness checker — surfaces missing inputs per module."""

import json
import os
from playbook_runner import PlaybookParser, PlaybookRunner


# Maps required_input keys to their source playbook and collected_inputs key
INPUT_SOURCE_MAP = {
    "admired_examples": {"playbook": "viral-patterns-starter", "collected_key": "story_admired_refs"},
    "operator_stories": {"playbook": "story-frameworks-starter", "collected_key": "operator_stories"},
    "voice_summary": {"playbook": "voice-profile-builder", "collected_key": "voice_summary"},
    "audience_description": {"playbook": "business-profile-intake", "collected_key": "business_qa"},
    "audience_data": {"playbook": "audience-insights-builder", "collected_key": "audience_data"},
    "admired_signals": {"playbook": "audience-insights-builder", "collected_key": "admired_signals"},
    "admired_links": {"playbook": "viral-patterns-starter", "collected_key": "admired_links"},
    "anti_examples": {"playbook": "viral-patterns-starter", "collected_key": "anti_examples"},
    "top_performers": {"playbook": "viral-patterns-starter", "collected_key": "top_performers"},
    "voice_samples": {"playbook": "voice-profile-builder", "collected_key": "voice_samples"},
    "tone_redlines": {"playbook": "voice-profile-builder", "collected_key": "tone_redlines"},
    "business_qa": {"playbook": "business-profile-intake", "collected_key": "business_qa"},
    "platform_list": {"playbook": "business-profile-intake", "collected_key": "platform_list"},
    "format_observations": {"playbook": "format-guide-starter", "collected_key": "format_observations"},
    "platform_norms": {"playbook": "format-guide-starter", "collected_key": "platform_norms"},
    "photo_library": {"playbook": "visual-style-intake", "collected_key": "photo_library"},
    "brand_assets": {"playbook": "visual-style-intake", "collected_key": "brand_assets"},
    "visual_examples": {"playbook": "visual-style-intake", "collected_key": "visual_examples"},
}


def check_completeness(db_path: str, playbooks_dir: str, business_slug: str) -> list[dict]:
    """Check each playbook's required inputs against collected inputs.

    Returns a list of dicts:
    {
        "playbook": "story-frameworks-starter",
        "display_label": "Story Frameworks",
        "inputs": [
            {"name": "admired_examples", "status": "missing|present|inferred",
             "source_playbook": "viral-patterns-starter", "value": "..."},
        ]
    }
    """
    runner = PlaybookRunner(db_path)
    runs = runner.list_runs()

    # Build a map of playbook_name → collected_inputs (latest run wins)
    collected_by_playbook = {}
    for run in runs:
        run_dict = dict(run)
        collected = json.loads(run_dict.get("collected_inputs") or "{}")
        collected_by_playbook[run_dict["playbook_name"]] = collected

    results = []
    for pb_file in sorted(os.listdir(playbooks_dir)):
        if not pb_file.endswith(".md"):
            continue
        pb_path = os.path.join(playbooks_dir, pb_file)
        playbook = PlaybookParser.parse(pb_path)

        if not playbook.required_inputs:
            continue

        pb_collected = collected_by_playbook.get(playbook.name, {})
        input_statuses = []

        for req_key in playbook.required_inputs:
            source_info = INPUT_SOURCE_MAP.get(req_key, {})
            collected_key = source_info.get("collected_key", req_key)

            # Check if this input exists in the playbook's own collected_inputs
            # or in the onboarding run's collected_inputs
            value = pb_collected.get(collected_key)
            if value is None:
                # Check onboarding run
                onboarding_collected = collected_by_playbook.get("onboarding", {})
                value = onboarding_collected.get(collected_key)

            if value and str(value).strip():
                status = "present"
            else:
                status = "missing"

            input_statuses.append({
                "name": req_key,
                "status": status,
                "source_playbook": source_info.get("playbook", ""),
                "collected_key": collected_key,
            })

        results.append({
            "playbook": playbook.name,
            "display_label": playbook.display_label or playbook.name,
            "inputs": input_statuses,
        })

    return results