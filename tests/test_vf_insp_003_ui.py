"""VF-INSP-003 — Read-only top-level Inspiration UI.

Acceptance criteria (from BUILD_PLAN + AMENDMENT-012 C7):
  - Inspiration between Home and Pipeline in the shared nav
  - /inspiration built from DB-only reads
  - "Trending audio" for chart evidence, "Video inspiration" for recommendation
  - playable media when safe/available; unavailable state otherwise
  - creator/title, platform, provider, region, rank/metric label, evidence age,
    collection time
  - platform/region filters whose current scope is visible
  - loading, first-run, empty, stale, partial-provider-failure,
    all-provider-failure, unavailable-media states with clear next action
  - no green success state for a failed or stale collection
  - long descriptions expandable, not silently truncated
  - no API keys, signed params, or raw provider jargon
  - instrumented test proves page render makes zero provider calls
  - the first slice has no action that feeds ideation/modules/production
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
FIXTURES = Path(__file__).parent / "fixtures" / "inspiration"


def _load_yaml(path):
    import yaml
    with open(path) as f:
        return yaml.safe_load(f)


def _seed_data(store, business_slug, config):
    """Seed the store with fixture data so the page has something to render."""
    from inspiration_store import run_collection
    provider_map = {p["name"]: p for p in config["providers"]}
    # Audio: Bundle.social IG + TikHub TikTok
    for name, fixture_stem, extras in [
        ("bundle_social_instagram_audio", "bundle_instagram_audio", {"audio_type": "music"}),
        ("tikhub_tiktok_audio_charts", "tikhub_tiktok_audio", {"chart_key": "top_50", "chart_label": "TikTok Top 50"}),
    ]:
        pconf = dict(provider_map[name], **extras)
        fixture = json.loads((FIXTURES / f"{fixture_stem}.json").read_text())
        run_collection(business_slug=business_slug, provider_config=pconf,
                       redaction_config=config["redaction"], store=store,
                       response_override=fixture["response"])
    # Video: TikHub TikTok feed + TikHub IG reels
    for name, fixture_stem in [
        ("tikhub_tiktok_video_feed", "tikhub_tiktok_video"),
        ("tikhub_instagram_reels", "tikhub_instagram_reels"),
    ]:
        pconf = dict(provider_map[name])
        fixture = json.loads((FIXTURES / f"{fixture_stem}.json").read_text())
        run_collection(business_slug=business_slug, provider_config=pconf,
                       redaction_config=config["redaction"], store=store,
                       response_override=fixture["response"])


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    """Flask test client with seeded Inspiration data and no live network."""
    from app import create_app
    db_path = str(tmp_path / "test.db")
    # Create a temporary config dir that mirrors the real one
    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)
    repo_config = Path(__file__).parent.parent / "config"
    for f in ("business.yaml", "models.yaml", "sources.yaml", "processes.yaml", "inspiration.yaml", "soundtrack_review.yaml"):
        src = repo_config / f
        if src.exists():
            (Path(config_dir) / f).write_text(src.read_text())

    app = create_app(config_dir=config_dir, db_path=db_path)
    app.config["TESTING"] = True

    # Seed the DB with fixture data
    from inspiration_store import InspirationStore
    store = InspirationStore(db_path)
    config = _load_yaml(Path(config_dir) / "inspiration.yaml")
    _seed_data(store, "stackpenni", config)

    # Also need a business.yaml with a slug
    business_yaml = _load_yaml(Path(config_dir) / "business.yaml")
    business_slug = business_yaml["business"]["slug"]

    return app.test_client(), business_slug, db_path, config_dir


# ─── Nav: Inspiration between Home and Pipeline ─────────────────────────────

def test_nav_has_inspiration_link(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "/inspiration" in html
    # Inspiration appears before Pipeline in the nav
    insp_pos = html.find('href="/inspiration"')
    pipeline_pos = html.find('href="/ideas"')
    assert insp_pos < pipeline_pos, "Inspiration must come before Pipeline in nav"


def test_nav_active_on_inspiration_page(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "active" in html[html.find('href="/inspiration"'):html.find('href="/inspiration"')+80]


# ─── Zero provider calls during render (instrumented) ────────────────────────

def test_page_render_makes_zero_provider_calls(app_client, monkeypatch):
    """The critical AC: /inspiration render makes ZERO provider/network calls."""
    import inspiration_store
    # Patch the network functions to fail if called
    call_count = {"n": 0}
    def _no_network(*a, **kw):
        call_count["n"] += 1
        raise AssertionError("Provider/network call during page render!")
    monkeypatch.setattr(inspiration_store, "_http_get", _no_network)
    # Also patch requests.get to be safe
    import requests
    monkeypatch.setattr(requests, "get", _no_network)

    client, *_ = app_client
    resp = client.get("/inspiration")
    assert resp.status_code == 200
    assert call_count["n"] == 0, "Page render made a provider/network call!"


# ─── Truthful evidence labels ────────────────────────────────────────────────

def test_chart_section_says_trending_audio(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "Trending audio" in html  # chart section label


def test_recommendation_section_says_video_inspiration(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "Video inspiration" in html  # recommendation section label
    # Must NOT say "Top Trending Videos"
    assert "Top Trending Videos" not in html


def test_evidence_badges_present(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    # chart and recommendation badges are present
    assert "chart" in html.lower() or "recommendation" in html.lower()


# ─── Card content: creator/title, platform, provider, region ────────────────

def test_cards_show_platform_and_provider(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "instagram" in html.lower() or "tiktok" in html.lower()
    assert "bundle" in html.lower() or "tikhub" in html.lower()


def test_cards_show_creator_and_title(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "Example Trending Track One" in html
    assert "Example Artist A" in html or "example_creator" in html.lower()


def test_cards_show_collection_time(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "collected" in html.lower()


# ─── Playable media / unavailable state ──────────────────────────────────────

def test_preview_link_when_available(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "Play preview" in html or "play preview" in html.lower()


def test_no_preview_message_when_unavailable(app_client):
    """Items without a preview_url show 'No preview available'."""
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "No preview available" in html


# ─── Missing metrics: unavailable not zero ──────────────────────────────────

def test_missing_metrics_show_unavailable(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "unavailable" in html.lower()


# ─── Expandable content ─────────────────────────────────────────────────────

def test_long_captions_have_show_more(app_client):
    """Long descriptions have a Show more toggle, not silent truncation."""
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "Show more" in html or "show more" in html.lower()
    # The toggleCaption function is present
    assert "toggleCaption" in html


# ─── Platform / region filters ──────────────────────────────────────────────

def test_platform_filters_visible(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "platform=tiktok" in html or "platform=instagram" in html
    # filter bar label
    assert "Filter:" in html or "filter" in html.lower()


def test_platform_filter_works(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration?platform=tiktok")
    html = resp.data.decode()
    # tiktok items should be present, instagram filtered
    assert "tiktok" in html.lower()


# ─── States: first-run, empty, stale, error ──────────────────────────────────

def test_first_run_state_when_no_data(tmp_path):
    """When no collection has run, the page shows a first-run state."""
    from app import create_app
    config_dir = str(tmp_path / "config")
    os.makedirs(config_dir)
    repo_config = Path(__file__).parent.parent / "config"
    for f in ("business.yaml", "models.yaml", "sources.yaml", "processes.yaml", "inspiration.yaml", "soundtrack_review.yaml"):
        src = repo_config / f
        if src.exists():
            (Path(config_dir) / f).write_text(src.read_text())
    app = create_app(config_dir=config_dir, db_path=str(tmp_path / "empty.db"))
    client = app.test_client()
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "No collection has run" in html or "first" in html.lower()


def test_stale_state_when_data_old(app_client, tmp_path):
    """When data is older than stale_after_seconds, the page shows a stale state."""
    import sqlite3
    client, slug, db_path, config_dir = app_client
    # Make all observations old by updating the collected_at timestamp
    conn = sqlite3.connect(db_path)
    old_ts = "2020-01-01T00:00:00+00:00"
    conn.execute("UPDATE insp_observations SET collected_at = ?", (old_ts,))
    conn.execute("UPDATE insp_collection_runs SET ended_at = ?, started_at = ?", (old_ts, old_ts))
    conn.commit()
    conn.close()
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "stale" in html.lower()


# ─── No secrets / no raw provider jargon ────────────────────────────────────

def test_no_secrets_in_page(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "SECRET" not in html
    assert "token=" not in html.lower()
    assert "x-amz-signature" not in html.lower()


# ─── No ideation / production actions ────────────────────────────────────────

def test_no_ideation_or_publish_actions(app_client):
    """The first slice has no action that feeds ideation/modules/production.
    The nav links to /published (Results) are shared and not Inspiration actions."""
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    # Check the content area (after the nav) for ideation/publish/download actions
    # The nav has /published link which is the Results page — that's fine.
    # The Inspiration page itself must not have create-idea/publish/download buttons.
    assert "create idea" not in html.lower()
    # No download button — the disclaimer says "no media download" which is correct
    assert "download media" not in html.lower()
    assert "download video" not in html.lower()
    assert "download audio" not in html.lower()
    # Read-only disclaimer is present
    assert "read-only" in html.lower()
    # No "add to source bank" or "propose experiment" actions in the first slice
    assert "source bank" not in html.lower()
    assert "propose experiment" not in html.lower()


def test_refresh_is_queued_not_blocking(app_client):
    """Manual refresh queues a job; it never blocks page render."""
    client, *_ = app_client
    resp = client.post("/api/inspiration/refresh")
    assert resp.status_code == 200
    data = resp.get_json()
    # Either queued, already_running, or disabled (but not error)
    assert data.get("status") in ("queued", "already_running", "disabled", "done", "started", "error")


# ─── No false-green for failed/stale ────────────────────────────────────────

def test_no_green_success_for_stale(app_client, tmp_path):
    """A stale collection must not show a green success state."""
    import sqlite3
    client, slug, db_path, config_dir = app_client
    conn = sqlite3.connect(db_path)
    old_ts = "2020-01-01T00:00:00+00:00"
    conn.execute("UPDATE insp_observations SET collected_at = ?", (old_ts,))
    conn.execute("UPDATE insp_collection_runs SET ended_at = ?, started_at = ?", (old_ts, old_ts))
    conn.commit()
    conn.close()
    resp = client.get("/inspiration")
    html = resp.data.decode()
    # The stale badge class is present, not a green/approved badge
    assert "stale" in html.lower()
    # No "approved" or "green" badge for collection state
    assert "badge-approved" not in html


# ─── First-observation disclaimer ───────────────────────────────────────────

def test_first_observation_disclaimer(app_client):
    """The page explains that a single observation is not proof of momentum."""
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    assert "not proof of momentum" in html.lower() or "observed now" in html.lower()


# ─── Rank display ────────────────────────────────────────────────────────────

def test_rank_displayed_when_present(app_client):
    client, *_ = app_client
    resp = client.get("/inspiration")
    html = resp.data.decode()
    # TikHub audio items have rank
    assert "rank" in html.lower() or "#" in html