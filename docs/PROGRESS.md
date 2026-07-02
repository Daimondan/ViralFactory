# Build Progress — ViralFactory

> **Living document.** Updated every time a stage is started, completed,
> blocked, or changed. Any agent should be able to read this and know
> exactly where we are.

**Last Updated:** 2026-07-02
**Current Phase:** Pre-M0 — Foundation docs written, awaiting Claude architect review of divergences

---

## Overall Status

| Stage | Status | Notes |
|---|---|---|
| 0. Foundation | 🔄 | Repo layout created. CONTEXT.md, CHANGELOG.md, divergence note written. BUILD_PLAN needs update. Awaiting Claude review of DIVERGENCE-001. |
| 1. Onboarding engine: Voice Profile | ⬜ | Playbook exists (voice-profile-builder.md). Needs repo move + prompt templates + runner. |
| 2. Remaining playbooks wired | ⬜ | 7 playbooks written (playbooks-remaining-seven.md). Need split into individual files + prompts. |
| 3. Co-production loop | ⬜ | Core loop. Direct-edit mode added (divergence from charter). |
| 4. Publish + metrics automation | ⬜ | Postiz integration. Self-host vs cloud TBD. |
| 5. Inward learning loop | ⬜ | Async gate queue (not weekly sitting). |
| 6. Outward research loop | ⬜ | Continuous from v1. |
| 7. Generalization proof | ⬜ | Real near-term plan but not blocking v1. |

## What's Done
- [x] Repo created: https://github.com/Daimondan/ViralFactory (private)
- [x] Charter v3 reviewed and grilled (2026-07-02)
- [x] 5 divergences from charter identified and documented (DIVERGENCE-001)
- [x] CONTEXT.md written with locked-down terms, workflows, rules, edge cases
- [x] CHANGELOG.md created with all decisions logged
- [x] Directory structure created (config/, prompts/, playbooks/, modules/, src/, tests/, docs/)

## What's Next
- [ ] Claude (architect) reviews DIVERGENCE-001 and updates Charter to v3.1
- [ ] BUILD_PLAN.md updated: remove "extend existing app", reflect fresh start + laptop-first + async gate + direct edit
- [ ] Move existing playbooks into `playbooks/` directory (split playbooks-remaining-seven.md into individual files)
- [ ] Move existing docs into `docs/` (Charter → docs/, INTAKE → docs/, UI-DIRECTION → docs/)
- [ ] Write config schema files (business.yaml, models.yaml, sources.yaml)
- [ ] Resolve open question: module storage (repo markdown vs OB1)
- [ ] Resolve open question: Postiz self-host vs cloud
- [ ] Begin M0: Foundations (config loader, LLM adapter, validator, provenance, cache)

## Blockers
- Awaiting Claude architect review of DIVERGENCE-001 before updating Charter to v3.1
- 5 open questions in CONTEXT.md (module storage, Postiz deployment, LLM backend, context window strategy, video scope) — none block M0, but #1-3 should be resolved before M2