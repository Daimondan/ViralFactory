import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from distribution_intent import normalize_distribution_intent


def test_empty_request_is_open_selection():
    assert normalize_distribution_intent({}) == {
        "mode": "open",
        "platforms": [],
        "formats": [],
    }


def test_platform_request_constrains_selection_to_that_platform():
    assert normalize_distribution_intent({"platform": "Instagram"}) == {
        "mode": "platform_constrained",
        "platforms": ["Instagram"],
        "formats": [],
    }


def test_platform_and_format_request_is_exact_format():
    assert normalize_distribution_intent(
        {"platform": "Instagram", "format": "Instagram Reel"}
    ) == {
        "mode": "exact_format",
        "platforms": ["Instagram"],
        "formats": ["Instagram Reel"],
    }


def test_exact_format_requires_one_platform_and_one_format():
    with pytest.raises(ValueError, match="exact_format"):
        normalize_distribution_intent({
            "distribution_intent": {
                "mode": "exact_format",
                "platforms": [],
                "formats": ["Instagram Reel"],
            }
        })


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError, match="mode"):
        normalize_distribution_intent({"distribution_intent": {"mode": "everywhere"}})
