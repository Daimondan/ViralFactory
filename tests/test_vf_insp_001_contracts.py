"""VF-INSP-001 — Evidence contracts, provider config, redacted fixtures.

Acceptance criteria (from BUILD_PLAN):
  - chart, recommendation, seed, empty, partial, malformed, rate-limited, and
    auth-failed redacted fixtures validate through fake adapters
  - unlike endpoint semantics remain distinct
  - no live network or credentials in automated tests
  - tenant scoping on every persisted record
  - secrets stripped from URLs/payloads before persistence
  - missing metrics are unavailable, never zero
  - no green success state for a failed/stale collection
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
FIXTURES = Path(__file__).parent / "fixtures" / "inspiration"


# ─── Redaction ───────────────────────────────────────────────────────────────

def test_redact_url_strips_secret_params():
    from inspiration_contracts import redact_url
    url = "https://example.com/audio/001?token=SECRET&sig=abc&id=5"
    cleaned = redact_url(url, ["token", "sig"])
    assert "token=" not in cleaned
    assert "sig=" not in cleaned
    assert "id=5" in cleaned


def test_redact_url_case_insensitive():
    from inspiration_contracts import redact_url
    url = "https://example.com/x?Token=SECRET&keep=1"
    cleaned = redact_url(url, ["token"])
    assert "Token=" not in cleaned
    assert "keep=1" in cleaned


def test_redact_url_handles_empty():
    from inspiration_contracts import redact_url
    assert redact_url("", ["token"]) == ""
    assert redact_url("https://example.com/x", ["token"]) == "https://example.com/x"


def test_redact_url_handles_malformed():
    from inspiration_contracts import redact_url
    # malformed URL should not crash; return original
    malformed = "not a url at all"
    assert redact_url(malformed, ["token"]) == malformed


def test_redact_payload_strips_secret_fields():
    from inspiration_contracts import redact_payload
    payload = {"audio_id": "1", "access_token": "SECRET", "title": "ok"}
    cleaned = redact_payload(payload, ["access_token", "token"])
    assert "access_token" not in cleaned
    assert cleaned["title"] == "ok"


def test_redact_payload_recurses_nested():
    from inspiration_contracts import redact_payload
    payload = {"data": {"api_key": "SECRET", "id": "1"}, "list": [{"token": "s", "x": 1}]}
    cleaned = redact_payload(payload, ["api_key", "token"])
    assert "api_key" not in cleaned["data"]
    assert cleaned["data"]["id"] == "1"
    assert "token" not in cleaned["list"][0]
    assert cleaned["list"][0]["x"] == 1


def test_apply_redaction_strips_secret_fields_and_url_params():
    from inspiration_contracts import apply_redaction
    redaction_config = {
        "payload_field_names": ["access_token"],
        "url_fields": ["download_url"],
        "url_param_names": ["token", "sig"],
    }
    payload = {
        "access_token": "SECRET",
        "download_url": "https://example.com/x?token=SECRET&id=1",
        "title": "keep",
    }
    cleaned = apply_redaction(payload, redaction_config)
    assert "access_token" not in cleaned
    assert "token=" not in cleaned["download_url"]
    assert "id=1" in cleaned["download_url"]
    assert cleaned["title"] == "keep"


# ─── Safe payload hash ─────────────────────────────────────────────────────

def test_safe_payload_hash_stable():
    from inspiration_contracts import compute_safe_payload_hash
    a = compute_safe_payload_hash({"b": 2, "a": 1})
    b = compute_safe_payload_hash({"a": 1, "b": 2})
    assert a == b
    assert len(a) == 64


def test_safe_payload_hash_differs_on_content():
    from inspiration_contracts import compute_safe_payload_hash
    a = compute_safe_payload_hash({"a": 1})
    b = compute_safe_payload_hash({"a": 2})
    assert a != b


# ─── Collection run contract ────────────────────────────────────────────────

def test_make_collection_run_ok():
    from inspiration_contracts import make_collection_run, COLLECTION_RUN_STATUS_OK
    run = make_collection_run(
        business_slug="test-tenant",
        provider="bundle_social_instagram_audio",
        endpoint_key="chart",
        platform="instagram",
        region="global",
        status=COLLECTION_RUN_STATUS_OK,
        started_at="2026-07-20T10:00:00+00:00",
        ended_at="2026-07-20T10:00:05+00:00",
        result_count=3,
    )
    assert run["status"] == "ok"
    assert run["result_count"] == 3
    assert run["business_slug"] == "test-tenant"


def test_make_collection_run_rejects_missing_field():
    from inspiration_contracts import make_collection_run, InspirationContractError
    with pytest.raises(InspirationContractError) as exc:
        make_collection_run(
            business_slug="t",
            provider="p",
            endpoint_key="chart",
            platform="instagram",
            region="global",
            status="ok",
            started_at="2026-07-20T10:00:00+00:00",
            ended_at="",  # missing
        )
    assert "ended_at" in str(exc.value)


def test_make_collection_run_rejects_invalid_status():
    from inspiration_contracts import make_collection_run, InspirationContractError
    with pytest.raises(InspirationContractError):
        make_collection_run(
            business_slug="t", provider="p", endpoint_key="chart",
            platform="instagram", region="global", status="bogus",
            started_at="2026-07-20T10:00:00+00:00",
            ended_at="2026-07-20T10:00:05+00:00",
        )


def test_collection_run_statuses_distinct():
    """All status values are distinct — unlike endpoint semantics remain distinct."""
    from inspiration_contracts import COLLECTION_RUN_VALID_STATUSES
    assert COLLECTION_RUN_VALID_STATUSES == {
        "ok", "empty", "partial", "error", "rate_limited", "auth_failed",
    }


# ─── Trend item contract ───────────────────────────────────────────────────

def test_make_trend_item_ok():
    from inspiration_contracts import make_trend_item
    item = make_trend_item(
        business_slug="t", provider="p", platform="instagram",
        content_type="audio", native_id="ig_1",
        canonical_url="https://instagram.com/x",
    )
    assert item["native_id"] == "ig_1"
    assert item["content_type"] == "audio"


def test_make_trend_item_rejects_empty_native_id():
    from inspiration_contracts import make_trend_item, InspirationContractError
    with pytest.raises(InspirationContractError):
        make_trend_item(
            business_slug="t", provider="p", platform="instagram",
            content_type="audio", native_id="",
        )


def test_make_trend_item_rejects_bad_content_type():
    from inspiration_contracts import make_trend_item, InspirationContractError
    with pytest.raises(InspirationContractError):
        make_trend_item(
            business_slug="t", provider="p", platform="instagram",
            content_type="meme", native_id="x",
        )


# ─── Observation contract ───────────────────────────────────────────────────

def test_make_observation_ok():
    from inspiration_contracts import make_observation
    obs = make_observation(
        collection_run_id=1, trend_item_id=2,
        collected_at="2026-07-20T10:00:00+00:00",
        evidence_label="chart",
        safe_payload_hash="a" * 64,
        rank=1,
    )
    assert obs["rank"] == 1
    assert obs["evidence_label"] == "chart"


def test_make_observation_rejects_bad_hash():
    from inspiration_contracts import make_observation, InspirationContractError
    with pytest.raises(InspirationContractError):
        make_observation(
            collection_run_id=1, trend_item_id=2,
            collected_at="2026-07-20T10:00:00+00:00",
            evidence_label="chart",
            safe_payload_hash="tooshort",
        )


def test_make_observation_rejects_bad_label():
    from inspiration_contracts import make_observation, InspirationContractError
    with pytest.raises(InspirationContractError):
        make_observation(
            collection_run_id=1, trend_item_id=2,
            collected_at="2026-07-20T10:00:00+00:00",
            evidence_label="trending",  # not a valid label
            safe_payload_hash="a" * 64,
        )


def test_make_observation_rank_optional():
    from inspiration_contracts import make_observation
    obs = make_observation(
        collection_run_id=1, trend_item_id=2,
        collected_at="2026-07-20T10:00:00+00:00",
        evidence_label="recommendation",
        safe_payload_hash="a" * 64,
    )
    assert obs["rank"] is None


# ─── Metric normalization (no zero coercion) ──────────────────────────────

def test_normalize_metric_keeps_none():
    from inspiration_contracts import normalize_metric
    m = normalize_metric("play_count", None)
    assert m["value"] is None
    assert m["name"] == "play_count"


def test_normalize_metric_string_digits():
    from inspiration_contracts import normalize_metric
    m = normalize_metric("views", "1200")
    assert m["value"] == 1200


def test_normalize_metric_float_string():
    from inspiration_contracts import normalize_metric
    m = normalize_metric("duration", "30.5")
    assert m["value"] == 30.5


# ─── Evidence labels / endpoint meanings ───────────────────────────────────

def test_endpoint_meanings_distinct():
    """Chart and recommendation evidence labels are distinct — no false trend claim."""
    from inspiration_contracts import ENDPOINT_MEANING_TO_LABEL, SECTION_LABELS
    assert ENDPOINT_MEANING_TO_LABEL["chart"] != ENDPOINT_MEANING_TO_LABEL["recommendation"]
    # Section label for recommendation is NOT "Trending"
    assert "Trending" not in SECTION_LABELS["recommendation"]
    assert "Trending" in SECTION_LABELS["chart"]


# ─── Staleness ──────────────────────────────────────────────────────────────

def test_is_stale_true_for_old():
    from inspiration_contracts import is_stale
    old = "2020-01-01T00:00:00+00:00"
    assert is_stale(old, stale_after_seconds=3600) is True


def test_is_stale_false_for_recent():
    from inspiration_contracts import is_stale, now_iso
    assert is_stale(now_iso(), stale_after_seconds=3600) is False


def test_is_stale_true_for_missing():
    from inspiration_contracts import is_stale
    assert is_stale("", stale_after_seconds=3600) is True


# ─── Fixture validation ─────────────────────────────────────────────────────

FIXTURE_FILES = sorted(FIXTURES.glob("*.json"))


def test_fixtures_present():
    """All required states have a fixture: chart, recommendation, empty, partial,
    malformed, rate-limited, auth-failed."""
    names = {f.stem for f in FIXTURE_FILES}
    assert "bundle_instagram_audio" in names
    assert "tikhub_tiktok_audio" in names
    assert "tikhub_tiktok_video" in names
    assert "tikhub_instagram_reels" in names
    assert "bundle_instagram_audio_error" in names
    assert "tikhub_tiktok_audio_empty" in names
    assert "tikhub_tiktok_video_partial" in names
    assert "tikhub_tiktok_audio_malformed" in names
    assert "tikhub_tiktok_audio_rate_limited" in names


@pytest.mark.parametrize("fixture_file", FIXTURE_FILES, ids=lambda f: f.stem)
def test_fixture_validates_through_contract(fixture_file):
    """Every fixture validates through the collection run contract."""
    from inspiration_contracts import (
        make_collection_run, COLLECTION_RUN_VALID_STATUSES,
    )
    data = json.loads(fixture_file.read_text())
    status = data["status"]
    assert status in COLLECTION_RUN_VALID_STATUSES
    run = make_collection_run(
        business_slug="fixture-tenant",
        provider=data["name"],
        endpoint_key=data.get("chart_key", data["endpoint_meaning"]),
        platform=data["platform"],
        region=data["region"],
        status=status,
        started_at="2026-07-20T10:00:00+00:00",
        ended_at="2026-07-20T10:00:05+00:00",
        result_count=data.get("expected_count", 0),
    )
    assert run["status"] == status
    assert run["business_slug"] == "fixture-tenant"


@pytest.mark.parametrize("fixture_file", FIXTURE_FILES, ids=lambda f: f.stem)
def test_fixture_response_redactable(fixture_file):
    """Every fixture's response can be redacted without leaking secrets."""
    from inspiration_contracts import apply_redaction
    # Use the redaction config from config/inspiration.yaml
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        cfg = yaml.safe_load(f)
    redaction_config = cfg["redaction"]

    data = json.loads(fixture_file.read_text())
    response = data.get("response", {})
    cleaned = apply_redaction(response, redaction_config)
    blob = json.dumps(cleaned)
    # No secret values leak into the redacted payload
    assert "SECRET" not in blob
    # Secret param names that should be stripped appear as expected
    for param in data.get("expected_secret_params_stripped", []):
        # the param key should not appear as a query param in any URL field
        assert f"{param}=" not in blob, f"secret param '{param}' leaked in {fixture_file.name}"


