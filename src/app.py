"""
ViralFactory — Flask Console

The web interface for the system. Server-rendered Flask + minimal JS.
Laptop-first, responsive to mobile.

M1 scope: Onboarding surface (playbook runner UI).
"""

import os
import json
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory

# Support both package and direct imports
try:
    from .config_loader import load_all, ConfigError
    from .playbook_runner import PlaybookParser, PlaybookRunner
except ImportError:
    from config_loader import load_all, ConfigError
    from playbook_runner import PlaybookParser, PlaybookRunner


def create_app(config_dir: str = "config", db_path: str = "data/viralfactory.db", playbooks_dir: str = "playbooks"):
    """Create and configure the Flask app."""
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
        from module_store import ModuleStore, voice_profile_to_markdown

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

        # Convert to markdown
        md = voice_profile_to_markdown(profile, business["business"]["name"], version)

        # Store as versioned module
        store = ModuleStore(modules_dir="modules")
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
        )

        # Record gate result
        runner.set_gate_result(run_id, "5", "approve" if approved else "park", note)
        runner.update_run(run_id, status="completed" if approved else "awaiting_gate")

        return jsonify({
            "status": "ok",
            "version": version,
            "path": path,
        })

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "version": "0.1.0"})

    return app


# For development
if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=9121, debug=True)