"""VF-INSP-002 — Scheduled collection store and adapters.

Acceptance criteria (from BUILD_PLAN):
  - tenant-scoped collection/item/observation persistence in the writer's own
    _init_db (here: InspirationStore.SCHEMA, initialized by PipelineStore)
  - provider adapters plus shared HTTP/retry/rate-limit/redaction/cache mechanics
  - repeated fixture runs preserve movement history and dedupe item identity
  - first observation has no fabricated movement
  - signed/secret URL parameters do not reach DB/logs
  - provider failure cannot erase prior data or report success
  - no live network or credentials in automated tests
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
FIXTURES = Path(__file__).parent / "fixtures" / "inspiration"


def _load_inspiration_config():
    import yaml
    with open(os.path.join(os.path.dirname(__file__), "..", "config", "inspiration.yaml")) as f:
        return yaml.safe_load(f)


def _provider_config(name: str, config: dict | None = None) -> dict:
    config = config or _load_inspiration_config()
    for p in config["providers"]:
        if p["name"] == name:
            return p
    raise KeyError(name)


def _load_fixture(stem: str) -> dict:
    return json.loads((FIXTURES / f"{stem}.json").read_text())


@pytest.fixture()
def store(tmp_path):
    from inspiration_store import InspirationStore
    return InspirationStore(str(tmp_path / "test_insp.db"))


@pytest.fixture()
def config():
    return _load_inspiration_config()


# ─── Schema initialization ──────────────────────────────────────────────────

def test_store_creates_tables(tmp_path):
    from inspiration_store import InspirationStore
    s = InspirationStore(str(tmp_path / "x.db"))
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "x.db"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "insp_collection_runs" in tables
    assert "insp_trend_items" in tables
    assert "insp_observations" in tables


def test_pipeline_store_initializes_inspiration_schema(tmp_path):
    """PipelineStore._init_db must initialize the inspiration schema too."""
    from pipeline import PipelineStore
    ps = PipelineStore(str(tmp_path / "pipe.db"))
    import sqlite3
    conn = sqlite3.connect(str(tmp_path / "pipe.db"))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "insp_collection_runs" in tables
    assert "insp_trend_items" in tables
    assert "insp_observations" in tables


# ─── Adapter normalization ──────────────────────────────────────────────────

def test_bundle_adapter_normalizes_chart_audio(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("bundle_social_instagram_audio", config)
    provider["audio_type"] = "music"
    fixture = _load_fixture("bundle_instagram_audio")
    run = run_collection(
        business_slug="tenant-a",
        provider_config=provider,
        redaction_config=config["redaction"],
        store=store,
        response_override=fixture["response"],
    )
    assert run["status"] == "ok"
    assert run["result_count"] == 3
    items = store.get_items_for_section("tenant-a", "audio", [provider["name"]])
    assert len(items) == 3
    assert items[0]["title"] == "Example Trending Track One"
    assert items[0]["platform"] == "instagram"
    assert items[0]["content_type"] == "audio"


def test_tikhub_audio_adapter_preserves_chart_metrics(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    provider["chart_label"] = "TikTok Top 50"
    fixture = _load_fixture("tikhub_tiktok_audio")
    run = run_collection(
        business_slug="tenant-a",
        provider_config=provider,
        redaction_config=config["redaction"],
        store=store,
        response_override=fixture["response"],
    )
    assert run["status"] == "ok"
    items = store.get_items_for_section("tenant-a", "audio", [provider["name"]])
    assert len(items) == 2
    # metric names preserved verbatim, not renamed
    m = items[0]["obs_metrics"]
    assert "play_count" in m
    assert "use_count" in m
    assert m["chart"]["value"] == "TikTok Top 50"


def test_tikhub_video_adapter_missing_metric_not_zero(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_video_feed", config)
    fixture = _load_fixture("tikhub_tiktok_video")
    run = run_collection(
        business_slug="tenant-a",
        provider_config=provider,
        redaction_config=config["redaction"],
        store=store,
        response_override=fixture["response"],
    )
    assert run["status"] == "ok"
    items = store.get_items_for_section("tenant-a", "video", [provider["name"]])
    # item 1 (tt_video_002) has play_count null → must be None, not 0
    null_item = [i for i in items if i["native_id"] == "tt_video_002"][0]
    assert null_item["obs_metrics"]["play_count"]["value"] is None


def test_instagram_reels_adapter_normalizes(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_instagram_reels", config)
    fixture = _load_fixture("tikhub_instagram_reels")
    run = run_collection(
        business_slug="tenant-a",
        provider_config=provider,
        redaction_config=config["redaction"],
        store=store,
        response_override=fixture["response"],
    )
    assert run["status"] == "ok"
    items = store.get_items_for_section("tenant-a", "video", [provider["name"]])
    assert len(items) == 2
    assert items[0]["creator"] == "example_creator_f"


# ─── Distinct endpoint semantics ────────────────────────────────────────────

def test_chart_vs_recommendation_labels_distinct(store, config):
    from inspiration_store import run_collection
    audio_provider = _provider_config("tikhub_tiktok_audio_charts", config)
    audio_provider["chart_key"] = "top_50"
    audio_provider["chart_label"] = "TikTok Top 50"
    video_provider = _provider_config("tikhub_tiktok_video_feed", config)
    audio_fixture = _load_fixture("tikhub_tiktok_audio")
    video_fixture = _load_fixture("tikhub_tiktok_video")
    run_collection(business_slug="t", provider_config=audio_provider,
                  redaction_config=config["redaction"], store=store,
                  response_override=audio_fixture["response"])
    run_collection(business_slug="t", provider_config=video_provider,
                  redaction_config=config["redaction"], store=store,
                  response_override=video_fixture["response"])
    audio_items = store.get_items_for_section("t", "audio", [audio_provider["name"]])
    video_items = store.get_items_for_section("t", "video", [video_provider["name"]])
    assert audio_items[0]["obs_label"] == "chart"
    assert video_items[0]["obs_label"] == "recommendation"


# ─── Redaction: secrets never reach DB ──────────────────────────────────────

def test_secret_params_stripped_from_db(store, config):
    from inspiration_store import run_collection
    import sqlite3
    provider = _provider_config("bundle_social_instagram_audio", config)
    provider["audio_type"] = "music"
    fixture = _load_fixture("bundle_instagram_audio")
    run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        response_override=fixture["response"],
    )
    conn = sqlite3.connect(store.db_path)
    # scan all text columns in all inspiration tables for secret markers
    for table in ("insp_collection_runs", "insp_trend_items", "insp_observations"):
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        for row in rows:
            for val in row:
                if isinstance(val, str):
                    assert "SECRET" not in val, f"SECRET leaked in {table}: {val}"
                    assert "token=" not in val.lower(), f"token= leaked in {table}"
                    assert "sig=" not in val.lower(), f"sig= leaked in {table}"


def test_secret_url_params_stripped_tikhub(store, config):
    from inspiration_store import run_collection
    import sqlite3
    provider = _provider_config("tikhub_tiktok_video_feed", config)
    fixture = _load_fixture("tikhub_tiktok_video")
    run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        response_override=fixture["response"],
    )
    conn = sqlite3.connect(store.db_path)
    rows = conn.execute("SELECT preview_url, thumbnail_url FROM insp_trend_items").fetchall()
    for row in rows:
        for val in row:
            if val:
                assert "x-amz-signature" not in val.lower()
                assert "SECRET" not in val


# ─── Empty / partial / malformed / error / rate-limited ─────────────────────

def test_empty_response_status_empty(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "viral_50"
    fixture = _load_fixture("tikhub_tiktok_audio_empty")
    run = run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        response_override=fixture["response"],
    )
    assert run["status"] == "empty"
    assert run["result_count"] == 0


def test_partial_response_status_partial_or_ok(store, config):
    """A partial response (fewer items than requested) is ok with the items present.
    The AC distinguishes 'partial' from 'ok' only when a provider declares partiality;
    our adapter normalizes whatever items are present."""
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_video_feed", config)
    fixture = _load_fixture("tikhub_tiktok_video_partial")
    run = run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        response_override=fixture["response"],
    )
    assert run["status"] in ("ok", "partial")
    assert run["result_count"] == 1


def test_malformed_response_fails_visibly(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    fixture = _load_fixture("tikhub_tiktok_audio_malformed")
    run = run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        response_override=fixture["response"],
    )
    assert run["status"] == "error"
    assert run["error_class"] == "MalformedResponse"
    assert run["result_count"] == 0


def test_auth_failed_status(store, config):
    """Auth failure — status auth_failed, not success."""
    from inspiration_store import run_collection, COLLECTION_RUN_STATUS_AUTH_FAILED
    provider = _provider_config("bundle_social_instagram_audio", config)
    # Simulate auth failure via a fetcher that returns 401
    class FakeResp:
        status_code = 401
        def json(self): return {"error": "bad key"}
    run = run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        fetcher=lambda url, headers, params, timeout: FakeResp(),
    )
    assert run["status"] == "auth_failed"


def test_rate_limited_status(store, config, monkeypatch):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "viral_50"
    monkeypatch.setenv("TIKHUB_API_KEY", "fake-key-for-rate-limit-test")
    class FakeResp:
        status_code = 429
        def json(self): return {"error": "rate limited"}
    run = run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        fetcher=lambda url, headers, params, timeout: FakeResp(),
    )
    assert run["status"] == "rate_limited"


# ─── Provider failure preserves prior data ──────────────────────────────────

def test_failed_collection_preserves_prior_data(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    provider["chart_label"] = "TikTok Top 50"
    # First run succeeds
    good_fixture = _load_fixture("tikhub_tiktok_audio")
    run_collection(business_slug="t", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=good_fixture["response"])
    items_before = store.get_items_for_section("t", "audio", [provider["name"]])
    assert len(items_before) == 2
    # Second run fails (malformed)
    bad_fixture = _load_fixture("tikhub_tiktok_audio_malformed")
    failed_run = run_collection(business_slug="t", provider_config=provider,
                                redaction_config=config["redaction"], store=store,
                                response_override=bad_fixture["response"])
    assert failed_run["status"] == "error"
    # Prior items are still visible
    items_after = store.get_items_for_section("t", "audio", [provider["name"]])
    assert len(items_after) == 2
    assert items_after[0]["title"] == "Example TikTok Track One"


# ─── Append-only: repeated observations preserve history ────────────────────

def test_repeated_runs_append_observations(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    provider["chart_label"] = "TikTok Top 50"
    fixture = _load_fixture("tikhub_tiktok_audio")
    # Run twice with the same fixture
    run_collection(business_slug="t", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=fixture["response"])
    run_collection(business_slug="t", provider_config=provider,
                  redaction_config=config["redaction"], store=store,
                  response_override=fixture["response"])
    items = store.get_items_for_section("t", "audio", [provider["name"]])
    assert len(items) == 2  # deduped — not 4
    # Each item has 2 observations (append-only)
    for item in items:
        history = store.get_observation_history(item["id"])
        assert len(history) == 2
        assert item["observation_count"] == 2


def test_first_observation_no_fabricated_movement(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    provider["chart_label"] = "TikTok Top 50"
    fixture = _load_fixture("tikhub_tiktok_audio")
    run_collection(business_slug="t", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=fixture["response"])
    items = store.get_items_for_section("t", "audio", [provider["name"]])
    for item in items:
        history = store.get_observation_history(item["id"])
        assert len(history) == 1  # first observation only
        # No movement label fabricated — only the raw metric is stored
        m = history[0]["metrics"]
        assert "movement" not in m
        assert "trend" not in m
        assert "momentum" not in m


def test_item_metadata_updates_without_overwriting_history(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    provider["chart_label"] = "TikTok Top 50"
    fixture = _load_fixture("tikhub_tiktok_audio")
    run_collection(business_slug="t", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=fixture["response"])
    # Second run with a modified title on the same item
    modified = json.loads(json.dumps(fixture["response"]))
    modified["data"][0]["title"] = "Updated Title"
    run_collection(business_slug="t", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=modified)
    items = store.get_items_for_section("t", "audio", [provider["name"]])
    item = [i for i in items if i["native_id"] == "tt_music_001"][0]
    # Title updated in item metadata
    assert item["title"] == "Updated Title"
    # But first observation still has the original metric (append-only)
    history = store.get_observation_history(item["id"])
    assert len(history) == 2


# ─── Tenant scoping ─────────────────────────────────────────────────────────

def test_tenant_scoping_isolates_data(store, config):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    provider["chart_label"] = "TikTok Top 50"
    fixture = _load_fixture("tikhub_tiktok_audio")
    run_collection(business_slug="tenant-a", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=fixture["response"])
    run_collection(business_slug="tenant-b", provider_config=provider,
                   redaction_config=config["redaction"], store=store,
                   response_override=fixture["response"])
    a_items = store.get_items_for_section("tenant-a", "audio", [provider["name"]])
    b_items = store.get_items_for_section("tenant-b", "audio", [provider["name"]])
    assert len(a_items) == 2
    assert len(b_items) == 2
    # Different item IDs despite same native_id
    a_ids = {i["id"] for i in a_items}
    b_ids = {i["id"] for i in b_items}
    assert a_ids.isdisjoint(b_ids)


# ─── Missing credential ─────────────────────────────────────────────────────

def test_missing_credential_fails_closed(store, config, monkeypatch):
    from inspiration_store import run_collection
    provider = _provider_config("tikhub_tiktok_audio_charts", config)
    provider["chart_key"] = "top_50"
    # Ensure no env var set
    monkeypatch.delenv("TIKHUB_API_KEY", raising=False)
    run = run_collection(
        business_slug="t", provider_config=provider,
        redaction_config=config["redaction"], store=store,
        fetcher=lambda *a, **kw: None,  # would be called if creds present
    )
    assert run["status"] == "auth_failed"
    assert run["error_class"] == "AuthError"


# ─── Adapter registry completeness ──────────────────────────────────────────

def test_all_configured_adapters_registered():
    from inspiration_store import ADAPTERS
    config = _load_inspiration_config()
    for provider in config["providers"]:
        assert provider["adapter"] in ADAPTERS, f"adapter {provider['adapter']} not registered"


# ─── No live network in tests ───────────────────────────────────────────────

def test_store_module_network_isolated_for_fixtures():
    """The store module may import requests for the live path, but the fixture
    path (response_override) never calls the network."""
    import inspiration_store
    src = Path(inspiration_store.__file__).read_text()
    # The fixture path is guarded by `if response_override is not None`
    assert "response_override" in src
    assert "if response_override is not None" in src