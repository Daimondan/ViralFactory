# MANIFEST — 2026-07-02 batch C (diagram v3.3 + ops flags)

Per Inbox Protocol v1.0. File, execute APPLY, one CHANGELOG entry.

## Files

| File | Destination | Action |
|---|---|---|
| system-overview-v3.3.svg | docs/diagrams/system-overview-v3.3.svg | ADD (leave v3.2 in place, superseded) |
| diagrams-README.md | docs/diagrams/README.md | REPLACE |
| MANIFEST-2026-07-02-C.md | docs/inbox/processed/ | (after filing) |

## APPLY

1. Update the diagram pointer in CONTEXT.md ("current as of Charter v3.2" → v3.3, new flow: Gather → Ideas+Treatment (Gate 1, debut) → Awaiting-Capture → Draft (Gate 2) → Assets (Gate 3) → Publish (Gate 4) → Learn).
2. **BLOCKING OPS (architect flag):** do NOT create the `vf.glenbeu.com` DNS A record until Traefik has an auth middleware (basicauth acceptable) on that router. The console currently has no app-level auth; public DNS without router auth violates the documented R10 posture. Tailscale-only access remains the approved posture until auth exists. Commit the Traefik dynamic config (with the auth middleware, secrets excluded) to the repo so the deployment posture is versioned.
3. Record the T2.6–T2.8 deferral formally: note in BUILD_PLAN M2 + PROGRESS.md that audio/voice tasks are resequenced after operator UI review, and that `review-w2` must NOT be tagged until T2.6–T2.8 land (or a divergence re-scopes M2). The operator end-to-end test may run without the speak-a-sample path in the interim; the full test re-runs when audio lands.
4. Confirm to the operator (in PROGRESS.md) the Tailscale console URL is the one to use for early UI review.
