# Build Progress — ViralFactory

> **Living document.** Updated every time a stage is started, completed,
> blocked, or changed. Any agent should be able to read this and know
> exactly where we are.

**Last Updated:** 2026-07-02
**Current Phase:** Pre-M0 — Claude architect review complete, all actions applied. Ready for M0 code.

---

## Overall Status

| Stage | Status | Notes |
|---|---|---|
| 0. Foundation | 🔄 | All architect actions applied. Charter v3.1 in place. BUILD_PLAN v1.1 in place. UI-DIRECTION patched. CONTEXT.md patched. 8 playbooks split into individual files. v2 backup task (T0.7) added. Ready to begin M0 code. |
| 1. Onboarding engine: Voice Profile | ⬜ | 8 playbooks ready in playbooks/. Awaits M0 foundations + runner. |
| 2. Remaining playbooks wired | ⬜ | Playbooks split. Awaits M0 + M1. |
| 3. Co-production loop | ⬜ | Direct-edit mode in BUILD_PLAN (T3.3). Drafter A/B at checkpoint. |
| 4. Publish + metrics automation | ⬜ | Postiz self-hosted confirmed. |
| 5. Inward learning loop | ⬜ | Async gate queue (superseding, age, no pressure). |
| 6. Outward research loop | ⬜ | Continuous from v1 of this phase. |
| 7. Generalization proof | ⬜ | Real near-term but not blocking v1. |

## What's Done
- [x] Repo created: https://github.com/Daimondan/ViralFactory (private)
- [x] Charter v3 grilled and amended (5 divergences documented in DIVERGENCE-001)
- [x] Claude architect reviewed all 5 divergences — all APPROVED (some with refinements)
- [x] Charter v3.1 in place (supersedes v3; v3 in git history)
- [x] BUILD_PLAN v1.1 in place (fresh start, async gate, direct edit, v2 backup task T0.7, drafter A/B at M3)
- [x] CONTEXT.md patched (hierarchy ruling: conforms to charter, not "source of truth"; 3 open questions resolved)
- [x] UI-DIRECTION.md patched (laptop-first, voice available not assumed, direct-edit mode in draft view, async gate)
- [x] Operating loop reviewed and patched (weekly = architect review, not product gate)
- [x] 8 playbooks split into individual files in playbooks/
- [x] CHANGELOG.md with all decisions logged
- [x] Directory structure created (config/, prompts/, playbooks/, modules/, src/, tests/, docs/)

## What's Next
- [ ] T0.7: Scripted, verified backup of v2 SQLite database
- [ ] Begin M0: T0.1 (repo layout verified) → T0.2 (config loader) → T0.3 (LLM adapter) → ...
- [ ] Tag review-w1 when M0 completes