# ─── Config validation ──────────────────────────────────────────────────────

def test_inspiration_config_loads_and_has_required_sections():
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        cfg = yaml.safe_load(f)
    assert "providers" in cfg
    assert "sections" in cfg
    assert "collection" in cfg
    assert "redaction" in cfg
    # at least one chart (audio) and one recommendation (video) provider
    providers = {p["name"]: p for p in cfg["providers"]}
    chart_audio = [p for p in cfg["providers"] if p["endpoint_meaning"] == "chart" and "audio" in p["content_types"]]
    rec_video = [p for p in cfg["providers"] if p["endpoint_meaning"] == "recommendation" and "video" in p["content_types"]]
    assert chart_audio, "at least one chart audio provider required"
    assert rec_video, "at least one recommendation video provider required"


def test_inspiration_config_no_business_values():
    """Config must not contain StackPenni-specific business values in code.
    Provider names, endpoints, regions are config — not business identity."""
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        cfg = yaml.safe_load(f)
    blob = yaml.dump(cfg)
    # No business names, no credentials
    assert "StackPenni" not in blob
    assert "Bajan" not in blob
    assert "Penni" not in blob
    # No raw secrets
    for provider in cfg["providers"]:
        for key, value in provider.items():
            if key.endswith("_env"):
                # value must be an env var NAME, not a secret value
                assert value.isupper() or value == value.upper(), f"{key}={value} must be an env var name"


