"""VF-VS-512 planner-led search and config-driven provider execution."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pipeline import SOUNDTRACK_PLAN_LLM_SCHEMA
from soundtrack_discovery import (
    SoundtrackDiscoveryError,
    discover_soundtrack_candidates,
    normalize_search_queries,
)


def test_planner_schema_requires_bounded_search_queries():
    assert "search_queries" in SOUNDTRACK_PLAN_LLM_SCHEMA["required"]
    query_schema = SOUNDTRACK_PLAN_LLM_SCHEMA["properties"]["search_queries"]
    assert query_schema["minItems"] == 1
    assert query_schema["maxItems"] > 0
    assert query_schema["items"]["maxLength"] > 0


def test_query_mechanics_only_normalize_dedupe_and_cap():
    assert normalize_search_queries(
        ["  Reflective   minimal  ", "reflective minimal", "Pulse"],
        max_queries=2,
        max_query_chars=20,
    ) == ["Reflective minimal", "Pulse"]


def test_empty_planner_queries_fail_without_instrumental_fallback():
    with pytest.raises(SoundtrackDiscoveryError, match="search_queries"):
        normalize_search_queries([], max_queries=4, max_query_chars=40)


def _config(provider, endpoint, region):
    return {
        "discovery": {
            "max_queries": 4,
            "max_query_chars": 60,
            "cache_ttl_seconds": 300,
            "budget": {"max_requests": 4},
            "sources": [{
                "name": provider,
                "adapter": provider,
                "enabled": True,
                "endpoint": endpoint,
                "api_key_env": "TEST_AUDIO_KEY",
                "region": region,
                "limits": {"max_candidates": 5, "timeout_seconds": 2},
                "capabilities": ["audio_search", "preview"],
            }],
        }
    }


def test_two_tenant_configs_execute_different_providers_without_code_edits(monkeypatch):
    calls = []

    def alpha(query, source, credentials):
        calls.append(("alpha", query, source["endpoint"], source["region"]))
        return []

    def beta(query, source, credentials):
        calls.append(("beta", query, source["endpoint"], source["region"]))
        return []

    monkeypatch.setenv("TEST_AUDIO_KEY", "redacted-fixture")
    monkeypatch.setattr(
        "soundtrack_discovery.PROVIDER_ADAPTERS", {"alpha": alpha, "beta": beta}
    )

    first = discover_soundtrack_candidates(
        ["warm percussion"], _config("alpha", "https://alpha.invalid/search", "bb")
    )
    second = discover_soundtrack_candidates(
        ["bright synth"], _config("beta", "https://beta.invalid/search", "tt")
    )

    assert first["sources_searched"] == ["alpha"]
    assert second["sources_searched"] == ["beta"]
    assert calls == [
        ("alpha", "warm percussion", "https://alpha.invalid/search", "bb"),
        ("beta", "bright synth", "https://beta.invalid/search", "tt"),
    ]


def test_disabled_or_incapable_provider_is_not_executed(monkeypatch):
    called = False

    def adapter(*_args):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("soundtrack_discovery.PROVIDER_ADAPTERS", {"alpha": adapter})
    config = _config("alpha", "https://alpha.invalid/search", "bb")
    config["discovery"]["sources"][0]["enabled"] = False

    result = discover_soundtrack_candidates(["query"], config)

    assert not called
    assert result["sources_searched"] == []


def test_request_budget_caps_provider_query_execution(monkeypatch):
    calls = []

    def adapter(query, source, credentials):
        calls.append(query)
        return []

    monkeypatch.setenv("TEST_AUDIO_KEY", "redacted-fixture")
    monkeypatch.setattr("soundtrack_discovery.PROVIDER_ADAPTERS", {"alpha": adapter})
    config = _config("alpha", "https://alpha.invalid/search", "bb")
    config["discovery"]["budget"]["max_requests"] = 2

    discover_soundtrack_candidates(["one", "two", "three"], config)

    assert calls == ["one", "two"]
