"""VF-INSP-004 — Deployed live-provider first-slice proof (pytest half).

The live smoke (scripts/inspiration_live_smoke.py) is separate from pytest.
These tests verify the offline-proof path: disable provider network and prove
/inspiration renders the persisted snapshot with no secrets.

AC (from BUILD_PLAN):
  - live smoke is separate from pytest (this file proves the offline half)
  - auth/rate errors are plain-language and non-destructive
  - operator can play available examples and explain why/when each appears
  - full automated suite passes against fixtures
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
FIXTURES = Path(__file__).parent / "fixtures" / "inspiration"


@pytest.fixture()
def seeded_client(tmp_path):
    """Flask test client with seeded data, simulating a post-collection DB."""
    from app import create_app
    from inspiration_store import InspirationStore, run_collection
    import yaml

    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)
    repo_config = Path(__file__).parent.parent / "config"
    for f in ("business.yaml", "models.yaml", "sources.yaml", "processes.yaml", "inspiration.yaml", "soundtrack_review.yaml"):
        src = repo_config / f
        if src.exists():
            (Path(config_dir) / f).write_text(src.read_text())

    db_path = str(tmp_path / "test.db")
    app = create_app(config_dir=config_dir, db_path=db_path)
    store = InspirationStore(db_path)
    insp_config = yaml.safe_load(open(Path(config_dir) / "inspiration.yaml"))

    # Seed all four providers
    provider_map = {p["name"]: p for p in insp_config["providers"]}
    for name, stem, extras in [
        ("bundle_social_instagram_audio", "bundle_instagram_audio", {"audio_type": "music"}),
        ("tikhub_tiktok_audio_charts", "tikhub_tiktok_audio", {"chart_key": "top_50", "chart_label": "TikTok Top 50"}),
        ("tikhub_tiktok_video_feed", "tikhub_tiktok_video", {}),
        ("tikhub_instagram_reels", "tikhub_instagram_reels", {}),
    ]:
        pconf = dict(provider_map[name], **extras)
        fixture = json.loads((FIXTURES / f"{stem}.json").read_text())
        run_collection(business_slug="stackpenni", provider_config=pconf,
                       redaction_config=insp_config["redaction"], store=store,
                       response_override=fixture["response"])

    return app.test_client(), db_path, config_dir


# ─── Offline render: network disabled, page reads DB ────────────────────────

def test_page_renders_with_network_blocked(seeded_client, monkeypatch):
    """With provider network disabled, /inspiration renders the persisted snapshot."""
    import inspiration_store
    import requests

    call_count = {"n": 0}
    def _block(*a, **kw):
        call_count["n"] += 1
        raise ConnectionError("blocked")
    monkeypatch.setattr(requests, "get", _block)
    monkeypatch.setattr(inspiration_store, "_http_get", _block)

    client, db_path, config_dir = seeded_client
    resp = client.get("/inspiration")
    assert resp.status_code == 200
    assert call_count["n"] == 0, "Network call during render with network blocked!"
    html = resp.data.decode()
    # Persisted data is visible
    assert "Example Trending Track One" in html or "Example TikTok Track One" in html


def test_page_renders_after_auth_failure(seeded_client, monkeypatch):
    """A provider auth failure leaves prior data visible — non-destructive."""
    import sqlite3
    client, db_path, config_dir = seeded_client
    # Insert an auth_failed run for one provider (simulating live failure)
    conn = sqlite3.connect(db_path)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO insp_collection_runs
           (business_slug, provider, endpoint_key, platform, region, status,
            started_at, ended_at, request_params, result_count, response_hash,
            adapter_version, error_class, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', 0, '', 'inspiration-v1', 'AuthError', 'credential unavailable')""",
        ("stackpenni", "bundle_social_instagram_audio", "chart", "instagram", "global",
         "auth_failed", ts, ts),
    )
    conn.commit()
    conn.close()
    resp = client.get("/inspiration")
    assert resp.status_code == 200
    html = resp.data.decode()
    # Prior data from other providers still visible
    assert "tiktok" in html.lower()
    # No green success for the failed provider
    # (the section may show stale or error state, but not a green "ok")


