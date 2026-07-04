# DIVERGENCE-009: Architect↔Builder Webhook Notification Loop

**Filed by:** Architect  
**Date:** 2026-07-04  
**Status:** IMPLEMENTED — ACTIVE  
**Type:** Infrastructure / OPS  

## Problem

The architect and builder are two separate Hermes profiles that communicate through the repo (docs/inbox, docs/reviews, docs/decisions). Neither has a live messaging channel. When the architect leaves a review, the builder has no way to know it arrived — and vice versa when the builder pushes progress. The operator (Daimon) has to manually relay "go check the repo" between the two agents.

## Approved Solution

An asymmetric notification pipeline:

- **Architect → Builder: webhook on every push.** Every architect push is meaningful (corrections, reviews, design decisions, inbox items). The builder always wakes up and checks for new work. The architect should be disciplined: don't push when there's nothing to change.
- **Builder → Architect: cron job, every 2 hours, batched.** Not every builder push triggers a review. A cron job checks for new commits since the last review, filters for significance (code changes, milestones, divergences), and only triggers the architect when there's something worth reviewing. Minor changes (docs, changelog, typos) pile up until something significant lands.

Both agent responses are delivered to Daimon's WhatsApp so he always knows what happened.

### Architecture

```
  Architect pushes to GitHub
         │
         ▼
  GitHub sends webhook POST
         │
         ├──→ /p/viralfactory/webhooks/architect-pushed
         │         │
         │         ▼
         │    Builder profile wakes up
         │    Agent: git pull → read inbox/reviews/decisions
         │    → apply corrections → continue BUILD_PLAN
         │    → WhatsApp summary to Daimon
         │
         ▼
  Builder pushes to GitHub (any number of commits)
         │
         ▼
  Cron job runs every 2 hours
         │
         ├── Check git log since last review marker
         ├── Any significant commits? (feat:/fix:/refactor:/divergence)
         │     │
         │     ├── YES → trigger architect profile
         │     │         Agent: git pull → charter compliance review
         │     │         → write findings → update docs
         │     │         → WhatsApp summary to Daimon
         │     │
         │     └── NO (only minor doc/changelog tweaks) → skip, pile up
         │
         ▼
  No infinite loop — builder pushes don't webhook-trigger architect
```

### Why Asymmetric?

| Direction | Mechanism | Why |
|-----------|----------|-----|
| Architect → Builder | Webhook (every push) | Architect pushes are infrequent and always actionable — corrections, reviews, inbox items with manifests. The builder needs to know immediately. |
| Builder → Architect | Cron (every 2h, batched) | Builder pushes frequently — many are minor fixes, doc updates, test additions. Triggering a full charter compliance review on every push wastes tokens and creates ping-pong noise. Batching lets minor changes accumulate until something significant lands. |

### What Each Side Does

**`architect-pushed` route (triggers builder):**

When the architect pushes to the repo, the builder profile wakes up and:
1. Does a fresh `git pull` of the repo
2. Checks `docs/inbox/` for new manifest items (ADD/REPLACE/SUPERSEDE)
3. Checks `docs/reviews/` for new review files
4. Checks `docs/decisions/` for new divergence/amendment files
5. Reads them carefully
6. Applies corrections that affect the current BUILD_PLAN task
7. If inbox items have a MANIFEST, follows the filing protocol (read manifest → apply items → move manifest to processed/ → log to CHANGELOG)
8. Reports what was found and what was done → delivered to Daimon's WhatsApp

**Builder→Architect cron (batched review):**

Every 2 hours, a cron job runs a script that:
1. Checks `git log` since the last review marker (a file `docs/reviews/.last-reviewed-commit`)
2. Filters commits: only `feat:`, `fix:`, `refactor:` prefixes, or commits touching `src/*.py`, or divergence filings in `docs/decisions/` count as significant
3. If significant changes exist → triggers the architect profile with a prompt describing what changed
4. If only minor changes (docs, changelog, typos) → skips, lets them pile up
5. Architect reviews diff for charter compliance, writes findings, updates docs
6. Reports → delivered to Daimon's WhatsApp

### How to Turn It Off Temporarily

**Option A — Disable individual webhook route (recommended for architect→builder):**
Set `enabled: false` on the route in `~/.hermes/config.yaml`:
```yaml
platforms:
  webhook:
    extra:
      routes:
        architect-pushed:
          enabled: false    # ← stops builder from being triggered
```
Then restart the gateway. The webhook endpoint stays up (returns 403) but no agent session triggers.

