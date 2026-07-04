# DIVERGENCE-008 — Postiz → Buffer swap (silent override, now ratified)

**Filed:** 2026-07-04
**Filed by:** Architect (discovered during review)
**Status:** APPROVED by operator — ratified as a filed divergence

## What happened

The charter (CHARTER-v3.3), CONTEXT.md, AMENDMENT-003, and multiple CHANGELOG entries (notably line 428: "Postiz for publishing (not Buffer)") all specify **Postiz** as the publishing/metrics platform. The original rationale (CHANGELOG 2026-07-02) was explicit:

> "Buffer's GraphQL API is more complex and its media handling is a dealbreaker for a system that produces text + images + video."

Despite this, the builder silently swapped Postiz for Buffer:
- `src/buffer_adapter.py` created with header "replaces Postiz for M4"
- `src/app.py` imports `BufferAdapter` in all publish/metrics routes
- `src/postiz_adapter.py` still exists but is dead code (nothing imports it)
- `config/models.yaml` has a `buffer:` block with channel IDs, no Postiz config
- The published page references Buffer status checks

**No divergence was filed. No changelog entry explains the swap.** This is exactly the silent override the charter forbids: "conflicts are divergences, never silent overrides."

## Why the swap happened

Operator confirmation (2026-07-04): "yes we switched to buffer as its cheap to use now."

The operator made a cost-driven decision to use Buffer instead of Postiz. This is a legitimate operational decision — the operator owns the stack. The problem is procedural: the decision was not filed as a divergence before or during implementation.

## What this conflicts with in the charter

1. **AMENDMENT-003** — "Approved pieces flow to Postiz for scheduling, posting, and metrics."
2. **CONTEXT.md** — "Postiz (self-hosted or cloud) for publishing + analytics"
3. **CHANGELOG 2026-07-02** — "Postiz for publishing (not Buffer)" with explicit rationale against Buffer
4. **Document hierarchy rule** — "conflicts are divergences, never silent overrides"

## Architect ruling: APPROVED

The operator confirms the swap is intentional. Buffer is the publishing platform going forward. The original rationale against Buffer (media handling) is the operator's call to make — they have the operational context.

### Conditions

1. **This divergence is the formal record.** It replaces the silent override.
2. **The dead `src/postiz_adapter.py` must be removed** — dead code that contradicts the live system is a defect.
3. **CONTEXT.md must be updated** — every reference to Postiz becomes Buffer.
4. **AMENDMENT-003 text must be amended** — "Postiz" → "Buffer" in the publish stage description. This is a minor amendment to AMENDMENT-003, not a new amendment.
5. **The published page template** already references Buffer correctly — no change needed there.
6. **Config naming**: the `buffer:` block in `models.yaml` is correct. The `postiz:` block (if any remains) should be removed.

### What the builder must do

1. Delete `src/postiz_adapter.py`
2. Remove any Postiz references from `config/models.yaml`
3. Update CONTEXT.md: all "Postiz" → "Buffer"
4. Add a CHANGELOG entry: "STRUCTURE — Postiz→Buffer swap ratified per DIVERGENCE-008"
5. Update tests that reference PostizAdapter to reference BufferAdapter

## What this does NOT change

- **Per-piece approval before publish** — still a hard rule. Buffer is the transport, not the gate.
- **No auto-publish** — Buffer posts only after explicit Gate 4 approval.
- **Failures are surfaced** — Buffer down → pieces stay in queue, never lost.
- **Config-driven** — Buffer API key, channel IDs from config, not code.

## Lessons

1. **The operator can change the stack at any time.** When they do, the builder must file a divergence BEFORE implementing — not after.
2. **Dead code that contradicts the live system is a defect.** `postiz_adapter.py` should have been deleted in the same commit that created `buffer_adapter.py`.
3. **The changelog is the record.** A decision that isn't in the changelog didn't happen.