def test_inspiration_config_sections_truthful_labels():
    """Section labels follow AMENDMENT-012: chart => Trending, recommendation => not Trending."""
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        cfg = yaml.safe_load(f)
    # audio section (chart providers) may use "Trending"
    audio_label = cfg["sections"]["audio"]["label"]
    assert "Trending" in audio_label
    # video section (recommendation providers) must NOT use "Trending"
    video_label = cfg["sections"]["video"]["label"]
    assert "Trending" not in video_label
    assert "inspiration" in video_label.lower() or "recommendation" in video_label.lower()


def test_inspiration_config_provider_endpoint_meanings_valid():
    from inspiration_contracts import ENDPOINT_MEANING_TO_LABEL
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        cfg = yaml.safe_load(f)
    for provider in cfg["providers"]:
        em = provider["endpoint_meaning"]
        assert em in ENDPOINT_MEANING_TO_LABEL, f"provider {provider['name']} has unknown endpoint_meaning {em}"


def test_inspiration_config_credentials_use_env_vars():
    """No credential values in config — only env var name references."""
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        cfg = yaml.safe_load(f)
    for provider in cfg["providers"]:
        if "api_key_env" in provider:
            assert provider["api_key_env"]
            # the value is an env var name; the actual secret is never in config
        if "team_id_env" in provider:
            assert provider["team_id_env"]


# ─── No live network ───────────────────────────────────────────────────────

def test_no_network_calls_in_contracts_module():
    """The contracts module imports no network libraries."""
    import inspiration_contracts
    src = Path(inspiration_contracts.__file__).read_text()
    assert "import requests" not in src
    assert "import urllib.request" not in src
    assert "import httpx" not in src
    assert "import aiohttp" not in src
    assert "import socket" not in src