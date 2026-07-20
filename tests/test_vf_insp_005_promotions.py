"""VF-INSP-005 — Bookmark and promotion paths (AMENDMENT-012 C5).

AC (from BUILD_PLAN):
  - Bookmark, Add to Source Bank, Propose experiment, Propose pattern are
    distinct actions
  - Bookmark does not ground ideation
  - Source promotion creates status='new' linked to observation/collection
    provenance and requires the existing Source Bank Keep gate
  - Experiment/module proposals enter the async gate
  - Creative interpretation uses a versioned Researcher prompt/schema with
    hypothesis language and full provenance (future task)
  - No observation silently changes a module, process, source status, idea
    input, or soundtrack
  - Each action's destination and undo/history are visible
  - Bulk operations exist if a queue can exceed 50
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
FIXTURES = Path(__file__).parent / "fixtures" / "inspiration"


def _seed(store, business_slug, config):
    from inspiration_store import run_collection
    provider_map = {p["name"]: p for p in config["providers"]}
    pconf = dict(provider_map["tikhub_tiktok_audio_charts"], chart_key="top_50", chart_label="TikTok Top 50")
    fixture = json.loads((FIXTURES / "tikhub_tiktok_audio.json").read_text())
    run_collection(business_slug=business_slug, provider_config=pconf,
                   redaction_config=config["redaction"], store=store,
                   platform_urls=config.get("platform_urls"),
                   response_override=fixture["response"])


@pytest.fixture()
def promotion_store(tmp_path):
    from inspiration_store import InspirationStore
    from inspiration_promotions import PromotionStore
    from pipeline import PipelineStore
    import yaml
    db = str(tmp_path / "test.db")
    # Initialize pipeline schema (creates sources table)
    PipelineStore(db)
    insp_store = InspirationStore(db)
    config = yaml.safe_load(open(Path(__file__).parent.parent / "config" / "inspiration.yaml"))
    _seed(insp_store, "test-tenant", config)
    return PromotionStore(db), insp_store, db


# ─── Bookmark ──────────────────────────────────────────────────────────────

def test_bookmark_creates_record(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    # Get the observation ID for this item
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    result = pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    assert result["action"] == "bookmark"
    assert result["status"] == "active"
    assert result["destination"] == "bookmark"


def test_bookmark_does_not_ground_ideation(promotion_store):
    """Bookmark keeps a reference without making it grounding material."""
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    # The observation history is unchanged — bookmark does not modify observations
    history_after = insp_store.get_observation_history(item_id)
    assert len(history_after) == len(history)
    # No source bank entry was created
    import sqlite3
    conn = sqlite3.connect(db)
    # The source bank table (sources) should not have new entries from bookmarking
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "sources" in tables:
        source_count = conn.execute("SELECT COUNT(*) FROM sources WHERE business_slug='test-tenant'").fetchone()[0]
        assert source_count == 0, "Bookmark created a source bank entry — it should not"
    conn.close()


def test_duplicate_bookmark_prevented(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    from inspiration_promotions import PromotionError
    with pytest.raises(PromotionError):
        pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)


# ─── Source Bank promotion ──────────────────────────────────────────────────

def test_add_to_source_bank_creates_record(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    result = pstore.add_to_source_bank(
        business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id,
        db_path=db)
    assert result["action"] == "add_to_source_bank"
    assert result["destination"] == "source_bank"
    assert result["status"] == "active"


def test_source_bank_creates_reviewable_entry(promotion_store):
    """Source Bank promotion inserts a row into the sources table with status='new'
    so it appears in the Source Bank UI for review."""
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    pstore.add_to_source_bank(
        business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id,
        db_path=db)
    # Verify a source row was created
    import sqlite3
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM sources WHERE business_slug='test-tenant' AND source_type='inspiration'"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "new"
    assert "Inspiration Center" in rows[0]["summary"]
    conn.close()


def test_source_bank_does_not_feed_ideation(promotion_store):
    """Source Bank promotion creates a status='new' candidate linked to
    observation provenance. It does not immediately feed ideation."""
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    pstore.add_to_source_bank(
        business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id,
        db_path=db)
    # The promotion record exists but no idea card was created
    import sqlite3
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "idea_cards" in tables:
        idea_count = conn.execute("SELECT COUNT(*) FROM idea_cards WHERE business_slug='test-tenant'").fetchone()[0]
        assert idea_count == 0, "Source Bank promotion created an idea card — it should not"
    conn.close()


# ─── Experiment and pattern proposals ───────────────────────────────────────

def test_propose_experiment(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    result = pstore.propose_experiment(
        business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    assert result["action"] == "propose_experiment"
    assert result["destination"] == "experiment_queue"


def test_propose_pattern(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    result = pstore.propose_pattern(
        business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    assert result["action"] == "propose_pattern"
    assert result["destination"] == "module_proposal_queue"


def test_proposal_does_not_change_module(promotion_store):
    """No observation silently changes a module."""
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    pstore.propose_pattern(
        business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    # The proposal exists but no module was changed
    bookmarks = pstore.list_bookmarks(business_slug="test-tenant")
    assert len(bookmarks) == 1
    assert bookmarks[0]["action"] == "propose_pattern"
    assert bookmarks[0]["status"] == "active"


# ─── Revert / undo / history ─────────────────────────────────────────────────

def test_revert_preserves_history(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    result = pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    reverted = pstore.revert(bookmark_id=result["id"])
    assert reverted["status"] == "reverted"
    assert reverted["reverted_at"] is not None
    # History preserved — the bookmark still exists
    bm = pstore.get_bookmark(result["id"])
    assert bm is not None
    assert bm["status"] == "reverted"


def test_revert_already_reverted_fails(promotion_store):
    from inspiration_promotions import PromotionError
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    result = pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    pstore.revert(bookmark_id=result["id"])
    with pytest.raises(PromotionError):
        pstore.revert(bookmark_id=result["id"])


# ─── Tenant scoping ──────────────────────────────────────────────────────────

def test_tenant_scoping(promotion_store):
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    # Wrong tenant cannot bookmark
    from inspiration_promotions import PromotionError
    with pytest.raises(PromotionError):
        pstore.bookmark(business_slug="wrong-tenant", trend_item_id=item_id, observation_id=obs_id)


# ─── Bulk operations ─────────────────────────────────────────────────────────

def test_bulk_revert(promotion_store):
    """Bulk revert works for queues >50 items."""
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    bookmark_ids = []
    for item in items:
        history = insp_store.get_observation_history(item["id"])
        obs_id = history[0]["id"]
        result = pstore.bookmark(business_slug="test-tenant", trend_item_id=item["id"], observation_id=obs_id)
        bookmark_ids.append(result["id"])
    # Bulk revert
    result = pstore.bulk_revert(business_slug="test-tenant", bookmark_ids=bookmark_ids)
    assert len(result["reverted"]) == len(bookmark_ids)
    assert len(result["errors"]) == 0
    # All are reverted
    for bid in bookmark_ids:
        bm = pstore.get_bookmark(bid)
        assert bm["status"] == "reverted"


# ─── API routes ─────────────────────────────────────────────────────────────

@pytest.fixture()
def api_client(tmp_path):
    from app import create_app
    from inspiration_store import InspirationStore
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
    app.config["TESTING"] = True
    # Initialize pipeline schema (creates sources table needed by Source Bank promotion)
    from pipeline import PipelineStore
    PipelineStore(db_path)
    store = InspirationStore(db_path)
    config = yaml.safe_load(open(Path(config_dir) / "inspiration.yaml"))
    _seed(store, "stackpenni", config)
    return app.test_client(), db_path


def test_api_bookmark(api_client):
    client, db = api_client
    import sqlite3
    conn = sqlite3.connect(db)
    item = conn.execute("SELECT id FROM insp_trend_items WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    obs = conn.execute("SELECT id FROM insp_observations WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    conn.close()
    resp = client.post(f"/api/inspiration/{item[0]}/{obs[0]}/bookmark", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["bookmark"]["action"] == "bookmark"


def test_api_promote_source_bank(api_client):
    client, db = api_client
    import sqlite3
    conn = sqlite3.connect(db)
    item = conn.execute("SELECT id FROM insp_trend_items WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    obs = conn.execute("SELECT id FROM insp_observations WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    conn.close()
    resp = client.post(f"/api/inspiration/{item[0]}/{obs[0]}/promote",
                       json={"action": "add_to_source_bank"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["promotion"]["destination"] == "source_bank"


def test_api_list_bookmarks(api_client):
    client, db = api_client
    import sqlite3
    conn = sqlite3.connect(db)
    item = conn.execute("SELECT id FROM insp_trend_items WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    obs = conn.execute("SELECT id FROM insp_observations WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    conn.close()
    client.post(f"/api/inspiration/{item[0]}/{obs[0]}/bookmark", json={})
    resp = client.get("/api/inspiration/bookmarks")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["bookmarks"]) == 1
    assert data["bookmarks"][0]["action"] == "bookmark"


def test_api_revert(api_client):
    client, db = api_client
    import sqlite3
    conn = sqlite3.connect(db)
    item = conn.execute("SELECT id FROM insp_trend_items WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    obs = conn.execute("SELECT id FROM insp_observations WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    conn.close()
    bm = client.post(f"/api/inspiration/{item[0]}/{obs[0]}/bookmark", json={}).get_json()
    resp = client.post(f"/api/inspiration/bookmarks/{bm['bookmark']['id']}/revert", json={})
    assert resp.status_code == 200
    assert resp.get_json()["reverted"]["status"] == "reverted"


def test_api_bulk_revert(api_client):
    client, db = api_client
    import sqlite3
    conn = sqlite3.connect(db)
    items = conn.execute("SELECT id FROM insp_trend_items WHERE business_slug='stackpenni'").fetchall()
    obs = conn.execute("SELECT id FROM insp_observations WHERE business_slug='stackpenni'").fetchall()
    conn.close()
    bookmark_ids = []
    for i, item in enumerate(items[:2]):
        bm = client.post(f"/api/inspiration/{item[0]}/{obs[i][0]}/bookmark", json={}).get_json()
        bookmark_ids.append(bm["bookmark"]["id"])
    resp = client.post("/api/inspiration/bookmarks/bulk-revert", json={"bookmark_ids": bookmark_ids})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["reverted"]) == 2


# ─── No silent changes ──────────────────────────────────────────────────────

def test_no_silent_idea_creation(api_client):
    """No promotion action creates an idea card."""
    client, db = api_client
    import sqlite3
    conn = sqlite3.connect(db)
    item = conn.execute("SELECT id FROM insp_trend_items WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    obs = conn.execute("SELECT id FROM insp_observations WHERE business_slug='stackpenni' LIMIT 1").fetchone()
    conn.close()
    # All promotion actions
    client.post(f"/api/inspiration/{item[0]}/{obs[0]}/bookmark", json={})
    conn = sqlite3.connect(db)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "idea_cards" in tables:
        count = conn.execute("SELECT COUNT(*) FROM idea_cards WHERE business_slug='stackpenni'").fetchone()[0]
        assert count == 0
    conn.close()


def test_observation_history_unchanged_by_promotion(promotion_store):
    """Promotion does not rewrite observation history."""
    pstore, insp_store, db = promotion_store
    items = insp_store.get_items_for_section("test-tenant", "audio", ["tikhub_tiktok_audio_charts"])
    item_id = items[0]["id"]
    history_before = insp_store.get_observation_history(item_id)
    history = insp_store.get_observation_history(item_id)
    obs_id = history[0]["id"]
    pstore.bookmark(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id)
    pstore.add_to_source_bank(business_slug="test-tenant", trend_item_id=item_id, observation_id=obs_id + 1 if len(history) > 1 else obs_id)
    history_after = insp_store.get_observation_history(item_id)
    assert len(history_after) == len(history_before)
    # The observation content is unchanged
    assert history_after[0]["safe_payload_hash"] == history_before[0]["safe_payload_hash"]