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

    # --- Routes ---

    @app.route("/")
    def index():
        """Dashboard — shows system status and links to surfaces."""
        try:
            config = load_all(config_dir)
            business_name = config["business"]["business"]["name"]
            business_slug = config["business"]["business"]["slug"]
        except ConfigError:
            business_name = "Not configured"
            business_slug = None

        # Get playbook runs if we have a slug — only show the latest per playbook
        runs = []
        if business_slug:
            runner = PlaybookRunner(db_path)
            all_runs = runner.list_runs(business_slug)
            # Dedupe: keep only the latest run per playbook name
            seen = set()
            for r in all_runs:
                pb_name = r["playbook_name"]
                if pb_name not in seen:
                    seen.add(pb_name)
                    runs.append(r)

        return render_template("index.html",
            business_name=business_name,
            business_slug=business_slug,
            runs=runs,
        )

    @app.route("/onboard")
    def onboard():
        """Onboarding surface — list playbooks sorted by run_order with locked/completed state."""
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

    def _build_materials_summary(run_id):
        """Build a summary of uploaded materials for the converse prompt.

        Lists each material with filename, type, and an excerpt of content.
        Caps total size to ~6,000 chars so it fits within the LLM context window.
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
            # Don't include binary garbage
            if raw and any(ord(c) < 9 for c in raw[:50]):
                excerpt = "(binary content — not text-extractable)"
            elif raw:
                excerpt = raw[:PER_MATERIAL_CAP]
                if len(raw) > PER_MATERIAL_CAP:
                    excerpt += "... [truncated]"
            else:
                excerpt = "(empty)"

            entry = f"- {filename} ({mtype}): {excerpt}"
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

    def _build_readback(playbook_name, profile):
        """Build a plain-language readback for the operator based on playbook type."""
        if playbook_name == "business-profile-intake":
            return _build_business_readback(profile)
        # Generic readback: just format the key fields
        lines = ["Here's what I put together:", ""]
        if isinstance(profile, dict):
            for key, val in profile.items():
                if isinstance(val, str) and len(val) < 500:
                    lines.append(f"**{key.replace('_', ' ').title()}:** {val}")
                elif isinstance(val, list):
                    lines.append(f"**{key.replace('_', ' ').title()}:**")
                    for item in val[:10]:
                        if isinstance(item, str):
                            lines.append(f"  • {item}")
                        elif isinstance(item, dict):
                            name = item.get("name", item.get("subject", item.get("format", str(item)[:60])))
                            lines.append(f"  • {name}")
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

        # Map playbook name → analysis prompt file, schema, and output key
        from module_store import (
            BUSINESS_PROFILE_SCHEMA, SOURCE_CRITERIA_SCHEMA, VIRAL_PATTERNS_SCHEMA,
            AUDIENCE_INSIGHTS_SCHEMA, STORY_FRAMEWORKS_SCHEMA, FORMAT_GUIDE_SCHEMA,
            VISUAL_STYLE_SCHEMA,
        )

        playbook_map = {
            "business-profile-intake": ("business_profile/analyze_v1.md", BUSINESS_PROFILE_SCHEMA, "analysis"),
            "sources-engine": ("sources_engine/analyze_v1.md", SOURCE_CRITERIA_SCHEMA, "criteria"),
            "viral-patterns-starter": ("viral_patterns/analyze_v1.md", VIRAL_PATTERNS_SCHEMA, "patterns"),
            "audience-insights-builder": ("audience_insights/analyze_v1.md", AUDIENCE_INSIGHTS_SCHEMA, "insights"),
            "story-frameworks-starter": ("story_frameworks/analyze_v1.md", STORY_FRAMEWORKS_SCHEMA, "frameworks"),
            "format-guide-starter": ("format_guide/analyze_v1.md", FORMAT_GUIDE_SCHEMA, "guide"),
            "visual-style-intake": ("visual_style/analyze_v1.md", VISUAL_STYLE_SCHEMA, "style_guide"),
        }

        pb_name = run["playbook_name"]
        prompt_file, schema, output_key = playbook_map.get(
            pb_name, ("business_profile/analyze_v1.md", BUSINESS_PROFILE_SCHEMA, "analysis")
        )

        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        # Build variables — start with the common ones, add playbook-specific ones
        variables = {
            "business_name": business["business"]["name"],
            "existing_info": business["business"].get("description", ""),
            "qa_transcript": transcript[:8000],
            "subjects": ", ".join(business.get("subjects", [])),
            "audience_description": business.get("audience_description", ""),
        }

        # Add playbook-specific variables from collected inputs
        if pb_name == "sources-engine":
            variables["seed_sources"] = _format_seed_sources(collected)
            variables["anti_examples"] = _format_anti_examples(collected)
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
        elif pb_name == "format-guide-starter":
            platforms_text = ", ".join(f"{p['name']} ({p.get('handle', '')})" for p in business.get("platforms", []))
            variables["platforms"] = platforms_text
            variables["format_observations"] = collected.get("format_observations", "(none)")
            variables["platform_norms"] = collected.get("platform_norms", "(use general knowledge)")
        elif pb_name == "visual-style-intake":
            platforms_text = ", ".join(f"{p['name']} ({p.get('handle', '')})" for p in business.get("platforms", []))
            variables["platforms"] = platforms_text
            variables["brand_assets"] = collected.get("brand_assets", "(none)")
            variables["visual_examples"] = collected.get("visual_examples", "(none)")
            variables["shot_library_summary"] = "(see uploaded files)"

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
        """Library surface — read-only browse of modules + version history."""
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
                # Extract schema marker
                schema_name = None
                if content:
                    import re as _re
                    m = _re.search(r'Schema:\s*(\w+)', content)
                    schema_name = m.group(1) if m else None
                modules.append({
                    "name": name,
                    "schema": schema_name,
                    "version_count": len(versions) + 1,  # +1 for current
                    "versions": [{"version": v["version"], "timestamp": v["timestamp"]} for v in versions],
                    "preview": content[:500] if content else "",
                })

        return render_template("library.html", business_slug=business_slug, modules=modules)

    @app.route("/api/library/<business_slug>/<module_name>")
    def api_library_module(business_slug, module_name):
        """API: get a specific module's content + version history."""
        from module_store import ModuleStore
        store = ModuleStore(modules_dir="modules", db_path=app.config["DB_PATH"])
        content = store.load(business_slug, module_name)
        if not content:
            return jsonify({"error": "Module not found"}), 404
        versions = store.list_versions(business_slug, module_name)
        return jsonify({
            "module": module_name,
            "business_slug": business_slug,
            "content": content,
            "versions": [{"version": v["version"], "timestamp": v["timestamp"], "filename": v["filename"]} for v in versions],
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

        try:
            result = adapter.complete(
                prompt_file="story_frameworks/analyze_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
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
            "awaiting": ["awaiting_capture"],
            "approved": ["approved", "capture_fulfilled"],
            "parked": ["parked"],
            "killed": ["killed"],
            "all": None,
        }
        states = state_map.get(active_tab, ["new"])

        if states:
            cards_raw = store.list_idea_cards_by_states(business_slug, states)
        else:
            cards_raw = store.list_idea_cards(business_slug)

        # Enrich cards for display
        cards = []
        for c in cards_raw:
            card = dict(c)
            card["hook_options"] = json.loads(c.get("hook_options") or "[]")
            treatment = json.loads(c.get("treatment") or "{}")
            card["treatment"] = treatment
            card["evidence_links"] = json.loads(c.get("evidence_links") or "[]")

            # Compact treatment line: scope · format · capture flag
            scope = treatment.get("scope", {})
            fmt = treatment.get("format", {})
            capture = treatment.get("capture_required", [])
            compact = []
            compact.append(f"Scope: {scope.get('type', '?')}")
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

            cards.append(card)

        # Count cards per state for tab badges
        all_cards = store.list_idea_cards(business_slug)
        counts = {}
        for c in all_cards:
            s = c["card_state"]
            counts[s] = counts.get(s, 0) + 1
        counts_display = {
            "new": counts.get("new", 0),
            "awaiting_capture": counts.get("awaiting_capture", 0),
            "approved": counts.get("approved", 0) + counts.get("capture_fulfilled", 0),
            "parked": counts.get("parked", 0),
            "killed": counts.get("killed", 0),
            "all": len(all_cards),
        }

        return render_template("ideas.html",
            business_name=business_name, business_slug=business_slug,
            cards=cards, active_tab=active_tab, counts=counts_display)

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
        """Generate an idea card from a human seed using the LLM."""
        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return {"status": "error", "error": f"Config error: {e}"}

        modules = _load_all_modules(business_slug)

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import IDEA_CARD_SCHEMA

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="ideas/generate_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "origin_type": origin,
                    "source_material": f"Operator seed: {seed}",
                    "viral_patterns": modules.get("viral-patterns", "(not built)")[:2000],
                    "audience_insights": modules.get("audience-insights", "(not built)")[:2000],
                    "story_frameworks": modules.get("story-frameworks", "(not built)")[:2000],
                    "format_guide": modules.get("format-guide", "(not built)")[:2000],
                    "num_cards": "1",
                },
                schema=IDEA_CARD_SCHEMA,
                backend="default",
                context=f"Idea card generation from seed ({origin})",
                business_slug=business_slug,
            )
        except (LLMAdapterError, Exception) as e:
            return {"status": "error", "error": str(e)}

        store = _get_pipeline_store()
        cards_created = []
        for card_data in result.get("cards", []):
            treatment = card_data.get("treatment", {})
            card_id = store.create_idea_card(
                business_slug=business_slug,
                idea=card_data["idea"],
                hook_options=card_data.get("hook_options", []),
                treatment=treatment,
                origin=origin,
                evidence_links=card_data.get("evidence_links", []),
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

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        modules = _load_all_modules(business_slug)

        # Build source material from source-criteria module + sources config
        source_material = modules.get("source-criteria", "(not built)")
        try:
            sources_config = config.get("sources", {})
            if sources_config:
                source_material += "\n\n## Configured monitoring\n"
                for feed in sources_config.get("feeds", [])[:5]:
                    source_material += f"- {feed.get('name', '')}: {feed.get('url', '')}\n"
                for ch in sources_config.get("channels", [])[:5]:
                    source_material += f"- {ch.get('name', '')} ({ch.get('platform', '')}/{ch.get('handle', '')})\n"
        except Exception:
            pass

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import IDEA_CARD_SCHEMA

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="ideas/generate_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "subjects": ", ".join(business.get("subjects", [])),
                    "audience_description": business.get("audience_description", ""),
                    "origin_type": "ai_originated",
                    "source_material": source_material[:4000],
                    "viral_patterns": modules.get("viral-patterns", "(not built)")[:2000],
                    "audience_insights": modules.get("audience-insights", "(not built)")[:2000],
                    "story_frameworks": modules.get("story-frameworks", "(not built)")[:2000],
                    "format_guide": modules.get("format-guide", "(not built)")[:2000],
                    "num_cards": str(num_cards),
                },
                schema=IDEA_CARD_SCHEMA,
                backend="default",
                context=f"AI idea card generation ({num_cards} cards)",
                business_slug=business_slug,
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        store = _get_pipeline_store()
        cards_created = []
        for card_data in result.get("cards", []):
            treatment = card_data.get("treatment", {})
            card_id = store.create_idea_card(
                business_slug=business_slug,
                idea=card_data["idea"],
                hook_options=card_data.get("hook_options", []),
                treatment=treatment,
                origin="ai_originated",
                evidence_links=card_data.get("evidence_links", []),
            )
            cards_created.append(card_id)

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
            # Check if card has capture tasks
            treatment = json.loads(card.get("treatment") or "{}")
            capture_required = treatment.get("capture_required", [])
            if capture_required:
                new_state = "awaiting_capture"
            else:
                new_state = "approved"

            # T3.10: Series spawning — if scope is series_of_n, spawn child cards
            scope = treatment.get("scope", {})
            if scope.get("type") == "series_of_n" and not card.get("parent_id"):
                n = scope.get("n", 1)
                cadence = scope.get("cadence", "")
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
                    # Children start as 'approved' (parent was approved)
                    store.update_card_state(child_id, "approved")

            # T3.11: Experimental format debut — auto-write Format Guide entry
            fmt = treatment.get("format", {})
            if fmt.get("experimental") and fmt.get("format_spec"):
                _debut_experimental_format(business_slug, card_id, fmt, treatment)

            store.update_card_state(card_id, new_state)
            return jsonify({"status": "ok", "new_state": new_state})

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

        return render_template("draft.html",
            business_name=business_name, card=card,
            treatment=treatment, hook_options=hook_options,
            draft=_parse_draft_for_display(existing_draft))

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
        return d

    @app.route("/api/draft/<int:card_id>/generate", methods=["POST"])
    def draft_generate(card_id):
        """Generate a draft from an approved idea card + all modules (T3.5)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        card = store.get_idea_card(card_id)
        if not card:
            return jsonify({"error": "Card not found"}), 404

        # Card must be approved or capture_fulfilled
        if card["card_state"] not in ("approved", "capture_fulfilled", "drafting", "drafted"):
            return jsonify({"error": f"Card state is '{card['card_state']}' — must be approved or capture_fulfilled to draft"}), 400

        treatment = json.loads(card.get("treatment") or "{}")
        hook_options = json.loads(card.get("hook_options") or "[]")
        format_name = treatment.get("format", {}).get("format_name", "")
        scope = treatment.get("scope", {}).get("type", "")

        # Load ALL modules
        modules = _load_all_modules(business_slug)

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

        from llm_adapter import LLMAdapter, LLMAdapterError
        from pipeline import DRAFT_SCHEMA

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        try:
            result = adapter.complete(
                prompt_file="draft/generate_v1.md",
                variables={
                    "business_name": business["business"]["name"],
                    "audience_description": business.get("audience_description", ""),
                    "origin": card["origin"],
                    "format_name": format_name,
                    "scope": scope,
                    "idea": card["idea"],
                    "hook_options": "\n".join(f"- {h}" for h in hook_options),
                    "voice_profile": modules.get("voice-profile", "(not built)")[:3000],
                    "tells_checklist": _extract_tells_checklist(modules.get("voice-profile", "")),
                    "story_frameworks": modules.get("story-frameworks", "(not built)")[:2000],
                    "audience_insights": modules.get("audience-insights", "(not built)")[:2000],
                    "viral_patterns": modules.get("viral-patterns", "(not built)")[:2000],
                    "visual_style": modules.get("visual-style", "(not built)")[:2000],
                    "format_guide": modules.get("format-guide", "(not built)")[:2000],
                    "capture_material": capture_text[:2000] if capture_text else "(none)",
                },
                schema=DRAFT_SCHEMA,
                backend="drafter",
                context=f"Draft generation for card {card_id} ({card['origin']}, {format_name})",
                business_slug=business_slug,
            )
        except (LLMAdapterError, Exception) as e:
            return jsonify({"error": str(e)}), 500

        # Create or update draft record
        existing = None
        for d in store.list_drafts(business_slug):
            if d["idea_card_id"] == card_id:
                existing = d
                break

        if existing:
            store.save_draft_content(
                existing["id"],
                result["draft_text"],
                result["visual_direction"],
                result["self_audit_flags"],
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
                result["draft_text"],
                result["visual_direction"],
                result["self_audit_flags"],
            )

        # Update card state to 'drafted'
        store.update_card_state(card_id, "drafted")

        return jsonify({
            "status": "ok",
            "draft_id": draft_id,
            "draft_text": result["draft_text"],
            "visual_direction": result["visual_direction"],
            "self_audit_flags": result["self_audit_flags"],
        })

    def _extract_tells_checklist(voice_profile_md: str) -> str:
        """Extract the Tells Checklist section from the Voice Profile module."""
        if not voice_profile_md or voice_profile_md.startswith("("):
            return "(Voice Profile not built — no Tells Checklist available)"
        # Look for the Tells Checklist section
        import re
        match = re.search(r'##\s*Tells\s*Checklist\s*\n(.+?)(?=\n##\s|$)', voice_profile_md, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return "(Tells Checklist section not found in Voice Profile)"

    # ── T3.6: Human pass UI (Gate 2) ──

    @app.route("/api/draft/<int:draft_id>/feedback", methods=["POST"])
    def draft_feedback(draft_id):
        """Add feedback to a draft (chip, text, or direct edit)."""
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

        if feedback_type not in ("chip", "text", "direct_edit"):
            return jsonify({"error": "Invalid feedback type"}), 400
        if not feedback_text:
            return jsonify({"error": "No feedback text provided"}), 400

        entry_id = store.add_feedback(
            business_slug=business_slug,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            draft_id=draft_id,
            line_reference=line_reference,
        )

        # If direct edit, save the edit
        if feedback_type == "direct_edit":
            edits = json.loads(draft.get("human_edits") or "{}")
            edits[line_reference or f"edit_{entry_id}"] = feedback_text
            store.save_human_edits(draft_id, edits)

        return jsonify({"status": "ok", "feedback_id": entry_id})

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
        if action not in ("ship", "kill", "revise"):
            return jsonify({"error": "Invalid action. Use ship, kill, or revise."}), 400

        if action == "ship":
            store.update_draft_state(draft_id, "shipped")
            # Update card state
            store.update_card_state(draft["idea_card_id"], "drafted")
            return jsonify({"status": "ok", "new_state": "shipped"})
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

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
            platforms = config["business"].get("platforms", [])
        except ConfigError:
            business_name = "Not configured"
            platforms = []

        return render_template("assets.html",
            business_name=business_name, draft=draft,
            assets=assets, visual_direction=visual_direction,
            platforms=platforms)

    @app.route("/api/assets/<int:draft_id>/fan-out", methods=["POST"])
    def assets_fan_out(draft_id):
        """T3.7: Generate per-platform variants from a shipped draft."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        draft = store.get_draft(draft_id)
        if not draft:
            return jsonify({"error": "Draft not found"}), 404
        if draft["draft_state"] != "shipped":
            return jsonify({"error": f"Draft state is '{draft['draft_state']}' — must be 'shipped' to fan out"}), 400

        try:
            config = load_all(app.config["CONFIG_DIR"])
            models_config = config["models"]
            business = config["business"]
        except ConfigError as e:
            return jsonify({"error": f"Config error: {e}"}), 500

        platforms = business.get("platforms", [])
        visual_direction = json.loads(draft.get("visual_direction") or "{}")

        # For each platform, generate a variant via LLM
        from llm_adapter import LLMAdapter, LLMAdapterError

        adapter = LLMAdapter(models_config, db_path=app.config["DB_PATH"], prompts_dir="prompts")

        assets_created = []
        for platform in platforms:
            platform_name = platform["name"]
            variant_schema = {
                "type": "object",
                "required": ["content", "variant_type"],
                "properties": {
                    "content": {"type": "string"},
                    "variant_type": {"type": "string"},
                    "image_prompts": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            }

            try:
                result = adapter.complete(
                    prompt_file="assets/fan_out_v1.md",
                    variables={
                        "business_name": business["business"]["name"],
                        "platform_name": platform_name,
                        "platform_handle": platform.get("handle", ""),
                        "draft_text": draft["draft_text"][:4000],
                        "visual_direction": json.dumps(visual_direction)[:1000],
                        "format": draft.get("format", ""),
                    },
                    schema=variant_schema,
                    backend="default",
                    context=f"Asset fan-out for draft {draft_id} → {platform_name}",
                    business_slug=business_slug,
                )
            except (LLMAdapterError, Exception) as e:
                # Continue with other platforms even if one fails
                continue

            asset_id = store.create_asset(
                business_slug=business_slug,
                draft_id=draft_id,
                platform=platform_name,
                variant_type=result.get("variant_type", "post"),
                content=result["content"],
                image_prompts=result.get("image_prompts", []),
            )
            assets_created.append({"id": asset_id, "platform": platform_name})

        return jsonify({"status": "ok", "assets": assets_created, "count": len(assets_created)})

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

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        return render_template("publish.html",
            business_name=business_name, draft=draft,
            approved_assets=approved_assets)

    @app.route("/api/assets/<int:asset_id>/schedule", methods=["POST"])
    def schedule_publish(asset_id):
        """T3.12: Schedule an approved asset for publish (go + timing)."""
        business_slug = _get_business_slug()
        if not business_slug:
            return jsonify({"error": "Business not configured"}), 500

        store = _get_pipeline_store()
        asset = store.get_asset(asset_id)
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        if asset["asset_state"] != "approved":
            return jsonify({"error": "Asset must be approved first"}), 400

        scheduled_at = request.json.get("scheduled_at", "")
        if scheduled_at:
            store.set_asset_schedule(asset_id, scheduled_at)
            store.update_asset_state(asset_id, "published")
            return jsonify({"status": "ok", "scheduled_at": scheduled_at})
        else:
            # Hold — no schedule yet
            return jsonify({"status": "ok", "message": "Held — not scheduled"})

    # ── Create surface (dashboard for the co-production loop) ──

    @app.route("/create")
    def create_surface():
        """Create surface — overview of drafts and assets in the pipeline."""
        business_slug = _get_business_slug()
        if not business_slug:
            return "Business not configured", 500

        store = _get_pipeline_store()

        # Get all drafts and their states
        drafts = store.list_drafts(business_slug)
        idea_cards = store.list_idea_cards(business_slug)

        try:
            config = load_all(app.config["CONFIG_DIR"])
            business_name = config["business"]["business"]["name"]
        except ConfigError:
            business_name = "Not configured"

        # Categorize drafts
        shipped = [d for d in drafts if d["draft_state"] == "shipped"]
        ready = [d for d in drafts if d["draft_state"] == "draft_ready"]
        drafting = [d for d in drafts if d["draft_state"] == "drafting"]

        return render_template("create.html",
            business_name=business_name,
            idea_cards=idea_cards,
            drafts=drafts,
            shipped=shipped, ready=ready, drafting=drafting)

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "version": "0.2.0"})

    return app


# For development
if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=9121, debug=True)