def test_auth_error_is_plain_language(seeded_client):
    """Auth/rate errors are plain-language and non-destructive."""
    import sqlite3
    client, db_path, config_dir = seeded_client
    conn = sqlite3.connect(db_path)
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO insp_collection_runs
           (business_slug, provider, endpoint_key, platform, region, status,
            started_at, ended_at, request_params, result_count, response_hash,
            adapter_version, error_class, error_message)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, '{}', 0, '', 'inspiration-v1', 'RateLimitError', 'Rate limit exceeded')""",
        ("stackpenni", "tikhub_tiktok_audio_charts", "viral_50", "tiktok", "global",
         "rate_limited", ts, ts),
    )
    conn.commit()
    conn.close()
    resp = client.get("/inspiration")
    assert resp.status_code == 200
    html = resp.data.decode()
    # No raw HTTP status codes or jargon rendered as primary copy
    assert "HTTP 429" not in html
    assert "stack trace" not in html.lower()


# ─── Operator can explain why/when each item appears ─────────────────────────

def test_items_show_collection_context(seeded_client):
    """Each item shows provider, platform, region, collection time, and evidence label
    so the operator can explain why and when each appears."""
    client, *_ = seeded_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "via " in html  # provider attribution
    assert "collected" in html.lower()  # collection time
    # Evidence labels visible
    assert "chart" in html.lower() or "recommendation" in html.lower()


def test_playable_examples_present(seeded_client):
    """Operator can play available examples (preview link when URL exists)."""
    client, *_ = seeded_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "Play preview" in html or "play preview" in html.lower()


# ─── No credentials or raw secret URLs in DB or rendered page ────────────────

def test_no_credentials_in_db(seeded_client):
    """The persisted DB contains no API keys or secret values."""
    import sqlite3
    client, db_path, config_dir = seeded_client
    conn = sqlite3.connect(db_path)
    for table in ("insp_collection_runs", "insp_trend_items", "insp_observations"):
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        for row in rows:
            for val in row:
                if isinstance(val, str):
                    assert "SECRET" not in val
                    assert "token=" not in val.lower()
                    # No actual API key values (env var names are ok in config, not in DB)
                    assert "x-api-key" not in val.lower()
    conn.close()


def test_no_credentials_in_rendered_page(seeded_client):
    client, *_ = seeded_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "SECRET" not in html
    assert "api_key" not in html.lower()


# ─── Full suite passes against fixtures ─────────────────────────────────────

def test_fixture_based_collection_complete(seeded_client):
    """All four fixture-based providers collected successfully (simulating live)."""
    import sqlite3
    client, db_path, config_dir = seeded_client
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT provider, status, result_count FROM insp_collection_runs ORDER BY provider"
    ).fetchall()
    conn.close()
    # Four providers collected
    providers = {r[0] for r in rows}
    assert "bundle_social_instagram_audio" in providers
    assert "tikhub_tiktok_audio_charts" in providers
    assert "tikhub_tiktok_video_feed" in providers
    assert "tikhub_instagram_reels" in providers
    # All have a valid status
    for r in rows:
        assert r[1] in ("ok", "empty", "partial")


# ─── Live smoke script exists and is separate ──────────────────────────────

def test_live_smoke_script_exists():
    """The live smoke script exists at scripts/inspiration_live_smoke.py and is
    separate from the pytest suite."""
    script = Path(__file__).parent.parent / "scripts" / "inspiration_live_smoke.py"
    assert script.exists(), "Live smoke script not found"
    content = script.read_text()
    # It must not be imported by pytest — it's a standalone script
    assert 'if __name__ == "__main__"' in content
    # It loads credentials from env, not from code
    assert "/etc/viralfactory/env" in content or "env_file" in content
    # It verifies the offline render path
    assert "verify_page_renders_from_db" in content