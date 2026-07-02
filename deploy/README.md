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
# ## Deployment steps
#
# 1. **systemd service:**
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
# 2. **Traefik dynamic config:**
#    ```bash
#    sudo cp deploy/traefik/viralfactory.yml /docker/traefik/dynamic/viralfactory.yml
#    # Create the users file (basicauth — NOT committed to repo):
#    sudo htpasswd -nbB daimon 'your_password' | sudo tee /docker/traefik/dynamic/vf-users.txt
#    ```
#    Traefik picks up dynamic config changes automatically (no restart needed).
#
# 3. **DNS A record:**
#    Create `vf.glenbeu.com` A record → `2.24.127.70`.
#    Do NOT create this until steps 1 and 2 are complete (per architect R10 posture).
#
# ## Security posture
#
# - Basicauth middleware is MANDATORY on the public route (R10).
# - The Flask app has no app-level auth; router auth is the only gate.
# - Tailscale access (http://100.96.184.48:9121) is the approved posture for early UI review.
# - The users file (`vf-users.txt`) holds bcrypt hashes and is NOT committed to the repo.