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

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "ok", "version": "0.1.0"})

    return app


# For development
if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=9121, debug=True)