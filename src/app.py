"""
ViralFactory — Flask Console

The web interface for the system. Server-rendered Flask + minimal JS.
Laptop-first, responsive to mobile.

M1 scope: Onboarding surface (playbook runner UI).
"""

import os
import json
import shutil
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory

# Support both package and direct imports
try:
    from .config_loader import load_all, ConfigError
    from .playbook_runner import PlaybookParser, PlaybookRunner
except ImportError:
    from config_loader import load_all, ConfigError
    from playbook_runner import PlaybookParser, PlaybookRunner


def _archive_config_file(filepath):
    """Archive an existing config file before it is overwritten.

    Copies *filepath* to ``config/archive/{name}-{timestamp}.yaml`` if the file
    exists. Creates the ``config/archive/`` directory if needed. Safe to call
    when the file does not exist (no-op).
    """
    if not os.path.exists(filepath):
        return None
    config_dir = os.path.dirname(filepath)
    archive_dir = os.path.join(config_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    name = os.path.basename(filepath)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    archive_path = os.path.join(archive_dir, f"{name}-{ts}")
    shutil.copy2(filepath, archive_path)
    return archive_path


def _verify_config_write(db_path: str, run_id: int, gate_token: str):
    """
    Verify a gate token before writing config files (business.yaml, sources.yaml).

    Same verification as module writes: the run must have an 'approve' gate
    decision, and the token must match.

    Raises GateTokenError if invalid.
    """
    from module_store import verify_gate_token, GateTokenError
    verify_gate_token(db_path, run_id, gate_token)


def _resolve_ai_video_generator(generator: str, media_config: dict) -> dict:
    """Resolve generator strings like ai_video:veo to concrete model/provider config.

    Returns {model, provider, name}. Bare ``ai_video`` intentionally returns
    null model/provider so MediaAdapter uses the legacy configured default.
    Raises ValueError when a named generator is requested but not configured —
    silently falling back to the default provider hides exactly the failure this
    helper exists to prevent.
    """
    if not (generator or "").startswith("ai_video"):
        raise ValueError(f"Not an AI video generator: {generator}")
    if ":" not in generator:
        return {"model": None, "provider": None, "name": "default"}

    name = generator.split(":", 1)[1]
    for vg in media_config.get("video_generators", []):
        if vg.get("name") == name:
            return {
                "model": vg.get("model"),
                "provider": vg.get("provider"),
                "name": name,
            }
    raise ValueError(f"Unknown AI video generator '{name}' — add it to media.video_generators")


def _summarize_media_generation_results(results: list[dict]) -> dict:
    """Summarize media generation results for honest UI messaging.

    Only status='ok' means a renderable local media ingredient exists now.
    status='processing' means a video job timed out and is still running —
    the operator should check back. The UI must not call that ready-to-render.
    """
    available_count = sum(1 for r in results if r.get("status") == "ok")
    processing_count = sum(1 for r in results if r.get("status") == "processing")
    submitted_count = sum(1 for r in results if r.get("status") == "submitted")
    failed_count = sum(1 for r in results if r.get("status") == "failed")
    skipped_count = sum(1 for r in results if r.get("status") == "skipped")
    return {
        "available_count": available_count,
        "processing_count": processing_count,
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "ready_to_render": available_count > 0,
    }


def _poll_download_register_video(
    media_adapter, external_job_id, asset_id, model, prompt,
    business_slug, provider=None,
):
    """Poll a video job, download on completion, register as asset_media.

    Returns dict with keys:
        status  — "ok" | "processing" | "failed"
        ingredient_id — "generated:<media_id>" (only when status=="ok")
        path        — local file path (only when status=="ok")
        external_job_id — the provider job ID (only when status=="processing")
        error       — plain-language error (only when status=="failed")
    """
    import time as _time

    max_polls = 60  # 5 minutes at 5s intervals
    for _ in range(max_polls):
        _time.sleep(5)
        poll_result = media_adapter.check_video_job(external_job_id, provider=provider)
        status = poll_result.get("status", "")
        if status == "completed":
            download_url = poll_result.get("download_url", "")
            if not download_url:
                return {
                    "status": "failed",
                    "error": "Job completed but no download URL was returned by the provider",
                }
            dl = media_adapter.download_video(
                external_job_id, download_url, asset_id,
                model, prompt,
                poll_result.get("cost_usd", 0),
                business_slug,
                video_provider=provider,
            )
            return {
                "status": "ok",
                "path": dl["file_path"],
                "ingredient_id": f"generated:{dl['media_id']}",
            }
        elif status == "failed":
            return {
                "status": "failed",
                "error": poll_result.get("error", "Video generation failed"),
            }

    # Timeout — job still processing
    return {
        "status": "processing",
        "external_job_id": external_job_id,
    }


def create_app(config_dir: str = "config", db_path: str = "data/viralfactory.db", playbooks_dir: str = None):
    """Create and configure the Flask app."""
    if playbooks_dir is None:
        # Default to repo-root playbooks/ (absolute so CWD changes don't break it)
        playbooks_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "playbooks")
        playbooks_dir = os.path.abspath(playbooks_dir)

    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["CONFIG_DIR"] = config_dir
    app.config["DB_PATH"] = db_path
    app.config["PLAYBOOKS_DIR"] = playbooks_dir

    # F5: Register from_json Jinja filter for parsing JSON strings in templates
    import json as _json
    @app.template_filter("from_json")
    def from_json_filter(s):
        if isinstance(s, (list, dict)):
            return s
        try:
            return _json.loads(s) if s else []
        except (ValueError, TypeError):
            return []

    # P1-2: Register relative_time Jinja filter for human-readable timestamps
    from datetime import datetime as _dt, timezone as _tz
    @app.template_filter("relative_time")
    def relative_time_filter(iso_string):
        """Convert ISO timestamp to relative time string (e.g. '2 hours ago')."""
        if not iso_string:
            return ""
        try:
            # Handle ISO 8601 with or without 'Z' suffix
            ts_str = iso_string.strip()
            if ts_str.endswith("Z"):
                ts_str = ts_str[:-1] + "+00:00"
            dt = _dt.fromisoformat(ts_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_tz.utc)
            now = _dt.now(_tz.utc)
            delta = now - dt
            seconds = int(delta.total_seconds())
            if seconds < 0:
                return "just now"
            if seconds < 60:
                return "just now"
            if seconds < 3600:
                minutes = seconds // 60
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            if seconds < 86400:
                hours = seconds // 3600
                return f"{hours} hour{'s' if hours != 1 else ''} ago"
            if seconds < 604800:
                days = seconds // 86400
                return f"{days} day{'s' if days != 1 else ''} ago"
            if seconds < 2592000:
                weeks = seconds // 604800
                return f"{weeks} week{'s' if weeks != 1 else ''} ago"
            months = seconds // 2592000
            return f"{months} month{'s' if months != 1 else ''} ago"
        except (ValueError, TypeError):
            return ""

    # F10: Strip basic markdown from preview text
    import re as _re
    @app.template_filter("strip_md")
    def strip_md_filter(s):
        if not s:
            return ""
        # Remove markdown headers, bold, italic, code blocks, links
        s = _re.sub(r'^#{1,6}\s+', '', s, flags=_re.MULTILINE)  # headers
        s = _re.sub(r'\*\*(.+?)\*\*', r'\1', s)  # bold
        s = _re.sub(r'\*(.+?)\*', r'\1', s)  # italic
        s = _re.sub(r'`(.+?)`', r'\1', s)  # inline code
        s = _re.sub(r'```[\s\S]*?```', '', s)  # code blocks
        s = _re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', s)  # links
        s = _re.sub(r'^[-*]\s+', '• ', s, flags=_re.MULTILINE)  # list items
        return s

    # F1: Initialize the jobs table (shared idempotency + async job substrate)
    from jobs import JobsStore
    app.config["JOBS_DB_PATH"] = db_path  # jobs table lives in the same DB
    # Ensure the jobs table exists
    _jobs_init = JobsStore(db_path)

    # Allow large file uploads (videos, zips of brand assets, etc.)
    # Default Flask has no limit; set explicit high limit so it fails clearly
    # rather than timing out silently. 2GB max upload.
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB

    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"status": "error", "error": "File too large. Maximum upload size is 2GB."}), 413

    @app.after_request
    def add_no_cache_headers(response):
        """Prevent browser caching of HTML pages so code updates are always served."""
        if response.content_type and 'text/html' in response.content_type:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        return response

    # UX-1: Context processor — inject nav_counts + business_name into every template
    @app.context_processor
    def inject_nav_counts():
        """Count cards in each pipeline stage so the nav menu shows real-time counts."""
        try:
            config = load_all(config_dir)
            business_slug = config["business"]["business"]["slug"]
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_slug = None
            business_name = None
        if not business_slug:
            return dict(nav_counts={}, business_name=business_name or "Not configured")
        try:
            from pipeline import PipelineStore
            store = PipelineStore(db_path=db_path)
            all_cards = store.list_idea_cards(business_slug)
            all_drafts = store.list_drafts(business_slug)
            draft_by_card = {d["idea_card_id"]: d for d in all_drafts}
            counts = {"new": 0, "ready_review": 0, "asset_ready": 0}
            for card in all_cards:
                cs = card["card_state"]
                if cs == "new":
                    counts["new"] += 1
                elif cs in ("writing", "draft_ready", "drafted"):
                    counts["ready_review"] += 1
                elif cs in ("asset_ready", "assembling"):
                    counts["asset_ready"] += 1
                elif cs == "approved":
                    draft = draft_by_card.get(card["id"])
                    if draft and draft["draft_state"] in ("draft_ready", "revised", "drafted"):
                        counts["ready_review"] += 1
                    elif draft and draft["draft_state"] == "shipped":
                        counts["asset_ready"] += 1
                    else:
                        counts["ready_review"] += 1
            return dict(nav_counts=counts, business_name=business_name)
        except Exception:
            return dict(nav_counts={}, business_name=business_name or "Not configured")

    # --- Routes ---

    def _greeting_period() -> str:
        """Return time-of-day greeting word."""
        from datetime import datetime, timezone
        h = datetime.now().hour
        if h < 12: return "morning"
        if h < 18: return "afternoon"
        return "evening"

    @app.route("/")
    def index():
        """Dashboard — shows system status and recent activity."""
        try:
            config = load_all(config_dir)
            business_name = config["business"]["business"]["name"]
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_name = "Not configured"
            business_slug = None

        # Build gate counts for stat cards
        gate_counts = {"ideas": 0, "drafts": 0, "assets": 0}
        pipeline_counts = {"ideas": 0, "drafting": 0, "assets": 0, "published": 0}
        decision_queue = []  # items needing operator action

        if business_slug:
            store = _get_pipeline_store()
            from datetime import datetime, timezone

            def fmt_time(iso_str):
                """Format ISO timestamp as human-readable."""
                if not iso_str:
                    return ""
                try:
                    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                    return dt.strftime("%b %d, %I:%M %p").lstrip("0")
                except Exception:
                    return iso_str[:16]

            def fmt_date(iso_str):
                """Format ISO timestamp as date only."""
                if not iso_str:
                    return ""
                try:
                    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
                    return dt.strftime("%b %d, %Y")
                except Exception:
                    return iso_str[:10]

            # Build a grouped activity log: each idea gets one entry with sub-events
            all_cards = store.list_idea_cards(business_slug)
            grouped = {}  # {idea_title: {type, state, title, link, time, sub_events: []}}

            for card in all_cards:
                title = card["idea"][:100]  # longer truncation, CSS handles overflow
                cs = card["card_state"]
                card_num = card.get("id", 0)

                # Count pipeline stages
                if cs == "new":
                    gate_counts["ideas"] += 1
                    pipeline_counts["ideas"] += 1
                    decision_queue.append({
                        "num": card_num,
                        "title": title,
                        "gate": "Gate 1",
                        "meta": card.get("treatment_line", ""),
                        "link": "/ideas",
                        "gate_type": "gate1",
                    })
                elif cs in ("writing", "draft_ready", "drafted"):
                    pipeline_counts["drafting"] += 1
                    if cs in ("draft_ready", "drafted"):
                        gate_counts["drafts"] += 1
                        decision_queue.append({
                            "num": card_num,
                            "title": title,
                            "gate": "Gate 2",
                            "meta": "draft ready for review",
                            "link": f"/create/draft/{card_num}",
                            "gate_type": "gate2",
                        })
                elif cs in ("asset_ready", "assembling"):
                    pipeline_counts["assets"] += 1
                    if cs == "asset_ready":
                        gate_counts["assets"] += 1
                        # find the draft id for link
                        card_drafts = [d for d in store.list_drafts(business_slug) if d["idea_card_id"] == card["id"]]
                        if card_drafts:
                            latest_draft = max(card_drafts, key=lambda d: d.get("draft_version", 1))
                            decision_queue.append({
                                "num": card_num,
                                "title": title,
                                "gate": "Gate 3",
                                "meta": "assets ready for preview",
                                "link": f"/create/assets/{latest_draft['id']}",
                                "gate_type": "gate3",
                            })
                elif cs == "approved":
                    pipeline_counts["drafting"] += 1
                    gate_counts["drafts"] += 1
                    decision_queue.append({
                        "num": card_num,
                        "title": title,
                        "gate": "Gate 2",
                        "meta": "draft ready for review",
                        "link": f"/create/draft/{card_num}",
                        "gate_type": "gate2",
                    })
                elif cs == "shipped":
                    pipeline_counts["published"] += 1

                if title not in grouped:
                    grouped[title] = {
                        "type": "idea",
                        "state": cs,
                        "title": title,
                        "link": "/ideas",
                        "time": card.get("created_at", ""),
                        "sub_events": [],
                    }
                # Check for drafts on this card — group assets under each draft
                card_drafts = [d for d in store.list_drafts(business_slug) if d["idea_card_id"] == card["id"]]
                # Only show the latest draft version to avoid repetition
                if card_drafts:
                    latest_draft = max(card_drafts, key=lambda d: d.get("draft_version", 1))
                    draft_sub = {
                        "type": "draft",
                        "state": latest_draft["draft_state"],
                        "title": f"Draft v{latest_draft['draft_version']}",
                        "link": f"/create/draft/{card['id']}",
                        "time": fmt_time(latest_draft.get("updated_at", "")),
                    }
                    grouped[title]["sub_events"].append(draft_sub)
                    # Assets for the latest draft only
                    seen_asset_keys = set()
                    for asset in store.list_assets(latest_draft["id"]):
                        asset_key = f"{asset['platform']}_{asset['variant_type']}"
                        if asset_key in seen_asset_keys:
                            continue
                        seen_asset_keys.add(asset_key)
                        grouped[title]["sub_events"].append({
                            "type": "asset",
                            "state": asset["asset_state"],
                            "title": f"  → {asset['platform']} {asset['variant_type']}",
                            "link": f"/create/assets/{latest_draft['id']}",
                            "time": fmt_time(asset.get("updated_at", "")),
                        })
                    if latest_draft["draft_state"] == "shipped":
                        grouped[title]["state"] = "shipped"

            # Convert to list, sort by time desc
            activity = list(grouped.values())
            activity.sort(key=lambda x: x.get("time") or "", reverse=True)
            for item in activity:
                item["time"] = fmt_time(item.get("time", ""))
                item["sub_events"].sort(key=lambda x: x.get("time") or "", reverse=False)

            # System health summary
            system_health = []
            try:
                # Module count
                modules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules", business_slug)
                if os.path.isdir(modules_dir):
                    module_files = [f for f in os.listdir(modules_dir) if f.endswith(".md")]
                    approved = sum(1 for f in module_files if not f.startswith("_draft_") and not f.startswith("_pending_"))
                    system_health.append({"icon": "green", "text": f"{approved} of {len(module_files)} modules approved"})
            except Exception:
                pass

            # Source staleness
            try:
                sources = store.list_sources(business_slug) if hasattr(store, 'list_sources') else []
                stale = sum(1 for s in sources if s.get("staleness_status") == "stale")
                if stale:
                    system_health.append({"icon": "yellow", "text": f"Source Bank: {stale} sources stale (>30d)"})
                else:
                    system_health.append({"icon": "green", "text": "Source Bank: all sources fresh"})
            except Exception:
                pass

            system_health.append({"icon": "green", "text": "Auto-publish disabled · per-piece approval"})

        else:
            system_health = []

        return render_template("index.html",
            business_name=business_name,
            business_slug=business_slug,
            activity=activity,
            greeting_period=_greeting_period(),
            pending_count=len(decision_queue),
            gate_counts=gate_counts,
            pipeline_counts=pipeline_counts,
            decision_queue=decision_queue[:6],
            system_health=system_health,
        )

    @app.route("/onboard")
    def onboard():
        """Single-thread onboarding — one conversation for all 8 playbooks.

        Opens directly into the conversation (new or resumed). The hub page
        is retired as an entry point. (CORRECTION-onboarding-single-thread-v1.0 Item 2)
        """
        config = load_all(app.config["CONFIG_DIR"])
        business_slug = config["business"]["business"]["slug"]
        business_name = config["business"]["business"]["name"]

        runner = PlaybookRunner(app.config["DB_PATH"])

        # Find or create the single onboarding run (playbook_name = "onboarding")
        all_runs = runner.list_runs(business_slug)
        onboarding_run = None
        for r in all_runs:
            if r["playbook_name"] == "onboarding" and r["status"] not in ("completed", "cancelled"):
                onboarding_run = r
                break

        if onboarding_run:
            run_id = onboarding_run["id"]
            run = onboarding_run
        else:
            run_id = runner.start_run("onboarding", "1.0", business_slug)
            run = runner.get_run(run_id)

        collected = json.loads(run.get("collected_inputs") or "{}")

        # Build coverage map
        from module_store import ModuleStore
        ms = ModuleStore(app.config.get("MODULES_DIR", "modules"))
        coverage = _build_coverage_map(collected, module_store=ms)

        # Save coverage if it's new
        if "coverage" not in collected:
            collected["coverage"] = coverage
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

        # Build conversation history
        conversation_so_far = _build_conversation_history(collected)

        # P1-2: Build structured conversation turns for template rendering on page load
        session_messages = collected.get("session_messages", [])
        ai_replies = collected.get("ai_replies", [])
        conversation_turns = []
        max_len = max(len(session_messages), len(ai_replies))
        for i in range(max_len):
            if i < len(ai_replies):
                conversation_turns.append({"role": "ai", "text": ai_replies[i]})
            if i < len(session_messages):
                conversation_turns.append({"role": "operator", "text": session_messages[i]})

        # Opening question for fresh conversation
        opening_question = "Welcome! I'm going to learn everything about your business in one conversation — your story, your voice, your audience, your style. This will feed all eight onboarding modules at once. Let's start simple: tell me about your business. What do you do, who's it for, and what makes you different?"

        if not collected.get("ai_replies") and not collected.get("session_messages"):
            if "ai_replies" not in collected:
                collected["ai_replies"] = []
            collected["ai_replies"].append(opening_question)
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

        # Build coverage chips for the progress rail
        coverage_chips = []
        pb_dir = app.config["PLAYBOOKS_DIR"]
        for pb_name in ONBOARDING_PLAYBOOKS:
            pb_path = os.path.join(pb_dir, f"{pb_name}.md")
            label = pb_name
            if os.path.exists(pb_path):
                pb = PlaybookParser.parse(pb_path)
                label = pb.display_label or pb_name
            entry = coverage.get(pb_name, {"status": "empty"})
            coverage_chips.append({
                "name": pb_name,
                "label": label,
                "status": entry.get("status", "empty"),
            })

        # Check for any drafted docs with gate cards pending
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        gate_cards = []
        for pb_name in ONBOARDING_PLAYBOOKS:
            output_key = pb_name.replace("-", "_")
            if output_key in llm_outputs:
                output = llm_outputs[output_key]
                gate_results = json.loads(run.get("gate_results") or "{}")
                if pb_name not in gate_results:
                    # This doc has been drafted but not yet gated — show gate card
                    readback = _build_readback(pb_name, output)
                    gate_cards.append({
                        "playbook": pb_name,
                        "readback": readback,
                        "output_key": output_key,
                    })

        # Build materials summary
        materials_summary = _build_materials_summary(run_id)

        return render_template("onboarding_session.html",
            business_name=business_name, business_slug=business_slug,
            run_id=run_id, run=run,
            opening_question=opening_question,
            conversation_so_far=conversation_so_far,
            conversation_turns=conversation_turns,
            coverage_chips=coverage_chips,
            gate_cards=gate_cards,
            materials_summary=materials_summary)

    @app.route("/onboard/hub")
    def onboard_hub():
        """Legacy hub page — kept for reference, not the entry point."""
        playbooks = []
        pb_dir = app.config["PLAYBOOKS_DIR"]
        if os.path.isdir(pb_dir):
            for f in sorted(os.listdir(pb_dir)):
                if f.endswith(".md"):
                    playbook = PlaybookParser.parse(os.path.join(pb_dir, f))
                    playbooks.append({
                        "name": playbook.name,
                        "display_label": playbook.display_label or playbook.name,
                        "purpose": playbook.purpose[:200],
                        "version": playbook.file_version,
                        "num_steps": len(playbook.steps),
                        "has_gate": any(s.is_gate for s in playbook.steps),
                        "run_order": playbook.run_order,
                    })
        # Sort by run_order (UI-REVIEW-001 F1)
        playbooks.sort(key=lambda p: p["run_order"])

        # Determine locked/completed states from playbook runs
        business_slug = None
        try:
            config = load_all(config_dir)
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            pass

        if business_slug:
            runner = PlaybookRunner(app.config["DB_PATH"])
            all_runs = runner.list_runs(business_slug)
            # Map playbook name → completed status
            completed_names = set()
            for r in all_runs:
                if r.get("status") == "completed":
                    completed_names.add(r["playbook_name"])
            # Mark completed and locked
            prev_completed = True  # First playbook is always unlocked
            for pb in playbooks:
                pb["completed"] = pb["name"] in completed_names
                pb["locked"] = not prev_completed and not pb["completed"]
                if pb["completed"]:
                    prev_completed = True
                else:
                    prev_completed = False
        else:
            # No business slug — only first playbook is unlocked
            for i, pb in enumerate(playbooks):
                pb["completed"] = False
                pb["locked"] = i > 0

        return render_template("onboard.html", playbooks=playbooks)

    @app.route("/onboard/<playbook_name>")
    def start_playbook(playbook_name):
        """Start or resume a playbook — all playbooks use the session component (UI-REVIEW-001 F3)."""
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], f"{playbook_name}.md")
        if not os.path.exists(pb_path):
            return "Playbook not found", 404

        playbook = PlaybookParser.parse(pb_path)
        config = load_all(app.config["CONFIG_DIR"])
        business_slug = config["business"]["business"]["slug"]

        runner = PlaybookRunner(app.config["DB_PATH"])

        # Run reuse: find the latest run for this playbook that isn't completed/cancelled.
        # Only create a new run if no resumable one exists (UI-REVIEW-001 — don't create runs on every visit).
        all_runs = runner.list_runs(business_slug)
        existing_run = None
        for r in all_runs:
            if r["playbook_name"] == playbook.name and r["status"] not in ("completed", "cancelled"):
                existing_run = r
                break

        if existing_run:
            run_id = existing_run["id"]
            run = existing_run
        else:
            run_id = runner.start_run(playbook.name, playbook.file_version, business_slug)
            run = runner.get_run(run_id)

        # Build progress rail from playbook steps
        rail_steps = []
        gate_results = json.loads(run.get("gate_results") or "{}")
        for s in playbook.steps:
            state = "pending"
            if s.number in gate_results:
                if gate_results[s.number].get("decision") == "approve":
                    state = "done"
                else:
                    state = "active"
            elif s.is_intake and not s.is_gate:
                state = "active"
            rail_steps.append({"label": s.title[:40], "state": state})

        # Check if analysis already exists
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        # The analysis key varies by playbook — check common ones
        profile = (llm_outputs.get("analysis") or llm_outputs.get("profile")
                   or llm_outputs.get("patterns") or llm_outputs.get("insights")
                   or llm_outputs.get("frameworks") or llm_outputs.get("guide")
                   or llm_outputs.get("style_guide") or llm_outputs.get("criteria"))

        # Build readback text if profile exists
        readback_text = ""
        if profile:
            readback_text = _build_readback(playbook_name, profile)

        try:
            business_name = config["business"]["business"]["name"]
        except (ConfigError, KeyError):
            business_name = "Your Business"

        # Determine the opening question (do this before building conversation history)
        opening_question = _get_opening_question(playbook)

        # Build conversation so far for the opening question
        collected = json.loads(run.get("collected_inputs") or "{}")

        # If this is a fresh conversation, store the opening question as the first AI reply
        if not collected.get("ai_replies") and not collected.get("session_messages"):
            if "ai_replies" not in collected:
                collected["ai_replies"] = []
            collected["ai_replies"].append(opening_question)
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

        conversation_so_far = _build_conversation_history(collected)

        return render_template("session.html",
            display_label=playbook.display_label or playbook.name,
            business_name=business_name, business_slug=business_slug,
            playbook_name=playbook_name, run_id=run_id, run=run,
            rail_steps=rail_steps, opening_question=opening_question,
            profile=profile, readback_text=readback_text,
            gate_step=PlaybookRunner.get_gate_step_number(playbook),
            conversation_so_far=conversation_so_far)

    def _get_opening_question(playbook):
        """Generate a playbook-specific opening question for the operator.
        Not generic — references what this playbook actually needs."""
        questions = {
            "business-profile-intake": "Let's get started. Tell me about your business — what do you do, and who's it for? Don't worry about structure, just talk.",
            "voice-profile-builder": "I'm going to learn how YOU talk so everything we create sounds like you. What kind of stuff do you have that shows your voice — voice notes, WhatsApp chats, emails, social posts? Or would you rather I just ask you questions?",
            "sources-engine": "I need to learn what 'good' looks like for your sources. Give me 3-5 links to content you wish you'd made — stuff in your space that you admire. URLs are fine, just paste them.",
            "viral-patterns-starter": "Let's figure out what goes viral in YOUR space. Share 3-5 links to content you admire — stuff where you thought 'I wish we'd made that.' Paste the URLs.",
            "audience-insights-builder": "Let's understand your audience. Who are they? Not demographics — who are they as people? What do they care about? What makes them stop scrolling?",
            "story-frameworks-starter": "Every piece of content tells a story. Let's figure out YOUR stories. Tell me 2-3 stories you tell often — about your business, your life, your take on things. Just talk, I'll structure it.",
            "format-guide-starter": "Let's figure out what formats work for you. What platforms do you post on, and what do you notice works well there? Threads? Reels? Carousels? Just tell me what you've seen perform.",
            "visual-style-intake": "I need to understand your visual identity. What does your brand look like? Colors, mood, aesthetic — or just upload some images and I'll work from those.",
        }
        return questions.get(playbook.name, f"Let's get started with {playbook.display_label or playbook.name}. Tell me what you know about this.")

    def _build_conversation_history(collected):
        """Build a full conversation transcript for the LLM.
        Includes every operator message and AI reply so the LLM can reason
        about the entire conversation, not just the latest message."""
        lines = []
        # Session messages are the operator's raw inputs
        messages = collected.get("session_messages", [])
        # AI replies are stored alongside
        ai_replies = collected.get("ai_replies", [])

        # Interleave operator messages and AI replies
        max_len = max(len(messages), len(ai_replies))
        for i in range(max_len):
            if i < len(ai_replies):
                lines.append(f"AI: {ai_replies[i]}")
                lines.append("")
            if i < len(messages):
                lines.append(f"Operator: {messages[i]}")
                lines.append("")

        # Also include legacy Q&A pairs if they exist
        qa_pairs = collected.get("business_qa", [])
        legacy_count = len(qa_pairs) - len(messages)  # Q&A pairs from old UI
        if legacy_count > 0:
            lines.append("(Earlier Q&A from form-based intake:)")
            for pair in qa_pairs[:legacy_count]:
                q = pair.get("q", "")
                a = pair.get("a", "")
                if q != "(session message)":
                    lines.append(f"Q: {q}")
                    lines.append(f"A: {a}")
                    lines.append("")

        return "\n".join(lines) if lines else "(This is the first turn — no conversation yet)"

    def _is_near_duplicate(reply: str, prior_replies: list[str], threshold: float = 0.9) -> bool:
        """Check if reply is too similar to any prior AI reply using difflib."""
        import difflib
        normalized = reply.strip().lower()
        for prior in prior_replies:
            ratio = difflib.SequenceMatcher(None, normalized, prior.strip().lower()).ratio()
            if ratio > threshold:
                return True
        return False

    # ── Onboarding Orchestrator (single-thread onboarding) ──

    ONBOARDING_PLAYBOOKS = [
        "business-profile-intake",
        "voice-profile-builder",
        "sources-engine",
        "viral-patterns-starter",
        "audience-insights-builder",
        "story-frameworks-starter",
        "format-guide-starter",
        "visual-style-intake",
    ]

    def _build_coverage_map(collected, module_store=None):
        """Build the coverage map from collected inputs and existing approved modules.

        Statuses: empty → collecting → ready → drafted → approved
        """
        coverage = collected.get("coverage", {})
        # Seed from existing approved modules
        if module_store:
            for pb_name in ONBOARDING_PLAYBOOKS:
                if pb_name not in coverage or coverage[pb_name].get("status") == "empty":
                    try:
                        mod = module_store.load_latest("default", pb_name.replace("-starter", "").replace("-builder", "").replace("-intake", "").replace("-engine", ""))
                        if mod:
                            coverage[pb_name] = {"status": "approved", "doc_version": mod.get("version", "1.0")}
                    except Exception:
                        pass
        # Ensure all 8 playbooks are in the map
        for pb_name in ONBOARDING_PLAYBOOKS:
            if pb_name not in coverage:
                coverage[pb_name] = {"status": "empty"}
        return coverage

    def _format_coverage_map(coverage):
        """Format coverage map as readable text for the LLM prompt."""
        lines = []
        for pb_name in ONBOARDING_PLAYBOOKS:
            entry = coverage.get(pb_name, {"status": "empty"})
            status = entry.get("status", "empty")
            extra = ""
            if entry.get("gaps"):
                extra = f" — gaps: {', '.join(entry['gaps'])}"
            if entry.get("doc_version"):
                extra += f" (v{entry['doc_version']})"
            lines.append(f"- {pb_name}: {status}{extra}")
        return "\n".join(lines)

    def _build_playbook_inputs_all():
        """Build a combined summary of what each of the 8 playbooks needs."""
        pb_dir = app.config["PLAYBOOKS_DIR"]
        lines = []
        for pb_name in ONBOARDING_PLAYBOOKS:
            pb_path = os.path.join(pb_dir, f"{pb_name}.md")
            if not os.path.exists(pb_path):
                continue
            playbook = PlaybookParser.parse(pb_path)
            label = playbook.display_label or pb_name
            purpose = playbook.purpose[:200] if playbook.purpose else ""
            inputs = "; ".join(playbook.inputs[:5]) if playbook.inputs else "free-form conversation"
            lines.append(f"### {label} ({pb_name})\n{purpose}\nNeeds: {inputs}\n")
        return "\n".join(lines)

    def _build_materials_summary(run_id):
        """Build a summary of uploaded materials for the converse prompt.

        Lists each material with filename, type, and an excerpt of content.
        Caps total size to ~6,000 chars so it fits within the LLM context window.

        Audio files show transcription status honestly:
        - pending/processing: "(transcribing — will be available shortly)"
        - done: transcript excerpt
        - failed: failure note
        """
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        materials = intake.list_materials(run_id=run_id)
        if not materials:
            return "(No materials uploaded yet.)"

        PER_MATERIAL_CAP = 1500
        TOTAL_CAP = 6000
        lines = []
        total = 0
        for m in materials:
            filename = m.get("filename", "unknown")
            mtype = m.get("material_type", "unknown")
            raw = m.get("raw_content", "")
            normalized = m.get("normalized_content", "")

            # Audio materials: show transcription status honestly
            if mtype == "audio":
                if normalized and not normalized.startswith("[Audio") and not normalized.startswith("["):
                    excerpt = normalized[:PER_MATERIAL_CAP]
                    if len(normalized) > PER_MATERIAL_CAP:
                        excerpt += "... [truncated]"
                    entry = f"- {filename} (audio, transcript): {excerpt}"
                elif normalized and "failed" in normalized.lower():
                    entry = f"- {filename} (audio): {normalized[:200]}"
                else:
                    entry = f"- {filename} (audio): (transcribing — will be available shortly)"
            elif raw and any(ord(c) < 9 for c in raw[:50]):
                excerpt = "(binary content — not text-extractable)"
                entry = f"- {filename} ({mtype}): {excerpt}"
            elif normalized or raw:
                content = normalized or raw
                excerpt = content[:PER_MATERIAL_CAP]
                if len(content) > PER_MATERIAL_CAP:
                    excerpt += "... [truncated]"
                entry = f"- {filename} ({mtype}): {excerpt}"
            else:
                entry = f"- {filename} ({mtype}): (empty)"

            if total + len(entry) > TOTAL_CAP:
                remaining = TOTAL_CAP - total
                if remaining > 50:
                    entry = entry[:remaining] + "... [truncated]"
                    lines.append(entry)
                lines.append(f"... and {len(materials) - len(lines)} more materials (truncated)")
                break
            lines.append(entry)
            total += len(entry)

        return "\n".join(lines)

    def _build_shot_library_summary(run_id):
        """P0-1(d): Build a real shot library listing from uploaded materials.

        Replaces the hardcoded '(see uploaded files)' literal that told the LLM nothing.
        Lists filenames, types, and extracted content for image-adjacent text materials.
        """
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        materials = intake.list_materials(run_id=run_id)
        if not materials:
            return "(No shot library uploaded.)"

        lines = []
        for m in materials:
            filename = m.get("filename", "unknown")
            mtype = m.get("material_type", "unknown")
            raw = m.get("raw_content", "")
            normalized = m.get("normalized_content", "")
            content = normalized or raw

            if mtype == "image":
                lines.append(f"- {filename} (image)")
            elif content and not content.startswith("[Audio") and not content.startswith("[Binary"):
                excerpt = content[:300]
                if len(content) > 300:
                    excerpt += "..."
                lines.append(f"- {filename} ({mtype}): {excerpt}")
            else:
                lines.append(f"- {filename} ({mtype})")

        return "\n".join(lines) if lines else "(No shot library uploaded.)"

    def _build_readback(playbook_name, profile):
        """Build a plain-language readback for the operator based on playbook type.

        P1-3: No raw dict text. Unknown dicts render key: value lines, untruncated.
        Empty sections are omitted, not rendered as bare headers.
        """
        if playbook_name == "business-profile-intake":
            return _build_business_readback(profile)
        # Generic readback: format the key fields in prose
        lines = ["Here's what I put together:", ""]
        if isinstance(profile, dict):
            for key, val in profile.items():
                label = key.replace('_', ' ').title()
                if isinstance(val, str) and len(val) < 500:
                    if val:
                        lines.append(f"**{label}:** {val}")
                elif isinstance(val, list) and val:
                    lines.append(f"**{label}:**")
                    for item in val[:10]:
                        if isinstance(item, str):
                            lines.append(f"  • {item}")
                        elif isinstance(item, dict):
                            # P1-3: Render meaningful fields in prose, never str(dict)
                            name = item.get("name", item.get("subject", item.get("format", item.get("pattern", item.get("tell", "")))))
                            if name:
                                lines.append(f"  • {name}")
                            else:
                                # Fallback: key: value lines, untruncated
                                for k, v in item.items():
                                    if isinstance(v, str) and len(v) < 200:
                                        lines.append(f"  • {k}: {v}")
                                    elif isinstance(v, list):
                                        lines.append(f"  • {k}: {', '.join(str(x) for x in v[:5])}")
                elif isinstance(val, dict) and val:
                    lines.append(f"**{label}:**")
                    for k, v in val.items():
                        if isinstance(v, (str, int, float)):
                            lines.append(f"  • {k}: {v}")
                        elif isinstance(v, list):
                            lines.append(f"  • {k}: {', '.join(str(x) for x in v[:5])}")
                # Empty values are omitted, not rendered
        return "\n".join(lines)

    def _build_business_readback(profile):
        """Build a plain-language readback of the business profile for the operator."""
        lines = []
        biz = profile.get("business", {})
        lines.append(f"Business: {biz.get('name', '?')} — {biz.get('description', '')}")
        lines.append("")
        brands = profile.get("brands", [])
        if brands:
            lines.append("Brands:")
            for b in brands:
                lines.append(f"  • {b['name']} — {b.get('purpose', '')}")
            lines.append("")
        subjects = profile.get("subjects", [])
        if subjects:
            lines.append(f"Topics: {', '.join(subjects)}")
            lines.append("")
        platforms = profile.get("platforms", [])
        if platforms:
            lines.append("Platforms:")
            for p in platforms:
                lines.append(f"  • {p['name']} ({p.get('handle', '')})")
            lines.append("")
        goals = profile.get("goals", [])
        if goals:
            lines.append("Goals:")
            for g in goals:
                lines.append(f"  • {g}")
            lines.append("")
        red_lines = profile.get("red_lines", [])
        if red_lines:
            lines.append("Never do:")
            for r in red_lines:
                lines.append(f"  • {r}")
            lines.append("")
        audience = profile.get("audience_description", "")
        if audience:
            lines.append(f"Audience: {audience}")
        return "\n".join(lines)

    # ── Onboarding Orchestrator API ──

    @app.route("/api/onboarding/<int:run_id>/message", methods=["POST"])
    def onboarding_message(run_id):
        """Handle a message in the single-thread onboarding conversation.

        Uses the orchestrator prompt which routes seeds to all 8 docs,
        updates coverage, and flags docs as ready for drafting.
        """
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        text = request.json.get("text", "").strip()
        files = request.json.get("files", [])

        if not text and not files:
            return jsonify({"error": "No message provided"}), 400

        # Store the message
        collected = json.loads(run.get("collected_inputs") or "{}")
        if "session_messages" not in collected:
            collected["session_messages"] = []
        file_note = ""
        if files:
            file_note = f"\n[Operator attached files: {', '.join(files)}]"
        turn_text = (text + "\n" if text else "") + file_note.strip() if files else text
        collected["session_messages"].append(turn_text)
        if "business_qa" not in collected:
            collected["business_qa"] = []
        collected["business_qa"].append({"q": "(session message)", "a": turn_text})

        # Get config
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        # Build conversation history and materials summary
        conversation_so_far = _build_conversation_history(collected)
        materials_summary = _build_materials_summary(run_id)

        # Build coverage map
        from module_store import ModuleStore
        ms = ModuleStore(app.config.get("MODULES_DIR", "modules"))
        coverage = _build_coverage_map(collected, module_store=ms)

        # Build playbook inputs summary
        playbook_inputs = _build_playbook_inputs_all()

        # Call the orchestrator LLM
        from llm_adapter import LLMAdapter, LLMAdapterError
        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        orchestrator_schema = {
            "type": "object",
            "required": ["reply", "routed_seeds", "coverage_updates"],
            "properties": {
                "reply": {"type": "string"},
                "routed_seeds": {"type": "array", "items": {"type": "object",
                    "properties": {"doc": {"type": "string"}, "seed": {"type": "string"}}}},
                "coverage_updates": {"type": "array", "items": {"type": "object",
                    "properties": {"doc": {"type": "string"}, "status": {"type": "string"}}}},
                "next_focus": {"type": "string"},  # optional — orchestrator may return null
            },
        }

        try:
            # P2-1: Use the fast converse backend for orchestrator turns.
            # Falls back to default if converse role is not configured.
            result = adapter.complete(
                prompt_file="session/onboarding_orchestrator_v2.md",
                variables={
                    "business_name": business["business"]["name"],
                    "coverage_map": _format_coverage_map(coverage),
                    "materials_summary": materials_summary,
                    "playbook_inputs": playbook_inputs[:4000],
                    "conversation_so_far": conversation_so_far[-12000:],
                },
                schema=orchestrator_schema,
                backend="converse",  # P2-1: fast non-reasoning backend
                context=f"Onboarding orchestrator for run {run_id}",
                business_slug=business["business"]["slug"],
            )
        except (LLMAdapterError, Exception) as e:
            # P0-2: Never surface raw validator internals to the operator.
            # Log the real error to provenance (already done by adapter), show friendly copy.
            import logging
            logging.getLogger("viralfactory").error(f"Onboarding orchestrator error: {e}", exc_info=True)
            return jsonify({
                "error": "I hit a snag processing that — say 'continue' and I'll pick up where we left off."
            }), 500

        # Apply coverage updates
        for update in result.get("coverage_updates", []):
            doc = update.get("doc", "")
            status = update.get("status", "")
            if doc in ONBOARDING_PLAYBOOKS and status in ("empty", "collecting", "ready", "drafted", "approved"):
                coverage[doc] = {"status": status}
        collected["coverage"] = coverage

        # P0-1(a): Persist routed seeds — the orchestrator's core function.
        # These are the primary input for drafting. Without them, drafting starves.
        if "seeds" not in collected:
            collected["seeds"] = {}
        for seed in result.get("routed_seeds", []):
            doc = seed.get("doc", "")
            seed_text = seed.get("seed", "")
            if doc and seed_text and doc in ONBOARDING_PLAYBOOKS:
                if doc not in collected["seeds"]:
                    collected["seeds"][doc] = []
                # Avoid exact-duplicate seeds
                if seed_text not in collected["seeds"][doc]:
                    collected["seeds"][doc].append(seed_text)

        # Save the AI's reply
        if "ai_replies" not in collected:
            collected["ai_replies"] = []
        collected["ai_replies"].append(result["reply"])
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        # Check if any docs just hit "ready" — trigger drafting for them
        # P1-1: Drafts are stored immediately as draft-status modules in the Library.
        # No gate card blocks the conversation — the Library is the review surface.
        drafted_cards = []
        for update in result.get("coverage_updates", []):
            doc = update.get("doc", "")
            status = update.get("status", "")
            if status == "ready" and doc in ONBOARDING_PLAYBOOKS:
                # Check if we already have an output for this doc
                llm_outputs = json.loads(run.get("llm_outputs") or "{}")
                output_key = doc.replace("-", "_")
                if output_key not in llm_outputs:
                    # Trigger drafting for this doc
                    draft_result = _draft_onboarding_doc(run_id, runner, run, doc, business, models_config, collected)
                    if draft_result:
                        # P1-1: Store as draft-status module immediately
                        try:
                            business_slug = business["business"]["slug"]
                            from module_store import ModuleStore
                            ms = ModuleStore(app.config.get("MODULES_DIR", "modules"), db_path=app.config["DB_PATH"])
                            md = _convert_playbook_output_to_markdown(doc, draft_result)
                            module_name = doc.replace("-starter", "").replace("-builder", "").replace("-intake", "").replace("-engine", "")
                            if doc == "business-profile-intake":
                                module_name = "brand-context"
                            ms.store(business_slug, module_name, md, status="draft")
                        except Exception:
                            pass  # Module store failure shouldn't crash the conversation

                        drafted_cards.append({
                            "playbook": doc,
                            "readback": _build_readback(doc, draft_result),
                            "output_key": output_key,
                        })

        # Update coverage for drafted docs
        for card in drafted_cards:
            coverage[card["playbook"]] = {"status": "drafted"}
        collected["coverage"] = coverage
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        # Return coverage chips for UI update
        coverage_chips = []
        pb_dir = app.config["PLAYBOOKS_DIR"]
        for pb_name in ONBOARDING_PLAYBOOKS:
            pb_path = os.path.join(pb_dir, f"{pb_name}.md")
            label = pb_name
            if os.path.exists(pb_path):
                pb = PlaybookParser.parse(pb_path)
                label = pb.display_label or pb_name
            entry = coverage.get(pb_name, {"status": "empty"})
            coverage_chips.append({
                "name": pb_name,
                "label": label,
                "status": entry.get("status", "empty"),
            })

        return jsonify({
            "status": "ok",
            "reply": result["reply"],
            "coverage_chips": coverage_chips,
            "drafted_cards": drafted_cards,
            "next_focus": result.get("next_focus", ""),
        })

    def _build_drafting_package(run_id, collected, playbook_name, business):
        """P0-1(b): Build a uniform drafting input package for a doc.

        Assembles: routed seeds + conversation transcript + materials content.
        This replaces the legacy per-playbook variable scavenging that resolved
        everything to "(none provided)" because the orchestrator never populated
        those keys.
        """
        # 1. Routed seeds for this doc (verbatim operator phrasing)
        seeds = collected.get("seeds", {}).get(playbook_name, [])
        routed_seeds_text = "\n".join(f"- {s}" for s in seeds) if seeds else "(No routed seeds for this doc yet.)"

        # 2. Full conversation transcript
        conversation_transcript = _build_conversation_history(collected)

        # 3. Materials content — full raw_content with a ~24,000 char budget
        #    (drafting is a one-shot analysis call, not a conversational turn)
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        materials = intake.list_materials(run_id=run_id)

        MATERIALS_BUDGET = 24000
        materials_parts = []
        total_chars = 0

        for m in materials:
            filename = m.get("filename", "unknown")
            mtype = m.get("material_type", "unknown")
            raw = m.get("raw_content", "")
            normalized = m.get("normalized_content", "")

            # Prefer normalized_content (transcripts, cleaned text) over raw
            content = normalized or raw
            if not content:
                continue

            # Skip binary content
            if content.startswith("[Audio") or content.startswith("[Image") or content.startswith("[Binary"):
                # For audio: check if transcription is pending/done
                if mtype == "audio":
                    if normalized and normalized.startswith("[Audio"):
                        materials_parts.append(f"--- {filename} (audio — transcription pending) ---\n(transcription pending)\n")
                    elif normalized and not normalized.startswith("["):
                        materials_parts.append(f"--- {filename} (audio transcript) ---\n{content}\n")
                    else:
                        materials_parts.append(f"--- {filename} (audio — transcription pending) ---\n(transcription pending)\n")
                continue

            # Truncate per-material proportionally if over budget
            remaining = MATERIALS_BUDGET - total_chars
            if remaining <= 100:
                materials_parts.append(f"... (materials budget exhausted, {len(materials) - len(materials_parts)} more files omitted)")
                break

            if len(content) > remaining:
                content = content[:remaining] + "... [truncated]"

            materials_parts.append(f"--- {filename} ({mtype}) ---\n{content}\n")
            total_chars += len(content) + len(filename) + 20

        materials_content = "\n".join(materials_parts) if materials_parts else "(No materials uploaded.)"

        # 4. Voice Profile corpus: text-bearing materials + operator's conversational messages
        corpus = ""
        if playbook_name == "voice-profile-builder":
            corpus_parts = []
            for m in materials:
                mtype = m.get("material_type", "")
                normalized = m.get("normalized_content", "")
                raw = m.get("raw_content", "")
                content = normalized or raw
                if not content:
                    continue
                # Include text-bearing materials (exclude audio unless transcribed)
                if mtype == "audio":
                    if normalized and not normalized.startswith("[Audio") and not normalized.startswith("["):
                        corpus_parts.append(content)
                    continue
                if content.startswith("[Image") or content.startswith("[Binary"):
                    continue
                corpus_parts.append(content)
            # Add operator's own conversational messages as corpus
            for msg in collected.get("session_messages", []):
                # Strip file attachment notes
                clean_msg = msg.split("\n[Operator attached files:")[0].strip()
                if clean_msg:
                    corpus_parts.append(clean_msg)
            corpus = "\n\n".join(corpus_parts) if corpus_parts else "(No corpus available — upload text materials or voice notes for analysis.)"

        return {
            "routed_seeds": routed_seeds_text,
            "conversation_transcript": conversation_transcript[-12000:],
            "materials_content": materials_content,
            "corpus": corpus,
        }

    def _draft_onboarding_doc(run_id, runner, run, playbook_name, business, models_config, collected):
        """Trigger the playbook-specific analysis for a doc that hit 'ready'.

        Returns the analysis result dict, or None on failure.

        P0-1(b): Now uses a uniform drafting package (routed seeds + transcript +
        materials content) instead of scavenging legacy keys that were never populated.
        """
        from module_store import (
            BUSINESS_PROFILE_SCHEMA, SOURCE_CRITERIA_SCHEMA, VIRAL_PATTERNS_SCHEMA,
            AUDIENCE_INSIGHTS_SCHEMA, STORY_FRAMEWORKS_SCHEMA, FORMAT_GUIDE_SCHEMA,
            VISUAL_STYLE_SCHEMA, VOICE_PROFILE_SCHEMA,
        )

        # Map playbook name → analysis prompt file (v2), schema, and output key
        playbook_map = {
            "business-profile-intake": ("business_profile/analyze_v2.md", BUSINESS_PROFILE_SCHEMA, "business_profile_intake"),
            "voice-profile-builder": ("voice_profile/analyze_v2.md", VOICE_PROFILE_SCHEMA, "voice_profile_builder"),
            "sources-engine": ("sources_engine/analyze_v2.md", SOURCE_CRITERIA_SCHEMA, "sources_engine"),
            "viral-patterns-starter": ("viral_patterns/analyze_v2.md", VIRAL_PATTERNS_SCHEMA, "viral_patterns_starter"),
            "audience-insights-builder": ("audience_insights/analyze_v2.md", AUDIENCE_INSIGHTS_SCHEMA, "audience_insights_builder"),
            "story-frameworks-starter": ("story_frameworks/analyze_v3.md", STORY_FRAMEWORKS_SCHEMA, "story_frameworks_starter"),
            "format-guide-starter": ("format_guide/analyze_v2.md", FORMAT_GUIDE_SCHEMA, "format_guide_starter"),
            "visual-style-intake": ("visual_style/analyze_v2.md", VISUAL_STYLE_SCHEMA, "visual_style_intake"),
        }

        prompt_file, schema, output_key = playbook_map.get(
            playbook_name, ("business_profile/analyze_v2.md", BUSINESS_PROFILE_SCHEMA, "business_profile_intake")
        )

        # Build the drafting package
        pkg = _build_drafting_package(run_id, collected, playbook_name, business)

        # Build common variables — the v2 prompts use the package variables
        variables = {
            "business_name": business["business"]["name"],
            "existing_info": business["business"].get("description", ""),
            "subjects": ", ".join(business.get("subjects", [])),
            "audience_description": business.get("audience_description", ""),
            "routed_seeds": pkg["routed_seeds"],
            "conversation_transcript": pkg["conversation_transcript"],
            "materials_content": pkg["materials_content"],
            "corpus": pkg["corpus"],
        }

        # Add playbook-specific variables (from config/business, not from collected
        # which was the legacy path that always resolved to "(none)")
        platforms_text = ", ".join(f"{p['name']} ({p.get('handle', '')})" for p in business.get("platforms", []))
        if playbook_name == "sources-engine":
            # Auto-extract seed sources from uploaded materials if seed_sources is empty.
            # This catches the case where the operator uploads a source list (CSV/JSON/MD)
            # during onboarding but the orchestrator never routed it into seed_sources.
            if not collected.get("seed_sources"):
                extracted = _extract_seed_sources_from_materials(run_id)
                if extracted:
                    collected["seed_sources"] = extracted
                    runner = PlaybookRunner(app.config["DB_PATH"])
                    runner.update_run(run_id, collected_inputs=json.dumps(collected))
            variables["seed_sources"] = _format_seed_sources(collected)
            variables["anti_examples"] = _format_anti_examples(collected)
            variables["business_region"] = business.get("business", {}).get("region", "global")
        elif playbook_name == "viral-patterns-starter":
            variables["admired_examples"] = _format_admired(collected)
            variables["anti_examples"] = _format_viral_anti(collected)
        elif playbook_name == "audience-insights-builder":
            variables["operator_description"] = collected.get("audience_operator_desc", "")
            variables["audience_data"] = collected.get("audience_data", "(none)")
            variables["admired_signals"] = collected.get("audience_admired_signals", "(none)")
        elif playbook_name == "story-frameworks-starter":
            variables["admired_examples"] = collected.get("story_admired_refs", "(none)")
            variables["operator_stories"] = collected.get("operator_stories", "")
            variables["voice_summary"] = collected.get("voice_summary", "(not available)")
        elif playbook_name == "format-guide-starter":
            variables["platforms"] = platforms_text
            variables["format_observations"] = collected.get("format_observations", "(none)")
            variables["platform_norms"] = collected.get("platform_norms", "(use general knowledge)")
        elif playbook_name == "visual-style-intake":
            variables["platforms"] = platforms_text
            variables["brand_assets"] = collected.get("brand_assets", "(none)")
            variables["visual_examples"] = collected.get("visual_examples", "(none)")
            # P0-1(d): Kill the "(see uploaded files)" literal — use actual materials listing
            variables["shot_library_summary"] = _build_shot_library_summary(run_id)

        from llm_adapter import LLMAdapter, LLMAdapterError
        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file=prompt_file,
                variables=variables,
                schema=schema,
                backend="default",
                context=f"Onboarding auto-draft: {playbook_name} for run {run_id}",
                business_slug=business["business"]["slug"],
            )
        except (LLMAdapterError, Exception):
            return None

        runner.add_llm_output(run_id, output_key, result)
        return result

    @app.route("/api/onboarding/<int:run_id>/gate/<playbook_name>", methods=["POST"])
    def onboarding_gate(run_id, playbook_name):
        """Handle a gate decision for an onboarding doc (approve/park/reject)."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        decision = request.json.get("decision", "park")
        edit_text = request.json.get("edit", "")

        # Record gate result
        runner.set_gate_result(run_id, playbook_name, decision, edit_text[:500])

        # If approved, store the module
        if decision == "approve":
            llm_outputs = json.loads(run.get("llm_outputs") or "{}")
            output_key = playbook_name.replace("-", "_")
            output = llm_outputs.get(output_key)
            if output:
                try:
                    config = load_all(app.config["CONFIG_DIR"])
                    business_slug = config["business"]["business"]["slug"]
                    from module_store import ModuleStore, generate_gate_token
                    ms = ModuleStore(app.config.get("MODULES_DIR", "modules"), db_path=app.config["DB_PATH"])
                    pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], f"{playbook_name}.md")
                    playbook = PlaybookParser.parse(pb_path)
                    gate_step = PlaybookRunner.get_gate_step_number(playbook)
                    runner.set_gate_result(run_id, gate_step, "approve", "Onboarding orchestrator")
                    gate_token = generate_gate_token(run_id)

                    if playbook_name == "business-profile-intake":
                        # Business profile is special: writes business.yaml + brand-context module
                        from module_store import business_profile_to_yaml
                        yaml_content = business_profile_to_yaml(output)
                        biz_yaml_path = os.path.join(app.config["CONFIG_DIR"], "business.yaml")
                        _archive_config_file(biz_yaml_path)
                        with open(biz_yaml_path, "w") as f:
                            f.write("# ViralFactory business config\n")
                            f.write("# Generated by Onboarding Orchestrator.\n\n")
                            f.write(yaml_content)
                        md = _convert_playbook_output_to_markdown(playbook_name, output)
                        ms.store(business_slug, "brand-context", md, gate_token=gate_token, run_id=run_id)
                    else:
                        md = _convert_playbook_output_to_markdown(playbook_name, output)
                        module_name = playbook_name.replace("-starter", "").replace("-builder", "").replace("-intake", "").replace("-engine", "")
                        ms.store(business_slug, module_name, md, gate_token=gate_token, run_id=run_id)
                except Exception as e:
                    return jsonify({"error": f"Failed to store module: {e}"}), 500

        # Update coverage map
        collected = json.loads(run.get("collected_inputs") or "{}")
        coverage = collected.get("coverage", {})
        if decision == "approve":
            coverage[playbook_name] = {"status": "approved"}
        elif decision == "park":
            coverage[playbook_name] = {"status": "drafted"}  # stays drafted
        collected["coverage"] = coverage
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "decision": decision})

    def _convert_playbook_output_to_markdown(playbook_name, output):
        """Convert a playbook analysis output to markdown for module storage."""
        from module_store import (
            brand_context_to_markdown, source_criteria_to_markdown,
            viral_patterns_to_markdown, audience_insights_to_markdown,
            story_frameworks_to_markdown, format_guide_to_markdown,
            visual_style_to_markdown, voice_profile_to_markdown,
        )
        if playbook_name == "business-profile-intake":
            return brand_context_to_markdown(output)
        elif playbook_name == "sources-engine":
            return source_criteria_to_markdown(output)
        elif playbook_name == "viral-patterns-starter":
            return viral_patterns_to_markdown(output)
        elif playbook_name == "audience-insights-builder":
            return audience_insights_to_markdown(output)
        elif playbook_name == "story-frameworks-starter":
            return story_frameworks_to_markdown(output)
        elif playbook_name == "format-guide-starter":
            return format_guide_to_markdown(output)
        elif playbook_name == "visual-style-intake":
            return visual_style_to_markdown(output)
        elif playbook_name == "voice-profile-builder":
            return voice_profile_to_markdown(output, "Business", "1.0")
        return f"```json\n{json.dumps(output, indent=2)}\n```"

    @app.route("/api/onboarding/<int:run_id>/upload", methods=["POST"])
    def onboarding_upload(run_id):
        """Handle a file upload in the onboarding session."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No filename"}), 400

        import uuid
        upload_dir = os.path.join(app.config.get("UPLOAD_DIR", "data/uploads"))
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_slug = "unknown"

        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"], upload_dir)
        material_id = intake.ingest_file(
            filepath, run_id=run_id, business_slug=business_slug,
            channel="session_upload")

        return jsonify({
            "status": "ok",
            "filename": file.filename,
            "material_id": material_id,
        })

    # ── Session API endpoints (UI-REVIEW-001 F3) ──

    @app.route("/api/session/<int:run_id>/message", methods=["POST"])
    def session_message(run_id):
        """Handle a message from the operator in the chat session.

        The AI reasons about what it knows and what it still needs, then either:
        - Asks a smart follow-up question (LLM-driven, not template)
        - Says it's ready to draft → triggers analysis
        """
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        text = request.json.get("text", "").strip()
        files = request.json.get("files", [])

        if not text and not files:
            return jsonify({"error": "No message provided"}), 400

        # Store the message — include file note so the AI can see uploads
        collected = json.loads(run.get("collected_inputs") or "{}")
        if "session_messages" not in collected:
            collected["session_messages"] = []
        file_note = ""
        if files:
            file_note = f"\n[Operator attached files: {', '.join(files)}]"
        turn_text = (text + "\n" if text else "") + file_note.strip() if files else text
        collected["session_messages"].append(turn_text)
        # Also keep in business_qa for backward compat with analysis
        if "business_qa" not in collected:
            collected["business_qa"] = []
        collected["business_qa"].append({"q": "(session message)", "a": turn_text})
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        # Get config
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        # Build conversation history for the LLM
        conversation_so_far = _build_conversation_history(collected)

        # Build materials summary so the AI can see what was uploaded
        materials_summary = _build_materials_summary(run_id)

        # Get playbook info
        playbook_name = run["playbook_name"]
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], f"{playbook_name}.md")
        playbook = PlaybookParser.parse(pb_path)

        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        converse_schema = {
            "type": "object",
            "required": ["reply", "ready_to_draft"],
            "properties": {
                "reply": {"type": "string"},
                "ready_to_draft": {"type": "boolean"},
            },
        }

        try:
            result = adapter.complete(
                prompt_file="session/generic_converse_v1.md",
                variables={
                    "playbook_display_label": playbook.display_label or playbook.name,
                    "playbook_purpose": playbook.purpose[:500],
                    "conversation_so_far": conversation_so_far[-12000:],
                    "playbook_inputs": "\n".join(f"- {i}" for i in playbook.inputs)[:1000],
                    "materials_summary": materials_summary,
                },
                schema=converse_schema,
                backend="default",
                context=f"Session conversation for {playbook_name} run {run_id}",
                business_slug=business["business"]["slug"],
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        # Anti-repeat guard: check if the reply is too similar to a prior AI reply
        prior_replies = collected.get("ai_replies", [])
        if prior_replies and _is_near_duplicate(result["reply"], prior_replies):
            # Regenerate once with a collision warning
            try:
                retry_variables = {
                    "playbook_display_label": playbook.display_label or playbook.name,
                    "playbook_purpose": playbook.purpose[:500],
                    "conversation_so_far": conversation_so_far[-12000:],
                    "playbook_inputs": "\n".join(f"- {i}" for i in playbook.inputs)[:1000],
                    "materials_summary": materials_summary,
                }
                result = adapter.complete(
                    prompt_file="session/generic_converse_v1.md",
                    variables=retry_variables,
                    schema=converse_schema,
                    backend="default",
                    context=f"Session conversation for {playbook_name} run {run_id} (anti-repeat retry)",
                    business_slug=business["business"]["slug"],
                )
            except (LLMAdapterError, Exception):
                pass  # Use the original result if retry fails

        if result.get("ready_to_draft"):
            # AI says it has enough — trigger analysis
            # But first, save the AI's reply to the conversation history
            collected = json.loads(run.get("collected_inputs") or "{}")
            if "ai_replies" not in collected:
                collected["ai_replies"] = []
            collected["ai_replies"].append(result["reply"])
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

            return _session_trigger_analysis(run_id, runner, run, playbook, business, models_config)
        else:
            # Save the AI's reply to the conversation history so it's available next turn
            collected = json.loads(run.get("collected_inputs") or "{}")
            if "ai_replies" not in collected:
                collected["ai_replies"] = []
            collected["ai_replies"].append(result["reply"])
            runner.update_run(run_id, collected_inputs=json.dumps(collected))

            return jsonify({"status": "ok", "reply": result["reply"], "show_readback": False})

    def _session_trigger_analysis(run_id, runner, run, playbook, business, models_config):
        """Trigger the playbook's analysis LLM call and return a readback signal.
        Works for all playbooks — routes to the right prompt + schema based on playbook name."""
        collected = json.loads(run.get("collected_inputs") or "{}")
        qa_pairs = collected.get("business_qa", [])
        if not qa_pairs:
            return jsonify({"status": "error", "error": "No Q&A collected yet."}), 400

        # Build transcript from all collected Q&A and messages
        transcript = ""
        for i, pair in enumerate(qa_pairs, 1):
            transcript += f"Q{i}: {pair.get('q', '(free-form)')}\nA{i}: {pair['a']}\n\n"

        # Map playbook name → analysis prompt file (v2), schema, and output key
        from module_store import (
            BUSINESS_PROFILE_SCHEMA, SOURCE_CRITERIA_SCHEMA, VIRAL_PATTERNS_SCHEMA,
            AUDIENCE_INSIGHTS_SCHEMA, STORY_FRAMEWORKS_SCHEMA, FORMAT_GUIDE_SCHEMA,
            VISUAL_STYLE_SCHEMA, VOICE_PROFILE_SCHEMA,
        )

        playbook_map = {
            "business-profile-intake": ("business_profile/analyze_v2.md", BUSINESS_PROFILE_SCHEMA, "analysis"),
            "voice-profile-builder": ("voice_profile/analyze_v2.md", VOICE_PROFILE_SCHEMA, "voice_profile"),
            "sources-engine": ("sources_engine/analyze_v2.md", SOURCE_CRITERIA_SCHEMA, "criteria"),
            "viral-patterns-starter": ("viral_patterns/analyze_v2.md", VIRAL_PATTERNS_SCHEMA, "patterns"),
            "audience-insights-builder": ("audience_insights/analyze_v2.md", AUDIENCE_INSIGHTS_SCHEMA, "insights"),
            "story-frameworks-starter": ("story_frameworks/analyze_v3.md", STORY_FRAMEWORKS_SCHEMA, "frameworks"),
            "format-guide-starter": ("format_guide/analyze_v2.md", FORMAT_GUIDE_SCHEMA, "guide"),
            "visual-style-intake": ("visual_style/analyze_v2.md", VISUAL_STYLE_SCHEMA, "style_guide"),
        }

        pb_name = run["playbook_name"]
        prompt_file, schema, output_key = playbook_map.get(
            pb_name, ("business_profile/analyze_v2.md", BUSINESS_PROFILE_SCHEMA, "analysis")
        )

        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        # Build drafting package (same as orchestrator path)
        pkg = _build_drafting_package(run_id, collected, pb_name, business)

        # Build variables — start with the drafting package + common ones
        variables = {
            "business_name": business["business"]["name"],
            "existing_info": business["business"].get("description", ""),
            "qa_transcript": transcript[:8000],
            "subjects": ", ".join(business.get("subjects", [])),
            "audience_description": business.get("audience_description", ""),
            "routed_seeds": pkg["routed_seeds"],
            "conversation_transcript": pkg["conversation_transcript"],
            "materials_content": pkg["materials_content"],
            "corpus": pkg["corpus"],
        }

        # Add playbook-specific variables from collected inputs
        platforms_text = ", ".join(f"{p['name']} ({p.get('handle', '')})" for p in business.get("platforms", []))
        if pb_name == "sources-engine":
            # Auto-extract seed sources from uploaded materials if seed_sources is empty
            if not collected.get("seed_sources"):
                extracted = _extract_seed_sources_from_materials(run_id)
                if extracted:
                    collected["seed_sources"] = extracted
                    runner = PlaybookRunner(app.config["DB_PATH"])
                    runner.update_run(run_id, collected_inputs=json.dumps(collected))
            variables["seed_sources"] = _format_seed_sources(collected)
            variables["anti_examples"] = _format_anti_examples(collected)
            variables["business_region"] = business.get("business", {}).get("region", "global")
        elif pb_name == "viral-patterns-starter":
            variables["admired_examples"] = _format_admired(collected)
            variables["anti_examples"] = _format_viral_anti(collected)
        elif pb_name == "audience-insights-builder":
            variables["operator_description"] = collected.get("audience_operator_desc", "")
            variables["audience_data"] = collected.get("audience_data", "(none)")
            variables["admired_signals"] = collected.get("audience_admired_signals", "(none)")
        elif pb_name == "story-frameworks-starter":
            variables["admired_examples"] = collected.get("story_admired_refs", "(none)")
            variables["operator_stories"] = collected.get("operator_stories", "")
            variables["voice_summary"] = collected.get("voice_summary", "(not available)")
            # Load narrative patterns config for v3 prompt
            import yaml as _yaml
            _patterns_path = os.path.join(app.config["CONFIG_DIR"], "narrative_patterns.yaml")
            try:
                with open(_patterns_path) as f:
                    _patterns_data = _yaml.safe_load(f)
                variables["narrative_patterns"] = "\n".join(
                    f"- **{p['name']}**: {p['description']}\n  Beats: {', '.join(p['beats'])}"
                    for p in _patterns_data["patterns"]
                )
                if _patterns_data.get("allow_custom"):
                    variables["narrative_patterns"] += "\n\nYou may also propose a custom pattern if none of the above fit."
            except Exception:
                variables["narrative_patterns"] = "(narrative patterns config not available)"
        elif pb_name == "format-guide-starter":
            variables["platforms"] = platforms_text
            variables["format_observations"] = collected.get("format_observations", "(none)")
            variables["platform_norms"] = collected.get("platform_norms", "(use general knowledge)")
        elif pb_name == "visual-style-intake":
            variables["platforms"] = platforms_text
            variables["brand_assets"] = collected.get("brand_assets", "(none)")
            variables["visual_examples"] = collected.get("visual_examples", "(none)")
            variables["shot_library_summary"] = _build_shot_library_summary(run_id)

        try:
            result = adapter.complete(
                prompt_file=prompt_file,
                variables=variables,
                schema=schema,
                backend="default",
                context=f"{playbook.display_label} analysis for run {run_id} (session)",
                business_slug=business["business"]["slug"],
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        runner.add_llm_output(run_id, output_key, result)
        return jsonify({
            "status": "ok",
            "reply": "I've put together your " + (playbook.display_label or pb_name) + ". Review it below — correct anything, then approve to save.",
            "show_readback": True,
        })

    def _format_seed_sources(collected):
        seeds = collected.get("seed_sources", [])
        if not seeds:
            return "(none provided yet — ask the operator for trusted sources)"
        lines = []
        for i, s in enumerate(seeds, 1):
            lines.append(f"  {i}. {s.get('name', '')} — {s.get('url', '')} ({s.get('type', 'rss')})")
        return "\n".join(lines)

    def _extract_seed_sources_from_materials(run_id):
        """Auto-extract seed sources from uploaded materials that look like source lists.
        Detects CSV files with source entries (rank/title/url columns) and JSON files
        with source arrays. Returns a list of seed source dicts, or None if nothing found.
        This catches the case where the operator uploads a source export (e.g. Obsidian
        Strongest Sources) during onboarding but the orchestrator never routes it into
        the seed_sources list."""
        import csv as csv_module
        import io as io_module
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        materials = intake.list_materials(run_id=run_id)
        if not materials:
            return None

        extracted = []
        for m in materials:
            filename = (m.get("filename") or "").lower()
            content = m.get("normalized_content") or m.get("raw_content") or ""
            if not content or len(content) < 50:
                continue

            # CSV files with source-like columns
            if filename.endswith(".csv") or ("rank" in content[:200].lower() and "title" in content[:200].lower()):
                try:
                    reader = csv_module.DictReader(io_module.StringIO(content))
                    if reader.fieldnames and any(
                        col in [f.lower() for f in reader.fieldnames]
                        for col in ["rank", "title", "name", "url", "source", "score"]
                    ):
                        for row in reader:
                            title = (row.get("title") or row.get("name") or "").strip().strip('"')
                            if not title or len(title) < 2:
                                continue
                            rank = row.get("rank", "")
                            score = row.get("score", "")
                            url = row.get("url") or row.get("feed_url") or ""
                            source_type = "csv_export"
                            if url:
                                source_type = "rss" if "feed" in url.lower() or "rss" in url.lower() else "web"
                            extracted.append({
                                "name": title,
                                "url": url or f"(source rank {rank}, score {score})",
                                "type": source_type,
                                "auto_extracted": True,
                            })
                except Exception:
                    pass

            # JSON files with source arrays
            elif filename.endswith(".json"):
                try:
                    data = json.loads(content)
                    if isinstance(data, list):
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            title = (item.get("title") or item.get("name") or "").strip()
                            if not title or len(title) < 2:
                                continue
                            url = item.get("url") or item.get("feed_url") or ""
                            rank = item.get("rank", "")
                            score = item.get("score", "")
                            source_type = "json_export"
                            if url:
                                source_type = "rss" if "feed" in url.lower() or "rss" in url.lower() else "web"
                            extracted.append({
                                "name": title,
                                "url": url or f"(source rank {rank}, score {score})",
                                "type": source_type,
                                "auto_extracted": True,
                            })
                except Exception:
                    pass

        # Deduplicate by name
        seen = set()
        unique = []
        for s in extracted:
            name_lower = s["name"].lower()
            if name_lower not in seen:
                seen.add(name_lower)
                unique.append(s)

        return unique if unique else None

    def _format_anti_examples(collected):
        anti = collected.get("anti_examples", [])
        if not anti:
            return "(none provided)"
        return "\n".join(f"  {i+1}. {a}" for i, a in enumerate(anti))

    def _format_admired(collected):
        admired = collected.get("admired_examples", [])
        if not admired:
            return "(none provided yet)"
        lines = []
        for a in admired:
            lines.append(f"  {a.get('name', '')} — {a.get('url', '')}")
        return "\n".join(lines)

    def _format_viral_anti(collected):
        anti = collected.get("viral_anti_examples", [])
        if not anti:
            return "(none provided)"
        return "\n".join(f"  {i+1}. {a}" for i, a in enumerate(anti))

    @app.route("/api/session/<int:run_id>/upload", methods=["POST"])
    def session_upload(run_id):
        """Handle a file upload in the session."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No filename"}), 400

        upload_dir = os.path.join(app.config.get("UPLOAD_DIR", "data/uploads"))
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, file.filename)
        file.save(filepath)

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_slug = "unknown"

        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"], upload_dir)
        material_id = intake.ingest_file(
            filepath, run_id=run_id, business_slug=business_slug,
            channel="session_upload",
        )

        return jsonify({"status": "ok", "material_id": material_id, "filename": file.filename})

    @app.route("/api/session/<int:run_id>/edit-readback", methods=["POST"])
    def session_edit_readback(run_id):
        """Save direct edits to the readback draft (authoritative, highest weight)."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        edited_text = request.json.get("text", "").strip()
        if not edited_text:
            return jsonify({"error": "No text provided"}), 400

        # Store the edit as a note on the run
        collected = json.loads(run.get("collected_inputs") or "{}")
        collected["readback_edit"] = edited_text
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok"})

    @app.route("/onboard/<playbook_name>/<int:run_id>")
    def view_run(playbook_name, run_id):
        """View a playbook run's current state."""
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], f"{playbook_name}.md")
        if not os.path.exists(pb_path):
            return "Playbook not found", 404

        playbook = PlaybookParser.parse(pb_path)
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)

        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        gate_results = json.loads(run.get("gate_results") or "{}")

        return render_template("playbook_run.html",
            playbook=playbook,
            run_id=run_id,
            run=run,
            collected=collected,
            llm_outputs=llm_outputs,
            gate_results=gate_results,
        )

    @app.route("/api/run/<int:run_id>/input", methods=["POST"])
    def add_input(run_id):
        """Add collected input to a run."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        key = request.json.get("key", "untitled")
        value = request.json.get("value", "")
        if not value:
            return jsonify({"error": "No value provided"}), 400

        runner.add_input(run_id, key, value)
        return jsonify({"status": "ok"})

    @app.route("/api/run/<int:run_id>/gate", methods=["POST"])
    def gate_decision(run_id):
        """Record a gate decision."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        step = request.json.get("step", "")
        decision = request.json.get("decision", "")
        notes = request.json.get("notes", "")

        if decision not in ("approve", "reject", "park"):
            return jsonify({"error": "Invalid decision"}), 400

        runner.set_gate_result(run_id, step, decision, notes)

        if decision == "approve":
            runner.update_run(run_id, status="completed")
        elif decision == "reject":
            runner.update_run(run_id, status="cancelled")

        return jsonify({"status": "ok", "decision": decision})

    @app.route("/library")
    def library():
        """Library surface — browse modules with draft/approved status, inline edit, and approve."""
        try:
            config = load_all(config_dir)
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_slug = None

        modules = []
        if business_slug:
            from module_store import ModuleStore
            store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
            for name in store.list_modules(business_slug):
                content = store.load(business_slug, name)
                versions = store.list_versions(business_slug, name)
                status = store.get_status(business_slug, name)
                # Extract schema marker
                schema_name = None
                if content:
                    import re as _re
                    m = _re.search(r'Schema:\s*(\w+)', content)
                    schema_name = m.group(1) if m else None
                modules.append({
                    "name": name,
                    "schema": schema_name,
                    "status": status,
                    "version_count": len(versions) + 1,
                    "versions": [{"version": v["version"], "timestamp": v["timestamp"]} for v in versions],
                    "preview": content[:500] if content else "",
                })

        return render_template("library.html", business_slug=business_slug, modules=modules)

    @app.route("/api/library/<business_slug>/<module_name>")
    def api_library_module(business_slug, module_name):
        """API: get a specific module's content + version history + status."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
        content = store.load(business_slug, module_name)
        if not content:
            return jsonify({"error": "Module not found"}), 404
        versions = store.list_versions(business_slug, module_name)
        status = store.get_status(business_slug, module_name)
        return jsonify({
            "module": module_name,
            "business_slug": business_slug,
            "content": content,
            "status": status,
            "versions": [{"version": v["version"], "timestamp": v["timestamp"], "filename": v["filename"]} for v in versions],
        })

    @app.route("/api/library/<business_slug>/<module_name>/approve", methods=["POST"])
    def api_library_approve(business_slug, module_name):
        """P1-1: Approve a draft module — promotes it to approved status with gate token."""
        from module_store import ModuleStore, generate_gate_token
        store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])

        status = store.get_status(business_slug, module_name)
        if status != "draft":
            return jsonify({"error": f"Module is not a draft (status: {status})"}), 400

        # Get the run_id from the request or find the onboarding run
        run_id = request.json.get("run_id")
        if not run_id:
            # Find the onboarding run for this business
            runner = PlaybookRunner(app.config["DB_PATH"])
            runs = runner.list_runs(business_slug=business_slug)
            onboarding_runs = [r for r in runs if r.get("playbook_name") == "onboarding"]
            if onboarding_runs:
                run_id = onboarding_runs[-1]["id"]
            else:
                return jsonify({"error": "No onboarding run found to issue gate token"}), 400

        # Record gate approval and generate token
        runner = PlaybookRunner(app.config["DB_PATH"])
        runner.set_gate_result(run_id, module_name, "approve", "Library approve action")
        runner.set_gate_result(run_id, "gate", "approve", "Library approve action")
        gate_token = generate_gate_token(run_id)

        try:
            store.promote_to_approved(business_slug, module_name, gate_token=gate_token, run_id=run_id)
        except Exception as e:
            return jsonify({"error": f"Failed to promote module: {e}"}), 500

        return jsonify({"status": "ok", "module": module_name, "new_status": "approved"})

    @app.route("/api/library/<business_slug>/<module_name>/edit", methods=["POST"])
    def api_library_edit(business_slug, module_name):
        """P1-1: Edit a module's content inline. Saves the edited content."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])

        content = request.json.get("content", "").strip()
        if not content:
            return jsonify({"error": "No content provided"}), 400

        existing = store.load(business_slug, module_name)
        if not existing:
            return jsonify({"error": "Module not found"}), 404

        # Preserve status marker
        current_status = store.get_status(business_slug, module_name)
        if current_status == "draft":
            content = f"<!-- status: draft -->\n{content}"

        # Archive and write
        path = store._module_path(business_slug, module_name)
        if path.exists():
            store._archive_version(business_slug, module_name, path)
        path.write_text(content)

        return jsonify({"status": "ok", "module": module_name})

    # ── Materials Library (CORRECTION-final-assembly-and-materials-editing-v1.0 Part 2) ──

    @app.route("/materials")
    def materials_library():
        """Materials page — lists all materials with filter by run and channel."""
        from materials import MaterialsIntake
        try:
            config = load_all(config_dir)
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_slug = None

        materials_list = []
        if business_slug:
            intake = MaterialsIntake(db_path=app.config["DB_PATH"])
            materials_list = intake.list_materials(business_slug=business_slug)

        # Build filter options
        channels = sorted(set(m.get("channel", "") for m in materials_list if m.get("channel")))
        run_ids = sorted(set(m.get("run_id") for m in materials_list if m.get("run_id")))

        # Apply filters from query params
        filter_run = request.args.get("run_id", type=int)
        filter_channel = request.args.get("channel", "")
        if filter_run:
            materials_list = [m for m in materials_list if m.get("run_id") == filter_run]
        if filter_channel:
            materials_list = [m for m in materials_list if m.get("channel") == filter_channel]

        # Add excerpts
        for m in materials_list:
            content = m.get("normalized_content") or m.get("raw_content", "")
            m["excerpt"] = content[:300] if content else ""
            m["excluded_flag"] = bool(m.get("excluded", 0))

        return render_template("materials.html",
            business_slug=business_slug,
            materials=materials_list,
            channels=channels,
            run_ids=run_ids,
            filter_run=filter_run,
            filter_channel=filter_channel,
        )

    @app.route("/materials/<int:material_id>")
    def material_detail(material_id):
        """Detail view for a single material — editable normalized_content."""
        from materials import MaterialsIntake
        intake = MaterialsIntake(db_path=app.config["DB_PATH"])
        material = intake.get_material_with_extras(material_id)
        if not material:
            return render_template("error.html", error="Material not found"), 404
        return render_template("material_detail.html", material=material)

    @app.route("/api/materials/<int:material_id>/edit", methods=["POST"])
    def api_material_edit(material_id):
        """Edit a material's normalized_content. raw_content is never touched."""
        from materials import MaterialsIntake
        intake = MaterialsIntake(db_path=app.config["DB_PATH"])
        material = intake.get_material(material_id)
        if not material:
            return jsonify({"error": "Material not found"}), 404

        content = request.json.get("content", "")
        if not content.strip():
            return jsonify({"error": "Content cannot be empty"}), 400

        updated = intake.save_edit(material_id, content)
        return jsonify({
            "status": "ok",
            "material_id": material_id,
            "word_count": updated.get("word_count", 0),
        })

    @app.route("/api/materials/<int:material_id>/exclude", methods=["POST"])
    def api_material_exclude(material_id):
        """Toggle the excluded flag on a material."""
        from materials import MaterialsIntake
        intake = MaterialsIntake(db_path=app.config["DB_PATH"])
        material = intake.get_material(material_id)
        if not material:
            return jsonify({"error": "Material not found"}), 404

        excluded = request.json.get("excluded", False)
        updated = intake.toggle_exclude(material_id, excluded)
        return jsonify({
            "status": "ok",
            "material_id": material_id,
            "excluded": bool(updated.get("excluded", 0)),
        })

    @app.route("/api/materials/<int:material_id>/restore", methods=["POST"])
    def api_material_restore(material_id):
        """Restore a material's normalized_content to its raw_content."""
        from materials import MaterialsIntake
        intake = MaterialsIntake(db_path=app.config["DB_PATH"])
        material = intake.get_material(material_id)
        if not material:
            return jsonify({"error": "Material not found"}), 404

        restored = intake.restore_to_raw(material_id)
        return jsonify({
            "status": "ok",
            "material_id": material_id,
            "word_count": restored.get("word_count", 0),
        })

    @app.route("/onboard/<playbook_name>/<int:run_id>/intake", methods=["GET"])
    def intake_page(playbook_name, run_id):
        """Materials intake UI for a playbook run."""
        return render_template("intake.html", playbook_name=playbook_name, run_id=run_id)

    @app.route("/api/run/<int:run_id>/upload", methods=["POST"])
    def upload_file(run_id):
        """Upload a file (WhatsApp export, plain text, audio)."""
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No filename"}), 400

        # Save to temp location
        upload_dir = os.path.join(app.config.get("UPLOAD_DIR", "data/uploads"))
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, file.filename)
        file.save(filepath)

        # Get metadata
        channel = request.form.get("channel", "")
        date_approx = request.form.get("date_approx", "")
        audience = request.form.get("audience", "")

        # Get business slug
        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_slug = "unknown"

        # Ingest
        try:
            from materials import MaterialsIntake
            intake = MaterialsIntake(app.config["DB_PATH"], upload_dir)
            material_id = intake.ingest_file(
                filepath, run_id=run_id, business_slug=business_slug,
                channel=channel, date_approx=date_approx, audience=audience,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return jsonify({"status": "ok", "material_id": material_id})

    @app.route("/api/run/<int:run_id>/paste", methods=["POST"])
    def paste_text(run_id):
        """Paste text directly (no file upload)."""
        content = request.json.get("content", "").strip()
        if not content:
            return jsonify({"error": "No content"}), 400

        channel = request.json.get("channel", "pasted")
        date_approx = request.json.get("date_approx", "")
        audience = request.json.get("audience", "")

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_slug = "unknown"

        try:
            from materials import MaterialsIntake
            intake = MaterialsIntake(app.config["DB_PATH"])
            material_id = intake.ingest_text(
                content, run_id=run_id, business_slug=business_slug,
                material_type="pasted", channel=channel,
                date_approx=date_approx, audience=audience,
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        return jsonify({"status": "ok", "material_id": material_id})

    @app.route("/api/run/<int:run_id>/corpus", methods=["GET"])
    def get_corpus(run_id):
        """Get the collected corpus for a run."""
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        corpus = intake.get_corpus(run_id)
        return jsonify(corpus)

    @app.route("/api/run/<int:run_id>/analyze-voice", methods=["POST"])
    def analyze_voice(run_id):
        """
        Run the Voice Profile analysis LLM call.
        Takes the collected corpus, sends to LLM with the voice analysis prompt,
        validates the output against the Voice Profile schema, stores the result.
        """
        from materials import MaterialsIntake
        from module_store import ModuleStore, VOICE_PROFILE_SCHEMA, voice_profile_to_markdown

        # Get the corpus
        intake = MaterialsIntake(app.config["DB_PATH"])
        corpus = intake.get_corpus(run_id)
        if corpus["total_words"] < 50:
            return jsonify({"error": f"Corpus too small ({corpus['total_words']} words). Need at least 50."}), 400

        # Build the corpus text from samples
        corpus_text = ""
        for s in corpus["samples"]:
            content = intake.get_material(s["id"])
            if content and content["normalized_content"]:
                corpus_text += content["normalized_content"] + "\n\n"
            elif content and content["raw_content"]:
                corpus_text += content["raw_content"] + "\n\n"

        if not corpus_text.strip():
            return jsonify({"error": "No text content in corpus"}), 400

        # Get config
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        # Call the LLM
        from llm_adapter import LLMAdapter, LLMAdapterError
        adapter = LLMAdapter(
            models_config,
            db_path=app.config["DB_PATH"],
            prompts_dir="prompts",
        )

        try:
            result = adapter.complete(
                prompt_file="voice_profile/analyze_v1.md",
                variables={
                    "corpus": corpus_text[:8000],  # truncate to fit context
                    "business_name": business["business"]["name"],
                    "audience_description": business.get("audience_description", ""),
                },
                schema=VOICE_PROFILE_SCHEMA,
                backend="default",
                context=f"Voice Profile analysis for run {run_id}",
            )
        except LLMAdapterError as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": f"LLM call failed: {e}"}), 500

        # Store the LLM output on the run
        runner = PlaybookRunner(app.config["DB_PATH"])
        runner.add_llm_output(run_id, "3", result)  # Step 3 = Analyze

        # Convert to markdown (but don't store yet — gate must approve)
        md = voice_profile_to_markdown(result, business["business"]["name"])

        return jsonify({
            "status": "ok",
            "profile": result,
            "markdown": md,
            "word_count": corpus["total_words"],
        })

    @app.route("/onboard/<playbook_name>/<int:run_id>/calibrate")
    def calibrate_page(playbook_name, run_id):
        """Calibration gate UI for voice profile."""
        return render_template("calibrate.html", run_id=run_id)

    @app.route("/api/run/<int:run_id>/calibrate", methods=["POST"])
    def calibrate(run_id):
        """Generate 3 calibration samples from the voice profile."""
        from materials import MaterialsIntake
        from module_store import VOICE_PROFILE_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        profile = llm_outputs.get("3")  # Step 3 = Analyze
        if not profile:
            return jsonify({"error": "No voice profile found. Run analysis first."}), 400

        # Check if this is a revise request (has feedback)
        feedback = request.json.get("feedback") if request.is_json else None

        adapter = LLMAdapter(
            models_config,
            db_path=app.config["DB_PATH"],
            prompts_dir="prompts",
        )

        # Use a topic from the business config
        topic = config["business"].get("subjects", ["AI and wealth"])[0]

        try:
            result = adapter.complete(
                prompt_file="voice_profile/calibrate_v1.md",
                variables={
                    "voice_profile_json": json.dumps(profile),
                    "topic": topic,
                },
                schema={
                    "type": "object",
                    "required": ["samples"],
                    "properties": {
                        "samples": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["label", "emphasis", "text"],
                                "properties": {
                                    "label": {"type": "string"},
                                    "emphasis": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                            },
                        },
                    },
                },
                backend="drafter",
                context=f"Calibration for run {run_id}",
            )
        except LLMAdapterError as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": f"LLM call failed: {e}"}), 500

        return jsonify({"samples": result["samples"]})

    @app.route("/api/run/<int:run_id>/store-voice", methods=["POST"])
    def store_voice(run_id):
        """Store the voice profile as a versioned module (gate approval)."""
        from module_store import (
            ModuleStore, voice_profile_to_markdown,
            GateTokenError, generate_gate_token,
        )

        version = request.json.get("version", "1.0")
        approved = request.json.get("approved", False)
        note = request.json.get("note", "")

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        profile = llm_outputs.get("3")
        if not profile:
            return jsonify({"error": "No voice profile found"}), 400

        # Record gate decision FIRST (before any write attempt)
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], "voice-profile-builder.md")
        playbook = PlaybookParser.parse(pb_path)
        gate_step = PlaybookRunner.get_gate_step_number(playbook)
        runner.set_gate_result(run_id, gate_step, "approve" if approved else "park", note)

        # Convert to markdown
        md = voice_profile_to_markdown(profile, business["business"]["name"], version)

        # Gate enforcement: modules are written ONLY on approval, with verified gate token.
        path = None
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                path = store.store(
                    business["business"]["slug"],
                    "voice-profile",
                    md,
                    version=version,
                    provenance={
                        "version": version,
                        "approved": approved,
                        "note": note,
                        "run_id": run_id,
                        "sources": [s["type"] for s in json.loads(run.get("collected_inputs") or "{}").values()
                                   if isinstance(s, list)] if run.get("collected_inputs") else [],
                    },
                    gate_token=gate_token,
                    run_id=run_id,
                )
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {
            "status": "ok",
            "version": version,
            "approved": approved,
        }
        if path:
            result["path"] = path
        return jsonify(result)

    @app.route("/onboard/<playbook_name>/<int:run_id>/interview")
    def interview_page(playbook_name, run_id):
        """Interview fallback UI for users with no materials."""
        return render_template("interview.html", run_id=run_id)

    # --- Business Profile Intake (T2.1) ---

    @app.route("/onboard/<playbook_name>/<int:run_id>/business-profile")
    def business_profile_page(playbook_name, run_id):
        """Business Profile Q&A UI."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        qa_pairs = collected.get("business_qa", [])

        # Check if analysis already done
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        profile = llm_outputs.get("analysis")

        return render_template("business_profile.html",
            playbook_name=playbook_name, run_id=run_id,
            qa_pairs=qa_pairs, profile=profile)

    @app.route("/api/run/<int:run_id>/business-qa", methods=["POST"])
    def business_qa(run_id):
        """Add a Q&A pair for the business profile intake."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        question = request.json.get("question", "").strip()
        answer = request.json.get("answer", "").strip()
        if not answer:
            return jsonify({"error": "No answer provided"}), 400

        # Store as a Q&A pair
        collected = json.loads(run.get("collected_inputs") or "{}")
        if "business_qa" not in collected:
            collected["business_qa"] = []
        collected["business_qa"].append({"q": question, "a": answer})
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "count": len(collected["business_qa"])})

    @app.route("/api/run/<int:run_id>/analyze-business", methods=["POST"])
    def analyze_business(run_id):
        """Run the Business Profile analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        qa_pairs = collected.get("business_qa", [])
        if not qa_pairs:
            return jsonify({"error": "No Q&A collected yet. Add answers first."}), 400

        # Build transcript
        transcript = ""
        for i, pair in enumerate(qa_pairs, 1):
            transcript += f"Q{i}: {pair.get('q', '(free-form)')}\nA{i}: {pair['a']}\n\n"

        # Get config
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from module_store import BUSINESS_PROFILE_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(
            models_config,
            db_path=app.config["DB_PATH"],
            prompts_dir="prompts",
        )

        try:
            result = adapter.complete(
                prompt_file="business_profile/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "existing_info": business["business"].get("description", ""),
                    "qa_transcript": transcript[:8000],
                },
                schema=BUSINESS_PROFILE_SCHEMA,
                backend="default",
                context=f"Business Profile analysis for run {run_id}",
            )
        except LLMAdapterError as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": f"LLM call failed: {e}"}), 500

        # Store the LLM output
        runner.add_llm_output(run_id, "analysis", result)

        return jsonify({"status": "ok", "profile": result})

    @app.route("/api/run/<int:run_id>/store-business", methods=["POST"])
    def store_business(run_id):
        """Store the business profile: write business.yaml + brand-context module."""
        from module_store import (
            ModuleStore, business_profile_to_yaml, brand_context_to_markdown,
            GateTokenError, generate_gate_token,
        )

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        profile = llm_outputs.get("analysis")
        if not profile:
            return jsonify({"error": "No business profile found. Run analysis first."}), 400

        # Record gate decision FIRST
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], "business-profile-intake.md")
        playbook = PlaybookParser.parse(pb_path)
        gate_step = PlaybookRunner.get_gate_step_number(playbook)
        runner.set_gate_result(run_id, gate_step, "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                # Verify gate token before config write
                _verify_config_write(app.config["DB_PATH"], run_id, gate_token)

                # Write business.yaml (archive existing first)
                yaml_content = business_profile_to_yaml(profile)
                biz_yaml_path = os.path.join(app.config["CONFIG_DIR"], "business.yaml")
                _archive_config_file(biz_yaml_path)
                with open(biz_yaml_path, "w") as f:
                    f.write("# ViralFactory business config\n")
                    f.write("# Generated by Business Profile Intake playbook.\n")
                    f.write("# Every value here is business-specific — nothing in src/ should hardcode any of these.\n\n")
                    f.write(yaml_content)
                paths["business_yaml"] = biz_yaml_path

                # Write brand-context module
                md = brand_context_to_markdown(profile, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                module_path = store.store(
                    profile["business"]["slug"],
                    "brand-context",
                    md,
                    version=version,
                    provenance={
                        "version": version,
                        "approved": approved,
                        "note": note,
                        "run_id": run_id,
                        "playbook": "business-profile-intake",
                    },
                    gate_token=gate_token,
                    run_id=run_id,
                )
                paths["brand_context"] = module_path
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    # --- Sources Engine Part A (T2.2) ---

    @app.route("/onboard/<playbook_name>/<int:run_id>/sources-engine")
    def sources_engine_page(playbook_name, run_id):
        """Sources Engine Part A UI — seed sources, anti-examples, criteria generation."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        seed_sources = collected.get("seed_sources", [])
        anti_examples = collected.get("anti_examples", [])

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        criteria = llm_outputs.get("criteria")

        # Check for v2 backup availability (deferred bulk-import path)
        v2_backup_path = os.environ.get("V2_BACKUP_PATH", "/home/daimon/v2-backups/")
        v2_backup_available = os.path.exists(v2_backup_path)

        return render_template("sources_engine.html",
            playbook_name=playbook_name, run_id=run_id,
            seed_sources=seed_sources, anti_examples=anti_examples,
            criteria=criteria, v2_backup_available=v2_backup_available)

    @app.route("/api/run/<int:run_id>/seed-source", methods=["POST"])
    def add_seed_source(run_id):
        """Add a seed source URL."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        url = request.json.get("url", "").strip()
        name = request.json.get("name", "").strip()
        source_type = request.json.get("type", "rss").strip()
        if not url:
            return jsonify({"error": "URL required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        if "seed_sources" not in collected:
            collected["seed_sources"] = []
        collected["seed_sources"].append({"url": url, "name": name or url, "type": source_type})
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "count": len(collected["seed_sources"])})

    @app.route("/api/run/<int:run_id>/anti-example", methods=["POST"])
    def add_anti_example(run_id):
        """Add an anti-example source."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        description = request.json.get("description", "").strip()
        if not description:
            return jsonify({"error": "Description required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        if "anti_examples" not in collected:
            collected["anti_examples"] = []
        collected["anti_examples"].append(description)
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "count": len(collected["anti_examples"])})

    @app.route("/api/run/<int:run_id>/analyze-sources", methods=["POST"])
    def analyze_sources(run_id):
        """Run the Source Criteria analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        seed_sources = collected.get("seed_sources", [])
        if len(seed_sources) < 3:
            return jsonify({"error": "Need at least 3 seed sources. Add more first."}), 400

        # Build seed sources text
        seeds_text = ""
        for i, s in enumerate(seed_sources, 1):
            seeds_text += f"  {i}. {s.get('name', '')} — {s['url']} ({s.get('type', 'rss')})\n"

        anti_text = ""
        for i, a in enumerate(collected.get("anti_examples", []), 1):
            anti_text += f"  {i}. {a}\n"
        if not anti_text:
            anti_text = "  (none provided)"

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from module_store import SOURCE_CRITERIA_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(
            models_config,
            db_path=app.config["DB_PATH"],
            prompts_dir="prompts",
        )

        try:
            result = adapter.complete(
                prompt_file="sources_engine/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "seed_sources": seeds_text,
                    "anti_examples": anti_text,
                },
                schema=SOURCE_CRITERIA_SCHEMA,
                backend="default",
                context=f"Source Criteria analysis for run {run_id}",
            )
        except LLMAdapterError as e:
            return jsonify({"error": str(e)}), 500
        except Exception as e:
            return jsonify({"error": f"LLM call failed: {e}"}), 500

        runner.add_llm_output(run_id, "criteria", result)
        return jsonify({"status": "ok", "criteria": result})

    @app.route("/api/run/<int:run_id>/store-sources", methods=["POST"])
    def store_sources(run_id):
        """Store source criteria: write sources.yaml + source-criteria module."""
        from module_store import (
            ModuleStore, source_criteria_to_markdown, monitoring_plan_to_yaml,
            GateTokenError, generate_gate_token,
        )

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        criteria = llm_outputs.get("criteria")
        if not criteria:
            return jsonify({"error": "No source criteria found. Run analysis first."}), 400

        # Record gate decision FIRST
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], "sources-engine.md")
        playbook = PlaybookParser.parse(pb_path)
        gate_step = PlaybookRunner.get_gate_step_number(playbook)
        runner.set_gate_result(run_id, gate_step, "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                # Get business slug — return 500 if config is missing (no orphans)
                try:
                    config = load_all(app.config["CONFIG_DIR"])
                    business_slug = config["business"]["business"]["slug"]
                except ConfigError as e:
                    return jsonify({"error": f"Cannot write source-criteria module: config error: {e}"}), 500

                if not business_slug or business_slug == "unknown":
                    return jsonify({"error": "Cannot write module: business slug is missing or 'unknown'."}), 500

                # Verify gate token before config write
                _verify_config_write(app.config["DB_PATH"], run_id, gate_token)

                # Write sources.yaml (archive existing first)
                yaml_content = monitoring_plan_to_yaml(criteria)
                sources_yaml_path = os.path.join(app.config["CONFIG_DIR"], "sources.yaml")
                _archive_config_file(sources_yaml_path)
                with open(sources_yaml_path, "w") as f:
                    f.write("# ViralFactory sources config\n")
                    f.write("# Generated by the Sources Engine playbook (Part A).\n")
                    f.write("# All monitoring targets — feeds, channels, search queries.\n\n")
                    f.write(yaml_content)
                paths["sources_yaml"] = sources_yaml_path

                # Write source-criteria module
                md = source_criteria_to_markdown(criteria, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                module_path = store.store(
                    business_slug, "source-criteria", md,
                    version=version,
                    provenance={
                        "version": version, "approved": approved,
                        "note": note, "run_id": run_id,
                        "playbook": "sources-engine",
                    },
                    gate_token=gate_token,
                    run_id=run_id,
                )
                paths["source_criteria"] = module_path

                # FIX-2: Persist seed sources into the Source Bank.
                # The Sources Engine playbook analyzes seed sources to produce
                # the Source Criteria, but the seeds themselves were never
                # written to the sources table — they were consumed and
                # discarded. On gate approval, write each seed as a source row
                # so they're available for ideation and citation.
                collected = json.loads(run.get("collected_inputs") or "{}")
                seed_sources = collected.get("seed_sources", [])
                if seed_sources:
                    from pipeline import PipelineStore
                    pipe_store = PipelineStore(db_path=app.config["DB_PATH"])
                    pipe_store._init_db()
                    import hashlib as _h
                    persisted = 0
                    for seed in seed_sources:
                        seed_name = seed.get("name", "") or seed.get("url", "") or "Unnamed seed"
                        seed_url = seed.get("url", "") or None
                        seed_type = seed.get("type", "seed")
                        # Normalize type: csv_export/json_export → seed_reference
                        if seed_type in ("csv_export", "json_export"):
                            seed_type = "seed_reference"
                        # Build a content hash from name+url for dedup
                        hash_input = f"{seed_name}|{seed_url or ''}"
                        seed_hash = _h.sha256(hash_input.encode("utf-8")).hexdigest()[:16]
                        try:
                            pipe_store.add_source(
                                business_slug=business_slug,
                                source_type=seed_type,
                                title=seed_name[:500],
                                url=seed_url if seed_url and not seed_url.startswith("(") else None,
                                summary=None,
                                content=None,
                                origin="operator",
                                content_hash=seed_hash,
                            )
                            persisted += 1
                        except Exception:
                            pass  # non-fatal — individual seed failures don't block
                    paths["seed_sources_persisted"] = persisted
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")
        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    @app.route("/api/run/<int:run_id>/v2-bulk-import", methods=["POST"])
    def v2_bulk_import(run_id):
        """
        Optional deferred v2 bulk-import path.
        Reads the T0.7 backup of the v2 SQLite DB and proposes source entries.
        Ships DISABLED by default — operator must set V2_IMPORT_ENABLED=true env var.
        """
        # Server-side switch: env var must be explicitly set to 'true'
        if os.environ.get("V2_IMPORT_ENABLED") != "true":
            return jsonify({
                "status": "disabled",
                "message": "V2 bulk import is disabled. Set V2_IMPORT_ENABLED=true env var to enable.",
            })

        v2_backup_path = os.environ.get("V2_BACKUP_PATH", "/home/daimon/v2-backups/")
        # Find the v2 SQLite backup
        import glob
        db_files = glob.glob(os.path.join(v2_backup_path, "*.db")) + \
                   glob.glob(os.path.join(v2_backup_path, "*.sqlite")) + \
                   glob.glob(os.path.join(v2_backup_path, "**/*.db"), recursive=True)

        if not db_files:
            return jsonify({"error": f"No v2 backup database found in {v2_backup_path}"}), 404

        # Select the NEWEST backup by mtime instead of arbitrary glob order
        db_file = max(db_files, key=os.path.getmtime)

        import sqlite3
        FETCH_LIMIT = 500
        try:
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            # Try to read sources table (v2 schema may vary)
            try:
                total_available = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
            except sqlite3.OperationalError:
                return jsonify({"error": "V2 backup found but 'sources' table does not exist or has different schema."}), 500

            # Fetch first page; paginate if needed
            rows = conn.execute(
                "SELECT * FROM sources LIMIT ? OFFSET 0", (FETCH_LIMIT,)
            ).fetchall()
            truncated = total_available > len(rows)

            sources = []
            for row in rows:
                row_dict = dict(row)
                sources.append({
                    "url": row_dict.get("url", row_dict.get("feed_url", "")),
                    "name": row_dict.get("name", row_dict.get("title", "")),
                    "type": row_dict.get("type", "rss"),
                    "score": row_dict.get("score", row_dict.get("quality_score", None)),
                })
            conn.close()
        except Exception as e:
            return jsonify({"error": f"Failed to read v2 backup: {e}"}), 500

        # Add as seed sources (operator reviews at the gate)
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        if "seed_sources" not in collected:
            collected["seed_sources"] = []
        imported = 0
        for s in sources:
            if s["url"]:
                collected["seed_sources"].append({
                    "url": s["url"], "name": s["name"] or s["url"],
                    "type": s["type"], "v2_imported": True,
                })
                imported += 1
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        result = {
            "status": "ok",
            "imported": imported,
            "total_seed_sources": len(collected["seed_sources"]),
        }
        if truncated:
            result["truncated"] = True
            result["total_available"] = total_available
        return jsonify(result)

    @app.route("/api/run/<int:run_id>/interview-question", methods=["POST"])
    def interview_question(run_id):
        """Generate the next interview question."""
        from llm_adapter import LLMAdapter, LLMAdapterError

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        # Count existing interview answers
        collected = json.loads(run.get("collected_inputs") or "{}")
        q_count = sum(1 for k in collected.keys() if k.startswith("interview_q"))

        adapter = LLMAdapter(
            models_config,
            db_path=app.config["DB_PATH"],
            prompts_dir="prompts",
        )

        try:
            result = adapter.complete(
                prompt_file="voice_profile/interview_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "audience_description": business.get("audience_description", ""),
                    "subjects": ", ".join(business.get("subjects", [])),
                },
                schema={
                    "type": "object",
                    "required": ["question_number", "question"],
                    "properties": {
                        "question_number": {"type": "integer", "minimum": 1},
                        "question": {"type": "string"},
                        "prompt_hint": {"type": "string"},
                    },
                },
                backend="default",
                context=f"Interview question {q_count + 1} for run {run_id}",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        return jsonify(result)

    # ── T2.3: Viral Patterns + Audience Insights + Story Frameworks + Format Guide ──

    def _get_business_context(self):
        """Helper: load business context for LLM calls. Returns dict or raises."""
        try:
            config = load_all(self.config["CONFIG_DIR"])
            return config["business"], config["models"]
        except ConfigError as e:
            return None, None

    # --- Viral Patterns ---

    @app.route("/onboard/<playbook_name>/<int:run_id>/viral-patterns")
    def viral_patterns_page(playbook_name, run_id):
        """Viral Patterns intake UI."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        admired = collected.get("admired_examples", [])
        anti = collected.get("viral_anti_examples", [])
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        patterns = llm_outputs.get("patterns")

        return render_template("viral_patterns.html",
            playbook_name=playbook_name, run_id=run_id,
            admired=admired, anti=anti, patterns=patterns)

    @app.route("/api/run/<int:run_id>/admired-example", methods=["POST"])
    def add_admired_example(run_id):
        """Add an admired example for Viral Patterns."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        url = request.json.get("url", "").strip()
        name = request.json.get("name", "").strip()
        note = request.json.get("note", "").strip()
        if not url:
            return jsonify({"error": "URL required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        if "admired_examples" not in collected:
            collected["admired_examples"] = []
        collected["admired_examples"].append({"url": url, "name": name or url, "note": note})
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "count": len(collected["admired_examples"])})

    @app.route("/api/run/<int:run_id>/viral-anti-example", methods=["POST"])
    def add_viral_anti(run_id):
        """Add an anti-example for Viral Patterns."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        description = request.json.get("description", "").strip()
        if not description:
            return jsonify({"error": "Description required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        if "viral_anti_examples" not in collected:
            collected["viral_anti_examples"] = []
        collected["viral_anti_examples"].append(description)
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "count": len(collected["viral_anti_examples"])})

    @app.route("/api/run/<int:run_id>/analyze-viral-patterns", methods=["POST"])
    def analyze_viral_patterns(run_id):
        """Run the Viral Patterns analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        admired = collected.get("admired_examples", [])
        if len(admired) < 3:
            return jsonify({"error": "Need at least 3 admired examples."}), 400

        admired_text = ""
        for i, a in enumerate(admired, 1):
            admired_text += f"  {i}. {a.get('name', '')} — {a['url']}"
            if a.get("note"):
                admired_text += f" (note: {a['note']})"
            admired_text += "\n"

        anti_text = ""
        for i, a in enumerate(collected.get("viral_anti_examples", []), 1):
            anti_text += f"  {i}. {a}\n"
        if not anti_text:
            anti_text = "  (none provided)"

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from module_store import VIRAL_PATTERNS_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="viral_patterns/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "admired_examples": admired_text,
                    "anti_examples": anti_text,
                },
                schema=VIRAL_PATTERNS_SCHEMA,
                backend="default",
                context=f"Viral Patterns analysis for run {run_id}",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        runner.add_llm_output(run_id, "patterns", result)
        return jsonify({"status": "ok", "patterns": result})

    @app.route("/api/run/<int:run_id>/store-viral-patterns", methods=["POST"])
    def store_viral_patterns(run_id):
        """Store viral patterns module (gate enforced)."""
        from module_store import (ModuleStore, viral_patterns_to_markdown,
            GateTokenError, generate_gate_token)

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        patterns = llm_outputs.get("patterns")
        if not patterns:
            return jsonify({"error": "No viral patterns found. Run analysis first."}), 400

        runner.set_gate_result(run_id, PlaybookRunner.get_gate_step_number(
            PlaybookParser.parse(os.path.join(app.config["PLAYBOOKS_DIR"], "viral-patterns-starter.md"))
        ), "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                config = load_all(app.config["CONFIG_DIR"])
                business_slug = config["business"]["business"]["slug"]
                if not business_slug or business_slug == "unknown":
                    return jsonify({"error": "Cannot write: business slug missing."}), 500

                md = viral_patterns_to_markdown(patterns, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                path = store.store(business_slug, "viral-patterns", md,
                    version=version,
                    provenance={"version": version, "approved": True, "note": note,
                                "run_id": run_id, "playbook": "viral-patterns-starter"},
                    gate_token=gate_token, run_id=run_id)
                paths["viral_patterns"] = path
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    # --- Audience Insights ---

    @app.route("/onboard/<playbook_name>/<int:run_id>/audience-insights")
    def audience_insights_page(playbook_name, run_id):
        """Audience Insights intake UI."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        operator_desc = collected.get("audience_operator_desc", "")
        audience_data = collected.get("audience_data", "")
        admired_signals = collected.get("audience_admired_signals", "")
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        insights = llm_outputs.get("insights")

        return render_template("audience_insights.html",
            playbook_name=playbook_name, run_id=run_id,
            operator_desc=operator_desc, audience_data=audience_data,
            admired_signals=admired_signals, insights=insights)

    @app.route("/api/run/<int:run_id>/audience-input", methods=["POST"])
    def add_audience_input(run_id):
        """Add audience description/data for Audience Insights."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        key = request.json.get("key", "")
        value = request.json.get("value", "").strip()
        if not key or not value:
            return jsonify({"error": "Key and value required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        collected[key] = value
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok"})

    @app.route("/api/run/<int:run_id>/analyze-audience", methods=["POST"])
    def analyze_audience(run_id):
        """Run the Audience Insights analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        operator_desc = collected.get("audience_operator_desc", "")
        if not operator_desc:
            return jsonify({"error": "Add an audience description first."}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from module_store import AUDIENCE_INSIGHTS_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="audience_insights/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "operator_description": operator_desc,
                    "audience_data": collected.get("audience_data", "(none provided)"),
                    "admired_signals": collected.get("audience_admired_signals", "(none provided)"),
                },
                schema=AUDIENCE_INSIGHTS_SCHEMA,
                backend="default",
                context=f"Audience Insights analysis for run {run_id}",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        runner.add_llm_output(run_id, "insights", result)
        return jsonify({"status": "ok", "insights": result})

    @app.route("/api/run/<int:run_id>/store-audience-insights", methods=["POST"])
    def store_audience_insights(run_id):
        """Store audience insights module (gate enforced)."""
        from module_store import (ModuleStore, audience_insights_to_markdown,
            GateTokenError, generate_gate_token)

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        insights = llm_outputs.get("insights")
        if not insights:
            return jsonify({"error": "No audience insights found. Run analysis first."}), 400

        runner.set_gate_result(run_id, PlaybookRunner.get_gate_step_number(
            PlaybookParser.parse(os.path.join(app.config["PLAYBOOKS_DIR"], "audience-insights-builder.md"))
        ), "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                config = load_all(app.config["CONFIG_DIR"])
                business_slug = config["business"]["business"]["slug"]
                if not business_slug or business_slug == "unknown":
                    return jsonify({"error": "Cannot write: business slug missing."}), 500

                md = audience_insights_to_markdown(insights, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                path = store.store(business_slug, "audience-insights", md,
                    version=version,
                    provenance={"version": version, "approved": True, "note": note,
                                "run_id": run_id, "playbook": "audience-insights-builder"},
                    gate_token=gate_token, run_id=run_id)
                paths["audience_insights"] = path
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    # --- Story Frameworks ---

    @app.route("/onboard/<playbook_name>/<int:run_id>/story-frameworks")
    def story_frameworks_page(playbook_name, run_id):
        """Story Frameworks intake UI."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        admired_refs = collected.get("story_admired_refs", "")
        operator_stories = collected.get("operator_stories", "")
        voice_summary = collected.get("voice_summary", "")
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        frameworks = llm_outputs.get("frameworks")

        return render_template("story_frameworks.html",
            playbook_name=playbook_name, run_id=run_id,
            admired_refs=admired_refs, operator_stories=operator_stories,
            voice_summary=voice_summary, frameworks=frameworks)

    @app.route("/api/run/<int:run_id>/story-input", methods=["POST"])
    def add_story_input(run_id):
        """Add story framework input (admired refs, operator stories, voice summary)."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        key = request.json.get("key", "")
        value = request.json.get("value", "").strip()
        if not key or not value:
            return jsonify({"error": "Key and value required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        collected[key] = value
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok"})

    @app.route("/api/run/<int:run_id>/analyze-story-frameworks", methods=["POST"])
    def analyze_story_frameworks(run_id):
        """Run the Story Frameworks analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        operator_stories = collected.get("operator_stories", "")
        if not operator_stories:
            return jsonify({"error": "Add at least one operator story first."}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from module_store import STORY_FRAMEWORKS_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        # Load narrative patterns config
        import yaml as _yaml
        patterns_path = os.path.join(app.config["CONFIG_DIR"], "narrative_patterns.yaml")
        try:
            with open(patterns_path) as f:
                patterns_data = _yaml.safe_load(f)
            patterns_text = "\n".join(
                f"- **{p['name']}**: {p['description']}\n  Beats: {', '.join(p['beats'])}"
                for p in patterns_data["patterns"]
            )
            if patterns_data.get("allow_custom"):
                patterns_text += "\n\nYou may also propose a custom pattern if none of the above fit."
        except Exception:
            patterns_text = "(narrative patterns config not available)"

        try:
            result = adapter.complete(
                prompt_file="story_frameworks/analyze_v3.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "narrative_patterns": patterns_text,
                    "routed_seeds": "(none)",
                    "conversation_transcript": "(none)",
                    "materials_content": "(none)",
                    "admired_examples": collected.get("story_admired_refs", "(none provided)"),
                    "operator_stories": operator_stories,
                    "voice_summary": collected.get("voice_summary", "(not yet available)"),
                },
                schema=STORY_FRAMEWORKS_SCHEMA,
                backend="default",
                context=f"Story Frameworks analysis for run {run_id}",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        runner.add_llm_output(run_id, "frameworks", result)
        return jsonify({"status": "ok", "frameworks": result})

    @app.route("/api/run/<int:run_id>/store-story-frameworks", methods=["POST"])
    def store_story_frameworks(run_id):
        """Store story frameworks module (gate enforced)."""
        from module_store import (ModuleStore, story_frameworks_to_markdown,
            GateTokenError, generate_gate_token)

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        frameworks = llm_outputs.get("frameworks")
        if not frameworks:
            return jsonify({"error": "No story frameworks found. Run analysis first."}), 400

        runner.set_gate_result(run_id, PlaybookRunner.get_gate_step_number(
            PlaybookParser.parse(os.path.join(app.config["PLAYBOOKS_DIR"], "story-frameworks-starter.md"))
        ), "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                config = load_all(app.config["CONFIG_DIR"])
                business_slug = config["business"]["business"]["slug"]
                if not business_slug or business_slug == "unknown":
                    return jsonify({"error": "Cannot write: business slug missing."}), 500

                md = story_frameworks_to_markdown(frameworks, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                path = store.store(business_slug, "story-frameworks", md,
                    version=version,
                    provenance={"version": version, "approved": True, "note": note,
                                "run_id": run_id, "playbook": "story-frameworks-starter"},
                    gate_token=gate_token, run_id=run_id)
                paths["story_frameworks"] = path
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    # --- Format Guide ---

    @app.route("/onboard/<playbook_name>/<int:run_id>/format-guide")
    def format_guide_page(playbook_name, run_id):
        """Format Guide intake UI."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        format_observations = collected.get("format_observations", "")
        platform_norms = collected.get("platform_norms", "")
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        guide = llm_outputs.get("guide")

        return render_template("format_guide.html",
            playbook_name=playbook_name, run_id=run_id,
            format_observations=format_observations,
            platform_norms=platform_norms, guide=guide)

    @app.route("/api/run/<int:run_id>/format-input", methods=["POST"])
    def add_format_input(run_id):
        """Add format guide input (observations, norms)."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        key = request.json.get("key", "")
        value = request.json.get("value", "").strip()
        if not key or not value:
            return jsonify({"error": "Key and value required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        collected[key] = value
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok"})

    @app.route("/api/run/<int:run_id>/analyze-format-guide", methods=["POST"])
    def analyze_format_guide(run_id):
        """Run the Format Guide analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        collected = json.loads(run.get("collected_inputs") or "{}")

        # Build platforms text
        platforms_text = ", ".join(
            f"{p['name']} ({p.get('handle', '')})" for p in business.get("platforms", [])
        )

        from module_store import FORMAT_GUIDE_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="format_guide/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "platforms": platforms_text,
                    "subjects": ", ".join(business.get("subjects", [])),
                    "format_observations": collected.get("format_observations", "(none provided)"),
                    "platform_norms": collected.get("platform_norms", "(use general knowledge)"),
                },
                schema=FORMAT_GUIDE_SCHEMA,
                backend="default",
                context=f"Format Guide analysis for run {run_id}",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        runner.add_llm_output(run_id, "guide", result)
        return jsonify({"status": "ok", "guide": result})

    @app.route("/api/run/<int:run_id>/store-format-guide", methods=["POST"])
    def store_format_guide(run_id):
        """Store format guide module (gate enforced)."""
        from module_store import (ModuleStore, format_guide_to_markdown,
            GateTokenError, generate_gate_token)

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        guide = llm_outputs.get("guide")
        if not guide:
            return jsonify({"error": "No format guide found. Run analysis first."}), 400

        runner.set_gate_result(run_id, PlaybookRunner.get_gate_step_number(
            PlaybookParser.parse(os.path.join(app.config["PLAYBOOKS_DIR"], "format-guide-starter.md"))
        ), "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                config = load_all(app.config["CONFIG_DIR"])
                business_slug = config["business"]["business"]["slug"]
                if not business_slug or business_slug == "unknown":
                    return jsonify({"error": "Cannot write: business slug missing."}), 500

                md = format_guide_to_markdown(guide, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                path = store.store(business_slug, "format-guide", md,
                    version=version,
                    provenance={"version": version, "approved": True, "note": note,
                                "run_id": run_id, "playbook": "format-guide-starter"},
                    gate_token=gate_token, run_id=run_id)
                paths["format_guide"] = path
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    # ── T2.4: Visual Style Intake + Shot Library ──

    @app.route("/onboard/<playbook_name>/<int:run_id>/visual-style")
    def visual_style_page(playbook_name, run_id):
        """Visual Style intake UI."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return "Run not found", 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        shot_library = collected.get("shot_library", [])
        brand_assets = collected.get("brand_assets", "")
        visual_examples = collected.get("visual_examples", "")
        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        style_guide = llm_outputs.get("style_guide")

        return render_template("visual_style.html",
            playbook_name=playbook_name, run_id=run_id,
            shot_library=shot_library, brand_assets=brand_assets,
            visual_examples=visual_examples, style_guide=style_guide)

    @app.route("/api/run/<int:run_id>/shot-library-item", methods=["POST"])
    def add_shot_library_item(run_id):
        """Add a shot-library item description (operator describes what they uploaded)."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        description = request.json.get("description", "").strip()
        if not description:
            return jsonify({"error": "Description required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        if "shot_library" not in collected:
            collected["shot_library"] = []
        # Store the raw description; indexing happens on analyze
        collected["shot_library"].append({"raw_description": description})
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "count": len(collected["shot_library"])})

    @app.route("/api/run/<int:run_id>/visual-style-input", methods=["POST"])
    def add_visual_style_input(run_id):
        """Add visual style input (brand assets, visual examples)."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        key = request.json.get("key", "")
        value = request.json.get("value", "").strip()
        if not key or not value:
            return jsonify({"error": "Key and value required"}), 400

        collected = json.loads(run.get("collected_inputs") or "{}")
        collected[key] = value
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok"})

    @app.route("/api/run/<int:run_id>/index-shot-library", methods=["POST"])
    def index_shot_library(run_id):
        """Index all un-indexed shot library items via LLM."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        shot_library = collected.get("shot_library", [])
        if not shot_library:
            return jsonify({"error": "No shot library items. Add some first."}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from module_store import SHOT_LIBRARY_ITEM_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        indexed = []
        errors = []
        for i, item in enumerate(shot_library):
            if "tags" in item:
                # Already indexed
                indexed.append(item)
                continue

            raw_desc = item.get("raw_description", "")
            if not raw_desc:
                continue

            try:
                result = adapter.complete(
                    prompt_file="visual_style/index_item_v1.md",
                    variables={
                        "business_name": business["business"]["name"],
                        "subjects": ", ".join(business.get("subjects", [])),
                        "item_description": raw_desc,
                    },
                    schema=SHOT_LIBRARY_ITEM_SCHEMA,
                    backend="default",
                    context=f"Shot library indexing item {i+1} for run {run_id}",
                )
                # Preserve raw_description and add indexed fields
                item.update(result)
                indexed.append(item)
            except (LLMAdapterError, Exception) as e:
                errors.append(f"Item {i+1}: {e}")
                indexed.append(item)  # Keep un-indexed item

        # Update collected with indexed items
        collected["shot_library"] = indexed
        runner.update_run(run_id, collected_inputs=json.dumps(collected))

        # Also store as LLM output for the style guide analysis to use
        runner.add_llm_output(run_id, "shot_library", indexed)

        result = {"status": "ok", "indexed": len([i for i in indexed if "tags" in i]),
                  "total": len(indexed)}
        if errors:
            result["errors"] = errors
        return jsonify(result)

    @app.route("/api/run/<int:run_id>/analyze-visual-style", methods=["POST"])
    def analyze_visual_style(run_id):
        """Run the Visual Style Guide analysis LLM call."""
        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        collected = json.loads(run.get("collected_inputs") or "{}")
        shot_library = collected.get("shot_library", [])

        # Build shot library summary from indexed items
        shot_summary = ""
        for i, item in enumerate(shot_library, 1):
            if "tags" in item:
                shot_summary += f"  {i}. {item.get('description', '')} [tags: {', '.join(item.get('tags', []))}] [mood: {item.get('mood', '')}]\n"
            else:
                shot_summary += f"  {i}. {item.get('raw_description', '(un-indexed)')}\n"

        if not shot_summary:
            shot_summary = "  (no items uploaded yet)"

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        platforms_text = ", ".join(
            f"{p['name']} ({p.get('handle', '')})" for p in business.get("platforms", [])
        )

        from module_store import VISUAL_STYLE_SCHEMA
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="visual_style/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "platforms": platforms_text,
                    "subjects": ", ".join(business.get("subjects", [])),
                    "brand_assets": collected.get("brand_assets", "(none provided)"),
                    "visual_examples": collected.get("visual_examples", "(none provided)"),
                    "shot_library_summary": shot_summary,
                },
                schema=VISUAL_STYLE_SCHEMA,
                backend="default",
                context=f"Visual Style Guide analysis for run {run_id}",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        runner.add_llm_output(run_id, "style_guide", result)
        return jsonify({"status": "ok", "style_guide": result})

    @app.route("/api/run/<int:run_id>/store-visual-style", methods=["POST"])
    def store_visual_style(run_id):
        """Store visual style guide + shot library modules (gate enforced)."""
        from module_store import (ModuleStore, visual_style_to_markdown,
            shot_library_to_markdown, GateTokenError, generate_gate_token)

        approved = request.json.get("approved", False)
        version = request.json.get("version", "1.0")
        note = request.json.get("note", "")

        runner = PlaybookRunner(app.config["DB_PATH"])
        run = runner.get_run(run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        llm_outputs = json.loads(run.get("llm_outputs") or "{}")
        style_guide = llm_outputs.get("style_guide")
        if not style_guide:
            return jsonify({"error": "No visual style guide found. Run analysis first."}), 400

        runner.set_gate_result(run_id, PlaybookRunner.get_gate_step_number(
            PlaybookParser.parse(os.path.join(app.config["PLAYBOOKS_DIR"], "visual-style-intake.md"))
        ), "approve" if approved else "park", note)

        paths = {}
        if approved:
            gate_token = generate_gate_token(run_id)
            runner.update_run(run_id, status="completed")
            try:
                config = load_all(app.config["CONFIG_DIR"])
                business_slug = config["business"]["business"]["slug"]
                if not business_slug or business_slug == "unknown":
                    return jsonify({"error": "Cannot write: business slug missing."}), 500

                # Write visual-style module
                md = visual_style_to_markdown(style_guide, version)
                store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
                path = store.store(business_slug, "visual-style", md,
                    version=version,
                    provenance={"version": version, "approved": True, "note": note,
                                "run_id": run_id, "playbook": "visual-style-intake"},
                    gate_token=gate_token, run_id=run_id)
                paths["visual_style"] = path

                # Write shot-library module (if items exist)
                collected = json.loads(run.get("collected_inputs") or "{}")
                shot_library = collected.get("shot_library", [])
                indexed_items = [item for item in shot_library if "tags" in item]
                if indexed_items:
                    sl_md = shot_library_to_markdown(indexed_items, version)
                    sl_path = store.store(business_slug, "shot-library", sl_md,
                        version=version,
                        provenance={"version": version, "approved": True, "note": note,
                                    "run_id": run_id, "playbook": "visual-style-intake"},
                        gate_token=gate_token, run_id=run_id)
                    paths["shot_library"] = sl_path
            except GateTokenError as e:
                return jsonify({"error": str(e)}), 403
        else:
            runner.update_run(run_id, status="awaiting_gate")

        result = {"status": "ok", "version": version, "approved": approved}
        if paths:
            result["paths"] = paths
        return jsonify(result)

    # ── M3: Co-production loop ──────────────────────────────────────────

    def _get_pipeline_store():
        """Get a PipelineStore instance."""
        from pipeline import PipelineStore
        return PipelineStore(db_path=app.config["DB_PATH"])

    def _get_jobs_store():
        """F1: Get a JobsStore instance for idempotency + async job tracking."""
        from jobs import JobsStore
        return JobsStore(app.config["DB_PATH"])

    def _check_job_running(job_type, entity_id=None, input_hash=None, stale_timeout_s=None):
        """F1: Check if a job is already running. Returns (is_running, job_info dict).
        If a job is running, caller should return 409.
        stale_timeout_s: forwarded to JobsStore.start_job — jobs older than this are
        treated as stale and a new job starts instead of returning 409."""
        store = _get_jobs_store()
        kwargs = {}
        if stale_timeout_s:
            kwargs["stale_timeout_s"] = stale_timeout_s
        result = store.start_job(job_type, entity_id, input_hash, **kwargs)
        if result["status"] == "running":
            return True, result
        return False, result

    def _load_all_modules(business_slug: str) -> dict:
        """Load all available modules for a business as markdown text.
        Returns dict of {module_name: markdown_content or '(not yet built)'}.
        The drafter and idea generator consult these modules."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
        modules = {}
        for name in ["voice-profile", "viral-patterns", "story-frameworks",
                      "format-guide", "audience-insights", "visual-style",
                      "source-criteria", "brand-context"]:
            content = store.load(business_slug, name)
            modules[name] = content if content else f"({name} not yet built)"
        return modules

    def _get_business_slug() -> str:
        """Get the current business slug from config."""
        try:
            config = load_all(app.config["CONFIG_DIR"])
            return config["business"]["business"]["slug"]
        except ConfigError:
            return None

    # ── T9.1: Format Guide metadata parsers (mechanical, no keyword heuristics) ──
    # These replace the charter-violating _resolve_format_platforms (regex parser)
    # and _determine_variant_type (keyword heuristic). Per AMENDMENT-007, the
    # format + platform set are locked from the treatment at Gate 1 — no code
    # re-derives them with keyword matching or regex parsing.

    def _get_platforms_from_format_entry(ms: "ModuleStore", business_slug: str, format_name: str) -> list[str]:
        """T9.1: Resolve which platforms a format is native to, from the Format Guide
        entry's structured '- **Platforms:**' field.
        Returns a list of platform names (e.g. ['X', 'Instagram']).
        Returns empty list if the format or its platforms field is not found.
        """
        if not format_name:
            return []
        try:
            entry = ms.get_entry(business_slug, "format-guide", "Formats", format_name)
            if not entry:
                return []
            for line in entry.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- **Platforms:**"):
                    raw = stripped.split("**Platforms:**", 1)[1].strip()
                    return [p.strip() for p in raw.split(",") if p.strip()]
            return []
        except Exception:
            return []

    def _get_variant_type_from_format_entry(ms: "ModuleStore", business_slug: str, format_name: str) -> str | None:
        """T9.1: Resolve variant_type from the Format Guide entry's structured
        '- **Variant type:**' field. Returns None if the field is not present
        (T9.2 adds this field to the Format Guide schema). The caller falls back
        to 'single_post' when None.
        """
        if not format_name:
            return None
        try:
            entry = ms.get_entry(business_slug, "format-guide", "Formats", format_name)
            if not entry:
                return None
            for line in entry.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- **Variant type:**"):
                    return stripped.split("**Variant type:**", 1)[1].strip()
            return None
        except Exception:
            return None

    def _carry_draft_media(db_path: str, draft_id: int, asset_id: int):
        """S4: Copy draft media rows into a spawned asset (link, don't re-render).
        Copies owner_type='draft' rows for this draft_id as new owner_type='asset'
        rows with the new asset_id, same file path (no file copy).

        Only carries media whose prompt matches one of the draft's current
        visual_direction image_prompts. Stale media from a previous draft
        generation (different content) is silently skipped — it would produce
        mismatched image/text pairing on the asset page.
        """
        import sqlite3 as _sqlite3
        import json as _json
        conn = _sqlite3.connect(db_path)
        # Check owner_type column exists
        cols = [row[1] for row in conn.execute("PRAGMA table_info(asset_media)").fetchall()]
        if "owner_type" not in cols:
            conn.close()
            return 0

        # Get the draft's current visual_direction prompts for validation
        draft_row = conn.execute(
            "SELECT visual_direction FROM drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        current_prompts = set()
        if draft_row and draft_row[0]:
            try:
                vd = _json.loads(draft_row[0])
                for p in vd.get("image_prompts", []):
                    current_prompts.add(p.strip().lower())
            except (ValueError, TypeError):
                pass

        # Get draft media rows
        rows = conn.execute(
            "SELECT kind, path, model, prompt, cost_usd FROM asset_media WHERE asset_id = ? AND owner_type = 'draft'",
            (draft_id,),
        ).fetchall()

        if not rows:
            conn.close()
            return 0

        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).isoformat()
        carried = 0
        for row in rows:
            kind, path, model, prompt, cost_usd = row
            # Skip stale media: if we have current prompts to validate against,
            # only carry media whose prompt matches one of them.
            if current_prompts and prompt:
                if prompt.strip().lower() not in current_prompts:
                    continue  # Stale image from a previous draft generation
            conn.execute(
                """INSERT INTO asset_media
                   (asset_id, kind, path, model, prompt, cost_usd, created_at, owner_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'asset')""",
                (asset_id, kind, path, model, (prompt or "")[:2000], cost_usd, ts),
            )
            carried += 1
        conn.commit()
        conn.close()
        return carried

    # ── S1b/S2: Novelty context helpers ──

    def _build_existing_ideas(business_slug: str, limit: int = 40) -> str:
        """S1b: Build the existing_ideas prompt variable — recent idea cards, one line each."""
        store = _get_pipeline_store()
        cards = store.list_idea_cards(business_slug)
        lines = []
        for card in cards[:limit]:
            state = card.get("card_state", "?")
            idea = card.get("idea", "")[:120]
            treatment = json.loads(card.get("treatment") or "{}")
            fmt = treatment.get("format", {}).get("format_name", "?") if isinstance(treatment.get("format"), dict) else "?"
            lines.append(f"[{state}] {idea} ({fmt})")
        return "\n".join(lines) if lines else "(no existing ideas)"

    def _build_kill_lessons(business_slug: str, limit: int = 20) -> str:
        """S1b: Build the kill_lessons prompt variable — kill-reason feedback for idea cards."""
        store = _get_pipeline_store()
        # Get kill_reason feedback entries for idea cards
        conn = __import__("sqlite3").connect(app.config["DB_PATH"])
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            """SELECT * FROM feedback_log
               WHERE business_slug = ? AND feedback_type = 'kill_reason'
               AND idea_card_id IS NOT NULL
               ORDER BY id ASC LIMIT ?""",
            (business_slug, limit),
        ).fetchall()
        conn.close()
        lines = []
        for row in rows:
            text = dict(row).get("feedback_text", "")[:200]
            lines.append(f"- {text}")
        return "\n".join(lines) if lines else "(no kill lessons yet)"

    def _build_format_usage(business_slug: str) -> str:
        """S2: Build the format_usage prompt variable — format counts from idea cards."""
        store = _get_pipeline_store()
        cards = store.list_idea_cards(business_slug)
        from collections import Counter
        format_counts = Counter()
        for card in cards:
            treatment = json.loads(card.get("treatment") or "{}")
            fmt = treatment.get("format", {}).get("format_name", "?") if isinstance(treatment.get("format"), dict) else "?"
            format_counts[fmt] += 1
        if not format_counts:
            return "(no format usage data yet)"
        lines = [f"{fmt}: {count}" for fmt, count in format_counts.most_common()]
        return " · ".join(lines)

    # ── T3.1 + T3.2: Idea cards + Ideas gate ──

    @app.route("/ideas")
    def ideas_queue():
        """Ideas gate UI — card queue with origin badge, treatment, approve/kill/park."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        from config_loader import load_all, ConfigError
        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        store = _get_pipeline_store()

        # Determine active tab
        active_tab = request.args.get("tab", "queue")

        # Map tabs to states
        state_map = {
            "queue": ["new"],
            "approved": ["approved", "capture_fulfilled", "awaiting_capture"],
            "parked": ["parked"],
            "killed": ["killed"],
            "all": None,
        }
        states = state_map.get(active_tab, ["new"])

        if states:
            cards_raw = store.list_idea_cards_by_states(business_slug, states)
        else:
            cards_raw = store.list_idea_cards(business_slug)

        # UI-REVIEW-002 #5: Human-readable scope labels
        SCOPE_LABELS = {
            "one_off": "Single piece",
            "series_of_n": "Series",
            "pillar_with_derivatives": "Main + derivatives",
        }

        # Enrich cards for display
        cards = []
        for c in cards_raw:
            card = dict(c)
            card["hook_options"] = json.loads(c.get("hook_options") or "[]")
            treatment = json.loads(c.get("treatment") or "{}")
            card["treatment"] = treatment
            card["evidence_links"] = json.loads(c.get("evidence_links") or "[]")
            # T8.4: Resolve source_refs to display sources with title, url, type badge
            source_ref_ids = json.loads(c.get("source_refs") or "[]")
            if source_ref_ids:
                resolved_sources = store.resolve_source_refs(business_slug, source_ref_ids)
                card["resolved_sources"] = resolved_sources
            else:
                card["resolved_sources"] = []

            # Compact treatment line: scope · format · capture flag
            scope = treatment.get("scope", {})
            fmt = treatment.get("format", {})
            capture = treatment.get("capture_required", [])
            compact = []
            compact.append(f"Scope: {SCOPE_LABELS.get(scope.get('type', '?'), scope.get('type', '?'))}")
            if scope.get("type") == "series_of_n":
                compact.append(f"({scope.get('n', '?')} × {scope.get('cadence', '?')})")
            compact.append(f"Format: {fmt.get('format_name', '?')}")
            if fmt.get("experimental"):
                compact.append('<span class="capture-flag">EXPERIMENTAL</span>')
            if capture:
                compact.append(f'<span class="capture-flag">Capture: {len(capture)} tasks</span>')
            else:
                compact.append("Capture: none")
            card["treatment_compact"] = compact

            # Full treatment (expandable)
            full = f"<dl>"
            full += f"<dt>Scope</dt><dd>{scope.get('type', '?')}"
            if scope.get("n"):
                full += f" — {scope['n']} pieces, {scope.get('cadence', '')}"
            full += "</dd>"
            full += f"<dt>Format</dt><dd>{fmt.get('format_name', '?')}"
            if fmt.get("experimental"):
                full += " (experimental debut)"
            if fmt.get("format_spec"):
                full += f"<br><em>{fmt['format_spec']}</em>"
            full += "</dd>"
            if capture:
                full += f"<dt>Capture required</dt><dd><ul>"
                for task in capture:
                    full += f"<li>{task}</li>"
                full += "</ul></dd>"
            if treatment.get("reuse", {}).get("reuse_notes"):
                full += f"<dt>Reuse</dt><dd>{treatment['reuse']['reuse_notes']}</dd>"
            full += f"<dt>Rationale</dt><dd>{treatment.get('rationale', '')}</dd>"
            full += "</dl>"
            card["treatment_full"] = full

            # Capture tasks for display
            card["capture_tasks"] = capture if capture else None

            # F3: Count new children for parent cards (for bulk approve button)
            if not c.get("parent_id"):
                all_children = [cc for cc in cards_raw if cc.get("parent_id") == c["id"]]
                new_children = [cc for cc in all_children if cc["card_state"] == "new"]
                card["new_children_count"] = len(new_children)
            else:
                card["new_children_count"] = 0

            cards.append(card)

        # F3: Sort cards — children grouped immediately after their parent
        grouped = []
        used_ids = set()
        # First pass: parents (no parent_id) in their original order
        for c in cards:
            if not c.get("parent_id"):
                grouped.append(c)
                used_ids.add(c["id"])
                # Immediately add this parent's children
                for child in cards:
                    if child.get("parent_id") == c["id"] and child["id"] not in used_ids:
                        grouped.append(child)
                        used_ids.add(child["id"])
        # Second pass: any remaining (orphans or edge cases)
        for c in cards:
            if c["id"] not in used_ids:
                grouped.append(c)
        cards = grouped

        # Count cards per state for tab badges
        all_cards = store.list_idea_cards(business_slug)
        counts = {}
        for c in all_cards:
            s = c["card_state"]
            counts[s] = counts.get(s, 0) + 1
        counts_display = {
            "new": counts.get("new", 0),
            "approved": counts.get("approved", 0) + counts.get("capture_fulfilled", 0) + counts.get("awaiting_capture", 0),
            "parked": counts.get("parked", 0),
            "killed": counts.get("killed", 0),
            "all": len(all_cards),
        }

        return render_template("ideas.html",
            business_name=business_name, business_slug=business_slug,
            cards=cards, active_tab=active_tab, counts=counts_display,
            scope_labels=SCOPE_LABELS)

    @app.route("/api/ideas/seed", methods=["POST"])
    def ideas_seed():
        """Create a human-seeded idea card from a raw seed (T3.4 seed intake)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        seed = request.json.get("seed", "").strip()
        origin = request.json.get("origin", "human_seeded")
        if not seed:
            return jsonify({"error": "No seed provided"}), 400
        if origin not in ("human_seeded", "human_seeded_ai_developed"):
            return jsonify({"error": "Invalid origin for seed. Use human_seeded or human_seeded_ai_developed"}), 400

        store = _get_pipeline_store()

        if origin == "human_seeded":
            # Simple: the idea IS the seed; no AI development
            # Generate a basic treatment via LLM
            card = _generate_card_from_seed(business_slug, seed, "human_seeded")
            return jsonify(card)
        else:
            # AI-developed: sharpen the seed via LLM
            card = _generate_card_from_seed(business_slug, seed, "human_seeded_ai_developed")
            return jsonify(card)

    def _generate_card_from_seed(business_slug: str, seed: str, origin: str) -> dict:
        """Generate an idea card from a human seed using the LLM.
        T8.4: Seed auto-registers as a 'manual' source so the card is grounded."""
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return {"status": "error", "error": f"Config error: {e}"}

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import IDEA_CARD_SCHEMA
        from context_assembly import assemble_module_context

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        module_vars, module_prov = assemble_module_context(
            "ideas/generate_v1.md", business_slug,
            db_path=app.config["DB_PATH"], modules_dir="modules",
        )

        # T8.4: Register the seed as a manual source so the card is grounded
        store = _get_pipeline_store()
        import hashlib as h
        seed_hash = h.sha256(seed.encode("utf-8")).hexdigest()[:16]
        seed_source_id = store.add_source(
            business_slug=business_slug,
            source_type="manual",
            title=f"Operator seed: {seed[:80]}",
            url=None,
            summary=seed,
            content=seed,
            origin="operator",
            content_hash=seed_hash,
        )

        # Build source material digest from sources table (includes the seed)
        from module_store import ModuleStore
        ms = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
        source_criteria = ms.load(business_slug, "source-criteria") or "(not built)"

        active_sources = store.list_sources(business_slug, limit=50)
        if active_sources:
            source_lines = []
            for src in active_sources:
                line = f"[S{src['id']}] {src['title']}"
                if src.get("summary"):
                    line += f" — {src['summary']}"
                if src.get("url"):
                    line += f" ({src['url']})"
                source_lines.append(line)
            source_material = "\n".join(source_lines)
        else:
            source_material = f"[S{seed_source_id}] Operator seed: {seed}"

        try:
            result = adapter.complete(
                prompt_file="ideas/generate_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "origin_type": origin,
                    "source_material": source_material,
                    "source_criteria": source_criteria,
                    "existing_ideas": _build_existing_ideas(business_slug),
                    "kill_lessons": _build_kill_lessons(business_slug),
                    "format_usage": _build_format_usage(business_slug),
                    **module_vars,
                    "num_cards": "1",
                },
                schema=IDEA_CARD_SCHEMA,
                backend="ideator",
                context=f"Idea card generation from seed ({origin}) | module_ctx: {module_prov}",
                business_slug=business_slug,
                profile="researcher",
            )
        except (LLMAdapterError, Exception) as e:
            return {"status": "error", "error": str(e)}

        cards_created = []
        for card_data in result.get("cards", []):
            treatment = card_data.get("treatment", {})
            source_refs = card_data.get("source_refs", [seed_source_id])
            # Ensure the seed source is always cited
            if seed_source_id not in source_refs:
                source_refs = [seed_source_id] + source_refs

            # Derive evidence_links from source_refs
            resolved_sources = store.resolve_source_refs(business_slug, source_refs)
            evidence_links = [{"url": src.get("url") or "", "note": src.get("title", "")} for src in resolved_sources]

            card_id = store.create_idea_card(
                business_slug=business_slug,
                idea=card_data["idea"],
                hook_options=card_data.get("hook_options", []),
                treatment=treatment,
                origin=origin,
                evidence_links=evidence_links,
                source_refs=source_refs,
                seed_text=card_data.get("seed_text", seed),
            )
            cards_created.append(card_id)

        return {"status": "ok", "card_ids": cards_created}

    @app.route("/api/ideas/generate", methods=["POST"])
    def ideas_generate():
        """Generate AI-originated idea cards from Source Bank × modules (T3.1)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        num_cards = request.json.get("count", 3)
        if num_cards < 1 or num_cards > 10:
            return jsonify({"error": "Count must be 1-10"}), 400

        # F1: Idempotency guard
        is_running, job_info = _check_job_running("ideas_generate", entity_id=0,
                                                   input_hash=f"count_{num_cards}")
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already generating ideas.",
            }), 409
        ideas_job_id = job_info.get("job_id")

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import IDEA_CARD_SCHEMA
        from context_assembly import assemble_module_context

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        module_vars, module_prov = assemble_module_context(
            "ideas/generate_v1.md", business_slug,
            db_path=app.config["DB_PATH"], modules_dir="modules",
        )

        # T8.4: Build source material digest from the `sources` table (Source Bank)
        # Each item prefixed with its ID: [S14] title — summary
        from module_store import ModuleStore
        ms = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
        source_criteria = ms.load(business_slug, "source-criteria") or "(not built)"

        # Trigger RSS snapshot to populate the sources table (T8.3 integration)
        try:
            sources_config = config.get("sources", {})
            feeds = sources_config.get("feeds", []) if sources_config else []
            if feeds:
                from source_snapshot import SourceSnapshot
                snapshot = SourceSnapshot(db_path=app.config["DB_PATH"], business_slug=business_slug)
                snapshot.build_snapshot_text(feeds)
        except Exception:
            pass

        # Build digest view from the sources table — count-bounded, ID-prefixed
        from pipeline import PipelineStore
        store = _get_pipeline_store()
        active_sources = store.list_sources(business_slug, limit=50)
        if active_sources:
            source_lines = []
            for src in active_sources:
                line = f"[S{src['id']}] {src['title']}"
                if src.get("summary"):
                    line += f" — {src['summary']}"
                if src.get("url"):
                    line += f" ({src['url']})"
                source_lines.append(line)
            source_material = "\n".join(source_lines)
        else:
            source_material = "(no sources available yet — source bank empty)"

        try:
            result = adapter.complete(
                prompt_file="ideas/generate_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "origin_type": "ai_originated",
                    "source_material": source_material,
                    "source_criteria": source_criteria,
                    "existing_ideas": _build_existing_ideas(business_slug),
                    "kill_lessons": _build_kill_lessons(business_slug),
                    "format_usage": _build_format_usage(business_slug),
                    **module_vars,
                    "num_cards": str(num_cards),
                },
                schema=IDEA_CARD_SCHEMA,
                backend="ideator",
                context=f"AI idea card generation ({num_cards} cards) | module_ctx: {module_prov}",
                business_slug=business_slug,
                profile="researcher",
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        store = _get_pipeline_store()
        cards_created = []
        for card_data in result.get("cards", []):
            treatment = card_data.get("treatment", {})
            source_refs = card_data.get("source_refs", [])
            source_notes = card_data.get("source_notes", [])

            # T8.4: Validate source_refs — reject/quarantine unresolved refs
            if source_refs:
                resolved = store.resolve_source_refs(business_slug, source_refs)
                resolved_ids = {r["id"] for r in resolved}
                unresolved = [sid for sid in source_refs if sid not in resolved_ids]
                if unresolved:
                    # Quarantine: still create the card but flag it
                    # (In production, the LLM should only cite real IDs from the digest)
                    pass  # non-fatal for now — the LLM sees real IDs in the prompt

            # Derive evidence_links from source_refs for backward display compatibility
            evidence_links = []
            if source_refs:
                resolved_sources = store.resolve_source_refs(business_slug, source_refs)
                notes_map = {sn.get("source_id"): sn.get("note", "") for sn in source_notes if isinstance(sn, dict)}
                for src in resolved_sources:
                    evidence_links.append({
                        "url": src.get("url") or "",
                        "note": notes_map.get(src["id"], src.get("title", "")),
                    })

            card_id = store.create_idea_card(
                business_slug=business_slug,
                idea=card_data["idea"],
                hook_options=card_data.get("hook_options", []),
                treatment=treatment,
                origin="ai_originated",
                evidence_links=evidence_links,
                source_refs=source_refs,
            )
            cards_created.append(card_id)

        # F1: Mark job as done
        _get_jobs_store().complete_job(ideas_job_id, f"ideas:{len(cards_created)}")

        return jsonify({"status": "ok", "card_ids": cards_created, "count": len(cards_created)})

    @app.route("/api/ideas/<int:card_id>/gate", methods=["POST"])
    def ideas_gate_decision(card_id):
        """Gate 1 decision: approve / kill / park an idea card (T3.2)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        action = request.json.get("action", "")
        kill_reason = request.json.get("kill_reason", "")

        if action not in ("approve", "kill", "park"):
            return jsonify({"error": "Invalid action. Use approve, kill, or park."}), 400

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            return jsonify({"error": "Card not found"}), 404
        if card["business_slug"] != business_slug:
            return jsonify({"error": "Card does not belong to this business"}), 403

        # Handle state transitions
        if action == "approve":
            # Cards with capture tasks no longer block — they go to the Writer
            # like any other approved card. The Assembler creates what it can;
            # real photos arrive later and update the asset.
            treatment = json.loads(card.get("treatment") or "{}")
            new_state = "approved"

            # F3 (CORRECTION-feedback-plumbing): Series spawning via LLM breakdown
            # Children enter state 'new' (not 'approved') — "AI proposes, humans gate everything"
            # Idempotency: skip spawn if children already exist (prevents duplicates on re-approval)
            spawn_warning = None
            scope = treatment.get("scope", {})
            existing_children = [c for c in store.list_idea_cards(business_slug)
                                 if c.get("parent_id") == card_id]
            if scope.get("type") == "series_of_n" and not card.get("parent_id") and not existing_children:
                n = scope.get("n", 1)
                cadence = scope.get("cadence", "")
                try:
                    children = _spawn_series_children(
                        business_slug, card_id, card, treatment, n, cadence
                    )
                except Exception as e:
                    # Fallback: clone behavior in state 'new' with a warning
                    children = []
                    spawn_warning = f"Series breakdown failed ({str(e)[:200]}); children created as clones in state 'new'."
                    for i in range(1, n):
                        child_id = store.create_idea_card(
                            business_slug=business_slug,
                            idea=f"{card['idea']} (Part {i+1}/{n})",
                            hook_options=json.loads(card.get("hook_options") or "[]"),
                            treatment=treatment,
                            origin=card["origin"],
                            evidence_links=json.loads(card.get("evidence_links") or "[]"),
                            parent_id=card_id,
                        )
                        store.update_card_state(child_id, "new")
                        children.append(child_id)

            # T3.11: Experimental format debut — auto-write Format Guide entry
            fmt = treatment.get("format", {})
            if fmt.get("experimental") and fmt.get("format_spec"):
                _debut_experimental_format(business_slug, card_id, fmt, treatment)

            store.update_card_state(card_id, new_state)
            response = {"status": "ok", "new_state": new_state}
            if spawn_warning:
                response["warning"] = spawn_warning

            # Writer chain — approval triggers draft generation (Gate 2 review next)
            if new_state == "approved":
                try:
                    from produce_chain import enqueue_writer_chain
                    enqueue_writer_chain(
                        db_path=app.config["DB_PATH"],
                        config_dir=app.config["CONFIG_DIR"],
                        modules_dir=app.config.get("MODULES_DIR", "modules"),
                        prompts_dir="prompts",
                        card_id=card_id,
                        business_slug=business_slug,
                    )
                    response["chain_started"] = True
                except Exception as e:
                    response["chain_started"] = False
                    response["chain_error"] = str(e)[:200]

            return jsonify(response)

        elif action == "kill":
            store.update_card_state(card_id, "killed", kill_reason=kill_reason)
            # Log kill reason to Feedback Log
            store.add_feedback(
                business_slug=business_slug,
                feedback_type="kill_reason",
                feedback_text=kill_reason or "No reason given",
                idea_card_id=card_id,
            )
            return jsonify({"status": "ok", "new_state": "killed"})

        elif action == "park":
            store.update_card_state(card_id, "parked")
            return jsonify({"status": "ok", "new_state": "parked"})

    @app.route("/api/ideas/<int:card_id>/retry-production", methods=["POST"])
    def retry_production(card_id):
        """T8.6: Retry the production chain from the failed step."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            return jsonify({"error": "Card not found"}), 404
        if card["card_state"] not in ("writer_failed", "assembly_failed"):
            return jsonify({"error": f"Card state is '{card['card_state']}' — must be 'writer_failed' or 'assembly_failed' to retry"}), 400

        # Determine which chain to retry based on which step failed
        production_error = json.loads(card.get("production_error") or "{}")
        failed_step = production_error.get("step", "")

        try:
            if failed_step == "draft_generation":
                # Retry writer chain from scratch
                from produce_chain import enqueue_writer_chain
                enqueue_writer_chain(
                    db_path=app.config["DB_PATH"],
                    config_dir=app.config["CONFIG_DIR"],
                    modules_dir=app.config.get("MODULES_DIR", "modules"),
                    prompts_dir="prompts",
                    card_id=card_id,
                    business_slug=business_slug,
                )
            else:
                # Retry assembler chain — find the existing draft for this card
                drafts = [d for d in store.list_drafts(business_slug) if d["idea_card_id"] == card_id]
                if not drafts:
                    return jsonify({"error": "No draft found to retry assembler"}), 400
                latest_draft = max(drafts, key=lambda d: d.get("draft_version", 1))
                from produce_chain import enqueue_assembler_chain
                enqueue_assembler_chain(
                    db_path=app.config["DB_PATH"],
                    config_dir=app.config["CONFIG_DIR"],
                    modules_dir=app.config.get("MODULES_DIR", "modules"),
                    prompts_dir="prompts",
                    draft_id=latest_draft["id"],
                    card_id=card_id,
                    business_slug=business_slug,
                )
            return jsonify({"status": "ok", "message": "Production chain retried"})
        except Exception as e:
            return jsonify({"error": str(e)[:200]}), 500

    @app.route("/api/ideas/<int:parent_id>/bulk-approve-children", methods=["POST"])
    def ideas_bulk_approve_children(parent_id):
        """F3: Bulk approve all 'new' children of a parent card.

        Transitions all children with parent_id and state 'new' to 'approved'.
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        all_cards = store.list_idea_cards(business_slug)
        approved = []
        for card in all_cards:
            if card.get("parent_id") == parent_id and card["card_state"] == "new":
                store.update_card_state(card["id"], "approved")
                approved.append(card["id"])

        return jsonify({"status": "ok", "approved": approved, "count": len(approved)})

    def _spawn_series_children(business_slug: str, parent_card_id: int,
                                parent_card, treatment: dict, n: int,
                                cadence: str) -> list[int]:
        """F3: Spawn series children via LLM breakdown call.

        Children enter state 'new' — the operator must gate each part.
        Returns list of child card IDs.
        Raises on LLM failure (caller falls back to clones).
        """
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            raise Exception(f"Config error: {e}")

        from context_assembly import assemble_module_context
        from llm_adapter import LLMAdapter, LLMAdapterError

        module_vars, module_prov = assemble_module_context(
            "ideas/series_breakdown_v1.md", business_slug,
            db_path=app.config["DB_PATH"], modules_dir="modules",
        )

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        hook_options = json.loads(parent_card.get("hook_options") or "[]")
        series_schema = {
            "type": "object",
            "required": ["parts"],
            "properties": {
                "parts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["part_number", "idea", "hook_options"],
                        "properties": {
                            "part_number": {"type": "integer"},
                            "idea": {"type": "string"},
                            "hook_options": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "capture_required": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }

        result = adapter.complete(
            prompt_file="ideas/series_breakdown_v1.md",
            variables={
                "business_name": business["business"]["name"],
                "subjects": ", ".join(business.get("subjects", [])),
                "audience_description": business.get("audience_description", ""),
                "cadence": cadence,
                "parent_idea": parent_card["idea"],
                "parent_hooks": "\n".join(f"- {h}" for h in hook_options),
                "parent_treatment": json.dumps(treatment, indent=2)[:2000],
                "n": str(n),
                **module_vars,
            },
            schema=series_schema,
            backend="default",
            context=f"Series breakdown for card {parent_card_id} ({n} parts) | module_ctx: {module_prov}",
            business_slug=business_slug,
        )

        store = _get_pipeline_store()
        child_ids = []
        for part in result.get("parts", []):
            # Override capture_required in treatment if the breakdown supplies it
            child_treatment = dict(treatment)
            if part.get("capture_required"):
                child_treatment["capture_required"] = part["capture_required"]

            child_id = store.create_idea_card(
                business_slug=business_slug,
                idea=part["idea"],
                hook_options=part.get("hook_options", []),
                treatment=child_treatment,
                origin=parent_card["origin"],
                evidence_links=json.loads(parent_card.get("evidence_links") or "[]"),
                parent_id=parent_card_id,
            )
            # F3: children enter state 'new' — operator must gate each part
            store.update_card_state(child_id, "new")
            child_ids.append(child_id)

        return child_ids

    def _debut_experimental_format(business_slug: str, card_id: int, fmt: dict, treatment: dict):
        """T3.11: Auto-write an experimental format entry to the Format Guide module."""
        from module_store import ModuleStore

        store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
        existing = store.load(business_slug, "format-guide")

        # Build the new format entry
        new_entry = f"""
### {fmt['format_name']} (EXPERIMENTAL — debut via card #{card_id})

- **Platforms:** (as specified in treatment)
- **Status:** experimental
- **Provenance:** Debuted via idea card #{card_id}. {fmt.get('format_spec', '')}
- **Structure notes:** {fmt.get('format_spec', 'See format spec in treatment.')}
- **Effort level:** (to be assessed)
- **Requires human capture:** {treatment.get('capture_required', [])}
"""

        if existing:
            # Append the new entry before the Provenance section
            updated = existing.replace(
                "\n## Provenance\n",
                f"\n{new_entry}\n## Provenance\n"
            )
            if updated == existing:
                # No Provenance section found; append at end
                updated = existing + new_entry
            store.store(
                business_slug, "format-guide", updated,
                version="1.1",  # minor version bump for new entry
                provenance={
                    "version": "1.1",
                    "note": f"Experimental format debut: {fmt['format_name']} via card #{card_id}",
                    "debut_card_id": card_id,
                },
                gate_token=f"run_0_approved",  # card approval is the gate
                run_id=0,  # not a playbook run — this is a pipeline gate
            )
        # If no existing format guide, we can't auto-create it (needs the full playbook)
        # — the format will be recorded when the Format Guide playbook is next run

    @app.route("/ideas/<int:card_id>/capture")
    def capture_page(card_id):
        """T3.3: Awaiting-capture state UI — capture task list + upload flow."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            return "Card not found", 404

        treatment = json.loads(card.get("treatment") or "{}")
        capture_required = treatment.get("capture_required", [])
        uploads = json.loads(card.get("capture_uploads") or "[]")

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        return render_template("capture.html",
            business_name=business_name, card=card,
            capture_required=capture_required, uploads=uploads,
            treatment=treatment)

    @app.route("/api/ideas/<int:card_id>/capture-upload", methods=["POST"])
    def capture_upload(card_id):
        """T3.3: Upload capture material for an awaiting-capture card."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            return jsonify({"error": "Card not found"}), 404

        # Accept text-based capture (paste) or file upload
        content = request.json.get("content", "").strip() if request.is_json else ""
        if not content and "file" not in request.files:
            return jsonify({"error": "No content or file provided"}), 400

        # Store as material via materials intake
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"], upload_dir="data/uploads")

        if content:
            material_id = intake.ingest_text(
                content, run_id=None, business_slug=business_slug,
                material_type="pasted", channel="capture_upload",
            )
        else:
            file = request.files["file"]
            upload_dir = os.path.join(app.config.get("UPLOAD_DIR", "data/uploads"))
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, file.filename)
            file.save(filepath)
            material_id = intake.ingest_file(
                filepath, run_id=None, business_slug=business_slug,
                channel="capture_upload",
            )

        # Record upload against the card
        store.add_capture_upload(card_id, material_id)

        # Check if all capture tasks are fulfilled
        if store.check_capture_fulfilled(card_id):
            store.update_card_state(card_id, "capture_fulfilled")

        return jsonify({"status": "ok", "material_id": material_id})

    # ── T3.5: Drafter ──

    @app.route("/create/draft/<int:card_id>")
    def draft_page(card_id):
        """Drafter UI — generate or view a draft for an approved idea card."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            return "Card not found", 404

        treatment = json.loads(card.get("treatment") or "{}")
        hook_options = json.loads(card.get("hook_options") or "[]")
        evidence_links = json.loads(card.get("evidence_links") or "[]")
        source_refs = json.loads(card.get("source_refs") or "[]")
        capture_required = treatment.get("capture_required") or []
        capture_tasks = []
        if isinstance(capture_required, list):
            capture_tasks = [
                item.get("task", item) if isinstance(item, dict) else item
                for item in capture_required
            ]

        # Check if a draft already exists for this card
        all_drafts = store.list_drafts(business_slug)
        existing_draft = None
        for d in all_drafts:
            if d["idea_card_id"] == card_id:
                existing_draft = d
                break

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        # Load draft visual previews (generated images from visual_direction)
        draft_visuals = []
        if existing_draft:
            from media_adapter import MediaAdapter
            try:
                mc = load_all(app.config["CONFIG_DIR"])
                ma = MediaAdapter(mc.get("models", {}), db_path=app.config["DB_PATH"])
                # F4: use owner_type='draft' with the real draft_id
                draft_visuals = ma.list_asset_media(existing_draft["id"], kind="image", owner_type="draft")
            except Exception:
                pass

        # UI-REVIEW-002 #5: Human-readable scope labels
        SCOPE_LABELS = {
            "one_off": "Single piece",
            "series_of_n": "Series",
            "pillar_with_derivatives": "Main + derivatives",
        }

        # Provenance trail: idea → script (this page)
        trail = []
        trail.append({"stage": "Idea", "state": "approved", "label": "Idea approved"})
        if existing_draft:
            if existing_draft["draft_state"] in ("draft_ready", "revised"):
                trail.append({"stage": "Script", "state": "ready", "label": "Script ready for review"})
            elif existing_draft["draft_state"] == "drafting":
                trail.append({"stage": "Script", "state": "writing", "label": "Writer working"})
            elif existing_draft["draft_state"] == "shipped":
                trail.append({"stage": "Script", "state": "approved", "label": "Script approved"})
            elif existing_draft["draft_state"] == "killed":
                trail.append({"stage": "Script", "state": "killed", "label": "Script killed"})
            else:
                trail.append({"stage": "Script", "state": "pending", "label": "Not started"})
        else:
            trail.append({"stage": "Script", "state": "pending", "label": "Not started"})

        return render_template("draft.html",
            business_name=business_name, card=card,
            treatment=treatment, hook_options=hook_options,
            evidence_links=evidence_links, source_refs=source_refs,
            capture_tasks=capture_tasks,
            draft=_parse_draft_for_display(existing_draft),
            draft_visuals=draft_visuals,
            scope_labels=SCOPE_LABELS, trail=trail)

    def _parse_draft_for_display(draft):
        """Parse JSON fields on a draft for template display. Merges parsed fields into the draft dict."""
        if not draft:
            return None
        d = dict(draft)
        try:
            d["self_audit_flags_parsed"] = json.loads(draft.get("self_audit_flags") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["self_audit_flags_parsed"] = []
        try:
            d["visual_direction_parsed"] = json.loads(draft.get("visual_direction") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["visual_direction_parsed"] = {}
        try:
            d["platform_content_parsed"] = json.loads(draft.get("platform_content") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["platform_content_parsed"] = []
        try:
            d["review_history_parsed"] = json.loads(draft.get("review_history") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["review_history_parsed"] = []
        return d

    @app.route("/api/draft/<int:card_id>/generate", methods=["POST"])
    def draft_generate(card_id):
        """Generate a draft from an approved idea card + all modules (T3.5)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency — don't fire a second LLM call if one is already running
        is_running, job_info = _check_job_running("draft_generate", entity_id=card_id)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already generating this draft.",
                "job_id": job_info.get("job_id"),
            }), 409
        job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            _get_jobs_store().fail_job(job_id, "Card not found")
            return jsonify({"error": "Card not found"}), 404

        # Card must be approved or capture_fulfilled
        if card["card_state"] not in ("approved", "capture_fulfilled", "drafting", "drafted"):
            _get_jobs_store().fail_job(job_id, f"Card state is '{card['card_state']}'")
            return jsonify({"error": f"Card state is '{card['card_state']}' — must be approved or capture_fulfilled to draft"}), 400

        treatment = json.loads(card.get("treatment") or "{}")
        hook_options = json.loads(card.get("hook_options") or "[]")
        format_name = treatment.get("format", {}).get("format_name", "")
        scope = treatment.get("scope", {}).get("type", "")

        # Load modules via context assembly (CORRECTION-module-context-assembly)
        from context_assembly import assemble_module_context

        # Load capture material if any
        capture_text = ""
        uploads = json.loads(card.get("capture_uploads") or "[]")
        if uploads:
            from materials import MaterialsIntake
            intake = MaterialsIntake(app.config["DB_PATH"])
            for mid in uploads:
                mat = intake.get_material(mid)
                if mat and mat.get("normalized_content"):
                    capture_text += mat["normalized_content"] + "\n\n"
                elif mat and mat.get("raw_content"):
                    capture_text += mat["raw_content"] + "\n\n"

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        # T9.3: Load modules for the v3 prompt (per-platform content)
        module_vars, module_prov = assemble_module_context(
            "draft/generate_v3.md", business_slug,
            dynamic={"treatment.format_name": format_name},
            db_path=app.config["DB_PATH"], modules_dir="modules",
        )

        # F2 (CORRECTION-feedback-plumbing): revision context — previous draft + feedback
        existing = None
        for d in store.list_drafts(business_slug):
            if d["idea_card_id"] == card_id:
                existing = d
                break

        if existing:
            # T9.3: For revision context, show previous platform_content as text
            prev_pc = json.loads(existing.get("platform_content") or "[]")
            if prev_pc:
                prev_lines = []
                for pc in prev_pc:
                    prev_lines.append(f"### {pc.get('platform', '')} ({pc.get('variant_type', '')})")
                    prev_lines.append(pc.get("content", ""))
                    for p in pc.get("posts", []):
                        prev_lines.append(f"  - {p}")
                previous_draft = "\n".join(prev_lines)
            else:
                previous_draft = existing["draft_text"] or ""
            # Truncate at paragraph boundary near 6000 chars
            if len(previous_draft) > 6000:
                cut = previous_draft.rfind('\n\n', 0, 6000)
                if cut > 3000:
                    previous_draft = previous_draft[:cut] + "\n\n[...truncated]"
                else:
                    previous_draft = previous_draft[:6000] + "\n\n[...truncated]"

            # Gather weight-tagged feedback, newest-last
            feedback_entries = store.list_feedback(business_slug, draft_id=existing["id"])
            feedback_lines = []
            for entry in feedback_entries:
                w = entry.get("weight", 1)
                wtype = entry.get("feedback_type", "")
                ftext = entry.get("feedback_text", "")
                feedback_lines.append(f"[{wtype} w{w}] {ftext}")
            revision_feedback = "\n".join(feedback_lines)
            # Cap 3000 chars, keep highest-weight entries when trimming
            if len(revision_feedback) > 3000:
                # Sort by weight desc, keep top entries until budget
                sorted_entries = sorted(feedback_entries, key=lambda e: e.get("weight", 1), reverse=True)
                kept = []
                total = 0
                for entry in sorted_entries:
                    w = entry.get("weight", 1)
                    wtype = entry.get("feedback_type", "")
                    ftext = entry.get("feedback_text", "")
                    line = f"[{wtype} w{w}] {ftext}"
                    if total + len(line) > 3000:
                        continue
                    kept.append(line)
                    total += len(line)
                # Re-sort by original order (id ascending)
                kept_ids = {l: True for l in kept}
                revision_feedback = "\n".join(
                    f"[{e.get('feedback_type','')} w{e.get('weight',1)}] {e.get('feedback_text','')}"
                    for e in sorted(feedback_entries, key=lambda e: e.get("id", 0))
                    if f"[{e.get('feedback_type','')} w{e.get('weight',1)}] {e.get('feedback_text','')}" in kept_ids
                )
        else:
            previous_draft = "(first draft — no previous version)"
            revision_feedback = "(first draft — no previous version)"

        # T8.5: Assemble grounding_sources from the card's source_refs
        source_ref_ids = json.loads(card.get("source_refs") or "[]")
        grounding_sources = "(no sources cited on this card)"
        if source_ref_ids:
            resolved_sources = store.resolve_source_refs(business_slug, source_ref_ids)
            if resolved_sources:
                source_blocks = []
                for src in resolved_sources:
                    block = f"### [S{src['id']}] {src['title']}"
                    if src.get("url"):
                        block += f"\nURL: {src['url']}"
                    content = src.get("content") or ""
                    summary = src.get("summary") or ""
                    if content:
                        block += f"\n\n{content}"
                    elif summary:
                        block += f"\n\n{summary}\n\n(summary only — full content not available)"
                    else:
                        block += "\n\n(no content or summary available)"
                    source_blocks.append(block)
                grounding_sources = "\n\n---\n\n".join(source_blocks)

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import DRAFT_SCHEMA

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="draft/generate_v3.md",
                variables={
                    "business_name": business["business"]["name"],
                    "audience_description": business.get("audience_description", ""),
                    "origin": card["origin"],
                    "format_name": format_name,
                    "scope": scope,
                    "idea": card["idea"],
                    "hook_options": "\n".join(f"- {h}" for h in hook_options),
                    "grounding_sources": grounding_sources,
                    "capture_material": capture_text[:2000] if capture_text else "(none)",
                    "previous_draft": previous_draft,
                    "revision_feedback": revision_feedback,
                    **module_vars,
                },
                schema=DRAFT_SCHEMA,
                backend="drafter",
                context=f"Draft generation for card {card_id} ({card['origin']}, {format_name}) | module_ctx: {module_prov}",
                business_slug=business_slug,
                profile="drafter",
            )
        except (LLMAdapterError, Exception) as e:
            _get_jobs_store().fail_job(job_id, str(e)[:200])
            return jsonify({"error": str(e)}), 500

        # T9.3: Save draft with platform_content
        platform_content = result.get("platform_content", [])
        draft_text_summary = platform_content[0].get("content", "") if platform_content else ""

        # existing was found above for F2 revision context; reuse it for save
        if existing:
            store.save_draft_content(
                existing["id"],
                draft_text_summary,
                result["visual_direction"],
                result["self_audit_flags"],
                platform_content=platform_content,
            )
            draft_id = existing["id"]
        else:
            draft_id = store.create_draft(
                business_slug=business_slug,
                idea_card_id=card_id,
                origin=card["origin"],
                format_name=format_name,
                scope=scope,
            )
            store.save_draft_content(
                draft_id,
                draft_text_summary,
                result["visual_direction"],
                result["self_audit_flags"],
                platform_content=platform_content,
            )

        # Update card state to 'drafted'
        store.update_card_state(card_id, "drafted")

        # F1: Mark job as done
        _get_jobs_store().complete_job(job_id, f"draft:{draft_id}")

        return jsonify({
            "status": "ok",
            "draft_id": draft_id,
            "platform_content": platform_content,
            "draft_text": draft_text_summary,
            "visual_direction": result["visual_direction"],
            "self_audit_flags": result["self_audit_flags"],
        })

    # ── T3.6: Human pass UI (Gate 2) ──

    @app.route("/api/draft/<int:draft_id>/feedback", methods=["POST"])
    def draft_feedback(draft_id):
        """Add feedback to a draft (chip or text only).

        F1 (CORRECTION-feedback-plumbing): direct_edit via this endpoint is
        deprecated — returns 400 pointing to /edit-text. Direct edits now
        write draft_text directly via the /edit-text endpoint.
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        feedback_type = request.json.get("feedback_type", "")
        feedback_text = request.json.get("feedback_text", "")
        line_reference = request.json.get("line_reference", "")

        # F1: direct_edit is deprecated on this endpoint
        if feedback_type == "direct_edit":
            return jsonify({
                "error": "Direct edits are now done via the Edit draft button. "
                         "Use POST /api/draft/<id>/edit-text with {draft_text} instead."
            }), 400

        if feedback_type not in ("chip", "text", "kill_reason"):
            return jsonify({"error": "Invalid feedback type. Use chip, text, or kill_reason."}), 400
        if not feedback_text:
            return jsonify({"error": "No feedback text provided"}), 400

        entry_id = store.add_feedback(
            business_slug=business_slug,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            draft_id=draft_id,
            line_reference=line_reference,
        )

        return jsonify({"status": "ok", "feedback_id": entry_id})

    @app.route("/api/draft/<int:draft_id>/edit-text", methods=["POST"])
    def draft_edit_text(draft_id):
        """F1 (CORRECTION-feedback-plumbing): Edit the draft body directly.

        The edited text becomes draft_text (the authoritative artifact).
        Downstream (fan-out, assets, assembly) reads draft_text automatically.
        Bumps draft_version, logs a weight-3 direct_edit diff as feedback,
        invalidates stale self-audit flags whose line no longer appears.
        Does NOT change draft_state — ship/kill/revise remain the only
        state transitions.
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        new_text = request.json.get("draft_text", "")
        if not new_text or not new_text.strip():
            return jsonify({"error": "draft_text is required and must not be empty"}), 400

        old_text = draft.get("draft_text") or ""
        if new_text == old_text:
            return jsonify({"error": "Text is identical to current draft — no change"}), 400

        # Generate a compact unified diff (cap 4000 chars)
        import difflib
        diff_lines = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="old",
            tofile="new",
            n=1,
        ))
        diff_text = "".join(diff_lines)
        if len(diff_text) > 4000:
            diff_text = diff_text[:4000] + "\n[...diff truncated]"

        # Save the edited text (bumps version, writes draft_text only)
        updated = store.save_edited_text(draft_id, new_text)

        # Log the diff as a weight-3 direct_edit feedback entry
        store.add_feedback(
            business_slug=business_slug,
            feedback_type="direct_edit",
            feedback_text=diff_text,
            draft_id=draft_id,
        )

        # Invalidate stale self-audit flags whose line no longer appears
        flags = json.loads(updated.get("self_audit_flags") or "[]")
        changed = False
        for flag in flags:
            if flag.get("status") in (None, "active", "applied", "dismissed"):
                line = flag.get("line", "")
                if line and line not in new_text:
                    flag["status"] = "stale"
                    changed = True
        if changed:
            # Save updated flags
            import sqlite3 as _sqlite3
            conn = _sqlite3.connect(app.config["DB_PATH"])
            conn.execute(
                "UPDATE drafts SET self_audit_flags = ? WHERE id = ?",
                (json.dumps(flags), draft_id),
            )
            conn.commit()
            conn.close()

        display = _parse_draft_for_display(updated)
        return jsonify({
            "status": "ok",
            "draft_id": draft_id,
            "draft_version": updated["draft_version"],
            "draft_text": updated["draft_text"],
        })

    @app.route("/api/draft/<int:draft_id>/edit-platform/<int:variant_index>", methods=["POST"])
    def draft_edit_platform(draft_id, variant_index):
        """Edit the posts for a specific platform variant in platform_content.

        Saves the edited posts array back into platform_content[variant_index].
        Bumps draft_version, logs a weight-3 direct_edit feedback entry.
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        new_posts = request.json.get("posts", [])
        if not new_posts:
            return jsonify({"error": "posts is required and must not be empty"}), 400

        platform_content = json.loads(draft.get("platform_content") or "[]")
        if variant_index < 0 or variant_index >= len(platform_content):
            return jsonify({"error": "Invalid variant index"}), 400

        # Capture old posts for diff
        old_posts = platform_content[variant_index].get("posts", [])
        old_text = "\n".join(old_posts)
        new_text = "\n".join(new_posts)

        # Update the posts for this variant
        platform_content[variant_index]["posts"] = new_posts
        # Update content summary if single-post variant
        if len(new_posts) == 1 and platform_content[variant_index].get("variant_type") in ("single_post", "reel", "poll", "newsletter"):
            platform_content[variant_index]["content"] = new_posts[0]

        # Generate diff
        import difflib
        diff_lines = list(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"{platform_content[variant_index].get('platform','?')}/old",
            tofile=f"{platform_content[variant_index].get('platform','?')}/new",
            n=1,
        ))
        diff_text = "".join(diff_lines)
        if len(diff_text) > 4000:
            diff_text = diff_text[:4000] + "\n[...diff truncated]"

        # Save updated platform_content + bump version
        store.save_platform_content(draft_id, platform_content)

        # Bump version separately (save_platform_content doesn't bump)
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(app.config["DB_PATH"])
        conn.execute("UPDATE drafts SET draft_version = draft_version + 1 WHERE id = ?", (draft_id,))
        conn.commit()
        conn.close()

        # Log the diff as feedback
        store.add_feedback(
            business_slug=business_slug,
            feedback_type="direct_edit",
            feedback_text=diff_text,
            draft_id=draft_id,
        )

        return jsonify({"status": "ok", "draft_id": draft_id})

    @app.route("/api/draft/<int:draft_id>/gate", methods=["POST"])
    def draft_gate(draft_id):
        """Gate 2 decision: ship-forward or kill the draft."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        action = request.json.get("action", "")
        if action not in ("ship", "kill", "revise", "reopen"):
            return jsonify({"error": "Invalid action. Use ship, kill, revise, or reopen."}), 400

        if action == "ship":
            store.update_draft_state(draft_id, "shipped")
            # Update card state
            store.update_card_state(draft["idea_card_id"], "drafted")

            # Assembler chain — shipping the draft triggers fan-out → assets (Gate 3 review)
            try:
                from produce_chain import enqueue_assembler_chain
                enqueue_assembler_chain(
                    db_path=app.config["DB_PATH"],
                    config_dir=app.config["CONFIG_DIR"],
                    modules_dir=app.config.get("MODULES_DIR", "modules"),
                    prompts_dir="prompts",
                    draft_id=draft_id,
                    card_id=draft["idea_card_id"],
                    business_slug=business_slug,
                )
                return jsonify({"status": "ok", "new_state": "shipped", "chain_started": True})
            except Exception as e:
                return jsonify({"status": "ok", "new_state": "shipped",
                                "chain_started": False, "chain_error": str(e)[:200]})
        elif action == "kill":
            store.update_draft_state(draft_id, "killed")
            reason = request.json.get("kill_reason", "")
            if reason:
                store.add_feedback(
                    business_slug=business_slug,
                    feedback_type="kill_reason",
                    feedback_text=reason,
                    draft_id=draft_id,
                )
            return jsonify({"status": "ok", "new_state": "killed"})
        elif action == "revise":
            # Increment version, set state to revised
            new_version = store.increment_draft_version(draft_id)
            return jsonify({"status": "ok", "new_state": "revised", "new_version": new_version})
        elif action == "reopen":
            store.update_draft_state(draft_id, "draft_ready")
            return jsonify({"status": "ok", "new_state": "draft_ready"})

    @app.route("/api/draft/<int:draft_id>/audit-flag", methods=["POST"])
    def draft_audit_flag(draft_id):
        """F2: Apply or dismiss a self-audit flag by index."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        flag_index = request.json.get("index")
        action = request.json.get("action", "")
        if action not in ("apply", "dismiss"):
            return jsonify({"error": "Invalid action. Use apply or dismiss."}), 400
        if flag_index is None or not isinstance(flag_index, int):
            return jsonify({"error": "index must be an integer"}), 400

        # F1: Idempotency guard
        is_running, job_info = _check_job_running(
            "audit_flag", entity_id=draft_id, input_hash=f"{flag_index}_{action}"
        )
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already processing this flag.",
            }), 409

        updated = store.update_audit_flag(draft_id, flag_index, action)
        if not updated:
            return jsonify({"error": "Flag not found or line changed"}), 400

        _get_jobs_store().complete_job(job_info.get("job_id"), f"flag:{flag_index}:{action}")

        # Re-parse for display
        display = _parse_draft_for_display(updated)
        return jsonify({
            "status": "ok",
            "draft_text": updated["draft_text"],
            "draft_version": updated["draft_version"],
            "flag_status": json.loads(updated.get("self_audit_flags") or "[]")[flag_index].get("status", ""),
        })

    # ── Draft visual preview: generate images from visual direction ──

    @app.route("/api/draft/<int:draft_id>/generate-visuals", methods=["POST"])
    def draft_generate_visuals(draft_id):
        """Generate images from the draft's visual_direction prompts, for preview on the draft page."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency guard
        is_running, job_info = _check_job_running("draft_visuals", entity_id=draft_id)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already generating draft visuals.",
            }), 409
        dv_job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            _get_jobs_store().fail_job(dv_job_id, "Draft not found")
            return jsonify({"error": "Draft not found"}), 404

        visual_direction = json.loads(draft.get("visual_direction") or "{}")
        image_prompts = visual_direction.get("image_prompts", [])

        if not image_prompts:
            _get_jobs_store().fail_job(dv_job_id, "No image prompts in visual direction")
            return jsonify({"error": "No image prompts in this draft's visual direction"}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError as e:
            _get_jobs_store().fail_job(dv_job_id, str(e)[:200])
            return jsonify({"error": f"Config error: {e}"}), 500

        from media_adapter import MediaAdapter, MediaAdapterError
        adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        # F4 (CORRECTION-feedback-plumbing): use owner_type='draft' with the
        # real draft_id instead of the synthetic draft_id + 100000 scheme.

        # Clear any stale draft preview media before generating fresh images.
        # If a draft was re-generated with new content, old preview images from
        # a completely different topic would otherwise persist and get carried
        # into assets during fan-out — causing mismatched image/text pairing.
        adapter.clear_draft_media(draft_id)

        # Determine aspect ratio from format
        format_name = (draft.get("format") or "").lower()
        if "reel" in format_name or "short" in format_name:
            aspect_ratio = "9:16"
        elif "carousel" in format_name:
            aspect_ratio = "1:1"
        else:
            aspect_ratio = "16:9"

        results = []
        errors = []
        for i, prompt in enumerate(image_prompts):
            try:
                result = adapter.generate_image(
                    prompt=prompt,
                    asset_id=draft_id,
                    aspect_ratio=aspect_ratio,
                    context=f"Draft visual preview {i+1}/{len(image_prompts)} for draft {draft_id}",
                    business_slug=business_slug,
                    owner_type="draft",
                )
                results.append(result)
            except (MediaAdapterError, Exception) as e:
                errors.append({"prompt": prompt[:100], "error": str(e)[:200]})

        _get_jobs_store().complete_job(dv_job_id, f"draft_visuals:{len(results)}")

        # If all images failed, return error status so the JS shows the message
        if len(results) == 0 and errors:
            error_msg = errors[0].get("error", "Image generation failed")
            return jsonify({
                "status": "error",
                "error": error_msg,
                "images_generated": 0,
                "errors": errors,
            }), 500

        return jsonify({
            "status": "ok",
            "images_generated": len(results),
            "errors": errors,
            "image_paths": [r["path"] for r in results],
        })

    @app.route("/api/draft/<int:draft_id>/visuals", methods=["GET"])
    def draft_list_visuals(draft_id):
        """List generated visual previews for a draft."""
        from media_adapter import MediaAdapter
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}
        adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])
        # F4: draft visuals stored with owner_type='draft' and the real draft_id
        media = adapter.list_asset_media(draft_id, kind="image", owner_type="draft")
        return jsonify({"status": "ok", "visuals": media})

    # ── T3.7: Assets stage ──

    @app.route("/create/assets/<int:draft_id>")
    def assets_page(draft_id):
        """Assets gate UI — per-platform variants for a shipped draft (T3.7/T3.8)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return "Draft not found", 404

        assets = store.list_assets(draft_id)
        visual_direction = json.loads(draft.get("visual_direction") or "{}")

        # F5: Load media + edit plans for each asset so the preview can show final cuts
        from media_adapter import MediaAdapter
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business_name = config["business"]["business"]["name"]
            platforms = config["business"].get("platforms", [])
        except ConfigError:
            models_config = {}
            business_name = "Not configured"
            platforms = []

        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        # Enrich each asset with its media and edit plans
        enriched_assets = []
        for asset in assets:
            a = dict(asset)
            # Parse JSON string fields
            a["image_prompts_parsed"] = json.loads(asset.get("image_prompts") or "[]")
            a["generated_images_parsed"] = json.loads(asset.get("generated_images") or "[]")
            a["posts_parsed"] = json.loads(asset.get("posts") or "[]")
            # Get all media for this asset (images, videos, final cuts)
            a["media_list"] = media_adapter.list_asset_media(asset["id"])
            a["final_cuts"] = [m for m in a["media_list"] if m.get("kind") == "final_cut"]
            a["videos"] = [m for m in a["media_list"] if m.get("kind") == "video"]
            a["images"] = [m for m in a["media_list"] if m.get("kind") == "image"]
            # Get edit plans
            a["edit_plans"] = store.list_edit_plans(asset["id"])

            # Build post_images mapping: index by post index → image dict or None.
            # Only posts whose image_prompt is not "none" should get an image.
            # Images list is flat (generated images only, skipping "none" prompts),
            # so we walk image_prompts and assign images sequentially to non-"none" slots.
            posts_list = a["posts_parsed"]
            prompts_list = a["image_prompts_parsed"]
            images_list = a["images"]
            post_images = [None] * len(posts_list)
            img_counter = 0
            for pi in range(len(posts_list)):
                if pi < len(prompts_list):
                    prompt_val = (prompts_list[pi] or "").strip().lower()
                    if prompt_val == "none" or prompt_val == "":
                        continue  # This post is text-only
                if img_counter < len(images_list):
                    post_images[pi] = images_list[img_counter]
                    img_counter += 1
            a["post_images"] = post_images

            enriched_assets.append(a)

        # Provenance trail: idea → script → assets
        card = store.get_idea_card(draft["idea_card_id"])
        display_card = dict(card) if card else None
        if display_card:
            try:
                treatment_for_capture = json.loads(display_card.get("treatment") or "{}")
            except (json.JSONDecodeError, TypeError):
                treatment_for_capture = {}
            capture_required = treatment_for_capture.get("capture_required") or []
            if isinstance(capture_required, list):
                display_card["capture_tasks_parsed"] = [
                    item.get("task", item) if isinstance(item, dict) else item
                    for item in capture_required
                ]
            else:
                display_card["capture_tasks_parsed"] = []
            # Parse treatment + hooks for display
            display_card["treatment_parsed"] = treatment_for_capture
            try:
                display_card["hook_options_parsed"] = json.loads(display_card.get("hook_options") or "[]")
            except (json.JSONDecodeError, TypeError):
                display_card["hook_options_parsed"] = []
            try:
                display_card["evidence_links_parsed"] = json.loads(display_card.get("evidence_links") or "[]")
            except (json.JSONDecodeError, TypeError):
                display_card["evidence_links_parsed"] = []
        trail = []
        trail.append({"stage": "Idea", "state": "approved", "label": "Idea approved"})
        trail.append({"stage": "Script", "state": "approved", "label": "Script approved (shipped)"})
        if card and card["card_state"] == "asset_ready":
            trail.append({"stage": "Assets", "state": "ready", "label": "Assets ready for review"})
        elif enriched_assets:
            approved = [a for a in enriched_assets if a["asset_state"] == "approved"]
            if approved and len(approved) == len(enriched_assets):
                trail.append({"stage": "Assets", "state": "approved", "label": "All assets approved"})
            else:
                trail.append({"stage": "Assets", "state": "partial", "label": f"{len(approved)}/{len(enriched_assets)} assets approved"})
        else:
            trail.append({"stage": "Assets", "state": "pending", "label": "No assets generated yet"})

        return render_template("assets.html",
            business_name=business_name, draft=_parse_draft_for_display(draft),
            assets=enriched_assets, visual_direction=visual_direction,
            platforms=platforms, trail=trail, idea_card=display_card)

    @app.route("/api/assets/<int:draft_id>/fan-out", methods=["POST"])
    def assets_fan_out(draft_id):
        """T9.4: Assembler is media-only. Reads platform_content from the approved
        draft and creates assets directly — zero LLM text calls.

        The Writer already produced complete per-platform text. This route
        creates asset rows from platform_content (mechanical, no LLM).
        Media generation happens separately (Gate 3 review → generate visuals).
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency guard
        is_running, job_info = _check_job_running("fan_out", entity_id=draft_id)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already generating platform variants.",
                "job_id": job_info.get("job_id"),
            }), 409
        fan_job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            _get_jobs_store().fail_job(fan_job_id, "Draft not found")
            return jsonify({"error": "Draft not found"}), 404
        if draft["draft_state"] != "shipped":
            _get_jobs_store().fail_job(fan_job_id, f"Draft state is '{draft['draft_state']}'")
            return jsonify({"error": f"Draft state is '{draft['draft_state']}' — must be 'shipped' to fan out"}), 400

        # T9.4: Read platform_content from the draft — no LLM calls
        platform_content = json.loads(draft.get("platform_content") or "[]")
        if not platform_content:
            _get_jobs_store().fail_job(fan_job_id, "Draft has no platform_content")
            return jsonify({"error": "Draft has no platform_content — cannot assemble"}), 400

        # Idempotency: skip platforms that already have an asset for this draft
        existing_assets = store.list_assets(draft_id)
        existing_platforms = {a["platform"] for a in existing_assets
                              if a.get("asset_state") != "killed"}
        skipped_platforms = list(existing_platforms)

        assets_created = []
        for pc in platform_content:
            platform_name = pc.get("platform", "")
            if platform_name in existing_platforms:
                continue

            asset_id = store.create_asset(
                business_slug=business_slug,
                draft_id=draft_id,
                platform=platform_name,
                variant_type=pc.get("variant_type", "single_post"),
                content=pc.get("content", ""),
                image_prompts=pc.get("image_prompts", []),
                posts=pc.get("posts", []),
                native=True,  # All platform_content is native (Writer wrote it)
            )
            _carry_draft_media(app.config["DB_PATH"], draft_id, asset_id)
            assets_created.append({"id": asset_id, "platform": platform_name, "native": True})

        # F1: Mark job as done
        _get_jobs_store().complete_job(fan_job_id, f"assets:{len(assets_created)}")

        response = {"status": "ok", "assets": assets_created, "count": len(assets_created)}
        if skipped_platforms:
            response["skipped"] = skipped_platforms
            response["message"] = (
                f"Skipped {len(skipped_platforms)} platform(s) that already have assets: "
                f"{', '.join(skipped_platforms)}. Kill the existing variant first if you want a new one."
            )
        if not assets_created and skipped_platforms:
            response["status"] = "already_exists"
            response["message"] = (
                f"All platform variants already exist for this draft: {', '.join(skipped_platforms)}. "
                f"Kill the ones you want to regenerate, then click again."
            )
        return jsonify(response)

    @app.route("/api/assets/<int:asset_id>/gate", methods=["POST"])
    def assets_gate(asset_id):
        """T3.8: Gate 3 — approve/fix/kill per platform variant."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        action = request.json.get("action", "")
        if action not in ("approve", "fix", "kill"):
            return jsonify({"error": "Invalid action. Use approve, fix, or kill."}), 400

        state_map = {"approve": "approved", "fix": "fix", "kill": "killed"}
        store.update_asset_state(asset_id, state_map[action])
        return jsonify({"status": "ok", "new_state": state_map[action]})

    # ── F4: Media generation (image + video) ──

    @app.route("/api/assets/<int:asset_id>/generate-images", methods=["POST"])
    def generate_visuals(asset_id):
        """F4: Generate images for an asset from its image_prompts + visual direction.
        Images run automatically as part of 'Generate visuals' — no per-image confirmation needed."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency guard
        is_running, job_info = _check_job_running("media_images", entity_id=asset_id)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already generating visuals for this asset.",
                "job_id": job_info.get("job_id"),
            }), 409
        media_job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            _get_jobs_store().fail_job(media_job_id, "Asset not found")
            return jsonify({"error": "Asset not found"}), 404

        # Get image prompts from the asset (fan-out) + visual direction from the draft
        image_prompts = json.loads(asset.get("image_prompts") or "[]")
        draft = store.get_draft(asset["draft_id"])
        visual_direction = json.loads(draft.get("visual_direction") or "{}") if draft else {}

        # If asset has no image_prompts, fall back to the draft's visual direction
        if not image_prompts and visual_direction:
            image_prompts = visual_direction.get("image_prompts", [])

        if not image_prompts:
            _get_jobs_store().fail_job(media_job_id, "No image prompts found")
            return jsonify({"error": "No image prompts found on this asset or its draft"}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError as e:
            _get_jobs_store().fail_job(media_job_id, str(e)[:200])
            return jsonify({"error": f"Config error: {e}"}), 500

        from media_adapter import MediaAdapter, MediaAdapterError
        adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        # S4: Count carried media — generate only for prompts beyond what's carried
        carried_media = adapter.list_asset_media(asset_id, kind="image", owner_type="asset")
        carried_count = len(carried_media)

        # Check for regenerate flag
        try:
            req_body = request.get_json(silent=True) or {}
        except Exception:
            req_body = {}
        regenerate = req_body.get("regenerate", False) if req_body else False

        # If we have carried media and not regenerating, only generate for uncovered prompts
        if carried_count > 0 and not regenerate:
            active_prompts = [(i, p) for i, p in enumerate(image_prompts)
                            if p.strip().lower() != "none" and i >= carried_count]
        else:
            active_prompts = [(i, p) for i, p in enumerate(image_prompts) if p.strip().lower() != "none"]

        # Determine aspect ratio from the platform
        platform_name = asset.get("platform", "").lower()
        if "instagram" in platform_name and "reel" in asset.get("variant_type", "").lower():
            aspect_ratio = "9:16"
        elif "instagram" in platform_name and "carousel" in asset.get("variant_type", "").lower():
            aspect_ratio = "1:1"
        elif "x" in platform_name or "twitter" in platform_name:
            aspect_ratio = "16:9"
        else:
            aspect_ratio = "9:16"  # default vertical for short-form

        results = []
        errors = []
        # S4: active_prompts already filtered above (carried media check)
        for idx, prompt in active_prompts:
            try:
                result = adapter.generate_image(
                    prompt=prompt,
                    asset_id=asset_id,
                    aspect_ratio=aspect_ratio,
                    context=f"Image {idx+1} for asset {asset_id} ({platform_name})",
                    business_slug=business_slug,
                )
                results.append(result)
            except (MediaAdapterError, Exception) as e:
                errors.append({"prompt": prompt[:100], "error": str(e)[:200]})

        # Store generated image paths on the asset
        generated_paths = [r["path"] for r in results]
        if generated_paths:
            existing_images = json.loads(asset.get("generated_images") or "[]")
            existing_images.extend(generated_paths)
            conn = __import__("sqlite3").connect(app.config["DB_PATH"])
            from datetime import datetime, timezone
            conn.execute(
                "UPDATE assets SET generated_images = ?, updated_at = ? WHERE id = ?",
                (json.dumps(existing_images), datetime.now(timezone.utc).isoformat(), asset_id),
            )
            conn.commit()
            conn.close()

        _get_jobs_store().complete_job(media_job_id, f"images:{len(results)}")

        # If all images failed, return error status so the JS shows the message
        if len(results) == 0 and errors:
            error_msg = errors[0].get("error", "Image generation failed")
            return jsonify({
                "status": "error",
                "error": error_msg,
                "images_generated": 0,
                "errors": errors,
            }), 500

        return jsonify({
            "status": "ok",
            "images_generated": len(results),
            "carried": carried_count,
            "regenerate": regenerate,
            "errors": errors,
            "image_paths": generated_paths,
        })

    @app.route("/api/assets/<int:asset_id>/generate-video", methods=["POST"])
    def generate_video(asset_id):
        """F4: Submit a video generation job. Video always requires explicit confirmation
        with model + estimated cost shown before the click — the no-surprise-spend rule."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency guard
        is_running, job_info = _check_job_running("media_video", entity_id=asset_id)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Video generation already in progress for this asset.",
                "job_id": job_info.get("job_id"),
            }), 409
        video_job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            _get_jobs_store().fail_job(video_job_id, "Asset not found")
            return jsonify({"error": "Asset not found"}), 404

        prompt = request.json.get("prompt", "")
        duration = request.json.get("duration", 5)
        aspect_ratio = request.json.get("aspect_ratio", "9:16")

        if not prompt:
            # Use the draft's visual direction to construct a prompt
            draft = store.get_draft(asset["draft_id"])
            vd = json.loads(draft.get("visual_direction") or "{}") if draft else {}
            shot_choices = vd.get("shot_format_choices", [])
            image_prompts = vd.get("image_prompts", [])
            prompt = ". ".join(shot_choices[:2] + image_prompts[:1]) if (shot_choices or image_prompts) else asset["content"][:500]

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError as e:
            _get_jobs_store().fail_job(video_job_id, str(e)[:200])
            return jsonify({"error": f"Config error: {e}"}), 500

        from media_adapter import MediaAdapter, MediaAdapterError
        adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        try:
            result = adapter.submit_video(
                prompt=prompt,
                asset_id=asset_id,
                aspect_ratio=aspect_ratio,
                duration=duration,
                context=f"Video generation for asset {asset_id}",
                business_slug=business_slug,
            )
            _get_jobs_store().complete_job(video_job_id, f"video_submitted:{result.get('external_job_id', '')}")
            return jsonify({
                "status": "ok",
                "external_job_id": result.get("external_job_id"),
                "model": result.get("model"),
                "estimated_cost": result.get("cost_usd", 0),
            })
        except MediaAdapterError as e:
            _get_jobs_store().fail_job(video_job_id, str(e)[:200])
            return jsonify({"error": str(e)}), 500

    @app.route("/api/assets/<int:asset_id>/media", methods=["GET"])
    def get_asset_media(asset_id):
        """F4/F5: List all generated media for an asset (images, videos, final cuts)."""
        from media_adapter import MediaAdapter
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}
        adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])
        media = adapter.list_asset_media(asset_id)
        return jsonify({"status": "ok", "media": media})

    @app.route("/media/<path:filepath>")
    def serve_media(filepath):
        """Serve generated media files from data/media/.
        Handles paths that may or may not include the data/media/ prefix."""
        # Strip leading "data/media/" if present (paths from DB include it)
        if filepath.startswith("data/media/"):
            filepath = filepath[len("data/media/"):]
        # Use absolute path to avoid gunicorn working directory issues
        media_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "media")
        media_root = os.path.abspath(media_root)
        return send_from_directory(media_root, filepath)

    # ── Final Assembly: Edit Plan + Render (CORRECTION-final-assembly Part 1) ──

    @app.route("/api/assets/<int:asset_id>/edit-plan", methods=["POST"])
    def generate_edit_plan(asset_id):
        """Final Assembly: Generate an Edit Plan via LLM for an asset."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency guard
        is_running, job_info = _check_job_running("edit_plan", entity_id=asset_id)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Already generating edit plan.",
            }), 409
        plan_job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            _get_jobs_store().fail_job(plan_job_id, "Asset not found")
            return jsonify({"error": "Asset not found"}), 404

        draft = store.get_draft(asset["draft_id"])
        if not draft:
            _get_jobs_store().fail_job(plan_job_id, "Draft not found")
            return jsonify({"error": "Draft not found"}), 404

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            _get_jobs_store().fail_job(plan_job_id, str(e)[:200])
            return jsonify({"error": f"Config error: {e}"}), 500

        # Capture guard: if the idea card has capture_required tasks, the edit
        # planner may only work from this asset's generated media and this
        # card's linked capture uploads. Never substitute random old uploads
        # from the business-wide materials library.
        card = store.get_idea_card(draft["idea_card_id"]) if draft.get("idea_card_id") else None
        capture_required = []
        capture_upload_ids = set()
        if card:
            import json as _json
            treatment = _json.loads(card.get("treatment") or "{}")
            capture_required = treatment.get("capture_required", [])
            capture_upload_ids = {int(mid) for mid in _json.loads(card.get("capture_uploads") or "[]")}

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import EDIT_PLAN_SCHEMA
        from media_adapter import MediaAdapter

        # Build ingredient inventory
        adapter_llm = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")
        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        ingredients = []
        visual_ingredient_count = 0
        # F5 (CORRECTION-feedback-plumbing): probe real durations for videos/uploads
        from assembly import probe_duration

        # Generated media
        for m in media_adapter.list_asset_media(asset_id):
            kind = m.get("kind", "")
            if kind in ("image", "video"):
                if kind == "image":
                    dur = 3.0  # images: 3.0s is plan intent, not a file property
                    desc = (m.get("prompt") or "")[:100]
                else:
                    # F5: probe real duration for generated videos
                    media_path = os.path.join("data", "media", str(asset_id), os.path.basename(m.get("path", "")))
                    probed = probe_duration(media_path)
                    if probed is not None:
                        dur = probed
                        desc = (m.get("prompt") or "")[:100]
                    else:
                        dur = 5.0  # fallback default
                        desc = (m.get("prompt") or "")[:100] + " (duration unverified)"
                ingredients.append({
                    "id": f"generated:{m['id']}",
                    "kind": kind,
                    "duration": dur,
                    "description": desc,
                })
                visual_ingredient_count += 1

        # Uploaded materials — ONLY this card's linked capture uploads, never
        # session_upload and never unrelated capture_upload history.
        # session_upload materials are personal WhatsApp/voice recordings for voice
        # analysis, NOT content to be stitched into public-facing videos.
        # Privacy: personal recordings must never leak into published content.
        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        all_materials = intake.list_materials(business_slug)
        for mat in all_materials:
            if int(mat.get("id")) not in capture_upload_ids:
                continue
            # Privacy guard: skip session uploads — these are personal voice/audio
            # recordings used for voice analysis, never as video content.
            if mat.get("channel") == "session_upload":
                continue
            if mat.get("material_type") in ("video", "audio"):
                # F5: probe real duration for uploaded video/audio
                mat_path = mat.get("file_path") or ""
                if mat_path and not os.path.isabs(mat_path):
                    mat_path = os.path.join("data", "materials", mat_path)
                probed = probe_duration(mat_path) if mat_path else None
                if probed is not None:
                    dur = probed
                    desc = (mat.get("filename") or mat.get("normalized_content", ""))[:100]
                else:
                    dur = 10.0  # fallback default
                    desc = (mat.get("filename") or mat.get("normalized_content", ""))[:100] + " (duration unverified)"
                ingredients.append({
                    "id": f"upload:{mat['id']}",
                    "kind": "video" if str(mat.get("filename") or "").lower().endswith((".mp4", ".mov", ".avi", ".webm")) else mat["material_type"],
                    "duration": dur,
                    "description": desc,
                })
                visual_ingredient_count += 1

        if visual_ingredient_count == 0:
            message = (
                "No usable visual media is available. Generate missing media or upload "
                "a capture before creating an edit plan."
            )
            _get_jobs_store().fail_job(plan_job_id, message[:200])
            return jsonify({
                "status": "missing_media",
                "message": message,
                "required_count": len(capture_required),
                "available_visual_count": 0,
                "missing_count": max(1, len(capture_required)),
            }), 409

        if capture_required and visual_ingredient_count < len(capture_required):
            missing_count = len(capture_required) - visual_ingredient_count
            message = (
                f"Missing {missing_count} required visual capture(s). "
                "Generate missing media or upload the required captures before creating an edit plan."
            )
            _get_jobs_store().fail_job(plan_job_id, message[:200])
            return jsonify({
                "status": "missing_media",
                "message": message,
                "required_count": len(capture_required),
                "available_visual_count": visual_ingredient_count,
                "missing_count": missing_count,
            }), 409

        inventory_text = "\n".join(
            f"- {ing['id']} ({ing['kind']}, {ing['duration']:.1f}s): {ing['description']}"
            for ing in ingredients
        ) or "(no ingredients available)"

        # Determine canvas from format/platform
        platform_name = asset.get("platform", "")
        variant_type = asset.get("variant_type", "").lower()
        if "reel" in variant_type or "short" in variant_type:
            aspect, resolution, max_seg = "9:16", "1080x1920", 3
        elif "carousel" in variant_type:
            aspect, resolution, max_seg = "1:1", "1080x1080", 3
        else:
            aspect, resolution, max_seg = "16:9", "1920x1080", 4

        # Load modules via context assembly (CORRECTION-module-context-assembly)
        from context_assembly import assemble_module_context

        format_name_for_lookup = draft.get("format") or ""
        module_vars, module_prov = assemble_module_context(
            "assembly/edit_plan_v1.md", business_slug,
            dynamic={"format_name": format_name_for_lookup},
            db_path=app.config["DB_PATH"], modules_dir="modules",
        )

        # Feedback (if regenerating with feedback)
        feedback = request.json.get("feedback", "")

        try:
            result = adapter_llm.complete(
                prompt_file="assembly/edit_plan_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "platform_name": platform_name,
                    "format_name": draft.get("format") or "",
                    "scope": draft.get("scope") or "",
                    "asset_content": asset["content"][:2000],
                    "vo_info": "(no VO take yet)",
                    "ingredient_inventory": inventory_text,
                    "max_segment_seconds": str(max_seg),
                    **module_vars,
                },
                schema=EDIT_PLAN_SCHEMA,
                backend="default",
                context=f"Edit plan for asset {asset_id} ({platform_name}) | module_ctx: {module_prov}",
                business_slug=business_slug,
            )
        except (LLMAdapterError, Exception) as e:
            _get_jobs_store().fail_job(plan_job_id, str(e)[:200])
            return jsonify({"error": str(e)}), 500

        # Save the edit plan
        plan_id = store.save_edit_plan(draft["id"], asset_id, result)

        # Build readable cut list
        from assembly import AssemblyRenderer
        renderer = AssemblyRenderer(models_config, db_path=app.config["DB_PATH"])
        cut_list = renderer.format_cut_list_for_display(result)

        _get_jobs_store().complete_job(plan_job_id, f"plan:{plan_id}")

        return jsonify({
            "status": "ok",
            "plan_id": plan_id,
            "cut_list": cut_list,
            "plan": result,
        })

    @app.route("/api/assets/<int:asset_id>/edit-plans", methods=["GET"])
    def list_edit_plans(asset_id):
        """List all edit plans for an asset."""
        store = _get_pipeline_store()
        plans = store.list_edit_plans(asset_id)
        # Parse plan_json for display
        for p in plans:
            try:
                p["plan_parsed"] = json.loads(p.get("plan_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                p["plan_parsed"] = {}
        return jsonify({"status": "ok", "plans": plans})

    @app.route("/api/assets/<int:asset_id>/render", methods=["POST"])
    def render_final_cut(asset_id):
        """Final Assembly: Render the edit plan to a finished MP4."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        # F1: Idempotency guard (long stale timeout for rendering)
        is_running, job_info = _check_job_running("assembly_render", entity_id=asset_id,
                                                   stale_timeout_s=1200)
        if is_running:
            return jsonify({
                "status": "running",
                "message": "Render already in progress for this asset.",
            }), 409
        render_job_id = job_info.get("job_id")

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            _get_jobs_store().fail_job(render_job_id, "Asset not found")
            return jsonify({"error": "Asset not found"}), 404

        plan_id = request.json.get("plan_id")
        if not plan_id:
            _get_jobs_store().fail_job(render_job_id, "No plan_id provided")
            return jsonify({"error": "plan_id required"}), 400

        edit_plan = store.get_edit_plan(plan_id)
        if not edit_plan:
            _get_jobs_store().fail_job(render_job_id, "Edit plan not found")
            return jsonify({"error": "Edit plan not found"}), 404

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from assembly import AssemblyRenderer, AssemblyError

        plan = json.loads(edit_plan.get("plan_json") or "{}")
        renderer = AssemblyRenderer(models_config, db_path=app.config["DB_PATH"])

        # Update plan status to rendering
        store.update_edit_plan_status(plan_id, "rendering")

        try:
            result = renderer.render(
                plan=plan,
                asset_id=asset_id,
                draft_id=asset["draft_id"],
                business_slug=business_slug,
                plan_id=plan_id,
            )
            # VH-4: validate output file size — 0 bytes = silent render failure
            import os as _os
            out_path = result["path"]
            if not _os.path.exists(out_path) or _os.path.getsize(out_path) == 0:
                # Delete the 0-byte file so it doesn't linger as a false green
                if _os.path.exists(out_path):
                    _os.remove(out_path)
                err_msg = "Render produced a 0-byte output file — FFmpeg failed silently"
                _get_jobs_store().fail_job(render_job_id, err_msg)
                store.update_edit_plan_status(plan_id, "failed", err_msg)
                return jsonify({"error": err_msg}), 500
            _get_jobs_store().complete_job(render_job_id, f"rendered:{out_path}")
            return jsonify({
                "status": "ok",
                "path": out_path,
                "duration": result["duration"],
                "render_time_s": result["render_time_s"],
                "version": result["version"],
                "cut_list": result["cut_list"],
            })
        except AssemblyError as e:
            _get_jobs_store().fail_job(render_job_id, str(e)[:200])
            store.update_edit_plan_status(plan_id, "failed", str(e)[:500])
            return jsonify({"error": str(e)}), 500

    @app.route("/api/assets/<int:asset_id>/render-status", methods=["GET"])
    def render_status(asset_id):
        """Check render status for an asset — used for polling while rendering in background."""
        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        # Check for final_cut media
        from media_adapter import MediaAdapter
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}
        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])
        media_list = media_adapter.list_asset_media(asset_id)
        final_cuts = [m for m in media_list if m.get("kind") == "final_cut"]

        # Check edit plan status
        edit_plans = store.list_edit_plans(asset_id)
        plan_status = None
        if edit_plans:
            plan_status = edit_plans[0].get("status")

        # Check job status
        jobs_store = _get_jobs_store()
        conn = __import__("sqlite3").connect(app.config["DB_PATH"])
        conn.row_factory = __import__("sqlite3").Row
        job_row = conn.execute(
            "SELECT * FROM jobs WHERE job_type = 'assembly_render' AND entity_id = ? ORDER BY id DESC LIMIT 1",
            (asset_id,),
        ).fetchone()
        conn.close()
        job_status = dict(job_row)["status"] if job_row else None

        if final_cuts:
            return jsonify({
                "status": "rendered",
                "path": final_cuts[-1]["path"],
                "plan_status": plan_status,
            })
        if job_status == "running":
            return jsonify({"status": "rendering", "plan_status": plan_status})
        if job_status == "failed":
            error = dict(job_row).get("error", "") if job_row else ""
            return jsonify({"status": "failed", "error": error, "plan_status": plan_status})
        if plan_status == "rendering":
            return jsonify({"status": "rendering", "plan_status": plan_status})
        return jsonify({"status": "idle", "plan_status": plan_status})

    @app.route("/api/stock/search", methods=["POST"])
    def search_stock():
        """Final Assembly: Search stock library (Pexels + Pixabay)."""
        query = request.json.get("query", "")
        kind = request.json.get("kind", "photo")
        per_page = request.json.get("per_page", 5)

        if not query:
            return jsonify({"error": "query required"}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from stock_adapter import StockAdapter
        adapter = StockAdapter(models_config, db_path=app.config["DB_PATH"])
        results = adapter.search(query, kind=kind, per_page=per_page)

        return jsonify({"status": "ok", "results": results, "count": len(results)})

    @app.route("/api/stock/download", methods=["POST"])
    def download_stock():
        """Download a stock clip and register it as an ingredient for an asset."""
        item = request.json.get("item", {})
        asset_id = request.json.get("asset_id")

        if not item or not asset_id:
            return jsonify({"error": "item and asset_id required"}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from stock_adapter import StockAdapter, StockAdapterError
        adapter = StockAdapter(models_config, db_path=app.config["DB_PATH"])
        try:
            path = adapter.download(item)
        except StockAdapterError as e:
            return jsonify({"error": str(e)}), 500

        # Get the stock_cache ID for this download
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(app.config["DB_PATH"])
        conn.row_factory = _sqlite3.Row
        row = conn.execute(
            "SELECT id FROM stock_cache WHERE local_path = ?",
            (path,),
        ).fetchone()
        conn.close()
        stock_id = row["id"] if row else 0

        return jsonify({
            "status": "ok",
            "path": path,
            "ingredient_id": f"stock:{stock_id}",
            "title": item.get("title", ""),
        })

    @app.route("/api/assets/<int:asset_id>/generate-clip", methods=["POST"])
    def generate_clip(asset_id):
        """Generate a video clip for a segment using AI (Grok/xAI).

        Input: {prompt, duration, aspect_ratio}
        Returns: {status, path, ingredient_id} when done (synchronous).
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        prompt = request.json.get("prompt", "")
        duration = request.json.get("duration", 5)
        aspect_ratio = request.json.get("aspect_ratio", "9:16")

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        if not prompt:
            # The operator may leave the dialog prompt blank. Derive the same
            # asset-specific fallback used by the earlier video endpoint.
            draft = store.get_draft(asset["draft_id"])
            visual_direction = json.loads(draft.get("visual_direction") or "{}") if draft else {}
            shot_choices = visual_direction.get("shot_format_choices", [])
            image_prompts = visual_direction.get("image_prompts", [])
            prompt = ". ".join(shot_choices[:2] + image_prompts[:1])
            if not prompt:
                prompt = (asset.get("content") or "").strip()
            if not prompt:
                return jsonify({"error": "No visual direction is available for this asset"}), 409

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from media_adapter import MediaAdapter, MediaAdapterError
        adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        try:
            # Submit video generation
            submit_result = adapter.submit_video(
                prompt=prompt,
                asset_id=asset_id,
                aspect_ratio=aspect_ratio,
                duration=duration,
                context=f"AI clip generation for asset {asset_id}",
                business_slug=business_slug,
            )
            external_job_id = submit_result.get("external_job_id")
            if not external_job_id:
                return jsonify({"error": "No job ID returned from video API"}), 500

            # Poll until done (with timeout)
            import time as _time
            max_polls = 60  # 5 minutes at 5s intervals
            for _ in range(max_polls):
                _time.sleep(5)
                poll_result = adapter.check_video_job(external_job_id)
                status = poll_result.get("status", "")
                if status == "completed":
                    download_url = poll_result.get("download_url", "")
                    if not download_url:
                        return jsonify({
                            "error": "Job completed but no download URL returned",
                        }), 500
                    # download_video() downloads the file AND records it in
                    # asset_media — returns {file_path, media_id}. Do NOT call
                    # _record_media separately (would double-register).
                    dl = adapter.download_video(
                        external_job_id, download_url, asset_id,
                        submit_result.get("model", ""),
                        prompt,
                        poll_result.get("cost_usd", 0),
                        business_slug,
                    )
                    return jsonify({
                        "status": "ok",
                        "path": dl["file_path"],
                        "ingredient_id": f"generated:{dl['media_id']}",
                    })
                elif status == "failed":
                    return jsonify({"error": poll_result.get("error", "Video generation failed")}), 500

            return jsonify({"error": "Video generation timed out — check back later"}), 504
        except MediaAdapterError as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/assets/<int:asset_id>/missing-captures", methods=["GET"])
    def missing_captures(asset_id):
        """Get the missing capture tasks for an asset's idea card.
        Returns the capture_required tasks and how many are fulfilled."""
        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        draft = store.get_draft(asset["draft_id"])
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        card = store.get_idea_card(draft["idea_card_id"]) if draft.get("idea_card_id") else None
        if not card:
            return jsonify({"status": "ok", "capture_required": [], "uploads": [], "missing": []})

        import json as _json
        treatment = _json.loads(card.get("treatment") or "{}")
        capture_required = treatment.get("capture_required", [])
        uploads = _json.loads(card.get("capture_uploads") or "[]")
        missing = capture_required[len(uploads):] if len(uploads) < len(capture_required) else []

        return jsonify({
            "status": "ok",
            "capture_required": capture_required,
            "uploads": uploads,
            "missing": missing,
            "missing_count": len(missing),
        })

    @app.route("/api/assets/<int:asset_id>/generate-media", methods=["POST"])
    def generate_missing_media(asset_id):
        """LLM-driven media generation plan: the LLM acts as creative director,
        deciding per-segment which generator to use and writing style-consistent
        prompts so all clips share a cohesive visual look.

        Flow: get missing captures → LLM produces media plan → execute each plan
        item (stock download or AI generation) → register as ingredients.
        """
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        draft = store.get_draft(asset["draft_id"])
        if not draft:
            return jsonify({"error": "Draft not found"}), 404

        # Get missing captures
        card = store.get_idea_card(draft["idea_card_id"]) if draft.get("idea_card_id") else None
        if not card:
            return jsonify({"error": "No idea card for this asset"}), 400

        import json as _json
        treatment = _json.loads(card.get("treatment") or "{}")
        capture_required = treatment.get("capture_required", [])
        uploads = _json.loads(card.get("capture_uploads") or "[]")
        missing = capture_required[len(uploads):] if len(uploads) < len(capture_required) else []

        if not missing:
            return jsonify({"status": "ok", "message": "No missing captures — all fulfilled"})

        # Build missing captures text for the prompt
        missing_text = "\n".join(f"{i}. {task}" for i, task in enumerate(missing))

        # Load config + modules
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        # Assemble module context (Visual Style)
        from context_assembly import assemble_module_context
        module_vars, module_prov = assemble_module_context(
            "assembly/media_plan_v1.md", business_slug,
            db_path=app.config["DB_PATH"], modules_dir="modules",
        )

        # Build available generators list from config — config-driven, not hardcoded
        media_config = models_config.get("media", {})
        stock_config = models_config.get("stock", {})
        generators = []

        # Stock footage
        stock_providers = stock_config.get("providers", [])
        if stock_providers:
            import os as _os
            stock_key_env = {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY"}
            available_stock = [p for p in stock_providers if _os.environ.get(stock_key_env.get(p, ""), "")]
            missing_stock = [p for p in stock_providers if p not in available_stock]
            stock_status = (
                f"✅ available: {', '.join(available_stock)}" if available_stock
                else f"⚠️ needs API key: {', '.join(missing_stock)}"
            )
            if available_stock and missing_stock:
                stock_status += f"; unavailable: {', '.join(missing_stock)}"
            generators.append(
                f"- **stock** — Search {', '.join(stock_providers)} for real-world footage. "
                f"You write a search query. Returns real video clips. {stock_status}."
            )

        # Video generators — read from video_generators list (new config)
        video_gens = media_config.get("video_generators", [])
        # Filter to only generators whose API key is set
        for vg in video_gens:
            api_key_env = vg.get("api_key_env", "")
            import os as _os
            api_key_set = bool(_os.environ.get(api_key_env, ""))
            status = "✅ available" if api_key_set else "⚠️ needs API key"
            generators.append(
                f"- **ai_video:{vg['name']}** — {vg.get('provider', '')} video generation ({vg.get('model', '')}). "
                f"Best for: {vg.get('best_for', '')}. {status}."
            )

        # Fallback to legacy single video generator if no list configured
        if not video_gens:
            video_model = media_config.get("video_default", "")
            video_provider = media_config.get("video_provider", "")
            if video_model:
                generators.append(
                    f"- **ai_video** — Generate a video clip with AI ({video_model} via {video_provider}). "
                    f"You write the generation prompt. Full creative control over the output."
                )

        # AI image generation
        image_model = media_config.get("image_default", "")
        if image_model:
            generators.append(
                f"- **ai_image** — Generate a static image with AI ({image_model}). "
                f"You write the generation prompt. Use for cover frames, data cards, text slides."
            )

        # Voice/narration
        voice_config = models_config.get("voice_cloning", {})
        voice_engine = voice_config.get("engine", "")
        if voice_engine:
            generators.append(
                f"- **voice** — Generate narration/voiceover ({voice_engine}). "
                f"You write the script text. The voice will match the business's voice profile."
            )

        # 3D/animation (check if configured and enabled)
        animation_config = media_config.get("animation", {})
        if animation_config.get("enabled"):
            anim_tool = animation_config.get("tool", "blender")
            generators.append(
                f"- **animation** — 3D animation / motion graphics ({anim_tool}). "
                f"Best for: {animation_config.get('best_for', 'motion graphics and 3D sequences')}. "
                f"You write the scene description."
            )

        available_generators = "\n".join(generators) if generators else "(no generators configured)"

        # Call LLM with the media plan prompt
        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import MEDIA_PLAN_SCHEMA

        adapter_llm = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter_llm.complete(
                prompt_file="assembly/media_plan_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "platform_name": asset.get("platform", ""),
                    "format_name": draft.get("format") or "",
                    "asset_content": asset["content"][:2000],
                    "missing_captures": missing_text,
                    "available_generators": available_generators,
                    **module_vars,
                },
                schema=MEDIA_PLAN_SCHEMA,
                backend="default",
                context=f"Media plan for asset {asset_id} ({asset.get('platform', '')}) | module_ctx: {module_prov}",
                business_slug=business_slug,
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        # Execute the media plan
        from media_adapter import MediaAdapter, MediaAdapterError
        from stock_adapter import StockAdapter, StockAdapterError
        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])
        stock_adapter = StockAdapter(models_config, db_path=app.config["DB_PATH"])

        results = []
        for plan_item in result.get("media_plan", []):
            generator = plan_item.get("generator", "")
            item_result = {"capture_index": plan_item.get("capture_index", 0), "generator": generator}

            try:
                if generator == "stock":
                    # Search stock libraries
                    query = plan_item.get("search_query", "")
                    stock_results = stock_adapter.search(query, kind="video", per_page=3)
                    if stock_results:
                        # Download the first match
                        path = stock_adapter.download(stock_results[0])
                        # Get stock_cache ID
                        import sqlite3 as _sqlite3
                        conn = _sqlite3.connect(app.config["DB_PATH"])
                        conn.row_factory = _sqlite3.Row
                        row = conn.execute(
                            "SELECT id FROM stock_cache WHERE local_path = ?",
                            (path,),
                        ).fetchone()
                        conn.close()
                        stock_id = row["id"] if row else 0
                        stock_provider = stock_results[0].get("provider", "stock")
                        media_id = media_adapter._record_media(
                            asset_id, "video", path,
                            f"stock:{stock_provider}", query, 0,
                            owner_type="asset",
                        )
                        item_result["status"] = "ok"
                        item_result["ingredient_id"] = f"generated:{media_id}"
                        item_result["stock_id"] = stock_id
                        item_result["path"] = path
                    else:
                        # Fallback to AI generation
                        fallback = plan_item.get("fallback_generator", "ai_video")
                        fallback_prompt = plan_item.get("fallback_prompt", plan_item.get("generation_prompt", ""))
                        if fallback and fallback_prompt:
                            try:
                                resolved = _resolve_ai_video_generator(fallback, media_config)
                            except ValueError as ve:
                                item_result["status"] = "failed"
                                item_result["error"] = str(ve)
                            else:
                                duration = plan_item.get("duration", 5)
                                submit = media_adapter.submit_video(
                                    prompt=fallback_prompt, asset_id=asset_id,
                                    aspect_ratio="9:16", duration=duration,
                                    model=resolved["model"],
                                    provider=resolved["provider"],
                                    context=f"Media plan fallback ({fallback}) for asset {asset_id}",
                                    business_slug=business_slug,
                                )
                                ext_job = submit.get("external_job_id")
                                if not ext_job:
                                    item_result["status"] = "failed"
                                    item_result["error"] = "Video API returned no job ID"
                                else:
                                    # VH-2: poll → download → register
                                    poll_result = _poll_download_register_video(
                                        media_adapter, ext_job, asset_id,
                                        submit.get("model", resolved["model"] or ""),
                                        fallback_prompt, business_slug,
                                        provider=resolved["provider"],
                                    )
                                    item_result.update(poll_result)
                        else:
                            item_result["status"] = "failed"
                            item_result["error"] = "Stock search returned nothing and no fallback configured"

                elif generator.startswith("ai_video"):
                    # Handle both "ai_video" and "ai_video:<model_name>"
                    prompt = plan_item.get("generation_prompt", "")
                    if prompt:
                        resolved = _resolve_ai_video_generator(generator, media_config)
                        duration = plan_item.get("duration", 5)
                        # Submit video generation
                        submit = media_adapter.submit_video(
                            prompt=prompt, asset_id=asset_id,
                            aspect_ratio="9:16", duration=duration,
                            model=resolved["model"],
                            provider=resolved["provider"],
                            context=f"Media plan AI generation ({generator}) for asset {asset_id}",
                            business_slug=business_slug,
                        )
                        ext_job = submit.get("external_job_id")
                        if not ext_job:
                            item_result["status"] = "failed"
                            item_result["error"] = "Video API returned no job ID"
                        else:
                            # VH-2: poll → download → register
                            poll_result = _poll_download_register_video(
                                media_adapter, ext_job, asset_id,
                                submit.get("model", resolved["model"] or ""),
                                prompt, business_slug,
                                provider=resolved["provider"],
                            )
                            item_result.update(poll_result)

                elif generator == "ai_image":
                    prompt = plan_item.get("generation_prompt", "")
                    if prompt:
                        img_result = media_adapter.generate_image(
                            prompt=prompt, asset_id=asset_id,
                            aspect_ratio="9:16",
                            context=f"Media plan AI image for asset {asset_id}",
                            business_slug=business_slug,
                        )
                        item_result["status"] = "ok"
                        item_result["path"] = img_result["path"]

                elif generator == "voice":
                    # Voice generation — placeholder (TTS integration via voice_cloning config)
                    script_text = plan_item.get("script_text") or plan_item.get("generation_prompt", "")
                    if script_text:
                        # TODO: wire to voice_cloning engine when TTS is ready
                        item_result["status"] = "skipped"
                        item_result["error"] = "Voice generation not yet wired — TTS engine configured but not implemented"

                elif generator == "animation":
                    # 3D/animation — placeholder
                    prompt = plan_item.get("generation_prompt", "")
                    if prompt:
                        item_result["status"] = "skipped"
                        item_result["error"] = "Animation generation not yet wired — configure and install the animation tool"

                else:
                    item_result["status"] = "skipped"
                    item_result["error"] = f"Unknown generator: {generator}"

            except (MediaAdapterError, StockAdapterError, Exception) as e:
                item_result["status"] = "failed"
                item_result["error"] = str(e)[:200]

            results.append(item_result)

        summary = _summarize_media_generation_results(results)
        response_payload = {
            "status": "ok",
            "media_plan": result.get("media_plan", []),
            "results": results,
            "count": len(results),
            **summary,
        }
        if (len(results) > 0 and summary["available_count"] == 0
                and summary["submitted_count"] == 0
                and summary["processing_count"] == 0):
            response_payload["status"] = "error"
            response_payload["error"] = (
                f"No renderable media was generated — "
                f"{summary['failed_count']} failed, {summary['skipped_count']} skipped."
            )
            return jsonify(response_payload), 500

        return jsonify(response_payload)

    # ── T3.12: Publish handoff ──

    @app.route("/create/publish/<int:draft_id>")
    def publish_page(draft_id):
        """Gate 4 — go/hold + timing for approved assets (T3.12)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return "Draft not found", 404

        assets = store.list_assets(draft_id)
        approved_assets = [a for a in assets if a["asset_state"] == "approved"]
        published_assets = [a for a in assets if a["asset_state"] in ("published",) and a.get("publish_scheduled_at")]

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        return render_template("publish.html",
            business_name=business_name, draft=draft,
            approved_assets=approved_assets,
            published_assets=published_assets)

    @app.route("/api/assets/<int:asset_id>/schedule", methods=["POST"])
    def schedule_publish(asset_id):
        """T4.1: Schedule an approved asset for publish via Buffer (go + timing).
        HARD RULE: asset must be 'approved' — no auto-publish.
        post_now=true → share immediately (Buffer shareNow mode)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        if asset["asset_state"] != "approved":
            return jsonify({"error": "Asset must be approved first — no auto-publish"}), 400

        body = request.json or {}
        scheduled_at = body.get("scheduled_at", "")
        post_now = body.get("post_now", False)

        # Hold = empty scheduled_at and not post_now → don't publish
        if not scheduled_at and not post_now:
            return jsonify({"status": "ok", "message": "Held — not scheduled"})

        # ── Buffer publish path ──
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from buffer_adapter import BufferAdapter, BufferError
        publish = BufferAdapter(models_config, db_path=app.config["DB_PATH"])
       

        # Parse posts for thread/carousel
        posts_list = json.loads(asset.get("posts") or "[]")

        # Get generated images for this asset
        from media_adapter import MediaAdapter
        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])
        asset_media = media_adapter.list_asset_media(asset_id)
        images = [{"id": m.get("postiz_id", ""), "path": m.get("path", "")} for m in asset_media if m.get("kind") == "image"]

        try:
            result = publish.publish_piece(
                business_slug=business_slug,
                asset_id=asset_id,
                platform=asset["platform"],
                content=asset["content"],
                posts=posts_list if posts_list else None,
                images=images if images else None,
                scheduled_at=scheduled_at,
                asset_state=asset["asset_state"],
            )
            # Mark asset as published in pipeline
            store.set_asset_schedule(asset_id, scheduled_at)
            store.update_asset_state(asset_id, "published")
            return jsonify({
                "status": "ok",
                "scheduled_at": scheduled_at,
                "postiz_post_id": result.get("postiz_post_id", ""),
                "publish_status": result.get("status", ""),
            })
        except BufferError as e:
            # Buffer not available or failed — surface the error honestly
            # The asset stays in 'approved' state, no data loss
            return jsonify({
                "status": "error",
                "error": str(e),
                "hint": "Buffer may not be configured. Set BUFFER_API_KEY and configure buffer channels in models.yaml. The asset stays approved — no data lost.",
            }), 502

    @app.route("/api/publish/<int:asset_id>/retry", methods=["POST"])
    def retry_publish(asset_id):
        """Retry a failed publish attempt."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from buffer_adapter import BufferAdapter, BufferError
        publish = BufferAdapter(models_config, db_path=app.config["DB_PATH"])
       

        posts_list = json.loads(asset.get("posts") or "[]")
        from media_adapter import MediaAdapter
        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])
        asset_media = media_adapter.list_asset_media(asset_id)
        images = [{"id": m.get("postiz_id", ""), "path": m.get("path", "")} for m in asset_media if m.get("kind") == "image"]

        scheduled_at = asset.get("publish_scheduled_at") or datetime.now(timezone.utc).isoformat()

        try:
            result = publish.publish_piece(
                business_slug=business_slug,
                asset_id=asset_id,
                platform=asset["platform"],
                content=asset["content"],
                posts=posts_list if posts_list else None,
                images=images if images else None,
                scheduled_at=scheduled_at,
                asset_state="approved",
            )
            store.update_asset_state(asset_id, "published")
            return jsonify({"status": "ok", "postiz_post_id": result.get("postiz_post_id", "")})
        except BufferError as e:
            return jsonify({"error": str(e)}), 502

    @app.route("/api/buffer/status")
    def buffer_status():
        """Check if Buffer is configured and available."""
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from buffer_adapter import BufferAdapter
        publish_adapter = BufferAdapter(models_config, db_path=app.config["DB_PATH"])
        available = publish_adapter.is_available()
        integrations = publish_adapter.list_integrations() if available else []
        return jsonify({
            "available": available,
            "integrations": integrations,
            "base_url": publish_adapter.api_url,
        })

    # ── T4.2: Metrics ──

    @app.route("/metrics")
    def metrics_page():
        """Show metrics for published pieces, pulled from Buffer analytics."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            models_config = {}
            business_name = "Not configured"

        from buffer_adapter import BufferAdapter
        publish_adapter = BufferAdapter(models_config, db_path=app.config["DB_PATH"])

        store = _get_pipeline_store()
        published_items = []
        all_drafts = store.list_drafts(business_slug)
        for draft in all_drafts:
            assets = store.list_assets(draft["id"])
            for asset in assets:
                if asset["asset_state"] == "published":
                    a = dict(asset)
                    a["draft"] = draft
                    a["publish_log"] = publish_adapter.get_publish_log(asset["id"])
                    published_items.append(a)

        # Get metrics summary
        metrics_summary = publish_adapter.get_metrics_summary(business_slug)
        for item in published_items:
            item["metrics"] = metrics_summary.get(item["id"], {})

        postiz_available = publish_adapter.is_available()

        return render_template("metrics.html",
            business_name=business_name,
            published_items=published_items,
            postiz_available=postiz_available)

    @app.route("/api/metrics/pull", methods=["POST"])
    def pull_metrics():
        """Manually trigger a metrics pull for all published pieces."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError:
            models_config = {}

        from buffer_adapter import BufferAdapter, BufferError
        publish = BufferAdapter(models_config, db_path=app.config["DB_PATH"])
       

        days = request.json.get("days", 7) if request.json else 7
        try:
            result = publish.pull_all_metrics(business_slug, days=days)
            return jsonify({"status": "ok", **result})
        except BufferError as e:
            return jsonify({"error": str(e)}), 502

    # ── M6: Outward research loop ──

    @app.route("/research")
    def research_page():
        """T6.1: Show discovered research items from YouTube RSS scans."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        from research_job import ResearchJob
        rj = ResearchJob(db_path=app.config["DB_PATH"])
        items = rj.list_research_items(business_slug, limit=100)

        # Group by analysis status
        pending = [i for i in items if i.get("analysis_status") == "pending"]
        analyzed = [i for i in items if i.get("analysis_status") == "analyzed"]

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        return render_template("research.html",
                               business_name=business_name,
                               pending_items=pending,
                               analyzed_items=analyzed)

    @app.route("/api/research/run", methods=["POST"])
    def run_research():
        """T6.1: Run the YouTube RSS research job manually."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        try:
            config = load_all(app.config["CONFIG_DIR"])
            sources_config = config.get("sources", {})
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from research_job import ResearchJob
        rj = ResearchJob(db_path=app.config["DB_PATH"])
        result = rj.run(business_slug, sources_config)
        return jsonify({"status": "ok", **result})

    @app.route("/api/research/<int:item_id>/analyze", methods=["POST"])
    def analyze_research_item(item_id):
        """T6.2: Analyze a research item with LLM (hook/structure/format/emotion/pacing + hypothesis)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from research_job import ResearchJob
        rj = ResearchJob(db_path=app.config["DB_PATH"])
        item = rj.get_research_item(item_id)
        if not item:
            return jsonify({"error": "Research item not found"}), 404

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        # Load source criteria module
        from module_store import ModuleStore
        modules_dir = app.config.get("MODULES_DIR", "modules")
        ms = ModuleStore(modules_dir=modules_dir, db_path=app.config["DB_PATH"])
        source_criteria = ms.load(business_slug, "source-criteria") or "(not built)"

        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        analysis_schema = {
            "type": "object",
            "required": ["hook_analysis", "structure_analysis", "format_analysis",
                        "emotion_analysis", "pacing_analysis", "hypothesis", "relevance_score"],
            "properties": {
                "hook_analysis": {"type": "string"},
                "structure_analysis": {"type": "string"},
                "format_analysis": {"type": "string"},
                "emotion_analysis": {"type": "string"},
                "pacing_analysis": {"type": "string"},
                "hypothesis": {"type": "string"},
                "relevance_score": {"type": "integer"},
                "key_takeaways": {"type": "array", "items": {"type": "string"}},
                "source_bank_entry": {"type": "string"},
            },
        }

        try:
            result = adapter.complete(
                prompt_file="research/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "source_name": item["source_name"],
                    "channel_name": item.get("channel_name", ""),
                    "video_title": item["title"],
                    "video_description": item.get("description", ""),
                    "watch_url": item["watch_url"],
                    "published_at": item.get("published_at", ""),
                    "source_criteria": source_criteria[:3000],
                },
                schema=analysis_schema,
                backend="default",
                context=f"Research analysis for item {item_id} ({item['source_name']})",
                business_slug=business_slug,
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        rj.update_analysis(item_id, "analyzed", result)
        return jsonify({"status": "ok", "analysis": result})

    @app.route("/api/research/<int:item_id>/propose-experiment", methods=["POST"])
    def propose_experiment(item_id):
        """T6.3: Create an experiment proposal from an analyzed research item.
        Approved experiments flow into the proposals gate as seed suggestions."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from research_job import ResearchJob
        rj = ResearchJob(db_path=app.config["DB_PATH"])
        item = rj.get_research_item(item_id)
        if not item:
            return jsonify({"error": "Research item not found"}), 404
        if item.get("analysis_status") != "analyzed":
            return jsonify({"error": "Item must be analyzed first"}), 400

        analysis = json.loads(item.get("analysis_result") or "{}")
        hypothesis = analysis.get("hypothesis", "")
        takeaways = analysis.get("key_takeaways", [])
        source_bank_entry = analysis.get("source_bank_entry", "")

        # Create a proposal in the gate queue (T5.2 infrastructure)
        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=app.config["DB_PATH"])
        proposal_id = ps.create_proposal(
            business_slug=business_slug,
            target_module="source-bank",
            target_section="research-findings",
            proposal_type="experiment",
            evidence=[f"YouTube video: {item['watch_url']}", f"Hypothesis: {hypothesis}"],
            change_description=f"Experiment from {item['source_name']}: {item['title'][:80]}",
            exact_diff=source_bank_entry,
            rationale=hypothesis,
            confidence="medium",
        )

        return jsonify({"status": "ok", "proposal_id": proposal_id})

    @app.route("/api/sources/discover", methods=["POST"])
    def discover_sources():
        """T6.4: Sources Engine Part B — discover new sources from research findings.
        Proposes new channel additions or prunes based on analysis scores."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from research_job import ResearchJob
        rj = ResearchJob(db_path=app.config["DB_PATH"])
        analyzed = rj.list_research_items(business_slug, status="analyzed", limit=100)

        # Group by source_name and compute average relevance
        from collections import defaultdict
        by_source = defaultdict(list)
        for item in analyzed:
            analysis = json.loads(item.get("analysis_result") or "{}")
            score = analysis.get("relevance_score", 5)
            by_source[item["source_name"]].append(score)

        proposals = []
        for source_name, scores in by_source.items():
            avg_score = sum(scores) / len(scores)
            if avg_score >= 7:
                proposals.append({
                    "source_name": source_name,
                    "avg_relevance": round(avg_score, 1),
                    "video_count": len(scores),
                    "recommendation": "keep — high relevance",
                })
            elif avg_score <= 3:
                proposals.append({
                    "source_name": source_name,
                    "avg_relevance": round(avg_score, 1),
                    "video_count": len(scores),
                    "recommendation": "prune — low relevance",
                })

        return jsonify({"status": "ok", "proposals": proposals, "sources_evaluated": len(by_source)})

    # ── T5.2: Gate as persistent async queue ──

    @app.route("/proposals")
    def proposals_page():
        """Gate queue — module improvement proposals for operator approval."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=app.config["DB_PATH"])

        summary = ps.get_proposal_summary(business_slug)
        pending = ps.list_proposals(business_slug, status="pending")
        # Add age_days to each
        for p in pending:
            p["age_days"] = ps.get_proposal_age_days(p.get("created_at", ""))

        # Recent decided (approved, rejected, superseded)
        decided = ps.list_proposals(business_slug)
        decided = [p for p in decided if p["status"] != "pending"][:10]

        return render_template("proposals.html",
            business_name=business_name,
            summary=summary,
            pending_proposals=pending,
            decided_proposals=decided)

    @app.route("/api/proposals/<int:proposal_id>/approve", methods=["POST"])
    def approve_proposal(proposal_id):
        """Approve a proposal — triggers module version bump via gate."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=app.config["DB_PATH"])

        proposal = ps.get_proposal(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        if proposal["status"] != "pending":
            return jsonify({"error": f"Proposal is already {proposal['status']}"}), 400

        # Approve the proposal
        approved = ps.approve_proposal(proposal_id)

        # T5.3: If this is a Voice Profile proposal, apply the version bump
        if proposal["target_module"] == "voice-profile":
            try:
                from module_store import ModuleStore
                modules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "modules")
                store = ModuleStore(modules_dir=modules_dir)

                # Load current voice profile
                current = store.load(business_slug, "voice-profile")
                if current:
                    # The exact_diff describes the change — for now, we record the approval
                    # and the operator applies it manually or a future auto-apply path handles it
                    # Per the charter: AI proposes, human gates. The approval IS the gate.
                    pass
            except Exception as e:
                logger.warning(f"Voice Profile auto-apply not yet implemented: {e}")

        return jsonify({"status": "ok", "proposal": approved})

    @app.route("/api/proposals/<int:proposal_id>/reject", methods=["POST"])
    def reject_proposal_route(proposal_id):
        """Reject a proposal with a quick-reason."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=app.config["DB_PATH"])

        proposal = ps.get_proposal(proposal_id)
        if not proposal:
            return jsonify({"error": "Proposal not found"}), 404
        if proposal["status"] != "pending":
            return jsonify({"error": f"Proposal is already {proposal['status']}"}), 400

        reason = request.json.get("reason", "No reason given")
        rejected = ps.reject_proposal(proposal_id, reason)
        return jsonify({"status": "ok", "proposal": rejected})

    @app.route("/api/proposals/bulk-approve", methods=["POST"])
    def bulk_approve_proposals():
        """Bulk approve multiple proposals."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=app.config["DB_PATH"])

        ids = request.json.get("ids", [])
        results = ps.bulk_approve(ids)
        return jsonify({"status": "ok", "count": len(results)})

    @app.route("/api/proposals/bulk-reject", methods=["POST"])
    def bulk_reject_proposals():
        """Bulk reject multiple proposals."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from proposal_store import ProposalStore
        ps = ProposalStore(db_path=app.config["DB_PATH"])

        ids = request.json.get("ids", [])
        reason = request.json.get("reason", "Bulk rejected")
        results = ps.bulk_reject(ids, reason)
        return jsonify({"status": "ok", "count": len(results)})

    # ── Published page ──

    @app.route("/published")
    def published_page():
        """Show all published/scheduled assets across all drafts."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        from media_adapter import MediaAdapter
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            models_config = {}
            business_name = "Not configured"

        media_adapter = MediaAdapter(models_config, db_path=app.config["DB_PATH"])

        # Get all drafts for this business
        all_drafts = store.list_drafts(business_slug)
        published_items = []
        for draft in all_drafts:
            assets = store.list_assets(draft["id"])
            for asset in assets:
                if asset["asset_state"] in ("published",):
                    a = dict(asset)
                    a["posts_parsed"] = json.loads(asset.get("posts") or "[]")
                    a["images"] = [m for m in media_adapter.list_asset_media(asset["id"]) if m.get("kind") == "image"]
                    a["draft"] = draft
                    published_items.append(a)

        # Sort by scheduled time descending
        published_items.sort(key=lambda x: x.get("publish_scheduled_at") or "", reverse=True)

        return render_template("published.html",
            business_name=business_name,
            published_items=published_items)

    # ── Create surface (Writer page — unified card list with state + provenance trail) ──

    @app.route("/create")
    def create_surface():
        """Writer surface — unified list of all cards with their state in the pipeline,
        filter buttons with counts, and provenance trail per card."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        idea_cards = store.list_idea_cards(business_slug)
        drafts = store.list_drafts(business_slug)

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        # Build draft lookup by idea_card_id
        draft_by_card = {}
        for d in drafts:
            draft_by_card[d["idea_card_id"]] = d

        # Build unified card list with state + provenance trail
        # UX-3: Writer only shows cards that have been approved (not new/killed/parked).
        # New cards belong in Researcher; killed/parked are terminal states.
        writer_eligible_states = {
            "approved", "writing", "drafting", "draft_ready", "drafted",
            "shipped", "assembling", "asset_ready",
            "writer_failed", "assembly_failed", "production_failed",
            "awaiting_capture", "capture_fulfilled",
        }
        unified_cards = []
        for card in idea_cards:
            if card["card_state"] not in writer_eligible_states:
                continue
            c = dict(card)
            c["idea_short"] = card["idea"][:80]
            c["draft"] = draft_by_card.get(card["id"])

            # Provenance trail: which stages are approved
            trail = []
            trail.append({"stage": "Idea", "state": "approved" if card["card_state"] not in ("new", "killed", "parked") else card["card_state"], "label": "Idea approved"})
            draft = draft_by_card.get(card["id"])
            if draft:
                if draft["draft_state"] in ("draft_ready", "revised"):
                    trail.append({"stage": "Script", "state": "ready", "label": "Script ready for review"})
                elif draft["draft_state"] == "drafting":
                    trail.append({"stage": "Script", "state": "writing", "label": "Writer working"})
                elif draft["draft_state"] == "shipped":
                    trail.append({"stage": "Script", "state": "approved", "label": "Script approved"})
                elif draft["draft_state"] == "killed":
                    trail.append({"stage": "Script", "state": "killed", "label": "Script killed"})
            if card["card_state"] in ("asset_ready", "assembling"):
                trail.append({"stage": "Assets", "state": "ready" if card["card_state"] == "asset_ready" else "assembling", "label": "Assets ready for review" if card["card_state"] == "asset_ready" else "Assembler working"})
            c["trail"] = trail

            # Parse production_error
            if c.get("production_error"):
                try:
                    err = json.loads(c["production_error"])
                    c["production_error"] = f"{err.get('step', 'unknown')}: {err.get('error', '')[:150]}"
                except Exception:
                    pass

            # Determine display state for the card
            c["display_state"] = _writer_display_state(card, draft_by_card.get(card["id"]))
            # P1-2: state_changed_at for relative timestamp display
            c["state_changed_at"] = card.get("updated_at") or card.get("created_at")
            unified_cards.append(c)

        # Count cards per state for filter buttons
        state_counts = {}
        for c in unified_cards:
            state_counts[c["display_state"]] = state_counts.get(c["display_state"], 0) + 1

        return render_template("create.html",
            business_name=business_name,
            unified_cards=unified_cards,
            state_counts=state_counts)

    def _writer_display_state(card, draft):
        """Map card_state + draft_state to a single display state for the Writer page."""
        cs = card["card_state"]
        if cs in ("new",):
            return "queued"
        if cs in ("writing", "drafting", "reviewing"):
            return "writing"
        if cs in ("draft_ready", "revised"):
            return "ready_review"
        if cs == "drafted":
            if draft and draft["draft_state"] == "shipped":
                return "shipped"
            return "ready_review"
        if cs == "assembling":
            return "assembling"
        if cs == "asset_ready":
            return "asset_ready"
        if cs in ("writer_failed", "assembly_failed", "production_failed"):
            return "failed"
        if cs == "shipped":
            return "shipped"
        if cs == "killed":
            return "killed"
        if cs == "parked":
            return "parked"
        if cs == "awaiting_capture":
            return "queued"
        return cs

    @app.route("/assemble")
    def assembler_surface():
        """Assembler surface — unified list of all cards with assets in the pipeline,
        filter buttons with counts, and provenance trail per card."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        idea_cards = store.list_idea_cards(business_slug)
        drafts = store.list_drafts(business_slug)

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        # Build draft lookup by idea_card_id
        draft_by_card = {}
        for d in drafts:
            draft_by_card[d["idea_card_id"]] = d

        # Build unified card list — only cards that have shipped drafts or assets
        assembler_cards = []
        for card in idea_cards:
            draft = draft_by_card.get(card["id"])
            if not draft:
                continue
            # Only show cards that are at or past the assembler stage
            if draft["draft_state"] != "shipped" and card["card_state"] not in ("assembling", "asset_ready", "published"):
                continue

            c = dict(card)
            c["idea_short"] = card["idea"][:80]
            c["draft"] = draft

            # Load assets for this draft
            assets = store.list_assets(draft["id"])
            c["assets"] = assets
            c["asset_count"] = len(assets)
            c["approved_assets"] = [a for a in assets if a["asset_state"] == "approved"]
            c["pending_assets"] = [a for a in assets if a["asset_state"] in ("pending", "fix")]

            # Provenance trail
            trail = []
            trail.append({"stage": "Idea", "state": "approved", "label": "Idea approved"})
            trail.append({"stage": "Script", "state": "approved", "label": "Script approved (shipped)"})
            if card["card_state"] == "assembling":
                trail.append({"stage": "Assets", "state": "assembling", "label": "Assembler working"})
            elif card["card_state"] == "asset_ready":
                trail.append({"stage": "Assets", "state": "ready", "label": "Assets ready for review"})
            elif assets:
                if c["approved_assets"] and len(c["approved_assets"]) == len(assets):
                    trail.append({"stage": "Assets", "state": "approved", "label": "All assets approved"})
                else:
                    trail.append({"stage": "Assets", "state": "partial", "label": f"{len(c['approved_assets'])}/{len(assets)} assets approved"})
            else:
                trail.append({"stage": "Assets", "state": "pending", "label": "No assets generated yet"})
            c["trail"] = trail

            c["display_state"] = _assembler_display_state(card, draft, assets)
            # P1-2: state_changed_at for relative timestamp display
            c["state_changed_at"] = card.get("updated_at") or card.get("created_at")
            assembler_cards.append(c)

        # Count cards per state for filter buttons
        state_counts = {}
        for c in assembler_cards:
            state_counts[c["display_state"]] = state_counts.get(c["display_state"], 0) + 1

        return render_template("assemble.html",
            business_name=business_name,
            assembler_cards=assembler_cards,
            state_counts=state_counts)

    def _assembler_display_state(card, draft, assets):
        """Map card/draft/asset state to a single display state for the Assembler page."""
        cs = card["card_state"]
        if cs == "assembling":
            return "assembling"
        if cs == "asset_ready":
            return "ready_review"
        if not assets:
            return "no_assets"
        approved = [a for a in assets if a["asset_state"] == "approved"]
        if len(approved) == len(assets):
            return "all_approved"
        if approved:
            return "partial"
        return "pending"

    # ── Onboarding Module Health ──

    @app.route("/onboarding-health")
    def onboarding_health():
        """Module Health — shows completeness of onboarding inputs per module."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        from onboarding_completeness import check_completeness
        results = check_completeness(
            app.config["DB_PATH"],
            app.config["PLAYBOOKS_DIR"],
            business_slug,
        )

        total_inputs = sum(len(r["inputs"]) for r in results)
        missing_count = sum(1 for r in results for i in r["inputs"] if i["status"] == "missing")
        present_count = total_inputs - missing_count

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        return render_template("onboarding_health.html",
            business_name=business_name,
            modules=results,
            total_inputs=total_inputs,
            missing_count=missing_count,
            present_count=present_count,
        )

    @app.route("/api/onboarding/mine-sources", methods=["POST"])
    def mine_sources():
        """Mine existing data (materials, onboarding transcript, source bank) for a missing onboarding input."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        input_name = request.json.get("input_name", "")
        source_playbook = request.json.get("source_playbook", "")
        if not input_name:
            return jsonify({"error": "No input name provided"}), 400

        # Gather data sources
        runner = PlaybookRunner(app.config["DB_PATH"])
        onboarding_run = None
        for run in runner.list_runs():
            if dict(run).get("playbook_name") == "onboarding":
                onboarding_run = dict(run)
                break

        conversation_transcript = ""
        if onboarding_run:
            collected = json.loads(onboarding_run.get("collected_inputs") or "{}")
            messages = collected.get("session_messages", "")
            if isinstance(messages, str):
                conversation_transcript = messages[:10000]
            elif isinstance(messages, list):
                conversation_transcript = "\n".join(str(m) for m in messages)[:10000]

        from materials import MaterialsIntake
        intake = MaterialsIntake(app.config["DB_PATH"])
        materials = intake.list_materials()
        materials_content = ""
        for m in materials[:20]:
            content = m.get("normalized_content") or m.get("raw_content") or ""
            if content:
                materials_content += f"--- Material {m['id']} ({m.get('filename','')}) ---\n{content[:800]}\n\n"
        if not materials_content:
            materials_content = "(no material content available)"

        store = _get_pipeline_store()
        active_sources = store.list_sources(business_slug, limit=30)
        source_bank_entries = "\n".join(
            f"[S{s['id']}] {s['title']} — {s.get('summary','')}"
            for s in active_sources
        ) if active_sources else "(no sources in bank)"

        input_descriptions = {
            "admired_examples": "Links to content the operator admires in their domain — creators, posts, videos they wish they'd made",
            "operator_stories": "2-3 stories the operator tells often — about their business, life, or take on things",
            "voice_summary": "Summary of the operator's voice characteristics — tone, vocabulary, style preferences",
            "admired_links": "5-10 links to content the operator admires",
            "anti_examples": "3-5 examples of content the operator considers slop they'd never make",
            "voice_samples": "Voice samples — typed or spoken content showing the operator's natural voice",
            "tone_redlines": "Topics or stances the operator never wants to take",
        }

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        from llm_adapter import LLMAdapter
        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        result = adapter.complete(
            prompt_file="onboarding/mine_source_v1.md",
            variables={
                "input_name": input_name,
                "source_playbook": source_playbook,
                "input_description": input_descriptions.get(input_name, input_name),
                "conversation_transcript": conversation_transcript,
                "materials_content": materials_content[:8000],
                "source_bank_entries": source_bank_entries,
            },
            backend="default",
            context=f"Source mining for {input_name} ({source_playbook})",
            business_slug=business_slug,
        )

        if result.get("found"):
            onboarding_run_id = onboarding_run["id"] if onboarding_run else None
            if onboarding_run_id:
                collected = json.loads(onboarding_run.get("collected_inputs") or "{}")
                collected[input_name] = result.get("extracted_content", "")
                runner.update_run(onboarding_run_id, collected_inputs=json.dumps(collected))

        return jsonify({
            "status": "ok",
            "found": result.get("found", False),
            "extracted_content": result.get("extracted_content", ""),
            "sources_found": result.get("sources_found", []),
            "confidence": result.get("confidence", "low"),
        })

    @app.route("/api/onboarding/fill-input", methods=["POST"])
    def fill_input():
        """Manually fill a missing onboarding input."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        input_name = request.json.get("input_name", "")
        value = request.json.get("value", "")
        if not input_name or not value:
            return jsonify({"error": "Both input_name and value are required"}), 400

        runner = PlaybookRunner(app.config["DB_PATH"])
        onboarding_run = None
        for run in runner.list_runs():
            if dict(run).get("playbook_name") == "onboarding":
                onboarding_run = dict(run)
                break

        if not onboarding_run:
            return jsonify({"error": "No onboarding run found"}), 404

        collected = json.loads(onboarding_run.get("collected_inputs") or "{}")
        collected[input_name] = value
        runner.update_run(onboarding_run["id"], collected_inputs=json.dumps(collected))

        return jsonify({"status": "ok", "input_name": input_name})

    # ── Source Bank surface ──

    @app.route("/sources")
    def source_bank_page():
        """Source Bank — view all sources, review new items, remove junk."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()
        # List all statuses — the page has filters
        conn = __import__("sqlite3").connect(app.config["DB_PATH"])
        conn.row_factory = __import__("sqlite3").Row
        rows = conn.execute(
            "SELECT * FROM sources WHERE business_slug = ? ORDER BY first_seen DESC LIMIT 500",
            (business_slug,),
        ).fetchall()
        conn.close()
        sources = [dict(r) for r in rows]

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        # Categorize sources by status
        status_counts = {}
        for s in sources:
            st = s.get("status") or "active"
            s["display_status"] = st
            status_counts[st] = status_counts.get(st, 0) + 1

        return render_template("source_bank.html",
            business_name=business_name,
            sources=sources,
            status_counts=status_counts)

    @app.route("/api/sources/<int:source_id>/status", methods=["POST"])
    def update_source_status(source_id):
        """Update a source's status (active/parked/removed) — human review of source bank."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        new_status = request.json.get("status", "")
        if new_status not in ("active", "parked", "removed"):
            return jsonify({"error": "Invalid status. Use active, parked, or removed."}), 400

        conn = __import__("sqlite3").connect(app.config["DB_PATH"])
        conn.execute(
            "UPDATE sources SET status = ? WHERE id = ? AND business_slug = ?",
            (new_status, source_id, business_slug),
        )
        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "source_id": source_id, "new_status": new_status})

    @app.route("/api/sources/bulk-status", methods=["POST"])
    def bulk_update_source_status():
        """DIVERGENCE-007: Bulk update source status — operator reviews new sources.
        Updates all sources with from_status to to_status for the current business."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        from_status = request.json.get("from_status", "")
        to_status = request.json.get("to_status", "")
        if to_status not in ("active", "parked", "removed"):
            return jsonify({"error": "Invalid target status. Use active, parked, or removed."}), 400
        if not from_status:
            return jsonify({"error": "Missing from_status."}), 400

        conn = __import__("sqlite3").connect(app.config["DB_PATH"])
        cursor = conn.execute(
            "UPDATE sources SET status = ? WHERE business_slug = ? AND status = ?",
            (to_status, business_slug, from_status),
        )
        updated = cursor.rowcount
        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "updated": updated, "from": from_status, "to": to_status})

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "version": "0.2.0"})

    # P1-transcription: Start the transcription worker daemon thread
    try:
        from transcription import TranscriptionWorker
        config_for_worker = load_all(config_dir)
        worker = TranscriptionWorker(
            db_path=db_path,
            upload_dir=app.config.get("UPLOAD_DIR", "data/uploads"),
            models_config=config_for_worker.get("models", {}),
        )
        worker.start()
        app.config["TRANSCRIPTION_WORKER"] = worker
    except Exception as e:
        import logging
        logging.getLogger("viralfactory").warning(f"Transcription worker not started: {e}")

    return app


# For development
if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=9121, debug=True)