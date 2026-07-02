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

        # Get playbook runs if we have a slug
        runs = []
        if business_slug:
            runner = PlaybookRunner(db_path)
            runs = runner.list_runs(business_slug)

        return render_template("index.html",
            business_name=business_name,
            business_slug=business_slug,
            runs=runs,
        )

    @app.route("/onboard")
    def onboard():
        """Onboarding surface — list available playbooks."""
        playbooks = []
        pb_dir = app.config["PLAYBOOKS_DIR"]
        if os.path.isdir(pb_dir):
            for f in sorted(os.listdir(pb_dir)):
                if f.endswith(".md"):
                    playbook = PlaybookParser.parse(os.path.join(pb_dir, f))
                    playbooks.append({
                        "name": playbook.name,
                        "purpose": playbook.purpose[:200],
                        "version": playbook.file_version,
                        "num_steps": len(playbook.steps),
                        "has_gate": any(s.is_gate for s in playbook.steps),
                    })
        return render_template("onboard.html", playbooks=playbooks)

    @app.route("/onboard/<playbook_name>")
    def start_playbook(playbook_name):
        """Start or resume a playbook."""
        pb_path = os.path.join(app.config["PLAYBOOKS_DIR"], f"{playbook_name}.md")
        if not os.path.exists(pb_path):
            return "Playbook not found", 404

        playbook = PlaybookParser.parse(pb_path)
        config = load_all(app.config["CONFIG_DIR"])
        business_slug = config["business"]["business"]["slug"]

        runner = PlaybookRunner(app.config["DB_PATH"])
        run_id = runner.start_run(playbook.name, playbook.file_version, business_slug)
        run = runner.get_run(run_id)

        return render_template("playbook_run.html",
            playbook=playbook,
            run_id=run_id,
            run=run,
        )

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
        """Library surface — read-only browse of modules."""
        return render_template("library.html")

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

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "version": "0.1.0"})

    return app


# For development
if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=9121, debug=True)