To re-enable: set `enabled: true` (or remove the `enabled` key) and restart.

**Option B — Pause the cron job (recommended for builder→architect):**
```bash
hermes cron list        # find the job ID
hermes cron pause <id> # stops the batched review
hermes cron resume <id> # re-enables
```

**Option C — Disable the entire webhook platform:**
Remove `WEBHOOK_ENABLED=true` from `~/.hermes/.env`, restart gateway. Webhook HTTP server won't bind at all.

**Option D — Kill the Tailscale Funnel:**
```bash
tailscale funnel reset    # closes public endpoint
tailscale funnel 8644     # re-opens
```

**Option E — Delete GitHub webhook from the repo:**
GitHub repo Settings → Webhooks → delete. Re-add later via `gh` CLI.

### What's Already Wired Up (but Disabled)

1. ✅ **Hermes webhook platform** — configured on the default profile, listening on port 8644, route `architect-pushed` defined with `enabled: false`
2. ✅ **Multi-profile multiplexing** — `gateway.multiplex_profiles: true` is set
3. ✅ **HMAC secret** — generated and stored in route config
4. ✅ **Env vars** — `WEBHOOK_ENABLED=true`, `WEBHOOK_PORT=8644`, `WEBHOOK_SECRET=<secret>` in `.env`
5. ✅ **WhatsApp** — default profile has WhatsApp connected, home channel configured

### Implementation Steps (Approved)

1. **Tailscale Funnel** — `tailscale funnel 8644` to expose the webhook endpoint publicly with HTTPS
2. **GitHub Webhook** — Add one webhook to the repo: `architect-pushed` route, `push` events, HMAC secret
3. **WhatsApp delivery** — Set `deliver: whatsapp` and `deliver_extra.chat_id` on the `architect-pushed` route
4. **Cron job** — Create the batched builder→architect review cron job (every 2h, significance filter, triggers architect profile)
5. **Enable route** — Set `enabled: true` on `architect-pushed` route
6. **Restart gateway** — Pick up all config changes
7. **Test end-to-end** — Push a test commit, verify builder wakes up and WhatsApp notification arrives

### Security Considerations

- **HMAC-SHA256 signature validation** — GitHub signs every webhook payload. Hermes validates before processing. Invalid signatures rejected with 401.
- **Rate limiting** — 30 requests per minute per route (configurable).
- **Idempotency** — Duplicate deliveries (GitHub retries) deduplicated via `X-GitHub-Delivery` header.
- **Port exposure** — Tailscale Funnel exposes port 8644. Only `/webhooks/<route>` path served.
- **Agent session isolation** — Each webhook creates a fresh agent session with the target profile's config.

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Infinite loop (architect push → builder triggered → builder pushes → architect triggered) | Asymmetric design: builder pushes DON'T webhook-trigger architect. Cron batches instead. Builder prompt is idempotent (nothing new → does nothing → doesn't push). |
| Agent burns tokens on trivial pushes | Architect pushes always trigger (they're infrequent and actionable). Builder pushes are batched via cron with significance filter. |
| Webhook endpoint down | GitHub retries for 24h. Tailscale auto-reconnects. systemd restarts gateway. |
| Agent makes unapproved changes | Architect only writes docs. Builder only applies filed corrections. Per-piece approval is a charter hard rule. |
| Cron job triggers when nothing significant changed | Script checks commit significance before triggering. Minor changes pile up. |

### Charter Compliance

- ✅ **Config-driven** — Routes, prompts, secrets in config.yaml, not code
- ✅ **No hardcoded business values** — Prompts reference repo URL and doc paths (environment config)
- ✅ **LLM does judgment** — Agent reads diffs, makes charter compliance assessments
- ✅ **Per-piece approval** — Unaffected. This is agent-to-agent notification, not content publishing
- ✅ **Fresh start** — No migration needed

## Operator Decisions (Approved 2026-07-04)

1. ✅ **Approve the design** — YES
2. ✅ **Expose port 8644 via Tailscale Funnel** — YES
3. ✅ **WhatsApp delivery from both agents** — YES
4. ✅ **Commit-prefix filtering / batching** — YES (asymmetric: webhook for architect→builder, cron for builder→architect)