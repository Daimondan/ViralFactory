# Deployment artifacts for ViralFactory
#
# These files document the deployment posture and are versioned in the repo.
# The LIVE copies live on the VPS at their respective system paths.
#
# ## Files
#
# | File | Live path on VPS | Purpose |
# |------|-------------------|---------|
# | `traefik/viralfactory.yml` | `/docker/traefik/dynamic/viralfactory.yml` | Traefik dynamic config: routes vf.glenbeu.com → localhost:9121 with basicauth |
# | `viralfactory.service` | `/etc/systemd/system/viralfactory.service` | systemd unit: runs gunicorn on port 9121 |
# | `env.example` | `/etc/viralfactory/env` (create from this template) | Environment variables for the service (OLLAMA_API_KEY) |
#
# ## Dependency installation
#
# Three requirement files, chained with `-r` so they never drift:
#
# | File | Installs | Use when |
# |------|----------|----------|
# | `requirements.txt` | Core runtime (Flask, gunicorn, PyYAML, requests, Pillow, numpy) | Minimal deploy — app boots, UI works, no media processing |
# | `requirements-media.txt` | Everything in core + media/ML packages | Production — full capability |
# | `requirements-dev.txt` | Everything in media + pytest, edge-tts | Development and testing |
#
# ```bash
# python3 -m venv .venv
# .venv/bin/python -m pip install -r requirements-dev.txt   # or requirements-media.txt for prod
# ```
#
# **What is lost when `requirements-media.txt` is skipped:** audio
# transcription (faster-whisper), face identity QC (insightface, onnxruntime,
# opencv), PDF and DOCX material ingestion (pdfplumber, PyPDF2, python-docx),
# composition previews (matplotlib), RSS and article extraction (feedparser,
# trafilatura), image generation (fal-client), and VO generation (chatterbox,
# torchaudio). All degrade gracefully — the app does not crash — but those
# features report "unavailable" rather than producing output.
#
# ## Deployment steps
#
# 1. **Install dependencies:**
#    ```bash
#    cd /home/daimon/ViralFactory
#    python3 -m venv .venv
#    .venv/bin/python -m pip install -r requirements-media.txt
#    ```
#
# 2. **systemd service:**
#    ```bash
#    sudo cp deploy/viralfactory.service /etc/systemd/system/viralfactory.service
#    sudo mkdir -p /etc/viralfactory
#    sudo tee /etc/viralfactory/env << 'EOF'
#    OLLAMA_API_KEY=your_actual_key
#    EOF
#    sudo systemctl daemon-reload
#    sudo systemctl enable viralfactory
#    sudo systemctl start viralfactory
#    ```
#
# 3. **Traefik dynamic config:**
#    ```bash
#    sudo cp deploy/traefik/viralfactory.yml /docker/traefik/dynamic/viralfactory.yml
#    # Create the users file (basicauth — NOT committed to repo):
#    sudo htpasswd -nbB daimon 'your_password' | sudo tee /docker/traefik/dynamic/vf-users.txt
#    ```
#    Traefik picks up dynamic config changes automatically (no restart needed).
#
# 4. **DNS A record:**
#    Create `vf.glenbeu.com` A record → `2.24.127.70`.
#    Do NOT create this until steps 1 and 2 are complete (per architect R10 posture).
#
# ## Security posture
#
# - Basicauth middleware is MANDATORY on the public route (R10).
# - The Flask app has no app-level auth; router auth is the only gate.
# - Tailscale access (http://100.96.184.48:9121) is the approved posture for early UI review.
# - The users file (`vf-users.txt`) holds bcrypt hashes and is NOT committed to the repo.
#
# ## SQLite backup
#
# The database runs in WAL mode (P0-4). WAL adds `-wal` and `-shm` sidecar
# files next to the database file (`data/viralfactory.db-wal`,
# `data/viralfactory.db-shm`). **All three files must be backed up together**
# or use the safe backup command:
#
# ```bash
# sqlite3 data/viralfactory.db ".backup /path/to/backup.db"
# ```
#
# Copying only the `.db` file without the `-wal` sidecar may lose recent
# transactions that have not yet been checkpointed.